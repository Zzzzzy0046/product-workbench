"use strict";

/* outputs.js: document reader, comments, editing and version history. */

function commentsPanel(job) {
  const current = (job.comments || []).filter(
      (item) => item.version === job.current_version,
    ),
    historyCount = (job.comments || []).length - current.length,
    open = current.filter((item) => item.status === "open");
  return `<section class="comments-panel"><h3>V${job.current_version} 批注 · ${open.length} 条待处理</h3>${open.length ? `<button class="primary small mt-8" data-revise-comments="${E(job.id)}">按 ${open.length} 条批注修订</button>` : ""}<p class="help">在正文段落旁点「添加批注」。修订成功后，本次使用的批注会自动标记为已解决。</p><div class="comment-list">${current
    .map(
      (item) =>
        `<article class="comment-item ${item.status === "resolved" ? "resolved" : ""}"><div class="split"><div class="chipline flush"><span class="tag">${E(commentActionNames[item.action] || item.action)}</span><span class="tag ${item.status === "open" ? "warn" : "ok"}">${item.status === "open" ? "待处理" : "已解决"}</span></div><button class="small ghost" data-comment-status="${item.status === "open" ? "resolved" : "open"}" data-comment-id="${E(item.id)}" data-id="${E(job.id)}">${item.status === "open" ? "解决" : "重新打开"}</button></div><strong>${E(item.block_label)}</strong><div class="comment-quote">${E(item.quote)}</div><p>${E(item.note)}</p><small>${E(item.author || "未署名")} · ${date(item.created)}</small></article>`,
    )
    .join("") || '<div class="empty compact">当前版本还没有批注。</div>'}</div>${historyCount ? `<p class="help">另有 ${historyCount} 条旧版本批注仅作历史记录。</p>` : ""}</section>`;
}

function qualitySummary(job) {
  const quality = job.quality || { issues: [], errors: 0, warnings: 0, ok: true };
  if (!quality.issues?.length) return '<div class="quality-check quality-ok">质量校验通过，未发现阻断项。</div>';
  return `<div class="quality-check ${quality.errors ? "quality-has-errors" : "quality-has-warnings"}"><strong>质量校验：${quality.errors ? `${quality.errors} 个阻断项` : "无阻断项"}${quality.warnings ? ` · ${quality.warnings} 个提示` : ""}</strong><ul>${quality.issues.map((issue) => `<li class="${issue.severity === "error" ? "quality-error" : "quality-warning"}"><span class="tag ${issue.severity === "error" ? "bad" : "warn"}">${issue.severity === "error" ? "阻断" : "提示"}</span> ${E(issue.message)}${issue.hint ? `<small>建议：${E(issue.hint)}</small>` : ""}</li>`).join("")}</ul></div>`;
}

function f1ContinuationAction(job) {
  const active = currentVersion();
  if (job.review?.decision !== "accepted" || job.archived || job.is_latest === 0 || job.has_newer_revision || job.stale_upstream?.length ||
      (job.version_id || "") !== (active?.id || "")) return null;
  const parent = state.packs.flatMap((pack) => pack.tasks).find((task) => task.assembly === "accepted_sections" && task.key === "fast/new-product-analysis");
  if (!parent) return null;
  if (job.task_id === parent.key) {
    return taskIsCurrentConfirmed(parent.key) ? { type: "prototype", label: "继续：原型图＋需求说明" } : null;
  }
  const index = parent.section_tasks.indexOf(job.task_id);
  if (index < 0 || scopedTaskJobs(job.task_id)[0]?.id !== job.id) return null;
  const nextKey = parent.section_tasks[index + 1];
  if (nextKey) {
    const next = state.packs.flatMap((pack) => pack.tasks).find((task) => task.key === nextKey);
    if (!next || !(next.required_upstream_all || []).every((key) => scopedTaskJobs(key)[0]?.review_decision === "accepted")) return null;
    const existing = scopedTaskJobs(nextKey)[0];
    return existing ? { type: "job", jobId: existing.id, label: `继续查看：${next.name}` }
      : { type: "prepare", taskKey: nextKey, label: `继续准备：${next.name}` };
  }
  if (!parent.section_tasks.every((key) => scopedTaskJobs(key)[0]?.review_decision === "accepted")) return null;
  const combined = scopedTaskJobs(parent.key)[0];
  return combined && taskIsCurrentConfirmed(parent.key)
    ? { type: "job", jobId: combined.id, label: "查看已确认的完整 F1" }
    : { type: "assemble", taskKey: parent.key, label: "合并五章为完整 F1（不调用模型）" };
}

