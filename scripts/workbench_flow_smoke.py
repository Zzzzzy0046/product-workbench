"""Repeatable, isolated workflow integration smoke test (no real model calls).

Run with `.venv/Scripts/python.exe scripts/workbench_flow_smoke.py`.
The runner returns explicitly labelled test fixtures. This verifies task routing,
storage, review, source selection, exports and project migration, NOT model quality,
live competitor collection, native prototype writes or real app acceptance.
All project data lives inside a TemporaryDirectory, never workbench/data.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.app import Workbench


PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
SECTION_OUTPUTS = {
    "fast/f1-category-user": """# F1-1 品类与用户

## 2. 行业与市场背景
品类标记 A：本地 GBA 模拟器。本次只有测试资料，不下市场规模结论。

## 3. 用户分析
使用场景由本轮测试设定：持有本地游戏文件的用户希望导入并离线游玩。
""",
    "fast/f1-competitor-differences": """# F1-2 竞品差异

## 4. 竞品分析与差异
竞品标记 B：Test Emulator 是测试对标名称。测试 CSV 只包含一条导入失败评论，不代表真实市场。
""",
    "fast/f1-positioning-scope": """# F1-3 定位与版本范围

## 5. 产品定位与价值主张
定位标记 C：本轮拟定从本地游戏导入到离线启动的最小核心任务。

## 6. 产品范围与版本边界
首版范围是选择文件、导入结果与离线启动；不额外加入账号、云存档和订阅。
""",
    "fast/f1-product-solution": """# F1-4 功能框架与核心模块

## 7. 产品功能框架
功能标记 D：PAGE-01 游戏库 → PAGE-02 文件导入 → PAGE-03 游戏运行。

## 8. 核心功能说明
支持文件导入、失败重选和本地启动。格式支持清单待研发确认。
""",
    "fast/f1-flow-monetization": """# F1-5 流程、商业化与 PRD 交接

## 9. 产品主要流程
流程标记 E：游戏库 → 选择文件 → 导入回调 → 本地启动；导入失败可重新选择。

## 10. 商业化策略
当前未指定广告位与频控，不编造收入和回本结论。广告为主的具体方案待确认。

## 11. 进入 PRD 的交付结论
PRD 需要说明 PAGE-02 失败恢复与 RULE-01 离线规则，不扩出未确认模块。
""",
}

FIXTURES = {
    **SECTION_OUTPUTS,
    "fast/shared-rules": """# 全局共享规则（测试替身）

| 规则 ID | 规则 | 适用页面 | 来源 |
|---|---|---|---|
| RULE-01 | 已导入本地文件允许离线游玩 | PAGE-01、PAGE-03 | 本轮测试设定 |
| RULE-02 | 导入失败可重新选择文件 | PAGE-02 | 本轮测试设定 |
""",
    "fast/flow-pages": """# 功能流程与页面状态清单（测试替身）

游戏库 PAGE-01 → 文件选择 PAGE-02 → 导入成功回调 → 游戏 PAGE-03。
失败进入 STATE-02，允许重新选择。RULE-01 允许本地离线游玩。

| 稳定 ID | 页面/状态 | 进入条件 | 可用操作 | 返回去向 |
|---|---|---|---|---|
| PAGE-01 | 游戏库 | 启动应用 | 选择 Import | PAGE-02 |
| PAGE-02 | 文件导入 | 点击 Import | 选择本地文件 | PAGE-01 |
| STATE-02 | 导入失败 | 收到失败回调 | 重新选择 | PAGE-02 |
| PAGE-03 | 游戏运行 | 成功读取文件 | 返回游戏库 | PAGE-01 |
""",
    "fast/prototype-handoff": """# 原型与需求旁注交接（测试替身）

