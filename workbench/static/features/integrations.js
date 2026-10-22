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
  global: ["us", "gb", "de", "jp", "in", "id", "br", "sa"],
  english: ["us", "gb", "ca", "au"],
  southeast_asia: ["id", "th", "vn", "ph", "sg", "my"],
  western_europe: ["gb", "de", "fr", "it", "es", "nl"],
  latin_america: ["br", "mx", "ar", "co", "cl", "pe"],
  middle_east: ["ae", "sa", "eg"],
};

function competitorExpandedCountries(countries) {
  return Array.from(new Set((countries || []).flatMap((country) => country === "global" ? competitorCountryPresets.global : /^[a-z]{2}$/.test(country) ? [country] : [])));
}

function competitorReviewWorkload(entries, countries, count, translate) {
  const itemCount = new Set(String(entries || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean)).size;
  const markets = competitorExpandedCountries(countries);
  const perCountry = Math.max(0, Math.min(500, Number(count) || 0));
  const perApp = markets.length * perCountry;
  const total = itemCount * perApp;
  return {
    summary: markets.length ? `${itemCount || "待填写"} 款竞品 × ${markets.length} 个市场 · 每款上限 ${perApp.toLocaleString()} 条评论` : "请选择至少一个市场",
    note: `${markets.length ? `每款会逐市场采集 ${markets.map((code) => code.toUpperCase()).join("、")}；每国最多 ${perCountry} 条，${itemCount ? `本批筛选前最多 ${total.toLocaleString()} 条。` : "填写竞品后显示整批上限。"}` : "全球预设仅为 8 个常用市场，不是全部国家。"}${translate ? " 已开启翻译：对筛选后保留的评论，每款最多翻译前 500 条；更多仍保留原文。多市场会增加等待时间，并可能产生模型／翻译服务费用；具体用量取决于返回条数。" : " 未开启评论翻译。"}描述与截图优先使用候选已发现且本次勾选的具体市场；未提供发现信息或没有可用交集时，使用首个所选市场，不代表全部市场的统一版本。`,
  };
}

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

