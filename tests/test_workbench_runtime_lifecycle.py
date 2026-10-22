"""CLI diagnostic files stay local and embedded shutdown stops worker processes."""

import io
import zipfile

from workbench import app


def test_project_export_keeps_deliverables_but_excludes_cli_diagnostics(tmp_path):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        project = bench.create_project("运行日志隔离", "")
        job = bench.prepare(project["id"], "fast/product-acceptance", "只处理当前模块")
        bench.complete(job["id"], "# 产品验收用例\n\n| 验收场景 | 操作步骤 | 预期结果 |\n|---|---|---|\n| 1.1 取消编辑 | 修改后取消 | 返回来源，保留已保存内容 |")
        directory = tmp_path / "runs" / job["id"]
        (directory / "codex-diagnostics-attempt.log").write_text("LOCAL_DIAGNOSTIC_ONLY", encoding="utf-8")
        (directory / "model-output-attempt.md").write_text("RAW_INTERMEDIATE_ONLY", encoding="utf-8")
        package, _ = bench.export_project(project["id"])
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            names = archive.namelist()
            assert any(name.endswith("/交付物.md") for name in names)
            assert any(name.endswith("/任务包.md") for name in names)
            assert not any("codex-diagnostics" in name or "model-output" in name for name in names)
            assert all(b"LOCAL_DIAGNOSTIC_ONLY" not in archive.read(name) for name in names)
    finally:
        bench.close()


def test_embedded_close_stops_both_codex_and_scraper_processes(tmp_path, monkeypatch):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    codex_process, scraper_process = object(), object()
    stopped = []
    monkeypatch.setattr(bench, "stop_process", stopped.append)
    bench.processes["codex"] = codex_process
    bench.scrape_processes["scraper"] = scraper_process
    bench.close()
    assert codex_process in stopped
    assert scraper_process in stopped


def test_invalid_explicit_cli_setting_does_not_break_state(tmp_path, monkeypatch):
    bench = app.Workbench(tmp_path, runner=lambda _: "unused")
    try:
        monkeypatch.setenv("WORKBENCH_CODEX_BIN", "Z:/missing-workbench-test/codex.exe")
        runtime = bench.state()["runtime"]
        assert runtime["available"] is False
        assert "路径配置无效" in runtime["codex_error"]
        assert "missing-workbench-test" not in runtime["codex_error"]
        assert "token" not in runtime["codex_error"]
    finally:
        bench.close()
