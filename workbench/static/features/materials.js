"use strict";

/* materials.js: loaded by index.html before the app bootstrap. */

async function upload(e) {
  const files = Array.from(e.target.files),
    input = e.target;
  input.disabled = true;
  let successful = 0;
  for (const file of files) {
    try {
      if (file.size > 12 * 1024 * 1024) throw Error(file.name + " 超过 12 MB");
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(Error("文件读取失败"));
        reader.readAsDataURL(file);
      });
      const r = await api("/api/documents", {
        project_id: projectId,
        version_id: currentVersion()?.id || "",
        name: file.name,
        content,
      });
      successful++;
      toast(
        r.duplicate ? file.name + " 已存在，已关联到当前范围" : file.name + " 已导入",
      );
    } catch (err) {
      error(err);
    }
  }
  await refresh();
  toast(`已处理 ${successful}/${files.length} 份资料`);
}

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
