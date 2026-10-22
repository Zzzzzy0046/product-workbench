"use strict";

const API_TIMEOUT_MS = 120000;
let refreshSequence = 0;

async function api(path, body, { timeout = API_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(
      path,
      body === undefined
        ? { signal: controller.signal }
        : {
            method: "POST",
            signal: controller.signal,
            headers: {
              "Content-Type": "application/json",
              "X-Workbench-Token": state?.token || "",
            },
            body: JSON.stringify(body),
          },
    );
  } catch (err) {
    if (err.name === "AbortError") throw Error("请求超时，本地服务可能正忙，请稍后重试。");
    throw Error("无法连接本地工作台服务。");
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try {
    data = await response.json();
  } catch (_) {
    throw Error(response.ok ? "服务返回了无法解析的内容。" : `请求失败（HTTP ${response.status}）`);
  }
  if (!response.ok) throw Error(data?.error || `请求失败（HTTP ${response.status}）`);
  return data;
}

// Only the newest refresh may replace state: a slow response for a project the
// user already left must not overwrite the current view.
async function refresh(render = true) {
  const sequence = ++refreshSequence;
  const requested = projectId;
  const next = await api(
    "/api/state" + (requested ? "?project=" + encodeURIComponent(requested) : ""),
  );
  if (sequence !== refreshSequence || requested !== projectId) return false;
  state = next;
  if (render) draw();
  return true;
}
