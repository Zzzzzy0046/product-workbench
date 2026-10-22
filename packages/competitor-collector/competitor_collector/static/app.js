"use strict";

const $ = (id) => document.getElementById(id);
const ACTIVE = new Set(["queued", "running"]);
const STATUS = { queued: "等待采集", running: "采集中", completed: "采集完成", partial: "部分完成", failed: "采集失败", pending: "等待采集" };
const GLOBAL_MARKETS = ["us", "gb", "de", "jp", "in", "id", "br", "sa"];
let meta = null;
let jobs = [];
let markets = new Map([["us", "美国"]]);
let selected = new Set(["us"]);
let pollTimer = null;
let loadingJobs = false;
let submitting = false;
let jobsRevision = 0;
let currentUser = null;
let csrfToken = "";
let authGeneration = 0;
let resetUser = null;
let loadingUsers = false;
let jobsRequest = 0;
let usersRequest = 0;
const expanded = new Set();
const seenDetails = new Set();

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function setAlert(id, message) {
  const target = $(id);
  target.textContent = message || "";
  target.hidden = !message;
}

function clearAuth(message = "", setupRequired = false) {
  currentUser = null;
  csrfToken = "";
  meta = null;
  resetUser = null;
  authGeneration += 1;
  window.CollectorScreens?.reset();
  jobsRevision += 1;
  jobsRequest += 1;
  usersRequest += 1;
  loadingJobs = false;
  loadingUsers = false;
  jobs = [];
  expanded.clear();
  seenDetails.clear();
  clearTimeout(pollTimer);
  pollTimer = null;
  $("jobs").replaceChildren();
  $("jobs-count").textContent = "0";
  $("users-list").replaceChildren();
  $("output-path").textContent = "";
  $("current-user").textContent = "";
  $("image-caption").textContent = "";
  $("large-image").removeAttribute("src");
  for (const id of ["image-dialog", "password-dialog", "reset-dialog"]) if ($(id).open) $(id).close();
  for (const id of ["capture-form", "create-user-form", "password-form", "reset-form"]) $(id).reset();
  $("login-password").value = "";
  $("workspace").hidden = true;
  $("collector-navigation").hidden = true;
  $("account-actions").hidden = true;
  $("admin-panel").hidden = true;
  $("admin-details").open = false;
  $("login-panel").hidden = false;
  $("login-fields").hidden = setupRequired;
  $("setup-notice").hidden = !setupRequired;
  $("login-submit").disabled = setupRequired;
  $("login-submit").firstElementChild.textContent = setupRequired ? "请先在本机设置管理员" : "登录";
  $("submit").disabled = true;
  $("refresh").disabled = false;
  $("refresh-users").disabled = false;
  $("translate").disabled = true;
  $("version").textContent = "";
  setAlert("form-error", "");
  setAlert("results-error", "");
  setAlert("admin-feedback", "");
  setAlert("login-error", message);
  selected = new Set([markets.has("us") ? "us" : markets.keys().next().value].filter(Boolean));
  renderMarkets();
  updateFilters();
}

async function enterSession(data) {
  if (!data.user || !data.csrf_token) throw new Error("登录信息不完整，请重新登录。");
  currentUser = data.user;
  csrfToken = data.csrf_token;
  authGeneration += 1;
  jobsRevision += 1;
  $("login-form").reset();
  $("login-panel").hidden = true;
  $("workspace").hidden = false;
  $("collector-navigation").hidden = false;
  window.CollectorScreens?.enterSession();
  $("account-actions").hidden = false;
  $("admin-panel").hidden = currentUser.role !== "admin";
  $("current-user").textContent = `${currentUser.username} · ${currentUser.role === "admin" ? "管理员" : "成员"}`;
  setAlert("login-error", "");
  await loadPrivateData();
}

function adminFeedback(message, error = false) {
  $("admin-feedback").className = `alert ${error ? "error" : "success"}`;
  setAlert("admin-feedback", message);
}

