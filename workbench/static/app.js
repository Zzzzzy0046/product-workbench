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
setInterval(async () => {
  if (polling || !state) return;
  const running = state.jobs?.some((j) =>
    ["queued", "running"].includes(j.status),
  );
  const runningScrapes = state.scrapes?.some((item) => ["queued", "running"].includes(item.status));
  if (!running && !runningScrapes) return;
  polling = true;
  try {
    const previous = activeJob
      ? state.jobs.find((j) => j.id === activeJob)?.status
      : null;
    await refresh(false);
    if (
      activeJob &&
      state.jobs.find((j) => j.id === activeJob)?.status !== previous
    )
      showJob(await api("/api/jobs/" + activeJob));
    if (["overview", "outputs", "materials"].includes(tab)) draw();
  } catch (err) {
    $("#banner").textContent = "连接暂时中断，正在等待本地服务恢复。";
    $("#banner").hidden = false;
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
    await refresh();
  } catch (err) {
    $("#content").innerHTML =
      '<div class="empty"><h2>暂时无法连接工作台</h2><p>' +
      E(err.message) +
      "</p><p>请检查本地服务已启动，再刷新页面。</p></div>";
  }
})();
