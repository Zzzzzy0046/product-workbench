"use strict";
const $ = (s) => document.querySelector(s);
const escapeHTML = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const E = escapeHTML;
let state,
  projectId = localStorage.getItem("workbench-project"),
  tab = "overview",
  activeJob = null,
  outputFilter = "latest",
  polling = false,
  renderedBlocks = {},
  toastTimer;
const statusNames = {
  prepared: "待执行",
  queued: "等待执行",
  running: "生成中",
  completed: "待评审",
  failed: "执行失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const kinds = {
  upload: "原始资料",
  knowledge: "方法知识",
  deliverable: "待评审草稿",
  accepted: "已确认交付物",
};
const workflowNames = { fast: "快速迭代", full: "完整研究" };
const conditionNames = {
  open: "未开始",
  in_progress: "进行中",
  waiting_evidence: "待证据",
  closed: "已关闭",
  waived: "已豁免",
};
const blockNames = {
  development: "阻塞开发",
  "internal-test": "阻塞内部测试",
  "external-release": "阻塞外部发布",
  "non-blocking": "不阻塞",
};
const versionSourceNames = {
  generated: "模型生成",
  imported: "手工导入",
  manual: "正文编辑",
  restore: "版本恢复",
  legacy: "历史交付物",
  migration: "系统整理",
};
const commentActionNames = {
  add: "新增",
  modify: "修改",
  delete: "删除",
  compress: "压缩",
  preserve: "保留",
};
const commentBlockNames = {
  heading: "标题",
  paragraph: "段落",
  blockquote: "引用",
  table: "表格",
  code: "代码块",
};
const date = (s) =>
  new Date(s).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
