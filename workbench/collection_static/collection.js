"use strict";
let state, projectId = localStorage.getItem("collector-project"), tab = "materials", polling = false, toastTimer, searchQuery = "";
const $ = (selector) => document.querySelector(selector);
const E = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
const date = (value) => new Date(value).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});
const currentVersion = () => null;
const scrapeStatusNames = {queued:"排队中",running:"正在采集",ready:"待确认保存",completed:"已保存",empty:"结果为空",failed:"失败",cancelled:"已停止"};
function toast(message) { $("#toast").textContent = message; $("#toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $("#toast").hidden = true, 5000); }
function error(err) { toast(err.message || String(err)); console.error(err); }
function modal(label, body) { $("#modal-label").textContent = label; $("#modal-body").innerHTML = body; if (!$("#modal").open) $("#modal").showModal(); }
function close() { if (typeof androidCaptureStopPolling === "function") androidCaptureStopPolling(); $("#modal").close(); }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json","X-Workbench-Token":state?.token || ""},body:JSON.stringify(body)});
  const data = await response.json(); if (!response.ok) throw Error(data.error || "请求失败"); return data;
}
let refreshSequence = 0;
async function refresh(render = true) {
  const requested = projectId, sequence = ++refreshSequence;
  const result = await api("/api/state" + (requested ? "?project=" + encodeURIComponent(requested) : ""));
  if (sequence !== refreshSequence || requested !== projectId) return;
  state = result; $("#banner").hidden = true; if (render) draw();
}
function newProject() {
  modal("新建采集项目", '<h2>把同一轮采集放在一起</h2><form id="create-project"><label for="project-name">项目名称</label><input id="project-name" required maxlength="100" placeholder="例如：蓝牙查找器竞品采集"><label for="project-brief">备注（可选）</label><textarea id="project-brief" maxlength="12000" placeholder="采集目的、目标国家或本轮范围"></textarea><div class="actions"><button class="primary" type="submit">创建项目</button><button type="button" data-close-modal>取消</button></div></form>');
  $("#create-project").onsubmit = async (event) => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    try { const project = await api("/api/projects", {name:$("#project-name").value,brief:$("#project-brief").value}); projectId = project.id; localStorage.setItem("collector-project", projectId); close(); await refresh(); }
    catch (err) { error(err); button.disabled = false; }
  };
  $("#project-name").focus();
}
function draw() {
  $("#projects").innerHTML = state.projects.map((project) => `<button class="${project.id === projectId ? "active" : ""}" data-project="${E(project.id)}">${E(project.name)}</button>`).join("");
  if (!state.project) {
    $("#content").innerHTML = '<div class="collection-empty"><span class="eyebrow">DATA COLLECTION</span><h1>先收集，再判断。</h1><p>查找竞品，收集商店描述、评论和截图，或连接 Android 手机自动走查。原始资料集中保存，可以直接导出交给同事。</p><button class="primary" data-action="new">＋ 新建第一个采集项目</button></div>'; return;
  }
  $("#breadcrumb").textContent = `数据采集 / ${state.project.name}`;
  const scrapes = state.scrapes || [], files = state.documents || [];
  const rows = scrapes.map((item) => `<article class="row"><div class="row-main"><h3>${E(item.listing_title || item.app_id)}</h3><p>${E(item.platform === "app_store" ? "App Store" : "Google Play")} · ${Number(item.review_count || 0)} 条评论 · ${Number(item.translated_count || 0)} 条译文 · ${Number(item.screenshot_count || 0)} 张商店截图 · ${date(item.created)}</p>${item.error ? `<small class="scrape-error">${E(item.error)}</small>` : ""}</div><span class="tag ${["failed","cancelled"].includes(item.status)?"bad":["running","queued"].includes(item.status)?"run":item.status==="ready"?"warn":""}">${E(scrapeStatusNames[item.status] || item.status)}</span>${["ready","completed"].includes(item.status) ? `<button class="small" data-preview-scrape="${E(item.id)}">预览</button>` : ""}${item.status === "ready" ? `<button class="primary small" data-confirm-scrape="${E(item.id)}">确认保存</button>` : ""}${["running","queued"].includes(item.status) ? `<button class="small" data-cancel-scrape="${E(item.id)}">停止</button>` : ""}${["failed","cancelled","empty"].includes(item.status) ? `<button class="small" data-retry-scrape="${E(item.id)}">重试</button>` : ""}</article>`).join("");
  $("#content").innerHTML = `<section class="collection-hero"><span class="eyebrow">采集项目</span><h1>${E(state.project.name)}</h1><p>${E(state.project.brief || "选择采集方式，结果预览确认后保存在这个项目。")}</p><div class="collection-stats"><span><strong>${files.length}</strong>份已保存资料</span><span><strong>${scrapes.filter(item => item.status === "ready").length}</strong>项待确认</span><span><strong>${scrapes.filter(item => ["queued","running"].includes(item.status)).length}</strong>项正在采集</span></div></section>
  <section class="collection-actions" aria-label="采集方式"><article class="collection-action"><span class="step">01 / DISCOVER</span><h2>找竞品</h2><p>按关键词、平台和市场查找候选。你选定应用，再继续采集描述、评论和商店截图。</p><button class="primary" data-action="competitor-discovery">搜索竞品 →</button></article><article class="collection-action"><span class="step">02 / COLLECT</span><h2>采集商店资料</h2><p>已有链接或包名时直接采集。支持批量、多国家、评论筛选和中文翻译。</p><button class="primary" data-action="review-scrape">粘贴链接开始 →</button></article><article class="collection-action"><span class="step">03 / CAPTURE</span><h2>Android 实机截图</h2><p>连接已授权手机，给出 App 包名和走查范围。自动记录页面、分支和模块流程 PNG。</p><button class="primary" data-action="android-capture">连接手机走查 →</button></article></section>
  <section class="collection-section"><div class="section-title"><div><h2>商店采集记录</h2><p class="muted">采集完成后先预览，再确认保存。</p></div><button class="small" data-action="refresh">刷新</button></div><div class="card">${rows || '<div class="empty compact">还没有商店采集记录。</div>'}</div></section>
  <section class="collection-section"><div class="section-title"><div><h2>实机走查记录</h2><p class="muted">查看截图、暂停续跑，下载原始证据 ZIP。</p></div><button class="small" data-android-capture-history-refresh>刷新</button></div><div id="android-capture-history" aria-live="polite"></div></section>
  <section class="collection-section"><div class="section-title"><div><h2>已保存资料</h2><p class="muted">原文、评论 CSV、商店截图与实机证据统一保存。</p></div><a class="button-link" href="/api/projects/${encodeURIComponent(projectId)}/export">导出采集数据包 ↓</a></div><div class="searchbar collection-search"><input id="file-search" type="search" placeholder="搜索资料名称" value="${E(searchQuery)}" aria-label="搜索资料名称"></div><div class="collection-files" id="collection-files">${files.map((file) => {
    const image = /\.(png|jpg|jpeg|webp)$/i.test(file.name);
    return `<article class="collection-file" data-file-name="${E(file.name.toLocaleLowerCase())}" ${file.name.toLocaleLowerCase().includes(searchQuery.toLocaleLowerCase()) ? "" : "hidden"}>${image ? `<img loading="lazy" src="/api/assets/${encodeURIComponent(projectId)}/${encodeURIComponent(file.id)}" alt="${E(file.name)}">` : ""}<h3>${E(file.name)}</h3><p>${date(file.created)} · ${image ? "图片" : `${Number(file.characters || 0).toLocaleString()} 字符`}</p><div class="actions"><button class="small" data-document="${E(file.id)}">预览</button><a class="button-link small" href="/api/documents/${encodeURIComponent(file.id)}/download">下载</a></div></article>`;
  }).join("") || '<div class="empty compact">确认采集结果后，资料会显示在这里。</div>'}</div><p id="no-files" class="muted" hidden>没有匹配的资料。</p></section>`;
  $("#file-search").oninput = (event) => { searchQuery = event.target.value; let count = 0; document.querySelectorAll("[data-file-name]").forEach((file) => { file.hidden = !file.dataset.fileName.includes(searchQuery.toLocaleLowerCase()); if (!file.hidden) count++; }); $("#no-files").hidden = count > 0 || !files.length; };
  androidCaptureRenderHistory().catch(error);
}
function showDocument(document) {
  const image = /\.(png|jpg|jpeg|webp)$/i.test(document.name);
  const content = image ? `<img class="collection-preview" src="/api/assets/${encodeURIComponent(document.project_id)}/${encodeURIComponent(document.id)}" alt="${E(document.name)}">` : `<pre class="collection-text">${E(document.text || "")}</pre>`;
  modal(document.name, content + `<div class="actions"><a class="button-link" href="/api/documents/${encodeURIComponent(document.id)}/download">下载原文件</a>${/\.csv$/i.test(document.name) ? `<button class="small" data-translate-document="${E(document.id)}">补充中文翻译</button>` : ""}<button data-close-modal>关闭</button></div>`);
}
function showHelp() {
  modal("使用说明", '<h2>数据采集工作台</h2><ol><li>新建采集项目。</li><li>搜索竞品并手选，或直接粘贴商店链接采集资料。</li><li>需要实机证据时，连接 Android 手机，开启 USB 调试并允许这台电脑，填写已安装 App 包名和走查范围。</li><li>预览后确认保存，最后导出采集数据包交给同事。</li></ol><p>实机截图内置 android-walkthrough 1.0.1；自动查找电脑上的 ADB，并可复用完整版保存过的本机路径。换 Android 手机无需修改 ADB 路径。首次授权仍需在手机上确认。</p><p>商店采集需要网络；自动实机走查还需要本机已安装并登录 Codex CLI。收入资料可通过找竞品中的来源入口人工记录。App Store 的实际采集可用性取决于公开接口返回，本包未新增成功验证。</p><p>本版只提供采集、预览、保存和导出。数据独立保存在 %LOCALAPPDATA%\\ProductWorkbenchCollector\\data。关闭启动窗口或按 Ctrl+C 停止本次服务。</p><button data-close-modal>知道了</button>');
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button"); if (!button) return;
  try {
    if (button.dataset.project) { close(); projectId = button.dataset.project; localStorage.setItem("collector-project", projectId); await refresh(); }
    else if (button.dataset.action === "new") newProject();
    else if (button.hasAttribute("data-close-modal")) close();
    else if (button.dataset.action === "refresh") await refresh();
    else if (button.dataset.action === "competitor-discovery") openCompetitorDiscovery();
    else if (button.dataset.action === "review-scrape") reviewScrapeForm();
    else if (button.dataset.action === "android-capture") await openAndroidCapture();
    else if (button.dataset.androidCaptureSession) await openAndroidCapture(button.dataset.androidCaptureSession);
    else if (button.hasAttribute("data-android-capture-history-refresh")) await androidCaptureRenderHistory(true);
    else if (button.dataset.previewScrape) await competitorPreview(button.dataset.previewScrape);
    else if (button.dataset.confirmScrape) { button.disabled = true; await api(`/api/reviews/scrape/${button.dataset.confirmScrape}/confirm`, {}); close(); await refresh(); toast("采集资料已保存"); }
    else if (button.dataset.cancelScrape || button.dataset.retryScrape) { button.disabled = true; await api(`/api/reviews/scrape/${button.dataset.cancelScrape || button.dataset.retryScrape}/${button.dataset.cancelScrape ? "cancel" : "retry"}`, {}); await refresh(); }
    else if (button.dataset.document) showDocument(await api(`/api/documents/${button.dataset.document}`));
    else if (button.dataset.translateDocument) { button.disabled = true; button.textContent = "正在翻译…"; const result = await api(`/api/documents/${button.dataset.translateDocument}/translate`, {}); showDocument(await api(`/api/documents/${button.dataset.translateDocument}`)); await refresh(false); toast(`新增 ${result.newly_translated || 0} 条中文译文`); }
  } catch (err) { error(err); if (button.isConnected) button.disabled = false; }
});
window.addEventListener("DOMContentLoaded", async () => {
  $("#new-project").onclick = newProject; $("#help").onclick = showHelp; $("#close-modal").onclick = close;
  $("#modal").addEventListener("cancel", () => androidCaptureStopPolling());
  try { state = await api("/api/state"); if (!state.projects.some((project) => project.id === projectId)) projectId = state.projects[0]?.id || null; await refresh(); }
  catch (err) { $("#content").innerHTML = `<div class="empty"><h2>暂时无法连接采集工作台</h2><p>${E(err.message)}</p><p>请保留启动窗口，并刷新此页面。</p></div>`; }
  setInterval(async () => { if (polling || !state || !state.scrapes?.some((item) => ["queued","running"].includes(item.status))) return; polling = true; try { await refresh(!$("#modal").open); } catch (_) { $("#banner").textContent = "本机连接中断，正在重试。"; $("#banner").hidden = false; } finally { polling = false; } }, 3500);
});
