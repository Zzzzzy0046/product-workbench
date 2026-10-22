"""Synthetic capture evidence travels with projects; execution access stays local."""

import io
import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from workbench import app


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path / "data", runner=lambda _: "unused")
    try:
        yield instance
    finally:
        instance.close()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def seed_capture(bench, status="completed"):
    project = bench.create_project("截图生命周期", "仅使用合成证据")
    version = bench.create_product_version(project["id"], {"name": "V1"})
    document = bench.add_document(project["id"], "走查说明.md", b"synthetic capture notes", version["id"])
    capture_id = "a" * 32
    directory = bench.data / "scrapes" / project["id"] / ("android-" + capture_id)
    session = {
        "id": capture_id,
        "project_id": project["id"],
        "version_id": version["id"],
        "document_ids": [document["id"]],
        "package": "com.example.synthetic",
        "serial": "synthetic-device",
        "title": "首页与设置",
        "scope": "仅首页与设置，跳过支付",
        "app_version": "1.2.3",
        "status": status,
        "created": "2026-10-22T10:00:00+08:00",
        "updated": "2026-10-22T10:02:00+08:00",
        "summary": "已记录两个页面。",
    }
    write_json(directory / "session.json", session)
    write_json(directory / "request.json", {
        **session,
        "capture_id": capture_id,
        "adb_path": "C:/LOCAL_EXECUTION_ONLY/adb.exe",
        "python_path": "C:/LOCAL_EXECUTION_ONLY/python.exe",
        "skill_root": "C:/LOCAL_EXECUTION_ONLY/skill",
        "session_dir": str(directory),
        "model": "synthetic-model",
        "connection": {"url": "http://127.0.0.1:55555", "token": "LOCAL_CONNECTION_SECRET"},
        "nested": {"mcp_url": "http://127.0.0.1:55555", "scope": "首页"},
    })
    observation = {
        "id": "obs-0123456789abcdef",
        "package": session["package"],
        "serial": session["serial"],
        "files": {"screenshot": "observations/obs-0123456789abcdef.png", "ui_xml": "observations/obs-0123456789abcdef.xml"},
        "captured_at": session["created"],
        "actionable": True,
    }
    write_json(directory / "observations" / "obs-0123456789abcdef.json", observation)
    (directory / "observations" / "obs-0123456789abcdef.png").write_bytes(b"SYNTHETIC_PNG_EVIDENCE")
    (directory / "observations" / "obs-0123456789abcdef.xml").write_bytes(b"<hierarchy><node text='Settings'/></hierarchy>")
    write_json(directory / "capture-session.json", {
        "package": session["package"], "serial": session["serial"],
        "status": "ready", "last_observation_id": observation["id"],
        "session_dir": str(directory),
        "pending_action": {"source_observation_id": observation["id"], "action": {"command": "preserve original evidence"}},
    })
    write_json(directory / "research-map.json", {"id": "map-unchanged", "observations": [observation]})
    (directory / "timings.jsonl").write_text('{"phase":"screenshot","seconds":0.1}\n', encoding="utf-8")
    (directory / "flow_export").mkdir()
    (directory / "flow_export" / "首页与设置.png").write_bytes(b"SYNTHETIC_MONTAGE")
    (directory / "flow_export" / "流程说明.md").write_text("合成流程说明", encoding="utf-8")
    for relative in (
        "attempts/first/prompt.md", "attempts/first/agent-output.md",
        "attempts/first/codex-diagnostics.log", "attempts/first/stdout-events.jsonl",
        "progress.jsonl", "model-events.jsonl", "prompt.md", ".capture.lock",
    ):
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("LOCAL_RAW_EXECUTION_ONLY", encoding="utf-8")
    return project, version, document, capture_id, directory


def replace_package_json(package, replacements):
    """Build a valid older/synthetic package without bypassing manifest checks."""
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    for name, value in replacements.items():
        files[name] = json.dumps(value, ensure_ascii=False).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    for item in manifest["files"]:
        item["size"] = len(files[item["path"]])
        item["sha256"] = hashlib.sha256(files[item["path"]]).hexdigest()
    files["manifest.json"] = json.dumps(manifest).encode()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return result.getvalue()


