"use strict";

/* No provider requests or credentials. Only explicit, source-linked records. */
const competitorRevenueTypes = {iap: "订阅 / IAP", ads: "广告收入", combined: "合计（来源明确含广告）", paid_download: "付费下载", unknown: "来源未明确"};
const competitorRevenueBases = {consumer_spend: "消费者支出 / 扣费前", publisher_net: "开发者净收入", unknown: "来源未明确"};
const competitorRevenueNatures = {estimate: "第三方估算", disclosed: "来源披露（未自动核验）", unknown: "来源未明确"};
const competitorRevenueProviders = [
  {name: "Sensor Tower", url: "https://app.sensortower.com/", detail: "可查商店收入；Ad Monetization 另提供广告收入，需对应账号和数据权限，应用覆盖须核对。", source: "https://sensortower.com/blog/ad-monetization-app-analysis-top-ad-publishers"},
  {name: "AppTweak", url: "https://www.apptweak.com/en/market-intelligence", detail: "可查看商店收入估算；有免费 Starter 页面能力，API 是另一种需授权的服务。商店收入不包含广告。", source: "https://developers.apptweak.com/reference/overview"},
  {name: "AppMagic", url: "https://appmagic.rocks/", detail: "用于查看下载和 IAP 收入数据；是否能看到此应用、周期和地区取决于登录及权限，不代表广告收入。", source: "https://appmagic.rocks/"},
];

function competitorRevenueCardLabel(item) {
  // Filenames are not identity: platform or a truncated long ID can collide.
  // The detail API filters full project/version/platform/app_id before display.
  return "收入资料：来源查询 / 人工记录";
}

function competitorRevenueDate() {
  const local = new Date();
  return `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, "0")}-${String(local.getDate()).padStart(2, "0")}`;
}

function competitorRevenueRecordHtml(record) {
  const url = competitorSafeUrl(record.source_url);
  return `<article class="card revenue-record"><div class="split"><strong>${E(record.value_display || "未获取")} ${E(record.currency || "")}</strong><span class="tag warn">人工记录 · 未自动核验</span></div><p>${E(competitorRevenueTypes[record.revenue_type] || "来源未明确")} · ${E(record.country === "global" ? "来源标明全球" : String(record.country || "").toUpperCase())} · ${E(record.period_start)} 至 ${E(record.period_end)}</p><p class="muted">${E(record.provider)} · ${E(competitorRevenueNatures[record.data_nature] || "来源未明确")} · ${E(competitorRevenueBases[record.basis] || "来源未明确")} · 查看日期 ${E(record.observed_on)}</p>${record.note ? `<p>${E(record.note)}</p>` : ""}<div class="actions">${url ? `<a href="${E(url)}" target="_blank" rel="noopener noreferrer">核对来源 ↗</a>` : ""}<button class="small" data-revenue-document="${E(record.document_id)}">查看收入资料</button></div></article>`;
}