function renderUsers(users) {
  const area = $("users-list");
  area.replaceChildren();
  users.forEach((user) => {
    const row = node("div", "user-row");
    const info = node("div", "user-info");
    const self = user.id === currentUser?.id;
    info.append(node("span", "user-name", `${user.username}${self ? "（我）" : ""}`), node("span", "status-tag", user.role === "admin" ? "管理员" : "成员"), node("span", `status-tag ${user.disabled ? "failed" : "completed"}`, user.disabled ? "已停用" : "正常"));
    const buttons = node("div", "user-buttons");
    const toggle = node("button", "secondary-button", user.disabled ? "启用" : "停用");
    toggle.type = "button";
    toggle.disabled = self;
    if (self) toggle.title = "不能停用当前管理员账号";
    toggle.addEventListener("click", async () => {
      if (!confirm(`${user.disabled ? "启用" : "停用"}账号“${user.username}”？${user.disabled ? "" : "该账号将无法登录。"}`)) return;
      toggle.disabled = true;
      try { await api(`/api/users/${encodeURIComponent(user.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ disabled: !user.disabled }) }); adminFeedback(`账号“${user.username}”已${user.disabled ? "启用" : "停用"}。`); await loadUsers(); }
      catch (error) { if (currentUser) adminFeedback(error.message, true); }
      finally { toggle.disabled = self; }
    });
    const reset = node("button", "secondary-button", self ? "修改密码" : "重置密码");
    reset.type = "button";
    reset.addEventListener("click", () => {
      if (self) { $("change-password").click(); return; }
      resetUser = { id: user.id, username: user.username };
      $("reset-form").reset();
      $("reset-target").textContent = `为“${user.username}”设置新密码（10–128 个字符）。该账号已有登录会失效，请将新密码直接交给本人。`;
      setAlert("reset-error", "");
      $("reset-dialog").showModal();
    });
    buttons.append(toggle, reset); row.append(info, buttons); area.append(row);
  });
  if (!users.length) area.append(node("p", "no-content", "暂无账号。"));
}

async function loadUsers() {
  if (!currentUser || currentUser.role !== "admin" || loadingUsers) return;
  const generation = authGeneration;
  const request = ++usersRequest;
  loadingUsers = true;
  $("refresh-users").disabled = true;
  try { const data = await api("/api/users"); if (currentUser?.role === "admin" && generation === authGeneration) renderUsers(Array.isArray(data.users) ? data.users : []); }
  catch (error) { if (currentUser && generation === authGeneration) adminFeedback(error.message, true); }
  finally { if (request === usersRequest) { loadingUsers = false; $("refresh-users").disabled = false; } }
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const requestAuthGeneration = authGeneration;
  const { timeoutMs = 20000, ...fetchOptions } = options;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const method = (fetchOptions.method || "GET").toUpperCase();
    const headers = { Accept: "application/json", ...(fetchOptions.headers || {}) };
    if (["POST", "PATCH"].includes(method) && path !== "/api/login" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
    const response = await fetch(path, { cache: "no-store", credentials: "same-origin", ...fetchOptions, signal: controller.signal, headers });
    let data;
    try { data = await response.json(); } catch (_) { throw new Error("本地服务返回了无法读取的结果，请检查服务是否仍在运行。"); }
    if (response.status === 401) {
      if (requestAuthGeneration === authGeneration) clearAuth(path === "/api/login" ? "" : "登录已失效，请重新登录。采集记录仍保存在你的账号下。");
      const error = new Error(data.error || "登录已失效，请重新登录。");
      error.status = 401;
      throw error;
    }
    if (!response.ok) {
      const error = new Error(response.status === 403 ? `无权限：${data.error || "当前账号不能执行此操作。"}` : data.error || `请求失败（${response.status}）`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("请求超时。任务可能已创建，请先刷新结果再决定是否重试。");
    if (error instanceof TypeError) throw new Error("无法连接本地服务，请确认启动器仍在运行。");
    throw error;
  } finally { clearTimeout(timer); }
}

function localURL(value) {
  if (typeof value !== "string" || !value) return null;
  try {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin || !["http:", "https:"].includes(url.protocol)) return null;
    if (!(url.pathname.startsWith("/files/") || url.pathname.startsWith("/api/jobs/"))) return null;
    return url.href;
  } catch (_) { return null; }
}

function sourceURL(value) {
  if (typeof value !== "string" || !value) return null;
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : null; } catch (_) { return null; }
}

function download(value, text, main = false) {
  const href = localURL(value);
  if (!href) return null;
  const link = node("a", `download-link${main ? " main" : ""}`, text);
  link.href = href;
  link.setAttribute("download", "");
  return link;
}

function dateText(value) {
  if (!value) return "时间未提供";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value).slice(0, 32) : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function positiveCount(value) {
  return Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;
}

function renderMarkets() {
  const options = $("market-options");
  options.replaceChildren();
  for (const [code, label] of markets) {
    const row = node("label");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.value = code;
    checkbox.checked = selected.has(code);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selected.add(code); else selected.delete(code);
      renderMarketSelection();
    });
    row.append(checkbox, node("span", "", label));
    options.append(row);
  }
  renderMarketSelection();
}

function renderMarketSelection() {
  const labels = [...selected].map((code) => markets.get(code) || code.toUpperCase());
  $("market-summary").textContent = labels.length ? (labels.length <= 2 ? labels.join("、") : `已选 ${labels.length} 个国家 / 地区`) : "请选择采集市场";
  $("selected-markets").replaceChildren();
  for (const code of selected) {
    const button = node("button", "market-chip");
    button.type = "button";
    button.setAttribute("aria-label", `移除${markets.get(code) || code}`);
    button.append(node("span", "", markets.get(code) || code.toUpperCase()), node("span", "", "×"));
    button.addEventListener("click", () => { selected.delete(code); renderMarkets(); });
    $("selected-markets").append(button);
  }
}

function detailsBlock(key, title, defaultOpen = false) {
  const wrapper = node("details", "content-details");
  wrapper.open = expanded.has(key) || (!seenDetails.has(key) && defaultOpen);
  seenDetails.add(key);
  if (wrapper.open) expanded.add(key);
  wrapper.addEventListener("toggle", () => { if (wrapper.open) expanded.add(key); else expanded.delete(key); });
  wrapper.append(node("summary", "", title));
  const body = node("div", "content-body");
  wrapper.append(body);
  return [wrapper, body];
}

function firstText(object, keys) {
  for (const key of keys) { if (typeof object[key] === "string" && object[key].trim()) return object[key]; }
  return "";
}

function renderListing(item, key) {
  const listing = item.listing || {};
  const short = firstText(listing, ["short_description", "summary", "subtitle", "description_short"]);
  const long = firstText(listing, ["full_description", "description", "long_description", "description_long"]);
  const [wrapper, body] = detailsBlock(`${key}:listing`, "商店资料 · 长短描述");
  const facts = node("div", "listing-facts");
  const developer = listing.developer || listing.developer_name || listing.seller;
  if (developer) facts.append(node("span", "", `开发者：${developer}`));
  const score = listing.score ?? listing.rating ?? listing.average_user_rating;
  if (score !== undefined && score !== null && score !== "") facts.append(node("span", "", `评分：${score}`));
  const installs = listing.installs || listing.downloads;
  if (installs) facts.append(node("span", "", `商店下载信息：${installs}`));
  const version = listing.version || listing.current_version;
  if (version) facts.append(node("span", "", `版本：${version}`));
  const url = sourceURL(listing.url || listing.store_url || listing.source_url || listing.track_view_url);
  if (url) { const link = node("a", "", "打开原始商店页 ↗"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; facts.append(link); }
  if (facts.childNodes.length) body.append(facts);
  body.append(node("p", "description-label", "短描述 / 副标题"), node("p", "description-text", short || "商店未提供独立短描述。"));
  body.append(node("p", "description-label", "完整描述"), node("p", "description-text", long || "本次未获取到完整描述。"));
  return wrapper;
}

function renderScreenshots(item, key) {
  const screenshots = Array.isArray(item.screenshots) ? item.screenshots : [];
  const [wrapper, body] = detailsBlock(`${key}:screenshots`, `商店截图 · ${screenshots.length} 张`);
  const strip = node("div", "screenshot-strip");
  screenshots.forEach((shot, index) => {
    const url = localURL(shot.url);
    if (!url) return;
    const button = node("button", "screenshot-button");
    button.type = "button";
    button.setAttribute("aria-label", `放大查看第 ${index + 1} 张商店截图`);
    const image = node("img");
    image.src = url;
    image.alt = shot.name || `${item.title || item.app_id} · 商店截图 ${index + 1}`;
    image.loading = "lazy";
    button.append(image);
    button.addEventListener("click", () => {
      $("large-image").src = url;
      $("large-image").alt = image.alt;
      $("image-caption").textContent = image.alt;
      $("image-dialog").showModal();
    });
    strip.append(button);
  });
  body.append(strip, node("p", "screenshots-note", "点击放大。这些是商店宣传截图，不代表实际 App 页面走查。"));
  return wrapper;
}

function renderReviews(item, key) {
  const reviews = Array.isArray(item.review_samples) ? item.review_samples : [];
  const [wrapper, body] = detailsBlock(`${key}:reviews`, `用户评论 · ${positiveCount(item.review_count)} 条`, true);
  const heading = node("div", "reviews-heading");
  heading.append(node("span", "", `页面预览 ${reviews.length} 条 · 完整数据下载 CSV`), node("span", "", "保留原文，不以翻译替代证据"));
  body.append(heading);
  if (!reviews.length) { body.append(node("p", "no-content", "本次没有可展示的评论，可能未勾选评论或没有匹配筛选条件的数据。")); return wrapper; }
  const scroll = node("div", "review-table-wrap");
  const table = node("table", "review-table");
  const head = node("thead");
  const row = node("tr");
  ["评分 / 来源", "评论原文", "中文翻译"].forEach((label) => row.append(node("th", "", label)));
  head.append(row); table.append(head);
  const tbody = node("tbody");
  reviews.forEach((review) => {
    const tr = node("tr");
    const metadata = node("td");
    const score = Number(review.score);
    metadata.append(node("div", "review-score", Number.isFinite(score) ? `${score} / 5 ★` : "—"));
    metadata.append(node("div", "review-meta", `${(review.market || "—").toUpperCase()}\n${review.published_at ? String(review.published_at).slice(0, 10) : "日期未提供"}${review.version ? `\nv${review.version}` : ""}`));
    metadata.style.whiteSpace = "pre-line";
    const original = node("td");
    if (review.title) original.append(node("span", "review-title", review.title));
    original.append(node("span", "review-text", review.original_content || review.content || "（评论正文为空）"));
    const translated = node("td");
    translated.append(node("span", review.translated_content ? "review-text" : "untranslated", review.translated_content || "未翻译"));
    tr.append(metadata, original, translated); tbody.append(tr);
  });
  table.append(tbody); scroll.append(table); body.append(scroll);
  return wrapper;
}

function renderItem(item, jobId, index) {
  const wrapper = node("article", "item");
  const key = `${jobId}:${item.id || index}`;
  const heading = node("div", "item-heading");
  const title = node("div");
  title.append(node("h3", "item-title", item.title || item.app_id || `竞品 ${index + 1}`));
  title.append(node("div", "item-subtitle", `${item.platform === "app_store" ? "App Store" : item.platform === "google_play" ? "Google Play" : item.platform || "识别中"} / ${item.app_id || ""}`));
  heading.append(title, node("span", `status-tag ${item.status || "queued"}`, STATUS[item.status] || item.status || "等待采集"));
  wrapper.append(heading);
  const counts = node("div", "item-counts");
  for (const [label, value] of [["条评论", item.review_count], ["张截图", item.screenshot_count]]) { const count = node("span"); count.append(node("strong", "", positiveCount(value)), document.createTextNode(` ${label}`)); counts.append(count); }
  wrapper.append(counts);
  const warnings = Array.isArray(item.warnings) ? item.warnings : [];
  if (warnings.length) { const box = node("div", "alert warning"); warnings.forEach((warning) => box.append(node("p", "", warning))); wrapper.append(box); }
  if (item.error) wrapper.append(node("div", "alert error", item.error));
  const links = node("div", "item-links");
  const files = item.files || {};
  [[files.reviews_csv, "↓ 评论 CSV"], [files.listing_md, "↓ 商店资料 MD"], [files.listing_json, "↓ 商店 JSON"], [files.result_json, "↓ 采集 JSON"]].forEach(([url, text]) => { const link = download(url, text); if (link) links.append(link); });
  if (item.platform === "google_play" && item.app_id) {
    const screenCapture = node("button", "secondary-button", "采集此 App 实机页面");
    screenCapture.type = "button";
    screenCapture.addEventListener("click", () => window.CollectorScreens?.openForPackage(item.app_id, item.title || item.app_id));
    links.append(screenCapture);
  }
  if (links.childNodes.length) wrapper.append(links);
  const content = node("div", "item-content");
  if (item.listing && Object.keys(item.listing).length) content.append(renderListing(item, key));
  if (Array.isArray(item.screenshots) && item.screenshots.length) content.append(renderScreenshots(item, key));
  const hasReviewSamples = Array.isArray(item.review_samples) && item.review_samples.length > 0;
  if (hasReviewSamples || positiveCount(item.review_count) || (!ACTIVE.has(item.status) && Array.isArray(item.review_samples))) content.append(renderReviews(item, key));
  if (content.childNodes.length) wrapper.append(content);
  return wrapper;
}

function renderJobs() {
  const area = $("jobs");
  const focusId = document.activeElement?.id;
  area.replaceChildren();
  $("jobs-count").textContent = String(jobs.length);
  $("empty-state").hidden = jobs.length > 0;
  jobs.forEach((job) => {
    const card = node("section", "job-card");
    const header = node("div", "job-header");
    const top = node("div", "job-topline");
    const title = node("div", "job-title");
    title.append(node("span", `status-tag ${job.status}`, STATUS[job.status] || job.status), node("span", "", `${positiveCount(job.total)} 个采集项`), node("span", "job-time", dateText(job.created_at)));
    top.append(title);
    if (!ACTIVE.has(job.status)) { const zip = download(job.download_url, "↓ 下载整包 ZIP", true); if (zip) top.append(zip); }
    const info = node("div", "job-meta");
    info.append(node("span", "", `已处理 ${positiveCount(job.completed)} / ${positiveCount(job.total)}`), node("span", "job-id", `#${String(job.id).slice(0, 10)}`));
    header.append(top, info);
    if (ACTIVE.has(job.status)) { const track = node("div", "progress-track"); const fill = node("div", "progress-fill"); fill.style.width = `${job.total ? Math.min(100, positiveCount(job.completed) / positiveCount(job.total) * 100) : 0}%`; track.append(fill); header.append(track); }
    card.append(header);
    if (job.error) card.append(node("div", "alert error", job.error));
    if (Array.isArray(job.items)) job.items.forEach((item, index) => card.append(renderItem(item, job.id, index)));
    area.append(card);
  });
  if (focusId && $(focusId)) $(focusId).focus({ preventScroll: true });
}

function schedulePolling() {
  clearTimeout(pollTimer);
  pollTimer = null;
  if (currentUser && jobs.some((job) => ACTIVE.has(job.status))) pollTimer = setTimeout(() => loadJobs(), 2000);
}

async function loadJobs() {
  if (loadingJobs || !currentUser) return;
  loadingJobs = true;
  $("refresh").disabled = true;
  const revision = jobsRevision;
  const request = ++jobsRequest;
  try {
    const data = await api("/api/jobs");
    if (revision === jobsRevision) {
      jobs = Array.isArray(data.jobs) ? data.jobs : [];
      jobs.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
      renderJobs();
    }
    setAlert("results-error", "");
  } catch (error) { if (currentUser && revision === jobsRevision) setAlert("results-error", `${error.message} 可点击“刷新”重试；已启动的采集任务不会因页面断开而取消。`); }
  finally { if (request === jobsRequest) { loadingJobs = false; $("refresh").disabled = false; schedulePolling(); } }
}

function updateFilters() {
  const count = document.querySelectorAll('input[name="rating"]:checked').length + ["include-keywords", "exclude-keywords", "date-from", "date-to", "version-filter"].filter((id) => $(id).value.trim()).length + ($("reply-filter").value !== "any" ? 1 : 0) + (Number($("min-thumbs").value) > 0 ? 1 : 0);
  $("filter-count").hidden = count === 0;
  $("filter-count").textContent = `${count} 项`;
}

$("capture-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submitting || !meta || !currentUser) return;
  setAlert("form-error", "");
  const entries = $("entries").value.trim();
  const count = Number($("count").value);
  const thumbs = Number($("min-thumbs").value);
  const from = $("date-from").value;
  const to = $("date-to").value;
  if (!entries) { setAlert("form-error", "请先填写至少一个竞品链接或 App ID。"); $("entries").focus(); return; }
  if (!selected.size) { setAlert("form-error", "请至少选择一个采集国家 / 地区。"); $("market-picker").open = true; return; }
  if (!Number.isInteger(count) || count < 1 || count > 500) { setAlert("form-error", "每国评论条数应为 1–500 的整数（App Store 实际最多 100 条）。"); $("count").focus(); return; }
  if (!Number.isInteger(thumbs) || thumbs < 0) { setAlert("form-error", "最低点赞数应为不小于 0 的整数。"); return; }
  if (from && to && from > to) { setAlert("form-error", "起始日期不能晚于结束日期。"); return; }
  if (!$("collect-listing").checked && !$("collect-reviews").checked && !$("collect-screenshots").checked) { setAlert("form-error", "请至少选择一项采集内容。"); return; }
  submitting = true;
  const generation = authGeneration;
  $("submit").disabled = true;
  $("submit").firstElementChild.textContent = "正在创建采集任务…";
  const body = { entries, countries: [...selected], count_per_country: count, sort: $("sort").value, collect_listing: $("collect-listing").checked, collect_reviews: $("collect-reviews").checked, download_screenshots: $("collect-screenshots").checked, ratings: [...document.querySelectorAll('input[name="rating"]:checked')].map((element) => Number(element.value)), include_keywords: $("include-keywords").value.trim(), exclude_keywords: $("exclude-keywords").value.trim(), date_from: from, date_to: to, reply_filter: $("reply-filter").value, version_filter: $("version-filter").value.trim(), min_thumbs_up: thumbs, translate: $("translate").checked && !$("translate").disabled && $("collect-reviews").checked, translation_provider: "google" };
  try {
    const data = await api("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!currentUser || generation !== authGeneration) return;
    if (data.job) { jobsRevision += 1; jobs = [data.job, ...jobs.filter((job) => job.id !== data.job.id)]; renderJobs(); schedulePolling(); }
    else await loadJobs();
    $("results-heading").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  } catch (error) { if (currentUser && generation === authGeneration) setAlert("form-error", error.message); }
  finally { submitting = false; $("submit").disabled = !currentUser || !meta; $("submit").firstElementChild.textContent = "开始采集"; }
});

$("global-markets").addEventListener("click", () => { selected = new Set(GLOBAL_MARKETS.filter((code) => markets.has(code))); renderMarkets(); });
$("refresh").addEventListener("click", loadJobs);
$("review-filters").addEventListener("input", updateFilters);
$("collect-reviews").addEventListener("change", () => { const enabled = $("collect-reviews").checked && meta?.capabilities?.translation_google; $("translate").disabled = !enabled; if (!enabled) $("translate").checked = false; });
$("close-image").addEventListener("click", () => $("image-dialog").close());
$("image-dialog").addEventListener("click", (event) => { if (event.target === $("image-dialog")) { const rect = $("image-dialog").getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) $("image-dialog").close(); } });
$("image-dialog").addEventListener("close", () => { $("large-image").removeAttribute("src"); });

async function loadPrivateData() {
  const generation = authGeneration;
  try {
    const data = await api("/api/meta");
    if (!currentUser || generation !== authGeneration) return;
    meta = data;
    if (Array.isArray(meta.markets) && meta.markets.length) markets = new Map(meta.markets.map((market) => [String(market.code).toLowerCase(), market.label]));
    selected = new Set([...selected].filter((code) => markets.has(code)));
    if (!selected.size && markets.size) selected.add(markets.keys().next().value);
    renderMarkets();
    $("version").textContent = meta.version ? `v${meta.version}` : "";
    $("connection-dot").className = "status-dot online";
    $("connection-text").textContent = "本地服务已连接";
    $("output-path").textContent = meta.output_dir ? `保存位置：${meta.output_dir}` : "";
    $("count").value = Math.max(1, Math.min(500, Number(meta.defaults?.count_per_country) || 100));
    $("sort").value = ["newest", "relevant"].includes(meta.defaults?.sort) ? meta.defaults.sort : "newest";
    $("translate").disabled = !meta.capabilities?.translation_google;
    $("translation-status").textContent = meta.capabilities?.translation_google ? "可选 · 默认关闭" : "当前环境未安装翻译依赖";
    $("submit").disabled = false;
  } catch (error) {
    if (!currentUser || generation !== authGeneration) return;
    $("connection-dot").className = "status-dot offline";
    $("connection-text").textContent = "本地服务未连接";
    $("translation-status").textContent = "本地服务连接后可用";
    setAlert("form-error", `${error.message} 请确认启动器正在运行，然后重新加载页面。`);
  }
  if (currentUser && generation === authGeneration) await loadJobs();
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = $("login-username").value.trim();
  const password = $("login-password").value;
  if (!username || !password) { setAlert("login-error", "请输入用户名和密码。"); return; }
  $("login-submit").disabled = true;
  $("login-submit").firstElementChild.textContent = "正在登录…";
  setAlert("login-error", "");
  try { const data = await api("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) }); await enterSession(data); }
  catch (error) { setAlert("login-error", error.message); $("login-password").value = ""; }
  finally { $("login-submit").disabled = false; $("login-submit").firstElementChild.textContent = "登录"; }
});

$("logout").addEventListener("click", async () => {
  $("logout").disabled = true;
  try { await api("/api/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); clearAuth("已退出登录。"); }
  catch (error) { if (currentUser) { setAlert("results-error", `退出未成功：${error.message} 请重试，或关闭浏览器。`); } }
  finally { $("logout").disabled = false; }
});

$("change-password").addEventListener("click", () => { $("password-form").reset(); setAlert("password-error", ""); $("password-dialog").showModal(); });
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => $(button.dataset.close).close()));
$("password-dialog").addEventListener("close", () => { $("password-form").reset(); setAlert("password-error", ""); });
$("reset-dialog").addEventListener("close", () => { $("reset-form").reset(); resetUser = null; setAlert("reset-error", ""); });
$("password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const current_password = $("current-password").value;
  const new_password = $("new-password").value;
  if (!current_password || !new_password) { setAlert("password-error", "请填写当前密码和新密码。新密码需 10–128 个字符。"); return; }
  if (new_password !== $("confirm-password").value) { setAlert("password-error", "两次输入的新密码不一致。"); return; }
  $("password-submit").disabled = true;
  try { await api("/api/password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ current_password, new_password }) }); clearAuth("密码已修改，请使用新密码登录。"); }
  catch (error) { if (currentUser) setAlert("password-error", error.message); }
  finally { $("password-submit").disabled = false; }
});

$("admin-details").addEventListener("toggle", () => { if ($("admin-details").open) loadUsers(); });
$("refresh-users").addEventListener("click", loadUsers);
$("create-user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = $("new-username").value.trim();
  const password = $("new-user-password").value;
  if (!username || !password) { adminFeedback("请填写用户名和初始密码。用户名 3–64 位，仅字母、数字、_ . -；密码 10–128 个字符。", true); return; }
  $("create-user").disabled = true;
  const generation = authGeneration;
  try {
    await api("/api/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password, role: $("new-user-role").value }) });
    if (currentUser && generation === authGeneration) { $("create-user-form").reset(); adminFeedback(`账号“${username}”已创建。请将账号和初始密码直接交给本人。`); await loadUsers(); }
  } catch (error) { if (currentUser && generation === authGeneration) adminFeedback(error.message, true); }
  finally { $("new-user-password").value = ""; $("create-user").disabled = false; }
});

$("reset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!resetUser) return;
  const password = $("reset-password").value;
  if (!password) { setAlert("reset-error", "请设置 10–128 个字符的新密码。"); return; }
  const target = { ...resetUser };
  const generation = authGeneration;
  $("reset-submit").disabled = true;
  try { await api(`/api/users/${encodeURIComponent(target.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) }); if (currentUser && generation === authGeneration) { $("reset-dialog").close(); adminFeedback(`账号“${target.username}”的密码已重置。`); } }
  catch (error) { if (currentUser && generation === authGeneration) setAlert("reset-error", error.message); }
  finally { $("reset-submit").disabled = false; }
});

async function init() {
  $("new-username").maxLength = 64;
  $("new-username").placeholder = "3–64 位，字母 / 数字 / _ . -";
  $("new-user-password").placeholder = "10–128 个字符";
  $("new-password").placeholder = "10–128 个字符";
  $("reset-password").placeholder = "10–128 个字符";
  renderMarkets();
  try {
    const data = await api("/api/session");
    $("connection-dot").className = "status-dot online";
    $("connection-text").textContent = "本地服务已连接";
    if (data.user) await enterSession(data); else clearAuth("", Boolean(data.setup_required));
  } catch (error) {
    clearAuth(error.message);
    $("connection-dot").className = "status-dot offline";
    $("connection-text").textContent = "本地服务未连接";
  }
}

init();
