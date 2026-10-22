"use strict";

/* materials.js: loaded by index.html before the app bootstrap. */

let pendingMaterialFiles = [];
let pastedImageSequence = 0;
let activeMaterialCategory = "all";
let activeImageSubcategory = "all";
let materialSearchQuery = "";

const materialCategories = [
  { id: "competitor", label: "竞品资料" },
  { id: "reviews", label: "评论数据" },
  { id: "images", label: "截图与图片" },
  { id: "policy", label: "政策与合规" },
  { id: "technical", label: "技术与日志" },
  { id: "research", label: "研究资料" },
  { id: "deliverable", label: "交付物" },
  { id: "other", label: "其他资料" },
];

const imageSubcategories = [
  { id: "competitor", label: "竞品截图" },
  { id: "prototype", label: "产品与原型" },
  { id: "data", label: "数据与报表" },
  { id: "policy", label: "政策与规则" },
  { id: "feedback", label: "用户反馈" },
  { id: "reference", label: "参考与素材" },
  { id: "other", label: "其他图片" },
];

function materialCategoryLabel(category) {
  return materialCategories.find((item) => item.id === category)?.label || "其他资料";
}

function materialCategoryOptions(document) {
  if (["accepted", "deliverable"].includes(document.kind)) {
    return '<span class="tag material-category-tag">交付物</span>';
  }
  return `<select class="material-category-control" data-document-category="${E(document.id)}" aria-label="设置 ${E(document.name)} 的分类">${materialCategories
    .filter((item) => item.id !== "deliverable")
    .map((item) => `<option value="${item.id}" ${item.id === document.category ? "selected" : ""}>${E(item.label)}</option>`)
    .join("")}</select>`;
}

function materialImageSubcategoryOptions(document) {
  return `<select class="material-category-control image-subcategory-control" data-document-subcategory="${E(document.id)}" aria-label="设置 ${E(document.name)} 的图片分类">${imageSubcategories
    .map((item) => `<option value="${item.id}" ${item.id === document.subcategory ? "selected" : ""}>${E(item.label)}</option>`)
    .join("")}</select>`;
}

