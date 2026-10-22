"use strict";

/* workspace.js: project shell, workflow page, documents list and settings.
   Loaded by index.html before the app bootstrap. */

const projectTabs = [
  ["workflow", "工作流"],
  ["materials", "资料"],
  ["outputs", "文档"],
  ["settings", "设置"],
];
// Old tab ids still used by feature modules map onto the new four-tab layout.
const tabAliases = { overview: "workflow", tasks: "workflow", context: "settings", versions: "settings", conditions: "settings" };
const settingsSectionFor = { context: "context", versions: "versions", conditions: "conditions" };
let settingsSection = "context";

function normalizeTab() {
  if (settingsSectionFor[tab]) settingsSection = settingsSectionFor[tab];
  if (tabAliases[tab]) tab = tabAliases[tab];
}

function draw() {
  normalizeTab();
  $("#projects").innerHTML =
    state.projects
      .map(
        (p) =>
          `<button data-project="${E(p.id)}" class="${p.id === projectId && !["capabilities", "trash"].includes(tab) ? "selected" : ""}" title="${E(p.name)}">${E(p.name)}</button>`,
      )
      .join("") || "<small>还没有项目</small>";
  $("#capabilities").classList.toggle("selected", tab === "capabilities");
  $("#trash").classList.toggle("selected", tab === "trash");
  if (tab === "capabilities") return drawCapabilities();
  if (tab === "trash") return drawTrash();
  if (!state.project) {
    $("#content").innerHTML =
      `<div class="empty"><h2>创建第一个项目</h2><p>一个项目对应一个产品。先写下背景，再导入竞品资料，按工作流逐步生成文档。</p><button class="primary" data-action="new">新建项目</button><p class="help">已连接 ${Number(state.runtime.knowledge_count || 0)} 份方法与模板</p></div>`;
    return;
  }
  const counts = {
    materials: (state.documents || []).filter((d) => d.kind === "upload").length,
    outputs: (state.jobs || []).filter((j) => !j.archived).length,
  };
  const platform = state.project.platform ? platformLabels[state.project.platform] || state.project.platform : "";
  $("#content").innerHTML =
    `<div class="project-header"><div class="project-header-row"><div class="project-title"><h1>${E(state.project.name)}</h1>${platform ? `<span class="tag">${E(platform)}</span>` : ""}<span class="tag">${E(workflowNames[state.project.workflow_mode] || state.project.workflow_mode)}</span></div><div class="project-tools">${activeVersionSelect()}<button class="primary" data-tab="workflow">开始任务</button></div></div><nav class="tabs" aria-label="工作区" role="tablist">${projectTabs.map(([id, label]) => `<button role="tab" aria-selected="${tab === id}" data-tab="${id}" class="${tab === id ? "active" : ""}">${label}${counts[id] ? ` <span class="tab-count">${counts[id]}</span>` : ""}</button>`).join("")}</nav></div><div id="view" role="tabpanel"></div>`;
  (({ workflow: drawTasks, materials: drawMaterials, outputs: drawOutputs, settings: drawSettings })[tab] || drawTasks)();
}

/* ---------- Status helpers ---------- */

function jobState(job) {
  if (!job) return { label: "未开始", cls: "", icon: "" };
  if (job.review_decision === "accepted") return { label: "已确认", cls: "ok", icon: "done" };
  if (job.review_decision === "changes_requested") return { label: "需修改", cls: "warn", icon: "review" };
  return {
    prepared: { label: "待执行", cls: "", icon: "ready" },
    queued: { label: "排队中", cls: "run", icon: "run" },
    running: { label: "生成中", cls: "run", icon: "run" },
    completed: { label: "待评审", cls: "warn", icon: "review" },
    failed: { label: "失败", cls: "bad", icon: "bad" },
    cancelled: { label: "已取消", cls: "", icon: "" },
    interrupted: { label: "已中断", cls: "bad", icon: "bad" },
  }[job.status] || { label: job.status, cls: "", icon: "" };
}

function stateTag(info) {
  return `<span class="tag ${info.cls}">${E(info.label)}</span>`;
}

function taskIcon(info) {
  return `<span class="task-icon ${info.icon}" aria-hidden="true">${info.icon === "done" ? "✓" : info.icon === "bad" ? "!" : ""}</span>`;
}

function allTaskDefs() {
  return state.packs.filter((pack) => pack.enabled).flatMap((pack) => pack.tasks)
    .filter((task) => !task.modes || task.modes.includes(state.project.workflow_mode));
}

function jobRows(jobs) {
  return (
    jobs
      .map((j) => {
        const info = jobState(j);
        return `<div class="row ${j.archived ? "archived-row" : ""}"><div class="row-main"><h3>${E(j.title)}${j.revision_number > 1 ? ` · 修订 V${j.revision_number}` : ""}</h3><p>${date(j.created)} · ${E(scopeLabel(j))}${j.is_latest ? "" : " · 已有后续修订"}${j.error ? ` · ${E(j.error)}` : ""}</p></div>${stateTag(info)}<button class="small" aria-label="查看 ${E(j.title)}" data-job="${E(j.id)}">打开</button></div>`;
      })
      .join("") ||
    '<div class="empty compact">暂时没有记录。</div>'
  );
}

