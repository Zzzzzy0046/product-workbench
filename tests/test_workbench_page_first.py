"""Page-first task preparation and authoritative upstream source boundaries."""

import json

import pytest

from workbench import app


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path, runner=lambda _: "unused")
    instance.retrieval_mode = "keyword"
    yield instance
    instance.close()


def confirmed_job(bench, project_id, task_id, text, version_id=""):
    job = bench.prepare(project_id, task_id, "只整理当前模块", version_id=version_id)
    bench.complete(job["id"], text)
    bench.review(job["id"], "accepted", "用户确认当前口径")
    return bench.job(job["id"])


def test_page_first_tasks_allow_direct_entry_and_preserve_requested_scope(bench):
    project = bench.create_project("模块工作", "从当前模块直接开始")
    for key in (
        "fast/shared-rules", "fast/flow-pages", "fast/prototype-handoff",
        "fast/review-changes", "fast/consistency-review", "fast/product-acceptance",
    ):
        task = bench.task(key)
        assert not task.get("required_upstream_all")
        job = bench.prepare(project["id"], key, "本轮范围：游戏导入\n交付点：只处理错误恢复状态")
        assert job["status"] == "prepared"
        assert "本轮范围：游戏导入" in job["prompt"]
        assert "交付点：只处理错误恢复状态" in job["prompt"]
        assert "文件名带“正式/最终”" in job["prompt"]
        assert "广告为主、订阅/IAP 为辅" in job["prompt"]
        assert "不填写 ROI、ROAS" in job["prompt"]
    handoff = bench.prepare(project["id"], "fast/prototype-handoff", "")
    assert "没有原生 Figma、Axure 写入能力" in handoff["prompt"]
    revisions = bench.prepare(project["id"], "fast/review-changes", "")
    assert "未修改的对象不能标“已落实/已同步/已修复”" in revisions["prompt"]
    acceptance = bench.prepare(project["id"], "fast/product-acceptance", "")
    assert "验收场景 | 操作步骤 | 预期结果" in acceptance["prompt"]
    assert "用例是预期行为，不是实测记录" in acceptance["prompt"]
    prd = bench.prepare(project["id"], "fast/core-prd", "本轮范围：完整产品基线")
    assert "正文最多 24000 个中文字符" in prd["prompt"]
    assert "不为压缩预算删除已确认页面" in prd["prompt"]


def test_confirmed_current_upstream_is_injected_without_search_hit(bench, monkeypatch):
    project = bench.create_project("定向引用", "已有页面口径")
    upstream = confirmed_job(
        bench, project["id"], "fast/flow-pages",
        "# 游戏导入流程\n\nPAGE-02 导入失败状态保留已选择文件，提供重新选择操作，返回时恢复原文件列表。",
    )
    monkeypatch.setattr(bench, "search", lambda *args: [])
    downstream = bench.prepare(project["id"], "fast/prototype-handoff", "只做导入页")
    assert upstream["id"] in {source["source_id"] for source in downstream["sources"]}
    assert "PAGE-02" in downstream["prompt"]


@pytest.mark.parametrize("is_revision", [False, True])
def test_newer_draft_blocks_automatic_old_accepted_leaf(bench, monkeypatch, is_revision):
    project = bench.create_project("不捡旧版本", "")
    old = confirmed_job(
        bench, project["id"], "fast/flow-pages",
        "# 旧流程\n\nPAGE-01 旧版流程要求用户始终联网才能进入产品，本轮已经准备替换此业务规则。",
    )
    newer = bench.prepare(project["id"], "fast/flow-pages", "新版正在准备，取消强制联网")
    if is_revision:
        with bench.db() as db:
            db.execute("UPDATE jobs SET parent_job_id=? WHERE id=?", (old["id"], newer["id"]))
    monkeypatch.setattr(bench, "search", lambda *args: [{
        "source_id": old["id"], "name": "旧流程（已确认）.md", "kind": "accepted",
        "location": "旧流程", "chunk": 1, "text": old["output"],
    }])
    downstream = bench.prepare(project["id"], "fast/prototype-handoff", "")
    assert old["id"] not in {source["source_id"] for source in downstream["sources"]}
    assert "旧版流程要求用户始终联网" not in downstream["prompt"]


