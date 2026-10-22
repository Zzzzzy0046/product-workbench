"""Regression tests for backend fixes: import fidelity, revisions, cancel races,
snapshot image boundaries, HTTP error logging, state caching and locking."""

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from workbench import app
from workbench.adapters import codex_runner as runner_module
from workbench.adapters import review_scraper as scraper_module
from workbench.api.handler import Handler
from workbench.services.competitor_service import CompetitorService


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path / "data", runner=lambda _: "# 测试交付物\n\n自动化测试正文。")
    try:
        yield instance
    finally:
        instance.close()


def insert_scrape(bench, project_id, status="queued", request=None):
    scrape_id = os.urandom(16).hex()
    request = request or {"platform": "google_play", "app_id": "com.example.synthetic", "countries": ["us"]}
    with bench.db() as db:
        db.execute(
            "INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (scrape_id, project_id, "google_play", request["app_id"], json.dumps(request), status, "", "2026-10-22", "2026-10-22", "", ""),
        )
    return scrape_id


def ready_settings(tmp_path):
    return lambda *_: {"ready": True, "enabled": True, "root": str(tmp_path), "python": "python", "backend": "legacy", "message": ""}


# 1. Project import keeps team and timebox.
def test_project_roundtrip_preserves_team_and_timebox(bench):
    project = bench.create_project("团队项目", "背景", team="PM 小王，研发 2 人", timebox="3 周")
    package, _ = bench.export_project(project["id"])
    imported = bench.import_project(package)
    assert imported["team"] == "PM 小王，研发 2 人"
    assert imported["timebox"] == "3 周"


# 2. Revising an acceptance run reuses the explicit evidence.
def test_acceptance_run_revision_keeps_explicit_evidence(bench):
    project = bench.create_project("验收修订", "", workflow_mode="full")
    evidence = bench.add_document(project["id"], "测试记录.txt", "实际测试记录、日志索引和设备结果".encode())
    job = bench.prepare(project["id"], "product/acceptance-run", "", [evidence["id"]])
    bench.complete(job["id"], "# 验收结果\n\n最终结果：`Pass`\n\n全部用例在真实设备上通过，日志与截图索引已附在测试记录中。")
    bench.review(job["id"], "changes_requested", "补充设备型号")
    revision = bench.revise(job["id"])
    assert revision["parent_job_id"] == job["id"]
    assert revision["task_id"] == "product/acceptance-run"
    assert any(source.get("source_id") == evidence["id"] for source in revision["sources"])


# 3. Scrape status writes never overwrite a user cancel.
def test_scrape_cancel_before_running_write_is_kept(bench, tmp_path, monkeypatch):
    project = bench.create_project("采集取消", "")
    scrape_id = insert_scrape(bench, project["id"])
    settings = ready_settings(tmp_path)

    def cancel_then_settings(self):
        bench.cancel_scrape(scrape_id)
        return settings()

    launched = []
    monkeypatch.setattr(scraper_module.ReviewScraperAdapter, "review_scraper_settings", cancel_then_settings)
    monkeypatch.setattr(scraper_module.subprocess, "Popen", lambda *a, **k: launched.append(a) or (_ for _ in ()).throw(AssertionError("must not launch")))
    bench.review_scraper._run_review_scrape(scrape_id)
    assert bench.scrape(scrape_id)["status"] == "cancelled"
    assert not launched


@pytest.mark.parametrize("confirmation", [False, True])
def test_scrape_cancel_before_completion_write_is_kept(bench, tmp_path, monkeypatch, confirmation):
    project = bench.create_project("采集完成前取消", "")
    request = {"platform": "google_play", "app_id": "com.example.synthetic", "countries": ["us"]}
    if confirmation:
        request.update({"requires_confirmation": True, "collect_reviews": True})
    scrape_id = insert_scrape(bench, project["id"], request=request)
    monkeypatch.setattr(scraper_module.ReviewScraperAdapter, "review_scraper_settings", ready_settings(tmp_path))

    class Process:
        returncode = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, content, timeout):
            return json.dumps({"reviews": [{"review_id": "r1", "content": "Nice", "score": 5}], "warnings": []}).encode(), b""

        def poll(self):
            return 0

    monkeypatch.setattr(scraper_module.subprocess, "Popen", Process)
    if confirmation:
        def stage_then_cancel(self, *args, **kwargs):
            bench.cancel_scrape(scrape_id)
            return {"document_ids": []}

        monkeypatch.setattr(scraper_module.ReviewScraperAdapter, "_stage_collection_result", stage_then_cancel)
    else:
        original_add = bench.add_document

        def add_then_cancel(*args, **kwargs):
            document = original_add(*args, **kwargs)
            bench.cancel_scrape(scrape_id)
            return document

        monkeypatch.setattr(bench, "add_document", add_then_cancel)
    bench.review_scraper._run_review_scrape(scrape_id)
    result = bench.scrape(scrape_id)
    assert result["status"] == "cancelled"
    assert result["error"] == "已由用户取消。"


