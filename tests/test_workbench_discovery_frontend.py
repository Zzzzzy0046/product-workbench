"""Repeatable frontend helper assertions, without browser or network access."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_competitor_discovery_helpers_and_scope():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend helper checks")
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const sandbox = {URL, console, state: {project: {platform: 'ios'}}, projectId: 'p1', currentVersion: () => null};
vm.createContext(sandbox);
for (const file of ['features/integrations.js', 'features/competitor_discovery.js']) {
  vm.runInContext(fs.readFileSync('workbench/static/' + file, 'utf8'), sandbox);
}
const check = expression => vm.runInContext(expression, sandbox);
assert.equal(check("competitorSafeUrl('javascript:alert(1)')"), '');
assert.equal(check("competitorSafeUrl('https://secret@example.com/x')"), '');
assert.equal(check("competitorSafeUrl('https://evil.test/x', true)"), '');
assert.equal(check("competitorSafeUrl('https://play.google.com/store/apps/details?id=com.test', true)"), 'https://play.google.com/store/apps/details?id=com.test');
assert.equal(check("competitorKnownNumber(null)"), null);
assert.equal(check("competitorKnownNumber('')"), null);
assert.equal(check("competitorInstallMinimum({installs:'1,000,000+'})"), 1000000);
assert.equal(check("competitorInstallMinimum({installs:'1.5M+'})"), 1500000);
assert.equal(check("competitorInstallMinimum({installs:null})"), null);
assert.equal(check("competitorCandidatePrice({free:false,price:null})"), '付费 · 价格未提供');
assert.equal(check("competitorDiscoverySession().platform"), 'app_store');
check("competitorDiscoverySession().query = 'test'");
sandbox.projectId = 'p2';
assert.equal(check("competitorDiscoverySession().query"), '');
sandbox.projectId = 'p1';
assert.equal(check("competitorDiscoverySession().query"), 'test');
const selection = check("JSON.stringify(matchedCompetitorSelections(['https://play.google.com/store/apps/details?id=com.keep','12345','com.keep'], [{platform:'google_play',app_id:'com.keep',role:'feature',note:'save',title:'Keep',query:'gba'},{platform:'google_play',app_id:'com.remove',role:'primary',note:''}]))");
const rows = JSON.parse(selection);
assert.equal(rows.length, 2);
assert.equal(rows[0].role, 'feature');
assert.equal(rows[0].note, 'save');
assert.equal(rows[1].app_id, '12345');
assert.equal(rows[1].role, 'primary');
assert.equal(rows[1].platform, 'app_store');
// A market switch keeps the chosen competitor but explicitly identifies the
// old discovery market and the new default collection market.
const marketNote = check("competitorCollectionMarketNote({country:'gb', selected:new Map([['a',{item:{search_country:'us'}}]])})");
assert(marketNote.includes('英国 GB'));
assert(marketNote.includes('来自 US'));
assert(marketNote.includes('也将按当前采集市场'));
assert.equal(check("competitorCandidateSummary({short_description:'<b>Hello</b>   &amp; world'})"), 'Hello & world');
assert.equal(check("Array.from(competitorCandidateSummary({short_description:'a'.repeat(2000)})).length"), 220);
assert.equal(check("competitorCandidateSummary({description:'b'.repeat(2000)}).endsWith('…')"), true);
assert.equal(check("competitorCandidateScore({score:4.123456})"), '★ 4.12');
assert.equal(check("competitorCandidateScore({score:null})"), '评分未提供');
assert.equal(check("Object.hasOwn(JSON.parse(JSON.stringify({entries:['com.test'],selections:matchedCompetitorSelections(['com.test'],[])})), 'selections')"), false);
assert.equal(check("competitorCollectionSelections([{item:{platform:'google_play',app_id:'com.test',search_country:'us'},role:'primary',note:'',query:'gba'}])[0].search_country"), 'us');
assert.equal(check("JSON.stringify(competitorExpandedCountries(['global']))"), '["us","gb","de","jp","in","id","br","sa"]');
assert.equal(check("competitorExpandedCountries(['global','us','gb']).length"), 8);
assert.equal(check("competitorExpandedCountries(['global']).includes('global')"), false);
assert(check("competitorCollectionMarketNote({country:'global',selected:new Map()})").includes('每款都会采集这 8 个市场'));
const workload = JSON.parse(check("JSON.stringify(competitorReviewWorkload('com.one\\ncom.two',['global'],100,true))"));
assert(workload.summary.includes('2 款竞品 × 8 个市场'));
assert(workload.summary.includes('每款上限 800'));
assert(workload.note.includes('1,600'));
assert(workload.note.includes('费用'));
assert(workload.note.includes('每款最多翻译前 500 条；更多仍保留原文'));
assert(workload.note.includes('候选已发现且本次勾选的具体市场'));
assert(workload.note.includes('没有可用交集时'));
assert(check("competitorReviewWorkload('com.one',['us'],10,false).note").includes('未开启评论翻译'));
assert.equal(check("competitorLookupCountry({search_country:'global',observed_countries:['de']})"), 'de');
assert.equal(check("competitorLookupCountry({search_country:'global'})"), '');
assert.equal(check("competitorLookupCountry({search_country:'us'})"), 'us');
const globalSelection = JSON.parse(check("JSON.stringify(competitorCollectionSelections([{item:{platform:'google_play',app_id:'com.test',search_country:'global',lookup_country:'de',observed_countries:['de','gb']},role:'feature',note:'flow',query:'gba'}])[0])"));
assert.equal(globalSelection.search_country, 'global');
assert.equal(globalSelection.lookup_country, 'de');
assert.deepEqual(globalSelection.observed_countries, ['de','gb']);
const coverage = check("competitorCoverageSummary({scope:'global_multi_market',attempted_countries:['us','gb','jp'],successful_countries:['us','gb'],failed_countries:['jp']})");
assert(coverage.includes('实际覆盖 2 / 3'));
assert(coverage.includes('失败市场：JP'));
assert(coverage.includes('并非全部国家'));
assert(coverage.includes('不是全球排名'));
assert(!check("JSON.stringify(competitorReviewWorkload('com.one',['global'],'not-a-number',true))").includes('NaN'));
assert(!check("JSON.stringify(competitorReviewWorkload('com.one',['global'],Infinity,true))").includes('NaN'));
console.log(JSON.stringify({checks:'PASS'}));
"""
    result = subprocess.run(
        [node, "-e", script], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report == {"checks": "PASS"}