def test_accepted_revision_excludes_ancestor_even_from_nested_sources(bench, monkeypatch):
    project = bench.create_project("修订链", "")
    old = confirmed_job(
        bench, project["id"], "fast/shared-rules",
        "# 旧规则\n\nRULE-01 旧奖励有效期是一天；该值只用于旧规则，不应成为新模块的业务依据。",
    )
    bench.review(old["id"], "changes_requested", "取消旧奖励期限")
    revision = bench.revise(old["id"])
    bench.complete(revision["id"], "# 共享规则\n\nRULE-01 奖励不再设置一天有效期，退出后保留当前状态；该变化已由产品明确确认。")
    bench.review(revision["id"], "accepted", "按新规则")
    # Simulate a confirmed handoff whose historic snapshot still contains the
    # accepted ancestor. Normalization must not restore its obsolete text.
    handoff = confirmed_job(
        bench, project["id"], "fast/prototype-handoff",
        "# 原型交接\n\nPAGE-01 引用共享规则，完成奖励后返回当前页面，按已确认恢复行为展示内容。",
    )
    with bench.db() as db:
        db.execute("UPDATE jobs SET sources=? WHERE id=?", (json.dumps([{
            "source_id": old["id"], "name": "旧共享规则", "kind": "accepted", "location": "旧共享规则",
            "chunk": 1, "text": old["output"], "citation": "S1",
        }], ensure_ascii=False), handoff["id"]))
        db.execute("UPDATE jobs SET output=output||' [S1]' WHERE id=?", (handoff["id"],))
    monkeypatch.setattr(bench, "search", lambda *args: [])
    downstream = bench.prepare(project["id"], "fast/core-prd", "只整理 PAGE-01")
    ids = {source["source_id"] for source in downstream["sources"]}
    assert revision["id"] in ids
    assert handoff["id"] in ids
    assert old["id"] not in ids
    assert "旧奖励有效期是一天" not in downstream["prompt"]
    assert not bench.citation_issues("\n".join(source["text"] for source in downstream["sources"]), downstream["sources"])


def test_automatic_upstream_remains_in_selected_version_scope(bench, monkeypatch):
    project = bench.create_project("版本来源", "")
    v1 = bench.create_product_version(project["id"], {"name": "V1"})
    v2 = bench.create_product_version(project["id"], {"name": "V2"})
    old = confirmed_job(bench, project["id"], "fast/flow-pages", "# V1 流程\n\nPAGE-01 采用旧版操作布局，返回到文件列表；这是 V1 专属口径。", v1["id"])
    current = confirmed_job(bench, project["id"], "fast/flow-pages", "# V2 流程\n\nPAGE-02 使用当前导入入口，错误恢复返回选择器；这是 V2 专属口径。", v2["id"])
    monkeypatch.setattr(bench, "search", lambda *args: [])
    downstream = bench.prepare(project["id"], "fast/prototype-handoff", "", version_id=v2["id"])
    ids = {source["source_id"] for source in downstream["sources"]}
    assert current["id"] in ids
    assert old["id"] not in ids
    product_job = bench.prepare(project["id"], "fast/prototype-handoff", "")
    assert not product_job["sources"]


def test_conflicting_uploaded_baselines_are_retained_for_explicit_resolution(bench):
    project = bench.create_project("上传冲突", "")
    old = bench.add_document(project["id"], "正式版旧规则.txt", "奖励权益一天后到期。".encode())
    current = bench.add_document(project["id"], "当前原型旁注.txt", "奖励权益本轮不设置到期时间。".encode())
    job = bench.prepare(project["id"], "fast/consistency-review", "本轮范围：奖励权益", [old["id"], current["id"]])
    assert {old["id"], current["id"]} <= {source["source_id"] for source in job["sources"]}
    assert "不能凭关键词裁定真伪" in job["prompt"]
    assert "来源文件/页面/章节" in job["prompt"]


def test_explicitly_selected_baseline_remains_available_despite_newer_draft(bench, monkeypatch):
    project = bench.create_project("显式基线", "")
    old = confirmed_job(
        bench, project["id"], "fast/flow-pages",
        "# 选定基线\n\nPAGE-03 保留原列表操作和返回行为。本轮用户主动选择这一份作为比较基线。",
    )
    bench.prepare(project["id"], "fast/flow-pages", "正在准备新版")
    monkeypatch.setattr(bench, "search", lambda *args: [])
    job = bench.prepare(project["id"], "fast/prototype-handoff", "以勾选文档为比较基线", [old["id"]])
    assert old["id"] in {source["source_id"] for source in job["sources"]}
    assert "本轮用户主动选择这一份" in job["prompt"]