def test_project_package_keeps_capture_evidence_and_remaps_session_identity(bench):
    project, version, document, capture_id, directory = seed_capture(bench)
    evidence = {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file() and (path.parent.name in {"observations", "flow_export"} or path.name in {"research-map.json", "timings.jsonl"})
    }
    package, _ = bench.export_project(project["id"])
    prefix = f"scrapes/{project['id']}/android-{capture_id}/"
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        capture_names = [name for name in archive.namelist() if name.startswith(prefix)]
        exported_request = json.loads(archive.read(prefix + "request.json"))
        checkpoint = json.loads(archive.read(prefix + "capture-session.json"))
        assert exported_request["model"] == "synthetic-model"
        assert exported_request["package"] == "com.example.synthetic"
        assert exported_request["serial"] == "synthetic-device"
        assert exported_request["nested"] == {"scope": "首页"}
        assert "session_dir" not in checkpoint
        assert checkpoint["pending_action"]["action"] == {"command": "preserve original evidence"}
        assert not any("attempts/" in name or name.endswith(("progress.jsonl", "model-events.jsonl", "prompt.md", ".lock")) for name in capture_names)
        for relative, expected in evidence.items():
            assert archive.read(prefix + relative) == expected
        payload = b"".join(archive.read(name) for name in archive.namelist())
        assert b"LOCAL_EXECUTION_ONLY" not in payload
        assert b"LOCAL_RAW_EXECUTION_ONLY" not in payload
        assert b"LOCAL_CONNECTION_SECRET" not in payload
        assert str(directory).encode() not in payload

    copied = bench.import_project(package)
    copy_directories = list((bench.data / "scrapes" / copied["id"]).glob("android-*"))
    assert len(copy_directories) == 1
    copied_directory = copy_directories[0]
    copied_session = json.loads((copied_directory / "session.json").read_text(encoding="utf-8"))
    copied_request = json.loads((copied_directory / "request.json").read_text(encoding="utf-8"))
    copied_version = bench.product_versions(copied["id"])[0]
    copied_document = bench.rows("SELECT id FROM documents WHERE project_id=?", (copied["id"],))[0]
    assert copied_session["id"] != capture_id
    assert copied_directory.name == "android-" + copied_session["id"]
    assert copied_session["project_id"] == copied["id"] != project["id"]
    assert copied_session["version_id"] == copied_version["id"] != version["id"]
    assert copied_session["document_ids"] == [copied_document["id"]]
    assert copied_document["id"] != document["id"]
    assert copied_request["capture_id"] == copied_request["id"] == copied_session["id"]
    assert copied_request["project_id"] == copied["id"]
    assert copied_request["version_id"] == copied_session["version_id"]
    assert copied_request["document_ids"] == copied_session["document_ids"]
    assert copied_session["status"] == "completed"
    for relative, expected in evidence.items():
        assert (copied_directory / relative).read_bytes() == expected
    assert directory.is_dir()
    assert json.loads((directory / "session.json").read_text(encoding="utf-8"))["id"] == capture_id


@pytest.mark.parametrize("status", ["queued", "running", "prepared", "paused"])
def test_imported_capture_never_automatically_resumes(bench, status):
    project, _, _, _, _ = seed_capture(bench, status)
    package, _ = bench.export_project(project["id"])
    copied = bench.import_project(package)
    session_file = next((bench.data / "scrapes" / copied["id"]).glob("android-*/session.json"))
    session = json.loads(session_file.read_text(encoding="utf-8"))
    assert session["status"] == "interrupted"
    assert "重新检测" in session["pause_reason"]
    assert "未继续执行" in session["error"]


def test_import_sanitizes_local_execution_fields_from_older_packages(bench):
    project, _, _, capture_id, directory = seed_capture(bench)
    package, _ = bench.export_project(project["id"])
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    prefix = f"scrapes/{project['id']}/android-{capture_id}/"
    package = replace_package_json(package, {prefix + "request.json": request})
    copied = bench.import_project(package)
    request_file = next((bench.data / "scrapes" / copied["id"]).glob("android-*/request.json"))
    restored_request = request_file.read_text(encoding="utf-8")
    assert "LOCAL_EXECUTION_ONLY" not in restored_request
    assert "LOCAL_CONNECTION_SECRET" not in restored_request
    assert str(directory) not in restored_request
    assert json.loads(restored_request)["package"] == request["package"]


def test_invalid_capture_reference_rolls_back_project_import(bench):
    project, _, _, capture_id, directory = seed_capture(bench)
    package, _ = bench.export_project(project["id"])
    session = json.loads((directory / "session.json").read_text(encoding="utf-8"))
    session["project_id"] = "f" * 32
    package = replace_package_json(package, {f"scrapes/{project['id']}/android-{capture_id}/session.json": session})
    with pytest.raises(ValueError, match="截图会话引用无效"):
        bench.import_project(package)
    assert [row["id"] for row in bench.rows("SELECT id FROM projects")] == [project["id"]]
    assert list((bench.data / "scrapes").iterdir()) == [directory.parent]
    assert not list((bench.data / "imports").iterdir())


def test_capture_evidence_survives_project_trash_and_restore(bench):
    project, _, _, _, directory = seed_capture(bench)
    original = {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    deleted = bench.delete_project(project["id"], project["name"])
    trash = Path(deleted["backup"])
    assert not directory.exists()
    assert (trash / "scrapes" / directory.name / "observations" / "obs-0123456789abcdef.png").is_file()
    restored = bench.restore_project(trash.name)
    assert restored["id"] == project["id"]
    for relative, expected in original.items():
        assert (directory / relative).read_bytes() == expected


def test_active_android_capture_blocks_delete_and_old_hosts_remain_compatible(bench, monkeypatch):
    project, _, _, _, directory = seed_capture(bench)
    called = []
    monkeypatch.setattr(bench, "android_capture", SimpleNamespace(has_active=lambda project_id: called.append(project_id) or True), raising=False)
    with pytest.raises(ValueError, match="Android 截图走查运行中"):
        bench.delete_project(project["id"], project["name"])
    assert called == [project["id"]]
    assert directory.is_dir()
    assert bench.project(project["id"])["id"] == project["id"]
    monkeypatch.setattr(bench, "android_capture", SimpleNamespace())
    assert bench.delete_project(project["id"], project["name"])["deleted"] is True
