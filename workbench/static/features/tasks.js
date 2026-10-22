"use strict";

/* tasks.js: loaded by index.html before the app bootstrap. */

function scopedTaskJobs(key) {
  const active = currentVersion();
  const jobs = (state.jobs || []).filter((job) => !job.archived && job.is_latest !== 0 && job.task_id === key);
  const scoped = jobs.filter((job) => active ? job.version_id === active.id : !job.version_id);
  return scoped.sort((left, right) => Date.parse(right.created || 0) - Date.parse(left.created || 0));
}

function taskIsCurrentConfirmed(key) {
  const job = scopedTaskJobs(key)[0];
  if (job?.review_decision !== "accepted") return false;
  const task = state.packs.flatMap((pack) => pack.tasks).find((item) => item.key === key);
  if (task?.assembly !== "accepted_sections") return true;
  return task.section_tasks.every((chapterKey) => {
    const chapter = scopedTaskJobs(chapterKey)[0];
    return chapter?.review_decision === "accepted" && Date.parse(chapter.review_created || chapter.updated || chapter.created || 0) <= Date.parse(job.created || 0);
  });
}

const taskFormDrafts = new Map();

function prioritizeTaskReferences(ids, documents) {
  const images = new Set(documents.filter((item) => item.category === "images" || /\.(png|jpe?g|webp)$/i.test(item.name || "")).map((item) => item.id));
  return [...ids].sort((left, right) => Number(images.has(left)) - Number(images.has(right)));
}

function taskDocumentChoices(documents, selectedIds, active) {
  const inScope = (item) => !(item.versions || []).length ||
    Boolean(active && item.versions.some((version) => version.id === active.id));
  const render = (items) => items.map((item) =>
    `<label><input type="checkbox" name="docs" value="${E(item.id)}" ${selectedIds.has(item.id) ? "checked" : ""}>${E(item.name)}${(item.versions || []).length ? `（${E(item.versions.map((version) => version.name).join("、"))}）` : "（产品级）"}${item.kind === "deliverable" ? "（草稿，将附带警告）" : ""}</label>`,
  ).join("");
  const current = documents.filter(inScope), other = documents.filter((item) => !inScope(item));
  return `<div class="checks">${render(current) || "<small>当前范围还没有可指定的资料，可以先导入，也可以先准备任务。</small>"}</div>${other.length ? `<details ${other.some((item) => selectedIds.has(item.id)) ? "open" : ""}><summary>其他产品版本的资料（${other.length} 份，明确勾选才引用）</summary><div class="checks">${render(other)}</div></details>` : ""}`;
}

function taskExplicitSourceEligible(item, active, competitorIds) {
  if (item.kind !== "upload" || item.confirmed === false ||
      ["pending", "ready", "queued", "running", "failed", "cancelled", "interrupted", "empty"].includes(item.status)) return false;
  if ((item.versions || []).length && !item.versions.some((version) => version.id === active?.id)) return false;
  const owners = item.competitor_ids || [];
  return !owners.length || owners.some((id) => competitorIds.includes(id));
}

