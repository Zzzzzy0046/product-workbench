"use strict";

/* Composition entry: bind navigation, polling and initial state loading. */

$("#new-project").onclick = newProject;
$("#capabilities").onclick = () => {
  tab = "capabilities";
  draw();
};
$("#import-project").onclick = importProjectDialog;
$("#trash").onclick = () => {
  tab = "trash";
  draw();
};

// Signature of everything the polling loop can change on screen. If it is
// unchanged we skip re-rendering, so open <details>, scroll position, search
// results and half-typed inputs survive background refreshes.
function pollSignature(source) {
  const jobs = (source.jobs || []).map((j) => `${j.id}:${j.status}:${j.review_decision || ""}:${j.archived || 0}:${j.current_version || ""}`);
  const scrapes = (source.scrapes || []).map((s) => `${s.id}:${s.status}:${s.review_count || 0}:${s.translated_count || 0}`);
  return `${jobs.join("|")}#${scrapes.join("|")}#${(source.documents || []).length}`;
}

function setConnectionBanner(message) {
  $("#banner").textContent = message || "";
  $("#banner").hidden = !message;
}

setInterval(async () => {
  if (polling || !state || document.hidden) return;
  const running = state.jobs?.some((j) => ["queued", "running"].includes(j.status));
  const runningScrapes = state.scrapes?.some((item) => ["queued", "running"].includes(item.status));
  if (!running && !runningScrapes) return;
  polling = true;
  try {
    const before = pollSignature(state);
    const previous = activeJob ? state.jobs.find((j) => j.id === activeJob)?.status : null;
    if (!(await refresh(false))) return;
    setConnectionBanner("");
    if (activeJob && state.jobs.find((j) => j.id === activeJob)?.status !== previous)
      showJob(await api("/api/jobs/" + activeJob));
    if (pollSignature(state) === before) return;
    if (hasUnsavedEdits()) return;
    if (["workflow", "outputs", "materials"].includes(tab) && !readerIsOpen()) draw();
  } catch (err) {
    setConnectionBanner("连接暂时中断，正在等待本地服务恢复。");
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
    tab = "workflow";
    await refresh();
  } catch (err) {
    $("#content").innerHTML =
      '<div class="empty"><h2>暂时无法连接工作台</h2><p>' +
      E(err.message) +
      "</p><p>请确认本地服务已启动，再刷新页面。</p></div>";
  }
})();
