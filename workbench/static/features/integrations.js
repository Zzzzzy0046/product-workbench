"use strict";

/* integrations.js: loaded by index.html before the app bootstrap. */

const competitorCountries = [
  ["us", "美国", "北美"], ["ca", "加拿大", "北美"],
  ["gb", "英国", "欧洲"], ["de", "德国", "欧洲"], ["fr", "法国", "欧洲"],
  ["it", "意大利", "欧洲"], ["es", "西班牙", "欧洲"], ["pt", "葡萄牙", "欧洲"],
  ["nl", "荷兰", "欧洲"], ["be", "比利时", "欧洲"], ["ch", "瑞士", "欧洲"],
  ["at", "奥地利", "欧洲"], ["se", "瑞典", "欧洲"], ["no", "挪威", "欧洲"],
  ["dk", "丹麦", "欧洲"], ["fi", "芬兰", "欧洲"], ["pl", "波兰", "欧洲"],
  ["cz", "捷克", "欧洲"], ["ro", "罗马尼亚", "欧洲"], ["hu", "匈牙利", "欧洲"],
  ["ua", "乌克兰", "欧洲"], ["ru", "俄罗斯", "欧洲"], ["tr", "土耳其", "欧洲"],
  ["id", "印度尼西亚", "东南亚"], ["th", "泰国", "东南亚"], ["vn", "越南", "东南亚"],
  ["ph", "菲律宾", "东南亚"], ["sg", "新加坡", "东南亚"], ["my", "马来西亚", "东南亚"],
  ["jp", "日本", "东亚"], ["kr", "韩国", "东亚"], ["tw", "台湾", "东亚"], ["hk", "香港", "东亚"],
  ["in", "印度", "南亚"], ["pk", "巴基斯坦", "南亚"], ["bd", "孟加拉国", "南亚"],
  ["br", "巴西", "拉美"], ["mx", "墨西哥", "拉美"], ["ar", "阿根廷", "拉美"],
  ["co", "哥伦比亚", "拉美"], ["cl", "智利", "拉美"], ["pe", "秘鲁", "拉美"],
  ["ae", "阿联酋", "中东"], ["sa", "沙特阿拉伯", "中东"], ["eg", "埃及", "中东"], ["il", "以色列", "中东"],
  ["za", "南非", "非洲"], ["ng", "尼日利亚", "非洲"],
  ["au", "澳大利亚", "大洋洲"], ["nz", "新西兰", "大洋洲"],
];

const competitorCountryPresets = {
  english: ["us", "gb", "ca", "au"],
  southeast_asia: ["id", "th", "vn", "ph", "sg", "my"],
  western_europe: ["gb", "de", "fr", "it", "es", "nl"],
  latin_america: ["br", "mx", "ar", "co", "cl", "pe"],
  middle_east: ["ae", "sa", "eg"],
};