function filteredJobs() {
  const jobs = state.jobs || [];
  if (outputFilter === "all") return jobs.filter((j) => !j.archived);
  if (outputFilter === "archived") return jobs.filter((j) => j.archived);
  if (outputFilter === "latest") return jobs.filter((j) => !j.archived && j.is_latest);
  if (outputFilter === "attention")
    return jobs.filter((j) => !j.archived && (["failed", "interrupted"].includes(j.status) || j.review_decision === "changes_requested" || (j.status === "completed" && !j.review_decision)));
  if (outputFilter === "accepted") return jobs.filter((j) => !j.archived && j.review_decision === "accepted");
  return jobs.filter((j) => !j.archived && j.status === outputFilter);
}

/* ---------- Workflow (default project page) ---------- */

function defaultWorkflowId(workflows) {
  const stored = localStorage.getItem(`workbench-workflow:${projectId}`);
  if (workflows.some((item) => item.id === stored)) return stored;
  return workflows[0]?.id || null;
}

function workflowTaskRow(task, taskKey, opts = {}) {
  const job = scopedTaskJobs(taskKey)[0];
  const info = job ? jobState(job) : opts.blocked ? { label: "等待前置", cls: "", icon: "" } : { label: "可开始", cls: "", icon: "ready" };
  const prepareLabel = job ? (job.review_decision === "accepted" ? "生成新版" : "重新准备") : "准备";
  const actions = job
    ? `<button class="small" data-job="${E(job.id)}">打开</button>${job.review_decision === "accepted" || ["failed", "cancelled"].includes(job.status) ? `<button class="small ghost" data-task="${E(taskKey)}">${prepareLabel}</button>` : ""}`
    : `<button class="small ${opts.blocked ? "" : "primary"}" data-task="${E(taskKey)}" ${opts.blocked || !task ? "disabled" : ""}>准备</button>`;
  return `<div class="task-row ${opts.sub ? "sub" : ""}">${taskIcon(info)}<div class="row-main"><h3>${E(opts.name || task?.name || taskKey)}${opts.optional ? ' <span class="tag">按需</span>' : ""}</h3>${opts.description ? `<p title="${E(opts.description)}">${E(opts.description)}</p>` : ""}</div><span class="task-state">${stateTag(info)}</span><div class="task-actions">${actions}</div></div>`;
}

