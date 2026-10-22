"use strict";

/* Automated, scope-bound Android walkthroughs. Device operations stay on the
   server; this view starts a task, shows evidence and handles human handoff. */
const androidCaptureDrafts = new Map();
const androidCaptureHistory = new Map();
let androidCaptureModal = null;
let androidCaptureSequence = 0;
const androidCaptureStatusNames = {
  prepared: "待开始", queued: "等待走查", running: "正在自动走查",
  paused: "等待你接管", blocked: "需要你处理", ready: "待确认入库",
  failed: "走查失败", cancelled: "已停止", interrupted: "走查已中断",
  confirmed: "已加入资料",
};

function androidCaptureScope() {
  return `${projectId || ""}:${currentVersion()?.id || ""}`;
}

function androidCaptureDraft() {
  const scope = androidCaptureScope();
  if (!androidCaptureDrafts.has(scope)) {
    androidCaptureDrafts.set(scope, { package: "", scope: "", title: "", serial: "", adb_path: "" });
  }
  return androidCaptureDrafts.get(scope);
}

function androidCaptureArray(value) {
  return Array.isArray(value) ? value : [];
}

function androidCaptureAppVersion(value) {
  if (value && typeof value === "object") {
    const name = String(value.name || "");
    const code = value.code === undefined || value.code === null || value.code === "" ? "" : String(value.code);
    return [name, code ? `(${code})` : ""].filter(Boolean).join(" ");
  }
  return value === undefined || value === null ? "" : String(value);
}

function androidCaptureBadge(status) {
  const color = ["failed", "interrupted"].includes(status) ? "bad"
    : ["running", "queued"].includes(status) ? "run"
    : ["paused", "blocked", "ready", "prepared"].includes(status) ? "warn" : "";
  return `<span class="tag ${color}">${E(androidCaptureStatusNames[status] || status || "未开始")}</span>`;
}

function androidCaptureFileUrl(session, file) {
  if (!session?.id || !file) return "";
  const prefix = `/api/android-capture/sessions/${encodeURIComponent(session.id)}/file`;
  if (typeof file.path === "string" && file.path) return `${prefix}?path=${encodeURIComponent(file.path)}`;
  // Only accept the session's own local asset route when the server supplies URL.
  return typeof file.url === "string" && file.url.startsWith(`${prefix}?`) ? file.url : "";
}

function androidCaptureSelectSerial(devices, preferred = "") {
  const connected = androidCaptureArray(devices).filter((device) => device.state === "device");
  if (connected.some((device) => device.serial === preferred)) return preferred;
  return connected.length === 1 ? connected[0].serial : "";
}

function androidCaptureHistoryHtml(sessions) {
  if (!sessions.length) return '<div class="empty compact">还没有实机走查。给出 App 和范围后，工作台会自动操作设备、记录截图并按模块生成流程拼图。</div>';
  return sessions.slice(0, 12).map((session) => {
    const appVersion = androidCaptureAppVersion(session.app_version);
    const count = Number.isFinite(Number(session.composite_count)) && session.composite_count !== null ? Math.max(0, Number(session.composite_count)) : androidCaptureArray(session.composites).length;
    const facts = [session.package, appVersion ? `App ${appVersion}` : "", date(session.created), `${count} 张模块拼图`].filter(Boolean).join(" · ");
    return `<article class="row android-capture-history-row"><div class="row-main"><h3>${E(session.title || session.package || "Android 实机走查")}</h3><p>${E(facts)}</p>${session.pause_reason ? `<small>${E(session.pause_reason)}</small>` : ""}</div>${androidCaptureBadge(session.status)}<button class="small" data-android-capture-session="${E(session.id)}">${["running", "queued", "paused", "blocked"].includes(session.status) ? "查看进度" : "查看结果"}</button></article>`;
  }).join("");
}

