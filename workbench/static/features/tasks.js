"use strict";

/* tasks.js: loaded by index.html before the app bootstrap. */

function prepareTask(key) {
  const t = state.packs.flatMap((p) => p.tasks).find((t) => t.key === key);
  if (!t) return error(Error("任务不存在或当前能力未启用"));
  const active = currentVersion();
  const requiredKeys = t.required_upstream_all || [];
  const requiredTasks = requiredKeys.map((upstreamKey) => state.packs.flatMap((p) => p.tasks).find((item) => item.key === upstreamKey)).filter(Boolean);
  const requiredAccepted = requiredKeys.every((upstreamKey) => state.jobs.some(
    (job) => job.task_id === upstreamKey && job.review_decision === "accepted" && (active ? job.version_id === active.id : !job.version_id),
  ));
  const upstreamKeys = t.recommended_upstream_any || (t.recommended_upstream ? [t.recommended_upstream] : []);
  const upstreamTasks = upstreamKeys.map((upstreamKey) => state.packs.flatMap((p) => p.tasks).find((item) => item.key === upstreamKey)).filter(Boolean);
  const upstreamAccepted = !upstreamKeys.length || upstreamKeys.some((upstreamKey) => state.jobs.some(
    (job) => job.task_id === upstreamKey && job.review_decision === "accepted" && (active ? !job.version_id || job.version_id === active.id : !job.version_id),
  ));
  modal(
    "准备任务",
    `<div class="eyebrow">${E(t.output)}</div><h2>${E(t.name)}</h2><p class="muted">${E(t.description)}</p><div class="chipline"><span class="tag">${active ? `产品版本：${E(active.name)}` : "产品级任务"}</span></div>${requiredAccepted ? "" : `<div class="banner">本章依赖前文，请先生成并确认“${E(requiredTasks.map((item) => item.name).join("”、“") || requiredKeys.join(" / "))}”。前置章节未确认前不会启动本章，避免上下文冲突。</div>`}${upstreamAccepted ? "" : `<div class="banner">推荐先确认“${E(upstreamTasks.map((item) => item.name).join("”或“") || upstreamKeys.join(" / "))}”。你仍可继续准备本任务，但当前缺少已确认上游。</div>`}<div class="chipline">${t.tools.map((id) => `<span class="tag">${E(state.tools.find((tool) => tool.id === id)?.name || id)}</span>`).join("")}</div><form id="task-form"><label for="instruction">这次的具体要求</label><textarea id="instruction" maxlength="12000" placeholder="希望解决的问题、重点、范围、交付深度…"></textarea><label>指定要写进文档的资料（可选，最多 12 份）</label><div class="checks">${
      state.documents
        .filter((d) => ["upload", "accepted", "deliverable"].includes(d.kind))
        .map(
          (d) =>
            `<label><input type="checkbox" name="docs" value="${E(d.id)}">${E(d.name)}${(d.versions || []).length ? `（${E(d.versions.map((version) => version.name).join("、"))}）` : "（产品级）"}${d.kind === "deliverable" ? "（草稿，将附带警告）" : ""}</label>`,
        )
        .join("") ||
      "<small>没有可指定的资料；可以先导入，也可以先准备任务。</small>"
    }</div><div class="help">模板：${E(t.template)}<br>快速模式会把勾选的评论、政策、日志、截图和研究资料写入资料索引并用于相关结论。指定文本每份最多带入 12000 字；图片作为视觉输入。</div><button class="primary" type="submit" ${requiredAccepted ? "" : "disabled"}>生成任务包</button></form>`,
  );
  $("#task-form").onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      const j = await api("/api/prepare", {
        project_id: projectId,
        task: key,
        instruction: $("#instruction").value,
        version_id: active?.id || "",
        document_ids: Array.from(
          document.querySelectorAll("input[name=docs]:checked"),
        ).map((i) => i.value),
      });
      await refresh();
      showJob(j);
    } catch (err) {
      error(err);
      e.submitter.disabled = false;
    }
  };
}

async function assembleF1(key, button) {
  button.disabled = true;
  try {
    const active = currentVersion();
    const job = await api("/api/assemble", {
      project_id: projectId,
      task: key,
      version_id: active?.id || "",
    });
    await refresh();
    showJob(job);
    toast("已合并完整 F1，请进行最终检查和确认");
  } catch (err) {
    error(err);
    button.disabled = false;
  }
}