function drawTasks() {
  const allTasks = allTaskDefs();
  const workflows = state.workflows || [];
  if (!workflows.some((item) => item.id === activeWorkflow)) activeWorkflow = defaultWorkflowId(workflows);
  const workflow = workflows.find((item) => item.id === activeWorkflow);
  const mismatch = state.mode_mismatch_count ? `<div class="banner">有 ${state.mode_mismatch_count} 个历史任务由另一工作流模式生成，下方只列出当前模式可新建的任务。</div>` : "";
  const standalone = allTasks.filter((task) => !task.hidden);
  const standaloneMarkup = `<details class="standalone-tasks"><summary>单项任务（不按工作流，直接生成某一份文档）</summary><div class="standalone-grid">${standalone.map((task) => `<article class="card"><h3>${E(task.name)}</h3><p>${E(task.description)}</p><footer><button class="small" data-task="${E(task.key)}">准备</button></footer></article>`).join("")}</div></details>`;
  const switcher = workflows.length > 1 ? `<label class="workflow-switch inline-filter" for="workflow-select">工作流<select id="workflow-select">${workflows.map((item) => `<option value="${E(item.id)}" ${item.id === activeWorkflow ? "selected" : ""}>${E(item.name)}</option>`).join("")}</select></label>` : "";
  if (!workflow) {
    $("#view").innerHTML = `${mismatch}<div class="empty compact">当前模式没有预设工作流，请直接选择单项任务。</div>${standaloneMarkup}${statusStrip()}`;
    return;
  }
  const stages = workflow.stages || [];
  const stepsForStage = (stageId) => workflow.steps.filter((step) => step.stage === stageId);
  const stageDone = (stageId) => {
    const required = stepsForStage(stageId).filter((step) => !step.optional);
    return required.length > 0 && required.every((step) => taskIsCurrentConfirmed(step.task));
  };
  if (stages.length && !stages.some((stage) => stage.id === activeWorkflowStage)) {
    activeWorkflowStage = (stages.find((stage) => !stageDone(stage.id)) || stages[0]).id;
  }
  const selectedStage = stages.find((stage) => stage.id === activeWorkflowStage);
  const visibleSteps = selectedStage ? stepsForStage(selectedStage.id) : workflow.steps;
  const stepper = stages.length ? `<nav class="stepper" aria-label="工作阶段">${stages.map((stage, index) => {
    const steps = stepsForStage(stage.id);
    const confirmed = steps.filter((step) => taskIsCurrentConfirmed(step.task)).length;
    const done = stageDone(stage.id);
    return `<button class="${stage.id === activeWorkflowStage ? "selected" : ""} ${done ? "done" : ""}" data-workflow-stage="${E(stage.id)}" aria-current="${stage.id === activeWorkflowStage ? "step" : "false"}"><span class="step-num">${done ? "✓" : index + 1}</span><span class="step-text"><strong>${E(stage.name)}</strong><small>${confirmed}/${steps.length} 已确认</small></span></button>`;
  }).join("")}</nav>${selectedStage?.description ? `<p class="stage-intro">${E(selectedStage.description)}</p>` : ""}` : "";
  const rows = visibleSteps.map((step) => {
    const task = allTasks.find((item) => item.key === step.task);
    if (task?.assembly === "accepted_sections" && task.section_tasks?.length) {
      const chapterJobs = task.section_tasks.map((key) => scopedTaskJobs(key)[0]);
      const acceptedCount = chapterJobs.filter((job) => job?.review_decision === "accepted").length;
      const allAccepted = acceptedCount === task.section_tasks.length;
      const finalJob = scopedTaskJobs(step.task)[0];
      const latestChapterTime = Math.max(0, ...chapterJobs.map((job) => Date.parse(job?.review_created || job?.updated || job?.created || 0) || 0));
      const stale = Boolean(finalJob && latestChapterTime > (Date.parse(finalJob.created || 0) || 0));
      const done = taskIsCurrentConfirmed(step.task);
      const headInfo = done ? { label: "已确认", cls: "ok", icon: "done" } : stale ? { label: "需重新合并", cls: "warn", icon: "review" } : finalJob ? jobState(finalJob) : { label: `${acceptedCount}/${task.section_tasks.length} 章已确认`, cls: "", icon: acceptedCount ? "ready" : "" };
      const headActions = `${finalJob ? `<button class="small" data-job="${E(finalJob.id)}">打开完整版</button>` : ""}${allAccepted && (!done || stale) ? `<button class="small primary" data-f1-assemble="${E(step.task)}">${finalJob ? "重新合并" : "合并五章"}</button>` : ""}`;
      const head = `<div class="task-row group-head">${taskIcon(headInfo)}<div class="row-main"><h3>${E(step.name || task.name)}</h3><p>分 5 章逐章生成和确认；合并只统一编号和顺序，不调用模型重写。</p></div><span class="task-state">${stateTag(headInfo)}</span><div class="task-actions">${headActions}</div></div>`;
      const chapters = task.section_tasks.map((key) => {
        const chapter = allTasks.find((item) => item.key === key);
        const ready = (chapter?.required_upstream_all || []).every((upstream) => scopedTaskJobs(upstream)[0]?.review_decision === "accepted");
        return workflowTaskRow(chapter, key, { sub: true, blocked: !ready, description: chapter?.description });
      }).join("");
      return head + chapters;
    }
    return workflowTaskRow(task, step.task, { name: step.name, description: step.description, optional: step.optional });
  }).join("");
  $("#view").innerHTML = `${mismatch}<div class="workflow-head"><div><h2>${E(workflow.name)}</h2><p>${E(workflow.prompt || workflow.description || "")}</p></div>${switcher}</div>${stepper}<div class="task-list">${rows || '<div class="empty compact">这个阶段没有任务。</div>'}</div>${standaloneMarkup}${statusStrip()}`;
  const select = $("#workflow-select");
  if (select) select.onchange = () => {
    activeWorkflow = select.value;
    activeWorkflowStage = null;
    localStorage.setItem(`workbench-workflow:${projectId}`, activeWorkflow);
    drawTasks();
  };
}

function statusStrip() {
  const docs = state.documents || [], jobs = (state.jobs || []).filter((j) => !j.archived);
  const pendingScrapes = (state.scrapes || []).filter((item) => item.status === "ready").length;
  const runningScrapes = (state.scrapes || []).filter((item) => ["queued", "running"].includes(item.status)).length;
  const running = jobs.filter((j) => ["queued", "running"].includes(j.status)).length;
  const toReview = jobs.filter((j) => j.status === "completed" && !j.review_decision).length;
  const items = [
    `<span><b>${docs.filter((d) => d.kind === "upload").length}</b>份资料</span>`,
    `<span><b>${docs.filter((d) => d.kind === "accepted").length}</b>份已确认文档</span>`,
    toReview ? `<button data-tab="outputs" data-output-filter="attention"><b>${toReview}</b>份待评审</button>` : "",
    running ? `<span><b>${running}</b>个生成中</span>` : "",
    pendingScrapes ? `<button data-tab="materials"><b>${pendingScrapes}</b>份采集待确认入库</button>` : "",
    runningScrapes ? `<span><b>${runningScrapes}</b>个采集进行中</span>` : "",
  ].filter(Boolean);
  const working = state.context?.working ? `<span title="${E(state.context.working)}">当前工作：${E(state.context.working.split("\n")[0].slice(0, 60))}</span>` : `<button data-tab="settings">补充当前工作背景 →</button>`;
  return `<div class="status-strip">${items.join("")}${working}</div>`;
}

/* ---------- Materials ---------- */

function drawMaterials() {
  return drawCompetitorDossiers();
}