async function androidCaptureRenderHistory(force = false) {
  const root = $("#android-capture-history");
  if (!root || !projectId) return;
  const scope = androidCaptureScope();
  const project = projectId;
  const version = currentVersion()?.id || "";
  const cached = androidCaptureHistory.get(scope);
  root.dataset.scope = scope;
  if (cached && !force && Date.now() - cached.time < 2500) {
    root.innerHTML = androidCaptureHistoryHtml(cached.sessions);
    return;
  }
  root.innerHTML = '<p class="muted" role="status">正在读取实机走查记录…</p>';
  try {
    const result = await api(`/api/android-capture/sessions?project_id=${encodeURIComponent(project)}&version_id=${encodeURIComponent(version)}`);
    if (androidCaptureScope() !== scope || $("#android-capture-history") !== root) return;
    const sessions = androidCaptureArray(result.sessions);
    androidCaptureHistory.set(scope, { time: Date.now(), sessions });
    root.innerHTML = androidCaptureHistoryHtml(sessions);
  } catch (err) {
    if (androidCaptureScope() === scope && $("#android-capture-history") === root) {
      root.innerHTML = `<p class="scrape-error" role="status">${E(err.message)} <button class="small" data-android-capture-history-refresh>重新读取</button></p>`;
    }
  }
}

function androidCaptureStopPolling() {
  if (androidCaptureModal?.timer) clearTimeout(androidCaptureModal.timer);
  if (androidCaptureModal) androidCaptureModal.timer = null;
}

function androidCaptureIsCurrent(context) {
  const root = $("#android-capture-console");
  if (androidCaptureModal !== context || !root || root.dataset.instance !== String(context.token) || !$("#modal")?.open) return false;
  if (androidCaptureScope() !== context.scope) {
    androidCaptureStopPolling();
    close();
    toast("项目范围已切换，已关闭走查窗口。任务仍保留在原项目范围中。");
    return false;
  }
  return true;
}

function androidCaptureSchedule(context) {
  androidCaptureStopPolling();
  if (!androidCaptureIsCurrent(context) || context.busy || !["queued", "running"].includes(context.session?.status)) return;
  context.timer = setTimeout(async () => {
    if (!androidCaptureIsCurrent(context)) return;
    const request = ++context.request;
    try {
      const session = await api(`/api/android-capture/sessions/${encodeURIComponent(context.session.id)}`);
      if (!androidCaptureIsCurrent(context) || context.request !== request) return;
      context.session = session;
      context.error = "";
      androidCaptureRenderSession(context);
    } catch (err) {
      if (!androidCaptureIsCurrent(context) || context.request !== request) return;
      context.error = `连接暂时中断，正在重试。${err.message}`;
      androidCaptureRenderSession(context);
    } finally {
      if (androidCaptureIsCurrent(context) && context.request === request) androidCaptureSchedule(context);
    }
  }, 2500);
}

async function openAndroidCapture(sessionId = "", options = {}) {
  if (!projectId) return toast("请先选择项目");
  androidCaptureStopPolling();
  const context = {
    token: ++androidCaptureSequence, scope: androidCaptureScope(),
    project: projectId, version: currentVersion()?.id || "", draft: androidCaptureDraft(),
    request: 0, busy: false, loading: true, settings: null, devices: [], session: null, error: "", timer: null,
  };
  context.competitorId = options.competitor_id || "";
  if (options.package) context.draft = {...context.draft,package:options.package,title:options.title || context.draft.title};
  androidCaptureModal = context;
  modal("Android 实机走查", `<div id="android-capture-console" class="android-capture-console" data-instance="${context.token}"><div class="empty" role="status">正在准备实机走查…</div></div>`);
  if (sessionId) {
    try {
      const session = await api(`/api/android-capture/sessions/${encodeURIComponent(sessionId)}`);
      if (!androidCaptureIsCurrent(context)) return;
      if (session.project_id !== context.project || (session.version_id || "") !== context.version) throw Error("这条走查不属于当前项目版本，请切换范围后查看。");
      context.session = session;
      context.loading = false;
      androidCaptureRenderSession(context);
      androidCaptureSchedule(context);
    } catch (err) {
      if (!androidCaptureIsCurrent(context)) return;
      context.error = err.message;
      context.loading = false;
      $("#android-capture-console").innerHTML = `<h2>无法读取这条走查</h2><p class="scrape-error" role="alert">${E(err.message)}</p><button type="button" data-close-modal>关闭</button>`;
    }
    return;
  }
  await androidCaptureLoadSetup(context);
}

