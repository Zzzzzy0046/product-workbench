"use strict";

// A capture is never started, resumed or observed by loading this page.
// Device actions are explicit and are bound to the latest observation ID.
(() => {
  let captureMeta = null;
  let captures = [];
  let installedApps = [];
  let requestedPackage = "";
  let capture = null;
  let busy = false;
  let capabilityLoading = false;
  let detailRequest = 0;
  let listRequest = 0;
  let deviceRequest = 0;
  let appsRequest = 0;
  let operationRequest = 0;
  let loadedGeneration = -1;

  function sameSession(generation) { return Boolean(currentUser) && authGeneration === generation; }
  function errorMessage(message) { setAlert("screens-error", message); }
  function ownerCanControl() {
    return Boolean(currentUser && capture && String(capture.owner_id) === String(currentUser.id) && capture.can_control !== false);
  }
  function activeCapture() { return ownerCanControl() && capture.status === "active"; }
  function adminCanRelease() { return Boolean(currentUser?.role === "admin" && capture?.status === "active"); }
  function canAct() {
    const observation = capture?.observation;
    return activeCapture() && Boolean(observation?.id) && observation.actionable === true;
  }
  function captureURL(value, selectedCapture = capture) {
    if (!selectedCapture?.id || typeof value !== "string" || !value) return null;
    try {
      const url = new URL(value, location.origin);
      const prefix = `/api/captures/${encodeURIComponent(selectedCapture.id)}/`;
      if (url.origin !== location.origin || !["http:", "https:"].includes(url.protocol)) return null;
      if (!(url.pathname.startsWith(`${prefix}files/`) || url.pathname === `${prefix}archive`)) return null;
      return url.href;
    } catch (_) { return null; }
  }
  function captureLink(value, text, selectedCapture = capture) {
    const href = captureURL(value, selectedCapture);
    if (!href) return null;
    const link = node("a", "download-link", text);
    link.href = href;
    link.setAttribute("download", "");
    return link;
  }
  function imageButton(url, alt, className = "screens-thumb") {
    const safeURL = captureURL(url);
    if (!safeURL) return null;
    const button = node("button", className);
    button.type = "button";
    button.setAttribute("aria-label", `放大${alt}`);
    const image = node("img");
    image.src = safeURL;
    image.alt = alt;
    image.loading = "lazy";
    button.append(image);
    button.addEventListener("click", () => {
      if (!currentUser) return;
      $("large-image").src = safeURL;
      $("large-image").alt = alt;
      $("image-caption").textContent = alt;
      $("image-dialog").showModal();
    });
    return button;
  }

  function selectPane(name) {
    if (!currentUser) return;
    const screens = name === "screens";
    $("workspace").hidden = screens;
    $("screens-workspace").hidden = !screens;
    for (const [id, selectedPane] of [["nav-store", !screens], ["nav-screens", screens]]) {
      $(id).classList.toggle("active", selectedPane);
      $(id).setAttribute("aria-pressed", String(selectedPane));
    }
    if (screens && loadedGeneration !== authGeneration) loadCaptureData();
  }

  function clearCurrent() {
    capture = null;
    $("screens-current").hidden = true;
    $("screens-empty").hidden = false;
    $("screens-image").removeAttribute("src");
    $("screens-image").hidden = true;
    $("screens-image-empty").hidden = false;
    $("screens-image-open").disabled = true;
    for (const id of ["screens-current-title", "screens-current-meta", "screens-observation-time", "screens-operation-status"]) $(id).textContent = "";
    for (const id of ["screens-session-actions", "screens-elements", "screens-saved", "screens-flows", "screens-module-options"]) $(id).replaceChildren();
    $("screens-label-form").reset();
    setAlert("screens-observation-note", "");
    $("screens-readonly").hidden = true;
  }

  function reset() {
    detailRequest += 1; listRequest += 1; deviceRequest += 1; appsRequest += 1; operationRequest += 1;
    captureMeta = null; captures = []; installedApps = []; requestedPackage = ""; busy = false; capabilityLoading = false; loadedGeneration = -1;
    clearCurrent();
    $("screens-workspace").hidden = true;
    $("screens-create-form").reset();
    $("screens-device").replaceChildren(new Option("先查找设备", ""));
    $("screens-app").replaceChildren(new Option("先选择设备", ""));
    $("screens-device").disabled = true;
    $("screens-app").disabled = true;
    $("screens-app-search").disabled = true;
    $("screens-sessions").replaceChildren();
    $("screens-capability").textContent = "打开后检查本机截图能力。";
    $("nav-store").classList.add("active");
    $("nav-store").setAttribute("aria-pressed", "true");
    $("nav-screens").classList.remove("active");
    $("nav-screens").setAttribute("aria-pressed", "false");
    errorMessage("");
    updateControls();
  }

  function updateControls() {
    const available = captureMeta?.available === true;
    $("screens-devices-refresh").disabled = busy || !currentUser || !available;
    $("screens-create").disabled = busy || !currentUser || !available || !$("screens-device").value || !$("screens-app").value;
    $("screens-launch").disabled = busy || !activeCapture() || !available;
    $("screens-observe").disabled = busy || !activeCapture() || !available;
    $("screens-label").disabled = busy || !activeCapture() || !capture?.observation?.id || capture?.observation?.labelled === true || Boolean(capture?.error) || capture?.observation?.uncertain === true;
    $("screens-label").textContent = capture?.observation?.labelled === true ? "当前截图已保存" : "保存当前页到模块";
    $("screens-export").disabled = busy || !ownerCanControl() || !(capture?.states?.length);
    for (const button of document.querySelectorAll("[data-screen-action], [data-screen-swipe], .screens-element")) button.disabled = busy || !canAct() || button.dataset.blocked === "true";
    for (const button of $("screens-session-actions").querySelectorAll("button")) button.disabled = busy;
    $("screens-create").firstElementChild.textContent = busy ? "正在处理设备操作…" : "创建截图任务";
  }

  async function loadCaptureData() {
    if (!currentUser || capabilityLoading) return;
    const generation = authGeneration;
    capabilityLoading = true;
    try {
      const data = await api("/api/capture/meta");
      if (!sameSession(generation)) return;
      captureMeta = data;
      loadedGeneration = generation;
      $("screens-capability").className = `alert ${data.available ? "success" : "warning"}`;
      $("screens-capability").textContent = data.message || (data.available ? "本机截图能力已就绪。点击“查找已连接设备”开始。" : "本机截图能力暂不可用。请先安装 Android platform-tools，并配置 ADB；刷新页面后重试。");
      if (Array.isArray(data.instructions)) for (const instruction of data.instructions) $("screens-capability").append(node("p", "", instruction));
      else if (typeof data.instructions === "string" && data.instructions) $("screens-capability").append(node("p", "", data.instructions));
    } catch (error) { if (sameSession(generation)) { loadedGeneration = -1; errorMessage(error.message); } }
    finally { if (sameSession(generation)) { capabilityLoading = false; updateControls(); } }
    if (sameSession(generation)) await loadCaptures();
  }

  function renderCaptures() {
    const area = $("screens-sessions");
    area.replaceChildren();
    captures.forEach((item) => {
      const button = node("button", `screens-session${capture?.id === item.id ? " selected" : ""}`);
      button.type = "button";
      button.append(node("strong", "", item.title || item.package || "未命名截图任务"), node("span", "", `${item.status === "active" ? "使用中" : "已释放设备"} · ${dateText(item.updated_at || item.created_at)}`));
      if (currentUser?.role === "admin" && String(item.owner_id) !== String(currentUser.id)) button.append(node("span", "", `创建者：${item.owner_name || "其他成员"} · 只读`));
      button.addEventListener("click", () => selectCapture(item.id));
      area.append(button);
    });
    if (!captures.length) area.append(node("p", "field-note", "暂无实机截图任务。创建任务不会自动打开或操作 App。"));
  }

  async function loadCaptures() {
    if (!currentUser) return;
    const generation = authGeneration;
    const request = ++listRequest;
    $("screens-refresh").disabled = true;
    try {
      const data = await api("/api/captures");
      if (!sameSession(generation) || request !== listRequest) return;
      captures = Array.isArray(data.captures) ? data.captures : [];
      captures.sort((a, b) => String(b.updated_at || b.created_at).localeCompare(String(a.updated_at || a.created_at)));
      renderCaptures();
    } catch (error) { if (sameSession(generation) && request === listRequest) errorMessage(error.message); }
    finally { if (sameSession(generation) && request === listRequest) $("screens-refresh").disabled = false; }
  }

  async function selectCapture(id) {
    if (!currentUser || busy) return;
    const generation = authGeneration;
    const request = ++detailRequest;
    clearCurrent();
    errorMessage("");
    try {
      const data = await api(`/api/captures/${encodeURIComponent(id)}`);
      if (!sameSession(generation) || request !== detailRequest) return;
      capture = data.capture;
      renderCapture();
      renderCaptures();
    } catch (error) { if (sameSession(generation) && request === detailRequest) errorMessage(error.message); }
  }

  function renderSaved() {
    const area = $("screens-saved");
    area.replaceChildren();
    const modules = Array.isArray(capture.modules) ? capture.modules : [];
    const pages = Array.isArray(capture.pages) ? capture.pages : [];
    const states = Array.isArray(capture.states) ? capture.states : [];
    $("screens-module-options").replaceChildren();
    modules.forEach((module) => {
      const option = node("option"); option.value = module.title || ""; $("screens-module-options").append(option);
      const section = node("section", "screens-module");
      section.append(node("h4", "", module.title || "未命名模块"));
      const strip = node("div", "screens-state-strip");
      const modulePages = pages.filter((page) => page.module_id === module.id);
      states.filter((state) => modulePages.some((page) => page.id === state.page_id) || state.module_id === module.id).forEach((state) => {
        const page = modulePages.find((item) => item.id === state.page_id);
        const card = node("figure", "screens-state-card");
        const caption = `${page?.title || state.page_title || "页面"}${state.title ? ` · ${state.title}` : ""}`;
        const image = imageButton(state.screenshot_url, caption);
        if (image) card.append(image);
        card.append(node("figcaption", "", caption));
        strip.append(card);
      });
      if (!strip.childNodes.length) strip.append(node("p", "field-note", module.reason || "此模块尚未保存截图。"));
      section.append(strip); area.append(section);
    });
    if (!modules.length) area.append(node("p", "no-content", "还没有整理页面。获取截图后，在右侧填写模块和页面名称。"));
    const flows = $("screens-flows");
    flows.replaceChildren();
    if (capture.flows_stale) flows.append(node("div", "alert warning", "页面或流程已更新，下面的流程图是上次生成的版本，请重新生成。"));
    for (const flow of Array.isArray(capture.flows) ? capture.flows : []) {
      const row = node("section", "screens-flow");
      const title = flow.title || "模块流程图";
      const top = node("div", "screens-flow-heading"); top.append(node("h4", "", title));
      const link = captureLink(flow.url, "↓ 下载流程 PNG"); if (link) top.append(link);
      row.append(top);
      const image = imageButton(flow.url, `${title} · 实际截图流程`, "screens-flow-preview");
      if (image) row.append(image);
      flows.append(row);
    }
  }

  function renderCapture() {
    if (!capture || !currentUser) { clearCurrent(); return; }
    $("screens-current").hidden = false;
    $("screens-empty").hidden = true;
    $("screens-current-title").textContent = capture.title || capture.package;
    $("screens-current-meta").textContent = `${capture.package} · ${capture.serial} · ${capture.status === "active" ? "设备使用中" : "设备已释放"}`;
    $("screens-readonly").hidden = ownerCanControl();
    const actions = $("screens-session-actions"); actions.replaceChildren();
    if (ownerCanControl()) {
      const release = node("button", "secondary-button", capture.status === "active" ? "释放设备" : "继续此任务");
      release.type = "button";
      release.addEventListener("click", () => operate(capture.status === "active" ? "release" : "resume"));
      actions.append(release);
    } else if (adminCanRelease()) {
      const release = node("button", "secondary-button", "释放设备占用");
      release.type = "button";
      release.title = "只解除任务对设备的占用，不点击或控制手机";
      release.addEventListener("click", () => {
        if (confirm("解除此任务对设备的占用？这不会点击或操作手机。原创建者需重新继续任务才能操作。")) operate("release");
      });
      actions.append(release);
    }
    const zip = captureLink(capture.download_url || `/api/captures/${encodeURIComponent(capture.id)}/archive`, "↓ 下载截图与流程 ZIP");
    if (zip) actions.append(zip);
    const observation = capture.observation || {};
    const screenshotURL = captureURL(observation.screenshot_url);
    if (screenshotURL) {
      $("screens-image").src = screenshotURL;
      $("screens-image").hidden = false;
      $("screens-image-empty").hidden = true;
      $("screens-image-open").disabled = false;
    } else {
      $("screens-image").removeAttribute("src");
      $("screens-image").hidden = true;
      $("screens-image-empty").hidden = false;
      $("screens-image-open").disabled = true;
    }
    $("screens-observation-time").textContent = observation.id ? `${observation.activity || "当前页面"} · 截图 ${String(observation.id).slice(0, 12)}` : "点击“打开目标 App”，或手动打开后点击“获取当前截图”。";
    const notes = [capture.warning, capture.error, observation.ui_error, observation.message].filter((item) => typeof item === "string" && item);
    if (capture.status === "active" && observation.id && !observation.actionable) notes.push("当前页面不可通过本工具操作。请在手机上处理后，再获取当前截图；已获得的截图仍可整理。");
    if (capture.status !== "active" && !notes.length) notes.push("此任务已释放设备。点击“继续此任务”后，先获取新截图再操作。");
    setAlert("screens-observation-note", notes.join("\n"));
    const elements = $("screens-elements"); elements.replaceChildren();
    for (const clickable of Array.isArray(observation.clickables) ? observation.clickables : []) {
      if (!Number.isInteger(clickable.index)) continue;
      const label = clickable.text || clickable.content_desc || clickable["content-desc"] || clickable.resource_id || `元素 ${clickable.index}`;
      const button = node("button", "screens-element"); button.type = "button";
      button.append(node("span", "screens-element-index", clickable.index), node("span", "", label));
      if (clickable.blocked || clickable.safe === false) { button.dataset.blocked = "true"; button.title = clickable.blocked_reason || clickable.reason || "请在手机上操作此敏感入口"; }
      button.addEventListener("click", () => operate("action", { observation_id: observation.id, action: "tap", index: clickable.index }));
      elements.append(button);
    }
    if (!elements.childNodes.length) elements.append(node("p", "field-note", observation.id ? "没有识别到可点击元素。可尝试滑动，或在手机上操作后重新获取截图。" : "获取截图后显示当前页的可点击元素。"));
    renderSaved();
    updateControls();
  }

  const OPERATION_LABELS = { launch: "正在打开目标 App 并截图…", observe: "正在获取当前页面与截图…", action: "正在操作并获取新截图…", label: "正在保存模块页面…", export: "正在拼接模块流程图…", release: "正在释放设备…", resume: "正在恢复任务…" };
  async function operate(operation, payload = {}) {
    if (!currentUser || !capture || busy || (!ownerCanControl() && !(operation === "release" && adminCanRelease()))) return;
    const generation = authGeneration;
    const request = ++operationRequest;
    const captureId = capture.id;
    busy = true; errorMessage("");
    $("screens-operation-status").textContent = OPERATION_LABELS[operation] || "正在处理…";
    updateControls();
    try {
      const data = await api(`/api/captures/${encodeURIComponent(captureId)}/${operation}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), timeoutMs: 120000 });
      if (!sameSession(generation) || request !== operationRequest || capture?.id !== captureId) return;
      capture = data.capture;
      renderCapture();
      if (operation === "label") {
        $("screens-label-form").reset();
        $("screens-module").value = payload.module_title || "";
      }
      $("screens-operation-status").textContent = operation === "export" ? "流程图已更新" : operation === "label" ? "页面已保存" : "已完成";
      await loadCaptures();
    } catch (error) {
      if (!sameSession(generation) || request !== operationRequest) return;
      if (error.data?.capture?.id === captureId && capture?.id === captureId) {
        capture = error.data.capture;
        renderCapture();
      } else if (["launch", "observe", "action"].includes(operation) && capture?.observation) {
        capture.observation = { ...capture.observation, actionable: false, uncertain: true };
        renderCapture();
      }
      const timeout = /超时/.test(error.message);
      const uncertain = timeout || error.data?.action_may_have_run;
      errorMessage(uncertain ? `${error.message} 操作可能已经执行，请先刷新截图记录查看结果，再获取当前截图；不要直接重复点击。` : error.message);
      $("screens-operation-status").textContent = "本次操作未确认完成";
      // Never retry an uncertain device action automatically.
    } finally { if (sameSession(generation) && request === operationRequest) { busy = false; updateControls(); } }
  }

  function renderApps() {
    const previous = $("screens-app").value;
    const term = $("screens-app-search").value.trim().toLowerCase();
    const filtered = installedApps.filter((item) => `${item.package} ${item.label || ""}`.toLowerCase().includes(term));
    $("screens-app").replaceChildren(new Option(filtered.length ? "请选择目标 App" : "没有匹配的已安装 App", ""));
    filtered.forEach((item) => $("screens-app").append(new Option(item.label ? `${item.label} · ${item.package}` : item.package, item.package)));
    if (filtered.some((item) => item.package === previous)) $("screens-app").value = previous;
    else if (requestedPackage && filtered.some((item) => item.package === requestedPackage)) $("screens-app").value = requestedPackage;
    $("screens-app").disabled = !filtered.length;
    updateControls();
  }

  $("nav-store").addEventListener("click", () => selectPane("store"));
  $("nav-screens").addEventListener("click", () => selectPane("screens"));
  $("screens-refresh").addEventListener("click", async () => {
    errorMessage("");
    if (loadedGeneration !== authGeneration) await loadCaptureData(); else await loadCaptures();
    if (capture && !busy) await selectCapture(capture.id);
  });
  $("screens-devices-refresh").addEventListener("click", async () => {
    if (!currentUser || busy || !captureMeta?.available) return;
    const generation = authGeneration; const request = ++deviceRequest;
    ++appsRequest; installedApps = [];
    $("screens-device").replaceChildren(new Option("正在查找设备…", ""));
    $("screens-device").disabled = true;
    $("screens-app").replaceChildren(new Option("先选择设备", ""));
    $("screens-app").disabled = true;
    $("screens-app-search").value = requestedPackage; $("screens-app-search").disabled = true;
    $("screens-devices-refresh").disabled = true; errorMessage(""); updateControls();
    try {
      const data = await api("/api/capture/devices", { timeoutMs: 45000 });
      if (!sameSession(generation) || request !== deviceRequest) return;
      const devices = Array.isArray(data.devices) ? data.devices : [];
      $("screens-device").replaceChildren(new Option(devices.length ? "请选择已授权设备" : "未发现设备", ""));
      devices.forEach((device) => {
        const ready = device.state === "device" && !device.busy;
        const label = `${device.model || device.serial} · ${device.serial}${device.busy ? " · 任务使用中，请从记录继续" : device.state === "device" ? "" : ` · ${device.state === "unauthorized" ? "请在手机确认调试授权" : device.state}`}`;
        const option = new Option(label, ready ? device.serial : ""); option.disabled = !ready;
        $("screens-device").append(option);
      });
      $("screens-device").disabled = !devices.some((device) => device.state === "device" && !device.busy);
      if (!devices.length) errorMessage("没有发现 Android 设备。请连接已开启 USB 调试的手机，或启动 Android 模拟器，再查找设备。");
    } catch (error) { if (sameSession(generation) && request === deviceRequest) errorMessage(error.message); }
    finally { if (sameSession(generation) && request === deviceRequest) updateControls(); }
  });
  $("screens-device").addEventListener("change", async () => {
    const serial = $("screens-device").value;
    const generation = authGeneration; const request = ++appsRequest;
    installedApps = []; $("screens-app-search").value = requestedPackage; $("screens-app-search").disabled = true;
    $("screens-app").replaceChildren(new Option(serial ? "正在读取已安装 App…" : "先选择设备", "")); $("screens-app").disabled = true;
    updateControls(); errorMessage("");
    if (!serial || !currentUser) return;
    try {
      const data = await api(`/api/capture/apps?serial=${encodeURIComponent(serial)}`, { timeoutMs: 45000 });
      if (!sameSession(generation) || request !== appsRequest || $("screens-device").value !== serial) return;
      installedApps = (Array.isArray(data.apps) ? data.apps : []).map((item) => typeof item === "string" ? { package: item } : item).filter((item) => item && typeof item.package === "string");
      $("screens-app-search").disabled = false; renderApps();
    } catch (error) { if (sameSession(generation) && request === appsRequest) errorMessage(error.message); }
  });
  $("screens-app-search").addEventListener("input", renderApps);
  $("screens-app").addEventListener("change", updateControls);
  $("screens-create-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!currentUser || busy || !captureMeta?.available) return;
    const serial = $("screens-device").value; const packageName = $("screens-app").value;
    if (!serial || !packageName) { errorMessage("请先选择已授权设备与已安装的目标 App。"); return; }
    const generation = authGeneration; const request = ++operationRequest;
    ++detailRequest; busy = true; updateControls(); errorMessage("");
    try {
      const data = await api("/api/captures", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ serial, package: packageName, title: $("screens-title").value.trim() }), timeoutMs: 120000 });
      if (!sameSession(generation) || request !== operationRequest) return;
      clearCurrent(); capture = data.capture; renderCapture(); await loadCaptures();
      $("screens-operation-status").textContent = "任务已创建，尚未打开 App。";
    } catch (error) { if (sameSession(generation) && request === operationRequest) errorMessage(error.message); }
    finally { if (sameSession(generation) && request === operationRequest) { busy = false; updateControls(); } }
  });
  $("screens-launch").addEventListener("click", () => operate("launch"));
  $("screens-observe").addEventListener("click", () => operate("observe"));
  $("screens-export").addEventListener("click", () => operate("export"));
  $("screens-image-open").addEventListener("click", () => {
    const url = captureURL(capture?.observation?.screenshot_url); if (!url || !currentUser) return;
    $("large-image").src = url; $("large-image").alt = `${capture.title || capture.package} · 当前实机截图`;
    $("image-caption").textContent = $("large-image").alt; $("image-dialog").showModal();
  });
  document.querySelectorAll("[data-screen-action], [data-screen-swipe]").forEach((button) => button.addEventListener("click", () => {
    if (!canAct()) return;
    operate("action", { observation_id: capture.observation.id, action: button.dataset.screenSwipe ? "swipe" : button.dataset.screenAction, ...(button.dataset.screenSwipe ? { direction: button.dataset.screenSwipe } : {}) });
  }));
  $("screens-label-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!activeCapture() || !capture?.observation?.id || busy) return;
    const module_title = $("screens-module").value.trim(); const page_title = $("screens-page").value.trim();
    if (!module_title || !page_title) { errorMessage("请填写当前页面所属模块和页面名称。"); return; }
    operate("label", { observation_id: capture.observation.id, module_title, page_title, state_title: $("screens-state").value.trim() });
  });
  window.CollectorScreens = {
    reset,
    enterSession: () => { reset(); selectPane("store"); },
    openForPackage(packageName, title) {
      if (!currentUser) return;
      requestedPackage = String(packageName || "");
      selectPane("screens");
      $("screens-app-search").value = requestedPackage;
      $("screens-title").value = String(title || packageName || "").slice(0, 120);
      if (installedApps.length) renderApps();
    }
  };
})();