// Carry forward what the user explicitly chose; fall back to every upload the
// previous chapter cited only when no explicit choice was recorded.
function continuationReferenceIds(job) {
  if ((job.selected_document_ids || []).length) return job.selected_document_ids;
  return (job.sources || []).filter((source) => source.kind === "upload").map((source) => source.source_id);
}

/* ---------- Full-screen reader ---------- */

let readerSideTab = "comments";

function readerIsOpen() {
  const reader = document.getElementById?.("reader");
  return Boolean(reader && !reader.hidden);
}

function closeReader() {
  const reader = document.getElementById("reader");
  if (!reader || reader.hidden) return;
  reader.hidden = true;
  document.body.classList.remove("reader-open");
  activeJob = null;
  if (state?.project) draw();
}

function readerShell() {
  let reader = document.getElementById("reader");
  if (!reader) {
    reader = document.createElement("section");
    reader.id = "reader";
    reader.className = "reader";
    reader.setAttribute("aria-label", "文档阅读");
    reader.hidden = true;
    document.body.appendChild(reader);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && readerIsOpen() && !$("#modal").open) closeReader();
    });
  }
  return reader;
}

function readerSidePanel(job) {
  const sources = job.sources || [];
  const openComments = (job.comments || []).filter((item) => item.version === job.current_version && item.status === "open").length;
  const tabs = [["comments", `批注${openComments ? ` ${openComments}` : ""}`], ["sources", `来源 ${sources.length}`], ["info", "任务信息"]];
  let body;
  if (readerSideTab === "sources") {
    body = sources.map((s) => `<div class="card"><h3>[${E(s.citation)}] ${E(s.name)}</h3><small>${E(kinds[s.kind] || s.kind)} · 片段 ${s.chunk}${s.truncated ? " · 已截断" : ""}</small><details><summary>查看片段</summary><div class="excerpt">${E(s.text)}</div></details></div>`).join("") || '<div class="empty compact">没有引用资料。</div>';
  } else if (readerSideTab === "info") {
    body = `<dl class="kv kv-narrow"><dt>模式</dt><dd>${E(workflowNames[job.workflow_mode] || job.workflow_mode)}</dd><dt>范围</dt><dd>${E(scopeLabel(job))}</dd><dt>创建</dt><dd>${date(job.created)}</dd><dt>版本</dt><dd>V${job.current_version || 1}（共 ${job.version_count || 1} 个）</dd><dt>分支</dt><dd>${job.is_latest === 0 || job.has_newer_revision ? "已有后续修订" : "当前分支最新版"}</dd></dl>${job.parent_job_id ? `<p class="mt-12"><button class="small" data-job="${E(job.parent_job_id)}">查看上一任务</button></p>` : ""}<details><summary>本次输入（背景、模板与任务要求）</summary><pre class="document">${E(job.prompt)}</pre></details>`;
  } else {
    body = job.output ? commentsPanel(job) : '<div class="empty compact">生成正文后可以添加批注。</div>';
  }
  return `<div class="reader-side-tabs" role="tablist">${tabs.map(([id, label]) => `<button role="tab" class="${readerSideTab === id ? "active" : ""}" data-reader-side="${id}">${label}</button>`).join("")}</div><div class="reader-side-body">${body}</div>`;
}

function bindReaderSide(reader, job) {
  reader.querySelectorAll("[data-reader-side]").forEach((button) => {
    button.onclick = () => {
      readerSideTab = button.dataset.readerSide;
      const side = reader.querySelector(".reader-side");
      side.innerHTML = readerSidePanel(job);
      bindReaderSide(reader, job);
    };
  });
}

