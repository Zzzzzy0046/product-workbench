"""Opt-in live Codex checks against a small, non-business sample project."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench import app
from workbench.core.codex_config import codex_command, configured_model


SAMPLE = """# 当前确认的内容管理方案

本文件为人工构造的连接测试资料，不代表现有产品。

## 本轮范围

只处理内容列表和修改名称，不增加账号、广告、订阅或其他能力。

## 页面和操作

- M01 内容列表：展示已保存名称，点击编辑进入 M02。
- M02 修改名称：显示当前名称，用户可以保存或取消。
- RULE-01：名称去首尾空格后不能为空；校验失败保留输入并停留原页。
- RULE-02：保存成功才更新列表并返回 M01；保存失败保留输入，允许重试。
- RULE-03：取消或返回时放弃尚未保存的修改，返回 M01，已保存内容不变。

## 实际评审意见

请在修改名称说明中补充：保存过程中禁用重复提交，结果确定后再恢复按钮。
本意见已作为本轮测试范围采用，尚未修改任何外部原型。
"""


def run_live(tasks: list[str], timeout: int) -> dict:
    directory = ROOT / "tmp" / f"codex-live-{uuid.uuid4().hex[:12]}"
    bench = app.Workbench(directory)
    bench.retrieval_mode = "keyword"
    report = {
        "model": configured_model() or "CLI 默认模型",
        "cli_found": bool(codex_command()),
        "sample": "synthetic content list and rename flow",
        "real_model": True,
        "data_directory": str(directory),
        "steps": [],
        "ok": False,
    }
    try:
        project = bench.create_project("Codex 真实链路检查（测试）", "仅测试内容列表与修改名称。")
        evidence = bench.add_document(project["id"], "当前确认方案及评审意见.md", SAMPLE.encode("utf-8"))
        for task_id in tasks:
            instruction = (
                "本轮范围：内容列表与修改名称\n"
                "当前采用的基线：指定测试资料及本项目最新确认产物。\n"
                "本轮交付点：只完成当前任务，用最短的可用形式表达，正文最多 1200 个中文字符。\n"
                "这是真实连接检查，保留 M01、M02 和 RULE 编号，引用实际 [Sx]。"
                "不扩展产品；不调用任何工具。"
            )
            job = bench.prepare(project["id"], task_id, instruction, [evidence["id"]])
            started = time.monotonic()
            bench.start(job["id"])
            while True:
                job = bench.job(job["id"])
                if job["status"] not in {"prepared", "queued", "running"}:
                    break
                if time.monotonic() - started >= timeout:
                    bench.cancel(job["id"])
                    job = bench.job(job["id"])
                    break
                time.sleep(0.25)
            step = {
                "task": task_id,
                "job_id": job["id"],
                "status": job["status"],
                "seconds": round(time.monotonic() - started, 2),
                "characters": len(job.get("output", "")),
                "source_count": len(job["sources"]),
                "errors": job.get("quality", {}).get("errors", 0),
            }
            if job.get("error"):
                step["error"] = job["error"]
            report["steps"].append(step)
            print(json.dumps(step, ensure_ascii=False), flush=True)
            if job["status"] != "completed":
                break
            if job.get("quality", {}).get("errors"):
                step["quality_issues"] = job["quality"]["issues"]
                break
            bench.review(job["id"], "accepted", "测试资料下确认，非真实项目业务评审。")
        report["ok"] = len(report["steps"]) == len(tasks) and all(
            step["status"] == "completed" and not step["errors"] for step in report["steps"]
        )
    finally:
        bench.close()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "smoke-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-real", action="store_true", help="Explicitly allow live Codex model calls.")
    parser.add_argument("--tasks", default="fast/flow-pages,fast/product-acceptance")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if not args.run_real:
        parser.error("真实模型测试需要显式传入 --run-real；默认不会发起模型请求。")
    report = run_live([value.strip() for value in args.tasks.split(",") if value.strip()], args.timeout)
    print(json.dumps({"ok": report["ok"], "report": str(Path(report["data_directory"]) / "smoke-report.json")}, ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