function drawCommonProjectMaterials(target = "#project-public-materials") {
  const documents = dossierCommonDocuments();
  const selection = dossierSession().publicSelected;
  const scraper = state.integrations?.review_scraper || {};
  const scopeVersionId = currentVersion()?.id || "";
  const scrapes = (state.scrapes || []).filter((item) => (item.version_id || "") === scopeVersionId);
  const visibleScrapes = scrapes.slice(0, 12);
  const readyScrapeIds = visibleScrapes.filter((item) => item.collection_type === "competitor" && item.status === "ready").map((item) => item.id);
  const scrapeRows = visibleScrapes.map((item) => {
    let request = {};
    try { request = JSON.parse(item.request || "{}"); } catch (_) { request = {}; }
    const platform = item.platform === "app_store" ? "App Store" : "Google Play";
    const title = item.listing_title ? `${item.listing_title} · ${platform}` : `${platform} · ${item.app_id}`;
    const statusClass = ["failed", "cancelled"].includes(item.status) ? "bad" : ["queued", "running"].includes(item.status) ? "run" : ["ready", "empty"].includes(item.status) ? "warn" : "";
    const facts = [
      item.version_name ? `产品版本：${item.version_name}` : "产品级",
      (request.countries || []).join(", "),
      date(item.created),
      item.review_count ? `${item.review_count} 条评论` : "",
      item.translation_requested ? `${item.translated_count || 0} 条中文译文` : "",
      item.screenshot_count ? `${item.screenshot_count} 张截图` : "",
      item.has_short_description ? "有短描述" : "",
      item.has_long_description ? "有长描述" : "",
      reviewFilterSummary(request),
      item.filter_stats?.active ? `筛选 ${item.filter_stats.fetched || 0} → ${item.filter_stats.kept || 0}` : "",
    ].filter(Boolean).join(" · ");
    return `<div class="row"><div class="row-main"><h3>${E(title)}</h3><p>${E(facts)}</p>${item.error ? `<small class="scrape-error">${E(item.error)}</small>` : ""}</div><span class="tag ${statusClass}">${E(scrapeStatusNames[item.status] || item.status)}</span>${item.collection_type === "competitor" && ["ready", "completed"].includes(item.status) ? `<button class="small" data-preview-scrape="${E(item.id)}">预览资料</button>` : ""}${item.status === "ready" ? `<button class="primary small" data-confirm-scrape="${E(item.id)}">确认入库</button>` : ""}${item.result_doc_id ? `<button class="small" data-document="${E(item.result_doc_id)}">查看主资料</button>` : ""}${["failed", "empty", "cancelled"].includes(item.status) ? `<button class="small" data-retry-scrape="${E(item.id)}">重试</button>` : ""}${["queued", "running"].includes(item.status) ? `<button class="small" data-cancel-scrape="${E(item.id)}">取消</button>` : ""}</div>`;
  }).join("") || '<div class="empty compact">还没有竞品资料采集记录。</div>';
  const images = imageDocuments().filter((document) => documents.some((item) => item.id === document.id));
  const activeScrape = scrapes.some((item) => ["queued", "running"].includes(item.status));
  const categoryCounts = Object.fromEntries(materialCategories.map((item) => [item.id, 0]));
  documents.forEach((document) => {
    const category = categoryCounts[document.category] === undefined ? "other" : document.category;
    categoryCounts[category] += 1;
  });
  if (activeMaterialCategory !== "all" && !categoryCounts[activeMaterialCategory]) activeMaterialCategory = "all";
  const imageSubcategoryCounts = Object.fromEntries(imageSubcategories.map((item) => [item.id, 0]));
  images.forEach((document) => {
    const subcategory = imageSubcategoryCounts[document.subcategory] === undefined ? "other" : document.subcategory;
    imageSubcategoryCounts[subcategory] += 1;
  });
  if (activeImageSubcategory !== "all" && !imageSubcategoryCounts[activeImageSubcategory]) activeImageSubcategory = "all";
  const imageSubcategoryFilters = [
    `<button type="button" data-image-subcategory-filter="all" aria-pressed="${activeImageSubcategory === "all"}">全部图片 <span>${images.length}</span></button>`,
    ...imageSubcategories
      .filter((item) => imageSubcategoryCounts[item.id])
      .map((item) => `<button type="button" data-image-subcategory-filter="${item.id}" aria-pressed="${activeImageSubcategory === item.id}">${E(item.label)} <span>${imageSubcategoryCounts[item.id]}</span></button>`),
  ].join("");
  const categoryFilters = [
    `<button type="button" data-material-filter="all" aria-pressed="${activeMaterialCategory === "all"}">全部 <span>${documents.length}</span></button>`,
    ...materialCategories
      .filter((item) => categoryCounts[item.id])
      .map((item) => `<button type="button" data-material-filter="${item.id}" aria-pressed="${activeMaterialCategory === item.id}">${E(item.label)} <span>${categoryCounts[item.id]}</span></button>`),
  ].join("");
  const materialRow = (d) => {
    const isImage = images.some((image) => image.id === d.id);
    const category = categoryCounts[d.category] === undefined ? "other" : d.category;
    const subcategory = imageSubcategoryCounts[d.subcategory] === undefined ? "other" : d.subcategory;
    const attributes = `data-material-item data-material-category="${E(category)}" data-material-subcategory="${E(subcategory)}" data-material-name="${E(d.name)}"`;
    const ownershipCheck = `<label class="public-material-select"><input type="checkbox" data-dossier-public-select="${E(d.id)}" aria-label="选择 ${E(d.name)} 以归入竞品档案" ${selection.has(d.id) ? "checked" : ""} ${dossierDocumentReady(d) ? "" : "disabled"}><span>归档</span></label>`;
    if (isImage) {
      return `<article class="material-image-card" ${attributes}>${ownershipCheck}<button class="material-image-preview" data-document="${E(d.id)}" aria-label="查看 ${E(d.name)}"><img src="/api/assets/${encodeURIComponent(projectId)}/${encodeURIComponent(d.id)}" alt="${E(d.name)}" loading="lazy"></button><div class="material-image-info"><h4 title="${E(d.name)}">${E(d.name)}</h4><p>${date(d.created)}</p><div class="material-item-actions">${materialImageSubcategoryOptions(d)}<button class="small" data-document="${E(d.id)}">查看</button><button class="danger small" data-delete-image="${E(d.id)}">删除</button></div></div></article>`;
    }
    return `<article class="row material-library-item" ${attributes}>${ownershipCheck}<div class="row-main material-row"><div><h3>${E(d.name)}</h3><p>${E(kinds[d.kind])} · ${Number(d.characters || 0).toLocaleString()} 字符 · ${date(d.created)}</p></div></div><div class="material-item-actions">${materialCategoryOptions(d)}<button class="small" data-document="${E(d.id)}">读原文</button></div></article>`;
  };
  const materialGroups = materialCategories.map((category) => {
    const categoryDocuments = documents.filter((document) => (categoryCounts[document.category] === undefined ? "other" : document.category) === category.id);
    if (!categoryDocuments.length) return "";
    const items = categoryDocuments.map(materialRow).join("");
    const bodyClass = category.id === "images" ? "material-image-grid" : "materials-list card";
    const secondaryFilters = category.id === "images" ? `<div class="image-subcategory-filters" role="group" aria-label="图片分类">${imageSubcategoryFilters}</div>` : "";
    return `<section class="material-category-group" data-material-group="${category.id}"><div class="material-category-heading"><div><h3>${E(category.label)}</h3><p data-material-group-count>${categoryDocuments.length} 份资料</p></div></div>${secondaryFilters}<div class="${bodyClass}">${items}</div></section>`;
  }).join("");
  const commonMarkup =
    `<div class="section-title public-materials-heading"><div><h3>项目公共资料</h3><p class="muted">${documents.length} 份资料${images.length ? ` · ${images.length} 张图片` : ""} · 未指定竞品的研究、榜单和产品资料都在这里。</p></div><button class="small" data-dossier-public-attach ${selection.size ? "" : "disabled"}>归入竞品档案（${selection.size}）</button></div>
    <section class="material-intake public-material-intake" aria-labelledby="material-intake-title"><div class="section-title"><div><h4 id="material-intake-title">补充公共资料</h4><p class="muted">上传到当前${currentVersion() ? `版本：${E(currentVersion().name || "当前版本")}` : "产品级范围"}。属于某个竞品的资料，请打开它的档案再添加。</p></div></div><div id="material-paste-zone" class="paste-zone" tabindex="0" role="button" aria-label="粘贴、拖入或选择项目公共资料"><div class="paste-shortcut" aria-hidden="true"><kbd>Ctrl</kbd><span>＋</span><kbd>V</kbd></div><strong>截图后直接粘贴到这里</strong><p>可连续粘贴多张；也可拖入文件，或点击选择。</p><button id="pick-materials" class="small" type="button">选择文件</button><input class="visually-hidden" type="file" id="upload" multiple accept=".md,.txt,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp" aria-label="选择要导入的资料"><small>点击“一并上传”后才写入项目。单份最大 12 MB，一批最多 30 份。</small></div><div id="pending-materials" aria-live="polite"></div></section>
    <section id="material-library" class="material-library"><div class="material-library-toolbar"><label class="material-search"><span class="visually-hidden">搜索资料名称</span><input id="material-search" type="search" placeholder="搜索公共资料名称" value="${E(materialSearchQuery)}"></label><div class="material-filter-status" id="material-filter-status" aria-live="polite"></div></div><div class="material-category-filters" role="group" aria-label="资料分类">${categoryFilters}</div><div class="material-category-groups">${materialGroups}</div><div id="material-filter-empty" class="empty compact" hidden>没有符合条件的资料。可以换一个分类或清空搜索词。</div>${documents.length ? "" : '<div class="empty compact">还没有公共资料。可直接粘贴截图，或选择文件加入。</div>'}</section>`;
  const toolsMarkup = `<div class="material-tools public-material-tools"><details class="material-tool" ${activeScrape || readyScrapeIds.length ? "open" : ""}><summary><span><strong>竞品资料采集记录</strong><small>当前版本范围 · 最近 12 条 · 预览后确认入库</small></span><span class="details-hint" aria-hidden="true"></span></summary><div class="material-tool-body"><p class="help">${E(scraper.message || "正在检测桌面竞品评论工具")} · 采集完成后需确认才会进入分析输入；范围由你逐项勾选。</p>${readyScrapeIds.length ? `<div class="discovery-collection-actions"><button class="small" data-confirm-visible-scrapes="${E(readyScrapeIds.join(","))}">确认本页 ${readyScrapeIds.length} 份已就绪资料</button><small>先逐条预览；不会包含其他版本或本页未显示记录。</small></div>` : ""}<div class="scrape-list">${scrapeRows}</div></div></details>
    <details class="material-tool android-capture-history"><summary><span><strong>实机走查记录</strong><small>当前版本范围 · 查看进度、接管续跑与模块拼图</small></span><span class="details-hint" aria-hidden="true"></span></summary><div class="material-tool-body"><div class="actions"><button class="small" data-android-capture-history-refresh>刷新走查记录</button></div><div id="android-capture-history" aria-live="polite"></div></div></details>
    <details class="material-tool"><summary><span><strong>查找资料依据</strong><small>在项目资料和知识库中查找可核对的原文片段</small></span><span class="details-hint" aria-hidden="true"></span></summary><div class="material-tool-body"><div class="searchbar"><input id="search-query" placeholder="例如：竞品差异、权限要求" aria-label="检索关键词"><button id="search">查找</button></div><p class="tool-note">只返回相关片段供你核对，不会自动改文档或把检索结果当成事实。</p><div id="search-results"></div></div></details></div>`;
  $(target).innerHTML = commonMarkup;
  $("#project-material-tools").innerHTML = toolsMarkup;
  $("#upload").onchange = upload;
  const pasteZone = $("#material-paste-zone");
  $("#pick-materials").onclick = () => $("#upload").click();
  pasteZone.onclick = (event) => {
    if (!event.target.closest("button")) $("#upload").click();
  };
  pasteZone.onkeydown = (event) => {
    if (["Enter", " "].includes(event.key)) {
      event.preventDefault();
      $("#upload").click();
    }
  };
  ["dragenter", "dragover"].forEach((name) => pasteZone.addEventListener(name, (event) => {
    event.preventDefault();
    pasteZone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => pasteZone.addEventListener(name, (event) => {
    event.preventDefault();
    pasteZone.classList.remove("dragging");
  }));
  pasteZone.addEventListener("drop", (event) => queueMaterialFiles(event.dataTransfer?.files));
  renderPendingMaterials();
  const materialSearch = $("#material-search");
  if (materialSearch) materialSearch.oninput = (event) => {
    materialSearchQuery = event.target.value;
    filterMaterialLibrary();
  };
  $("#material-library")?.querySelectorAll("[data-material-filter]").forEach((button) => {
    button.onclick = () => {
      activeMaterialCategory = button.dataset.materialFilter;
      if (activeMaterialCategory !== "images") activeImageSubcategory = "all";
      filterMaterialLibrary();
    };
  });
  $("#material-library")?.querySelectorAll("[data-image-subcategory-filter]").forEach((button) => {
    button.onclick = () => {
      activeMaterialCategory = "images";
      activeImageSubcategory = button.dataset.imageSubcategoryFilter;
      filterMaterialLibrary();
    };
  });
  $("#material-library")?.querySelectorAll("[data-document-category]").forEach((select) => {
    select.onchange = async () => {
      const previous = state.documents.find((document) => document.id === select.dataset.documentCategory)?.category || "other";
      select.disabled = true;
      try {
        await api(`/api/documents/${encodeURIComponent(select.dataset.documentCategory)}/category`, {
          project_id: projectId,
          category: select.value,
        });
        await refresh();
        toast("资料分类已更新");
      } catch (err) {
        select.value = previous;
        select.disabled = false;
        error(err);
      }
    };
  });
  $("#material-library")?.querySelectorAll("[data-document-subcategory]").forEach((select) => {
    select.onchange = async () => {
      const previous = state.documents.find((document) => document.id === select.dataset.documentSubcategory)?.subcategory || "other";
      select.disabled = true;
      try {
        await api(`/api/documents/${encodeURIComponent(select.dataset.documentSubcategory)}/subcategory`, {
          project_id: projectId,
          subcategory: select.value,
        });
        await refresh();
        toast("图片分类已更新");
      } catch (err) {
        select.value = previous;
        select.disabled = false;
        error(err);
      }
    };
  });
  filterMaterialLibrary();
  androidCaptureRenderHistory();
  $("#search").onclick = search;
  $("#search-query").onkeydown = (e) => {
    if (e.key === "Enter") search();
  };
}

/* ---------- Documents ---------- */

const outputFilters = [
  ["latest", "最新版"],
  ["attention", "需处理"],
  ["accepted", "已确认"],
  ["all", "全部"],
  ["archived", "已归档"],
];

function drawOutputs() {
  const jobs = filteredJobs();
  const count = (id) => { const keep = outputFilter; outputFilter = id; const n = filteredJobs().length; outputFilter = keep; return n; };
  const rows = jobs.map((j) => {
    const info = jobState(j);
    return `<tr data-job-row="${E(j.id)}" class="${j.archived ? "archived-row" : ""}"><td><span class="doc-name">${E(j.title)}${j.revision_number > 1 ? ` · 修订 V${j.revision_number}` : ""}</span><span class="doc-sub">${E(scopeLabel(j))}${j.is_latest ? "" : " · 已有后续修订"}${j.error ? ` · ${E(j.error)}` : ""}</span></td><td>${stateTag(info)}</td><td class="num">${E(workflowNames[j.workflow_mode] || j.workflow_mode)}</td><td class="num">${date(j.created)}</td><td><button class="small" data-job="${E(j.id)}">打开</button></td></tr>`;
  }).join("");
  $("#view").innerHTML = `<div class="doc-toolbar"><div class="segmented" role="group" aria-label="筛选">${outputFilters.map(([id, label]) => `<button class="${outputFilter === id ? "active" : ""}" data-output-filter="${id}">${label} <span>${count(id)}</span></button>`).join("")}</div></div>${rows ? `<table class="doc-table"><thead><tr><th>文档</th><th class="col-state">状态</th><th class="col-mode">模式</th><th class="col-date">创建时间</th><th class="col-open"></th></tr></thead><tbody>${rows}</tbody></table>` : '<div class="list"><div class="empty compact">这个筛选下没有文档。</div></div>'}`;
  $("#view").querySelectorAll("[data-job-row]").forEach((tr) => {
    tr.onclick = async (event) => {
      if (event.target.closest("button")) return;
      try { showJob(await api("/api/jobs/" + tr.dataset.jobRow)); } catch (err) { error(err); }
    };
  });
}

/* ---------- Settings: context / versions / conditions / danger zone ---------- */

function drawSettings() {
  const sections = [["context", "项目背景"], ["versions", "产品版本"]];
  if (state.project.workflow_mode === "full") sections.push(["conditions", "条件闭环"]);
  if (!sections.some(([id]) => id === settingsSection)) settingsSection = "context";
  $("#view").innerHTML = `<div class="settings-layout"><nav class="settings-nav" aria-label="设置">${sections.map(([id, label]) => `<button class="${settingsSection === id ? "active" : ""}" data-settings-section="${id}">${label}</button>`).join("")}</nav><div id="settings-body" class="settings-section"></div></div>`;
  ({ context: drawContext, versions: drawVersions, conditions: drawConditions })[settingsSection]();
}

function drawContext() {
  $("#settings-body").innerHTML =
    `<h2>项目背景</h2><p class="muted">每次准备任务时自动带入。执行过的任务保留当时的快照，修改这里不会改写历史文档。</p>${state.mode_mismatch_count ? `<div class="banner">有 ${state.mode_mismatch_count} 个历史任务使用了与当前项目不同的工作流模式；它们保留生成时的模式。</div>` : ""}<form id="context-form"><div class="context-card"><label for="foundation">长期背景</label><textarea id="foundation" maxlength="12000" placeholder="目标用户：\n地区：\n技术约束：\n长期决策：">${E(state.context.foundation)}</textarea><small>目标用户、地区、技术约束和长期决策；不知道的可以留空。</small></div><div class="context-card"><label for="working">当前工作</label><textarea id="working" maxlength="12000" placeholder="当前目标：\n已确认决策：\n待解决问题：\n本轮不做：">${E(state.context.working)}</textarea><small>迭代变化时更新，工作流页底部会显示第一行。</small></div><label for="brief">项目简介</label><textarea id="brief" maxlength="12000">${E(state.project.brief)}</textarea><div class="field-grid"><div><label for="workflow-mode">工作流模式</label><select id="workflow-mode"><option value="fast" ${state.project.workflow_mode === "fast" ? "selected" : ""}>快速迭代（默认）</option><option value="full" ${state.project.workflow_mode === "full" ? "selected" : ""}>完整研究</option></select></div><div><label for="platform">目标平台</label><select id="platform">${platformSelect(state.project.platform)}</select></div></div><p id="mode-help" class="help">切换模式只影响之后新准备的任务。</p><div class="form-footer"><a class="button-link" href="/api/projects/${encodeURIComponent(projectId)}/export">导出完整项目包</a><button class="primary" type="submit">保存</button></div></form><section class="danger-zone"><div><h2>删除项目</h2><p>移入回收站，之后可以恢复。</p></div><button class="danger" data-action="delete-project">删除项目</button></section>`;
  const form = $("#context-form");
  const snapshot = () => ["foundation", "working", "brief", "workflow-mode", "platform"].map((id) => $("#" + id).value).join("\u0000");
  const saved = snapshot();
  form.dataset.dirtyGuard = "true";
  form.isDirty = () => snapshot() !== saved;
  $("#workflow-mode").onchange = () => {
    $("#mode-help").textContent = `保存后只影响新任务；已有 ${state.jobs.length} 个历史任务保留各自的生成模式。`;
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
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
      });
      await refresh();
      toast("项目背景已保存");
    } catch (err) {
      error(err);
      e.submitter.disabled = false;
    }
  };
}