function showJob(job) {
  if ($("#modal").open && !$("#modal-body [data-dirty-guard]")) close();
  activeJob = job.id;
  const running = ["running", "queued"].includes(job.status),
    review = job.review,
    restorable = ["cancelled", "failed", "interrupted"].includes(job.status),
    reviewReasons = [
      job.open_comment_count ? `当前版本还有 ${job.open_comment_count} 条待处理批注` : "",
      (job.citation_issues || []).length ? `正文包含无法追溯的来源：${job.citation_issues.join("、")}` : "",
      (job.asset_issues || []).length ? `正文包含不存在的项目图片：${job.asset_issues.join("、")}` : "",
      ...(job.quality?.issues || []).filter((issue) => issue.severity === "error").map((issue) => issue.message),
    ].filter(Boolean),
    reviewBlocked = reviewReasons.length > 0,
    reviewReason = reviewReasons.join("；");
  const info = jobState({ ...job, review_decision: review?.decision || job.review_decision });
  const exportMenu = job.output ? `<div class="dropdown"><button class="small" data-reader-menu="export">导出 ▾</button><div class="dropdown-menu" data-menu="export" hidden><a href="/api/jobs/${E(job.id)}/download">Markdown</a><a href="/api/jobs/${E(job.id)}/export?format=docx">Word</a><a href="/api/jobs/${E(job.id)}/export?format=pdf">PDF</a><a href="/api/jobs/${E(job.id)}/export?format=xlsx">Excel</a><a href="/api/jobs/${E(job.id)}/export?format=csv">CSV</a></div></div>` : "";
  const topActions = [
    job.output ? `<button class="small" data-edit="${E(job.id)}">编辑</button>` : "",
    job.output ? `<button class="small" data-versions="${E(job.id)}">版本 ${job.version_count || 1}</button>` : "",
    exportMenu,
    running ? "" : `<button class="small ghost" data-archive-job="${E(job.id)}" data-archived="${job.archived ? "false" : "true"}">${job.archived ? "取消归档" : "归档"}</button>`,
  ].join("");
  let main = "";
  if (job.stale_upstream?.length) main += '<div class="banner reader-notice">上游内容已变化，请核对正文。工作台没有自动重写或取消本稿确认；再次确认只表示你已复核当前上游。</div>';
  if (job.error) main += `<div class="banner reader-notice">${E(job.error)}</div>`;
  if (job.status === "prepared") main += `<div class="reader-doc"><div class="card"><h2>任务已准备好</h2><p>执行时会把任务包里的项目背景和引用资料发送给 Codex 模型服务，使用你的账号额度。可以先在右侧「来源」和「任务信息」核对输入。</p><div class="actions"><button class="primary" data-run="${E(job.id)}" ${state.runtime.available ? "" : "disabled"}>开始生成</button><a class="button-link" href="/api/jobs/${E(job.id)}/prompt">下载任务包</a><button data-import="${E(job.id)}">导入已有结果</button><button class="ghost" data-cancel="${E(job.id)}">取消任务</button></div>${state.runtime.available ? "" : '<p class="help">未找到 Codex CLI。可以下载任务包，在其他会话中完成后导入结果。</p>'}</div></div>`;
  if (running) main += `<div class="reader-doc"><div class="progress-note"><span class="spinner"></span>正在生成，状态会自动更新。完整分析可能需要几分钟。<button class="small push-right" data-cancel="${E(job.id)}" data-running="true">停止生成</button></div></div>`;
  if (restorable) main += `<div class="reader-doc"><div class="card"><p>任务包和输入快照仍然保留。恢复后可以重新生成或导入已有结果。</p><button class="primary" data-restore-job="${E(job.id)}">恢复为待执行</button></div></div>`;
  if (job.output) {
    main += `<div class="reader-doc">${qualitySummary(job)}${reviewBlocked ? `<div class="banner" id="review-block-reason">暂不能确认：${E(reviewReason)}。</div>` : ""}<div class="document document-render">${renderMarkdown(job.output, true, (job.comments || []).filter((item) => item.version === job.current_version))}</div><div class="review-box"><h2>评审</h2><label for="review-note">整体意见（可选）</label><textarea id="review-note" maxlength="12000" placeholder="整份文档的总体意见；局部修改请在段落旁添加批注。">${E(review?.note || "")}</textarea><div class="actions review-actions mt-10"><button class="primary" data-review="accepted" data-id="${E(job.id)}" ${reviewBlocked ? 'disabled aria-describedby="review-block-reason"' : ""}>${job.stale_upstream?.length ? "已复核上游变化，重新确认" : "确认这份文档"}</button><button data-review="changes_requested" data-id="${E(job.id)}">记录需要修改</button>${review?.decision === "changes_requested" ? `<button data-revise="${E(job.id)}">按意见准备修订版</button>` : ""}</div><p class="help">确认只作用于本项目，后续任务会优先引用已确认的文档。</p><div id="reader-continue"></div></div></div>`;
  }
  const reader = readerShell();
  const previousMain = reader.querySelector(".reader-main");
  const scrollTop = previousMain ? previousMain.scrollTop : 0;
  const sameJob = reader.dataset.job === job.id && !reader.hidden;
  reader.dataset.job = job.id;
  reader.innerHTML = `<div class="reader-top"><button class="small ghost" data-reader-close aria-label="返回">← 返回</button><div class="reader-title"><h1>${E(job.title)}${job.revision_number > 1 ? ` · 修订 V${job.revision_number}` : ""}</h1><div class="reader-meta">${date(job.created)} · V${job.current_version || 1} · ${(job.sources || []).length} 段引用资料${job.archived ? " · 已归档" : ""}</div></div>${stateTag(info)}<div class="actions">${topActions}<button class="small ghost" data-reader-side-toggle title="批注与来源">☰</button></div></div><div class="reader-body"><div class="reader-main">${main || '<div class="reader-doc"><div class="empty compact">没有正文。</div></div>'}</div><aside class="reader-side">${readerSidePanel(job)}</aside></div>`;
  reader.hidden = false;
  document.body.classList.add("reader-open");
  if (sameJob) reader.querySelector(".reader-main").scrollTop = scrollTop;
  reader.querySelector("[data-reader-close]").onclick = closeReader;
  reader.querySelector("[data-reader-side-toggle]").onclick = () => reader.querySelector(".reader-body").classList.toggle("side-open");
  bindReaderSide(reader, job);
  reader.querySelectorAll("[data-reader-menu]").forEach((button) => {
    button.onclick = (event) => {
      event.stopPropagation();
      const menu = reader.querySelector(`[data-menu="${button.dataset.readerMenu}"]`);
      menu.hidden = !menu.hidden;
      if (!menu.hidden) document.addEventListener("click", () => (menu.hidden = true), { once: true });
    };
  });
  const continuation = f1ContinuationAction(job);
  const area = reader.querySelector("#reader-continue");
  if (continuation && area) {
    const button = document.createElement("button");
    button.className = "primary";
    button.textContent = continuation.label + " →";
    button.id = "continue-f1";
    button.onclick = async () => {
      try {
        if (continuation.type === "job") return showJob(await api(`/api/jobs/${continuation.jobId}`));
        if (continuation.type === "assemble") return assembleF1(continuation.taskKey, button);
        activeWorkflow = "new-product";
        activeWorkflowStage = continuation.type === "prototype" ? "prototype" : "analysis";
        if (continuation.type === "prototype") {
          tab = "workflow";
          closeReader();
          return;
        }
        prepareTask(continuation.taskKey, { documentIds: continuationReferenceIds(job) });
      } catch (err) { error(err); }
    };
    area.appendChild(button);
  }
}

