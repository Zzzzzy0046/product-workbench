"use strict";

function versionStorageKey() {
  return `workbench-version:${projectId || "none"}`;
}

function currentVersion() {
  const versions = state?.versions || [];
  const stored = localStorage.getItem(versionStorageKey()) || "";
  return versions.find((item) => item.id === stored) || null;
}

function setActiveVersion(versionId) {
  const value = String(versionId || "");
  if (value && !(state?.versions || []).some((item) => item.id === value)) {
    localStorage.removeItem(versionStorageKey());
    return;
  }
  if (value) localStorage.setItem(versionStorageKey(), value);
  else localStorage.removeItem(versionStorageKey());
}

function activeVersionSelect() {
  const active = currentVersion();
  return `<select class="active-version-select" aria-label="当前产品版本"><option value="">产品级工作</option>${(state.versions || [])
    .map((item) => `<option value="${E(item.id)}" ${active?.id === item.id ? "selected" : ""}>${E(item.name)} · ${E(productVersionStatusNames[item.status] || item.status)}</option>`)
    .join("")}</select>`;
}

function scopeLabel(item) {
  return item?.version_name ? `产品版本：${item.version_name}` : "产品级";
}

function productVersionForm(item = {}) {
  modal(
    item.id ? "编辑产品版本" : "新建产品版本",
    `<h2>${item.id ? `更新 ${E(item.name)}` : "为一次迭代建立工作范围"}</h2><p class="muted">产品版本用于归类本轮资料、评论、任务和交付物；不创建版本也可以继续做产品级工作。</p><form id="product-version-form"><label for="version-name">版本号或版本名</label><input id="version-name" required maxlength="80" value="${E(item.name || "")}" placeholder="例如：V1.2.0 或 首版 MVP"><div class="grid"><div><label for="version-type">版本类型</label><select id="version-type">${Object.entries(productVersionTypeNames).map(([value, label]) => `<option value="${value}" ${item.version_type === value ? "selected" : ""}>${E(label)}</option>`).join("")}</select></div><div><label for="version-status">状态</label><select id="version-status">${Object.entries(productVersionStatusNames).map(([value, label]) => `<option value="${value}" ${item.status === value ? "selected" : ""}>${E(label)}</option>`).join("")}</select></div><div><label for="version-target-date">目标日期（可选）</label><input id="version-target-date" maxlength="40" value="${E(item.target_date || "")}" placeholder="2026-10-01"></div></div><label for="version-goal">本版本唯一主目标（可选）</label><textarea id="version-goal" maxlength="2000" placeholder="只写这次迭代最重要的变化。">${E(item.goal || "")}</textarea><div class="actions"><button class="primary" type="submit">${item.id ? "保存版本" : "创建并切换"}</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  if (!item.version_type) $("#version-type").value = "feature";
  if (!item.status) $("#version-status").value = "planning";
  $("#product-version-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const payload = {
        project_id: projectId,
        name: $("#version-name").value,
        version_type: $("#version-type").value,
        status: $("#version-status").value,
        target_date: $("#version-target-date").value,
        goal: $("#version-goal").value,
      };
      const saved = await api(item.id ? `/api/product-versions/${item.id}` : "/api/product-versions", payload);
      setActiveVersion(saved.id);
      close();
      await refresh();
      tab = "settings";
      settingsSection = "versions";
      draw();
      toast(item.id ? "产品版本已更新" : `已创建并切换到 ${saved.name}`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

function drawVersions() {
  const versions = state.versions || [];
  const active = currentVersion();
  $("#settings-body").innerHTML = `<div class="section-title flush"><div><h2>产品版本</h2><p class="muted">一个项目是一个产品，产品版本是一次发布或迭代（与文档自己的 V1、V2 修订不同）。切换版本后，新资料、新采集和新任务默认归到该版本。</p></div><button class="primary small" data-action="new-version">＋ 新建版本</button></div><div class="list">${versions.map((item) => `<div class="row ${active?.id === item.id ? "selected-row" : ""}"><div class="row-main"><h3>${E(item.name)}${active?.id === item.id ? ' <span class="tag run">当前</span>' : ""}</h3><p>${E(productVersionTypeNames[item.version_type] || item.version_type)} · ${E(productVersionStatusNames[item.status] || item.status)}${item.target_date ? ` · 目标 ${E(item.target_date)}` : ""} · ${item.document_count} 份资料 · ${item.job_count} 个任务</p>${item.goal ? `<p>${E(item.goal)}</p>` : ""}</div><div class="actions">${active?.id === item.id ? "" : `<button class="small" data-version-select="${E(item.id)}">切换</button>`}<button class="small" data-version-edit="${E(item.id)}">编辑</button></div></div>`).join("") || '<div class="empty compact">还没有产品版本。新品分析可以先按产品级运行，进入具体迭代时再创建。</div>'}</div>`;
}