function reviewFilterSummary(request) {
  const parts = [];
  if (Array.isArray(request.ratings) && request.ratings.length) parts.push(`${request.ratings.join("/")} 星`);
  if (request.include_keywords?.length) parts.push(`含关键词 ${request.include_keywords.join("/")}`);
  if (request.exclude_keywords?.length) parts.push(`排除 ${request.exclude_keywords.join("/")}`);
  if (request.reply_filter === "replied") parts.push("仅有开发者回复");
  if (request.reply_filter === "unreplied") parts.push("仅无开发者回复");
  if (request.version_filter) parts.push(`版本含 ${request.version_filter}`);
  if (Number(request.min_thumbs_up || 0) > 0) parts.push(`点赞 ≥ ${Number(request.min_thumbs_up)}`);
  return parts.join(" · ");
}

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
  let selectedCountries = new Set(["us"]);
  const countryChoices = (query = "") => {
    const needle = String(query || "").trim().toLowerCase();
    const rows = competitorCountries.filter(([code, name, region]) => !needle || `${code} ${name} ${region}`.toLowerCase().includes(needle));
    return rows.map(([code, name, region]) => `<label class="country-choice"><input type="checkbox" value="${code}" ${selectedCountries.has(code) ? "checked" : ""}><span>${name}</span><small>${code.toUpperCase()} · ${region}</small></label>`).join("") || '<div class="empty compact">没有匹配地区，可在下方添加两位代码。</div>';
  };
  modal(
    "批量采集竞品资料",
    `<h2>采集你指定的竞品资料</h2><p class="muted">先选竞品和市场，再限定评论范围。不会搜索或自动选择竞品。</p><form id="review-scrape-form" class="scrape-form">
      <section class="scrape-step"><div class="scrape-step-title"><span>1</span><div><h3>竞品</h3><p>每行一个商店链接、package name 或 App Store ID，最多 8 个。</p></div></div><label class="visually-hidden" for="scrape-competitors">竞品列表（1–8 个）</label><textarea id="scrape-competitors" required maxlength="4000" rows="5" placeholder="com.fastemulator.gba&#10;https://play.google.com/store/apps/details?id=it.dbtecno.pizzaboygba&#10;https://apps.apple.com/us/app/example/id123456789"></textarea></section>
      <section class="scrape-step"><div class="scrape-step-title"><span>2</span><div><h3>国家或地区</h3><p>可多选，商店信息使用第一个市场；评论会采集全部已选市场。</p></div></div><div class="country-presets"><button type="button" data-country-preset="english">英语核心</button><button type="button" data-country-preset="southeast_asia">东南亚</button><button type="button" data-country-preset="western_europe">西欧</button><button type="button" data-country-preset="latin_america">拉美</button><button type="button" data-country-preset="middle_east">中东</button><button type="button" data-country-preset="clear">清空</button></div><label class="visually-hidden" for="country-search">搜索国家或地区</label><input id="country-search" class="country-search" type="search" placeholder="搜索国家、地区或代码"><div id="country-options" class="country-options">${countryChoices()}</div><div id="country-selection" class="selection-summary" aria-live="polite"></div><details class="custom-country"><summary>列表里没有？添加其他地区代码</summary><label for="scrape-custom-countries">两位国家或地区代码（可选）</label><input id="scrape-custom-countries" maxlength="120" placeholder="例如：ie,gr"></details></section>
      <section class="scrape-step"><div class="scrape-step-title"><span>3</span><div><h3>评论范围与筛选</h3><p>筛选在抓取后、翻译前执行；筛选条件越窄，最终条数可能越少。</p></div></div><div class="grid scrape-range-grid"><div><label for="scrape-count">每个国家抓取上限（筛选前）</label><input id="scrape-count" type="number" min="1" max="500" value="100"></div><div><label for="scrape-sort">评论排序</label><select id="scrape-sort"><option value="newest">最新</option><option value="relevant">相关</option></select></div><div><label for="scrape-date-from">开始日期（可选）</label><input id="scrape-date-from" type="date"></div><div><label for="scrape-date-to">结束日期（可选）</label><input id="scrape-date-to" type="date"></div></div><div class="filter-box"><div><label>只保留这些评分</label><small>不勾选表示全部评分</small></div><div class="rating-choices">${[1, 2, 3, 4, 5].map((rating) => `<label><input type="checkbox" name="scrape-rating" value="${rating}"><span>${rating} 星</span></label>`).join("")}</div><div class="grid filter-grid"><div><label for="scrape-include-keywords">包含关键词（任意一个）</label><input id="scrape-include-keywords" maxlength="500" placeholder="例如：ads, crash, save"></div><div><label for="scrape-exclude-keywords">排除关键词</label><input id="scrape-exclude-keywords" maxlength="500" placeholder="例如：giveaway, promo"></div><div><label for="scrape-reply-filter">开发者回复</label><select id="scrape-reply-filter"><option value="any">不限</option><option value="replied">仅有回复</option><option value="unreplied">仅无回复</option></select></div><div><label for="scrape-version-filter">App 版本包含</label><input id="scrape-version-filter" maxlength="100" placeholder="例如：2.3"></div><div><label for="scrape-min-thumbs">最低点赞数</label><input id="scrape-min-thumbs" type="number" min="0" max="1000000" value="0"></div></div></div></section>
      <div class="checks"><label><input id="scrape-translate" type="checkbox" checked> 对筛选后保留的评论生成简体中文译文（原评论始终保留）</label></div>
      <details class="scrape-settings"><summary>采集器设置</summary><label for="scrape-root">桌面工具目录</label><input id="scrape-root" maxlength="500" value="${E(config.root || "")}" placeholder="C:\\Users\\simon\\Desktop\\competitor-analysis-platform"><div class="help">${E(config.message || "保存目录后会自动检测 app/scrapers.py 和 Python 环境。")} 翻译优先使用已配置的 DeepSeek，失败时回退 Google 翻译。</div></details>
      <div class="scrape-submit"><div><strong id="scrape-scope-summary"></strong><small>结果先进入待确认区，确认后才写入项目资料。</small></div><div class="actions"><button class="primary" type="submit">开始采集</button><button type="button" data-close-modal>取消</button></div></div></form>`,
  );
  const renderCountryPicker = () => {
    $("#country-options").innerHTML = countryChoices($("#country-search").value);
    $("#country-selection").textContent = selectedCountries.size
      ? `已选 ${selectedCountries.size} 个：${Array.from(selectedCountries).map((code) => code.toUpperCase()).join("、")}`
      : "还没有选择国家或地区";
    $("#scrape-scope-summary").textContent = selectedCountries.size ? `当前选择 ${selectedCountries.size} 个市场` : "请选择至少一个市场";
    $("#country-options").onchange = (event) => {
      const input = event.target.closest('input[type="checkbox"]');
      if (!input) return;
      if (input.checked && selectedCountries.size >= 20) {
        input.checked = false;
        toast("一次最多选择 20 个市场");
        return;
      }
      if (input.checked) selectedCountries.add(input.value);
      else selectedCountries.delete(input.value);
      renderCountryPicker();
    };
  };
  $("#country-search").oninput = renderCountryPicker;
  document.querySelectorAll("[data-country-preset]").forEach((button) => {
    button.onclick = () => {
      selectedCountries = new Set(competitorCountryPresets[button.dataset.countryPreset] || []);
      renderCountryPicker();
    };
  });
  renderCountryPicker();
  $("#review-scrape-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const customCountries = $("#scrape-custom-countries").value.split(/[,，\s]+/).map((item) => item.trim().toLowerCase()).filter(Boolean);
      const countries = Array.from(new Set([...selectedCountries, ...customCountries]));
      if (!countries.length) throw Error("请至少选择一个国家或地区。");
      if (countries.length > 20) throw Error("一次最多选择 20 个国家或地区。");
      await api("/api/integrations/review-scraper", { root: $("#scrape-root").value, enabled: true });
      const result = await api("/api/competitors/collect", {
        project_id: projectId,
        version_id: active?.id || "",
        entries: $("#scrape-competitors").value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        countries,
        count_per_country: Number($("#scrape-count").value),
        sort: $("#scrape-sort").value,
        date_from: $("#scrape-date-from").value,
        date_to: $("#scrape-date-to").value,
        ratings: Array.from(document.querySelectorAll('input[name="scrape-rating"]:checked')).map((input) => Number(input.value)),
        include_keywords: $("#scrape-include-keywords").value,
        exclude_keywords: $("#scrape-exclude-keywords").value,
        reply_filter: $("#scrape-reply-filter").value,
        version_filter: $("#scrape-version-filter").value,
        min_thumbs_up: Number($("#scrape-min-thumbs").value),
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
  let request = {};
  try { request = JSON.parse(item.request || "{}"); } catch (_) { request = {}; }
  const platform = item.platform === "app_store" ? "App Store" : "Google Play";
  const description = (value, empty) => `<div class="document competitor-description">${E(value || empty)}</div>`;
  const filterText = reviewFilterSummary(request);
  modal(
    "竞品资料预览",
    `<div class="section-title"><div><h2>${E(listing.title || item.app_id)}</h2><p class="muted">${E(platform)} · ${E(listing.market || "未提供市场")} · ${E(listing.developer || "未提供开发者")}</p></div><span class="tag">${E(scrapeStatusNames[item.status] || item.status)}</span></div><div class="competitor-facts"><span>评论 ${Number(item.review_count || 0).toLocaleString()} 条</span>${item.filter_stats?.active ? `<span>筛选前 ${Number(item.filter_stats.fetched || 0).toLocaleString()} 条</span>` : ""}${item.translation_requested ? `<span>中文译文 ${Number(item.translated_count || 0).toLocaleString()} 条</span>` : ""}<span>截图 ${Number(item.screenshot_count || 0).toLocaleString()} 张</span><span>分类 ${E(listing.category || "未提供")}</span></div>${filterText ? `<p class="filter-summary"><strong>评论筛选：</strong>${E(filterText)}</p>` : ""}<h3>短描述</h3>${description(listing.short_description, "当前商店接口未提供短描述。")}${listing.promotional_text ? `<h3>Promotional Text</h3>${description(listing.promotional_text, "")}` : ""}<h3>长描述</h3>${description(listing.long_description, "当前商店接口未提供长描述。")}${item.error ? `<div class="banner">${E(item.error)}</div>` : ""}<p class="help">商店描述保持原文；评论筛选在翻译前执行，译文单独保存，不覆盖原评论，也不进行总结或观点分析。来源：${E(listing.source_url || "未提供")}</p><div class="actions">${item.status === "ready" ? `<button class="primary" data-confirm-scrape="${E(item.id)}">确认进入项目资料</button>` : ""}<button data-close-modal>关闭</button></div>`,
  );
}
