"use strict";

/* outputs.js: loaded by index.html before the app bootstrap. */

function commentsPanel(job) {
  const current = (job.comments || []).filter(
      (item) => item.version === job.current_version,
    ),
    historyCount = (job.comments || []).length - current.length,
    open = current.filter((item) => item.status === "open");
  return `<section class="comments-panel"><div class="split"><div><div class="eyebrow">定位批注 / V${job.current_version}</div><h3>按章节、段落或表格提出修改</h3></div>${open.length ? `<button class="primary" data-revise-comments="${E(job.id)}">按 ${open.length} 条批注精确修订</button>` : ""}</div><p class="muted">批注只属于当前版本。修订任务成功生成新版后，本次使用的批注会自动标记为已解决；生成前不会改变原批注。</p><div class="comment-list">${current
    .map(
      (item) =>
        `<article class="comment-item ${item.status === "resolved" ? "resolved" : ""}"><div class="split"><div class="chipline"><span class="tag">${E(commentActionNames[item.action] || item.action)}</span><span class="tag ${item.status === "open" ? "warn" : ""}">${item.status === "open" ? "待处理" : "已解决"}</span></div><button class="small" data-comment-status="${item.status === "open" ? "resolved" : "open"}" data-comment-id="${E(item.id)}" data-id="${E(job.id)}">${item.status === "open" ? "标记已解决" : "重新打开"}</button></div><strong>${E(item.block_label)}</strong><div class="comment-quote">${E(item.quote)}</div><p>${E(item.note)}</p><small>${E(item.author)} · ${date(item.created)}</small></article>`,
    )
    .join("") || '<div class="empty compact">当前版本还没有批注。</div>'}</div>${historyCount ? `<p class="muted">另有 ${historyCount} 条旧版本批注，仅保留为历史记录，不会用于本次修订。</p>` : ""}</section>`;
}

function qualitySummary(job) {
  const quality = job.quality || { issues: [], errors: 0, warnings: 0, ok: true };
  if (!quality.issues?.length) return '<div class="quality-check quality-ok">轻量质量校验：已通过，未发现阻断项。</div>';
  return `<div class="quality-check ${quality.errors ? "quality-has-errors" : "quality-has-warnings"}"><strong>轻量质量校验：${quality.errors ? `${quality.errors} 个阻断项` : "无阻断项"}${quality.warnings ? ` · ${quality.warnings} 个提示` : ""}</strong><ul>${quality.issues.map((issue) => `<li class="${issue.severity === "error" ? "quality-error" : "quality-warning"}"><span class="tag ${issue.severity === "error" ? "bad" : "warn"}">${issue.severity === "error" ? "阻断" : "提示"}</span> ${E(issue.message)}${issue.hint ? `<small>建议：${E(issue.hint)}</small>` : ""}</li>`).join("")}</ul></div>`;
}