function drawConditions() {
  const items = state.conditions || [];
  $("#settings-body").innerHTML =
    `<div class="section-title flush"><div><h2>条件闭环</h2><p class="muted">每项条件需要 Owner、截止时间、阻塞范围和关闭证据。</p></div><button class="primary small" data-action="new-condition">＋ 新增条件</button></div><div class="list">${items
      .map(
        (c) =>
          `<div class="row"><div class="row-main"><h3>${E(c.title)}</h3><p>${E(c.owner)} · 截止 ${E(c.due)} · 复核 ${E(c.review_date || c.due)} · ${E(blockNames[c.block_level])}</p></div><span class="tag ${["open", "in_progress", "waiting_evidence"].includes(c.status) ? "warn" : "ok"}">${E(conditionNames[c.status])}</span>${c.evidence ? '<span class="tag">有证据</span>' : ""}<button class="small" data-condition="${E(c.id)}">更新</button></div>`,
      )
      .join("") || '<div class="empty compact">暂时没有条件。F3 输出中的硬阻塞应在这里登记。</div>'}</div><p class="help">只有已关闭或已豁免的条件才算完成；条件会自动进入之后生成的任务包。</p>`;
}

/* ---------- Global pages ---------- */

function drawTrash() {
  $("#content").innerHTML =
    `<div class="page-header"><div><h1>回收站</h1><p>删除的项目在本机保留完整快照，恢复不会覆盖现有项目。</p></div><button data-tab="workflow">返回项目</button></div><div class="list">${(state.trash || []).map((item) => `<div class="row"><div class="row-main"><h3>${E(item.name)}</h3><p>${item.deleted_at ? date(item.deleted_at) : "时间未知"} · ${item.document_count} 份资料 · ${item.job_count} 个任务${item.restored ? " · 已恢复，备份仍保留" : ""}</p></div><div class="actions">${item.restored ? "" : `<button class="primary small" data-trash-restore="${E(item.id)}">恢复</button>`}<button class="danger small" data-trash-delete="${E(item.id)}" data-trash-name="${E(item.name)}">永久删除</button></div></div>`).join("") || '<div class="empty compact">回收站是空的。</div>'}</div>`;
}

