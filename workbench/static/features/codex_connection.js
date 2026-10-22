"use strict";

/* Local CLI onboarding. Opening this view only reads status; every CLI action
 * requires an explicit click, and login / generation additionally require consent. */
const codexConnectionView = {
  generation: 0, request: 0, timer: null, active: false, pending: false,
  snapshot: null, pathDraft: null, pathOpen: false, notice: "",
};

function codexConnectionSnapshot() {
  return codexConnectionView.snapshot || state?.integrations?.codex || {
    available: !!state?.runtime?.available,
    model: state?.runtime?.model || "", auth: {status: "unknown"},
    test: {status: "not_tested"},
  };
}

function codexConnectionRunning(snapshot = codexConnectionSnapshot()) {
  return snapshot.operation?.status === "running";
}

function codexConnectionBeforeDraw() {
  codexConnectionView.generation += 1;
  codexConnectionView.request += 1;
  codexConnectionView.active = false;
  codexConnectionView.pending = false;
  clearTimeout(codexConnectionView.timer);
  codexConnectionView.timer = null;
}

function codexConnectionScope() {
  return {generation: codexConnectionView.generation, project: projectId};
}

function codexConnectionIsCurrent(scope) {
  return codexConnectionView.active && scope.generation === codexConnectionView.generation &&
    scope.project === projectId && tab === "capabilities" &&
    !!$("#codex-connection-card");
}

