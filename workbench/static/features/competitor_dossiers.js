"use strict";

/* A dossier owns references, not copies. Collection and analysis selections never share a Set. */
const competitorDossierSessions = new Map();
const dossierMaterialLabels = {store_info:"商店信息", reviews:"评论", store_screenshot:"商店截图", device_screenshot:"实机截图", module_flow:"模块流程", note:"体验笔记", revenue:"下载与收入资料", attachment:"附件"};
const dossierRoleLabels = {"":"未指定用途", primary:"主对标", feature:"功能参考", monetization:"变现参考"};

function dossierScope() { return `${projectId}:${currentVersion()?.id || "product"}`; }
function dossierSession() {
  const key = dossierScope();
  if (!competitorDossierSessions.has(key)) competitorDossierSessions.set(key, {selected:new Set(), inputs:new Set(), publicSelected:new Set(), detail:"", detailTab:"overview", details:new Map(), summaries:new Map(), request:0, uploadType:"attachment", countsLoading:false});
  return competitorDossierSessions.get(key);
}
function dossierCompetitors() {
  const session=dossierSession();
  return (state.competitors || []).filter((item) => !item.archived).map((item) => {
    const summary=session.summaries.get(item.id);
    return summary ? {...item,counts:summary.counts,pending_count:summary.pending_count,last_collected:summary.last_collected} : item;
  });
}
function dossierDocumentTypes(document, competitorId = "") {
  const values = document.competitor_material_types;
  if (competitorId && values && !Array.isArray(values) && values[competitorId]) return [values[competitorId]].flat();
  if (document.material_type) return [document.material_type];
  if (Array.isArray(values) && values.length) return values;
  if (values && typeof values === "object") return Array.from(new Set(Object.values(values).flat()));
  if (document.category === "reviews" || /评论.*\.csv$/i.test(document.name || "")) return ["reviews"];
  if (/\.(png|jpe?g|webp)$/i.test(document.name || "")) return ["store_screenshot"];
  return ["attachment"];
}
function dossierDocumentReady(document) { return document.kind === "upload" && !["pending", "ready", "queued", "running", "failed", "cancelled", "interrupted", "empty"].includes(document.status) && document.confirmed !== false; }
function dossierDocumentInScope(document) { return !(document.versions || []).length || Boolean(currentVersion() && document.versions.some((version) => version.id === currentVersion().id)); }
function dossierDocuments(id) { return (state.documents || []).filter((document) => dossierDocumentInScope(document) && (document.competitor_ids || []).includes(id)); }
function dossierCommonDocuments() {
  // Unassigned source files are one group in this page, not a second workspace.
  // Generated drafts and confirmed outputs retain their own delivery records.
  return (state.documents || []).filter((document) => document.kind === "upload" && !(document.competitor_ids || []).length && dossierDocumentInScope(document));
}
function dossierInputDocuments(session = dossierSession()) {
  return (state.documents || []).filter((document) => dossierDocumentInScope(document) && dossierDocumentReady(document) && ((document.competitor_ids || []).some((id) => session.selected.has(id)) || (document.kind === "upload" && !(document.competitor_ids || []).length)));
}
function dossierPruneInputs(session = dossierSession()) {
  const eligible = new Set(dossierInputDocuments(session).map((document) => document.id));
  session.inputs = new Set([...session.inputs].filter((id) => eligible.has(id)));
  const common = new Set(dossierCommonDocuments().filter(dossierDocumentReady).map((document) => document.id));
  session.publicSelected = new Set([...session.publicSelected].filter((id) => common.has(id)));
}
function dossierInputSummary(session = dossierSession()) {
  const selected = dossierInputDocuments(session).filter((document) => session.inputs.has(document.id));
  const imageCount = selected.filter((document) => /\.(png|jpe?g|webp)$/i.test(document.name || "")).length;
  const competitors = new Set(selected.flatMap((document) => (document.competitor_ids || []).filter((id) => session.selected.has(id))));
  const commonCount = selected.filter((document) => !(document.competitor_ids || []).length).length;
  return `本次使用 ${competitors.size} 个竞品、${selected.length - imageCount} 份文档、${imageCount} 张截图${commonCount ? `，含 ${commonCount} 份项目公共资料` : ""}（最多 12 份资料）。`;
}
function dossierFileRow(document, options = {}) {
  const types = dossierDocumentTypes(document);
  const image = /\.(png|jpe?g|webp)$/i.test(document.name || "");
  return `<article class="dossier-file ${image ? "dossier-image-file" : ""}">${image ? `<button class="dossier-image-button" data-document="${E(document.id)}"><img src="/api/assets/${encodeURIComponent(projectId)}/${encodeURIComponent(document.id)}" alt="${E(document.name)}" loading="lazy"></button>` : ""}<div class="row-main"><strong>${E(document.name)}</strong><small>${E(types.map((type) => dossierMaterialLabels[type] || "附件").join(" · "))} · ${E(date(document.created))}</small></div><button class="small" data-document="${E(document.id)}">${image ? "查看" : types.includes("reviews") ? "查看评论" : "读原文"}</button>${options.unlink ? `<button class="small" data-dossier-unlink="${E(document.id)}">移出此档案</button>` : ""}</article>`;
}
function dossierIntakeMarkup(competitor) {
  return `<section class="material-intake dossier-intake"><div class="section-title"><div><h3>补充 ${E(competitor.title || competitor.app_id)} 的资料</h3><p class="muted">在这里粘贴或上传，自动归到当前竞品；切换档案不会改变暂存资料的归属。</p></div></div><label for="dossier-upload-type">本次上传资料类型</label><select id="dossier-upload-type">${Object.entries(dossierMaterialLabels).map(([key,label]) => `<option value="${key}" ${key === "attachment" ? "selected" : ""}>${label}</option>`).join("")}</select><div id="material-paste-zone" class="paste-zone" tabindex="0" role="button" aria-label="粘贴、拖入或选择当前竞品的资料"><strong>截图后按 Ctrl+V，可连续粘贴多张</strong><p>也可以拖入文件，检查后再一并上传。</p><button id="pick-materials" class="small" type="button">选择文件</button><input class="visually-hidden" type="file" id="upload" multiple accept=".md,.txt,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp"><small>单份最大 12 MB，一批最多 30 份。</small></div><div id="pending-materials" aria-live="polite"></div></section>`;
}
function bindDossierIntake() {
  const zone = $("#material-paste-zone");
  if (!zone) return;
  const typePicker=$("#dossier-upload-type");
  if (typePicker) {typePicker.value=dossierSession().uploadType;typePicker.onchange=()=>{dossierSession().uploadType=typePicker.value;};}
  $("#upload").onchange = upload;
  $("#pick-materials").onclick = () => $("#upload").click();
  zone.onclick = (event) => { if (!event.target.closest("button")) $("#upload").click(); };
  zone.onkeydown = (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); $("#upload").click(); } };
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove("dragging"); }));
  zone.addEventListener("drop", (event) => queueMaterialFiles(event.dataTransfer?.files));
  renderPendingMaterials();
}
function dossierInputTree(session) {
  const selected = dossierCompetitors().filter((item) => session.selected.has(item.id));
  const competitorTree = selected.map((competitor) => {
    const documents = dossierInputDocuments(session).filter((document) => (document.competitor_ids || []).includes(competitor.id));
    const groups = Object.entries(dossierMaterialLabels).map(([type,label]) => {
      const files = documents.filter((document) => dossierDocumentTypes(document, competitor.id).includes(type));
      return `<details class="dossier-input-group" ${files.some((document) => session.inputs.has(document.id)) ? "open" : ""}><summary>${E(label)} · ${files.length} 份${!files.length ? "（暂无已确认资料）" : ""}</summary>${files.map((document) => `<label><input type="checkbox" data-dossier-input="${E(document.id)}" ${session.inputs.has(document.id) ? "checked" : ""}><span>${E(document.name)}</span></label>`).join("") || '<small>先采集或补充资料，确认入库后才能选择。</small>'}</details>`;
    }).join("");
    return `<section class="dossier-input-competitor"><h4>${E(competitor.title || competitor.app_id)}</h4>${groups}</section>`;
  }).join("");
  const common = dossierCommonDocuments().filter(dossierDocumentReady);
  const commonTree = `<section class="dossier-input-competitor dossier-input-public"><h4>项目公共资料 <span class="tag">${common.length} 份可用</span></h4><p class="help">不必勾选竞品，也可仅用公共资料准备任务。</p>${common.map((document) => `<label class="dossier-public-input"><input type="checkbox" data-dossier-input="${E(document.id)}" ${session.inputs.has(document.id) ? "checked" : ""}><span>${E(document.name)}</span></label>`).join("") || '<small>暂无已确认的公共资料，可在上方粘贴或上传。</small>'}</section>`;
  return `${!selected.length ? '<p class="help dossier-input-hint">勾选上方竞品可展开它的资料；也可以直接选择项目公共资料。默认不会全选。</p>' : ""}${competitorTree}${commonTree}`;
}
function dossierAnalysisPanel(session) {
  return `<section class="card dossier-analysis-panel"><div class="section-title"><div><span class="eyebrow">分析输入 · 与采集范围分别勾选</span><h3>这次拿哪些资料进入分析？</h3></div><div class="actions"><button class="small" data-dossier-input-all>全选可用资料</button><button class="small" data-dossier-input-clear>清空</button></div></div><div class="dossier-input-tree">${dossierInputTree(session)}</div><div class="dossier-analysis-footer"><p id="dossier-input-summary" aria-live="polite">${E(dossierInputSummary(session))}</p><button class="primary" data-dossier-prepare ${session.inputs.size ? "" : "disabled"}>准备分析任务 →</button></div><small>仅带入明确勾选的已入库资料；待确认内容不进入分析。这里只准备任务包，不会自动生成。</small></section>`;
}
function drawCompetitorDossiers(refreshCounts = true) {
  const session = dossierSession();
  const competitors = dossierCompetitors();
  const currentIds = new Set(competitors.map((item) => item.id));
  session.selected = new Set([...session.selected].filter((id) => currentIds.has(id)));
  dossierPruneInputs(session);
  if (session.detail && currentIds.has(session.detail)) return drawDossierDetail(session.detail);
  session.detail = "";
  $("#view").innerHTML = `<div class="section-title"><div><h2>项目资料</h2><p class="muted">按竞品整理，公共资料也在这里。勾选需要的内容，再准备分析。</p></div><button class="primary" data-dossier-create>＋ 新建竞品档案</button></div><div class="dossier-toolbar"><span>勾选竞品后，可分别选择采集范围和分析输入。</span><div class="actions"><button class="small" data-action="competitor-discovery">找竞品</button><button class="small" data-action="review-scrape">粘贴链接采集</button><button class="small" data-action="android-capture">实机截图与流程</button><button class="primary" data-dossier-collect ${session.selected.size ? "" : "disabled"}>采集已选竞品（${session.selected.size}）</button></div></div><section aria-label="竞品分组"><div class="dossier-grid">${competitors.map((competitor) => {
    const counts = competitor.counts || {};
    return `<article class="card dossier-card ${session.selected.has(competitor.id) ? "is-selected" : ""}"><div class="dossier-card-heading"><label><input type="checkbox" data-dossier-select="${E(competitor.id)}" aria-label="选择 ${E(competitor.title || competitor.app_id)}" ${session.selected.has(competitor.id) ? "checked" : ""}><span class="tag">${competitor.platform === "app_store" ? "iOS" : "Android"}</span></label><button class="small" data-dossier-open="${E(competitor.id)}">打开档案 ↗</button></div><h3>${E(competitor.title || competitor.app_id)}</h3><p class="dossier-package">${E(competitor.app_id)}</p><span class="tag">${E(dossierRoleLabels[competitor.role] || "未指定用途")}</span>${competitor.note ? `<p>${E(competitor.note)}</p>` : ""}<div class="dossier-counts"><span><b>${Number(counts.reviews || 0)}</b> 份评论</span><span><b>${Number(counts.store_screenshot || 0)}</b> 张商店图</span><span><b>${Number(counts.device_screenshot || 0) + Number(counts.module_flow || 0)}</b> 份实机 / 流程</span></div><footer><span>已入库 ${Number(counts.documents || 0)} 份 · 待确认 ${Number(competitor.pending_count || 0)} 批</span><small>${competitor.last_collected ? `最近采集 ${E(date(competitor.last_collected))}` : "尚未采集"}</small></footer></article>`;
  }).join("") || '<div class="empty"><h3>先建一个竞品档案</h3><p>有链接或应用 ID 就能建立，不必先把资料收齐。</p><button class="primary" data-dossier-create>新建竞品档案</button></div>'}</div></section><section id="project-public-materials" class="project-public-materials" aria-label="项目公共资料"></section>${dossierAnalysisPanel(session)}<aside id="project-material-tools" aria-label="按需工具"></aside>`;
  drawCommonProjectMaterials("#project-public-materials");
  if (refreshCounts) dossierRefreshCounts(session);
}
async function dossierRefreshCounts(session) {
  if (session.countsLoading) return;
  session.countsLoading=true;
  const scope=dossierScope();
  try {
    const result=await api(`/api/competitors?project_id=${encodeURIComponent(projectId)}&version_id=${encodeURIComponent(currentVersion()?.id || "")}`);
    if (scope !== dossierScope()) return;
    session.summaries=new Map((result.competitors || []).map((item)=>[item.id,item]));
    if (tab === "materials" && !session.detail) drawCompetitorDossiers(false);
  } catch (err) {if (scope === dossierScope()) error(err);}
  finally {session.countsLoading=false;}
}
async function drawDossierDetail(id) {
  const session = dossierSession(), scope = dossierScope();
  const competitor = dossierCompetitors().find((item) => item.id === id);
  if (!competitor) return;
  const cached = session.details.get(id);
  renderDossierDetail(competitor, cached);
  const request = ++session.request;
  try {
    const detail = await api(`/api/competitors/${encodeURIComponent(id)}?project_id=${encodeURIComponent(projectId)}&version_id=${encodeURIComponent(currentVersion()?.id || "")}`);
    if (scope !== dossierScope() || session.detail !== id || request !== session.request || tab !== "materials") return;
    session.details.set(id, detail);
    // Update only the reading pane: never destroy a user's queued uploads or controls.
    const pane = $("#dossier-reading-pane");
    if (pane) pane.innerHTML = dossierDetailPane(detail, session.detailTab);
  } catch (err) { if (scope === dossierScope() && request === session.request) error(err); }
}
function dossierDetailPane(detail, activeTab) {
  const documents = detail.documents || dossierDocuments(detail.id);
  const typesFor = (type) => documents.filter((document) => dossierDocumentTypes(document).includes(type));
  const rows = (files) => files.map((document) => dossierFileRow(document, {unlink:true})).join("") || '<p class="help">暂无已入库资料，可在下方补充。</p>';
  const scrapes = detail.scrapes || [];
  const listingBatch = scrapes.find((item) => item.status === "completed" && item.listing && (item.listing.short_description || item.listing.long_description));
  const listing = listingBatch?.listing;
  const listingPreview = listing ? `<div class="dossier-listing-preview"><small>最近已确认商店资料 · ${E(listing.market || "市场未提供")} · ${E(date(listingBatch.updated || listingBatch.created))}</small><h4>短描述</h4><p class="document">${E(listing.short_description || "此商店未提供短描述。")}</p><details><summary>查看长描述</summary><div class="document">${E(listing.long_description || "此商店未提供长描述。")}</div></details></div>` : "";
  const batches = scrapes.map((item) => `<div class="row"><div class="row-main"><strong>${E(item.listing_title || item.app_id || detail.title)}</strong><small>${E(date(item.created))} · ${E(scrapeStatusNames[item.status] || item.status)}${item.review_count ? ` · ${Number(item.review_count)} 条评论` : ""}</small></div>${["ready", "completed"].includes(item.status) ? `<button class="small" data-preview-scrape="${E(item.id)}">预览批次</button>` : ""}${item.status === "ready" ? `<button class="primary small" data-confirm-scrape="${E(item.id)}">确认入库</button>` : ""}${["failed", "empty", "cancelled"].includes(item.status) ? `<button class="small" data-retry-scrape="${E(item.id)}">重试</button>` : ""}</div>`).join("");
  if (activeTab === "reviews") return `<h3>已确认评论</h3><p class="help">打开评论文件后可筛选查看原文与译文、补充翻译和下载 CSV；不同国家与采集日期保留为独立批次。</p>${rows(typesFor("reviews"))}<details class="dossier-batches"><summary>采集批次与待确认资料（${scrapes.length}）</summary>${batches || '<p class="help">暂无采集批次。</p>'}</details>`;
  if (activeTab === "images") return `<h3>商店宣传截图</h3><div class="dossier-images">${rows(typesFor("store_screenshot"))}</div><h3>App 实机截图</h3><div class="dossier-images">${rows(typesFor("device_screenshot"))}</div><h3>按模块的流程拼图</h3><div class="dossier-images">${rows(typesFor("module_flow"))}</div>${(detail.captures || []).length ? `<details><summary>实机走查记录</summary>${detail.captures.map((item) => `<button class="small" data-android-capture-session="${E(item.id)}">${E(item.title || item.package)} · ${E(item.status)}</button>`).join("")}</details>` : ""}`;
  if (activeTab === "notes") return `<h3>体验笔记与附件</h3><p class="document">${E(detail.note || "还没有填写竞品备注，可通过“编辑档案”补充。")}</p>${rows(documents.filter((document) => dossierDocumentTypes(document).some((type) => ["note", "attachment"].includes(type))))}`;
  return `<dl class="dossier-facts"><div><dt>应用 ID</dt><dd>${E(detail.app_id)}</dd></div><div><dt>对标用途</dt><dd>${E(dossierRoleLabels[detail.role] || "未指定用途")}</dd></div><div><dt>归属范围</dt><dd>${E(currentVersion()?.name || "产品级资料")}</dd></div></dl>${detail.note ? `<p>${E(detail.note)}</p>` : ""}<h3>商店信息与长短描述</h3>${listingPreview}${rows(typesFor("store_info"))}<h3>下载与收入资料</h3>${rows(typesFor("revenue"))}<details class="dossier-batches" ${scrapes.some((item) => item.status === "ready") ? "open" : ""}><summary>采集批次与待确认资料（${scrapes.length}）</summary>${batches || '<p class="help">暂无采集批次。</p>'}</details>`;
}
function renderDossierDetail(competitor, detail) {
  const session = dossierSession();
  const tabs = [["overview","概览与商店信息"],["reviews","评论"],["images","截图与流程"],["notes","笔记与附件"]];
  $("#view").innerHTML = `<div class="section-title dossier-detail-heading"><div><button class="small" data-dossier-back>← 返回项目资料</button><h2>${E(competitor.title || competitor.app_id)}</h2><p class="muted">${competitor.platform === "app_store" ? "App Store" : "Google Play"} · ${E(competitor.app_id)}</p></div><div class="actions"><button class="small" data-dossier-edit="${E(competitor.id)}">编辑档案</button><button class="small" data-dossier-attach="${E(competitor.id)}">归入已有资料</button><button class="primary" data-dossier-collect="${E(competitor.id)}">采集 / 补充资料</button><button class="small" data-dossier-device="${E(competitor.id)}" ${competitor.platform === "app_store" ? "disabled title=\"当前实机走查仅支持 Android\"" : ""}>实机截图与流程</button></div></div><nav class="tabs dossier-detail-tabs" role="tablist" aria-label="竞品档案内容">${tabs.map(([id,label]) => `<button role="tab" aria-selected="${session.detailTab === id}" class="${session.detailTab === id ? "active" : ""}" data-dossier-detail-tab="${id}">${label}</button>`).join("")}</nav><section class="card" id="dossier-reading-pane">${dossierDetailPane(detail || competitor, session.detailTab)}</section>${dossierIntakeMarkup(competitor)}`;
  bindDossierIntake();
}
function dossierParseIdentity(value, platform) {
  const text = String(value || "").trim();
  if (!text) throw Error("请填写商店链接或应用 ID。");
  if (!text.includes("://")) {
    if (!/^[A-Za-z0-9_.-]{1,200}$/.test(text)) throw Error("应用 ID 无效，请检查链接或包名。");
    return {platform:/^\d+$/.test(text) ? "app_store" : platform, app_id:text, source_url:""};
  }
  const url = new URL(text);
  if (url.protocol !== "https:" || url.username || url.password) throw Error("请填写正式的 HTTPS 商店链接。");
  if (url.hostname === "play.google.com") {
    const id = url.searchParams.get("id");
    if (!id) throw Error("Google Play 链接中缺少应用 ID。");
    return {platform:"google_play", app_id:id, source_url:url.href};
  }
  if (url.hostname === "apps.apple.com") {
    const id = url.pathname.match(/\/id(\d+)(?:\/|$)/)?.[1];
    if (!id) throw Error("App Store 链接中缺少应用 ID。");
    return {platform:"app_store", app_id:id, source_url:url.href};
  }
  throw Error("仅支持 Google Play 或 App Store 链接。");
}
function dossierForm(id = "") {
  const item = dossierCompetitors().find((competitor) => competitor.id === id) || {};
  const scopeProject = projectId;
  modal(id ? "编辑竞品档案" : "新建竞品档案", `<h2>${id ? "维护对标用途与备注" : "先把这个竞品留下来"}</h2><form id="dossier-form"><label for="dossier-identity">商店链接或应用 ID</label><input id="dossier-identity" required maxlength="1500" value="${E(item.source_url || item.app_id || "")}" ${id ? "readonly" : ""} placeholder="粘贴 Google Play / App Store 链接"><label for="dossier-platform">平台</label><select id="dossier-platform" ${id ? "disabled" : ""}><option value="google_play">Android / Google Play</option><option value="app_store" ${item.platform === "app_store" ? "selected" : ""}>iOS / App Store</option></select><label for="dossier-title">竞品名称（可选）</label><input id="dossier-title" maxlength="300" value="${E(item.title || "")}"><label for="dossier-role">对标用途</label><select id="dossier-role">${Object.entries(dossierRoleLabels).map(([key,label]) => `<option value="${key}" ${item.role === key ? "selected" : ""}>${label}</option>`).join("")}</select><label for="dossier-note">体验笔记与参考备注（可选）</label><textarea id="dossier-note" maxlength="12000">${E(item.note || "")}</textarea><div class="actions"><button class="primary" type="submit">保存档案</button><button type="button" data-close-modal>取消</button></div></form>`);
  const form = $("#dossier-form");
  form.onsubmit = async (event) => {
    event.preventDefault(); event.submitter.disabled = true;
    try {
      if (scopeProject !== projectId) throw Error("项目已切换，请重新打开。");
      const identity = dossierParseIdentity($("#dossier-identity").value, $("#dossier-platform").value);
      const result = await api(id ? `/api/competitors/${encodeURIComponent(id)}/update` : "/api/competitors", {project_id:scopeProject,...identity,title:$("#dossier-title").value,role:$("#dossier-role").value,note:$("#dossier-note").value});
      if (scopeProject !== projectId) return;
      close(); dossierSession().detail = result.id || id;
      await refresh(); toast("竞品档案已保存");
    } catch (err) {error(err); event.submitter.disabled = false;}
  };
}
function dossierAttachForm(id) {
  const competitor = dossierCompetitors().find((item) => item.id === id), scope = dossierScope(), scopeProject = projectId;
  if (!competitor) return;
  const candidates = (state.documents || []).filter((document) => dossierDocumentInScope(document) && !(document.competitor_ids || []).includes(id) && dossierDocumentReady(document));
  modal("归入已有资料", `<h2>将资料关联到 ${E(competitor.title || competitor.app_id)}</h2><p class="help">只建立关联，不移动或复制文件；同一份榜单可归入多个竞品。</p><form id="dossier-attach-form"><label for="dossier-attach-type">资料类型</label><select id="dossier-attach-type">${Object.entries(dossierMaterialLabels).map(([key,label]) => `<option value="${key}">${label}</option>`).join("")}</select><div class="checks">${candidates.map((document) => `<label><input type="checkbox" name="attach-docs" value="${E(document.id)}">${E(document.name)}</label>`).join("") || '<p>没有可以归入的资料。可直接在档案中上传。</p>'}</div><button type="submit" class="primary" ${candidates.length ? "" : "disabled"}>归入此竞品</button></form>`);
  $("#dossier-attach-form").onsubmit = async (event) => {
    event.preventDefault(); event.submitter.disabled = true;
    try {
      const ids = Array.from(event.target.querySelectorAll('input[name="attach-docs"]:checked')).map((input) => input.value);
      if (!ids.length) throw Error("至少勾选一份资料。");
      if (scope !== dossierScope()) throw Error("范围已切换，请重新打开。");
      await api(`/api/competitors/${encodeURIComponent(id)}/documents`, {project_id:scopeProject, document_ids:ids,material_type:$("#dossier-attach-type").value});
      close(); await refresh(); toast(`已关联 ${ids.length} 份资料`);
    } catch (err) {error(err);event.submitter.disabled=false;}
  };
}
function dossierCollect(ids) {
  const selected = dossierCompetitors().filter((item) => ids.includes(item.id));
  if (!selected.length) return toast("请先勾选竞品");
  reviewScrapeForm({entries:selected.map((item) => item.source_url || item.app_id),selections:selected,competitorIds:selected.map((item) => item.id)});
}
function dossierPublicAttachForm() {
  const session = dossierSession(), scope = dossierScope(), scopeProject = projectId;
  dossierPruneInputs(session);
  const documents = dossierCommonDocuments().filter((document) => dossierDocumentReady(document) && session.publicSelected.has(document.id));
  const competitors = dossierCompetitors();
  if (!documents.length) throw Error("请先在项目公共资料中勾选需要归档的文件。");
  if (!competitors.length) throw Error("请先新建一个竞品档案。");
  modal("归入竞品档案", `<h2>归入 ${documents.length} 份公共资料</h2><p class="help">只建立关联，不移动原文件，也不会修改文档中的图片引用。</p><form id="dossier-public-attach-form"><label for="dossier-public-target">归入哪个竞品</label><select id="dossier-public-target">${competitors.map((item) => `<option value="${E(item.id)}">${E(item.title || item.app_id)}</option>`).join("")}</select><label for="dossier-public-type">资料类型</label><select id="dossier-public-type">${Object.entries(dossierMaterialLabels).map(([key,label]) => `<option value="${key}" ${key === "attachment" ? "selected" : ""}>${E(label)}</option>`).join("")}</select><ul>${documents.map((document) => `<li>${E(document.name)}</li>`).join("")}</ul><div class="actions"><button class="primary" type="submit">确认归入</button><button type="button" data-close-modal>取消</button></div></form>`);
  $("#dossier-public-attach-form").onsubmit = async (event) => {
    event.preventDefault(); event.submitter.disabled=true;
    try {
      if (scope !== dossierScope()) throw Error("项目或版本已切换，请重新选择资料。");
      const competitorId=$("#dossier-public-target").value;
      await api(`/api/competitors/${encodeURIComponent(competitorId)}/documents`, {project_id:scopeProject,document_ids:documents.map((document)=>document.id),material_type:$("#dossier-public-type").value});
      if (scope !== dossierScope()) return;
      session.publicSelected.clear(); close(); await refresh(); toast(`已归入 ${documents.length} 份资料`);
    } catch (err) {error(err);event.submitter.disabled=false;}
  };
}
function dossierDevicePicker(ids) {
  const selected = dossierCompetitors().filter((item) => ids.includes(item.id) && item.platform === "google_play");
  if (!selected.length) throw Error("请保留至少一个 Android 竞品；当前实机走查不支持 iOS。");
  modal("设置实机截图与流程", `<h2>先选一款竞品，再设置设备与范围</h2><p class="help">实机走查逐款执行，不会因为勾选就自动操作设备。商店采集与实机走查分开运行。</p><label for="dossier-device-app">本次走查的竞品</label><select id="dossier-device-app">${selected.map((item) => `<option value="${E(item.id)}">${E(item.title || item.app_id)}</option>`).join("")}</select><div class="actions"><button class="primary" id="dossier-open-device">设置设备与范围</button><button type="button" data-close-modal>稍后再做</button></div>`);
  $("#dossier-open-device").onclick = () => {
    const item = selected.find((entry) => entry.id === $("#dossier-device-app").value);
    openAndroidCapture("",{competitor_id:item.id,package:item.app_id,title:`${item.title || item.app_id} 实机走查`});
  };
}
async function dossierPrepare(button) {
  const session = dossierSession(), scope = dossierScope(); dossierPruneInputs(session);
  if (!session.inputs.size) throw Error("请先勾选已确认的分析资料。");
  if (session.inputs.size > 12) throw Error("一次最多指定 12 份资料，请缩小本次范围。");
  button.disabled = true;
  const result = await api("/api/competitors/inputs", {project_id:projectId,version_id:currentVersion()?.id || "",competitor_ids:[...session.selected],document_ids:[...session.inputs]});
  if (scope !== dossierScope()) return;
  const choices = (state.packs || []).flatMap((pack) => pack.tasks || []).filter((task) => /f1-category-user|f1-competitor|competitor|review-analysis/.test(task.key));
  modal("选择分析任务", `<h2>资料已选好，再确定本次要做什么</h2><p>${E(dossierInputSummary(session))}</p><div class="dossier-task-choices">${choices.map((task) => `<button data-dossier-chosen-task="${E(task.key)}"><strong>${E(task.name)}</strong><small>${E(task.description || task.output || "")}</small></button>`).join("") || '<p class="help">当前没有可用分析任务，请先启用新品分析能力包。</p>'}</div><p class="help">下一步只准备任务包；你核对后再启动生成。</p>`);
  document.querySelectorAll("[data-dossier-chosen-task]").forEach((item) => {item.onclick = () => prepareTask(item.dataset.dossierChosenTask,{documentIds:result.document_ids || [...session.inputs],competitorIds:result.competitor_ids || [...session.selected],sourceSelectionMode:"explicit"});});
}