## PAGE-02 文件导入
左侧页面效果：展示文件名、导入操作、处理状态与失败重选入口。
右侧需求旁注：点击 Import 只是意图，收到导入成功回调后才进入 PAGE-03。
失败进入 STATE-02；用户可以重新选择，返回恢复 PAGE-01 文件列表。
引用 RULE-01、RULE-02。本交付只提供说明，外部原型等待人工执行。
""",
    "fast/review-changes": """# 初审意见与修订内容（测试替身）

原意见：PAGE-02 导入失败保留已选文件，并提供重新选择；不能强制本地游戏联网。
来源：测试输入的评审意见.md / 导入恢复。本意见是固定测试样例。
修订文本：失败时保留文件名，点击重新选择后打开文件选择器；本地游戏按 RULE-01 离线运行。
影响对象：STATE-02、PAGE-02 需求旁注、RULE-02、PRD 与产品验收用例。
当前仅提供修订文本，外部原型与其他文档等待写回，不宣称已同步。
""",
    "fast/consistency-review": """# 终审整理与一致性检查（测试替身）

冲突：旧验收样例.md / 联网规则要求联网；当前测试基线.md / 离线规则允许本地离线游玩。
采用依据：用户本轮明确指定当前测试基线。待同步对象：旧验收条目的联网限制。
PAGE-02 失败恢复应保留文件名并提供重新选择，与 RULE-02 对齐。
本结果是自动对照说明，不代表人工终审通过，也不代表外部原型已经改动。
""",
    "fast/core-prd": """# F2 核心 PRD（测试替身）

## 范围与竞品差异
只做本地导入与离线运行。竞品测试资料不支持额外功能或市场结论。

## PAGE-02 文件导入
入口：PAGE-01 点击 Import；英文 UI copy 为 Import 和 Choose Again。
Loading：等待导入回调；Empty：还未选择文件；Error：导入失败进入 STATE-02。
业务规则：RULE-01 允许本地离线运行；RULE-02 失败保留文件名并提供重新选择。
退出：返回 PAGE-01 并恢复列表；点击导入不等于成功，以实际回调为准。
验收标准：失败后可重新选择并再次提交；格式支持清单待研发确认。
""",
    "fast/product-acceptance": """# 产品验收用例（测试替身）

| 验收场景 | 操作步骤 | 预期结果 |
|---|---|---|
| PAGE-02 导入成功 | 选择文件并提交，等待导入回调 | 成功后进入 PAGE-03 |
| STATE-02 失败恢复 | 导入失败后点击 Choose Again | 保留文件名，可重新选择文件 |
| RULE-01 离线运行 | 导入本地文件后断网并启动 | 可以进入本地游戏 |

以上为预期用例，没有执行真实设备测试。
""",
    "fast/acceptance": """# F3 开发验收清单（测试替身）

构建版本：未提供；测试设备：未提供；实际日志、截图和证据索引：未提供。

| QA ID | 验收项 | 预期结果 | 实测结果 | 状态 | 证据 |
|---|---|---|---|---|---|
| QA-01 | 本地导入 | 成功回调后进入游戏 | 尚未测试 | NOT_RUN | 未提供 |

问题与复测：尚未测试，无真实测试报告。最终结果：NOT_RUN。
""",
    "fast/tracking-spec": """# 完整埋点方案（测试替身）

| 事件 ID | 中文名称 | 事件类型 | 触发时机 | 分析问题 | 来源页面 / 状态 |
|---|---|---|---|---|---|
| `import_click` | 点击导入 | click | 用户点击 Import 时 | 有多少用户尝试导入 | PAGE-02 |
| `import_result` | 导入结果 | result | 导入最终回调；实际回调由研发确认 | 导入失败占比是多少 | PAGE-02、STATE-02 |

| 事件 ID | 参数名 | 参数中文名 | 类型 | 枚举值 / 开放值 | 何时上报 | 是否必填 | 隐私与实现说明 |
|---|---|---|---|---|---|---|---|
| `import_result` | `result` | 结果 | enum | `success` | 成功回调 | 是 | 不记录文件名 |
| `import_result` | `result` | 结果 | enum | `fail` | 失败回调 | 是 | 不记录文件名 |

