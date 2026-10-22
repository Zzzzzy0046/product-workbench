"""Offline account, credential, session and authorization regression tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import sys
import threading

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))
from competitor_collector import auth
from competitor_collector.auth import AuthError, AuthStore


ADMIN_PASSWORD = "admin-secret-2026"
MEMBER_PASSWORD = "member-secret-2026"


@pytest.fixture
def initialized(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    admin = store.bootstrap_admin("Owner", ADMIN_PASSWORD)
    return store, admin


def _rows(store, query, values=()):
    with closing(sqlite3.connect(store.db_path)) as connection:
        connection.row_factory = sqlite3.Row
        return list(connection.execute(query, values))


def test_no_default_account_or_password_and_bootstrap_only_once(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    assert store.has_users() is False
    with pytest.raises(AuthError) as failure:
        store.authenticate("admin", "admin-default-password")
    assert failure.value.status == 401
    admin = store.bootstrap_admin("Owner", ADMIN_PASSWORD)
    assert store.has_users() is True
    assert admin["role"] == "admin"
    assert admin["disabled"] is False
    assert set(admin) == {"id", "username", "role", "disabled", "created_at"}
    with pytest.raises(AuthError) as failure:
        store.bootstrap_admin("Another", ADMIN_PASSWORD)
    assert failure.value.status == 409


def test_scrypt_production_parameters_are_not_configured_from_user_input(monkeypatch, tmp_path):
    calls = []

    def scrypt(password, **kwargs):
        calls.append((password, kwargs))
        return b"x" * kwargs["dklen"]

    monkeypatch.setattr(auth.hashlib, "scrypt", scrypt)
    store = AuthStore(tmp_path / "parameters.sqlite3")
    store.bootstrap_admin("Owner", ADMIN_PASSWORD)
    assert len(calls) == 2  # dummy credential and real account
    for _, values in calls:
        assert values["n"] == 2**15
        assert values["r"] == 8
        assert values["p"] == 3
        assert values["maxmem"] >= 64 * 1024 * 1024
        assert values["dklen"] >= 32


def test_password_salts_are_unique_even_for_identical_passwords(initialized):
    store, admin = initialized
    first = store.create_user(admin, "member.one", MEMBER_PASSWORD)
    second = store.create_user(admin, "member.two", MEMBER_PASSWORD)
    rows = _rows(store, "SELECT password_salt,password_hash FROM auth_users WHERE id IN (?,?)", (first["id"], second["id"]))
    assert len(rows) == 2
    assert rows[0]["password_salt"] != rows[1]["password_salt"]
    assert rows[0]["password_hash"] != rows[1]["password_hash"]
    assert all(len(row["password_salt"]) >= 16 for row in rows)


def test_password_and_session_bearer_token_are_never_stored_in_plaintext(initialized):
    store, admin = initialized
    login = store.authenticate("owner", ADMIN_PASSWORD)
    row = _rows(store, "SELECT * FROM auth_sessions")[0]
    assert row["token_hash"] == hashlib.sha256(login["token"].encode()).hexdigest()
    assert row["token_hash"] != login["token"]
    assert login["csrf_token"] != login["token"]
    for path in store.db_path.parent.glob("auth.sqlite3*"):
        content = path.read_bytes()
        assert ADMIN_PASSWORD.encode() not in content
        assert login["token"].encode() not in content
    assert "password_hash" not in repr(store.list_users(admin))
    assert "password_salt" not in repr(login)


def test_case_insensitive_username_login_and_duplicate_rejected(initialized):
    store, admin = initialized
    assert store.authenticate("oWnEr", ADMIN_PASSWORD)["user"]["id"] == admin["id"]
    with pytest.raises(AuthError) as failure:
        store.create_user(admin, "owner", MEMBER_PASSWORD)
    assert failure.value.status == 409


def test_unicode_password_roundtrip_and_exact_preservation(initialized):
    store, admin = initialized
    password = "  我的密码-游戏截图🎮  "
    user = store.create_user(admin, "unicode-user", password)
    assert store.authenticate("unicode-user", password)["user"]["id"] == user["id"]
    with pytest.raises(AuthError):
        store.authenticate("unicode-user", password.strip())


@pytest.mark.parametrize("username,password", [
    ("ab", MEMBER_PASSWORD), ("x" * 65, MEMBER_PASSWORD),
    ("space user", MEMBER_PASSWORD), ("user/../../", MEMBER_PASSWORD),
    ("valid.user", "short"), ("valid.user", "x" * 129),
    ("valid.user", "bad-surrogate\ud800"),
])
def test_username_and_password_validation(initialized, username, password):
    store, admin = initialized
    with pytest.raises(AuthError) as failure:
        store.create_user(admin, username, password)
    assert failure.value.status == 400


def test_members_cannot_manage_users_or_spoof_their_role(initialized):
    store, admin = initialized
    member = store.create_user(admin, "member", MEMBER_PASSWORD)
    spoofed = {**member, "role": "admin"}
    for action in (
        lambda: store.create_user(spoofed, "another", MEMBER_PASSWORD),
        lambda: store.list_users(spoofed),
        lambda: store.update_user(spoofed, admin["id"], password=MEMBER_PASSWORD),
    ):
        with pytest.raises(AuthError) as failure:
            action()
        assert failure.value.status == 403


def test_sessions_are_independent_and_logout_removes_only_one(initialized):
    store, admin = initialized
    first = store.authenticate("Owner", ADMIN_PASSWORD)
    second = store.authenticate("Owner", ADMIN_PASSWORD)
    assert first["token"] != second["token"]
    assert first["csrf_token"] != second["csrf_token"]
    assert store.resolve_session(first["token"]) == {"user": admin, "csrf_token": first["csrf_token"]}
    store.logout(first["token"])
    assert store.resolve_session(first["token"]) is None
    assert store.resolve_session(second["token"]) is not None
    store.logout("unknown")  # idempotent


def test_session_expires_at_exact_ttl_and_unknown_tokens_are_rejected(monkeypatch, tmp_path):
    now = [1000.0]
    monkeypatch.setattr(auth, "_now", lambda: now[0])
    store = AuthStore(tmp_path / "ttl.sqlite3", session_ttl=2)
    store.bootstrap_admin("Owner", ADMIN_PASSWORD)
    session = store.authenticate("Owner", ADMIN_PASSWORD)
    now[0] = 1001.999
    assert store.resolve_session(session["token"]) is not None
    now[0] = 1002.0
    assert store.resolve_session(session["token"]) is None
    assert _rows(store, "SELECT * FROM auth_sessions") == []
    for token in (None, [], "", "x" * 257, "unknown"):
        assert store.resolve_session(token) is None


@pytest.mark.parametrize("change", ["disabled", "password", "role"])
def test_admin_account_changes_revoke_all_target_sessions(initialized, change):
    store, admin = initialized
    member = store.create_user(admin, "member", MEMBER_PASSWORD)
    sessions = [store.authenticate("member", MEMBER_PASSWORD) for _ in range(2)]
    values = {"disabled": True} if change == "disabled" else {"password": "new-password-2026"} if change == "password" else {"role": "admin"}
    updated = store.update_user(admin, member["id"], **values)
    assert updated["id"] == member["id"]
    assert all(store.resolve_session(session["token"]) is None for session in sessions)
    if change == "disabled":
        with pytest.raises(AuthError) as failure:
            store.authenticate("member", MEMBER_PASSWORD)
        assert failure.value.status == 401
        store.update_user(admin, member["id"], disabled=False)
        assert store.authenticate("member", MEMBER_PASSWORD)["user"]["disabled"] is False
    elif change == "password":
        with pytest.raises(AuthError):
            store.authenticate("member", MEMBER_PASSWORD)
        assert store.authenticate("member", "new-password-2026")["user"]["id"] == member["id"]


def test_self_service_password_change_requires_current_password_and_revokes_sessions(initialized):
    store, admin = initialized
    first = store.authenticate("Owner", ADMIN_PASSWORD)
    second = store.authenticate("Owner", ADMIN_PASSWORD)
    with pytest.raises(AuthError) as failure:
        store.change_password(admin, "incorrect-password", "new-password-2026")
    assert failure.value.status == 401
    assert store.resolve_session(first["token"]) is not None
    store.change_password(admin, ADMIN_PASSWORD, "new-password-2026")
    assert store.resolve_session(first["token"]) is None
    assert store.resolve_session(second["token"]) is None
    assert store.authenticate("Owner", "new-password-2026")["user"]["id"] == admin["id"]


def test_admin_cannot_disable_or_demote_itself_even_with_another_admin(initialized):
    store, admin = initialized
    store.create_user(admin, "second-admin", MEMBER_PASSWORD, role="admin")
    for values in ({"disabled": True}, {"role": "member"}):
        with pytest.raises(AuthError) as failure:
            store.update_user(admin, admin["id"], **values)
        assert failure.value.status == 409
    assert len([user for user in store.list_users(admin) if user["role"] == "admin" and not user["disabled"]]) == 2


def test_last_usable_admin_survives_cross_instance_concurrent_updates(initialized):
    store, first = initialized
    second = store.create_user(first, "second-admin", MEMBER_PASSWORD, role="admin")
    other_store = AuthStore(store.db_path)
    barrier = threading.Barrier(2)

    def disable(actor, target, instance):
        barrier.wait(timeout=5)
        try:
            instance.update_user(actor, target["id"], disabled=True)
            return "ok"
        except AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(disable, first, second, store), executor.submit(disable, second, first, other_store)]
        results = [future.result(timeout=15) for future in futures]
    assert results.count("ok") == 1
    assert results.count(401) == 1
    assert len(_rows(store, "SELECT id FROM auth_users WHERE role='admin' AND disabled=0")) == 1


def test_unknown_disabled_and_wrong_password_share_identical_failure(initialized):
    store, admin = initialized
    member = store.create_user(admin, "disabled-user", MEMBER_PASSWORD)
    store.update_user(admin, member["id"], disabled=True)
    errors = []
    for username, password in (("not-existing", MEMBER_PASSWORD), ("disabled-user", MEMBER_PASSWORD), ("Owner", "incorrect-password")):
        with pytest.raises(AuthError) as failure:
            store.authenticate(username, password)
        errors.append((str(failure.value), failure.value.status))
    assert len(set(errors)) == 1
    assert errors[0][1] == 401


def test_pair_rate_limit_persists_across_store_instances_then_expires(monkeypatch, initialized):
    store, _ = initialized
    now = [1000.0]
    monkeypatch.setattr(auth, "_now", lambda: now[0])
    for _ in range(auth.LOGIN_PAIR_FAILURE_LIMIT):
        with pytest.raises(AuthError) as failure:
            store.authenticate("Owner", "incorrect-password", remote_addr="198.51.100.1")
        assert failure.value.status == 401
    restarted = AuthStore(store.db_path)
    with pytest.raises(AuthError) as failure:
        restarted.authenticate("Owner", ADMIN_PASSWORD, remote_addr="198.51.100.1")
    assert failure.value.status == 429
    assert restarted.authenticate("Owner", ADMIN_PASSWORD, remote_addr="198.51.100.2")
    now[0] += auth.LOGIN_WINDOW_SECONDS
    assert restarted.authenticate("Owner", ADMIN_PASSWORD, remote_addr="198.51.100.1")


def test_ip_rate_limit_blocks_username_rotation(initialized, monkeypatch):
    store, _ = initialized
    # Exercise persistent limiter behavior without running 30 expensive KDFs.
    # The real KDF parameters and real password roundtrips are tested separately.
    monkeypatch.setattr(auth, "_derive_password", lambda password, salt: b"always-wrong" * 4)
    for index in range(auth.LOGIN_IP_FAILURE_LIMIT):
        with pytest.raises(AuthError) as failure:
            store.authenticate(f"unknown-{index}", MEMBER_PASSWORD, remote_addr="203.0.113.1")
        assert failure.value.status == 401
    with pytest.raises(AuthError) as failure:
        store.authenticate("Owner", ADMIN_PASSWORD, remote_addr="203.0.113.1")
    assert failure.value.status == 429


def test_local_recovery_only_resets_existing_admin_and_revokes_sessions(initialized):
    store, admin = initialized
    session = store.authenticate("Owner", ADMIN_PASSWORD)
    member = store.create_user(admin, "member", MEMBER_PASSWORD)
    assert store.recover_admin("OWNER", "recovery-password-2026")["id"] == admin["id"]
    assert store.resolve_session(session["token"]) is None
    assert store.authenticate("Owner", "recovery-password-2026")["user"]["id"] == admin["id"]
    for username in ("not-existing", member["username"]):
        with pytest.raises(AuthError) as failure:
            store.recover_admin(username, "recovery-password-2026")
        assert failure.value.status == 404


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), "invalid"])
def test_invalid_session_ttl_is_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        AuthStore(tmp_path / "invalid.sqlite3", session_ttl=value)