# 4. Imported run snapshots cannot point --image at arbitrary local files.
def test_runner_only_passes_images_inside_project_uploads(tmp_path, monkeypatch):
    data = tmp_path / "data"
    project_id = "a" * 32
    job = {"id": "b" * 32, "project_id": project_id, "prompt": "生成", "status": "running"}
    directory = data / "runs" / job["id"]
    directory.mkdir(parents=True)
    uploads = data / "uploads" / project_id
    uploads.mkdir(parents=True)
    allowed = uploads / ("c" * 32 + ".png")
    allowed.write_bytes(b"img")
    other_project = data / "uploads" / ("d" * 32)
    other_project.mkdir(parents=True)
    foreign = other_project / ("e" * 32 + ".png")
    foreign.write_bytes(b"img")
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret")
    traversal = str(uploads / ".." / ".." / ".." / "secret.png")
    (directory / "执行记录.json").write_text(json.dumps({"sources": [
        {"image_path": str(allowed)}, {"image_path": str(outside)}, {"image_path": traversal},
        {"image_path": str(foreign)}, {"image_path": str(directory / "执行记录.json")},
    ]}), encoding="utf-8")
    host = SimpleNamespace(data=data, lock=threading.RLock(), processes={}, job=lambda _: job)
    calls = []

    class Process:
        pid = 1
        returncode = None

        def __init__(self, command, **kwargs):
            import io
            calls.append(command)
            self.command = command
            self.stdin = io.BytesIO()
            self.stderr = io.BytesIO(b"")

        def wait(self, timeout=None):
            Path(self.command[self.command.index("-o") + 1]).write_text("# ok", encoding="utf-8")
            self.returncode = 0
            return 0

        def poll(self):
            return self.returncode

    monkeypatch.setattr(runner_module, "codex_command", lambda: ["node", "codex.js"])
    monkeypatch.setattr(runner_module, "codex_runtime_settings", lambda: {"config_overrides": [], "secret_env_names": []})
    monkeypatch.setattr(runner_module.subprocess, "Popen", Process)
    runner_module.CodexRunner(host).run_codex(job)
    command = calls[0]
    images = [command[index + 1] for index, value in enumerate(command) if value == "--image"]
    assert images == [str(allowed.resolve())]