async function openCompetitorRevenue(item, options = {}) {
  const scopeProject = projectId, scopeVersion = currentVersion()?.id || "";
  const scopeKey = `${scopeProject}:${scopeVersion}`;
  const optionsHtml = (values, selected) => Object.entries(values).map(([value, label]) => `<option value="${E(value)}" ${value === selected ? "selected" : ""}>${E(label)}</option>`).join("");
  const defaultCountry = /^[a-z]{2}$/.test(options.country || "") ? options.country : "";
  const countries = [["", "请选择来源的地区"], ["global", "全球（仅当来源标明全球）"], ...competitorCountries.filter(([code]) => code !== "global")];
  modal("竞品收入 · 来源与资料", `<section id="competitor-revenue" class="competitor-revenue"><div class="split"><div><h2>${E(item.title || item.app_id)}</h2><p>${E(item.platform === "app_store" ? "iOS / App Store" : "Android / Google Play")} · <code>${E(item.app_id)}</code></p></div><button id="revenue-back">返回找竞品</button></div><div class="banner">工作台尚未自动接入收入数值，未获取不等于 0。以下为来源入口，不是已核实的该应用收入详情页；打开后按应用 ID 核对。搜索的八市场合并与数据源的全球收入不是同一口径。</div><div class="actions"><button id="revenue-copy-id">复制应用 ID</button></div><div class="revenue-provider-grid">${competitorRevenueProviders.map((provider) => `<article class="card revenue-provider"><h3>${E(provider.name)}</h3><p>${E(provider.detail)}</p><div class="actions"><a href="${E(provider.url)}" target="_blank" rel="noopener noreferrer">打开来源 ↗</a><a href="${E(provider.source)}" target="_blank" rel="noopener noreferrer">能力说明 ↗</a></div></article>`).join("")}</div><p class="help">没有调用收费 API、代你登录或读取账号凭证。不要用安装量、评分或单独的 IAP 数值补算广告收入与总收入。</p><h3>本项目已保存的收入资料</h3><div id="revenue-records" aria-live="polite"><p class="muted">正在读取本项目资料…</p></div><details class="card revenue-entry"><summary>补充查到的收入数值或范围</summary><p class="help">只记录来源上看到的内容。金额可写“低于 5,000”“10,000–20,000”，不必把区间伪装为精确值。需要多种收入类型时分开记录，不自动合计。</p><form id="revenue-form"><div class="revenue-form-grid"><label>来源名称<input name="provider" required maxlength="80" placeholder="例如 Sensor Tower / AppTweak"></label><label>金额或范围<input name="value_display" required maxlength="100" placeholder="按来源原样填写，未获取请勿填 0"></label><label>币种<input name="currency" required maxlength="3" pattern="[A-Za-z]{3}" value="USD"></label><label>收入类型<select name="revenue_type">${optionsHtml(competitorRevenueTypes, "unknown")}</select></label><label>统计开始<input type="date" name="period_start" required></label><label>统计结束<input type="date" name="period_end" required></label><label>来源地区<select name="country" required>${countries.map(([code, label]) => `<option value="${E(code)}" ${code === defaultCountry ? "selected" : ""}>${E(label)}</option>`).join("")}</select></label><label>净 / 毛口径<select name="basis">${optionsHtml(competitorRevenueBases, "unknown")}</select></label><label>数值性质<select name="data_nature">${optionsHtml(competitorRevenueNatures, "estimate")}</select></label><label>查看日期<input type="date" name="observed_on" value="${competitorRevenueDate()}" required></label><label class="revenue-field-wide">来源详情链接<input type="url" name="source_url" required maxlength="1800" placeholder="https://… 不要粘贴带 token 的链接"></label><label class="revenue-field-wide">补充说明（可选）<input name="note" maxlength="600" placeholder="例如：来源区间值、不含广告、覆盖不全"></label></div><label class="check-row"><input type="checkbox" name="acknowledged" required>我已按应用 ID 核对来源；这是人工记录，不是工作台自动核验的真实收入。</label><p class="help">保存后成为当前项目/版本的独立 Markdown 资料，可在任务中勾选引用，并随项目包迁移。不会改写已生成文档，也不会自动确认市场结论。</p><button class="primary" type="submit">保存为收入资料</button></form></details></section>`);
  const section = $("#competitor-revenue");
  const current = () => section.isConnected && $("#modal").open && `${projectId}:${currentVersion()?.id || ""}` === scopeKey;
  $("#revenue-back").onclick = openCompetitorDiscovery;
  $("#revenue-copy-id").onclick = async () => {
    try { await navigator.clipboard.writeText(item.app_id); toast("已复制应用 ID，请在来源中搜索并核对应用"); }
    catch (_) { toast("复制未成功，可手动复制上方应用 ID"); }
  };
  const loadRecords = async () => {
    try {
      const params = new URLSearchParams({project_id: scopeProject, version_id: scopeVersion, platform: item.platform, app_id: item.app_id});
      const result = await api(`/api/competitors/revenue?${params}`);
      if (!current()) return;
      $("#revenue-records").innerHTML = result.items.length ? result.items.map(competitorRevenueRecordHtml).join("") : '<p class="empty compact">尚未保存收入资料。可以先查看来源，获取到数据后再补充。</p>';
      if (result.truncated) $("#revenue-records").insertAdjacentHTML("beforeend", '<p class="help">只检查最近 200 份收入资料，更早记录请到资料库查找。</p>');
      section.querySelectorAll("[data-revenue-document]").forEach((button) => { button.onclick = async () => {
        try { showDocument(await api(`/api/documents/${encodeURIComponent(button.dataset.revenueDocument)}`)); }
        catch (err) { error(err); }
      }; });
    } catch (err) { if (current()) $("#revenue-records").textContent = `读取收入资料失败：${err.message}`; }
  };
  $("#revenue-form").onsubmit = async (event) => {
    event.preventDefault();
    if (!current()) return;
    const button = event.submitter;
    button.disabled = true;
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(form.entries());
    try {
      await api("/api/competitors/revenue", {...values, acknowledged: form.get("acknowledged") === "on", project_id: scopeProject, version_id: scopeVersion, platform: item.platform, app_id: item.app_id, title: item.title || item.app_id});
      if (!current()) return;
      await refresh(false);
      if (!current()) return;
      toast("收入资料已保存，未改写现有交付物");
      await loadRecords();
    } catch (err) { if (current()) error(err); }
    finally { if (current()) button.disabled = false; }
  };
  await loadRecords();
}
