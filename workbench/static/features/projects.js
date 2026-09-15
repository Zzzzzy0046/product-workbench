"use strict";

/* projects.js: loaded by index.html before the app bootstrap. */

function conditionForm(item = {}) {
  modal(
    item.id ? "更新条件" : "新增条件",
    `<form id="condition-form"><label for="condition-title">条件</label><textarea id="condition-title" maxlength="300" required>${E(item.title || "")}</textarea><div class="grid"><div><label for="condition-owner">Owner</label><input id="condition-owner" maxlength="120" required value="${E(item.owner || "")}"></div><div><label for="condition-due">截止时间</label><input id="condition-due" maxlength="80" required value="${E(item.due || "")}" placeholder="2026-09-18"></div><div><label for="condition-review-date">复核日期</label><input id="condition-review-date" maxlength="80" value="${E(item.review_date || item.due || "")}" placeholder="默认与截止时间相同"></div><div><label for="condition-status">状态</label><select id="condition-status">${Object.entries(conditionNames).map(([value, label]) => `<option value="${value}" ${item.status === value ? "selected" : ""}>${label}</option>`).join("")}</select></div><div><label for="condition-block">阻塞范围</label><select id="condition-block">${Object.entries(blockNames).map(([value, label]) => `<option value="${value}" ${item.block_level === value ? "selected" : ""}>${label}</option>`).join("")}</select></div></div><label for="condition-evidence">证据或决策记录</label><textarea id="condition-evidence" maxlength="4000" placeholder="链接、构建版本、测试结果、截图/录像索引；关闭或豁免时必填。">${E(item.evidence || "")}</textarea><button class="primary" type="submit">保存条件</button></form>`,
  );
  $("#condition-form").onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      await api("/api/conditions", {
        id: item.id,
        project_id: projectId,
        title: $("#condition-title").value,
        owner: $("#condition-owner").value,
        due: $("#condition-due").value,
        review_date: $("#condition-review-date").value,
        status: $("#condition-status").value,
        block_level: $("#condition-block").value,
        evidence: $("#condition-evidence").value,
      });
      close();
      await refresh();
      toast("条件已保存");
    } catch (err) {
      error(err);
      e.submitter.disabled = false;
    }
  };
}

function confirmPermanentDeleteTrash(id, name) {
  modal(
    "永久删除",
    `<h2>永久删除「${E(name)}」</h2><div class="banner">这会删除本机回收备份，之后无法恢复。</div><form id="trash-delete-form"><label for="trash-confirmation">输入完整项目名称</label><input id="trash-confirmation" autocomplete="off" required placeholder="${E(name)}"><div class="actions"><button class="danger" type="submit">永久删除</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  $("#trash-delete-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      await api("/api/trash/delete", {
        id,
        confirmation: $("#trash-confirmation").value,
      });
      close();
      await refresh();
      toast(`回收备份「${name}」已永久删除`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

function newProject() {
  modal(
    "新建项目",
    `<h2>先留下项目的起点。</h2><form id="new-form"><label for="project-name">项目名称</label><input id="project-name" required maxlength="100" placeholder="例如：GBA Emulator"><div class="grid"><div><label for="new-workflow-mode">工作流模式</label><select id="new-workflow-mode"><option value="fast">快速迭代（默认）</option><option value="full">完整研究</option></select></div><div><label for="new-platform">目标平台（可选）</label><select id="new-platform">${platformSelect("")}</select></div></div><label for="project-brief">想做什么，已经确定了什么？</label><textarea id="project-brief" maxlength="12000" placeholder="描述产品方向、对标竞品、核心能力和已知硬约束。暂时不知道的可以留空。"></textarea><div class="help">平台可选 Android、iOS 或双平台；不确定时可选择“未指定”。验证周期和团队资源不再作为项目输入项。快速模式默认品类已决定，不执行机会门否决。新建项目不会自动启动分析。</div><button class="primary" type="submit">创建项目</button></form>`,
  );
  $("#new-form").onsubmit = async (e) => {
    e.preventDefault();
    const b = e.submitter;
    b.disabled = true;
    try {
      const p = await api("/api/projects", {
        name: $("#project-name").value,
        brief: $("#project-brief").value,
        workflow_mode: $("#new-workflow-mode").value,
        platform: $("#new-platform").value,
      });
      projectId = p.id;
      localStorage.setItem("workbench-project", projectId);
      tab = "context";
      close();
      await refresh();
      toast("项目已创建");
    } catch (e) {
      error(e);
      b.disabled = false;
    }
  };
}

function importProjectDialog() {
  modal(
    "导入完整项目",
    `<h2>恢复或复制一个工作台项目</h2><p class="muted">选择由工作台导出的 .zip 项目包。导入会创建一个新的项目副本，不覆盖当前项目。</p><form id="project-import-form"><label for="project-package">项目包</label><input id="project-package" type="file" accept=".zip,application/zip" required><div class="help">项目背景、资料、图片、任务、版本、批注和评论采集记录会一起导入；正在执行的任务会标记为已中断，需要重新开始。</div><div class="actions"><button class="primary" type="submit">导入项目</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  $("#project-import-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const file = $("#project-package").files?.[0];
      if (!file) throw Error("请选择项目包");
      if (file.size > 200 * 1024 * 1024) throw Error("项目包超过 200 MB");
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(Error("项目包读取失败"));
        reader.readAsDataURL(file);
      });
      const project = await api("/api/projects/import", { content });
      projectId = project.id;
      localStorage.setItem("workbench-project", projectId);
      tab = "overview";
      close();
      await refresh();
      toast(`项目「${project.name}」已导入`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

function confirmDeleteProject() {
  const project = { ...state.project };
  modal(
    "删除项目",
    `<h2>确认删除「${E(project.name)}」</h2><div class="banner">项目、任务和交付物会移入本机回收站，可以稍后恢复。</div><p>请输入完整项目名称以继续：</p><form id="delete-project-form"><label for="delete-confirmation">${E(project.name)}</label><input id="delete-confirmation" autocomplete="off" required placeholder="输入完整项目名称"><div class="actions"><button class="danger" type="submit">移入回收站</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  $("#delete-project-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      await api("/api/project/delete", {
        id: project.id,
        confirmation: $("#delete-confirmation").value,
      });
      projectId = null;
      activeJob = null;
      localStorage.removeItem("workbench-project");
      close();
      await refresh();
      toast(`项目「${project.name}」已移入回收站`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}