document.addEventListener("change", (event) => {
  const input = event.target;
  if (input.dataset?.dossierSelect) {
    const session = dossierSession();
    if (input.checked) session.selected.add(input.dataset.dossierSelect); else session.selected.delete(input.dataset.dossierSelect);
    dossierPruneInputs(session); drawCompetitorDossiers();
  } else if (input.dataset?.dossierPublicSelect) {
    const session=dossierSession();
    const id=input.dataset.dossierPublicSelect;
    if (!dossierCommonDocuments().some((document)=>document.id === id && dossierDocumentReady(document))) {input.checked=false;return;}
    if (input.checked) session.publicSelected.add(id); else session.publicSelected.delete(id);
    const button=$("[data-dossier-public-attach]");
    if (button) {button.disabled=!session.publicSelected.size;button.textContent=`归入竞品档案（${session.publicSelected.size}）`;}
  } else if (input.dataset?.dossierInput) {
    const session = dossierSession();
    if (input.checked && session.inputs.size >= 12) {input.checked=false;toast("一次最多指定 12 份资料");return;}
    if (input.checked) session.inputs.add(input.dataset.dossierInput); else session.inputs.delete(input.dataset.dossierInput);
    document.querySelectorAll(`[data-dossier-input="${CSS.escape(input.dataset.dossierInput)}"]`).forEach((item) => {item.checked=input.checked;});
    $("#dossier-input-summary").textContent=dossierInputSummary(session);
    $("[data-dossier-prepare]").disabled = !session.inputs.size;
  }
});
document.addEventListener("click", async (event) => {
  const button=event.target.closest("button"); if (!button) return;
  const data=button.dataset;
  if (!Object.keys(data).some((key) => key.startsWith("dossier"))) return;
  const session=dossierSession();
  try {
    if (button.hasAttribute("data-dossier-create")) dossierForm();
    else if (data.dossierOpen) {session.detail=data.dossierOpen;session.detailTab="overview";await drawDossierDetail(session.detail);}
    else if (button.hasAttribute("data-dossier-back")) {session.detail="";drawCompetitorDossiers();}
    else if (data.dossierEdit) dossierForm(data.dossierEdit);
    else if (data.dossierAttach) dossierAttachForm(data.dossierAttach);
    else if (button.hasAttribute("data-dossier-public-attach")) dossierPublicAttachForm();
    else if (data.dossierDetailTab) {session.detailTab=data.dossierDetailTab;await drawDossierDetail(session.detail);}
    else if (button.hasAttribute("data-dossier-collect")) dossierCollect(data.dossierCollect ? [data.dossierCollect] : [...session.selected]);
    else if (data.dossierDevice) {
      const item=dossierCompetitors().find((competitor)=>competitor.id===data.dossierDevice);
      if (item?.platform !== "google_play") throw Error("当前实机走查仅支持 Android。");
      await openAndroidCapture("",{competitor_id:item.id,package:item.app_id,title:`${item.title || item.app_id} 实机走查`});
    }
    else if (button.hasAttribute("data-dossier-input-all")) {
      const available=dossierInputDocuments(session);
      if (available.length>12) return toast(`可用资料共 ${available.length} 份，超过 12 份；请按本次任务手动勾选。`);
      session.inputs=new Set(available.map((document)=>document.id));drawCompetitorDossiers();
    }
    else if (button.hasAttribute("data-dossier-input-clear")) {session.inputs.clear();drawCompetitorDossiers();}
    else if (button.hasAttribute("data-dossier-prepare")) await dossierPrepare(button);
    else if (data.dossierUnlink) {
      if (!confirm("仅移出当前竞品档案，原文件和其他竞品的关联仍保留。继续吗？")) return;
      await api(`/api/competitors/${encodeURIComponent(session.detail)}/unlink`,{project_id:projectId,document_ids:[data.dossierUnlink]});await refresh();
    }
  } catch (err) {error(err);button.disabled=false;}
});
