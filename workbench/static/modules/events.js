"use strict";

/* Central event delegation; feature functions are loaded before this module. */

document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    if (b.dataset.project) {
      projectId = b.dataset.project;
      localStorage.setItem("workbench-project", projectId);
      tab = "overview";
      activeWorkflow = null;
      await refresh();
    } else if (b.dataset.tab) {
      tab = b.dataset.tab;
      draw();
    } else if (b.dataset.removePendingMaterial) {
      removePendingMaterial(b.dataset.removePendingMaterial);
    } else if (b.hasAttribute("data-clear-pending-materials")) {
      clearPendingMaterials();
    } else if (b.hasAttribute("data-upload-pending-materials")) {
      await uploadPendingMaterials(b);
    } else if (b.dataset.action === "new") newProject();
    else if (b.dataset.action === "delete-project") confirmDeleteProject();
    else if (b.dataset.trashRestore) {
      b.disabled = true;
      const project = await api("/api/trash/restore", { id: b.dataset.trashRestore });
      projectId = project.id;
      localStorage.setItem("workbench-project", projectId);
      tab = "overview";
      await refresh();
      toast(`项目「${project.name}」已恢复`);
    } else if (b.dataset.trashDelete) {
      confirmPermanentDeleteTrash(b.dataset.trashDelete, b.dataset.trashName);
    }
    else if (b.hasAttribute("data-close-modal")) close();
    else if (b.dataset.action === "capabilities") {
      tab = "capabilities";
      draw();
    } else if (b.dataset.action === "lanhu-config") {
      lanhuConfigForm();
    } else if (b.dataset.action === "review-scrape") {
      reviewScrapeForm();
    } else if (b.dataset.previewScrape) {
      await competitorPreview(b.dataset.previewScrape);
    } else if (b.dataset.confirmScrape) {
      b.disabled = true;
      const result = await api(`/api/reviews/scrape/${b.dataset.confirmScrape}/confirm`, {});
      close();
      await refresh();
      tab = "materials";
      draw();
      toast(`竞品资料已入库：${result.listing_title || result.app_id}`);
    } else if (b.dataset.retryScrape) {
      b.disabled = true;
      await api(`/api/reviews/scrape/${b.dataset.retryScrape}/retry`, {});
      await refresh();
      toast("已重新开始采集这个竞品");
    } else if (b.dataset.action === "new-version") {
      productVersionForm();
    } else if (b.dataset.versionEdit) {
      const item = (state.versions || []).find((version) => version.id === b.dataset.versionEdit);
      if (!item) throw Error("产品版本不存在或已更新");
      productVersionForm(item);
    } else if (b.dataset.versionSelect) {
      setActiveVersion(b.dataset.versionSelect);
      draw();
      toast(`已切换到 ${currentVersion()?.name || "产品级工作"}`);
    } else if (b.dataset.workflow) {
      activeWorkflow = b.dataset.workflow;
      drawTasks();
    } else if (b.hasAttribute("data-workflow-back")) {
      activeWorkflow = null;
      drawTasks();
    } else if (b.dataset.pack) {
      b.disabled = true;
      await api("/api/packs", {
        id: b.dataset.pack,
        enabled: b.dataset.enabled === "true",
      });
      await refresh();
      toast("能力设置已保存，项目任务已更新");
    } else if (b.dataset.f1Assemble) await assembleF1(b.dataset.f1Assemble, b);
    else if (b.dataset.task) prepareTask(b.dataset.task);
    else if (b.dataset.condition) {
      const item = (state.conditions || []).find((c) => c.id === b.dataset.condition);
      if (item) conditionForm(item);
    } else if (b.dataset.action === "new-condition") conditionForm();
    else if (b.dataset.job) showJob(await api("/api/jobs/" + b.dataset.job));
    else if (b.dataset.edit) editJob(await api("/api/jobs/" + b.dataset.edit));
    else if (b.dataset.editCancel)
      showJob(await api("/api/jobs/" + b.dataset.editCancel));
    else if (b.dataset.versions) await showVersions(b.dataset.versions);
    else if (b.dataset.viewVersion)
      await showVersion(b.dataset.id, b.dataset.viewVersion);
    else if (b.dataset.versionRestore) {
      b.disabled = true;
      const job = await api(
        `/api/jobs/${b.dataset.id}/versions/${b.dataset.versionRestore}`,
        {},
      );
      await refresh();
      showJob(job);
      toast(`已恢复并保存为 V${job.current_version}`);
    } else if (b.dataset.revise) {
      b.disabled = true;
      const job = await api("/api/jobs/" + b.dataset.revise + "/revise", {});
      await refresh();
      showJob(job);
    } else if (b.dataset.addComment) {
      const job = await api(`/api/jobs/${activeJob}`),
        block = renderedBlocks[b.dataset.addComment];
      if (!block) throw Error("批注位置已变化，请刷新正文后重试");
      commentForm(job, block);
    } else if (b.dataset.commentStatus) {
      b.disabled = true;
      await api(`/api/jobs/${b.dataset.id}/comments/${b.dataset.commentId}`, {
        status: b.dataset.commentStatus,
      });
      showJob(await api(`/api/jobs/${b.dataset.id}`));
      toast(b.dataset.commentStatus === "resolved" ? "批注已标记为解决" : "批注已重新打开");
    } else if (b.dataset.reviseComments) {
      b.disabled = true;
      const job = await api(
        `/api/jobs/${b.dataset.reviseComments}/revise-comments`,
        {},
      );
      await refresh();
      showJob(job);
      toast("已按当前版本的待处理批注准备修订任务");
    } else if (b.dataset.deleteImage) {
      const image = imageDocuments().find((item) => item.id === b.dataset.deleteImage);
      if (!image) throw Error("图片资料不存在或已被删除");
      if (!window.confirm(`确定删除图片“${image.name}”？只有未被正文、历史版本或任务引用的图片可以删除。`)) return;
      b.disabled = true;
      await api(`/api/documents/${encodeURIComponent(image.id)}/delete`, { project_id: projectId });
      await refresh();
      toast(`图片「${image.name}」已删除`);
    } else if (b.dataset.document) {
      showDocument(await api("/api/documents/" + b.dataset.document));
    } else if (b.dataset.translateDocument) {
      b.disabled = true;
      b.textContent = "正在翻译…";
      const result = await api(`/api/documents/${encodeURIComponent(b.dataset.translateDocument)}/translate`, {});
      showDocument(await api(`/api/documents/${encodeURIComponent(b.dataset.translateDocument)}`));
      await refresh();
      const remaining = Number(result.remaining_count || 0);
      toast(`新增 ${result.newly_translated} 条中文译文${remaining ? `，还有 ${remaining} 条可继续翻译` : ""}`);
    } else if (b.dataset.run) {
      b.disabled = true;
      showJob(await api("/api/jobs/" + b.dataset.run + "/start", {}));
      await refresh();
    } else if (b.dataset.cancel) {
      b.disabled = true;
      showJob(await api("/api/jobs/" + b.dataset.cancel + "/cancel", {}));
      await refresh();
    } else if (b.dataset.cancelScrape) {
      b.disabled = true;
      await api(`/api/reviews/scrape/${b.dataset.cancelScrape}/cancel`, {});
      await refresh();
      toast("评论采集已取消");
    } else if (b.dataset.restoreCancelled) {
      b.disabled = true;
      showJob(
        await api(
          "/api/jobs/" + b.dataset.restoreCancelled + "/restore-cancelled",
          {},
        ),
      );
      await refresh();
      toast("任务已恢复为待执行");
    } else if (b.dataset.restoreJob) {
      b.disabled = true;
      showJob(await api(`/api/jobs/${b.dataset.restoreJob}/restore`, {}));
      await refresh();
      toast("任务已恢复为待执行，可以重新生成或导入结果");
    } else if (b.dataset.archiveJob) {
      b.disabled = true;
      const archived = b.dataset.archived === "true";
      showJob(await api(`/api/jobs/${b.dataset.archiveJob}/archive`, { archived }));
      await refresh();
      toast(archived ? "任务已归档" : "任务已取消归档");
    } else if (b.dataset.review) {
      b.disabled = true;
      showJob(
        await api("/api/jobs/" + b.dataset.id + "/review", {
          decision: b.dataset.review,
          note: $("#review-note").value,
        }),
      );
      await refresh();
      toast("评审已保存");
    } else if (b.dataset.import) {
      const id = b.dataset.import;
      modal(
        "导入交付物",
        `<h2>把完成的文档放回当前任务</h2><p class="muted">适用于在现有 AI 对话中完成任务后保存结果。</p><form id="import-form"><textarea id="import-output" aria-label="交付物正文" required placeholder="粘贴完整中文 Markdown 正文…"></textarea><button class="primary" type="submit">保存为待评审交付物</button></form>`,
      );
      $("#import-form").onsubmit = async (ev) => {
        ev.preventDefault();
        ev.submitter.disabled = true;
        try {
          const job = await api("/api/jobs/" + id + "/import", {
            output: $("#import-output").value,
          });
          await refresh();
          showJob(job);
        } catch (err) {
          error(err);
          ev.submitter.disabled = false;
        }
      };
    }
  } catch (err) {
    error(err);
    b.disabled = false;
  }
});

document.addEventListener("change", (event) => {
  if (!event.target.matches(".active-version-select")) return;
  setActiveVersion(event.target.value);
  draw();
  toast(`已切换到 ${currentVersion()?.name || "产品级工作"}`);
});
