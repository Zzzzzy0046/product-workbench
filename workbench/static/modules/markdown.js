"use strict";

/* markdown.js: loaded by index.html before the app bootstrap. */

function renderMarkdown(text, annotate = false, comments = []) {
  // Escape before formatting. Raw HTML and embedded media are never executed.
  const inline = (s) =>
    E(s)
      .replace(/!\[([^\]]*)\]\(asset:\/\/([a-f0-9]{16,64})\)/gi, (_, alt, id) => `<img class="document-image" src="/api/assets/${encodeURIComponent(projectId || "")}/${id}" alt="${E(alt || "项目图片")}">`)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  const plain = (s) =>
    String(s)
      .replace(/\*\*|__|`|^#+\s*/g, "")
      .replace(/\s+/g, " ")
      .trim();
  let lines = text.split("\n");
  let out = "",
    table = [],
    code = [];
  let inCode = false,
    blockIndex = 0;
  if (annotate) renderedBlocks = {};
  if (lines[0]?.trim() === "---") {
    const closing = lines.slice(1).findIndex((line) => line.trim() === "---");
    if (closing >= 0) {
      const metadata = lines.slice(1, closing + 1).join("\n");
      out += `<details class="frontmatter"><summary>文档元数据</summary><pre>${E(metadata)}</pre></details>`;
      lines = lines.slice(closing + 2);
    }
  }
  const addBlock = (type, label, quote, html) => {
    if (!annotate) {
      out += html;
      return;
    }
    const id = `block-${++blockIndex}`;
    const block = {
      block_id: id,
      block_type: type,
      block_label: plain(label).slice(0, 300) || `未命名${type}`,
      quote: String(quote).trim().slice(0, 1200),
    };
    renderedBlocks[id] = block;
    const related = comments.filter((item) => item.quote === block.quote);
    const open = related.filter((item) => item.status === "open").length;
    const labelText = related.length
      ? `${related.length} 条批注${open ? ` · ${open} 条待处理` : ""}`
      : "添加批注";
    out += `<div class="commentable-block ${related.length ? "has-comments" : ""}"><div class="commentable-content">${html}</div><button class="comment-button" aria-label="${E(labelText)}：${E(block.block_label)}" data-add-comment="${id}" type="button">${E(labelText)}</button></div>`;
  };
  const flushTable = () => {
    if (!table.length) return;
    const raw = table.join("\n");
    const tableHtml =
      '<div class="table-scroll"><table>' +
      table
        .filter((l) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(l))
        .map(
          (l, i) =>
            "<tr>" +
            l
              .trim()
              .replace(/^\||\|$/g, "")
              .split("|")
              .map(
                (c) =>
                  `<${i === 0 ? "th" : "td"}>${inline(c.trim())}</${i === 0 ? "th" : "td"}>`,
              )
              .join("") +
            "</tr>",
        )
        .join("") +
      "</table></div>";
    addBlock("table", plain(table[0]).slice(0, 80) || "表格", raw, tableHtml);
    table = [];
  };
  const flushCode = () => {
    if (!code.length) return;
    const raw = code.join("\n");
    addBlock("code", raw.slice(0, 80) || "代码块", raw, `<pre><code>${E(raw)}</code></pre>`);
    code = [];
  };
  for (const line of lines) {
    if (line.startsWith("```")) {
      flushTable();
      if (inCode) flushCode();
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    if (line.trim().startsWith("|")) {
      table.push(line);
      continue;
    }
    flushTable();
    const heading = line.match(/^(#{1,6}) (.*)/);
    if (heading)
      addBlock(
        "heading",
        heading[2],
        line,
        `<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`,
      );
    else if (line.startsWith("> "))
      addBlock(
        "blockquote",
        line.slice(2, 82),
        line,
        "<blockquote>" + inline(line.slice(2)) + "</blockquote>",
      );
    else if (line.trim())
      addBlock(
        "paragraph",
        line.slice(0, 80),
        line,
        "<p>" + inline(line) + "</p>",
      );
  }
  flushTable();
  if (inCode || code.length) flushCode();
  return out;
}