async function androidCaptureLoadSetup(context) {
  context.loading = true;
  context.error = "";
  androidCaptureRenderForm(context);
  const results = await Promise.allSettled([
    api("/api/android-capture/settings"), api("/api/android-capture/devices"),
  ]);
  if (!androidCaptureIsCurrent(context)) return;
  if (results[0].status === "fulfilled") {
    context.settings = results[0].value;
    context.draft.adb_path = context.settings.adb_path || context.draft.adb_path;
  } else context.error = results[0].reason.message;
  if (results[1].status === "fulfilled") context.devices = androidCaptureArray(results[1].value.devices);
  else context.error = [context.error, results[1].reason.message].filter(Boolean).join("；");
  context.draft.serial = androidCaptureSelectSerial(context.devices, context.draft.serial);
  context.loading = false;
  androidCaptureRenderForm(context);
}

function androidCaptureReady(context) {
  return Boolean(context.settings?.adb_available && context.settings?.codex_available && context.settings?.skill_available && context.draft.serial && !context.loading && !context.busy);
}

function androidCaptureRenderForm(context) {
  if (!androidCaptureIsCurrent(context)) return;
  const settings = context.settings || {};
  const devices = context.devices;
  const connected = devices.filter((device) => device.state === "device");
  const deviceOptions = connected.map((device) => `<option value="${E(device.serial)}" ${context.draft.serial === device.serial ? "selected" : ""}>${E(device.model || "Android 设备")} · ${E(device.serial)}</option>`).join("");
  const unavailable = devices.filter((device) => device.state !== "device").map((device) => `${device.model || device.serial}：${({ unauthorized: "请在手机上允许 USB 调试", offline: "设备离线，请重新连接" })[device.state] || device.state}`).join("；");
  const deviceHint = context.loading ? "正在检测设备…" : connected.length === 1 ? "已自动选择唯一可用设备。" : connected.length > 1 ? "检测到多台设备，请选择本次走查使用的设备。" : "请连接 Android 手机或启动模拟器，启用 USB 调试，并在设备上允许连接。";
  $("#android-capture-console").innerHTML = `<div class="android-capture-intro"><span class="eyebrow">从真实页面到模块流程图</span><h2>给出 App 和范围，自动完成走查。</h2><p class="muted">沿用实机截屏流程：确认页面、操作 App、记录状态与分支，最后按模块生成 PNG 拼图。遇到需要你处理的步骤时会暂停。</p><span class="tag">归属：${E(currentVersion()?.name || "产品级工作")}</span></div>
    ${context.error ? `<div class="banner android-capture-error" role="alert">${E(context.error)}</div>` : ""}
    <form id="android-capture-form" class="android-capture-form"><div class="grid"><div><label for="capture-package">App 包名</label><input id="capture-package" name="package" required maxlength="240" placeholder="例如：com.example.app" value="${E(context.draft.package)}" ${context.busy ? "disabled" : ""}><small>目标 App 需要已安装在所选设备上。</small></div><div><label for="capture-title">走查标题（可选）</label><input id="capture-title" name="title" maxlength="180" placeholder="例如：竞品首轮完整走查" value="${E(context.draft.title)}" ${context.busy ? "disabled" : ""}></div></div><div><label for="capture-scope">这次需要走查什么</label><textarea id="capture-scope" name="scope" required maxlength="12000" rows="5" placeholder="例如：走查首次启动、首页、主要功能、设置、广告和订阅入口；按功能模块拼图，记录异常和未覆盖分支。" ${context.busy ? "disabled" : ""}>${E(context.draft.scope)}</textarea></div>
    <section class="android-device-section"><div class="section-title"><div><h3>使用哪台设备</h3><p class="muted" id="capture-device-hint">${E(deviceHint)}</p></div><button type="button" id="capture-refresh-devices" class="small" ${context.busy || context.loading ? "disabled" : ""}>重新检测</button></div><label class="visually-hidden" for="capture-serial">走查设备</label><select id="capture-serial" ${connected.length < 2 || context.busy ? "disabled" : ""}><option value="">${connected.length ? "选择一台设备" : "尚未发现可用设备"}</option>${deviceOptions}</select>${unavailable ? `<p class="scrape-error">${E(unavailable)}</p>` : ""}</section>
    <div class="android-capture-environment" role="status">${context.loading ? "正在检查运行环境…" : `<span>${settings.adb_available ? "✓" : "○"} ADB</span><span>${settings.codex_available ? "✓" : "○"} Codex</span><span>${settings.skill_available ? "✓" : "○"} 实机截屏 Skill</span>${settings.message ? `<small>${E(settings.message)}</small>` : ""}`}</div>
    <div class="android-capture-submit"><small>结果先保存在走查记录中；预览并确认后，才加入当前项目资料。</small><div class="actions"><button class="primary" type="submit" ${androidCaptureReady(context) ? "" : "disabled"}>${context.busy ? "正在开始…" : "开始自动走查"}</button><button type="button" data-close-modal>关闭</button></div></div></form>
    <details class="android-capture-settings" ${!settings.adb_available && !context.loading ? "open" : ""}><summary>ADB 路径配置</summary><form id="capture-adb-form"><label for="capture-adb-path">adb.exe 完整路径</label><div class="searchbar"><input id="capture-adb-path" required maxlength="1000" placeholder="例如：C:\\Android\\platform-tools\\adb.exe" value="${E(context.draft.adb_path)}"><button type="submit" class="small" ${context.busy || context.loading ? "disabled" : ""}>保存并检测</button></div></form></details>`;
  ["package", "title", "scope", "serial"].forEach((name) => {
    const input = $(`#capture-${name}`);
    input.oninput = () => { context.draft[name] = input.value; };
    if (name === "serial") input.onchange = () => { context.draft.serial = input.value; androidCaptureRenderForm(context); };
  });
  $("#capture-adb-path").oninput = (event) => { context.draft.adb_path = event.target.value; };
  $("#capture-refresh-devices").onclick = () => androidCaptureLoadSetup(context);
  $("#capture-adb-form").onsubmit = async (event) => {
    event.preventDefault();
    if (context.busy || context.loading) return;
    context.busy = true;
    context.error = "";
    androidCaptureRenderForm(context);
    try {
      await api("/api/android-capture/settings", { adb_path: context.draft.adb_path.trim() });
      if (!androidCaptureIsCurrent(context)) return;
      context.busy = false;
      await androidCaptureLoadSetup(context);
    } catch (err) {
      if (!androidCaptureIsCurrent(context)) return;
      context.busy = false;
      context.error = err.message;
      androidCaptureRenderForm(context);
    }
  };
  $("#android-capture-form").onsubmit = (event) => {
    event.preventDefault();
    androidCaptureCreate(context);
  };
}