const badge = (status) =>
  `<span class="tag ${["failed", "interrupted"].includes(status) ? "bad" : ["running", "queued"].includes(status) ? "run" : status === "prepared" ? "warn" : ""}">${E(statusNames[status] || status)}</span>`;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Workbench-Token": state?.token || "",
          },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "请求失败");
  return data;
}
function error(err) {
  toast(err.message);
  console.error(err);
}
async function refresh(render = true) {
  state = await api(
    "/api/state" +
      (projectId ? "?project=" + encodeURIComponent(projectId) : ""),
  );
  if (render) draw();
}
function modal(label, html) {
  $("#modal-label").textContent = label;
  $("#modal-body").innerHTML = html;
  if (!$("#modal").open) $("#modal").showModal();
}
function close() {
  activeJob = null;
  $("#modal").close();
}
$("#close-modal").onclick = close;
$("#modal").addEventListener("cancel", () => (activeJob = null));
function draw() {
  $("#projects").innerHTML =
    state.projects
      .map(
        (p) =>
          `<button data-project="${E(p.id)}" class="${p.id === projectId ? "selected" : ""}">${E(p.name)}</button>`,
      )
      .join("") || "<small>创建你的第一个项目</small>";
  $("#breadcrumb").textContent =
    tab === "capabilities"
      ? "工作空间 / 能力与工具"
      : tab === "trash"
        ? "工作空间 / 项目回收站"
      : "工作空间 / " + (state.project?.name || "项目");
  if (tab === "capabilities") return drawCapabilities();
  if (tab === "trash") return drawTrash();
  if (!state.project) {
    $("#content").innerHTML =
      `<div class="empty"><div class="welcome-mark">P /</div><div class="eyebrow">从背景开始，向交付推进</div><h2>把你的产品工作接起来。</h2><p>创建一个项目，留下背景和已有资料。选择这次需要的交付物，后面的工作可以随时继续。</p><button class="primary" data-action="new">创建第一个项目</button><div class="help">已连接 ${state.runtime.knowledge_count} 份方法与模板 · 包含完整新品分析模板</div></div>`;
    return;
  }
  $("#content").innerHTML =
    `<div class="heading"><div><div class="eyebrow">PROJECT WORKSPACE</div><h1>${E(state.project.name)}</h1><div class="chipline"><span class="tag">当前模式：${E(workflowNames[state.project.workflow_mode] || state.project.workflow_mode)}</span><span class="tag">${E(state.project.platform || "平台待定")}</span><span class="tag">${E(state.project.timebox || "周期待定")}</span></div><p>${E(state.project.brief || "先补充项目背景，让后续任务有依据。")}</p></div><button class="primary" data-tab="tasks">开始一项任务 ↗</button></div><nav class="tabs" aria-label="工作区" role="tablist"><button role="tab" aria-selected="${tab === "overview"}" data-tab="overview" class="${tab === "overview" ? "active" : ""}">项目概览</button><button role="tab" aria-selected="${tab === "context"}" data-tab="context" class="${tab === "context" ? "active" : ""}">项目背景</button>${state.project.workflow_mode === "full" ? `<button role="tab" aria-selected="${tab === "conditions"}" data-tab="conditions" class="${tab === "conditions" ? "active" : ""}">条件闭环</button>` : ""}<button role="tab" aria-selected="${tab === "materials"}" data-tab="materials" class="${tab === "materials" ? "active" : ""}">资料与检索</button><button role="tab" aria-selected="${tab === "tasks"}" data-tab="tasks" class="${tab === "tasks" ? "active" : ""}">任务</button><button role="tab" aria-selected="${tab === "outputs"}" data-tab="outputs" class="${tab === "outputs" ? "active" : ""}">交付物</button></nav><div id="view" role="tabpanel"></div>`;
  if (tab === "conditions" && state.project.workflow_mode !== "full") tab = "overview";
  (
    ({
      overview: drawOverview,
      context: drawContext,
      conditions: drawConditions,
      materials: drawMaterials,
      tasks: drawTasks,
      outputs: drawOutputs,
    })[tab] || drawOverview
  )();
}
function jobRows(jobs) {
  return (
    jobs
      .map(
        (j) =>
          `<div class="row ${j.archived ? "archived-row" : ""}"><div class="row-main"><h3>${E(j.title)}${j.revision_number > 1 ? ` · 修订 V${j.revision_number}` : ""}</h3><p>${date(j.created)} · ${E(workflowNames[j.workflow_mode] || j.workflow_mode)}${j.parent_job_id ? ` · 修订自上一任务 V${j.source_version || 1}` : ""} · ${E(j.error || "执行记录与引用资料可追溯")}</p><div class="chipline">${j.is_latest ? '<span class="tag">当前分支最新版</span>' : '<span class="tag">已有后续修订</span>'}${j.archived ? '<span class="tag">已归档</span>' : ""}</div></div>${badge(j.review_decision === "accepted" ? "已确认" : j.review_decision === "changes_requested" ? "需修改" : j.status)}<button class="small" aria-label="查看 ${E(j.title)}，${E(workflowNames[j.workflow_mode] || j.workflow_mode)}，${date(j.created)}" data-job="${E(j.id)}">查看</button></div>`,
      )
      .join("") ||
    '<div class="empty">暂时没有记录。按你当前需要，开始一项任务。</div>'
  );
}
function filteredJobs() {
  const jobs = state.jobs || [];
  if (outputFilter === "all") return jobs.filter((j) => !j.archived);
  if (outputFilter === "archived") return jobs.filter((j) => j.archived);
  if (outputFilter === "latest") return jobs.filter((j) => !j.archived && j.is_latest);
  if (outputFilter === "attention")
    return jobs.filter((j) => !j.archived && (["failed", "interrupted"].includes(j.status) || j.review_decision === "changes_requested"));
  if (outputFilter === "accepted") return jobs.filter((j) => !j.archived && j.review_decision === "accepted");
  return jobs.filter((j) => !j.archived && j.status === outputFilter);
}
function drawOverview() {
  const docs = state.documents,
    jobs = state.jobs;
  $("#view").innerHTML =
    `<div class="grid"><div class="card hero"><div class="eyebrow">这次，要完成什么？</div><h2>一次推进一项工作，<br>留下可以继续用的成果。</h2><p>${state.project.workflow_mode === "fast" ? "快速模式只有三份主交付物：新品需求分析、核心 PRD、开发验收清单。评论、政策、日志、截图和研究资料直接进入对应文档。" : "完整模式保留完整研究深度和条件管理。"}</p><button data-tab="tasks">选择交付任务 →</button></div><div class="card"><h3>当前工作</h3><p>${E(state.context.working || "还没有记录当前目标。可以写下这周要解决的问题、已确定的方向和暂时不做的事。")}</p><button class="small" data-tab="context">维护项目上下文</button><div class="help">已确认交付物会自动进入检索；草稿只有被你显式勾选时才进入下游任务，并附带醒目警告。</div></div></div><div class="stats"><div class="stat"><b>${docs.filter((d) => d.kind === "upload").length}</b><span>已导入资料</span></div><div class="stat"><b>${jobs.filter((j) => !j.archived && (j.status === "completed" || j.review_decision === "accepted")).length}</b><span>已完成任务</span></div><div class="stat"><b>${docs.filter((d) => d.kind === "accepted").length}</b><span>已确认交付物</span></div></div><div class="section-title"><h2>最近的工作</h2><button class="small" data-tab="outputs">全部记录</button></div><div class="card">${jobRows(jobs.filter((j) => !j.archived).slice(0, 4))}</div>`;
}
function drawContext() {
  $("#view").innerHTML =
    `${state.mode_mismatch_count ? `<div class="banner">有 ${state.mode_mismatch_count} 个历史任务使用了与当前项目不同的工作流模式。历史任务不会被修改；任务记录会显示它生成时的模式。</div>` : ""}<form id="context-form"><div class="grid"><div class="card context-card"><div class="eyebrow">01 / 长期背景</div><h2>这个项目是什么</h2><p>目标用户、地区、技术约束和长期决策。</p><textarea id="foundation" maxlength="12000" aria-label="长期背景" placeholder="目标用户：\n地区：\n技术约束：\n长期决策：">${E(state.context.foundation)}</textarea><small>每次任务自动带入；不知道的内容可以暂留空。</small></div><div class="card context-card"><div class="eyebrow">02 / 当前工作</div><h2>现在推进到哪里</h2><p>当前目标、已确认决策、正在解决的问题。</p><textarea id="working" maxlength="12000" aria-label="当前工作" placeholder="当前目标：\n已确认决策：\n待解决问题：\n本轮不做：">${E(state.context.working)}</textarea><small>迭代变化时更新；执行过的任务仍保留当时快照。</small></div></div><div class="grid"><div><label for="workflow-mode">工作流模式</label><select id="workflow-mode"><option value="fast" ${state.project.workflow_mode === "fast" ? "selected" : ""}>快速迭代（默认）</option><option value="full" ${state.project.workflow_mode === "full" ? "selected" : ""}>完整研究</option></select></div><div><label for="platform">目标平台</label><input id="platform" maxlength="80" value="${E(state.project.platform)}" placeholder="Android-first"></div><div><label for="timebox">验证周期</label><input id="timebox" maxlength="80" value="${E(state.project.timebox)}" placeholder="1–2 周"></div><div><label for="team">团队与资源</label><input id="team" maxlength="1000" value="${E(state.project.team)}" placeholder="例如：1 产品、1 Android、设计兼职、无专职 QA"></div></div><label for="brief">项目简介</label><textarea id="brief" maxlength="12000">${E(state.project.brief)}</textarea><div id="mode-help" class="help">切换模式只影响之后准备的新任务；历史任务继续保留生成时的模式和输入快照。</div><button class="primary" type="submit">保存项目背景</button></form><section class="danger-zone"><div><h2>删除项目</h2><p>项目将从工作台移入回收站，之后可以恢复。</p></div><button class="danger" data-action="delete-project">删除这个项目</button></section>`;
  $("#workflow-mode").onchange = () => {
    $("#mode-help").textContent = `保存后只影响新任务。已有 ${state.jobs.length} 个历史任务仍保留各自的生成模式。`;
  };
  $("#context-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/context", {
        project_id: projectId,
        foundation: $("#foundation").value,
        working: $("#working").value,
      });
      await api("/api/project/update", {
        id: projectId,
        brief: $("#brief").value,
        workflow_mode: $("#workflow-mode").value,
        platform: $("#platform").value,
        team: $("#team").value,
        timebox: $("#timebox").value,
      });
      await refresh();
      toast("项目背景已保存");
    } catch (e) {
      error(e);
    }
  };
}
function drawConditions() {
  const items = state.conditions || [];
  $("#view").innerHTML =
    `<div class="section-title"><div><h2>条件闭环</h2><p class="muted">每项条件都必须有 Owner、截止时间、阻塞范围和关闭证据。</p></div><button class="primary" data-action="new-condition">＋ 新增条件</button></div><div class="card">${items
      .map(
        (c) =>
          `<div class="row"><div class="row-main"><h3>${E(c.title)}</h3><p>${E(c.owner)} · 截止 ${E(c.due)} · 复核 ${E(c.review_date || c.due)} · ${E(blockNames[c.block_level])}</p><div class="chipline"><span class="tag ${["open", "in_progress", "waiting_evidence"].includes(c.status) ? "warn" : ""}">${E(conditionNames[c.status])}</span>${c.evidence ? `<span class="tag">已有证据</span>` : ""}</div></div><button class="small" data-condition="${E(c.id)}">查看/更新</button></div>`,
      )
      .join("") || '<div class="empty">暂时没有条件。F3 输出中的硬阻塞应在这里登记并持续关闭。</div>'}</div><div class="help">只有已关闭或已豁免的条件才算完成；关闭和豁免必须填写证据或决策记录。条件会自动进入之后生成的任务包。</div>`;
}
function conditionForm(item = {}) {
  modal(
    item.id ? "更新条件" : "新增条件",
    `<form id="condition-form"><label for="condition-title">条件</label><textarea id="condition-title" maxlength="300" required>${E(item.title || "")}</textarea><div class="grid"><div><label for="condition-owner">Owner</label><input id="condition-owner" maxlength="120" required value="${E(item.owner || "")}"></div><div><label for="condition-due">截止时间</label><input id="condition-due" maxlength="80" required value="${E(item.due || "")}" placeholder="2026-09-18"></div><div><label for="condition-review-date">复核日期</label><input id="condition-review-date" maxlength="80" value="${E(item.review_date || item.due || "")}" placeholder="默认与截止时间相同"></div><div><label for="condition-status">状态</label><select id="condition-status">${Object.entries(conditionNames).map(([value, label]) => `<option value="${value}" ${item.status === value ? "selected" : ""}>${label}</option>`).join("")}</select></div><div><label for="condition-block">阻塞范围</label><select id="condition-block">${Object.entries(blockNames).map(([value, label]) => `<option value="${value}" ${item.block_level === value ? "selected" : ""}>${label}</option>`).join("")}</select></div></div><label for="condition-evidence">证据或决策记录</label><textarea id="condition-evidence" maxlength="4000" placeholder="链接、构建版本、测试结果、截图/录像索引；关闭或豁免时必填。">${E(item.evidence || "")}</textarea><button class="primary" type="submit">保存条件</button></form>`,
  );
  $("#condition-form").onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      await api("/api/conditions", {
        id: item.id,
        project_id: projectId,
        title: $("#condition-title").value,
        owner: $("#condition-owner").value,
        due: $("#condition-due").value,
        review_date: $("#condition-review-date").value,
        status: $("#condition-status").value,
        block_level: $("#condition-block").value,
        evidence: $("#condition-evidence").value,
      });
      close();
      await refresh();
      toast("条件已保存");
    } catch (err) {
      error(err);
      e.submitter.disabled = false;
    }
  };
}
function drawMaterials() {
  $("#view").innerHTML =
    `<div class="section-title"><h2>资料直接进入新品分析、PRD 和验收。</h2></div><div class="drop"><strong>导入竞品评论、政策、日志、截图和研究资料</strong><p class="muted">MD · TXT · CSV · JSON · 文本 PDF · DOCX · PNG · JPG · WEBP，每份最大 12 MB</p><input type="file" id="upload" multiple accept=".md,.txt,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp" aria-label="选择要导入的资料"><small>上传后在本机保存和解析。生成任务时请勾选重点资料；被勾选的截图会作为图片输入发送给模型。</small></div><div class="searchbar"><input id="search-query" placeholder="搜索项目资料和已有方法，例如：竞品差异 权限要求" aria-label="检索关键词"><button id="search">检索依据</button></div><div id="search-results"></div><div class="section-title"><h2>资料目录</h2><span class="muted">${state.documents.length} 份</span></div><div class="card">${state.documents.map((d) => `<div class="row"><div class="row-main"><h3>${E(d.name)}</h3><p>${E(kinds[d.kind])} · ${d.characters.toLocaleString()} 字符 · ${date(d.created)}</p></div><button class="small" data-document="${E(d.id)}">读原文</button></div>`).join("") || '<div class="empty">还没有资料。上传后即可检索和引用。</div>'}</div>`;
  $("#upload").onchange = upload;
  $("#search").onclick = search;
  $("#search-query").onkeydown = (e) => {
    if (e.key === "Enter") search();
  };
}
async function upload(e) {
  const files = Array.from(e.target.files),
    input = e.target;
  input.disabled = true;
  let successful = 0;
  for (const file of files) {
    try {
      if (file.size > 12 * 1024 * 1024) throw Error(file.name + " 超过 12 MB");
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(Error("文件读取失败"));
        reader.readAsDataURL(file);
      });
      const r = await api("/api/documents", {
        project_id: projectId,
        name: file.name,
        content,
      });
      successful++;
      toast(
        r.duplicate ? file.name + " 已存在，已跳过" : file.name + " 已导入",
      );
    } catch (err) {
      error(err);
    }
  }
  await refresh();
  toast(`已处理 ${successful}/${files.length} 份资料`);
}
async function search() {
  const button = $("#search");
  button.disabled = true;
  try {
    const results = await api(
      "/api/search?project=" +
        projectId +
        "&q=" +
        encodeURIComponent($("#search-query").value),
    );
    $("#search-results").innerHTML =
      `<div class="help">${state.runtime.retrieval} · 返回原文片段，匹配分数不代表事实可信度。</div>` +
      results
        .map(
          (r) =>
            `<div class="card"><h3>${E(r.name)} <span class="tag">${E(kinds[r.kind])}</span></h3><small>${E(r.location)} · 片段 ${r.chunk}</small><p class="excerpt">${E(r.text)}</p></div>`,
        )
        .join("") +
      (results.length
        ? ""
        : '<div class="empty">没有匹配依据，试试更具体的关键词。</div>');
  } catch (e) {
    error(e);
  } finally {
    button.disabled = false;
  }
}
function drawTasks() {
  $("#view").innerHTML =
    `${state.mode_mismatch_count ? `<div class="banner">当前项目是“${E(workflowNames[state.project.workflow_mode])}”，历史任务可能由另一模式生成。下面只显示当前模式可新建的任务。</div>` : ""}<div class="section-title"><h2>选择这次的交付物</h2><span class="muted">独立运行 · 按需组合</span></div><div class="grid">${state.packs
      .filter((p) => p.enabled)
      .flatMap((p) =>
        p.tasks.filter((t) => !t.hidden && (!t.modes || t.modes.includes(state.project.workflow_mode))).map(
          (t, i) =>
            `<article class="card task-card"><div class="eyebrow">${E(p.name)} / ${String(i + 1).padStart(2, "0")}</div><h3>${E(t.name)}</h3><p>${E(t.description)}</p><footer><span>${t.tools.length} 项能力 · 中文 Markdown</span><button class="primary" data-task="${E(t.key)}">准备任务 →</button></footer></article>`,
        ),
      )
      .join(
        "",
      )}</div><div class="help">先生成可检查的任务包；确认资料、模板和目标后启动模型。你也可以下载任务包，在现有 AI 对话中完成，再导入结果。</div><button data-action="capabilities">查看可扩展能力</button>`;
}
function drawOutputs() {
  $("#view").innerHTML =
    `<div class="section-title"><div><h2>任务与交付记录</h2><p class="muted">修订关系、生成时模式和历史执行都会保留。</p></div><label class="inline-filter" for="output-filter">显示<select id="output-filter"><option value="latest" ${outputFilter === "latest" ? "selected" : ""}>各分支最新版</option><option value="all" ${outputFilter === "all" ? "selected" : ""}>全部未归档</option><option value="attention" ${outputFilter === "attention" ? "selected" : ""}>需要处理</option><option value="accepted" ${outputFilter === "accepted" ? "selected" : ""}>已确认</option><option value="prepared" ${outputFilter === "prepared" ? "selected" : ""}>待执行</option><option value="completed" ${outputFilter === "completed" ? "selected" : ""}>待评审</option><option value="archived" ${outputFilter === "archived" ? "selected" : ""}>已归档</option></select></label></div><div class="card">${jobRows(filteredJobs())}</div>`;
  $("#output-filter").onchange = (event) => {
    outputFilter = event.target.value;
    drawOutputs();
  };
}