function showJob(job) {
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
  const outputHtml = job.output
    ? `<div class="actions"><button class="primary" data-edit="${E(job.id)}">编辑正文</button><button data-versions="${E(job.id)}">版本记录（${job.version_count || 1}）</button><a href="/api/jobs/${E(job.id)}/download">下载 Markdown</a><a href="/api/jobs/${E(job.id)}/export?format=docx">Word</a><a href="/api/jobs/${E(job.id)}/export?format=pdf">PDF</a><a href="/api/jobs/${E(job.id)}/export?format=xlsx">Excel</a><a href="/api/jobs/${E(job.id)}/export?format=csv">CSV</a><span class="tag">${review ? (review.decision === "accepted" ? "已确认 · 可用于后续任务" : "需要修改") : "尚未评审"}</span></div>${qualitySummary(job)}${reviewBlocked ? `<div class="banner" id="review-block-reason">暂不能确认：${E(reviewReason)}。请处理后再确认。</div>` : ""}<div class="document document-render">${renderMarkdown(job.output, true, (job.comments || []).filter((item) => item.version === job.current_version))}</div>${commentsPanel(job)}<div class="help">评审重点：核心场景是否齐全、关键结论是否有证据、异常与边界是否闭合。确认只作用于此项目，不会自动发布为全局知识。</div><label for="review-note">整份文档评审（可选）</label><textarea id="review-note" maxlength="12000" placeholder="这里用于整份文档的总体意见；局部修改请直接在正文旁添加批注。">${E(review?.note || "")}</textarea><div class="actions review-actions"><button class="primary" data-review="accepted" data-id="${E(job.id)}" ${reviewBlocked ? 'disabled aria-describedby="review-block-reason"' : ""}>确认这份交付物</button><button data-review="changes_requested" data-id="${E(job.id)}">记录整体修改意见</button></div>`
    : "";
  modal(
    "任务记录",
    `<div class="split"><div><h2>${E(job.title)}${job.revision_number > 1 ? ` · 修订 V${job.revision_number}` : ""}</h2><div class="chipline"><span class="tag">生成时模式：${E(workflowNames[job.workflow_mode] || job.workflow_mode)}</span>${job.is_latest === 0 || job.has_newer_revision ? '<span class="tag">已有后续修订</span>' : '<span class="tag">当前分支最新版</span>'}${job.archived ? '<span class="tag">已归档</span>' : ""}</div></div>${badge(job.status)}</div><p class="muted">${date(job.created)} · ${job.sources.length} 段资料已快照保存${job.parent_job_id ? ` · 修订自上一任务 V${job.source_version || 1}` : ""}</p><div class="actions">${job.parent_job_id ? `<button class="small" data-job="${E(job.parent_job_id)}">查看上一任务</button>` : ""}${running ? "" : `<button class="small" data-archive-job="${E(job.id)}" data-archived="${job.archived ? "false" : "true"}">${job.archived ? "取消归档" : "归档任务"}</button>`}</div>${job.error ? `<div class="banner">${E(job.error)}</div>` : ""}${job.status === "prepared" ? `<div class="help">执行将把任务包中的项目背景和引用资料发送给 Codex 模型服务，使用你的账号额度。先检查下方输入依据；生成后仍需评审。</div><div class="actions"><button class="primary" data-run="${E(job.id)}" ${state.runtime.available ? "" : "disabled"}>开始生成</button><a href="/api/jobs/${E(job.id)}/prompt">下载任务包</a><button data-import="${E(job.id)}">导入已有结果</button><button data-cancel="${E(job.id)}">取消任务</button></div>` : ""}${running ? `<div class="progress-note"><span class="spinner"></span>正在生成，状态会自动更新。完整分析可能需要几分钟。</div><button data-cancel="${E(job.id)}">停止生成</button>` : ""}${restorable ? `<div class="help">任务包和输入快照仍然保留。恢复后可以重新生成或导入已有结果，原错误记录不会写进交付物。</div><button class="primary" data-restore-job="${E(job.id)}">恢复为待执行</button>` : ""}${outputHtml}<details><summary>本次输入：项目背景、完整模板与任务要求</summary><pre class="document">${E(job.prompt)}</pre></details><details><summary>查看 ${job.sources.length} 段引用资料</summary>${job.sources.map((s) => `<div class="card"><h3>[${E(s.citation)}] ${E(s.name)}</h3><small>${E(kinds[s.kind])} · 片段 ${s.chunk}${s.truncated ? " · 超出 12000 字，已截断" : ""}</small><div class="excerpt">${E(s.text)}</div></div>`).join("") || "<p>没有检索到匹配材料。</p>"}</details>`,
  );
  if (review?.decision === "changes_requested") {
    const button = document.createElement("button");
    button.textContent = "按意见准备修订版";
    button.dataset.revise = job.id;
    $("#modal-body .review-actions").append(button);
  }
}

function commentForm(job, block) {
  const reviewer = localStorage.getItem("workbench-reviewer") || "";
  modal(
    "添加定位批注",
    `<div class="split"><div><div class="eyebrow">V${job.current_version} / ${E(commentBlockNames[block.block_type] || block.block_type)}</div><h2>${E(block.block_label)}</h2></div><button data-job="${E(job.id)}">返回正文</button></div><div class="comment-quote">${E(block.quote)}</div><form id="comment-form"><label for="comment-action">希望怎么处理</label><select id="comment-action"><option value="modify">修改</option><option value="add">新增</option><option value="delete">删除</option><option value="compress">压缩</option><option value="preserve">保留，不允许后续改动</option></select><label for="comment-note">具体意见</label><textarea id="comment-note" maxlength="4000" required placeholder="例如：这里改成与竞品 A 的差异，并补充离线存档规则。"></textarea><label for="comment-author">提出人</label><input id="comment-author" maxlength="120" value="${E(reviewer)}" placeholder="姓名或角色（选填）"><div class="help">批注绑定当前 V${job.current_version} 和这段原文。正文版本变化后，它只作为历史记录保留。</div><button class="primary" type="submit">保存批注</button></form>`,
  );
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
    `<div class="split"><h2>${E(job.title)}</h2><span class="tag">当前 V${job.current_version || 1}</span></div><div class="help">按 Markdown 直接修改。保存会生成新版本；如果原文已经确认，确认状态会被清除，新内容回到待评审草稿。</div><form id="edit-output-form"><label for="output-editor">正文</label><textarea id="output-editor" class="output-editor" maxlength="2000000" required>${E(job.output)}</textarea><div class="image-insert-panel"><label for="editor-image">插入项目图片</label><div class="actions"><select id="editor-image" ${images.length ? "" : "disabled"}>${images.map((image) => `<option value="${E(image.id)}" data-name="${E(image.name)}">${E(image.name)}</option>`).join("") || '<option>请先在“资料”上传图片</option>'}</select><input id="editor-image-caption" maxlength="120" placeholder="图片说明（可选）"><button type="button" id="insert-image" ${images.length ? "" : "disabled"}>插入到光标处</button></div><small>图片会以项目内部 asset:// 引用写入正文，导出 Word/PDF 时会一并带入。</small></div><label for="edit-note">修改说明（选填）</label><input id="edit-note" maxlength="500" placeholder="例如：补充核心流程，删减重复背景"><div class="actions"><button class="primary" type="submit">保存为新版本</button><button type="button" data-edit-cancel="${E(job.id)}">取消</button></div></form>`,
  );
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