# 5. 500 errors are logged; client disconnects are silent.
def test_http_500_is_logged_to_data_dir(bench, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic-state-failure")

    monkeypatch.setattr(bench, "state", boom)
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    server.app = bench
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with pytest.raises(urllib.error.HTTPError) as failure:
            opener.open(f"http://127.0.0.1:{server.server_port}/api/state")
        assert failure.value.code == 500
    finally:
        server.shutdown()
        server.server_close()
    log = (bench.data / "logs" / "workbench.log").read_text(encoding="utf-8")
    assert "synthetic-state-failure" in log
    assert "Traceback" in log
    assert "/api/state" in log


@pytest.mark.parametrize("error", [ConnectionAbortedError, BrokenPipeError, ConnectionResetError])
def test_respond_ignores_client_disconnect(error, capsys):
    class Broken:
        def write(self, _):
            raise error()

        def flush(self):
            raise error()

    handler = Handler.__new__(Handler)
    handler.request_version = "HTTP/1.1"
    handler.requestline = "GET /api/state HTTP/1.1"
    handler.command = "GET"
    handler.wfile = Broken()
    handler.respond({"ok": True})
    captured = capsys.readouterr()
    assert captured.err == "" and captured.out == ""


def test_disconnect_during_dispatch_is_not_logged(bench, monkeypatch):
    def disconnected(*args, **kwargs):
        raise ConnectionAbortedError()

    monkeypatch.setattr(bench, "state", disconnected)
    handler = Handler.__new__(Handler)
    handler.server = SimpleNamespace(app=bench, server_port=1234)
    handler.headers = {"Host": "127.0.0.1:1234"}
    handler.path = "/api/state"
    responses = []
    handler.respond = lambda *args, **kwargs: responses.append(args)
    handler.do_GET()
    assert not responses
    assert not (bench.data / "logs" / "workbench.log").exists()


# 6. /api/state avoids repeated full reads and keeps its shape.
def test_trash_listing_is_cached_by_mtime(bench, monkeypatch):
    project = bench.create_project("回收项目", "")
    bench.add_document(project["id"], "资料.txt", "内容".encode())
    bench.delete_project(project["id"], "回收项目")
    first = bench.trash_items()
    assert first and first[0]["document_count"] == 1
    original = Path.read_text
    reads = []

    def counting(self, *args, **kwargs):
        if self.name == "project-export.json":
            reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    assert bench.trash_items() == first
    assert not reads
    export = bench.data / "trash" / first[0]["id"] / "project-export.json"
    snapshot = json.loads(original(export, encoding="utf-8"))
    snapshot["project"]["name"] = "改名后"
    export.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    stat = export.stat()
    os.utime(export, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert bench.trash_items()[0]["name"] == "改名后"
    assert len(reads) == 1


def test_registry_and_knowledge_are_cached_and_isolated(bench, monkeypatch):
    packs = bench.registry()
    knowledge = bench.knowledge()
    original = Path.read_text
    reads = []

    def counting(self, *args, **kwargs):
        if self.suffix in {".json", ".md"} and ("capabilities" in self.parts or "knowledge" in self.parts):
            reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    import product_kb.frontmatter as frontmatter
    original_parse = frontmatter.parse_markdown
    monkeypatch.setattr(frontmatter, "parse_markdown", lambda path: reads.append(path) or original_parse(path))
    again = bench.registry()
    assert again == packs
    assert bench.knowledge() == knowledge
    assert not reads
    again[0]["tasks"].clear()
    assert bench.registry() == packs
    # Preferences remain live, not cached.
    with bench.db() as db:
        db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)", ("pack:" + packs[0]["id"], json.dumps(not packs[0]["enabled"])))
    assert bench.registry()[0]["enabled"] is (not packs[0]["enabled"])


def test_state_competitor_links_per_document(bench):
    project = bench.create_project("竞品关联", "")
    competitor = bench.competitor_service.upsert(project["id"], {"platform": "google_play", "app_id": "com.example.one"})
    linked = bench.add_document(project["id"], "商店信息.md", b"listing", competitor_id=competitor["id"], material_type="store_info")
    plain = bench.add_document(project["id"], "普通.md", b"plain")
    documents = {item["id"]: item for item in bench.state(project["id"])["documents"]}
    assert documents[linked["id"]]["competitor_ids"] == [competitor["id"]]
    assert documents[linked["id"]]["competitor_material_types"] == {competitor["id"]: "store_info"}
    assert documents[plain["id"]]["competitor_ids"] == []
    assert documents[plain["id"]]["competitor_material_types"] == {}


# 7. stop_process is never called while holding the shared lock.
def lock_free_probe(bench, stopped):
    def probe(process):
        result = []
        worker = threading.Thread(target=lambda: result.append(bench.lock.acquire(timeout=1) and (bench.lock.release() or True)))
        worker.start()
        worker.join(3)
        stopped.append(bool(result and result[0]))
        return True

    return probe


def test_job_cancel_stops_process_outside_lock(bench, monkeypatch):
    project = bench.create_project("取消锁", "")
    job = bench.prepare(project["id"], "product/framework", "")
    with bench.db() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
    stopped = []
    monkeypatch.setattr(bench, "stop_process", lock_free_probe(bench, stopped))
    bench.processes[job["id"]] = SimpleNamespace(poll=lambda: 0)
    assert bench.cancel(job["id"])["status"] == "cancelled"
    assert stopped == [True]


def test_scrape_cancel_stops_process_outside_lock(bench, monkeypatch):
    project = bench.create_project("采集取消锁", "")
    scrape_id = insert_scrape(bench, project["id"], status="running")
    stopped = []
    monkeypatch.setattr(bench, "stop_process", lock_free_probe(bench, stopped))
    bench.scrape_processes[scrape_id] = SimpleNamespace(poll=lambda: 0)
    assert bench.cancel_scrape(scrape_id)["status"] == "cancelled"
    assert stopped == [True]


# 8. Concurrent scrape starts cannot both pass the "already running" check.
def test_concurrent_scrape_start_allows_only_one(bench, monkeypatch):
    project = bench.create_project("并发采集", "")
    monkeypatch.setattr(scraper_module.ReviewScraperAdapter, "_run_review_scrape", lambda self, scrape_id: None)
    entered, release = threading.Event(), threading.Event()
    original = CompetitorService.upsert
    calls = []

    def slow_upsert(self, project_id, payload):
        calls.append(payload)
        if len(calls) == 1:
            entered.set()
            release.wait(3)
        return original(self, project_id, payload)

    monkeypatch.setattr(CompetitorService, "upsert", slow_upsert)
    results = []

    def start():
        try:
            results.append(bench.start_review_scrape(project["id"], {"platform": "google_play", "app_id": "com.example.race", "countries": ["us"]}))
        except ValueError as exc:
            results.append(exc)

    first = threading.Thread(target=start)
    first.start()
    assert entered.wait(3)
    second = threading.Thread(target=start)
    second.start()
    second.join(0.5)
    release.set()
    first.join(5)
    second.join(5)
    assert sum(isinstance(item, ValueError) for item in results) == 1
    assert len(bench.rows("SELECT id FROM scrapes WHERE project_id=? AND status IN ('queued','running')", (project["id"],))) == 1


# 9. Job detail exposes only what the user explicitly ticked, so "continue to next
#    chapter" does not carry auto-retrieved materials forward.
def test_job_exposes_explicit_document_selection(bench):
    project = bench.create_project("显式勾选", "")
    picked = bench.add_document(project["id"], "商店信息.md", "GBA 模拟器商店描述，扫描导入游戏文件".encode())
    bench.add_document(project["id"], "无关截图说明.md", "GBA 模拟器 工作台弹窗 截图 无关".encode())
    job = bench.prepare(project["id"], "product/prd", "GBA 模拟器", [picked["id"]])
    assert bench.job(job["id"])["selected_document_ids"] == [picked["id"]]
    unselected = bench.prepare(project["id"], "product/prd", "GBA 模拟器")
    assert bench.job(unselected["id"])["selected_document_ids"] == []