function filterMaterialLibrary() {
  const root = $("#material-library");
  if (!root) return;
  const query = materialSearchQuery.trim().toLocaleLowerCase("zh-CN");
  let visibleCount = 0;
  root.querySelectorAll("[data-material-item]").forEach((item) => {
    const matchesCategory = activeMaterialCategory === "all" || item.dataset.materialCategory === activeMaterialCategory;
    const matchesQuery = !query || String(item.dataset.materialName || "").toLocaleLowerCase("zh-CN").includes(query);
    const matchesImageSubcategory = activeMaterialCategory !== "images" || activeImageSubcategory === "all" || item.dataset.materialSubcategory === activeImageSubcategory;
    item.hidden = !(matchesCategory && matchesQuery && matchesImageSubcategory);
    if (!item.hidden) visibleCount += 1;
  });
  root.querySelectorAll("[data-material-group]").forEach((group) => {
    const groupVisibleCount = group.querySelectorAll("[data-material-item]:not([hidden])").length;
    group.hidden = groupVisibleCount === 0;
    const count = group.querySelector("[data-material-group-count]");
    if (count) count.textContent = `${groupVisibleCount} 份资料`;
  });
  root.querySelectorAll("[data-material-filter]").forEach((button) => {
    const active = button.dataset.materialFilter === activeMaterialCategory;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  root.querySelectorAll("[data-image-subcategory-filter]").forEach((button) => {
    const active = button.dataset.imageSubcategoryFilter === activeImageSubcategory;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const status = $("#material-filter-status");
  const hasMaterials = Boolean(root.querySelector("[data-material-item]"));
  if (status) status.textContent = visibleCount ? `当前显示 ${visibleCount} 份` : hasMaterials ? "没有符合条件的资料" : "尚未添加资料";
  const empty = $("#material-filter-empty");
  if (empty) empty.hidden = visibleCount > 0 || !hasMaterials;
}

const acceptedMaterialSuffixes = new Set(["md", "txt", "csv", "json", "pdf", "docx", "png", "jpg", "jpeg", "webp"]);

function readableBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function clipboardImageName(file) {
  const stamp = new Date();
  const datePart = [stamp.getFullYear(), String(stamp.getMonth() + 1).padStart(2, "0"), String(stamp.getDate()).padStart(2, "0")].join("");
  const timePart = [String(stamp.getHours()).padStart(2, "0"), String(stamp.getMinutes()).padStart(2, "0"), String(stamp.getSeconds()).padStart(2, "0")].join("");
  pastedImageSequence += 1;
  const suffix = file.type === "image/jpeg" ? "jpg" : file.type === "image/webp" ? "webp" : "png";
  return `截图-${datePart}-${timePart}-${String(pastedImageSequence).padStart(2, "0")}.${suffix}`;
}

function pendingMaterialId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function renderPendingMaterials() {
  const container = $("#pending-materials");
  if (!container) return;
  const scopedFiles = pendingMaterialFiles.filter((item) => !item.project || (item.project === projectId && item.version === (currentVersion()?.id || "")));
  if (!scopedFiles.length) {
    container.innerHTML = '<div class="paste-empty">暂存区还没有资料。你可以连续截图并按 Ctrl+V，最后再统一上传。</div>';
    return;
  }
  const totalSize = scopedFiles.reduce((sum, item) => sum + item.file.size, 0);
  const previews = scopedFiles.map((item) => {
    const suffix = String(item.file.name).split(".").pop().toLowerCase();
    const preview = item.objectUrl
      ? `<img src="${E(item.objectUrl)}" alt="${E(item.file.name)} 预览">`
      : `<div class="pending-file-type">${E(suffix.toUpperCase())}</div>`;
    return `<article class="pending-material">${preview}<div><strong>${E(item.file.name)}</strong><small>${E(readableBytes(item.file.size))}${item.pasted ? " · 剪贴板截图" : ""} · 归属 ${E(item.competitorTitle || "项目公共资料")}</small></div><button class="icon-button" data-remove-pending-material="${E(item.id)}" aria-label="移除 ${E(item.file.name)}">×</button></article>`;
  }).join("");
  container.innerHTML = `<div class="pending-toolbar"><div><strong>待上传 ${scopedFiles.length} 份</strong><small>共 ${E(readableBytes(totalSize))}，确认后才写入项目</small></div><div class="actions"><button class="small" data-clear-pending-materials>清空当前范围</button><button class="primary" data-upload-pending-materials>一并上传</button></div></div><div class="pending-grid">${previews}</div>`;
}

function queueMaterialFiles(files, pasted = false) {
  const incoming = Array.from(files || []);
  if (!incoming.length) return;
  let added = 0;
  for (const original of incoming) {
    if (pendingMaterialFiles.length >= 30) {
      error(Error("一次最多暂存 30 份资料，请先上传当前批次。"));
      break;
    }
    if (original.size > 12 * 1024 * 1024) {
      error(Error((original.name || "剪贴板图片") + " 超过 12 MB"));
      continue;
    }
    let file = original;
    if (pasted && String(original.type || "").startsWith("image/")) {
      file = new File([original], clipboardImageName(original), { type: original.type || "image/png", lastModified: Date.now() });
    }
    const suffix = String(file.name || "").split(".").pop().toLowerCase();
    if (!acceptedMaterialSuffixes.has(suffix)) {
      error(Error(`${file.name || "该文件"} 的格式不支持`));
      continue;
    }
    const dossier = typeof dossierSession === "function" ? dossierSession().detail : "";
    const competitor = (state.competitors || []).find((item) => item.id === dossier);
    const key = `${projectId}:${currentVersion()?.id || ""}:${dossier}:${file.name}:${file.size}:${file.lastModified}`;
    if (pendingMaterialFiles.some((item) => item.key === key)) continue;
    pendingMaterialFiles.push({
      id: pendingMaterialId(),
      key,
      file,
      pasted,
      project: projectId,
      version: currentVersion()?.id || "",
      competitorId: competitor?.id || "",
      competitorTitle: competitor?.title || competitor?.app_id || "",
      materialType: competitor ? ($("#dossier-upload-type")?.value || "attachment") : "",
      objectUrl: String(file.type || "").startsWith("image/") ? URL.createObjectURL(file) : "",
    });
    added += 1;
  }
  renderPendingMaterials();
  if (added) toast(`已暂存 ${added} 份资料，可继续粘贴`);
}

function removePendingMaterial(id) {
  const item = pendingMaterialFiles.find((entry) => entry.id === id);
  if (item?.objectUrl) URL.revokeObjectURL(item.objectUrl);
  pendingMaterialFiles = pendingMaterialFiles.filter((entry) => entry.id !== id);
  renderPendingMaterials();
}

function clearPendingMaterials() {
  const current = (item) => !item.project || (item.project === projectId && item.version === (currentVersion()?.id || ""));
  pendingMaterialFiles.filter(current).forEach((item) => item.objectUrl && URL.revokeObjectURL(item.objectUrl));
  pendingMaterialFiles = pendingMaterialFiles.filter((item) => !current(item));
  renderPendingMaterials();
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(Error("文件读取失败"));
    reader.readAsDataURL(file);
  });
}

async function uploadPendingMaterials(button) {
  if (!pendingMaterialFiles.length) return;
  const scopeProject = projectId, scopeVersion = currentVersion()?.id || "";
  const batch = pendingMaterialFiles.filter((item) => !item.project || (item.project === scopeProject && item.version === scopeVersion));
  if (!batch.length) return;
  const failed = [];
  let successful = 0;
  button.disabled = true;
  button.textContent = `正在上传 0/${batch.length}`;
  for (const item of batch) {
    try {
      const content = await readFileAsBase64(item.file);
      await api("/api/documents", {
        project_id: item.project || scopeProject,
        version_id: item.version ?? scopeVersion,
        ...(item.competitorId ? {competitor_id:item.competitorId, material_type:item.materialType || "attachment"} : {}),
        name: item.file.name,
        content,
      });
      successful++;
      if (item.objectUrl) URL.revokeObjectURL(item.objectUrl);
    } catch (err) {
      error(err);
      failed.push(item);
    }
    button.textContent = `正在上传 ${successful}/${batch.length}`;
  }
  const batchIds = new Set(batch.map((item) => item.id));
  pendingMaterialFiles = [...pendingMaterialFiles.filter((item) => !batchIds.has(item.id)), ...failed];
  await refresh();
  toast(failed.length ? `已上传 ${successful} 份，${failed.length} 份失败并保留在暂存区` : `已上传 ${successful} 份资料`);
}

function upload(e) {
  queueMaterialFiles(e.target.files);
  e.target.value = "";
}

function handleMaterialPaste(e) {
  if (tab !== "materials" || !projectId || document.querySelector("dialog[open]")) return;
  const active = document.activeElement;
  if (active && (active.matches("input, textarea") || active.isContentEditable)) return;
  const files = Array.from(e.clipboardData?.items || [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter(Boolean);
  if (!files.length) return;
  e.preventDefault();
  queueMaterialFiles(files, true);
}

document.addEventListener("paste", handleMaterialPaste);

async function search() {
  const button = $("#search");
  button.disabled = true;
  try {
    const results = await api(
      "/api/search?project=" +
        projectId +
        "&q=" +
        encodeURIComponent($("#search-query").value),
    );
    $("#search-results").innerHTML =
      `<div class="help">${state.runtime.retrieval} · 保留原文片段供核对；检索排序不代表事实已经确认。</div>` +
      results
        .map(
          (r) =>
            `<div class="card"><h3>${E(r.name)} <span class="tag">${E(kinds[r.kind])}</span></h3><small>${E(r.location)} · 片段 ${r.chunk}</small><p class="excerpt">${E(r.text)}</p></div>`,
        )
        .join("") +
      (results.length
        ? ""
        : '<div class="empty">没有匹配依据，试试更具体的关键词。</div>');
  } catch (e) {
    error(e);
  } finally {
    button.disabled = false;
  }
}

function imageDocuments() {
  return (state?.documents || []).filter((document) => document.kind === "upload" && imageSuffixes.has(String(document.name).split(".").pop().toLowerCase()));
}

const csvHeaderNames = {
  review_id: "评论 ID",
  content: "评论内容",
  score: "评分",
  published_at: "发布时间",
  market: "市场",
  language: "语言",
  version: "App 版本",
  source: "来源",
  platform: "平台",
  app_id: "应用 ID",
  thumbs_up_count: "点赞数",
  user_name: "用户名",
  title: "评论标题",
  original_content: "评论原文",
  translated_content: "翻译",
  reply_content: "开发者回复",
  reply_at: "回复时间",
};

function csvRowsAsObjects(preview) {
  return (preview.rows || []).map((row) => Object.fromEntries((preview.headers || []).map((header, index) => [header, row[index] || ""])));
}

function reviewScore(value) {
  const number = Math.max(0, Math.min(5, Math.round(Number(value) || 0)));
  return `${"★".repeat(number)}${"☆".repeat(5 - number)}`;
}

function renderReviewCsv(document) {
  const preview = document.csv_preview;
  const translationState = preview.translation || { total: 0, translated: 0, missing: 0 };
  const rows = csvRowsAsObjects(preview);
  const scoreCounts = rows.reduce((counts, row) => {
    const score = Math.round(Number(row.score));
    if (Number.isFinite(score) && score >= 1 && score <= 5) {
      counts[score] = (counts[score] || 0) + 1;
    }
    return counts;
  }, {});
  const scoreSummary = [5, 4, 3, 2, 1].map((score) => `<span>${score} 星 ${scoreCounts[score] || 0}</span>`).join("");
  const cards = rows.map((row) => {
    const content = row.content || row.original_content || "（评论正文为空）";
    const translation = row.translated_content && row.translated_content !== content ? `<div class="review-translation"><b>中文翻译</b><p>${E(row.translated_content)}</p></div>` : "";
    const reply = row.reply_content ? `<div class="review-reply"><b>开发者回复${row.reply_at ? ` · ${E(row.reply_at)}` : ""}</b><p>${E(row.reply_content)}</p></div>` : "";
    const context = [row.market, row.language, row.version ? `App ${row.version}` : "", row.published_at].filter(Boolean).join(" · ");
    const author = [row.user_name || "匿名用户", row.thumbs_up_count ? `${row.thumbs_up_count} 个赞` : ""].filter(Boolean).join(" · ");
    return `<article class="review-card"><header><div><strong class="review-stars">${reviewScore(row.score)}</strong><span>${E(row.score || "未评分")}</span></div><small>${E(context)}</small></header>${row.title ? `<h3>${E(row.title)}</h3>` : ""}<p class="review-content">${E(content)}</p><footer><span>${E(author)}</span><details><summary>来源信息</summary><small>评论 ID：${E(row.review_id || "未提供")}<br>来源：${E(row.source || "未提供")}<br>应用 ID：${E(row.app_id || "未提供")}</small></details></footer>${translation}${reply}</article>`;
  }).join("");
  const translationAction = Number(translationState.missing || 0) > 0
    ? `<button class="primary small" data-translate-document="${E(document.id)}">补充中文翻译（剩余 ${Number(translationState.missing).toLocaleString()}）</button>`
    : "";
  const translationLabel = Number(translationState.total || 0) > 0
    ? ` · 中文译文 ${Number(translationState.translated || 0).toLocaleString()}/${Number(translationState.total).toLocaleString()}`
    : "";
  return `<div class="review-toolbar"><div><b>${Number(preview.total_rows || 0).toLocaleString()} 条评论</b><small>${preview.truncated ? "当前预览前 200 条" : "已显示全部评论"}${translationLabel}</small></div><div class="competitor-facts">${scoreSummary}</div><div class="actions">${translationAction}<a class="button-link" href="/api/documents/${encodeURIComponent(document.id)}/download">下载原始 CSV</a></div></div><div class="review-list">${cards || '<div class="empty">CSV 中没有可以显示的评论。</div>'}</div>`;
}

function renderCsvTable(document) {
  const preview = document.csv_preview;
  const headers = (preview.headers || []).map((header) => `<th>${E(csvHeaderNames[header] || header)}</th>`).join("");
  const rows = (preview.rows || []).map((row) => `<tr>${row.map((value) => `<td>${E(value)}</td>`).join("")}</tr>`).join("");
  return `<div class="review-toolbar"><div><b>${Number(preview.total_rows || 0).toLocaleString()} 行数据</b><small>${preview.truncated ? "当前预览前 200 行" : "已显示全部数据"}</small></div><a class="button-link" href="/api/documents/${encodeURIComponent(document.id)}/download">下载原始 CSV</a></div><div class="csv-table-scroll"><table class="csv-preview-table"><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function showDocument(document) {
  const suffix = String(document.name).split(".").pop().toLowerCase();
  let body;
  if (imageSuffixes.has(suffix)) {
    body = `<img class="document-image document-image-preview" src="/api/assets/${encodeURIComponent(projectId)}/${encodeURIComponent(document.id)}" alt="${E(document.name)}">`;
  } else if (document.csv_preview?.kind === "reviews") {
    body = renderReviewCsv(document);
  } else if (document.csv_preview) {
    body = renderCsvTable(document);
  } else {
    body = `<div class="document">${E(document.text)}</div>`;
  }
  modal("资料原文", `<h2>${E(document.name)}</h2>${body}`);
}
