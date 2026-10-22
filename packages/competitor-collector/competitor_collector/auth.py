"""Local account and session storage for the collector's optional HTTP server.

There is no registration or default account. The first administrator and local
administrator recovery must be invoked from a trusted local CLI. HTTP handlers
are responsible for secure cookies and checking the session's CSRF token.
Only safe user records leave this module; passwords and bearer tokens are never
stored in plaintext. SQLite transactions also serialize updates across multiple
AuthStore instances, not only threads sharing one Python object.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import math
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from uuid import uuid4


SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3
SCRYPT_MAXMEM = 64 * 1024 * 1024
SCRYPT_DKLEN = 64
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_PAIR_FAILURE_LIMIT = 6
LOGIN_IP_FAILURE_LIMIT = 30
_USERNAME = re.compile(r"[A-Za-z0-9_.-]{3,64}\Z")
_LOGIN_ERROR = "用户名或密码不正确。"
_DUMMY_PASSWORD = "invalid-account-password"


class AuthError(Exception):
    """A deliberately safe message and HTTP-compatible status code."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> float:
    return time.time()


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")


def _password_valid(password: object) -> bool:
    if not isinstance(password, str) or not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        return False
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _validate_password(password: object) -> str:
    if not _password_valid(password):
        raise AuthError("密码长度必须为 10–128 个字符。")
    return password


def _validate_username(username: object) -> str:
    if not isinstance(username, str) or not _USERNAME.fullmatch(username):
        raise AuthError("用户名须为 3–64 位字母、数字、下划线、点或短横线。")
    return username


def _validate_role(role: object) -> str:
    if not isinstance(role, str) or role not in {"admin", "member"}:
        raise AuthError("账号角色只能为 admin 或 member。")
    return role


def _derive_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
        p=SCRYPT_P, maxmem=SCRYPT_MAXMEM, dklen=SCRYPT_DKLEN,
    )


def _password_record(password: str) -> tuple[bytes, bytes]:
    salt = secrets.token_bytes(16)
    return salt, _derive_password(password, salt)


def _safe_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "username": row["username"], "role": row["role"],
        "disabled": bool(row["disabled"]), "created_at": row["created_at"],
    }


def _token_hash(token: object) -> str | None:
    if not isinstance(token, str) or not token or len(token) > 256:
        return None
    return hashlib.sha256(token.encode("utf-8", errors="surrogatepass")).hexdigest()


