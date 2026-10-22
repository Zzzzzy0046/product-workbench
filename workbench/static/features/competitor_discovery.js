"use strict";

/* Search is read-only. All candidate choices stay in this page's memory, scoped
   to project + version; no model, collection or translation runs from search. */
const competitorDiscoverySessions = new Map();
let competitorDiscoveryModalSequence = 0;

function competitorDiscoveryScope() {
  return `${projectId || ""}:${currentVersion()?.id || ""}`;
}

function competitorSafeUrl(value, storeOnly = false) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol !== "https:" || url.username || url.password) return "";
    if (storeOnly && !["play.google.com", "apps.apple.com"].includes(url.hostname)) return "";
    return url.href;
  } catch (_) { return ""; }
}

function competitorCandidateKey(item) {
  return `${item.platform}:${item.app_id}`;
}

function competitorKnownNumber(value) {
  if (value === undefined || value === null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function competitorInstallMinimum(item) {
  const text = String(item.installs ?? "").replace(/[,，\s]/g, "");
  if (!text) return null;
  const match = text.match(/^(\d+(?:\.\d+)?)([kmb万亿]?)/i);
  if (!match) return null;
  return Number(match[1]) * ({k: 1000, m: 1000000, b: 1000000000, "万": 10000, "亿": 100000000}[match[2].toLowerCase()] || 1);
}

function competitorCandidatePrice(item) {
  if (item.free === true) return "免费";
  const price = competitorKnownNumber(item.price);
  if (item.free === false) return price === null ? "付费 · 价格未提供" : `${price} ${item.currency || ""} · 付费`.trim();
  return "价格未提供";
}

function competitorCandidateSummary(item) {
  const raw = String(item.short_description || item.description || "");
  const text = raw.replace(/<[^>]*>/g, " ").replace(/&nbsp;/gi, " ").replace(/&amp;/gi, "&").replace(/&lt;/gi, "<").replace(/&gt;/gi, ">").replace(/&quot;/gi, '"').replace(/&#39;/gi, "'").replace(/\s+/g, " ").trim();
  if (!text) return "商店接口未提供简介，展开详情核对。";
  const chars = Array.from(text);
  return chars.length > 220 ? chars.slice(0, 219).join("") + "…" : text;
}

function competitorCandidateScore(item) {
  const score = competitorKnownNumber(item.score);
  return score === null ? "评分未提供" : `★ ${score.toFixed(2)}`;
}

function competitorCollectionSelections(selected) {
  return selected.map((chosen) => ({platform: chosen.item.platform, app_id: chosen.item.app_id, title: chosen.item.title || "", role: chosen.role, note: chosen.note, query: chosen.query, search_country: chosen.item.search_country || "", lookup_country: competitorLookupCountry(chosen.item), observed_countries: competitorObservedCountries(chosen.item)}));
}

function competitorMarketLabel(code) {
  if (code === "global") return "全球（8 市场组合，非全部国家）";
  const country = competitorCountries.find(([value]) => value === code);
  return country ? `${country[1]} ${country[0].toUpperCase()}` : String(code || "未记录").toUpperCase();
}

function competitorObservedCountries(item) {
  return Array.from(new Set((Array.isArray(item.observed_countries) ? item.observed_countries : []).map((value) => String(value).toLowerCase()).filter((value) => /^[a-z]{2}$/.test(value))));
}

function competitorLookupCountry(item) {
  const candidates = [item.lookup_country, ...competitorObservedCountries(item), item.search_country];
  return candidates.map((value) => String(value || "").toLowerCase()).find((value) => /^[a-z]{2}$/.test(value)) || "";
}

function competitorCoverageSummary(coverage = {}) {
  const attempted = coverage.attempted_countries || coverage.countries || [];
  if (!attempted.length) return "";
  const successful = coverage.successful_countries || [];
  const failed = coverage.failed_countries || [];
  const codes = (items) => items.length ? items.map((item) => String(item).toUpperCase()).join("、") : "无";
  return `${coverage.scope === "global_multi_market" ? "全球代表性组合，并非全部国家。" : ""}实际覆盖 ${successful.length} / ${attempted.length} 个市场：${codes(successful)}；失败市场：${codes(failed)}。跨市场轮询去重，不是全球排名；评分、价格等取候选所示的具体详情市场。`;
}

function competitorCollectionMarketNote(session) {
  const label = competitorMarketLabel(session.country);
  const previousMarkets = Array.from(new Set(Array.from(session.selected.values()).map(({item}) => item.search_country).filter((code) => code && code !== session.country)));
  return `下一步默认采集市场：${label}${session.country === "global" ? "，将展开为 US、GB、DE、JP、IN、ID、BR、SA，每款都会采集这 8 个市场" : ""}，可在采集表单中修改或多选。${previousMarkets.length ? `选择篮中有来自 ${previousMarkets.map((code) => code.toUpperCase()).join("、")} 搜索结果的竞品；它们也将按当前采集市场获取资料，不会把发现市场当成采集市场。` : ""}`;
}

function competitorDiscoverySession() {
  const scope = competitorDiscoveryScope();
  if (!competitorDiscoverySessions.has(scope)) {
    const platform = String(state.project?.platform || "").toLowerCase();
    competitorDiscoverySessions.set(scope, {
      query: "", platform: platform === "ios" ? "app_store" : "google_play", country: "us",
      items: [], selected: new Map(), details: new Map(), openDetails: new Set(),
      filters: {keyword: "", rating: "", free: "", installs: "", sort: "store"},
      searched: false, loading: false, error: "", warnings: [], cached: false, collectedAt: "", coverage: {}, request: 0,
    });
  }
  return competitorDiscoverySessions.get(scope);
}

function openCompetitorDiscovery() {
  if (!projectId) return toast("请先选择项目");
  const session = competitorDiscoverySession();
  const scope = competitorDiscoveryScope();
  const token = ++competitorDiscoveryModalSequence;
  // A request from an older modal instance must not keep this one busy.
  session.request += 1;
  session.loading = false;
  for (const [key, detail] of session.details) if (detail.loading) session.details.delete(key);
  const roles = {primary: "主对标", feature: "功能参考", monetization: "变现参考"};
  modal("找竞品 · 你来选择", `<div id="competitor-discovery" class="competitor-discovery" data-instance="${token}">
    <h2>先找到候选，再由你决定对标谁。</h2><p class="muted">搜索只读取商店候选，不会自动勾选、采集评论或调用模型。已有链接也可以直接采集。</p>
    <form id="competitor-discovery-form" class="discovery-search-form"><div><label for="discovery-query">品类或功能关键词</label><input id="discovery-query" type="search" required maxlength="120" placeholder="例如：GBA emulator" value="${E(session.query)}"></div><div><label for="discovery-platform">平台</label><select id="discovery-platform"><option value="google_play" ${session.platform === "google_play" ? "selected" : ""}>Android · Google Play</option><option value="app_store" ${session.platform === "app_store" ? "selected" : ""}>iOS · App Store</option></select></div><div><label for="discovery-country">搜索市场</label><select id="discovery-country" aria-label="搜索市场"></select></div><button id="discovery-search-submit" class="primary" type="submit">搜索候选</button><div class="discovery-country-find"><label class="visually-hidden" for="discovery-country-search">筛选国家选项</label><input id="discovery-country-search" type="search" placeholder="筛选国家名称／代码" aria-controls="discovery-country"></div></form>
    <p class="help">默认返回最多 12 个候选。商店返回顺序不是市场排名；累计安装区间不代表近期增长、收入或 D7 ROI。未提供的字段不补造。</p>
    <div id="discovery-status" aria-live="polite"></div>
    <div class="discovery-filter-panel"><div class="discovery-filter-title"><strong>筛选本次结果</strong><span>只影响已返回候选，不会重新联网搜索</span></div><div class="discovery-filters"><div><label for="discovery-filter-keyword">名称／开发者／简介</label><input id="discovery-filter-keyword" type="search" value="${E(session.filters.keyword)}" placeholder="筛选关键词"></div><div><label for="discovery-filter-rating">最低评分</label><select id="discovery-filter-rating"><option value="">不限</option><option value="3">3.0</option><option value="4">4.0</option><option value="4.5">4.5</option></select></div><div><label for="discovery-filter-free">价格</label><select id="discovery-filter-free"><option value="">不限</option><option value="free">免费</option><option value="paid">付费</option></select></div><div><label for="discovery-filter-installs">累计安装区间下界</label><select id="discovery-filter-installs"><option value="">不限</option><option value="10000">≥ 1 万</option><option value="100000">≥ 10 万</option><option value="1000000">≥ 100 万</option><option value="10000000">≥ 1000 万</option></select></div><div><label for="discovery-filter-sort">排序</label><select id="discovery-filter-sort"><option value="store">商店返回顺序</option><option value="rating">评分优先</option><option value="ratings">评价量优先</option><option value="installs">累计安装下界优先</option><option value="title">名称</option></select></div></div></div>
    <div id="discovery-results" class="discovery-results"></div>
    <section class="discovery-selection"><div class="section-title"><div><h3>我的选择 <span id="discovery-selected-count"></span></h3><p class="muted">建议先选 2–3 个主对标；最多 8 个。选择用途由你判断，不是系统推荐结论。</p></div><button type="button" id="discovery-clear-selection" class="small">清空选择</button></div><div id="discovery-selection"></div><p id="discovery-market-note" class="help"></p></section>
    <div class="discovery-footer"><small>下一步还可调整评论范围，采集完成后预览并确认入库。</small><div class="actions"><button type="button" id="discovery-collect" class="primary">采集所选竞品</button><button type="button" id="discovery-known-links">已有链接，直接采集</button><button type="button" data-close-modal>关闭</button></div></div>
  </div>`);
  const root = $("#competitor-discovery");
  const live = () => root.isConnected && $("#modal").open && root.dataset.instance === String(token) && competitorDiscoveryScope() === scope;
  const findItem = (key) => session.items.find((item) => competitorCandidateKey(item) === key);
  const countryOptions = () => {
    const needle = $("#discovery-country-search").value.trim().toLowerCase();
    const options = [["global", "全球（多市场合并）", "全球 global 常用市场"], ...competitorCountries].filter(([code, name, region]) => code === session.country || !needle || `${code} ${name} ${region}`.toLowerCase().includes(needle));
    $("#discovery-country").innerHTML = options.map(([code, name]) => `<option value="${code}" ${code === session.country ? "selected" : ""}>${E(name)}${code === "global" ? "" : ` · ${code.toUpperCase()}`}</option>`).join("");
  };
  const renderStatus = () => {
    $("#discovery-search-submit").disabled = session.loading;
    $("#discovery-search-submit").textContent = session.loading ? "搜索中…" : "搜索候选";
    $("#discovery-status").innerHTML = session.loading ? `<div class="discovery-notice">${session.country === "global" ? "正在合并 8 个代表性市场的候选，可能需要几十秒；个别市场失败会明确显示。" : "正在获取商店候选，请稍候。"}不会开始评论采集。</div>` : session.error ? `<div class="banner">${E(session.error)} <button id="discovery-retry" type="button" class="small">重试搜索</button></div>` : session.searched ? `<p class="help">${session.cached ? "使用短时缓存" : "已获取商店结果"}${session.collectedAt ? ` · ${E(date(session.collectedAt))}` : ""} · 共 ${session.items.length} 个候选</p>${competitorCoverageSummary(session.coverage) ? `<p class="discovery-notice">${E(competitorCoverageSummary(session.coverage))}</p>` : ""}${session.warnings.length ? `<details class="discovery-data-notes"><summary>数据口径与额外提示（${session.warnings.length}）</summary>${session.warnings.map((warning) => `<p class="help">${E(warning)}</p>`).join("")}</details>` : ""}` : "";
    $("#discovery-retry")?.addEventListener("click", () => searchCandidates(true));
  };
  const renderSelection = () => {
    $("#discovery-selected-count").textContent = `${session.selected.size} / 8`;
    $("#discovery-collect").disabled = !session.selected.size;
    $("#discovery-clear-selection").disabled = !session.selected.size;
    $("#discovery-market-note").textContent = competitorCollectionMarketNote(session);
    $("#discovery-selection").innerHTML = session.selected.size ? Array.from(session.selected.entries()).map(([key, chosen]) => `<article class="discovery-selected-row" data-selection="${E(key)}"><div><strong>${E(chosen.item.title || chosen.item.app_id)}</strong><small>${E(chosen.item.platform === "app_store" ? "App Store" : "Google Play")} · 发现市场 ${E(competitorMarketLabel(chosen.item.search_country))} · ${E(chosen.query)}</small></div><div><label class="visually-hidden" for="role-${E(key)}">${E(chosen.item.title)}的参考用途</label><select id="role-${E(key)}" data-discovery-role="${E(key)}">${Object.entries(roles).map(([value, label]) => `<option value="${value}" ${chosen.role === value ? "selected" : ""}>${label}</option>`).join("")}</select></div><div><label class="visually-hidden" for="note-${E(key)}">${E(chosen.item.title)}的参考备注</label><input id="note-${E(key)}" data-discovery-note="${E(key)}" maxlength="200" placeholder="参考哪个功能／页面？（可选）" value="${E(chosen.note)}"></div><button class="small" type="button" data-discovery-remove="${E(key)}" aria-label="移除 ${E(chosen.item.title)}">移除</button></article>`).join("") : '<p class="empty compact">还没有选择。候选不会被自动勾选。</p>';
  };
  const renderDetails = (item) => {
    const detailKey = `${competitorCandidateKey(item)}:${competitorLookupCountry(item) || "unknown"}`;
    const detail = session.details.get(detailKey);
    if (!detail || detail.loading) return '<p class="help">正在读取商店详情…</p>';
    if (detail.error) return `<div class="banner">${E(detail.error)} <button type="button" class="small" data-discovery-retry-detail="${E(competitorCandidateKey(item))}">重试详情</button></div>`;
    const listing = detail.listing || {};
    const screenshots = (listing.screenshot_urls || []).map((url) => competitorSafeUrl(url)).filter(Boolean).slice(0, 20);
    return `<p class="help">详情、价格与评分口径：${E(competitorMarketLabel(competitorLookupCountry(item)))}；不代表全球统一数值。</p><div class="discovery-long-description"><h4>短描述</h4><p>${E(listing.short_description || "当前商店接口未提供短描述。")}</p><h4>长描述</h4><p>${E(listing.long_description || listing.description || "当前商店接口未提供长描述。")}</p></div><h4>商店截图</h4>${screenshots.length ? `<div class="discovery-screenshots">${screenshots.map((url, index) => `<a href="${E(url)}" target="_blank" rel="noopener noreferrer"><img src="${E(url)}" alt="${E(item.title)}商店截图 ${index + 1}" loading="lazy" referrerpolicy="no-referrer"></a>`).join("")}</div>` : '<p class="help">当前商店接口未提供截图。</p>'}${(detail.warnings || []).map((warning) => `<p class="help">${E(warning)}</p>`).join("")}`;
  };
  const visibleItems = () => {
    const filter = session.filters;
    const needle = filter.keyword.trim().toLowerCase();
    const items = session.items.filter((item) => {
      const score = competitorKnownNumber(item.score);
      const installs = competitorInstallMinimum(item);
      return (!needle || `${item.title || ""} ${item.developer || ""} ${item.short_description || ""} ${item.description || ""}`.toLowerCase().includes(needle))
        && (!filter.rating || (score !== null && score >= Number(filter.rating)))
        && (!filter.free || item.free === (filter.free === "free"))
        && (!filter.installs || (installs !== null && installs >= Number(filter.installs)));
    });
    const field = {rating: "score", ratings: "ratings", installs: "installs"}[filter.sort];
    if (field) items.sort((a, b) => {
      const av = field === "installs" ? competitorInstallMinimum(a) : competitorKnownNumber(a[field]);
      const bv = field === "installs" ? competitorInstallMinimum(b) : competitorKnownNumber(b[field]);
      return av === null ? (bv === null ? 0 : 1) : bv === null ? -1 : bv - av;
    });
    else if (filter.sort === "title") items.sort((a, b) => String(a.title || "").localeCompare(String(b.title || "")));
    return items;
  };
  const renderResults = () => {
    const items = visibleItems();
    $("#discovery-results").innerHTML = !session.searched ? '<div class="empty">输入品类或功能词，点击“搜索候选”。</div>' : !session.items.length ? `<div class="empty">${session.error ? "本次搜索未完成，请重试。" : "没有搜索到候选。可换英文关键词、平台或市场再试。"}</div>` : !items.length ? '<div class="empty">当前筛选条件没有匹配项。可清空筛选，已选竞品不会被移除。<button type="button" id="discovery-clear-filters" class="small">清空筛选</button></div>' : `<p class="discovery-result-count">本次结果显示 ${items.length} / ${session.items.length} 个 · 未提供数据的候选在相应筛选中不会匹配</p>${items.map((item) => {
      const key = competitorCandidateKey(item);
      const icon = competitorSafeUrl(item.icon_url);
      const url = competitorSafeUrl(item.source_url, true);
      const score = competitorKnownNumber(item.score);
      const ratings = competitorKnownNumber(item.ratings);
      return `<article class="discovery-card ${session.selected.has(key) ? "is-selected" : ""}" data-candidate="${E(key)}">
        <div class="discovery-card-top">${icon ? `<img src="${E(icon)}" alt="" class="discovery-icon" loading="lazy" referrerpolicy="no-referrer">` : '<span class="discovery-icon discovery-icon-empty" aria-hidden="true">App</span>'}<div class="discovery-card-heading"><h3>${E(item.title || item.app_id)}</h3><p>${E(item.developer || "开发者未提供")}</p><small>${E(item.app_id)}</small></div><label class="discovery-choice"><input type="checkbox" data-discovery-select="${E(key)}" ${session.selected.has(key) ? "checked" : ""}><span>选择</span></label></div>
        <p class="discovery-summary">${E(competitorCandidateSummary(item))}</p>
        <div class="discovery-facts"><span>${E(competitorCandidateScore(item))}</span><span>${ratings === null ? "评价量未提供" : `${ratings.toLocaleString()} 个评分`}</span><span>${item.installs === undefined || item.installs === null || item.installs === "" ? "安装量未提供" : `累计安装 ${E(item.installs)}`}</span><span>${E(competitorCandidatePrice(item))}</span>${typeof item.offers_iap === "boolean" ? `<span>${item.offers_iap ? "有内购" : "未标记内购"}</span>` : ""}${typeof item.contains_ads === "boolean" ? `<span>${item.contains_ads ? "含广告" : "未标记广告"}</span>` : ""}</div>
        <p class="discovery-market-context">${item.search_country === "global" ? `发现于 ${E(competitorObservedCountries(item).map((code) => code.toUpperCase()).join("、") || "未提供具体市场")}` : `发现市场：${E(competitorMarketLabel(item.search_country))}`} · 详情口径：${E(competitorLookupCountry(item).toUpperCase() || "未提供")}</p>
        <div class="discovery-card-links">${url ? `<a href="${E(url)}" target="_blank" rel="noopener noreferrer">商店原页 ↗</a>` : '<small>商店链接未提供</small>'}<span>${E(item.platform === "app_store" ? "App Store" : "Google Play")}</span></div>
        <div class="discovery-revenue-row"><small>${E(typeof competitorRevenueCardLabel === "function" ? competitorRevenueCardLabel(item) : "收入：未获取 · 查看来源/补充")}</small><button type="button" class="small" data-discovery-revenue="${E(key)}">查看收入来源／补充</button></div>
        <details data-discovery-detail="${E(key)}" ${session.openDetails.has(key) ? "open" : ""}><summary>查看描述与截图</summary><div class="discovery-detail-body">${session.openDetails.has(key) ? renderDetails(item) : ""}</div></details></article>`;
    }).join("")}`;
    $("#discovery-clear-filters")?.addEventListener("click", () => {
      session.filters = {keyword: "", rating: "", free: "", installs: "", sort: "store"};
      syncFilters();
      renderResults();
    });
    root.querySelectorAll("details[data-discovery-detail]").forEach((element) => {
      element.ontoggle = () => {
        const key = element.dataset.discoveryDetail;
        if (!element.open) { session.openDetails.delete(key); return; }
        session.openDetails.add(key);
        const item = findItem(key);
        if (item) loadDetail(item);
      };
    });
  };
  const loadDetail = async (item, force = false) => {
    const lookupCountry = competitorLookupCountry(item);
    const key = `${competitorCandidateKey(item)}:${lookupCountry || "unknown"}`;
    if (!force && session.details.has(key)) return;
    const marker = {};
    session.details.set(key, {loading: true, marker});
    const element = Array.from(root.querySelectorAll("details[data-discovery-detail]")).find((node) => node.dataset.discoveryDetail === competitorCandidateKey(item));
    if (!lookupCountry) {
      session.details.set(key, {error: "该候选缺少可用的具体详情市场。请选择某个具体国家重新搜索后查看，不能把全球视为一个商店国家。"});
      if (element) element.querySelector(".discovery-detail-body").innerHTML = renderDetails(item);
      return;
    }
    if (element) element.querySelector(".discovery-detail-body").innerHTML = renderDetails(item);
    try {
      const detail = await api("/api/competitors/detail", {project_id: projectId, version_id: currentVersion()?.id || "", platform: item.platform, app_id: item.app_id, country: lookupCountry, lang: "en", refresh: force});
      if (!live() || session.details.get(key)?.marker !== marker) return;
      session.details.set(key, detail);
    } catch (err) {
      if (!live() || session.details.get(key)?.marker !== marker) return;
      session.details.set(key, {error: err.message || "读取详情失败，请重试。"});
    }
    if (live() && element?.isConnected) element.querySelector(".discovery-detail-body").innerHTML = renderDetails(item);
  };
  const syncFilters = () => {
    for (const [key, value] of Object.entries(session.filters)) $("#discovery-filter-" + key).value = value;
  };
  const searchCandidates = async (force = false) => {
    if (!live() || session.loading) return;
    session.query = $("#discovery-query").value.trim();
    session.platform = $("#discovery-platform").value;
    session.country = $("#discovery-country").value;
    if (!session.query) { $("#discovery-query").focus(); return; }
    const request = ++session.request;
    const payload = {project_id: projectId, version_id: currentVersion()?.id || "", query: session.query, platform: session.platform, country: session.country, lang: "en", limit: 12, refresh: force};
    session.loading = true;
    session.error = "";
    renderStatus();
    try {
      const result = await api("/api/competitors/search", payload);
      if (!live() || request !== session.request) return;
      session.items = (result.items || []).map((item) => ({...item, search_query: payload.query, search_country: payload.country}));
      session.searched = true;
      session.cached = Boolean(result.cached);
      session.collectedAt = result.collected_at || "";
      session.warnings = Array.isArray(result.warnings) ? result.warnings : [];
      session.coverage = {scope: result.scope, countries: result.countries, attempted_countries: result.attempted_countries, successful_countries: result.successful_countries, failed_countries: result.failed_countries};
      session.openDetails.clear();
    } catch (err) {
      if (!live() || request !== session.request) return;
      session.error = err.message || "搜索失败，请重试。";
      // Keep the last successful candidates and basket; a failed query is not an empty result.
    } finally {
      if (live() && request === session.request) {
        session.loading = false;
        renderStatus();
        renderResults();
      }
    }
  };
  $("#competitor-discovery-form").onsubmit = (event) => { event.preventDefault(); searchCandidates(); };
  $("#discovery-query").oninput = (event) => { session.query = event.target.value; };
  $("#discovery-platform").onchange = (event) => { session.platform = event.target.value; };
  $("#discovery-country-search").oninput = countryOptions;
  $("#discovery-country").onchange = (event) => { session.country = event.target.value; renderSelection(); };
  for (const key of Object.keys(session.filters)) {
    const input = $("#discovery-filter-" + key);
    input.addEventListener(key === "keyword" ? "input" : "change", () => {
      session.filters[key] = input.value;
      renderResults();
    });
  }
  root.addEventListener("change", (event) => {
    const input = event.target;
    if (input.dataset.discoverySelect) {
      const key = input.dataset.discoverySelect;
      const item = findItem(key);
      if (input.checked && item) {
        if (session.selected.size >= 8) { input.checked = false; toast("最多选择 8 个竞品，请先移除一个。"); return; }
        session.selected.set(key, {item: {...item}, role: "primary", note: "", query: item.search_query || session.query});
      } else session.selected.delete(key);
      renderSelection();
      renderResults();
    }
    if (input.dataset.discoveryRole) {
      const chosen = session.selected.get(input.dataset.discoveryRole);
      if (chosen && roles[input.value]) chosen.role = input.value;
    }
  });
  root.addEventListener("input", (event) => {
    const chosen = session.selected.get(event.target.dataset.discoveryNote);
    if (chosen) chosen.note = event.target.value.slice(0, 200);
  });
  root.addEventListener("error", (event) => {
    const image = event.target;
    if (!image?.matches?.("img.discovery-icon")) return;
    const placeholder = document.createElement("span");
    placeholder.className = "discovery-icon discovery-icon-empty";
    placeholder.textContent = "App";
    placeholder.setAttribute("aria-hidden", "true");
    image.replaceWith(placeholder);
  }, true);
  root.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-discovery-remove]");
    if (remove) { session.selected.delete(remove.dataset.discoveryRemove); renderSelection(); renderResults(); }
    const retry = event.target.closest("[data-discovery-retry-detail]");
    if (retry) { const item = findItem(retry.dataset.discoveryRetryDetail); if (item) loadDetail(item, true); }
    const revenue = event.target.closest("[data-discovery-revenue]");
    if (revenue) {
      const item = findItem(revenue.dataset.discoveryRevenue);
      if (item && live() && typeof openCompetitorRevenue === "function") openCompetitorRevenue(item, {country: item.search_country || session.country});
    }
  });
  $("#discovery-clear-selection").onclick = () => { session.selected.clear(); renderSelection(); renderResults(); };
  $("#discovery-known-links").onclick = () => { if (live()) reviewScrapeForm(); };
  $("#discovery-collect").onclick = () => {
    if (!live() || !session.selected.size) return;
    const selected = Array.from(session.selected.values());
    const entries = selected.map(({item}) => competitorSafeUrl(item.source_url, true) || (item.platform === "app_store" ? `https://apps.apple.com/app/id${encodeURIComponent(item.app_id)}` : item.app_id));
    reviewScrapeForm({entries, countries: competitorExpandedCountries([session.country]), selections: competitorCollectionSelections(selected)});
  };
  countryOptions();
  syncFilters();
  renderStatus();
  renderSelection();
  renderResults();
}
