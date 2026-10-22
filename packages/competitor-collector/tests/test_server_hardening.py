"""Offline filesystem/error regressions; no store or translation request."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
from uuid import uuid4
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from competitor_collector import server
from competitor_collector.server import CollectorApp, HTTPError


USER = {"id": "member-one", "username": "member_one", "role": "member"}


def test_windows_reparse_point_fallback_without_python312_junction_api():
    fake = SimpleNamespace(is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0x400))
    assert server.linked_path(fake)
    fake.lstat = lambda: SimpleNamespace(st_file_attributes=0)
    assert not server.linked_path(fake)


@pytest.fixture
def app(tmp_path):
    value = CollectorApp(tmp_path / "data", runner=lambda payload: {"listing": {"title": "Offline"}, "reviews": [], "warnings": []})
    yield value
    value.close()


def seed(app, status="completed", count=1):
    identifier = uuid4().hex
    directory = app.runs / identifier
    directory.mkdir()
    items = []
    for index in range(count):
        item_id = uuid4().hex
        (directory / item_id).mkdir()
        (directory / item_id / "reviews.csv").write_text("source\npublic", encoding="utf-8")
        items.append({"id": item_id, "status": status, "platform": "google_play", "app_id": f"com.example.app{index}", "error": ""})
    job = {"id": identifier, "owner_id": USER["id"], "owner_name": USER["username"],
           "status": status, "items": items, "completed": 0 if status == "queued" else count,
           "total": count, "created_at": server.now(), "request": {"countries": ["us"], "collect_listing": True, "collect_reviews": False, "download_screenshots": False}}
    app.jobs[identifier] = job
    app._persist(job)
    return job, directory


def test_validation_error_keeps_actionable_trusted_message(app):
    with pytest.raises(HTTPError, match="1–500") as caught:
        app.new_job(USER, {"entries": ["com.example.app"], "count_per_country": 501})
    assert caught.value.status == 400
    assert app.jobs == {}


def test_wrong_filter_type_is_client_error_not_server_crash(app):
    with pytest.raises(HTTPError, match="参数类型") as caught:
        app.new_job(USER, {"entries": ["com.example.app"], "sort": []})
    assert caught.value.status == 400


def test_item_directory_creation_failure_finishes_job(app, monkeypatch):
    job, _ = seed(app, status="queued")
    def fail(*args, **kwargs):
        raise OSError("private path diagnostic")
    monkeypatch.setattr(app, "_item_root", fail)
    app._run_job(job["id"])
    assert job["status"] == "failed"
    assert job["items"][0]["status"] == "failed"
    assert job["completed"] == 1
    assert "private" not in json.dumps(job)


def test_first_persist_failure_finishes_in_memory_even_if_disk_stays_broken(app, monkeypatch):
    job, _ = seed(app, status="queued", count=2)
    monkeypatch.setattr(app, "_persist", lambda job: (_ for _ in ()).throw(OSError("disk full")))
    app._run_job(job["id"])
    assert job["status"] == "failed" and job["completed"] == 2
    assert all(item["status"] == "failed" for item in job["items"])
    assert all(item["status"] not in {"queued", "running"} for item in job["items"])


def test_later_persist_failure_retains_completed_item_and_finishes_remaining(app, monkeypatch):
    job, _ = seed(app, status="queued", count=2)
    original = app._persist
    def persist(value):
        if value["completed"]:
            raise OSError("disk unavailable")
        original(value)
    monkeypatch.setattr(app, "_persist", persist)
    app._run_job(job["id"])
    assert job["status"] == "partial"
    assert job["items"][0]["status"] == "completed"
    assert job["items"][1]["status"] == "failed"
    assert job["completed"] == 2


def test_initial_queue_persistence_failure_does_not_leave_active_job(app, monkeypatch):
    monkeypatch.setattr(app, "_persist", lambda job: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(HTTPError) as caught:
        app.new_job(USER, {"entries": ["com.example.app"]})
    assert caught.value.status == 503
    assert all(job["status"] == "failed" for job in app.jobs.values())
    assert all(item["status"] == "failed" for job in app.jobs.values() for item in job["items"])


@pytest.mark.parametrize("scope", ["job", "item"])
def test_linked_job_or_item_roots_refused_for_file_and_archive(app, monkeypatch, scope):
    job, directory = seed(app)
    item_id = job["items"][0]["id"]
    linked = directory if scope == "job" else directory / item_id
    original = server.linked_path
    monkeypatch.setattr(server, "linked_path", lambda path: Path(path) == linked or original(path))
    with pytest.raises(HTTPError):
        app.evidence_file(USER, job["id"], item_id, "reviews.csv")
    with pytest.raises(HTTPError):
        app.archive(USER, job["id"])
    assert not list(directory.glob("download-*.zip"))


def test_nested_linked_directory_not_served_or_packed(app, monkeypatch):
    job, directory = seed(app)
    item_id = job["items"][0]["id"]
    nested = directory / item_id / "screenshots"
    nested.mkdir()
    (nested / "private.json").write_text("must-not-export", encoding="utf-8")
    original = server.linked_path
    monkeypatch.setattr(server, "linked_path", lambda path: Path(path) == nested or original(path))
    with pytest.raises(HTTPError):
        app.evidence_file(USER, job["id"], item_id, "screenshots/private.json")
    archive = app.archive(USER, job["id"])
    with zipfile.ZipFile(archive) as packed:
        assert not any("private" in name for name in packed.namelist())
        assert any(name.endswith("reviews.csv") for name in packed.namelist())


def test_startup_rejects_linked_job_directory(app, monkeypatch):
    job, directory = seed(app)
    original = server.linked_path
    monkeypatch.setattr(server, "linked_path", lambda path: Path(path) == directory or original(path))
    restarted = CollectorApp(app.data, runner=lambda payload: pytest.fail("must not collect on load"))
    try:
        assert job["id"] not in restarted.jobs
    finally:
        restarted.close()


def test_startup_rejects_linked_item_directory(app, monkeypatch):
    job, directory = seed(app)
    linked = directory / job["items"][0]["id"]
    original = server.linked_path
    monkeypatch.setattr(server, "linked_path", lambda path: Path(path) == linked or original(path))
    restarted = CollectorApp(app.data)
    try:
        assert job["id"] not in restarted.jobs
    finally:
        restarted.close()


def test_startup_refuses_linked_runs_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    original = server.linked_path
    monkeypatch.setattr(server, "linked_path", lambda path: Path(path) == data / "runs" or original(path))
    with pytest.raises(HTTPError):
        CollectorApp(data)


def test_real_symlink_to_other_directory_is_refused_when_supported(app, tmp_path):
    job, directory = seed(app)
    item_id = job["items"][0]["id"]
    nested = directory / item_id / "linked"
    external = tmp_path / "other-owner"
    external.mkdir()
    (external / "secret.json").write_text("private", encoding="utf-8")
    try:
        nested.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink permission unavailable; link predicate regressions still ran")
    with pytest.raises(HTTPError):
        app.evidence_file(USER, job["id"], item_id, "linked/secret.json")
    with zipfile.ZipFile(app.archive(USER, job["id"])) as packed:
        assert not any("secret" in name for name in packed.namelist())