class AuthStore:
    def __init__(self, db_path, session_ttl=28800):
        if isinstance(session_ttl, bool):
            raise ValueError("session_ttl must be a positive finite number")
        try:
            ttl = float(session_ttl)
        except (TypeError, ValueError) as exc:
            raise ValueError("session_ttl must be a positive finite number") from exc
        if not math.isfinite(ttl) or ttl <= 0:
            raise ValueError("session_ttl must be a positive finite number")
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_ttl = ttl
        self._lock = threading.RLock()
        self._dummy_salt, self._dummy_hash = _password_record(_DUMMY_PASSWORD)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_key TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN ('admin','member')),
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id);
                CREATE TABLE IF NOT EXISTS auth_login_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username_key TEXT NOT NULL,
                    remote_key TEXT NOT NULL,
                    occurred_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_failure_pair
                    ON auth_login_failures(username_key,remote_key,occurred_at);
                CREATE INDEX IF NOT EXISTS auth_failure_ip
                    ON auth_login_failures(remote_key,occurred_at);
                """
            )

    def _connect(self):
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @contextmanager
    def _transaction(self):
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

    @staticmethod
    def _active_user(connection, user):
        user_id = user.get("id") if isinstance(user, Mapping) else None
        if not isinstance(user_id, str) or not user_id or len(user_id) > 64:
            raise AuthError("请重新登录。", status=401)
        row = connection.execute("SELECT * FROM auth_users WHERE id=?", (user_id,)).fetchone()
        if row is None or row["disabled"]:
            raise AuthError("请重新登录。", status=401)
        return row

    @classmethod
    def _admin(cls, connection, actor):
        row = cls._active_user(connection, actor)
        if row["role"] != "admin":
            raise AuthError("只有管理员可以管理账号。", status=403)
        return row

    @staticmethod
    def _insert_user(connection, username, password, role):
        salt, password_hash = _password_record(password)
        user_id = uuid4().hex
        try:
            connection.execute(
                "INSERT INTO auth_users VALUES(?,?,?,?,?,?,?,?)",
                (user_id, username, username.casefold(), role, 0, salt, password_hash, _timestamp(_now())),
            )
        except sqlite3.IntegrityError as exc:
            raise AuthError("用户名已存在。", status=409) from exc
        return _safe_user(connection.execute("SELECT * FROM auth_users WHERE id=?", (user_id,)).fetchone())

    def has_users(self) -> bool:
        with self._transaction() as connection:
            return connection.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None

    def bootstrap_admin(self, username, password) -> dict:
        """Trusted local initialization only; the HTTP server must not expose it."""
        username = _validate_username(username)
        password = _validate_password(password)
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone():
                raise AuthError("账号库已初始化，不能重复创建首个管理员。", status=409)
            return self._insert_user(connection, username, password, "admin")

    def create_user(self, actor, username, password, role="member") -> dict:
        username = _validate_username(username)
        password = _validate_password(password)
        role = _validate_role(role)
        with self._transaction() as connection:
            self._admin(connection, actor)
            return self._insert_user(connection, username, password, role)

    def list_users(self, actor) -> list:
        with self._transaction() as connection:
            self._admin(connection, actor)
            return [_safe_user(row) for row in connection.execute("SELECT * FROM auth_users ORDER BY created_at,username_key")]

    def update_user(self, actor, user_id, *, disabled=None, role=None, password=None) -> dict:
        if not isinstance(user_id, str) or not user_id or len(user_id) > 64:
            raise AuthError("账号 ID 无效。")
        if disabled is not None and not isinstance(disabled, bool):
            raise AuthError("disabled 必须为布尔值。")
        if role is not None:
            role = _validate_role(role)
        if password is not None:
            password = _validate_password(password)
        with self._transaction() as connection:
            admin = self._admin(connection, actor)
            row = connection.execute("SELECT * FROM auth_users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("账号不存在。", status=404)
            target_role = row["role"] if role is None else role
            target_disabled = bool(row["disabled"]) if disabled is None else disabled
            if row["id"] == admin["id"] and (target_disabled or target_role != "admin"):
                raise AuthError("管理员不能禁用或降权自己的账号。", status=409)
            if row["role"] == "admin" and not row["disabled"] and (target_disabled or target_role != "admin"):
                count = connection.execute("SELECT COUNT(*) FROM auth_users WHERE role='admin' AND disabled=0").fetchone()[0]
                if count <= 1:
                    raise AuthError("必须保留至少一个可用管理员。", status=409)
            connection.execute("UPDATE auth_users SET role=?,disabled=? WHERE id=?", (target_role, int(target_disabled), user_id))
            if password is not None:
                salt, password_hash = _password_record(password)
                connection.execute("UPDATE auth_users SET password_salt=?,password_hash=? WHERE id=?", (salt, password_hash, user_id))
            if disabled is not None or role is not None or password is not None:
                connection.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
            return _safe_user(connection.execute("SELECT * FROM auth_users WHERE id=?", (user_id,)).fetchone())

    def authenticate(self, username, password, remote_addr="local") -> dict:
        """Generic failures; persistent username+IP and aggregate-IP rate limits."""
        valid_username = isinstance(username, str) and _USERNAME.fullmatch(username) is not None
        # Hash bounded identities in the failure table; do not store raw IPs.
        username_key = hashlib.sha256(str(username or "")[:256].casefold().encode("utf-8", errors="surrogatepass")).hexdigest()
        remote_key = hashlib.sha256(str(remote_addr or "local")[:256].encode("utf-8", errors="surrogatepass")).hexdigest()
        failure = None
        result = None
        with self._transaction() as connection:
            now = _now()
            connection.execute("DELETE FROM auth_login_failures WHERE occurred_at<=?", (now - LOGIN_WINDOW_SECONDS,))
            pair_count = connection.execute("SELECT COUNT(*) FROM auth_login_failures WHERE username_key=? AND remote_key=?", (username_key, remote_key)).fetchone()[0]
            ip_count = connection.execute("SELECT COUNT(*) FROM auth_login_failures WHERE remote_key=?", (remote_key,)).fetchone()[0]
            if pair_count >= LOGIN_PAIR_FAILURE_LIMIT or ip_count >= LOGIN_IP_FAILURE_LIMIT:
                failure = AuthError("登录尝试过多，请 15 分钟后重试。", status=429)
            else:
                row = connection.execute("SELECT * FROM auth_users WHERE username_key=?", (username.casefold() if valid_username else "",)).fetchone()
                salt = bytes(row["password_salt"]) if row is not None else self._dummy_salt
                expected = bytes(row["password_hash"]) if row is not None else self._dummy_hash
                candidate = password if _password_valid(password) else _DUMMY_PASSWORD
                matched = hmac.compare_digest(_derive_password(candidate, salt), expected)
                if row is None or row["disabled"] or not _password_valid(password) or not matched:
                    connection.execute("INSERT INTO auth_login_failures(username_key,remote_key,occurred_at) VALUES(?,?,?)", (username_key, remote_key, now))
                    failure = AuthError(_LOGIN_ERROR, status=401)
                else:
                    token = secrets.token_urlsafe(32)
                    csrf_token = secrets.token_urlsafe(32)
                    connection.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (now,))
                    connection.execute("INSERT INTO auth_sessions VALUES(?,?,?,?,?)", (_token_hash(token), row["id"], csrf_token, now, now + self.session_ttl))
                    connection.execute("DELETE FROM auth_login_failures WHERE username_key=? AND remote_key=?", (username_key, remote_key))
                    result = {"token": token, "csrf_token": csrf_token, "user": _safe_user(row)}
        # Raise only after committing failed-attempt counters.
        if failure is not None:
            raise failure
        return result

    def resolve_session(self, token) -> dict | None:
        token_hash = _token_hash(token)
        if token_hash is None:
            return None
        with self._transaction() as connection:
            now = _now()
            connection.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (now,))
            row = connection.execute(
                "SELECT u.*,s.csrf_token FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=? AND u.disabled=0",
                (token_hash,),
            ).fetchone()
            return {"user": _safe_user(row), "csrf_token": row["csrf_token"]} if row is not None else None

    def logout(self, token) -> None:
        token_hash = _token_hash(token)
        if token_hash is not None:
            with self._transaction() as connection:
                connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))

    def change_password(self, user, current_password, new_password) -> None:
        new_password = _validate_password(new_password)
        with self._transaction() as connection:
            row = self._active_user(connection, user)
            candidate = current_password if _password_valid(current_password) else _DUMMY_PASSWORD
            matched = hmac.compare_digest(_derive_password(candidate, bytes(row["password_salt"])), bytes(row["password_hash"]))
            if not _password_valid(current_password) or not matched:
                raise AuthError("当前密码不正确。", status=401)
            salt, password_hash = _password_record(new_password)
            connection.execute("UPDATE auth_users SET password_salt=?,password_hash=? WHERE id=?", (salt, password_hash, row["id"]))
            connection.execute("DELETE FROM auth_sessions WHERE user_id=?", (row["id"],))

    def recover_admin(self, username, password) -> dict:
        """Trusted local CLI only: reset an existing admin, never create/elevate.

        Account disabled status is preserved. This method is not an HTTP API.
        """
        username = _validate_username(username)
        password = _validate_password(password)
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM auth_users WHERE username_key=? AND role='admin'", (username.casefold(),)).fetchone()
            if row is None:
                raise AuthError("未找到该管理员账号；恢复操作不会新建或提升账号。", status=404)
            salt, password_hash = _password_record(password)
            connection.execute("UPDATE auth_users SET password_salt=?,password_hash=? WHERE id=?", (salt, password_hash, row["id"]))
            connection.execute("DELETE FROM auth_sessions WHERE user_id=?", (row["id"],))
            return _safe_user(row)