async function androidCaptureCreate(context) {
  if (!androidCaptureIsCurrent(context) || !androidCaptureReady(context)) return;
  const payload = { project_id: context.project, version_id: context.version, package: context.draft.package.trim(), scope: context.draft.scope.trim(), title: context.draft.title.trim(), serial: context.draft.serial };
  if (context.competitorId) payload.competitor_id = context.competitorId;
  if (!payload.package || !payload.scope) return;
  context.busy = true;
  context.error = "";
  androidCaptureRenderForm(context);
  try {
    context.session = await api("/api/android-capture/sessions", payload);
    if (!androidCaptureIsCurrent(context)) return;
    androidCaptureRenderSession(context);
    context.session = await api(`/api/android-capture/sessions/${encodeURIComponent(context.session.id)}/start`, {});
    if (!androidCaptureIsCurrent(context)) return;
  } catch (err) {
    if (!androidCaptureIsCurrent(context)) return;
    context.error = err.message;
  } finally {
    if (androidCaptureIsCurrent(context)) {
      context.busy = false;
      if (context.session) {
        androidCaptureRenderSession(context);
        androidCaptureSchedule(context);
      } else androidCaptureRenderForm(context);
      androidCaptureHistory.delete(context.scope);
      androidCaptureRenderHistory(true);
    }
  }
}