function codexConnectionCard(snapshot = codexConnectionSnapshot()) {
  const auth = snapshot.auth || {}, test = snapshot.test || {};
  const running = codexConnectionRunning(snapshot);
  const busy = running || codexConnectionView.pending;
  const disabled = busy ? "disabled" : "";
  const authNames = {unknown: "尚未检查", logged_in: "已登录", not_logged_in: "未登录", error: "检查失败"};
  const testNames = {not_tested: "尚未测试", passed: "生成测试通过", failed: "生成测试失败"};
  const sourceNames = {environment: "环境变量指定", saved: "工作台指定", path: "系统 PATH", desktop: "Codex 桌面程序", npm: "npm 入口", missing: "尚未找到"};
  const kindNames = {check: "检查 CLI 与登录状态", login: "等待浏览器登录授权", test: "执行最小生成测试"};
  const complete = snapshot.available && auth.status === "logged_in" && test.status === "passed";
  const headline = running ? (kindNames[snapshot.operation.kind] || "正在处理") : complete ? "已连接 · 已验证" : !snapshot.available ? "先连接本机 Codex" : auth.status === "not_logged_in" ? "CLI 已找到，请登录" : "CLI 已找到，继续检查连接";
  const path = codexConnectionView.pathDraft ?? (snapshot.source === "saved" ? snapshot.binary_path || "" : "");
  const candidates = (snapshot.candidates || []).filter((candidate) => candidate.source !== "npm" && /\.exe$/i.test(candidate.path || ""));
  const nativeSelected = candidates.some((candidate) => candidate.path === path);
  const operation = snapshot.operation;
  return `<section id="codex-connection-card" class="card codex-connection-card" aria-labelledby="codex-connection-title">
    <div class="codex-connection-heading"><div><div class="eyebrow">LOCAL CODEX CONNECTION</div><h2 id="codex-connection-title">连接你的 Codex</h2><p>使用这台电脑自己的账号生成文档，工作台不接收密码，也不会复制登录凭据。</p></div><span class="tag ${complete ? "" : "warn"}">${E(headline)}</span></div>
    <ol class="codex-connection-steps" aria-label="连接状态">
      <li><span class="codex-step-number">1</span><div><h3>找到 CLI</h3><strong>${snapshot.available ? "已找到" : "未找到 CLI"}</strong><p>${E(snapshot.version || (snapshot.available ? "版本尚未检查" : "安装 CLI 或指定已有路径"))}</p></div></li>
      <li><span class="codex-step-number">2</span><div><h3>检查登录</h3><strong>${E(authNames[auth.status] || "尚未检查")}</strong><p>${E(auth.method === "api_key" ? "API Key 认证" : auth.method === "access_token" ? "Token 认证" : auth.method === "chatgpt" ? "ChatGPT 账号" : "认证由本机 Codex 管理")}</p></div></li>
      <li><span class="codex-step-number">3</span><div><h3>验证生成</h3><strong>${E(testNames[test.status] || "尚未测试")}</strong><p>${E(test.checked_at ? `最近测试：${date(test.checked_at)}` : "仅在你确认后发送一个小请求")}</p></div></li>
    </ol>
    <p class="help codex-connection-boundary">找到 CLI ≠ 已登录 ≠ 生成可用。登录成功后仍需单独测试账号、模型与网络。</p>
    <div class="codex-connection-actions actions"><button class="primary small" data-codex-connection="check" ${disabled}>${busy && operation?.kind === "check" ? "正在检查…" : "检测 CLI / 登录状态"}</button><button class="small" data-codex-connection="login" ${busy || !snapshot.available ? "disabled" : ""}>使用浏览器登录</button><button class="small" data-codex-connection="test" ${busy || !snapshot.available ? "disabled" : ""}>连接测试</button>${running ? `<button class="small danger" data-codex-connection="cancel" data-operation-id="${E(operation.id)}">取消本次操作</button>` : ""}</div>
    ${operation ? `<div class="codex-operation ${operation.status === "failed" ? "is-error" : ""}" role="status"><strong>${E(kindNames[operation.kind] || "连接操作")} · ${E({running:"进行中", succeeded:"已完成", failed:"失败，可重试", cancelled:"已取消"}[operation.status] || operation.status)}</strong><p>${E(operation.message || (running ? "可保留此页等待结果，也可以取消本次操作。" : ""))}</p>${operation.kind === "login" && running ? "<p>请在这台电脑打开的官方浏览器窗口中完成授权。工作台不接收账号密码；超时后可重试。</p>" : ""}</div>` : ""}
    ${codexConnectionView.notice ? `<p class="codex-connection-notice" role="status">${E(codexConnectionView.notice)} <button class="small" data-codex-connection="refresh" ${codexConnectionView.pending ? "disabled" : ""}>刷新状态</button></p>` : ""}
    ${snapshot.message ? `<p class="help">${E(snapshot.message)}</p>` : ""}
    ${auth.message ? `<p class="help">登录状态：${E(auth.message)}</p>` : ""}
    ${test.message ? `<p class="help">生成测试：${E(test.message)}</p>` : ""}
    ${!snapshot.available ? '<p class="codex-install-help">尚未安装？先按 <a href="https://developers.openai.com/codex/cli/" target="_blank" rel="noopener noreferrer">官方 Codex CLI 指引</a>安装，再返回检测。工作台不会自动安装软件。</p>' : ""}
    <details class="codex-connection-path" ${codexConnectionView.pathOpen ? "open" : ""}><summary>CLI 路径与运行信息</summary><dl><dt>当前入口</dt><dd>${E(snapshot.binary_path || (snapshot.command || []).join(" ") || "尚未找到")}</dd><dt>发现来源</dt><dd>${E(sourceNames[snapshot.source] || "自动发现")}</dd><dt>生成模型</dt><dd>${E(snapshot.model || "沿用 Codex 默认配置")}</dd><dt>配置文件</dt><dd>${E(snapshot.config_path || "由 Codex 管理")}</dd></dl>
      ${snapshot.source === "npm" ? '<p class="help">当前为自动发现的 npm 入口，无需手动指定；要继续使用它，请保留自动检测。</p>' : ""}
      ${snapshot.env_managed ? '<p class="help">CLI 由启动环境指定，当前不能在页面改写路径。请先调整启动环境，再重新检测。</p>' : ""}
      <fieldset ${busy || snapshot.env_managed ? "disabled" : ""}><legend class="visually-hidden">指定本机 Codex CLI 路径</legend><label for="codex-path-candidate">发现的原生 CLI</label><select id="codex-path-candidate"><option value="">手动粘贴路径或恢复自动检测</option>${candidates.map((candidate) => `<option value="${E(candidate.path)}" ${nativeSelected && candidate.path === path ? "selected" : ""}>${E(candidate.label || candidate.path)} · ${E(candidate.path)}</option>`).join("")}</select><label for="codex-binary-path">完整 codex.exe 路径</label><input id="codex-binary-path" value="${E(path)}" maxlength="1200" autocomplete="off" spellcheck="false" placeholder="例如 C:\\Tools\\Codex\\codex.exe"><p class="help">请选择这台电脑已有的 codex.exe，不要上传 EXE，也不要填写账号、API Key 或认证文件。</p><div class="actions"><button class="small" data-codex-connection="save">保存指定路径</button><button class="small" data-codex-connection="auto">恢复自动检测</button></div></fieldset>
    </details>
  </section>`;
}

function codexConnectionPaint() {
  const card = $("#codex-connection-card");
  if (!card || tab !== "capabilities") return;
  card.outerHTML = codexConnectionCard();
  const details = $(".codex-connection-path");
  if (details) details.ontoggle = () => { codexConnectionView.pathOpen = details.open; };
  const path = $("#codex-binary-path"), candidate = $("#codex-path-candidate");
  if (path) path.oninput = () => { codexConnectionView.pathDraft = path.value; };
  if (candidate) candidate.onchange = () => {
    if (candidate.value) {
      codexConnectionView.pathDraft = candidate.value;
      if (path) path.value = candidate.value;
    }
  };
}