function matchedCompetitorSelections(entries, selections) {
  // JSON.stringify omits undefined: the legacy known-link path must not send
  // an empty selections array to the strict searched-selection contract.
  if (!selections.length) return undefined;
  const selected = new Map(selections.map((item) => [`${item.platform}:${item.app_id}`, item]));
  const result = new Map();
  for (const entry of entries) {
    let platform = /^\d+$/.test(entry) ? "app_store" : "google_play";
    let appId = entry;
    if (entry.includes("://")) {
      let url;
      try { url = new URL(entry); } catch (_) { throw Error("有竞品链接无法识别，请检查每行链接。"); }
      if (url.hostname === "play.google.com" || url.hostname.endsWith(".play.google.com")) appId = url.searchParams.get("id") || "";
      else if (url.hostname === "apps.apple.com" || url.hostname.endsWith(".apps.apple.com")) {
        platform = "app_store";
        appId = url.pathname.match(/\/id(\d+)(?:\/|$)/)?.[1] || "";
      } else throw Error("仅支持 Google Play 和 App Store 链接。");
    }
    if (!/^[A-Za-z0-9_.-]{1,200}$/.test(appId)) throw Error("有竞品应用 ID 无法识别，请检查链接或 ID。");
    const key = `${platform}:${appId}`;
    result.set(key, selected.get(key) || {platform, app_id: appId, role: "primary", note: "", title: "", query: ""});
  }
  return Array.from(result.values());
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

function reviewScrapeForm(options = {}) {
  const config = state.integrations?.review_scraper || {};
  const active = currentVersion();
  const scopeProjectId = projectId;
  const scopeVersionId = active?.id || "";
  const entries = Array.isArray(options.entries) ? options.entries : [];
  const selections = Array.isArray(options.selections) ? options.selections : [];
  const dossierIds = Array.isArray(options.competitorIds) ? options.competitorIds : [];
  let selectedCountries = new Set(competitorExpandedCountries(options.countries || ["us"]));
  const countryChoices = (query = "") => {
    const needle = String(query || "").trim().toLowerCase();
    const rows = competitorCountries.filter(([code, name, region]) => !needle || `${code} ${name} ${region}`.toLowerCase().includes(needle));
    return rows.map(([code, name, region]) => `<label class="country-choice"><input type="checkbox" value="${code}" ${selectedCountries.has(code) ? "checked" : ""}><span>${name}</span><small>${code.toUpperCase()} · ${region}</small></label>`).join("") || '<div class="empty compact">没有匹配地区，可在下方添加两位代码。</div>';
  };
  modal(
    "批量采集竞品资料",
    `<h2>采集你指定的竞品资料</h2><p class="muted">${entries.length ? "已带入你手选的竞品，可继续调整链接与评论范围。" : "已知道竞品时，直接粘贴链接；还没有选好，可先使用“找竞品”。"}开启评论翻译后，每款最多翻译前 500 条；更多仍保留原文。</p><form id="review-scrape-form" class="scrape-form">
      <section class="scrape-step"><div class="scrape-step-title"><span>1</span><div><h3>竞品</h3><p>每行一个商店链接、package name 或 App Store ID，最多 8 个。</p></div></div><label class="visually-hidden" for="scrape-competitors">竞品列表（1–8 个）</label><textarea id="scrape-competitors" required maxlength="4000" rows="5" placeholder="com.fastemulator.gba&#10;https://play.google.com/store/apps/details?id=it.dbtecno.pizzaboygba&#10;https://apps.apple.com/us/app/example/id123456789">${E(entries.join("\n"))}</textarea>${selections.length ? `<div class="discovery-handoff"><strong>本次选择用途</strong>${selections.map((item) => `<p>${E(item.title || item.app_id)} · ${E({primary:"主对标",feature:"功能参考",monetization:"变现参考"}[item.role] || "主对标")}${item.note ? ` · ${E(item.note)}` : ""}</p>`).join("")}<small>删除或新增链接后，仅保留仍匹配的选择记录。</small></div>` : ""}</section>
      <fieldset class="dossier-collection-checks"><legend>本次采集什么</legend><p class="help">这里仅决定采集范围，不会自动勾选分析输入。可只补需要的内容。</p><div class="checks"><label><input id="scrape-collect-listing" type="checkbox" checked> 商店信息与长短描述</label><label><input id="scrape-collect-reviews" type="checkbox" checked> 用户评论</label><label><input id="scrape-collect-screenshots" type="checkbox" checked> 商店截图</label><label><input id="scrape-collect-device" type="checkbox" ${dossierIds.length ? "" : "disabled"}> App 实机截图与流程（单独设置设备与范围）</label></div>${dossierIds.length ? '<small>勾选实机截图后，会先进入设置页；不会在这里自动操作设备。</small>' : '<small>实机截图请先建立竞品档案，再从档案中选择设备与范围。当前实机走查支持 Android。</small>'}${dossierIds.length > 1 ? `<details class="dossier-specific-collection"><summary>按竞品单独调整（未启用时沿用上方勾选）</summary>${dossierIds.map((id) => {const item=(state.competitors || []).find((competitor)=>competitor.id===id);return `<section data-collection-row="${E(id)}"><label><input type="checkbox" data-collection-override="${E(id)}">单独设置 ${E(item?.title || item?.app_id || id)}</label><div class="checks"><label><input type="checkbox" data-collection-type="collect_listing" checked disabled>商店信息</label><label><input type="checkbox" data-collection-type="collect_reviews" checked disabled>评论</label><label><input type="checkbox" data-collection-type="collect_screenshots" checked disabled>商店截图</label></div></section>`;}).join("")}</details>` : ""}</fieldset>
      <section class="scrape-step"><div class="scrape-step-title"><span>2</span><div><h3>国家或地区</h3><p>描述与截图优先使用候选已发现且本次勾选的具体市场；未提供发现信息或没有可用交集时使用首个所选市场。评论采集全部已选市场。</p></div></div><div class="country-presets"><button type="button" data-country-preset="global">全球（常用 8 市场）</button><button type="button" data-country-preset="english">英语核心</button><button type="button" data-country-preset="southeast_asia">东南亚</button><button type="button" data-country-preset="western_europe">西欧</button><button type="button" data-country-preset="latin_america">拉美</button><button type="button" data-country-preset="middle_east">中东</button><button type="button" data-country-preset="clear">清空</button></div><p class="help">“全球”是美国、英国、德国、日本、印度、印度尼西亚、巴西、沙特阿拉伯的代表性组合，不是所有国家；可取消不需要的市场。</p><label class="visually-hidden" for="country-search">搜索国家或地区</label><input id="country-search" class="country-search" type="search" placeholder="搜索国家、地区或代码"><div id="country-options" class="country-options">${countryChoices()}</div><div id="country-selection" class="selection-summary" aria-live="polite"></div><details class="custom-country"><summary>列表里没有？添加其他地区代码</summary><label for="scrape-custom-countries">两位国家或地区代码（可选）</label><input id="scrape-custom-countries" maxlength="120" placeholder="例如：ie,gr"></details></section>
      <section class="scrape-step"><div class="scrape-step-title"><span>3</span><div><h3>评论范围与筛选</h3><p>筛选在抓取后、翻译前执行；筛选条件越窄，最终条数可能越少。</p></div></div><div class="grid scrape-range-grid"><div><label for="scrape-count">每个国家抓取上限（筛选前）</label><input id="scrape-count" type="number" min="1" max="500" value="100"></div><div><label for="scrape-sort">评论排序</label><select id="scrape-sort"><option value="newest">最新</option><option value="relevant">相关</option></select></div><div><label for="scrape-date-from">开始日期（可选）</label><input id="scrape-date-from" type="date"></div><div><label for="scrape-date-to">结束日期（可选）</label><input id="scrape-date-to" type="date"></div></div><div class="filter-box"><div><label>只保留这些评分</label><small>不勾选表示全部评分</small></div><div class="rating-choices">${[1, 2, 3, 4, 5].map((rating) => `<label><input type="checkbox" name="scrape-rating" value="${rating}"><span>${rating} 星</span></label>`).join("")}</div><div class="grid filter-grid"><div><label for="scrape-include-keywords">包含关键词（任意一个）</label><input id="scrape-include-keywords" maxlength="500" placeholder="例如：ads, crash, save"></div><div><label for="scrape-exclude-keywords">排除关键词</label><input id="scrape-exclude-keywords" maxlength="500" placeholder="例如：giveaway, promo"></div><div><label for="scrape-reply-filter">开发者回复</label><select id="scrape-reply-filter"><option value="any">不限</option><option value="replied">仅有回复</option><option value="unreplied">仅无回复</option></select></div><div><label for="scrape-version-filter">App 版本包含</label><input id="scrape-version-filter" maxlength="100" placeholder="例如：2.3"></div><div><label for="scrape-min-thumbs">最低点赞数</label><input id="scrape-min-thumbs" type="number" min="0" max="1000000" value="0"></div></div></div></section>
      <div class="checks"><label><input id="scrape-translate" type="checkbox" checked> 对筛选后保留的评论生成简体中文译文（原评论始终保留）</label></div>
      <details class="scrape-settings"><summary>采集器设置</summary><label for="scrape-root">${config.backend === "builtin" ? "随包采集核心目录" : "桌面工具目录"}</label><input id="scrape-root" maxlength="500" value="${E(config.root || "")}" ${config.backend === "builtin" ? "readonly" : ""} placeholder="采集器目录"><div class="help">${E(config.message || "保存目录后会自动检测 app/scrapers.py 和 Python 环境。")} ${config.backend === "builtin" ? "勾选翻译后将评论原文发送至 Google 翻译；原文保留，可取消勾选。" : "翻译优先使用已配置的 DeepSeek，失败时回退 Google 翻译。"}</div></details>
      <div class="scrape-workload" aria-live="polite"><strong id="scrape-scope-summary"></strong><p id="scrape-workload-note"></p></div><div class="scrape-submit"><div><small>结果先进入待确认区，确认后才写入项目资料。</small></div><div class="actions"><button class="primary" type="submit">开始采集</button><button type="button" data-close-modal>取消</button></div></div></form>`,
  );
  const renderCountryPicker = () => {
    $("#country-options").innerHTML = countryChoices($("#country-search").value);
    $("#country-selection").textContent = selectedCountries.size
      ? `已选 ${selectedCountries.size} 个：${Array.from(selectedCountries).map((code) => code.toUpperCase()).join("、")}`
      : "还没有选择国家或地区";
    const custom = $("#scrape-custom-countries").value.split(/[,，\s]+/).map((item) => item.trim().toLowerCase()).filter(Boolean);
    const workload = competitorReviewWorkload($("#scrape-competitors").value, [...selectedCountries, ...custom], $("#scrape-count").value, $("#scrape-translate").checked);
    const collectReviews = $("#scrape-collect-reviews").checked || Array.from(document.querySelectorAll("[data-collection-override]:checked")).some((input) => input.closest("[data-collection-row]").querySelector('[data-collection-type="collect_reviews"]').checked);
    $("#scrape-translate").disabled = !collectReviews;
    $("#scrape-scope-summary").textContent = collectReviews ? workload.summary : "本次不采集评论";
    $("#scrape-workload-note").textContent = collectReviews ? workload.note : "只采集已勾选的商店信息或截图；实机走查在设备与范围设置页单独确认。";
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
  ["#scrape-count", "#scrape-competitors", "#scrape-custom-countries"].forEach((selector) => { $(selector).addEventListener("input", renderCountryPicker); });
  $("#scrape-translate").addEventListener("change", renderCountryPicker);
  $("#scrape-collect-reviews").addEventListener("change", renderCountryPicker);
  document.querySelectorAll("[data-collection-override]").forEach((input) => {
    input.onchange = () => {
      input.closest("[data-collection-row]").querySelectorAll("[data-collection-type]").forEach((field) => {field.disabled = !input.checked;});
      renderCountryPicker();
    };
  });
  document.querySelectorAll("[data-collection-type]").forEach((input) => {input.onchange=renderCountryPicker;});
  document.querySelectorAll("[data-country-preset]").forEach((button) => {
    button.onclick = () => {
      selectedCountries = new Set(competitorCountryPresets[button.dataset.countryPreset] || []);
      renderCountryPicker();
    };
  });
  renderCountryPicker();
  const scrapeForm = $("#review-scrape-form");
  $("#review-scrape-form").onsubmit = async (event) => {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const customCountries = $("#scrape-custom-countries").value.split(/[,，\s]+/).map((item) => item.trim().toLowerCase()).filter(Boolean);
      if (customCountries.some((country) => country !== "global" && !/^[a-z]{2}$/.test(country))) throw Error("其他地区请填写两位代码，例如 ie、gr。");
      const countries = competitorExpandedCountries([...selectedCountries, ...customCountries]);
      const collectListing = $("#scrape-collect-listing").checked;
      const collectReviews = $("#scrape-collect-reviews").checked;
      const collectScreenshots = $("#scrape-collect-screenshots").checked;
      const collectDevice = $("#scrape-collect-device").checked;
      const collectionOptions={};
      document.querySelectorAll("[data-collection-override]:checked").forEach((input) => {
        collectionOptions[input.dataset.collectionOverride]=Object.fromEntries(Array.from(input.closest("[data-collection-row]").querySelectorAll("[data-collection-type]")).map((field)=>[field.dataset.collectionType,field.checked]));
      });
      const hasOverride=Object.keys(collectionOptions).length > 0;
      const anyReviews=collectReviews || Object.values(collectionOptions).some((value)=>value.collect_reviews);
      if (!collectListing && !collectReviews && !collectScreenshots && !collectDevice && !hasOverride) throw Error("请至少勾选一种采集内容。");
      if (!countries.length) throw Error("请至少选择一个国家或地区。");
      if (countries.length > 20) throw Error("一次最多选择 20 个国家或地区。");
      if (projectId !== scopeProjectId || (currentVersion()?.id || "") !== scopeVersionId) throw Error("项目或版本已切换，请重新打开采集窗口。");
      const scraperRoot = $("#scrape-root").value;
      const payload = {
        project_id: scopeProjectId,
        version_id: scopeVersionId,
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
        collect_listing: collectListing,
        collect_reviews: collectReviews,
        collect_screenshots: collectScreenshots,
        translate: anyReviews && $("#scrape-translate").checked,
        selections: matchedCompetitorSelections($("#scrape-competitors").value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean), selections),
      };
      const matchedKeys = new Set((matchedCompetitorSelections(payload.entries, selections) || []).map((item) => `${item.platform}:${item.app_id}`));
      if (dossierIds.length) payload.competitor_ids = (state.competitors || []).filter((item) => dossierIds.includes(item.id) && matchedKeys.has(`${item.platform}:${item.app_id}`)).map((item) => item.id);
      if (hasOverride) payload.collection_options=Object.fromEntries(Object.entries(collectionOptions).filter(([id])=>(payload.competitor_ids || []).includes(id)));
      if (!collectListing && !collectReviews && !collectScreenshots && !hasOverride) {
        if (collectDevice && typeof dossierDevicePicker === "function") return dossierDevicePicker(payload.competitor_ids || []);
        throw Error("请勾选商店信息、评论或商店截图。");
      }
      await api("/api/integrations/review-scraper", { root: scraperRoot, enabled: true });
      if (projectId !== scopeProjectId || (currentVersion()?.id || "") !== scopeVersionId || !scrapeForm.isConnected || !$("#modal").open) throw Error("采集窗口已关闭或范围改变，尚未开始采集。");
      const result = await api("/api/competitors/collect", payload);
      if (projectId !== scopeProjectId || (currentVersion()?.id || "") !== scopeVersionId || !scrapeForm.isConnected || !$("#modal").open) {
        toast(`已在原项目范围启动 ${result.count} 个竞品采集，可稍后查看`);
        return;
      }
      close();
      await refresh();
      tab = "materials";
      draw();
      toast(`已开始采集 ${result.count} 个你指定的竞品`);
      if (collectDevice && typeof dossierDevicePicker === "function") dossierDevicePicker(payload.competitor_ids || []);
    } catch (err) {
      error(err);
      event.submitter.disabled = false;
    }
  };
}

