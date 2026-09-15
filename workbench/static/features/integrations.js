"use strict";

/* integrations.js: loaded by index.html before the app bootstrap. */

function lanhuConfigForm() {
  const config = state.integrations?.lanhu || {};
  modal(
    "配置 Lanhu MCP",
    `<h2>让工作台读取本机蓝湖连接。</h2><p class="muted">工作台只保存启动配置，不保存 Cookie、Token 或其他认证值。保存后会重新检测本机环境。</p><form id="lanhu-config-form"><label for="lanhu-command">启动命令</label><input id="lanhu-command" value="${E(config.command || "npx")}" readonly><label for="lanhu-package">MCP 包</label><input id="lanhu-package" value="${E(config.package || "mcp-lanhu")}" readonly><label for="lanhu-config-path">配置文件路径（可选）</label><input id="lanhu-config-path" maxlength="500" value="${E(config.config_path || "")}" placeholder="默认读取 ~/.codex/config.toml"><div class="help">未安装时：先安装 Node.js，再运行 <code>npx -y mcp-lanhu</code>。认证仍由你本机的 Codex 配置提供。</div><div class="actions"><button class="primary" type="submit">保存并检测</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  $("#lanhu-config-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      await api("/api/integrations/lanhu", {
        command: $("#lanhu-command").value,
        package: $("#lanhu-package").value,
        config_path: $("#lanhu-config-path").value,
        enabled: true,
      });
      close();
      await refresh();
      tab = "capabilities";
      draw();
      toast("Lanhu MCP 配置已保存并完成环境检测");
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

function reviewScrapeForm() {
  const config = state.integrations?.review_scraper || {};
  const active = currentVersion();
  modal(
    "批量采集竞品资料",
    `<h2>你指定竞品，工作台负责采集和可选翻译。</h2><p class="muted">每行粘贴一个 Google Play / App Store 链接、package name 或 App Store ID。不会搜索、推荐、自动选择竞品或分析评论。</p><form id="review-scrape-form"><label for="scrape-competitors">竞品列表（1–8 个）</label><textarea id="scrape-competitors" required maxlength="4000" rows="6" placeholder="com.fastemulator.gba&#10;https://play.google.com/store/apps/details?id=it.dbtecno.pizzaboygba&#10;https://apps.apple.com/us/app/example/id123456789"></textarea><div class="help">默认采集商店长短描述、基础信息、商店截图和原始评论。结果先进入待确认区，确认后才写入项目资料。</div><div class="checks"><label><input id="scrape-translate" type="checkbox" checked> 同时生成简体中文译文（会增加采集时间，原评论始终保留）</label></div><label for="scrape-countries">国家或地区代码</label><input id="scrape-countries" required value="us" placeholder="例如：us,gb,de"><div class="grid"><div><label for="scrape-count">每个国家评论数</label><input id="scrape-count" type="number" min="1" max="500" value="100"></div><div><label for="scrape-sort">评论排序</label><select id="scrape-sort"><option value="newest">最新</option><option value="relevant">相关</option></select></div><div><label for="scrape-date-from">开始日期（可选）</label><input id="scrape-date-from" type="date"></div><div><label for="scrape-date-to">结束日期（可选）</label><input id="scrape-date-to" type="date"></div></div><label for="scrape-root">桌面工具目录</label><input id="scrape-root" maxlength="500" value="${E(config.root || "")}" placeholder="C:\\Users\\simon\\Desktop\\competitor-analysis-platform"><div class="help">${E(config.message || "保存目录后会自动检测 app/scrapers.py 和 Python 环境。")} 翻译优先使用该工具已配置的 DeepSeek，失败时回退 Google 翻译。</div><div class="actions"><button class="primary" type="submit">保存配置并开始采集</button><button type="button" data-close-modal>取消</button></div></form>`,
  );
  $("#review-scrape-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      await api("/api/integrations/review-scraper", { root: $("#scrape-root").value, enabled: true });
      const result = await api("/api/competitors/collect", {
        project_id: projectId,
        version_id: active?.id || "",
        entries: $("#scrape-competitors").value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        countries: $("#scrape-countries").value.split(/[,，\s]+/).filter(Boolean),
        count_per_country: Number($("#scrape-count").value),
        sort: $("#scrape-sort").value,
        date_from: $("#scrape-date-from").value,
        date_to: $("#scrape-date-to").value,
        translate: $("#scrape-translate").checked,
      });
      close();
      await refresh();
      tab = "materials";
      draw();
      toast(`已开始采集 ${result.count} 个你指定的竞品`);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

async function competitorPreview(scrapeId) {
  const item = await api(`/api/reviews/scrape/${scrapeId}`);
  const listing = item.listing || {};
  const platform = item.platform === "app_store" ? "App Store" : "Google Play";
  const description = (value, empty) => `<div class="document competitor-description">${E(value || empty)}</div>`;
  modal(
    "竞品资料预览",
    `<div class="section-title"><div><h2>${E(listing.title || item.app_id)}</h2><p class="muted">${E(platform)} · ${E(listing.market || "未提供市场")} · ${E(listing.developer || "未提供开发者")}</p></div><span class="tag">${E(scrapeStatusNames[item.status] || item.status)}</span></div><div class="competitor-facts"><span>评论 ${Number(item.review_count || 0).toLocaleString()} 条</span>${item.translation_requested ? `<span>中文译文 ${Number(item.translated_count || 0).toLocaleString()} 条</span>` : ""}<span>截图 ${Number(item.screenshot_count || 0).toLocaleString()} 张</span><span>分类 ${E(listing.category || "未提供")}</span></div><h3>短描述</h3>${description(listing.short_description, "当前商店接口未提供短描述。")}${listing.promotional_text ? `<h3>Promotional Text</h3>${description(listing.promotional_text, "")}` : ""}<h3>长描述</h3>${description(listing.long_description, "当前商店接口未提供长描述。")}${item.error ? `<div class="banner">${E(item.error)}</div>` : ""}<p class="help">商店描述保持原文；评论译文单独保存，不覆盖原评论，也不进行总结或观点分析。来源：${E(listing.source_url || "未提供")}</p><div class="actions">${item.status === "ready" ? `<button class="primary" data-confirm-scrape="${E(item.id)}">确认进入项目资料</button>` : ""}<button data-close-modal>关闭</button></div>`,
  );
}