function androidCaptureRenderSession(context) {
  if (!androidCaptureIsCurrent(context)) return;
  const session = context.session;
  const appVersion = androidCaptureAppVersion(session.app_version);
  const observations = androidCaptureArray(session.observations);
  const composites = androidCaptureArray(session.composites);
  const modules = androidCaptureArray(session.modules);
  const progress = androidCaptureArray(session.progress).slice(-15);
  const current = observations.at(-1);
  const currentUrl = androidCaptureFileUrl(session, current);
  const running = ["queued", "running"].includes(session.status);
  const needsHandoff = ["paused", "blocked", "interrupted"].includes(session.status);
  const canCancel = ["prepared", "queued", "running", "paused", "blocked", "interrupted"].includes(session.status);
  const canExport = ["ready", "confirmed", "failed", "cancelled", "interrupted", "blocked", "paused"].includes(session.status);
  const canResume = ["paused", "blocked", "interrupted", "failed", "cancelled"].includes(session.status);
  const canConfirmPartial = ["paused", "blocked"].includes(session.status) && (observations.length > 0 || composites.length > 0);
  const moduleNames = { pending: "待走查", running: "走查中", completed: "已覆盖", covered: "已覆盖", ready: "已完成", partial: "部分覆盖", blocked: "未完成", skipped: "未覆盖", failed: "失败" };
  const moduleCards = modules.map((item) => `<li><div><strong>${E(item.title || item.id || "未命名模块")}</strong><span class="tag">${E(moduleNames[item.status] || item.status || "待走查")}</span></div>${item.reason ? `<p>${E(item.reason)}</p>` : ""}</li>`).join("");
  const previewCards = composites.map((item) => {
    const url = androidCaptureFileUrl(session, item);
    return `<article class="android-composite-card"><h4>${E(item.title || item.module_id || "模块流程拼图")}</h4>${url ? `<a href="${E(url)}" target="_blank" rel="noopener" aria-label="打开 ${E(item.title || "模块拼图")} 原图"><img class="document-image" loading="lazy" src="${E(url)}" alt="${E(item.title || "模块流程拼图")}"></a><a class="button-link small" href="${E(url)}" target="_blank" rel="noopener">查看原图</a>` : '<p class="muted">图片路径尚未提供。</p>'}</article>`;
  }).join("");
  const summary = typeof session.summary === "string" ? session.summary : "";
  $("#android-capture-console").innerHTML = `<div class="android-capture-session-heading"><div><span class="eyebrow">ANDROID WALKTHROUGH</span><h2>${E(session.title || session.package || "Android 实机走查")}</h2><p class="muted">${E([session.package, appVersion ? `App ${appVersion}` : "", session.serial, date(session.created)].filter(Boolean).join(" · "))}</p></div>${androidCaptureBadge(session.status)}</div>
    ${context.error ? `<div class="banner android-capture-error" role="alert">${E(context.error)}</div>` : ""}
    ${needsHandoff ? `<section class="android-capture-handoff" role="status"><h3>${session.status === "interrupted" ? "走查中断，可从已有记录继续" : "在手机上处理后，继续走查"}</h3><p>${E(session.pause_reason || session.error || "请查看设备当前页面，完成需要手动处理的步骤。")}</p><small>保留当前 App 页面；处理完成后点击“继续自动走查”，工作台会重新观察设备并接着执行。</small></section>` : session.error ? `<div class="banner android-capture-error" role="alert">${E(session.error)}</div>` : ""}
    <div class="android-capture-stats"><div><b>${observations.length}</b><span>页面截图</span></div><div><b>${modules.length}</b><span>走查模块</span></div><div><b>${composites.length}</b><span>模块 PNG</span></div></div>
    <div class="android-capture-live-grid"><section class="android-capture-progress"><h3>${running ? "走查进度" : "执行记录"}</h3>${running ? '<p class="help" role="status">正在根据范围自动操作 App 并记录页面。可以关闭窗口，稍后从资料页查看进度。</p>' : ""}${progress.length ? `<ol>${progress.map((item) => `<li>${item.time ? `<time>${E(date(item.time))}</time>` : ""}<span>${E(item.message || "")}</span></li>`).join("")}</ol>` : `<div class="empty compact">${session.status === "prepared" ? "任务已准备，可以开始自动走查。" : "等待第一条执行记录。"}</div>`}<details><summary>本次走查范围</summary><p class="android-capture-scope">${E(session.scope || "未提供")}</p></details></section><section class="android-capture-current"><h3>最近记录的页面</h3>${currentUrl ? `<a href="${E(currentUrl)}" target="_blank" rel="noopener"><img class="document-image" src="${E(currentUrl)}" alt="最近记录的 App 页面"></a>${current?.captured_at ? `<small>${E(date(current.captured_at))}</small>` : ""}` : '<div class="empty compact">开始走查后，页面截图会出现在这里。</div>'}</section></div>
    ${modules.length ? `<section class="android-capture-modules"><h3>模块覆盖与缺口</h3><ul>${moduleCards}</ul></section>` : ""}
    ${summary ? `<section class="android-capture-summary"><h3>走查说明</h3><p>${E(summary)}</p></section>` : ""}
    ${composites.length ? `<section class="android-capture-composites"><div class="section-title"><div><h3>模块流程拼图</h3><p class="muted">按模块核对流程顺序、页面状态和未覆盖分支后，再确认加入项目资料。</p></div></div><div class="android-composite-grid">${previewCards}</div></section>` : ""}
    ${session.status === "ready" ? '<p class="help">走查已结束。当前结果仍在待确认区，确认后才会进入项目资料和后续分析。</p>' : ""}${canConfirmPartial ? '<p class="help">这轮走查尚未完成。可以继续补采，或先确认当前部分证据；本次范围和模块缺口会一同保留。</p>' : ""}${session.status === "confirmed" ? `<p class="help">已加入当前项目资料，共 ${androidCaptureArray(session.document_ids).length} 份。可在资料库查看并用于后续分析。</p>` : ""}
    <div class="android-capture-session-actions"><div class="actions">${session.status === "prepared" ? `<button class="primary" data-capture-operation="start" ${context.busy ? "disabled" : ""}>开始自动走查</button>` : ""}${canResume ? `<button class="primary" data-capture-operation="resume" ${context.busy ? "disabled" : ""}>${session.status === "failed" ? "重新尝试走查" : "继续自动走查"}</button>` : ""}${session.status === "ready" ? `<button class="primary" data-capture-operation="confirm" ${context.busy ? "disabled" : ""}>确认加入项目资料</button>` : ""}${canConfirmPartial ? `<button data-capture-operation="confirm" ${context.busy ? "disabled" : ""}>确认当前部分证据</button>` : ""}${canExport ? `<a class="button-link" href="/api/android-capture/sessions/${encodeURIComponent(session.id)}/export">下载完整 ZIP</a>` : ""}${canCancel ? `<button class="danger" data-capture-operation="cancel" ${context.busy ? "disabled" : ""}>停止走查</button>` : ""}<button type="button" data-close-modal>关闭</button></div>${context.busy ? '<small role="status">正在处理…</small>' : ""}</div>`;
  $("#android-capture-console").querySelectorAll("[data-capture-operation]").forEach((button) => {
    button.onclick = () => androidCaptureOperation(context, button.dataset.captureOperation);
  });
}