let competitorPreviewRequest = 0;
async function competitorPreview(scrapeId) {
  const requestNumber = ++competitorPreviewRequest;
  const requestedProjectId = projectId;
  const requestedVersionId = currentVersion()?.id || "";
  const item = await api(`/api/reviews/scrape/${scrapeId}`);
  if (requestNumber !== competitorPreviewRequest || projectId !== requestedProjectId || (currentVersion()?.id || "") !== requestedVersionId) return;
  const listing = item.listing || {};
  let request = {};
  try { request = JSON.parse(item.request || "{}"); } catch (_) { request = {}; }
  const platform = item.platform === "app_store" ? "App Store" : "Google Play";
  const description = (value, empty) => `<div class="document competitor-description">${E(value || empty)}</div>`;
  const filterText = reviewFilterSummary(request);
  const screenshotUrls = (item.screenshot_preview_urls || listing.screenshot_urls || []).map((url) => competitorSafeUrl(url)).filter(Boolean).slice(0, 6);
  const samples = Array.isArray(item.review_samples) ? item.review_samples.slice(0, 5) : [];
  const evidencePreview = `<section class="competitor-evidence-preview"><h3>截图预览</h3>${screenshotUrls.length ? `<div class="discovery-screenshots">${screenshotUrls.map((url, index) => `<a href="${E(url)}" target="_blank" rel="noopener noreferrer"><img src="${E(url)}" alt="商店截图 ${index + 1}" loading="lazy" referrerpolicy="no-referrer"></a>`).join("")}</div>` : '<p class="help">当前没有可预览截图；请核对采集提示。</p>'}<h3>评论样本 · 原文与译文</h3><p class="help">最多显示 5 条，仅用于确认采集内容，不代表整体评论结论。</p>${samples.length ? samples.map((sample) => `<article class="competitor-review-sample"><small>${sample.score === undefined || sample.score === null || sample.score === "" ? "评分未提供" : `${E(sample.score)} 星`}${sample.published_at ? ` · ${E(sample.published_at)}` : ""}</small>${sample.title ? `<strong>${E(sample.title)}</strong>` : ""}<p><span>原文</span>${E(sample.original_content || sample.content || "未提供原文")}</p><p><span>中文</span>${E(sample.translated_content || "未提供译文；请确认是否开启翻译，或检查采集提示。")}</p></article>`).join("") : '<p class="help">没有可预览评论。可能未返回评论或筛选后为空，请核对数量与采集提示。</p>'}${(item.warnings || []).map((warning) => `<p class="discovery-notice">${E(warning)}</p>`).join("")}</section>`;
  modal(
    "竞品资料预览",
    `<div class="section-title"><div><h2>${E(listing.title || item.app_id)}</h2><p class="muted">${E(platform)} · ${E(listing.market || "未提供市场")} · ${E(listing.developer || "未提供开发者")}</p></div><span class="tag">${E(scrapeStatusNames[item.status] || item.status)}</span></div><div class="competitor-facts"><span>评论 ${Number(item.review_count || 0).toLocaleString()} 条</span>${item.filter_stats?.active ? `<span>筛选前 ${Number(item.filter_stats.fetched || 0).toLocaleString()} 条</span>` : ""}${item.translation_requested ? `<span>中文译文 ${Number(item.translated_count || 0).toLocaleString()} 条</span>` : ""}<span>截图 ${Number(item.screenshot_count || 0).toLocaleString()} 张</span><span>分类 ${E(listing.category || "未提供")}</span></div>${filterText ? `<p class="filter-summary"><strong>评论筛选：</strong>${E(filterText)}</p>` : ""}<h3>短描述</h3>${description(listing.short_description, "当前商店接口未提供短描述。")}${listing.promotional_text ? `<h3>Promotional Text</h3>${description(listing.promotional_text, "")}` : ""}<h3>长描述</h3>${description(listing.long_description, "当前商店接口未提供长描述。")}${evidencePreview}${item.error ? `<div class="banner">${E(item.error)}</div>` : ""}<p class="help">商店描述保持原文；评论筛选在翻译前执行，译文单独保存，不覆盖原评论，也不进行总结或观点分析。来源：${E(listing.source_url || "未提供")}</p><div class="actions">${item.status === "ready" ? `<button class="primary" data-confirm-scrape="${E(item.id)}">确认进入项目资料</button>` : ""}<button data-close-modal>关闭</button></div>`,
  );
}
