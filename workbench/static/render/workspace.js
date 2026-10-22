"use strict";

/* workspace.js: loaded by index.html before the app bootstrap. */

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
    `<div class="heading"><div><div class="eyebrow">PROJECT WORKSPACE</div><h1>${E(state.project.name)}</h1><div class="chipline"><span class="tag">当前模式：${E(workflowNames[state.project.workflow_mode] || state.project.workflow_mode)}</span>${state.project.platform ? `<span class="tag">${E(platformLabels[state.project.platform] || state.project.platform)}</span>` : ""}</div><p>${E(state.project.brief || "先补充项目背景，让后续任务有依据。")}</p></div><div class="heading-tools"><div class="version-scope-card compact"><span>当前范围</span>${activeVersionSelect()}</div><div class="actions"><a class="button-link" href="/api/projects/${encodeURIComponent(projectId)}/export">导出完整项目</a><button class="primary" data-tab="tasks">开始一项任务 ↗</button></div></div></div><nav class="tabs" aria-label="工作区" role="tablist"><button role="tab" aria-selected="${tab === "overview"}" data-tab="overview" class="${tab === "overview" ? "active" : ""}">项目概览</button><button role="tab" aria-selected="${tab === "versions"}" data-tab="versions" class="${tab === "versions" ? "active" : ""}">产品版本</button><button role="tab" aria-selected="${tab === "context"}" data-tab="context" class="${tab === "context" ? "active" : ""}">项目背景</button>${state.project.workflow_mode === "full" ? `<button role="tab" aria-selected="${tab === "conditions"}" data-tab="conditions" class="${tab === "conditions" ? "active" : ""}">条件闭环</button>` : ""}<button role="tab" aria-selected="${tab === "materials"}" data-tab="materials" class="${tab === "materials" ? "active" : ""}">资料</button><button role="tab" aria-selected="${tab === "tasks"}" data-tab="tasks" class="${tab === "tasks" ? "active" : ""}">任务</button><button role="tab" aria-selected="${tab === "outputs"}" data-tab="outputs" class="${tab === "outputs" ? "active" : ""}">交付物</button></nav><div id="view" role="tabpanel"></div>`;
  if (tab === "conditions" && state.project.workflow_mode !== "full") tab = "overview";
  (
    ({
      overview: drawOverview,
      versions: drawVersions,
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
          `<div class="row ${j.archived ? "archived-row" : ""}"><div class="row-main"><h3>${E(j.title)}${j.revision_number > 1 ? ` · 修订 V${j.revision_number}` : ""}</h3><p>${date(j.created)} · ${E(workflowNames[j.workflow_mode] || j.workflow_mode)}${j.parent_job_id ? ` · 修订自上一任务 V${j.source_version || 1}` : ""} · ${E(j.error || "执行记录与引用资料可追溯")}</p><div class="chipline"><span class="tag">${E(scopeLabel(j))}</span>${j.is_latest ? '<span class="tag">当前分支最新版</span>' : '<span class="tag">已有后续修订</span>'}${j.archived ? '<span class="tag">已归档</span>' : ""}</div></div>${badge(j.review_decision === "accepted" ? "已确认" : j.review_decision === "changes_requested" ? "需修改" : j.status)}<button class="small" aria-label="查看 ${E(j.title)}，${E(workflowNames[j.workflow_mode] || j.workflow_mode)}，${date(j.created)}" data-job="${E(j.id)}">查看</button></div>`,
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
    `<div class="grid"><div class="card hero"><div class="eyebrow">这次，要完成什么？</div><h2>一次推进一项工作，<br>留下可以继续用的成果。</h2><p>${state.project.workflow_mode === "fast" ? "按当前阶段进入：市场竞品、原型与说明、初审修改、终审整理或需求评审。已有原型和文档可以直接接着做；规则、流程、PRD 和验收用例按本轮需要准备。" : "完整模式保留完整研究深度和条件管理。"}</p><button data-tab="tasks">选择工作流 →</button></div><div class="card"><h3>当前工作</h3><p>${E(state.context.working || "还没有记录当前目标。可以写下这周要解决的问题、已确定的方向和暂时不做的事。")}</p><button class="small" data-tab="context">维护项目上下文</button><div class="help">下游任务优先使用当前范围内最新已确认的交付物。已有新版待确认时，旧稿不会自动替它做决定。</div></div></div><div class="stats"><div class="stat"><b>${docs.filter((d) => d.kind === "upload").length}</b><span>已导入资料</span></div><div class="stat"><b>${jobs.filter((j) => !j.archived && (j.status === "completed" || j.review_decision === "accepted")).length}</b><span>已完成任务</span></div><div class="stat"><b>${docs.filter((d) => d.kind === "accepted").length}</b><span>已确认交付物</span></div></div><div class="section-title"><h2>最近的工作</h2><button class="small" data-tab="outputs">全部记录</button></div><div class="card">${jobRows(jobs.filter((j) => !j.archived).slice(0, 4))}</div>`;
}

function drawContext() {
  $("#view").innerHTML =
    `${state.mode_mismatch_count ? `<div class="banner">有 ${state.mode_mismatch_count} 个历史任务使用了与当前项目不同的工作流模式。历史任务不会被修改；任务记录会显示它生成时的模式。</div>` : ""}<form id="context-form"><div class="grid"><div class="card context-card"><div class="eyebrow">01 / 长期背景</div><h2>这个项目是什么</h2><p>目标用户、地区、技术约束和长期决策。</p><textarea id="foundation" maxlength="12000" aria-label="长期背景" placeholder="目标用户：\n地区：\n技术约束：\n长期决策：">${E(state.context.foundation)}</textarea><small>每次任务自动带入；不知道的内容可以暂留空。</small></div><div class="card context-card"><div class="eyebrow">02 / 当前工作</div><h2>现在推进到哪里</h2><p>当前目标、已确认决策、正在解决的问题。</p><textarea id="working" maxlength="12000" aria-label="当前工作" placeholder="当前目标：\n已确认决策：\n待解决问题：\n本轮不做：">${E(state.context.working)}</textarea><small>迭代变化时更新；执行过的任务仍保留当时快照。</small></div></div><div class="grid"><div><label for="workflow-mode">工作流模式</label><select id="workflow-mode"><option value="fast" ${state.project.workflow_mode === "fast" ? "selected" : ""}>快速迭代（默认）</option><option value="full" ${state.project.workflow_mode === "full" ? "selected" : ""}>完整研究</option></select></div><div><label for="platform">目标平台（可选）</label><select id="platform">${platformSelect(state.project.platform)}</select></div></div><label for="brief">项目简介</label><textarea id="brief" maxlength="12000">${E(state.project.brief)}</textarea><div id="mode-help" class="help">目标平台可选：Android、iOS 或双平台；不确定时可选择“未指定”。验证周期和团队资源不再作为项目输入项。切换模式只影响之后准备的新任务；历史任务继续保留生成时的模式和输入快照。</div><button class="primary" type="submit">保存项目背景</button></form><section class="danger-zone"><div><h2>删除项目</h2><p>项目将从工作台移入回收站，之后可以恢复。</p></div><button class="danger" data-action="delete-project">删除这个项目</button></section>`;
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

function drawTasks() {
  const allTasks = state.packs
    .filter((pack) => pack.enabled)
    .flatMap((pack) => pack.tasks)
    .filter((task) => !task.modes || task.modes.includes(state.project.workflow_mode));
  const tasks = allTasks.filter((task) => !task.hidden);
  const workflows = state.workflows || [];
  const workflow = workflows.find((item) => item.id === activeWorkflow);
  const active = currentVersion();
  const scope = `<div class="version-scope-card"><span>本次任务归属</span>${activeVersionSelect()}<button class="small" data-tab="versions">管理版本</button></div>`;
  const mismatch = state.mode_mismatch_count ? `<div class="banner">当前项目是“${E(workflowNames[state.project.workflow_mode])}”，历史任务可能由另一模式生成。下面只显示当前模式可新建的任务。</div>` : "";
  if (workflow) {
    const stages = workflow.stages || [];
    if (!stages.some((stage) => stage.id === activeWorkflowStage)) activeWorkflowStage = stages[0]?.id || null;
    const selectedStage = stages.find((stage) => stage.id === activeWorkflowStage);
    const visibleSteps = selectedStage ? workflow.steps.filter((step) => step.stage === selectedStage.id) : workflow.steps;
    const stageNavigation = stages.length ? `<nav class="workflow-stage-nav" aria-label="工作阶段">${stages.map((stage, index) => {
      const stageSteps = workflow.steps.filter((step) => step.stage === stage.id);
      const confirmed = stageSteps.filter((step) => taskIsCurrentConfirmed(step.task)).length;
      return `<button class="workflow-stage-tab ${stage.id === activeWorkflowStage ? "selected" : ""}" data-workflow-stage="${E(stage.id)}" aria-current="${stage.id === activeWorkflowStage ? "step" : "false"}"><span class="stage-number">${index + 1}</span><span><strong>${E(stage.name)}</strong><small>${confirmed ? `${confirmed} 项资料已确认` : "可直接进入"}</small></span></button>`;
    }).join("")}</nav><div class="workflow-stage-intro"><h3>${E(selectedStage?.name || "")}</h3><p>${E(selectedStage?.description || "")}</p></div>` : "";
    const steps = visibleSteps.map((step, index) => {
      const task = allTasks.find((item) => item.key === step.task);
      if (task?.assembly === "accepted_sections" && task.section_tasks?.length) {
        const scopedJobs = (taskKey) => scopedTaskJobs(taskKey);
        const chapterRows = task.section_tasks.map((taskKey, chapterIndex) => {
          const chapter = allTasks.find((item) => item.key === taskKey);
          const job = scopedJobs(taskKey)[0];
          const dependenciesReady = (chapter?.required_upstream_all || []).every((upstreamKey) => scopedJobs(upstreamKey)[0]?.review_decision === "accepted");
          const status = job?.review_decision === "accepted" ? "已确认" : job?.review_decision === "changes_requested" ? "需修改" : job?.status === "completed" ? "待评审" : job ? ({prepared: "待执行", queued: "排队中", running: "生成中", failed: "失败", cancelled: "已取消", interrupted: "已中断"}[job.status] || job.status) : dependenciesReady ? "可开始" : "等待前章";
          const actions = job
            ? `<button class="small" data-job="${E(job.id)}">查看</button>${job.review_decision === "accepted" ? `<button class="small" data-task="${E(taskKey)}">生成新版</button>` : ""}`
            : `<button class="primary small" data-task="${E(taskKey)}" ${dependenciesReady ? "" : "disabled"}>准备本章</button>`;
          return `<div class="f1-chapter ${job?.review_decision === "accepted" ? "accepted" : ""}"><div class="chapter-index">${chapterIndex + 1}</div><div class="row-main"><div class="chipline"><h4>${E(chapter?.name || taskKey)}</h4><span class="tag">${E(status)}</span></div><p>${E(chapter?.description || "")}</p></div><div class="chapter-actions">${actions}</div></div>`;
        }).join("");
        const chapterJobs = task.section_tasks.map((taskKey) => scopedJobs(taskKey)[0]);
        const allAccepted = chapterJobs.every((job) => job?.review_decision === "accepted");
        const finalJob = scopedJobs(step.task)[0];
        const latestChapterTime = Math.max(0, ...chapterJobs.map((job) => Date.parse(job?.review_created || job?.updated || job?.created || 0) || 0));
        const finalTime = Date.parse(finalJob?.created || 0) || 0;
        const stale = Boolean(finalJob && latestChapterTime > finalTime);
        const done = taskIsCurrentConfirmed(step.task);
        const finalStatus = done ? "完整 F1 已确认" : stale ? "章节已更新，需重新合并" : finalJob ? "完整 F1 待检查" : allAccepted ? "5 章已确认，可合并" : "按顺序完成各章";
        const finalActions = `${finalJob ? `<button class="small" data-job="${E(finalJob.id)}">查看完整 F1</button>` : ""}${allAccepted && (!done || stale) ? `<button class="primary small" data-f1-assemble="${E(step.task)}">${finalJob ? "重新合并" : "合并完整 F1"}</button>` : ""}`;
        return `<article class="workflow-step f1-workflow-group ${done ? "done" : ""}"><div class="step-index">${String(index + 1).padStart(2, "0")}</div><div class="row-main"><div class="chipline"><h3>${E(step.name)}</h3>${done ? '<span class="tag">当前范围已确认</span>' : ""}</div><p>分 5 章逐步生成、编辑和确认；后一章只使用已确认的前文。</p><div class="f1-chapter-list">${chapterRows}</div><div class="f1-assembly"><div><strong>${E(finalStatus)}</strong><small>合并只统一来源编号和章节顺序，不调用模型重写正文。</small></div><div class="actions">${finalActions}</div></div></div></article>`;
      }
      const done = taskIsCurrentConfirmed(step.task);
      const latest = scopedTaskJobs(step.task)[0];
      return `<article class="workflow-step ${done ? "done" : ""}"><div class="step-index">${String(index + 1).padStart(2, "0")}</div><div class="row-main"><div class="chipline"><h3>${E(step.name)}</h3>${step.optional ? '<span class="tag">按需</span>' : ""}${done ? '<span class="tag">当前资料已确认</span>' : ""}</div><p>${E(step.description)}</p></div><div class="workflow-step-actions">${latest ? `<button class="small" data-job="${E(latest.id)}">查看当前稿</button>` : ""}<button class="primary small" data-task="${E(step.task)}" ${task ? "" : "disabled"}>${latest ? "准备新版" : "准备任务"}</button></div></article>`;
    }).join("");
    $("#view").innerHTML = `${mismatch}${scope}<div class="section-title"><div><button class="small" data-workflow-back>← 返回全部工作流</button><h2>${E(workflow.name)}</h2><p class="muted">${E(workflow.prompt)}</p></div><span class="tag">${active ? E(active.name) : "产品级"}</span></div>${stageNavigation}<div class="workflow-steps">${steps}</div><div class="help">${stages.length ? "已有原型、PRD 或评审意见时，可直接选择对应阶段。资料确认用于后续任务引用，实际初审、终审和需求评审结论仍以评审人的决定为准。" : "按本轮目标选择任务；按需项可以跳过，已有资料可直接作为本轮输入。"}</div>`;
    return;
  }
  activeWorkflow = null;
  const workflowCards = workflows.map((item) => `<article class="card workflow-card"><div class="eyebrow">WORKFLOW</div><h3>${E(item.name)}</h3><p>${E(item.description)}</p><div class="workflow-preview">${(item.stages?.length ? item.stages : item.steps).map((step) => `<span>${E(step.name)}${step.optional && !step.name.includes("可选") ? "（可选）" : ""}</span>`).join("<b>→</b>")}</div><button class="primary" data-workflow="${E(item.id)}">进入工作流 →</button></article>`).join("");
  const taskCards = tasks.map((task) => `<article class="card task-card compact-task"><h3>${E(task.name)}</h3><p>${E(task.description)}</p><footer><span>中文 Markdown</span><button class="small" data-task="${E(task.key)}">单独准备</button></footer></article>`).join("");
  $("#view").innerHTML = `${mismatch}${scope}<div class="section-title"><div><h2>选择工作流</h2><p class="muted">按你现在要做的事进入；新品、版本、竞品和复盘互不强制串联。</p></div></div><div class="grid workflow-grid">${workflowCards || '<div class="empty">当前模式没有预设工作流，请直接选择单项任务。</div>'}</div><details class="standalone-tasks"><summary>也可以直接选择单项交付物</summary><div class="grid">${taskCards}</div></details><div class="help">先生成可检查的任务包；确认资料、模板和目标后再启动模型。产品版本是可选归类，不会阻止你直接开始。</div>`;
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

function drawCapabilities() {
  const globalStats = state.runtime.global || {},
    projectStats = state.runtime.project || {},
    lanhu = state.integrations?.lanhu || {};
  $("#content").innerHTML =
    `<div class="heading"><div><div class="eyebrow">CAPABILITY LIBRARY</div><h1>让工作台随工作生长。</h1><p>启用能力后，项目中会出现对应任务。任务、资料和交付物仍使用同一套工作方式。</p></div><button data-tab="overview">返回项目</button></div><div class="grid">${state.packs.map((p) => `<div class="card"><div class="pack-title"><h2>${E(p.name)}</h2><span class="tag">${p.enabled ? "已启用" : "可启用"}</span></div><p class="muted">${E(p.description)}</p><div class="chipline">${p.tasks.filter((t) => !t.hidden || t.assembly).map((t) => `<span class="tag">${E(t.name)}</span>`).join("")}</div><button data-pack="${E(p.id)}" data-enabled="${!p.enabled}">${p.enabled ? "停用此能力" : "启用此能力"}</button></div>`).join("")}</div><div class="section-title"><h2>工具接入</h2></div><div class="card">${state.tools.map((t) => `<div class="row"><div class="row-main"><h3>${E(t.name)}</h3><p>${E(t.description)}</p></div><span class="tag ${t.status === "manual" ? "warn" : ""}">${t.id === "codex" ? (state.runtime.available ? "已找到 CLI" : "未找到 CLI") : t.status === "ready" ? "已接入" : "手动导入"}</span></div>`).join("")}</div><div class="section-title"><h2>Lanhu MCP</h2></div><div class="card"><div class="row"><div class="row-main"><h3>蓝湖原型读取</h3><p>${E(lanhu.message || "尚未检测")}</p><p class="muted">配置来源：${E(lanhu.source || "本机 Codex 配置")} · 认证值不会显示或写入工作台。</p></div><span class="tag ${lanhu.ready ? "" : "warn"}">${lanhu.ready ? "配置可用" : "需要配置"}</span></div><div class="actions"><button class="primary small" data-action="lanhu-config">配置 / 重新检测</button><span class="help">未安装时请先安装 Node.js，再运行 npx -y mcp-lanhu；也可以继续上传截图或 PRD。</span></div></div><div class="section-title"><h2>运行环境</h2></div><div class="card"><p>生成模型：<span class="mono">${E(state.runtime.model)}</span></p><p>知识来源：${state.runtime.knowledge_count} 份已启用方法、模板与案例。</p><p>检索方式：${E(state.runtime.retrieval)}。</p><p>全局知识索引：${state.runtime.global_index ? `${globalStats.sources || 0} 个来源 / ${globalStats.chunks || 0} 个片段` : "未建立或当前不可用"}</p><p>项目隔离索引：${state.runtime.project_index ? `${projectStats.sources || 0} 份资料 / ${projectStats.chunks || 0} 个片段` : "将在首次检索时建立"}</p>${state.runtime.fallback ? '<div class="banner">Hybrid RAG 当前已自动回退关键词检索，不会阻断资料准备和文档生成。</div>' : ""}<div class="help">检索结果继续展示来源和原文，便于检查生成依据；向量 ID、内部得分和索引治理字段不会进入任务正文。扩展新工具仍需实现后端适配器，添加名字不会自动获得工具能力。</div></div>`;
  const connectionNote = document.createElement("div");
  connectionNote.className = state.runtime.codex_error ? "banner" : "help";
  connectionNote.textContent = state.runtime.codex_error ||
    "找到 CLI 只表示本机可执行入口存在，不代表账号、模型与网络已通过真实生成测试。登录与认证由本机 Codex 管理；工作台不会复制凭据。";
  $("#content").appendChild(connectionNote);
}