失败、取消、超时和重试只按真实回调记录；当前测试不证明这些回调已实现。
""",
}


def main() -> int:
    checks = []
    runner_calls = []

    def check(name, condition, detail=""):
        if not condition:
            raise AssertionError(f"{name}: {detail}")
        checks.append({"name": name, "result": "PASS", "detail": detail})

    def blocked(name, action, expected):
        try:
            action()
        except ValueError as exc:
            check(name, expected in str(exc), str(exc))
        else:
            raise AssertionError(f"{name}: expected a blocked operation")

    def fake_runner(job):
        runner_calls.append(job["task_id"])
        if job.get("revision_reason") == "comments":
            return FIXTURES[job["task_id"]] + "\n\n批注指定的失败恢复已纳入本说明：失败保留文件名，提供重新选择。\n"
        return FIXTURES[job["task_id"]]

    with tempfile.TemporaryDirectory(prefix="workbench-flow-smoke-") as temporary:
        bench = Workbench(Path(temporary) / "data", runner=fake_runner)
        try:
            check("isolated-data", not bench.data.is_relative_to(ROOT / "workbench" / "data"))
            check("keyword-retrieval-with-fixture", bench.retrieval_mode == "keyword")
            project = bench.create_project("GBA 流程测试（非真实研究）", "只做本地导入、失败恢复与离线游玩。", platform="Android")
            pid = project["id"]
            version = bench.create_product_version(pid, {"name": "V0 流程测试", "goal": "导入与离线游玩"})
            vid = version["id"]
            source = bench.add_document(pid, "当前测试基线.md", "# 当前测试基线\n\nRULE-01：已导入的本地游戏允许离线游玩。PAGE-02 失败可重新选择。".encode(), vid)
            old = bench.add_document(pid, "旧验收样例.md", "# 旧验收样例\n\n联网规则：任何游戏均要求联网才可进入，此条用于构造冲突测试。".encode(), vid)
            review = bench.add_document(pid, "评审意见.md", "# 评审意见\n\n测试样例：PAGE-02 导入失败保留文件名，并提供重新选择；不能强制本地游戏联网。".encode(), vid)
            csv_source = bench.add_document(pid, "竞品评论-Test.csv", "review_id,content,score,translated_content\ntest-1,Import failed,1,导入失败\n".encode(), vid)
            image = bench.add_document(pid, "测试页面.png", PIXEL, vid)
            check("material-uploads", all(bench.document(doc["id"]) for doc in (source, old, review, csv_source, image)))
            workflows = bench.workflows()
            check("workflow-routing", bool(workflows) and any(any(step["task"] == "fast/product-acceptance" for step in flow["steps"]) for flow in workflows))

            def execute(task_id, instruction="本轮范围：游戏导入\n交付点：仅提供当前模块交付文档", selected=None, accept=True):
                job = bench.prepare(pid, task_id, instruction, selected or [source["id"]], vid)
                bench.start(job["id"])
                deadline = time.monotonic() + 20
                while bench.job(job["id"])["status"] in {"prepared", "queued", "running"} and time.monotonic() < deadline:
                    time.sleep(0.01)
                result = bench.job(job["id"])
                check(task_id + ":execute", result["status"] == "completed", result.get("error", ""))
                check(task_id + ":references", not result["citation_issues"] and not result["asset_issues"])
                if accept:
                    result = bench.review(job["id"], "accepted", "仅确认固定测试替身的流程状态")
                    check(task_id + ":review", result["review"]["decision"] == "accepted")
                return result

            blocked("chapter-order-unconfirmed", lambda: bench.prepare(pid, "fast/f1-competitor-differences", "", version_id=vid), "请先生成并确认前置章节")
            chapters = [execute(task_id) for task_id in SECTION_OUTPUTS]
            before_assembly = len(runner_calls)
            merged = bench.assemble_sections(pid, version_id=vid)
            check("deterministic-assembly-no-model", len(runner_calls) == before_assembly)
            markers = ["品类标记 A", "竞品标记 B", "定位标记 C", "功能标记 D", "流程标记 E"]
            offsets = [merged["output"].index(marker) for marker in markers]
            check("chapter-content-preserved-and-ordered", offsets == sorted(offsets) and all(merged["output"].count(marker) == 1 for marker in markers))
            check("assembly-source-trace", {chapter["id"] for chapter in chapters} <= {entry["source_id"] for entry in merged["sources"]})
            bench.review(merged["id"], "accepted", "仅确认测试合并")
            rules = execute("fast/shared-rules")
            flow = execute("fast/flow-pages")
            handoff = execute("fast/prototype-handoff")
            check("confirmed-upstream-injected", {rules["id"], flow["id"]} <= {entry["source_id"] for entry in handoff["sources"]})
            check("native-prototype-boundary", "没有原生 Figma、Axure 写入能力" in handoff["prompt"])

            comment = bench.add_comment(handoff["id"], {"version": 1, "block_id": "block-3", "block_type": "paragraph", "block_label": "导入失败", "quote": "失败进入 STATE-02", "action": "modify", "note": "失败保留文件名，提供重新选择。", "author": "Smoke Fixture"})
            blocked("open-comment-blocks-review", lambda: bench.review(handoff["id"], "accepted", "不应通过"), "待处理批注")
            revision = bench.revise_from_comments(handoff["id"])
            check("scoped-comment-prompt", "block-3" in revision["prompt"] and "失败保留文件名" in revision["prompt"])
            bench.start(revision["id"])
            worker = bench.threads.get(revision["id"])
            if worker:
                worker.join(20)
            revised = bench.job(revision["id"])
            check("comment-revision-completed", revised["status"] == "completed")
            check("comment-resolved-on-complete", bench.comments(handoff["id"])[0]["status"] == "resolved")
            bench.review(revision["id"], "accepted", "确认测试修订文本")
            changes = execute("fast/review-changes", selected=[review["id"], source["id"], revision["id"]])
            check("review-material-present", review["id"] in {item["source_id"] for item in changes["sources"]})
            consistency = execute("fast/consistency-review", selected=[source["id"], old["id"], changes["id"]])
            check("conflicting-baselines-preserved", {source["id"], old["id"]} <= {item["source_id"] for item in consistency["sources"]})
            prd = execute("fast/core-prd")
            check("latest-confirmed-revision-source", revision["id"] in {entry["source_id"] for entry in prd["sources"]} and handoff["id"] not in {entry["source_id"] for entry in prd["sources"]})
            acceptance = execute("fast/product-acceptance")
            check("product-acceptance-exact-three-columns", "| 验收场景 | 操作步骤 | 预期结果 |" in acceptance["output"])
            f3 = execute("fast/acceptance")
            check("f3-no-invented-test-pass", "NOT_RUN" in f3["output"] and "最终结果：PASS" not in f3["output"])
            tracking = execute("fast/tracking-spec")
            check("tracking-skill-route", "按 tracking-spec-from-prototype 规则执行" in tracking["prompt"] and "已有已确认 F2" in tracking["prompt"])

            updated = bench.edit_output(prd["id"], prd["output"] + f"\n\n![测试页面](asset://{image['id']})\n\nEDIT-V2-MARKER：产品确认前需要复核此编辑。", "流程 smoke 编辑")
            check("manual-edit-creates-version-and-clears-review", updated["current_version"] == 2 and updated["review"] is None)
            draft_downstream = bench.prepare(pid, "fast/product-acceptance", "检查草稿不能自动当成已确认事实", version_id=vid)
            check("unconfirmed-edit-not-authoritative", prd["id"] not in {item["source_id"] for item in draft_downstream["sources"]})
            bench.cancel(draft_downstream["id"])
            restored = bench.restore_cancelled(draft_downstream["id"])
            check("cancelled-job-restorable", restored["status"] == "prepared")
            bench.cancel(restored["id"])
            bench.review(prd["id"], "accepted", "确认测试 V2")
            confirmed_downstream = bench.prepare(pid, "fast/product-acceptance", "按最新确认版本生成", version_id=vid)
            check("confirmed-edit-auto-used", "EDIT-V2-MARKER" in confirmed_downstream["prompt"])
            bench.cancel(confirmed_downstream["id"])

            for fmt in ("docx", "pdf", "xlsx", "csv"):
                content, mime, name = bench.export_job(acceptance["id"], fmt)
                check("export-" + fmt, bool(content) and name.endswith("." + fmt), mime)
                if fmt == "pdf":
                    check("pdf-magic", content.startswith(b"%PDF"))
                elif fmt in {"docx", "xlsx"}:
                    with zipfile.ZipFile(io.BytesIO(content)) as archive:
                        check(fmt + "-valid-package", bool(archive.namelist()))
                        if fmt == "docx":
                            check("word-chinese-table", "验收场景" in archive.read("word/document.xml").decode())
                        else:
                            from openpyxl import load_workbook
                            book = load_workbook(io.BytesIO(content), read_only=True)
                            try:
                                values = [str(cell) for sheet in book for row in sheet.values for cell in row if cell is not None]
                                check("excel-acceptance-table", all(header in values for header in ("验收场景", "操作步骤", "预期结果")))
                            finally:
                                book.close()
                else:
                    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
                    check("csv-three-columns", rows[0] == ["验收场景", "操作步骤", "预期结果"])

            package, package_name = bench.export_project(pid)
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                snapshot = json.loads(archive.read("data.json"))
            imported = bench.import_project(package)
            imported_pid = imported["id"]
            imported_jobs = bench.rows("SELECT * FROM jobs WHERE project_id=?", (imported_pid,))
            check("project-package-new-id", imported_pid != pid and package_name.endswith(".zip"))
            check("project-package-jobs-count", len(imported_jobs) == len(snapshot["jobs"]))
            check("project-package-materials-count", len(bench.rows("SELECT * FROM documents WHERE project_id=?", (imported_pid,))) == len(snapshot["documents"]))
            check("project-package-version-count", len(bench.product_versions(imported_pid)) == len(snapshot["product_versions"]))
            imported_prd = next(job for job in imported_jobs if job["task_id"] == "fast/core-prd")
            check("project-package-edits-reviews", bench.job(imported_prd["id"])["current_version"] == 2 and bench.job(imported_prd["id"])["review"]["decision"] == "accepted")
            asset_id = re.search(r"asset://([a-f0-9]{16,64})", imported_prd["output"]).group(1)
            check("project-package-image-remap", asset_id != image["id"] and bench.asset(imported_pid, asset_id)[0].is_file())
            check("project-package-comments-preserved", len(bench.rows("SELECT c.id FROM document_comments c JOIN jobs j ON c.job_id=j.id WHERE j.project_id=?", (imported_pid,))) == len(snapshot["document_comments"]))
            check("imported-document-export", bench.export_job(imported_prd["id"], "docx")[0].startswith(b"PK"))
            persisted = Workbench(bench.data, runner=fake_runner)
            try:
                check("restart-persistence", persisted.project(imported_pid)["name"] == imported["name"] and persisted.job(imported_prd["id"])["current_version"] == 2)
            finally:
                persisted.close()
            report = {"result": "PASS", "checks_passed": len(checks), "runner": "fixed fixture; never Codex", "fixture_calls": len(runner_calls), "data": "TemporaryDirectory; automatically removed", "boundaries": ["No real Codex authentication or model call", "No evaluation of model-generated document quality", "No network competitor collection", "No native Figma/Axure write", "No real Android acceptance", "Backend service integration, not browser UI click-through"], "checks": checks}
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            bench.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