function drawCapabilities() {
  const globalStats = state.runtime.global || {},
    projectStats = state.runtime.project || {},
    lanhu = state.integrations?.lanhu || {};
  $("#content").innerHTML =
    `<div class="page-header"><div><h1>能力与工具</h1><p>启用能力后，项目里会出现对应任务。</p></div><button data-tab="workflow">返回项目</button></div><div class="pack-grid">${state.packs.map((p) => `<div class="card"><div class="pack-title"><h2>${E(p.name)}</h2><span class="tag ${p.enabled ? "ok" : ""}">${p.enabled ? "已启用" : "未启用"}</span></div><p class="muted">${E(p.description)}</p><div class="chipline">${p.tasks.filter((t) => !t.hidden || t.assembly).map((t) => `<span class="tag">${E(t.name)}</span>`).join("")}</div><button class="small" data-pack="${E(p.id)}" data-enabled="${!p.enabled}">${p.enabled ? "停用" : "启用"}</button></div>`).join("")}</div><div class="section-title"><h2>工具接入</h2></div><div class="list">${state.tools.map((t) => `<div class="row"><div class="row-main"><h3>${E(t.name)}</h3><p>${E(t.description)}</p></div><span class="tag ${t.id === "codex" ? (state.runtime.available ? "ok" : "bad") : t.status === "ready" ? "ok" : "warn"}">${t.id === "codex" ? (state.runtime.available ? "已找到 CLI" : "未找到 CLI") : t.status === "ready" ? "已接入" : "手动导入"}</span></div>`).join("")}<div class="row"><div class="row-main"><h3>蓝湖原型读取（Lanhu MCP）</h3><p>${E(lanhu.message || "尚未检测")} · 配置来源：${E(lanhu.source || "本机 Codex 配置")}</p></div><span class="tag ${lanhu.ready ? "ok" : "warn"}">${lanhu.ready ? "可用" : "需要配置"}</span><button class="small" data-action="lanhu-config">配置</button></div></div><div class="section-title"><h2>运行环境</h2></div><div class="card"><dl class="kv"><dt>生成模型</dt><dd class="mono">${E(state.runtime.model)}</dd><dt>知识来源</dt><dd>${Number(state.runtime.knowledge_count || 0)} 份方法、模板与案例</dd><dt>检索方式</dt><dd>${E(state.runtime.retrieval)}</dd><dt>全局知识索引</dt><dd>${state.runtime.global_index ? `${globalStats.sources || 0} 个来源 / ${globalStats.chunks || 0} 个片段` : "未建立或不可用"}</dd><dt>项目索引</dt><dd>${state.runtime.project_index ? `${projectStats.sources || 0} 份资料 / ${projectStats.chunks || 0} 个片段` : "首次检索时建立"}</dd></dl>${state.runtime.fallback ? '<div class="banner">Hybrid 检索不可用，已自动回退关键词检索。</div>' : ""}</div>`;
  const connectionNote = document.createElement("p");
  connectionNote.className = state.runtime.codex_error ? "banner" : "help";
  connectionNote.textContent = state.runtime.codex_error ||
    "找到 CLI 只表示本机入口存在，不代表账号、模型和网络已通过真实生成测试。";
  $("#content").appendChild(connectionNote);
}