async function androidCaptureOperation(context, operation) {
  if (!androidCaptureIsCurrent(context) || context.busy) return;
  context.busy = true;
  context.error = "";
  context.request += 1; // Ignore an older polling response after an explicit action.
  androidCaptureStopPolling();
  androidCaptureRenderSession(context);
  try {
    const result = await api(`/api/android-capture/sessions/${encodeURIComponent(context.session.id)}/${operation}`, {});
    if (!androidCaptureIsCurrent(context)) return;
    context.session = { ...context.session, ...result };
    androidCaptureHistory.delete(context.scope);
    if (operation === "confirm") {
      await refresh();
      if (!androidCaptureIsCurrent(context)) return;
      toast("实机走查结果已加入当前项目资料");
    } else if (operation === "cancel") toast("已停止走查，已有截图与记录仍保留");
    androidCaptureRenderHistory(true);
  } catch (err) {
    if (androidCaptureIsCurrent(context)) context.error = err.message;
  } finally {
    if (androidCaptureIsCurrent(context)) {
      context.busy = false;
      androidCaptureRenderSession(context);
      androidCaptureSchedule(context);
    }
  }
}

$("#modal").addEventListener("close", () => {
  if (!androidCaptureModal) return;
  const scope = androidCaptureModal.scope;
  androidCaptureStopPolling();
  androidCaptureModal = null;
  androidCaptureHistory.delete(scope);
  androidCaptureRenderHistory(true);
});