function commentForm(job, block) {
  const reviewer = localStorage.getItem("workbench-reviewer") || "";
  modal(
    "添加定位批注",
    `<div class="split"><div><div class="eyebrow">V${job.current_version} / ${E(commentBlockNames[block.block_type] || block.block_type)}</div><h2>${E(block.block_label)}</h2></div><button data-job="${E(job.id)}">返回正文</button></div><div class="comment-quote">${E(block.quote)}</div><form id="comment-form"><label for="comment-action">希望怎么处理</label><select id="comment-action"><option value="modify">修改</option><option value="add">新增</option><option value="delete">删除</option><option value="compress">压缩</option><option value="preserve">保留，不允许后续改动</option></select><label for="comment-note">具体意见</label><textarea id="comment-note" maxlength="4000" required placeholder="例如：这里改成与竞品 A 的差异，并补充离线存档规则。"></textarea><label for="comment-author">提出人</label><input id="comment-author" maxlength="120" value="${E(reviewer)}" placeholder="姓名或角色（选填）"><div class="help">批注绑定当前 V${job.current_version} 和这段原文。正文版本变化后，它只作为历史记录保留。</div><button class="primary" type="submit">保存批注</button></form>`,
  );
  guardForm($("#comment-form"));
  $("#comment-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const author = $("#comment-author").value.trim();
      if (author) localStorage.setItem("workbench-reviewer", author);
      await api(`/api/jobs/${job.id}/comments`, {
        version: job.current_version,
        ...block,
        action: $("#comment-action").value,
        note: $("#comment-note").value,
        author,
      });
      showJob(await api(`/api/jobs/${job.id}`));
      toast("批注已添加到指定位置");
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

function editJob(job) {
  const images = imageDocuments();
  modal(
    "编辑交付物",
    `<div class="split"><h2>${E(job.title)}</h2><span class="tag">当前 V${job.current_version || 1}</span></div><div class="help">按 Markdown 直接修改。保存会生成新版本；如果原文已经确认，确认状态会被清除，新内容回到待评审草稿。</div><form id="edit-output-form"><label for="output-editor">正文</label><textarea id="output-editor" class="output-editor" maxlength="2000000" required>${E(job.output)}</textarea><div class="image-insert-panel"><label for="editor-image">插入项目图片</label><div class="actions"><select id="editor-image" ${images.length ? "" : "disabled"}>${images.map((image) => `<option value="${E(image.id)}" data-name="${E(image.name)}">${E(image.name)}</option>`).join("") || '<option>请先在“资料”上传图片</option>'}</select><input id="editor-image-caption" maxlength="120" placeholder="图片说明（可选）"><button type="button" id="insert-image" ${images.length ? "" : "disabled"}>插入到光标处</button></div><small>图片会以项目内部 asset:// 引用写入正文，导出 Word/PDF 时会一并带入。</small></div><label for="edit-note">修改说明（选填）</label><input id="edit-note" maxlength="500" placeholder="例如：补充核心流程，删减重复背景"><div class="form-footer"><button class="primary" type="submit">保存为新版本</button><button type="button" data-edit-cancel="${E(job.id)}">取消</button></div></form>`,
    { wide: true }
  );
  guardForm($("#edit-output-form"));
  if (images.length) {
    $("#insert-image").onclick = () => {
      const selector = $("#editor-image"), image = images.find((item) => item.id === selector.value);
      if (!image) return;
      const editor = $("#output-editor"), caption = $("#editor-image-caption").value.trim() || image.name;
      const snippet = `![${caption}](asset://${image.id})`;
      const start = editor.selectionStart ?? editor.value.length, end = editor.selectionEnd ?? start;
      editor.setRangeText(snippet, start, end, "end");
      editor.focus();
    };
  }
  $("#edit-output-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const updated = await api(`/api/jobs/${job.id}/edit`, {
        output: $("#output-editor").value,
        note: $("#edit-note").value,
      });
      await refresh();
      showJob(updated);
      toast(`已保存为 V${updated.current_version}`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

async function showVersions(jobId) {
  const [job, versions] = await Promise.all([
    api(`/api/jobs/${jobId}`),
    api(`/api/jobs/${jobId}/versions`),
  ]);
  modal(
    "版本记录",
    `<div class="split"><h2>${E(job.title)}</h2><button data-job="${E(job.id)}">返回正文</button></div><p class="muted">恢复旧版会另存为一个新版本，现有历史不会被覆盖。</p><div class="version-list">${versions.map((item) => `<div class="row"><div class="row-main"><h3>V${item.version} ${item.version === job.current_version ? '<span class="tag">当前版本</span>' : ""}</h3><p>${E(versionSourceNames[item.source] || item.source)} · ${date(item.created)} · ${item.characters} 字${item.note ? ` · ${E(item.note)}` : ""}</p></div><button data-view-version="${item.version}" data-id="${E(job.id)}">查看</button></div>`).join("")}</div>`,
  );
}

async function showVersion(jobId, versionNumber) {
  const [job, item] = await Promise.all([
    api(`/api/jobs/${jobId}`),
    api(`/api/jobs/${jobId}/versions/${versionNumber}`),
  ]);
  modal(
    `查看 V${item.version}`,
    `<div class="split"><div><h2>${E(job.title)}</h2><p class="muted">${E(versionSourceNames[item.source] || item.source)} · ${date(item.created)}${item.note ? ` · ${E(item.note)}` : ""}</p></div><button data-versions="${E(job.id)}">返回版本记录</button></div><div class="actions"><button class="primary" data-version-restore="${item.version}" data-id="${E(job.id)}" ${item.version === job.current_version ? "disabled" : ""}>恢复为新版本</button></div><div class="document document-render">${renderMarkdown(item.output)}</div>`,
  );
}