function prepareTask(key, options = {}) {
  const t = state.packs.flatMap((p) => p.tasks).find((t) => t.key === key);
  if (!t) return error(Error("任务不存在或当前能力未启用"));
  const active = currentVersion();
  const taskProjectId = projectId;
  const draftKey = `${taskProjectId}:${active?.id || "product"}:${key}`;
  const draft = taskFormDrafts.get(draftKey) || {};
  const sourceSelectionMode = options.sourceSelectionMode || draft.sourceSelectionMode || "auto";
  const competitorIds = Array.isArray(options.competitorIds) ? options.competitorIds : draft.competitorIds || [];
  const documents = state.documents.filter((item) => sourceSelectionMode === "explicit"
    ? taskExplicitSourceEligible(item, active, competitorIds)
    : ["upload", "accepted", "deliverable"].includes(item.kind));
  const availableIds = new Set(documents.map((item) => item.id));
  const suppliedIds = Array.from(new Set((Array.isArray(options.documentIds) ? options.documentIds : draft.documentIds || []).filter((id) => availableIds.has(id))));
  const requestedIds = Array.isArray(options.documentIds) ? prioritizeTaskReferences(suppliedIds, documents) : suppliedIds;
  const selectedIds = new Set(requestedIds.slice(0, 12));
  const referenceNotice = (sourceSelectionMode === "explicit" ? '<div class="banner">已启用“仅使用勾选资料”。不会自动检索其他竞品的项目资料；任务必需的已确认前置章节仍会单独列出。</div>' : "") + (requestedIds.length
    ? `<p class="help">已带入 ${selectedIds.size} 份参考资料，请核对后再准备任务。${requestedIds.length > 12 ? `本次最多指定 12 份，优先勾选描述和评论等文本，另有 ${requestedIds.length - 12} 份未勾选，可在下方调整。` : ""}</p>`
    : "");
  const requiredKeys = t.required_upstream_all || [];
  const requiredTasks = requiredKeys.map((upstreamKey) => state.packs.flatMap((p) => p.tasks).find((item) => item.key === upstreamKey)).filter(Boolean);
  const requiredAccepted = requiredKeys.every((upstreamKey) => scopedTaskJobs(upstreamKey)[0]?.review_decision === "accepted");
  const upstreamKeys = t.recommended_upstream_any || (t.recommended_upstream ? [t.recommended_upstream] : []);
  const upstreamTasks = upstreamKeys.map((upstreamKey) => state.packs.flatMap((p) => p.tasks).find((item) => item.key === upstreamKey)).filter(Boolean);
  const upstreamAccepted = !upstreamKeys.length || upstreamKeys.some((upstreamKey) => scopedTaskJobs(upstreamKey)[0]?.review_decision === "accepted");
  const workflow = (state.workflows || []).find((item) => item.id === activeWorkflow);
  const step = workflow?.steps.find((item) => item.task === key && (!activeWorkflowStage || item.stage === activeWorkflowStage));
  const stage = workflow?.stages?.find((item) => item.id === step?.stage);
  const instructionPlaceholder = key === "fast/review-changes"
    ? "粘贴真实评审意见，注明涉及模块、采用的决定和需要保留的内容。"
    : key === "fast/consistency-review"
      ? "例如：对照当前 PRD、流程和验收用例，找出权益、广告触发和返回规则的冲突。"
      : "希望解决的问题、参考资料、已确认规则和本轮重点…";
  const prototypeNotice = key === "fast/prototype-handoff"
    ? '<p class="tool-note">本任务生成页面制作说明与旁注草稿。交给具备 Figma / Axure 连接的会话执行后，再将原型截图或快照放回项目核对。</p>'
    : "";
  modal(
    "准备任务",
    `<div class="eyebrow">${E(t.output)}</div><h2>${E(t.name)}</h2><p class="muted">${E(t.description)}</p><div class="chipline"><span class="tag">${active ? `产品版本：${E(active.name)}` : "产品级任务"}</span>${stage ? `<span class="tag">${E(stage.name)}</span>` : ""}</div>${requiredAccepted ? "" : `<div class="banner">本章依赖前文，请先生成并确认“${E(requiredTasks.map((item) => item.name).join("”、“") || requiredKeys.join(" / "))}”。前置章节未确认前不会启动本章，避免上下文冲突。</div>`}${upstreamAccepted ? "" : `<div class="banner">可勾选已有原型、PRD 或流程作为当前基线，直接开始；也可先确认“${E(upstreamTasks.map((item) => item.name).join("”或“") || upstreamKeys.join(" / "))}”。</div>`}${prototypeNotice}<form id="task-form"><label for="task-scope">本轮只处理哪些模块（可选）</label><input id="task-scope" maxlength="600" value="${E(draft.scope || "")}" placeholder="例如：只处理首页与导入，沿用已确认的商业规则"><label for="instruction">这次的具体要求</label><textarea id="instruction" maxlength="10000" placeholder="${E(instructionPlaceholder)}">${E(draft.instruction || "")}</textarea><p class="help">本轮交付：${E(t.output)}。生成后留在当前任务，按需进入下一阶段。暂存输入只在当前页面内保留，刷新后清除。</p><label>指定当前基线与参考资料（可选，最多 12 份）</label>${referenceNotice}${taskDocumentChoices(documents, selectedIds, active)}<label for="task-baseline">采用哪份基线或已确认决定（可选）</label><input id="task-baseline" maxlength="600" value="${E(draft.baseline || "")}" placeholder="例如：以勾选的当前流程为准，旧 PRD 仅用于对照"><div class="help">有冲突时列出具体位置，未指定优先级时保留待决定项。不会仅凭文件名或日期替你决定。<br>模板：${E(t.template)}；指定文本每份最多带入 12000 字，图片作为视觉输入。</div><button class="primary" type="submit" ${requiredAccepted ? "" : "disabled"}>生成任务包</button></form>`,
  );
  const form = $("#task-form");
  const remember = () => {
    taskFormDrafts.delete(draftKey);
    taskFormDrafts.set(draftKey, {
      scope: $("#task-scope").value, instruction: $("#instruction").value,
      baseline: $("#task-baseline").value,
      documentIds: Array.from(form.querySelectorAll('input[name="docs"]:checked')).map((item) => item.value),
      sourceSelectionMode, competitorIds,
    });
    if (taskFormDrafts.size > 20) taskFormDrafts.delete(taskFormDrafts.keys().next().value);
  };
  form.oninput = remember;
  form.onchange = (event) => {
    if (event.target.matches('input[name="docs"]') && form.querySelectorAll('input[name="docs"]:checked').length > 12) {
      event.target.checked = false;
      toast("一次最多指定 12 份资料，请先取消其他选择。");
    }
    remember();
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      const j = await api("/api/prepare", {
        project_id: taskProjectId,
        task: key,
        instruction: [
          stage ? `当前阶段：${stage.name}` : "",
          $("#task-scope").value.trim() ? `本轮范围：${$("#task-scope").value.trim()}` : "",
          $("#task-baseline").value.trim() ? `当前采用的基线：${$("#task-baseline").value.trim()}` : "",
          $("#instruction").value.trim(),
          `本轮交付点：只生成${t.output}，后续任务按需单独启动。`,
        ].filter(Boolean).join("\n\n"),
        version_id: active?.id || "",
        source_selection_mode: sourceSelectionMode,
        competitor_ids: competitorIds,
        document_ids: Array.from(
          form.querySelectorAll("input[name=docs]:checked"),
        ).map((i) => i.value),
      });
      taskFormDrafts.delete(draftKey);
      if (projectId !== taskProjectId || (currentVersion()?.id || "") !== (active?.id || "") || $("#task-form") !== form) return;
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