function codexConnectionAccept(snapshot) {
  codexConnectionView.snapshot = snapshot;
  state.integrations ||= {};
  state.integrations.codex = snapshot;
  if (state.runtime) {
    state.runtime.available = !!snapshot.available;
    if (snapshot.model) state.runtime.model = snapshot.model;
  }
}

function codexConnectionSchedule(scope) {
  clearTimeout(codexConnectionView.timer);
  codexConnectionView.timer = null;
  if (!codexConnectionIsCurrent(scope) || !codexConnectionRunning()) return;
  codexConnectionView.timer = setTimeout(() => codexConnectionRead(scope), 1500);
}

async function codexConnectionRead(scope) {
  if (!codexConnectionIsCurrent(scope)) return;
  const request = ++codexConnectionView.request;
  try {
    const snapshot = await api("/api/integrations/codex");
    if (!codexConnectionIsCurrent(scope) || request !== codexConnectionView.request) return;
    codexConnectionAccept(snapshot);
    codexConnectionView.notice = "";
    codexConnectionPaint();
    codexConnectionSchedule(scope);
  } catch (err) {
    if (!codexConnectionIsCurrent(scope) || request !== codexConnectionView.request) return;
    codexConnectionView.notice = `状态读取失败：${err.message}。请刷新状态重试；不会自动发起生成。`;
    codexConnectionPaint();
  }
}

function codexConnectionMount() {
  codexConnectionView.active = true;
  codexConnectionPaint();
  // GET discovers files and returns cached operation state; never executes CLI.
  codexConnectionRead(codexConnectionScope());
}

async function codexConnectionAction(action, button) {
  const scope = codexConnectionScope(), snapshot = codexConnectionSnapshot();
  if (!codexConnectionIsCurrent(scope)) return;
  if (action === "refresh" && !codexConnectionView.pending) return codexConnectionRead(scope);
  if (codexConnectionView.pending || (codexConnectionRunning(snapshot) && action !== "cancel")) return;
  if (action === "login" && !window.confirm("将启动本机 Codex 的官方浏览器登录。请由你本人在浏览器完成授权；这会更新此电脑的 Codex 登录状态。工作台不接收密码，也不会复制凭据。继续？")) return;
  if (action === "test" && !window.confirm("连接测试会使用你自己的 Codex 账号与当前模型，发送一个固定的小请求，可能消耗账号额度。不包含任何项目资料。确定开始测试？")) return;
  if (!codexConnectionIsCurrent(scope)) return;
  let path, body = {};
  if (action === "save" || action === "auto") {
    if (snapshot.env_managed) return;
    const binaryPath = action === "auto" ? "" : ($("#codex-binary-path")?.value || "").trim();
    if (action === "save" && !binaryPath) { toast("请先选择或粘贴完整 codex.exe 路径，或使用自动检测。"); return; }
    codexConnectionView.pathDraft = binaryPath;
    path = "/api/integrations/codex"; body = {binary_path: binaryPath};
  } else if (["check", "login", "test", "cancel"].includes(action)) {
    if (["login", "test"].includes(action) && !snapshot.available) return;
    path = `/api/integrations/codex/${action}`;
    if (action === "login" || action === "test") body = {confirmed: true};
    if (action === "cancel") {
      const operationId = button?.dataset?.operationId;
      if (!operationId || operationId !== snapshot.operation?.id || !codexConnectionRunning(snapshot)) return;
      body = {operation_id: operationId};
    }
  } else return;
  const request = ++codexConnectionView.request;
  codexConnectionView.pending = true;
  codexConnectionView.notice = "";
  clearTimeout(codexConnectionView.timer);
  codexConnectionView.timer = null;
  codexConnectionPaint();
  try {
    const result = await api(path, body);
    if (!codexConnectionIsCurrent(scope) || request !== codexConnectionView.request) return;
    codexConnectionAccept(result);
    codexConnectionView.pending = false;
    if (action === "save" || action === "auto") codexConnectionView.notice = action === "save" ? "CLI 路径已保存；登录和生成状态请重新检查。" : "已恢复自动检测；登录和生成状态请重新检查。";
    codexConnectionPaint();
    codexConnectionSchedule(scope);
  } catch (err) {
    if (!codexConnectionIsCurrent(scope) || request !== codexConnectionView.request) return;
    codexConnectionView.pending = false;
    codexConnectionView.notice = `${err.message}。可重试。`;
    codexConnectionPaint();
    codexConnectionSchedule(scope);
  }
}

window.addEventListener("pagehide", codexConnectionBeforeDraw);
