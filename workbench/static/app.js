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
  polling = false,
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
      : "工作空间 / " + (state.project?.name || "项目");
  if (tab === "capabilities") return drawCapabilities();
  if (!state.project) {
    $("#content").innerHTML =
      `<div class="empty"><div class="welcome-mark">P /</div><div class="eyebrow">从背景开始，向交付推进</div><h2>把你的产品工作接起来。</h2><p>创建一个项目，留下背景和已有资料。选择这次需要的交付物，后面的工作可以随时继续。</p><button class="primary" data-action="new">创建第一个项目</button><div class="help">已连接 ${state.runtime.knowledge_count} 份方法与模板 · 包含完整新品分析模板</div></div>`;
    return;
  }
  $("#content").innerHTML =
    `<div class="heading"><div><div class="eyebrow">PROJECT WORKSPACE</div><h1>${E(state.project.name)}</h1><p>${E(state.project.brief || "先补充项目背景，让后续任务有依据。")}</p></div><button class="primary" data-tab="tasks">开始一项任务 ↗</button></div><nav class="tabs" aria-label="工作区"><button data-tab="overview" class="${tab === "overview" ? "active" : ""}">项目概览</button><button data-tab="context" class="${tab === "context" ? "active" : ""}">项目背景</button><button data-tab="materials" class="${tab === "materials" ? "active" : ""}">资料与检索</button><button data-tab="tasks" class="${tab === "tasks" ? "active" : ""}">任务</button><button data-tab="outputs" class="${tab === "outputs" ? "active" : ""}">交付物</button></nav><div id="view"></div>`;
  (
    ({
      overview: drawOverview,
      context: drawContext,
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
          `<div class="row"><div class="row-main"><h3>${E(j.title)}</h3><p>${date(j.created)} · ${E(j.error || "执行记录与引用资料可追溯")}</p></div>${badge(j.review_decision === "accepted" ? "已确认" : j.review_decision === "changes_requested" ? "需修改" : j.status)}<button class="small" data-job="${E(j.id)}">查看</button></div>`,
      )
      .join("") ||
    '<div class="empty">暂时没有记录。按你当前需要，开始一项任务。</div>'
  );
}
function drawOverview() {
  const docs = state.documents,
    jobs = state.jobs;
  $("#view").innerHTML =
    `<div class="grid"><div class="card hero"><div class="eyebrow">这次，要完成什么？</div><h2>一次推进一项工作，<br>留下可以继续用的成果。</h2><p>无需按顺序跑完所有阶段。先补背景，选交付物，再检查引用的依据。</p><button data-tab="tasks">选择交付任务 →</button></div><div class="card"><h3>当前工作</h3><p>${E(state.context.working || "还没有记录当前目标。可以写下这周要解决的问题、已确定的方向和暂时不做的事。")}</p><button class="small" data-tab="context">维护项目上下文</button><div class="help">草稿通过评审后，才会进入后续任务的项目检索。</div></div></div><div class="stats"><div class="stat"><b>${docs.filter((d) => d.kind === "upload").length}</b><span>已导入资料</span></div><div class="stat"><b>${jobs.filter((j) => ["running", "queued"].includes(j.status)).length}</b><span>正在执行</span></div><div class="stat"><b>${docs.filter((d) => d.kind === "accepted").length}</b><span>已确认交付物</span></div></div><div class="section-title"><h2>最近的工作</h2><button class="small" data-tab="outputs">全部记录</button></div><div class="card">${jobRows(jobs.slice(0, 4))}</div>`;
}
function drawContext() {
  $("#view").innerHTML =
    `<form id="context-form"><div class="grid"><div class="card context-card"><div class="eyebrow">01 / 长期背景</div><h2>这个项目是什么</h2><p>目标用户、平台与地区、团队资源、技术约束。</p><textarea id="foundation" maxlength="12000" aria-label="长期背景" placeholder="目标用户：\n平台与地区：\n团队与资源：\n约束：">${E(state.context.foundation)}</textarea><small>每次任务自动带入；不知道的内容可以暂留空。</small></div><div class="card context-card"><div class="eyebrow">02 / 当前工作</div><h2>现在推进到哪里</h2><p>当前目标、已确认决策、正在解决的问题。</p><textarea id="working" maxlength="12000" aria-label="当前工作" placeholder="当前目标：\n已确认决策：\n待解决问题：\n本轮不做：">${E(state.context.working)}</textarea><small>迭代变化时更新；执行过的任务仍保留当时快照。</small></div></div><label for="brief">项目简介</label><textarea id="brief" maxlength="12000">${E(state.project.brief)}</textarea><div class="help">第三层是每次任务的具体要求，在开始任务时填写。</div><button class="primary" type="submit">保存项目背景</button></form>`;
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
      });
      await refresh();
      toast("项目背景已保存");
    } catch (e) {
      error(e);
    }
  };
}
function drawMaterials() {
  $("#view").innerHTML =
    `<div class="section-title"><h2>资料留在项目里，依据带进任务中。</h2></div><div class="drop"><strong>导入需求文档、调研资料或竞品评论</strong><p class="muted">MD · TXT · CSV · JSON · 文本 PDF · DOCX，每份最大 12 MB</p><input type="file" id="upload" multiple accept=".md,.txt,.csv,.json,.pdf,.docx" aria-label="选择要导入的资料"><small>上传后在本机解析。只有点击生成时，任务包中的背景和资料才会发送给模型服务。</small></div><div class="searchbar"><input id="search-query" placeholder="搜索项目资料和已有方法，例如：新品分析 用户痛点" aria-label="检索关键词"><button id="search">检索依据</button></div><div id="search-results"></div><div class="section-title"><h2>资料目录</h2><span class="muted">${state.documents.length} 份</span></div><div class="card">${state.documents.map((d) => `<div class="row"><div class="row-main"><h3>${E(d.name)}</h3><p>${E(kinds[d.kind])} · ${d.characters.toLocaleString()} 字符 · ${date(d.created)}</p></div><button class="small" data-document="${E(d.id)}">读原文</button></div>`).join("") || '<div class="empty">还没有资料。上传后即可检索和引用。</div>'}</div>`;
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
    `<div class="section-title"><h2>选择这次的交付物</h2><span class="muted">独立运行 · 按需组合</span></div><div class="grid">${state.packs
      .filter((p) => p.enabled)
      .flatMap((p) =>
        p.tasks.map(
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
    `<div class="section-title"><h2>任务与交付记录</h2><span class="muted">保留每一次执行</span></div><div class="card">${jobRows(state.jobs)}</div>`;
}
function drawCapabilities() {
  $("#content").innerHTML =
    `<div class="heading"><div><div class="eyebrow">CAPABILITY LIBRARY</div><h1>让工作台随工作生长。</h1><p>启用能力后，项目中会出现对应任务。任务、资料和交付物仍使用同一套工作方式。</p></div><button data-tab="overview">返回项目</button></div><div class="grid">${state.packs.map((p) => `<div class="card"><div class="pack-title"><h2>${E(p.name)}</h2><span class="tag">${p.enabled ? "已启用" : "可启用"}</span></div><p class="muted">${E(p.description)}</p><div class="chipline">${p.tasks.map((t) => `<span class="tag">${E(t.name)}</span>`).join("")}</div><button data-pack="${E(p.id)}" data-enabled="${!p.enabled}">${p.enabled ? "停用此能力" : "启用此能力"}</button></div>`).join("")}</div><div class="section-title"><h2>工具接入</h2></div><div class="card">${state.tools.map((t) => `<div class="row"><div class="row-main"><h3>${E(t.name)}</h3><p>${E(t.description)}</p></div><span class="tag ${t.status === "manual" ? "warn" : ""}">${t.id === "codex" ? (state.runtime.available ? "已找到 CLI" : "未找到 CLI") : t.status === "ready" ? "已接入" : "手动导入"}</span></div>`).join("")}</div><div class="section-title"><h2>运行环境</h2></div><div class="card"><p>生成模型：<span class="mono">${E(state.runtime.model)}</span></p><p>知识来源：${state.runtime.knowledge_count} 份已启用方法、模板与案例。</p><p>检索方式：${E(state.runtime.retrieval)}。现有 Hybrid RAG 仍可从 Product KB MCP 使用，工作台暂未接上语义向量检索。</p><div class="help">扩展方式：在 workbench/capabilities 中增加 JSON 能力定义，引用仓库内 Markdown 模板，即可新增任务。新工具的实际执行需要编写后端适配器，添加名字不会自动获得工具能力。</div></div>`;
}
function newProject() {
  modal(
    "新建项目",
    `<h2>先留下项目的起点。</h2><form id="new-form"><label for="project-name">项目名称</label><input id="project-name" required maxlength="100" placeholder="例如：GBA Emulator"><label for="project-brief">想做什么，已经确定了什么？</label><textarea id="project-brief" maxlength="12000" placeholder="描述产品方向、目前进度和想解决的问题。暂时不知道的可以留空。"></textarea><div class="help">新建项目不会自动启动分析。已有资料可以稍后导入。</div><button class="primary" type="submit">创建项目</button></form>`,
  );
  $("#new-form").onsubmit = async (e) => {
    e.preventDefault();
    const b = e.submitter;
    b.disabled = true;
    try {
      const p = await api("/api/projects", {
        name: $("#project-name").value,
        brief: $("#project-brief").value,
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
function prepareTask(key) {
  const t = state.packs.flatMap((p) => p.tasks).find((t) => t.key === key);
  modal(
    "准备任务",
    `<div class="eyebrow">${E(t.output)}</div><h2>${E(t.name)}</h2><p class="muted">${E(t.description)}</p><div class="chipline">${t.tools.map((id) => `<span class="tag">${E(state.tools.find((t) => t.id === id)?.name || id)}</span>`).join("")}</div><form id="task-form"><label for="instruction">这次的具体要求</label><textarea id="instruction" maxlength="12000" placeholder="希望解决的问题、重点、范围、交付深度…"></textarea><label>指定重点资料（可选，最多 8 份）</label><div class="checks">${
      state.documents
        .filter((d) => ["upload", "accepted"].includes(d.kind))
        .map(
          (d) =>
            `<label><input type="checkbox" name="docs" value="${E(d.id)}">${E(d.name)}</label>`,
        )
        .join("") ||
      "<small>没有可指定的资料；可以先导入，也可以先准备任务。</small>"
    }</div><div class="help">模板：${E(t.template)}<br>项目背景自动带入；检索补充相关资料。指定资料每份最多带入 12000 字，截断会在任务包中标出。</div><button class="primary" type="submit">生成任务包</button></form>`,
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
function renderMarkdown(text) {
  // Escape before formatting. Raw HTML and embedded media are never executed.
  const inline = (s) =>
    E(s)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  const lines = text.split("\n");
  let out = "",
    code = false,
    table = [];
  const flush = () => {
    if (!table.length) return;
    out +=
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
    table = [];
  };
  for (const line of lines) {
    if (line.startsWith("```")) {
      flush();
      out += code ? "</code></pre>" : "<pre><code>";
      code = !code;
      continue;
    }
    if (code) {
      out += E(line) + "\n";
      continue;
    }
    if (line.trim().startsWith("|")) {
      table.push(line);
      continue;
    }
    flush();
    const heading = line.match(/^(#{1,6}) (.*)/);
    if (heading)
      out += `<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`;
    else if (line.startsWith("> "))
      out += "<blockquote>" + inline(line.slice(2)) + "</blockquote>";
    else if (line.trim()) out += "<p>" + inline(line) + "</p>";
  }
  flush();
  if (code) out += "</code></pre>";
  return out;
}
function showJob(job) {
  activeJob = job.id;
  const running = ["running", "queued"].includes(job.status),
    review = job.review;
  modal(
    "任务记录",
    `<div class="split"><h2>${E(job.title)}</h2>${badge(job.status)}</div><p class="muted">${date(job.created)} · ${job.sources.length} 段资料已快照保存</p>${job.error ? `<div class="banner">${E(job.error)}</div>` : ""}${job.status === "prepared" ? `<div class="help">执行将把任务包中的项目背景和引用资料发送给 Codex 模型服务，使用你的账号额度。先检查下方输入依据；生成后仍需评审。</div><div class="actions"><button class="primary" data-run="${E(job.id)}" ${state.runtime.available ? "" : "disabled"}>开始生成</button><a href="/api/jobs/${E(job.id)}/prompt">下载任务包</a><button data-import="${E(job.id)}">导入已有结果</button><button data-cancel="${E(job.id)}">取消</button></div>` : ""}${running ? `<div class="progress-note"><span class="spinner"></span>正在生成，状态会自动更新。完整分析可能需要几分钟。</div><button data-cancel="${E(job.id)}">停止生成</button>` : ""}${job.output ? `<div class="actions"><a href="/api/jobs/${E(job.id)}/download">下载 Markdown</a><span class="tag">${review ? (review.decision === "accepted" ? "已确认 · 可用于后续任务" : "需要修改") : "尚未评审"}</span></div><div class="document document-render">${renderMarkdown(job.output)}</div><div class="help">评审重点：核心场景是否齐全、关键结论是否有证据、异常与边界是否闭合。确认只作用于此项目，不会自动发布为全局知识。</div><label for="review-note">评审意见</label><textarea id="review-note" maxlength="12000" placeholder="需要修正的内容，或确认时附加的说明">${E(review?.note || "")}</textarea><div class="actions"><button class="primary" data-review="accepted" data-id="${E(job.id)}">确认这份交付物</button><button data-review="changes_requested" data-id="${E(job.id)}">记录修改意见</button></div>` : ""}<details><summary>本次输入：项目背景、完整模板与任务要求</summary><pre class="document">${E(job.prompt)}</pre></details><details><summary>查看 ${job.sources.length} 段引用资料</summary>${job.sources.map((s) => `<div class="card"><h3>[${E(s.citation)}] ${E(s.name)}</h3><small>${E(kinds[s.kind])} · 片段 ${s.chunk}${s.truncated ? " · 超出 12000 字，已截断" : ""}</small><div class="excerpt">${E(s.text)}</div></div>`).join("") || "<p>没有检索到匹配材料。</p>"}</details>`,
  );
  if (review?.decision === "changes_requested") {
    const button = document.createElement("button");
    button.textContent = "按意见准备修订版";
    button.dataset.revise = job.id;
    $("#modal-body .actions").append(button);
  }
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
    else if (b.dataset.job) showJob(await api("/api/jobs/" + b.dataset.job));
    else if (b.dataset.revise) {
      b.disabled = true;
      const job = await api("/api/jobs/" + b.dataset.revise + "/revise", {});
      await refresh();
      showJob(job);
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