function drawTrash() {
  $("#content").innerHTML =
    `<div class="heading"><div><div class="eyebrow">RECYCLE BIN</div><h1>项目回收站</h1><p>删除项目后，完整快照、资料和交付物保留在本机。恢复不会覆盖当前项目。</p></div><button data-tab="overview">返回项目</button></div><div class="card">${(state.trash || []).map((item) => `<div class="row"><div class="row-main"><h3>${E(item.name)}</h3><p>${item.deleted_at ? date(item.deleted_at) : "时间未知"} · ${item.document_count} 份资料 · ${item.job_count} 个任务${item.restored ? " · 已恢复，备份仍保留" : ""}</p></div><div class="actions">${item.restored ? "" : `<button class="primary small" data-trash-restore="${E(item.id)}">恢复项目</button>`}<button class="danger small" data-trash-delete="${E(item.id)}" data-trash-name="${E(item.name)}">永久删除</button></div></div>`).join("") || '<div class="empty">回收站是空的。</div>'}</div>`;
}

function confirmPermanentDeleteTrash(id, name) {
  modal(
    "永久删除",
    `<h2>永久删除「${E(name)}」</h2><div class="banner">这会删除本机回收备份，之后无法恢复。</div><form id="trash-delete-form"><label for="trash-confirmation">输入完整项目名称</label><input id="trash-confirmation" autocomplete="off" required placeholder="${E(name)}"><div class="actions"><button class="danger" type="submit">永久删除</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  $("#trash-delete-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      await api("/api/trash/delete", {
        id,
        confirmation: $("#trash-confirmation").value,
      });
      close();
      await refresh();
      toast(`回收备份「${name}」已永久删除`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}
function drawCapabilities() {
  $("#content").innerHTML =
    `<div class="heading"><div><div class="eyebrow">CAPABILITY LIBRARY</div><h1>让工作台随工作生长。</h1><p>启用能力后，项目中会出现对应任务。任务、资料和交付物仍使用同一套工作方式。</p></div><button data-tab="overview">返回项目</button></div><div class="grid">${state.packs.map((p) => `<div class="card"><div class="pack-title"><h2>${E(p.name)}</h2><span class="tag">${p.enabled ? "已启用" : "可启用"}</span></div><p class="muted">${E(p.description)}</p><div class="chipline">${p.tasks.map((t) => `<span class="tag">${E(t.name)}</span>`).join("")}</div><button data-pack="${E(p.id)}" data-enabled="${!p.enabled}">${p.enabled ? "停用此能力" : "启用此能力"}</button></div>`).join("")}</div><div class="section-title"><h2>工具接入</h2></div><div class="card">${state.tools.map((t) => `<div class="row"><div class="row-main"><h3>${E(t.name)}</h3><p>${E(t.description)}</p></div><span class="tag ${t.status === "manual" ? "warn" : ""}">${t.id === "codex" ? (state.runtime.available ? "已找到 CLI" : "未找到 CLI") : t.status === "ready" ? "已接入" : "手动导入"}</span></div>`).join("")}</div><div class="section-title"><h2>运行环境</h2></div><div class="card"><p>生成模型：<span class="mono">${E(state.runtime.model)}</span></p><p>知识来源：${state.runtime.knowledge_count} 份已启用方法、模板与案例。</p><p>检索方式：${E(state.runtime.retrieval)}。现有 Hybrid RAG 仍可从 Product KB MCP 使用，工作台暂未接上语义向量检索。</p><div class="help">扩展方式：在 workbench/capabilities 中增加 JSON 能力定义，引用仓库内 Markdown 模板，即可新增任务。新工具的实际执行需要编写后端适配器，添加名字不会自动获得工具能力。</div></div>`;
}
function newProject() {
  modal(
    "新建项目",
    `<h2>先留下项目的起点。</h2><form id="new-form"><label for="project-name">项目名称</label><input id="project-name" required maxlength="100" placeholder="例如：GBA Emulator"><div class="grid"><div><label for="new-workflow-mode">工作流模式</label><select id="new-workflow-mode"><option value="fast">快速迭代（默认）</option><option value="full">完整研究</option></select></div><div><label for="new-platform">目标平台</label><input id="new-platform" maxlength="80" value="Android-first"></div><div><label for="new-timebox">验证周期</label><input id="new-timebox" maxlength="80" value="1–2 周"></div><div><label for="new-team">团队与资源</label><input id="new-team" maxlength="1000" placeholder="1 产品、1 Android、设计兼职、无专职 QA"></div></div><label for="project-brief">想做什么，已经确定了什么？</label><textarea id="project-brief" maxlength="12000" placeholder="描述产品方向、对标竞品、核心能力和已知硬约束。暂时不知道的可以留空。"></textarea><div class="help">快速模式默认品类已决定，不执行机会门否决。新建项目不会自动启动分析。</div><button class="primary" type="submit">创建项目</button></form>`,
  );
  $("#new-form").onsubmit = async (e) => {
    e.preventDefault();
    const b = e.submitter;
    b.disabled = true;
    try {
      const p = await api("/api/projects", {
        name: $("#project-name").value,
        brief: $("#project-brief").value,
        workflow_mode: $("#new-workflow-mode").value,
        platform: $("#new-platform").value,
        team: $("#new-team").value,
        timebox: $("#new-timebox").value,
      });
      projectId = p.id;
      localStorage.setItem("workbench-project", projectId);
      tab = "context";
      close();
      await refresh();
      toast("项目已创建");
    } catch (e) {
      error(e);
      b.disabled = false;
    }
  };
}
function confirmDeleteProject() {
  const project = { ...state.project };
  modal(
    "删除项目",
    `<h2>确认删除「${E(project.name)}」</h2><div class="banner">项目、任务和交付物会移入本机回收站，可以稍后恢复。</div><p>请输入完整项目名称以继续：</p><form id="delete-project-form"><label for="delete-confirmation">${E(project.name)}</label><input id="delete-confirmation" autocomplete="off" required placeholder="输入完整项目名称"><div class="actions"><button class="danger" type="submit">移入回收站</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  $("#delete-project-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      await api("/api/project/delete", {
        id: project.id,
        confirmation: $("#delete-confirmation").value,
      });
      projectId = null;
      activeJob = null;
      localStorage.removeItem("workbench-project");
      close();
      await refresh();
      toast(`项目「${project.name}」已移入回收站`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}
function prepareTask(key) {
  const t = state.packs.flatMap((p) => p.tasks).find((t) => t.key === key);
  const upstream = t.recommended_upstream
    ? state.packs.flatMap((p) => p.tasks).find((item) => item.key === t.recommended_upstream)
    : null;
  const upstreamAccepted = !t.recommended_upstream || state.jobs.some(
    (job) => job.task_id === t.recommended_upstream && job.review_decision === "accepted",
  );
  modal(
    "准备任务",
    `<div class="eyebrow">${E(t.output)}</div><h2>${E(t.name)}</h2><p class="muted">${E(t.description)}</p>${upstreamAccepted ? "" : `<div class="banner">推荐先确认“${E(upstream?.name || t.recommended_upstream)}”。你仍可继续准备本任务，但系统会把它标记为缺少已确认上游。</div>`}<div class="chipline">${t.tools.map((id) => `<span class="tag">${E(state.tools.find((t) => t.id === id)?.name || id)}</span>`).join("")}</div><form id="task-form"><label for="instruction">这次的具体要求</label><textarea id="instruction" maxlength="12000" placeholder="希望解决的问题、重点、范围、交付深度…"></textarea><label>指定要写进文档的资料（可选，最多 12 份）</label><div class="checks">${
      state.documents
        .filter((d) => ["upload", "accepted", "deliverable"].includes(d.kind))
        .map(
          (d) =>
            `<label><input type="checkbox" name="docs" value="${E(d.id)}">${E(d.name)}${d.kind === "deliverable" ? "（草稿，将附带警告）" : ""}</label>`,
        )
        .join("") ||
      "<small>没有可指定的资料；可以先导入，也可以先准备任务。</small>"
    }</div><div class="help">模板：${E(t.template)}<br>快速模式会把勾选的评论、政策、日志、截图和研究资料写入资料索引并用于相关结论。指定文本每份最多带入 12000 字；图片作为视觉输入。</div><button class="primary" type="submit">生成任务包</button></form>`,
  );
  $("#task-form").onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      const j = await api("/api/prepare", {
        project_id: projectId,
        task: key,
        instruction: $("#instruction").value,
        document_ids: Array.from(
          document.querySelectorAll("input[name=docs]:checked"),
        ).map((i) => i.value),
      });
      await refresh();
      showJob(j);
    } catch (err) {
      error(err);
      e.submitter.disabled = false;
    }
  };
}
function renderMarkdown(text, annotate = false, comments = []) {
  // Escape before formatting. Raw HTML and embedded media are never executed.
  const inline = (s) =>
    E(s)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  const plain = (s) =>
    String(s)
      .replace(/\*\*|__|`|^#+\s*/g, "")
      .replace(/\s+/g, " ")
      .trim();
  let lines = text.split("\n");
  let out = "",
    table = [],
    code = [];
  let inCode = false,
    blockIndex = 0;
  if (annotate) renderedBlocks = {};
  if (lines[0]?.trim() === "---") {
    const closing = lines.slice(1).findIndex((line) => line.trim() === "---");
    if (closing >= 0) {
      const metadata = lines.slice(1, closing + 1).join("\n");
      out += `<details class="frontmatter"><summary>文档元数据</summary><pre>${E(metadata)}</pre></details>`;
      lines = lines.slice(closing + 2);
    }
  }
  const addBlock = (type, label, quote, html) => {
    if (!annotate) {
      out += html;
      return;
    }
    const id = `block-${++blockIndex}`;
    const block = {
      block_id: id,
      block_type: type,
      block_label: plain(label).slice(0, 300) || `未命名${type}`,
      quote: String(quote).trim().slice(0, 1200),
    };
    renderedBlocks[id] = block;
    const related = comments.filter((item) => item.quote === block.quote);
    const open = related.filter((item) => item.status === "open").length;
    const labelText = related.length
      ? `${related.length} 条批注${open ? ` · ${open} 条待处理` : ""}`
      : "添加批注";
    out += `<div class="commentable-block ${related.length ? "has-comments" : ""}"><div class="commentable-content">${html}</div><button class="comment-button" aria-label="${E(labelText)}：${E(block.block_label)}" data-add-comment="${id}" type="button">${E(labelText)}</button></div>`;
  };
  const flushTable = () => {
    if (!table.length) return;
    const raw = table.join("\n");
    const tableHtml =
      '<div class="table-scroll"><table>' +
      table
        .filter((l) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(l))
        .map(
          (l, i) =>
            "<tr>" +
            l
              .trim()
              .replace(/^\||\|$/g, "")
              .split("|")
              .map(
                (c) =>
                  `<${i === 0 ? "th" : "td"}>${inline(c.trim())}</${i === 0 ? "th" : "td"}>`,
              )
              .join("") +
            "</tr>",
        )
        .join("") +
      "</table></div>";
    addBlock("table", plain(table[0]).slice(0, 80) || "表格", raw, tableHtml);
    table = [];
  };
  const flushCode = () => {
    if (!code.length) return;
    const raw = code.join("\n");
    addBlock("code", raw.slice(0, 80) || "代码块", raw, `<pre><code>${E(raw)}</code></pre>`);
    code = [];
  };
  for (const line of lines) {
    if (line.startsWith("```")) {
      flushTable();
      if (inCode) flushCode();
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    if (line.trim().startsWith("|")) {
      table.push(line);
      continue;
    }
    flushTable();
    const heading = line.match(/^(#{1,6}) (.*)/);
    if (heading)
      addBlock(
        "heading",
        heading[2],
        line,
        `<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`,
      );
    else if (line.startsWith("> "))
      addBlock(
        "blockquote",
        line.slice(2, 82),
        line,
        "<blockquote>" + inline(line.slice(2)) + "</blockquote>",
      );
    else if (line.trim())
      addBlock(
        "paragraph",
        line.slice(0, 80),
        line,
        "<p>" + inline(line) + "</p>",
      );
  }
  flushTable();
  if (inCode || code.length) flushCode();
  return out;
}
function commentsPanel(job) {
  const current = (job.comments || []).filter(
      (item) => item.version === job.current_version,
    ),
    historyCount = (job.comments || []).length - current.length,
    open = current.filter((item) => item.status === "open");
  return `<section class="comments-panel"><div class="split"><div><div class="eyebrow">定位批注 / V${job.current_version}</div><h3>按章节、段落或表格提出修改</h3></div>${open.length ? `<button class="primary" data-revise-comments="${E(job.id)}">按 ${open.length} 条批注精确修订</button>` : ""}</div><p class="muted">批注只属于当前版本。修订任务成功生成新版后，本次使用的批注会自动标记为已解决；生成前不会改变原批注。</p><div class="comment-list">${current
    .map(
      (item) =>
        `<article class="comment-item ${item.status === "resolved" ? "resolved" : ""}"><div class="split"><div class="chipline"><span class="tag">${E(commentActionNames[item.action] || item.action)}</span><span class="tag ${item.status === "open" ? "warn" : ""}">${item.status === "open" ? "待处理" : "已解决"}</span></div><button class="small" data-comment-status="${item.status === "open" ? "resolved" : "open"}" data-comment-id="${E(item.id)}" data-id="${E(job.id)}">${item.status === "open" ? "标记已解决" : "重新打开"}</button></div><strong>${E(item.block_label)}</strong><div class="comment-quote">${E(item.quote)}</div><p>${E(item.note)}</p><small>${E(item.author)} · ${date(item.created)}</small></article>`,
    )
    .join("") || '<div class="empty compact">当前版本还没有批注。</div>'}</div>${historyCount ? `<p class="muted">另有 ${historyCount} 条旧版本批注，仅保留为历史记录，不会用于本次修订。</p>` : ""}</section>`;
}
function showJob(job) {
  activeJob = job.id;
  const running = ["running", "queued"].includes(job.status),
    review = job.review,
    restorable = ["cancelled", "failed", "interrupted"].includes(job.status),
    reviewReasons = [
      job.open_comment_count ? `当前版本还有 ${job.open_comment_count} 条待处理批注` : "",
      (job.citation_issues || []).length ? `正文包含无法追溯的来源：${job.citation_issues.join("、")}` : "",
    ].filter(Boolean),
    reviewBlocked = reviewReasons.length > 0,
    reviewReason = reviewReasons.join("；");
  const outputHtml = job.output
    ? `<div class="actions"><button class="primary" data-edit="${E(job.id)}">编辑正文</button><button data-versions="${E(job.id)}">版本记录（${job.version_count || 1}）</button><a href="/api/jobs/${E(job.id)}/download">下载 Markdown</a><span class="tag">${review ? (review.decision === "accepted" ? "已确认 · 可用于后续任务" : "需要修改") : "尚未评审"}</span></div>${reviewBlocked ? `<div class="banner" id="review-block-reason">暂不能确认：${E(reviewReason)}。请处理后再确认。</div>` : ""}<div class="document document-render">${renderMarkdown(job.output, true, (job.comments || []).filter((item) => item.version === job.current_version))}</div>${commentsPanel(job)}<div class="help">评审重点：核心场景是否齐全、关键结论是否有证据、异常与边界是否闭合。确认只作用于此项目，不会自动发布为全局知识。</div><label for="review-note">整份文档评审（可选）</label><textarea id="review-note" maxlength="12000" placeholder="这里用于整份文档的总体意见；局部修改请直接在正文旁添加批注。">${E(review?.note || "")}</textarea><div class="actions review-actions"><button class="primary" data-review="accepted" data-id="${E(job.id)}" ${reviewBlocked ? 'disabled aria-describedby="review-block-reason"' : ""}>确认这份交付物</button><button data-review="changes_requested" data-id="${E(job.id)}">记录整体修改意见</button></div>`
    : "";
  modal(
    "任务记录",
    `<div class="split"><div><h2>${E(job.title)}${job.revision_number > 1 ? ` · 修订 V${job.revision_number}` : ""}</h2><div class="chipline"><span class="tag">生成时模式：${E(workflowNames[job.workflow_mode] || job.workflow_mode)}</span>${job.is_latest === 0 || job.has_newer_revision ? '<span class="tag">已有后续修订</span>' : '<span class="tag">当前分支最新版</span>'}${job.archived ? '<span class="tag">已归档</span>' : ""}</div></div>${badge(job.status)}</div><p class="muted">${date(job.created)} · ${job.sources.length} 段资料已快照保存${job.parent_job_id ? ` · 修订自上一任务 V${job.source_version || 1}` : ""}</p><div class="actions">${job.parent_job_id ? `<button class="small" data-job="${E(job.parent_job_id)}">查看上一任务</button>` : ""}${running ? "" : `<button class="small" data-archive-job="${E(job.id)}" data-archived="${job.archived ? "false" : "true"}">${job.archived ? "取消归档" : "归档任务"}</button>`}</div>${job.error ? `<div class="banner">${E(job.error)}</div>` : ""}${job.status === "prepared" ? `<div class="help">执行将把任务包中的项目背景和引用资料发送给 Codex 模型服务，使用你的账号额度。先检查下方输入依据；生成后仍需评审。</div><div class="actions"><button class="primary" data-run="${E(job.id)}" ${state.runtime.available ? "" : "disabled"}>开始生成</button><a href="/api/jobs/${E(job.id)}/prompt">下载任务包</a><button data-import="${E(job.id)}">导入已有结果</button><button data-cancel="${E(job.id)}">取消任务</button></div>` : ""}${running ? `<div class="progress-note"><span class="spinner"></span>正在生成，状态会自动更新。完整分析可能需要几分钟。</div><button data-cancel="${E(job.id)}">停止生成</button>` : ""}${restorable ? `<div class="help">任务包和输入快照仍然保留。恢复后可以重新生成或导入已有结果，原错误记录不会写进交付物。</div><button class="primary" data-restore-job="${E(job.id)}">恢复为待执行</button>` : ""}${outputHtml}<details><summary>本次输入：项目背景、完整模板与任务要求</summary><pre class="document">${E(job.prompt)}</pre></details><details><summary>查看 ${job.sources.length} 段引用资料</summary>${job.sources.map((s) => `<div class="card"><h3>[${E(s.citation)}] ${E(s.name)}</h3><small>${E(kinds[s.kind])} · 片段 ${s.chunk}${s.truncated ? " · 超出 12000 字，已截断" : ""}</small><div class="excerpt">${E(s.text)}</div></div>`).join("") || "<p>没有检索到匹配材料。</p>"}</details>`,
  );
  if (review?.decision === "changes_requested") {
    const button = document.createElement("button");
    button.textContent = "按意见准备修订版";
    button.dataset.revise = job.id;
    $("#modal-body .review-actions").append(button);
  }
}
function commentForm(job, block) {
  const reviewer = localStorage.getItem("workbench-reviewer") || "";
  modal(
    "添加定位批注",
    `<div class="split"><div><div class="eyebrow">V${job.current_version} / ${E(commentBlockNames[block.block_type] || block.block_type)}</div><h2>${E(block.block_label)}</h2></div><button data-job="${E(job.id)}">返回正文</button></div><div class="comment-quote">${E(block.quote)}</div><form id="comment-form"><label for="comment-action">希望怎么处理</label><select id="comment-action"><option value="modify">修改</option><option value="add">新增</option><option value="delete">删除</option><option value="compress">压缩</option><option value="preserve">保留，不允许后续改动</option></select><label for="comment-note">具体意见</label><textarea id="comment-note" maxlength="4000" required placeholder="例如：这里改成与竞品 A 的差异，并补充离线存档规则。"></textarea><label for="comment-author">提出人</label><input id="comment-author" maxlength="120" value="${E(reviewer)}" placeholder="姓名或角色（选填）"><div class="help">批注绑定当前 V${job.current_version} 和这段原文。正文版本变化后，它只作为历史记录保留。</div><button class="primary" type="submit">保存批注</button></form>`,
  );
  $("#comment-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const author = $("#comment-author").value.trim();
      if (author) localStorage.setItem("workbench-reviewer", author);
      await api(`/api/jobs/${job.id}/comments`, {
        version: job.current_version,
        ...block,
        action: $("#comment-action").value,
        note: $("#comment-note").value,
        author,
      });
      showJob(await api(`/api/jobs/${job.id}`));
      toast("批注已添加到指定位置");
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}
function editJob(job) {
  modal(
    "编辑交付物",
    `<div class="split"><h2>${E(job.title)}</h2><span class="tag">当前 V${job.current_version || 1}</span></div><div class="help">按 Markdown 直接修改。保存会生成新版本；如果原文已经确认，确认状态会被清除，新内容回到待评审草稿。</div><form id="edit-output-form"><label for="output-editor">正文</label><textarea id="output-editor" class="output-editor" maxlength="2000000" required>${E(job.output)}</textarea><label for="edit-note">修改说明（选填）</label><input id="edit-note" maxlength="500" placeholder="例如：补充核心流程，删减重复背景"><div class="actions"><button class="primary" type="submit">保存为新版本</button><button type="button" data-edit-cancel="${E(job.id)}">取消</button></div></form>`,
  );
  $("#edit-output-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const updated = await api(`/api/jobs/${job.id}/edit`, {
        output: $("#output-editor").value,
        note: $("#edit-note").value,
      });
      await refresh();
      showJob(updated);
      toast(`已保存为 V${updated.current_version}`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}
async function showVersions(jobId) {
  const [job, versions] = await Promise.all([
    api(`/api/jobs/${jobId}`),
    api(`/api/jobs/${jobId}/versions`),
  ]);
  modal(
    "版本记录",
    `<div class="split"><h2>${E(job.title)}</h2><button data-job="${E(job.id)}">返回正文</button></div><p class="muted">恢复旧版会另存为一个新版本，现有历史不会被覆盖。</p><div class="version-list">${versions.map((item) => `<div class="row"><div class="row-main"><h3>V${item.version} ${item.version === job.current_version ? '<span class="tag">当前版本</span>' : ""}</h3><p>${E(versionSourceNames[item.source] || item.source)} · ${date(item.created)} · ${item.characters} 字${item.note ? ` · ${E(item.note)}` : ""}</p></div><button data-view-version="${item.version}" data-id="${E(job.id)}">查看</button></div>`).join("")}</div>`,
  );
}
async function showVersion(jobId, versionNumber) {
  const [job, item] = await Promise.all([
    api(`/api/jobs/${jobId}`),
    api(`/api/jobs/${jobId}/versions/${versionNumber}`),
  ]);
  modal(
    `查看 V${item.version}`,
    `<div class="split"><div><h2>${E(job.title)}</h2><p class="muted">${E(versionSourceNames[item.source] || item.source)} · ${date(item.created)}${item.note ? ` · ${E(item.note)}` : ""}</p></div><button data-versions="${E(job.id)}">返回版本记录</button></div><div class="actions"><button class="primary" data-version-restore="${item.version}" data-id="${E(job.id)}" ${item.version === job.current_version ? "disabled" : ""}>恢复为新版本</button></div><div class="document document-render">${renderMarkdown(item.output)}</div>`,
  );
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    if (b.dataset.project) {
      projectId = b.dataset.project;
      localStorage.setItem("workbench-project", projectId);
      tab = "overview";
      await refresh();
    } else if (b.dataset.tab) {
      tab = b.dataset.tab;
      draw();
    } else if (b.dataset.action === "new") newProject();
    else if (b.dataset.action === "delete-project") confirmDeleteProject();
    else if (b.dataset.trashRestore) {
      b.disabled = true;
      const project = await api("/api/trash/restore", { id: b.dataset.trashRestore });
      projectId = project.id;
      localStorage.setItem("workbench-project", projectId);
      tab = "overview";
      await refresh();
      toast(`项目「${project.name}」已恢复`);
    } else if (b.dataset.trashDelete) {
      confirmPermanentDeleteTrash(b.dataset.trashDelete, b.dataset.trashName);
    }
    else if (b.hasAttribute("data-close-modal")) close();
    else if (b.dataset.action === "capabilities") {
      tab = "capabilities";
      draw();
    } else if (b.dataset.pack) {
      b.disabled = true;
      await api("/api/packs", {
        id: b.dataset.pack,
        enabled: b.dataset.enabled === "true",
      });
      await refresh();
      toast("能力设置已保存，项目任务已更新");
    } else if (b.dataset.task) prepareTask(b.dataset.task);
    else if (b.dataset.condition) {
      const item = (state.conditions || []).find((c) => c.id === b.dataset.condition);
      if (item) conditionForm(item);
    } else if (b.dataset.action === "new-condition") conditionForm();
    else if (b.dataset.job) showJob(await api("/api/jobs/" + b.dataset.job));
    else if (b.dataset.edit) editJob(await api("/api/jobs/" + b.dataset.edit));
    else if (b.dataset.editCancel)
      showJob(await api("/api/jobs/" + b.dataset.editCancel));
    else if (b.dataset.versions) await showVersions(b.dataset.versions);
    else if (b.dataset.viewVersion)
      await showVersion(b.dataset.id, b.dataset.viewVersion);
    else if (b.dataset.versionRestore) {
      b.disabled = true;
      const job = await api(
        `/api/jobs/${b.dataset.id}/versions/${b.dataset.versionRestore}`,
        {},
      );
      await refresh();
      showJob(job);
      toast(`已恢复并保存为 V${job.current_version}`);
    } else if (b.dataset.revise) {
      b.disabled = true;
      const job = await api("/api/jobs/" + b.dataset.revise + "/revise", {});
      await refresh();
      showJob(job);
    } else if (b.dataset.addComment) {
      const job = await api(`/api/jobs/${activeJob}`),
        block = renderedBlocks[b.dataset.addComment];
      if (!block) throw Error("批注位置已变化，请刷新正文后重试");
      commentForm(job, block);
    } else if (b.dataset.commentStatus) {
      b.disabled = true;
      await api(`/api/jobs/${b.dataset.id}/comments/${b.dataset.commentId}`, {
        status: b.dataset.commentStatus,
      });
      showJob(await api(`/api/jobs/${b.dataset.id}`));
      toast(b.dataset.commentStatus === "resolved" ? "批注已标记为解决" : "批注已重新打开");
    } else if (b.dataset.reviseComments) {
      b.disabled = true;
      const job = await api(
        `/api/jobs/${b.dataset.reviseComments}/revise-comments`,
        {},
      );
      await refresh();
      showJob(job);
      toast("已按当前版本的待处理批注准备修订任务");
    } else if (b.dataset.document) {
      const d = await api("/api/documents/" + b.dataset.document);
      modal(
        "资料原文",
        `<h2>${E(d.name)}</h2><div class="document">${E(d.text)}</div>`,
      );
    } else if (b.dataset.run) {
      b.disabled = true;
      showJob(await api("/api/jobs/" + b.dataset.run + "/start", {}));
      await refresh();
    } else if (b.dataset.cancel) {
      b.disabled = true;
      showJob(await api("/api/jobs/" + b.dataset.cancel + "/cancel", {}));
      await refresh();
    } else if (b.dataset.restoreCancelled) {
      b.disabled = true;
      showJob(
        await api(
          "/api/jobs/" + b.dataset.restoreCancelled + "/restore-cancelled",
          {},
        ),
      );
      await refresh();
      toast("任务已恢复为待执行");
    } else if (b.dataset.restoreJob) {
      b.disabled = true;
      showJob(await api(`/api/jobs/${b.dataset.restoreJob}/restore`, {}));
      await refresh();
      toast("任务已恢复为待执行，可以重新生成或导入结果");
    } else if (b.dataset.archiveJob) {
      b.disabled = true;
      const archived = b.dataset.archived === "true";
      showJob(await api(`/api/jobs/${b.dataset.archiveJob}/archive`, { archived }));
      await refresh();
      toast(archived ? "任务已归档" : "任务已取消归档");
    } else if (b.dataset.review) {
      b.disabled = true;
      showJob(
        await api("/api/jobs/" + b.dataset.id + "/review", {
          decision: b.dataset.review,
          note: $("#review-note").value,
        }),
      );
      await refresh();
      toast("评审已保存");
    } else if (b.dataset.import) {
      const id = b.dataset.import;
      modal(
        "导入交付物",
        `<h2>把完成的文档放回当前任务</h2><p class="muted">适用于在现有 AI 对话中完成任务后保存结果。</p><form id="import-form"><textarea id="import-output" aria-label="交付物正文" required placeholder="粘贴完整中文 Markdown 正文…"></textarea><button class="primary" type="submit">保存为待评审交付物</button></form>`,
      );
      $("#import-form").onsubmit = async (ev) => {
        ev.preventDefault();
        ev.submitter.disabled = true;
        try {
          const job = await api("/api/jobs/" + id + "/import", {
            output: $("#import-output").value,
          });
          await refresh();
          showJob(job);
        } catch (err) {
          error(err);
          ev.submitter.disabled = false;
        }
      };
    }
  } catch (err) {
    error(err);
    b.disabled = false;
  }
});
$("#new-project").onclick = newProject;
$("#capabilities").onclick = () => {
  tab = "capabilities";
  draw();
};
$("#trash").onclick = () => {
  tab = "trash";
  draw();
};
setInterval(async () => {
  if (polling || !state) return;
  const running = state.jobs?.some((j) =>
    ["queued", "running"].includes(j.status),
  );
  if (!running) return;
  polling = true;
  try {
    const previous = activeJob
      ? state.jobs.find((j) => j.id === activeJob)?.status
      : null;
    await refresh(false);
    if (
      activeJob &&
      state.jobs.find((j) => j.id === activeJob)?.status !== previous
    )
      showJob(await api("/api/jobs/" + activeJob));
    if (["overview", "outputs"].includes(tab)) draw();
  } catch (err) {
    $("#banner").textContent = "连接暂时中断，正在等待本地服务恢复。";
    $("#banner").hidden = false;
  } finally {
    polling = false;
  }
}, 3500);
(async () => {
  try {
    const initial = await api("/api/state");
    state = initial;
    if (!state.projects.some((p) => p.id === projectId)) {
      projectId = state.projects[0]?.id || null;
      localStorage.removeItem("workbench-project");
    }
    await refresh();
  } catch (err) {
    $("#content").innerHTML =
      '<div class="empty"><h2>暂时无法连接工作台</h2><p>' +
      E(err.message) +
      "</p><p>请检查本地服务已启动，再刷新页面。</p></div>";
  }
})();