def test_selected_long_document_keeps_target_module_and_tail_shared_rules(bench):
    project = bench.create_project("长文按模块", "")
    original = (
        "# 产品当前基线\n\n这是原文导言，介绍本轮已确认的产品方向。\n\n"
        + "## 首页布局\n\n" + ("首页内容用于展示已有项目，不涉及本轮需要处理的权益模块。\n" * 600)
        + "\n## 购买恢复\n\nPAGE-09 用户点击 Restore 后恢复已有权益，结果返回当前页面。\n\n"
        + "## 购买规则与公共规则\n\nRULE-17 购买恢复成功后取消广告展示，离线时保留此前已确认的本地权益。\n"
    )
    document = bench.add_document(project["id"], "产品正式需求.md", original.encode())
    job = bench.prepare(
        project["id"], "fast/core-prd",
        "本轮范围：购买恢复\n交付点：页面旁注及公共规则同步",
        [document["id"]],
    )
    source = next(item for item in job["sources"] if item["source_id"] == document["id"])
    assert source["truncated"] is True
    assert len(source["text"]) <= 12000
    assert "这是原文导言" in source["text"]
    assert "PAGE-09" in source["text"]
    assert "RULE-17" in source["text"]
    assert "原文位置：第" in source["text"]
    assert "长文局部节选" in source["text"]
    assert "未列出的段落未进入本次上下文" in source["text"]
    assert "截断：True" in job["prompt"]
    assert bench.document(document["id"])["text"] == original


def test_selected_long_document_without_module_match_marks_partial_reading(bench):
    project = bench.create_project("不假称完整读取", "")
    original = "# 原文导言\n\n只介绍已有文件管理。\n" + ("文件列表包含排序与重命名操作。\n" * 1000)
    document = bench.add_document(project["id"], "长资料.md", original.encode())
    job = bench.prepare(project["id"], "fast/flow-pages", "本轮范围：量子通信", [document["id"]])
    source = next(item for item in job["sources"] if item["source_id"] == document["id"])
    assert source["truncated"] is True
    assert "未命中相关模块：当前仅提供导言" in source["text"]
    assert "不能据此宣称已读完整资料" in source["text"]
    assert len(source["text"]) <= 12000


def test_disk_task_template_excludes_stale_same_id_retrieval_chunk(bench, monkeypatch):
    project = bench.create_project("模板优先级", "")
    monkeypatch.setattr(bench, "search", lambda *args: [{
        "source_id": "template-f2-core-prd", "name": "旧版 PRD 模板", "kind": "knowledge",
        "location": "旧缓存.md", "chunk": 1, "text": "旧版模板限定必须压缩到三个页面，此段不应进入本次任务。",
    }])
    job = bench.prepare(project["id"], "fast/core-prd", "同步当前完整模块")
    assert "旧版模板限定必须压缩到三个页面" not in job["prompt"]
    assert "template-f2-core-prd" not in {source["source_id"] for source in job["sources"]}
    assert "不限制页面数量" in job["prompt"]


def test_long_excerpt_retains_rules_under_nested_global_business_headings(bench):
    project = bench.create_project("规则子章节", "")
    original = (
        "# 当前产品需求\n\n本轮已有内容管理方案。\n\n"
        "## 内容导入\n\n" + "内容导入时显示文件列表和处理进度。\n" * 1000
        + "\n## 全局业务规则\n\n### 权益结果\n\n"
        + "RULE-09 已获得权益在退出页面后继续保留，取消操作不额外发放；不得以页面关闭当成失败。\n" * 8
    )
    document = bench.add_document(project["id"], "当前正式需求.md", original.encode())
    job = bench.prepare(project["id"], "fast/core-prd", "本轮范围：内容导入", [document["id"]])
    source = next(item for item in job["sources"] if item["source_id"] == document["id"])
    assert len(source["text"]) <= 12000
    assert "RULE-09" in source["text"]
    assert "全局业务规则 / 权益结果" in source["text"]
