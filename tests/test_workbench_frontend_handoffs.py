"""Pure frontend handoff decisions; no browser or live model is required."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_f1_continuations_and_scoped_reference_picker():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend helper checks")
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = {console, setTimeout, clearTimeout, Date, Map, Set, document:{querySelector:()=>null}};
vm.createContext(context);
for (const file of ['modules/utils.js','features/tasks.js','features/outputs.js']) {
  vm.runInContext(fs.readFileSync('workbench/static/'+file,'utf8'),context);
}
const keys = ['one','two','three','four','five'].map(key=>'fast/'+key);
const parent = {key:'fast/new-product-analysis',assembly:'accepted_sections',section_tasks:keys};
context.state = {packs:[{tasks:[parent,...keys.map((key,index)=>({key,name:key,required_upstream_all:index?[keys[index-1]]:[]}))]}],jobs:[]};
context.activeVersion = null;
context.currentVersion = ()=>context.activeVersion;
const row = (index, extra={})=>({id:'job-'+index,task_id:keys[index],version_id:'',created:`2026-10-21T00:0${index}:00Z`,review_created:`2026-10-21T00:0${index}:30Z`,review_decision:'accepted',...extra});
const detail = row=>({...row,review:{decision:row.review_decision}});
context.state.jobs = [row(0)];
assert.equal(context.f1ContinuationAction(detail(row(0))).taskKey,keys[1]);
context.state.jobs.push(row(1,{review_decision:null}));
assert.equal(context.f1ContinuationAction(detail(row(0))).type,'job');
context.activeVersion = {id:'another-version'};
assert.equal(context.f1ContinuationAction(detail(row(0))),null);
context.activeVersion = null;
assert.equal(context.f1ContinuationAction(detail(row(0,{archived:1}))),null);
assert.equal(context.f1ContinuationAction(detail(row(0,{has_newer_revision:true}))),null);
assert.equal(context.f1ContinuationAction({...detail(row(0)),stale_upstream:[{reason:'changed'}]}),null);
context.state.jobs.push(row(0,{id:'newer-one',created:'2026-10-21T01:00:00Z',review_decision:null}));
assert.equal(context.f1ContinuationAction(detail(row(0))),null);
context.state.jobs = keys.map((_,index)=>row(index));
assert.equal(context.f1ContinuationAction(detail(row(4))).type,'assemble');
context.state.jobs[1].review_decision = null;
assert.equal(context.f1ContinuationAction(detail(row(4))),null);
context.state.jobs = keys.map((_,index)=>row(index));
const combined = {id:'combined',task_id:parent.key,version_id:'',review_decision:'accepted',created:'2026-10-21T02:00:00Z'};
context.state.jobs.push(combined);
assert.equal(context.f1ContinuationAction(detail(combined)).type,'prototype');
context.state.jobs[0].review_created = '2026-10-21T03:00:00Z';
assert.equal(context.f1ContinuationAction(detail(combined)),null);
const documents = [
 {id:'shared',name:'产品级 <script>',kind:'upload',versions:[]},
 {id:'current',name:'当前版本',kind:'upload',versions:[{id:'v1',name:'V1'}]},
 {id:'other',name:'其他版本',kind:'upload',versions:[{id:'v2',name:'V2'}]},
];
let html = context.taskDocumentChoices(documents,new Set(['current']),{id:'v1'});
assert(html.includes('&lt;script&gt;'));
assert(html.includes('其他产品版本的资料'));
assert(html.includes('value="current" checked'));
assert(!html.includes('<details open>'));
html = context.taskDocumentChoices(documents,new Set(['other']),{id:'v1'});
assert(html.includes('<details open>'));
assert(html.includes('value="other" checked'));
const refs = [{id:'image',name:'截图.png',category:'images'},{id:'listing',name:'商店描述.md'},{id:'reviews',name:'评论.csv'}];
assert.deepEqual(Array.from(context.prioritizeTaskReferences(['image','listing','reviews'],refs)),['listing','reviews','image']);
const publicSource = {id:'public',kind:'upload',versions:[]};
assert(context.taskExplicitSourceEligible(publicSource,null,[]));
assert(context.taskExplicitSourceEligible({...publicSource,versions:[{id:'v1'}]},{id:'v1'},[]));
assert(!context.taskExplicitSourceEligible({...publicSource,versions:[{id:'v2'}]},{id:'v1'},[]));
assert(!context.taskExplicitSourceEligible({...publicSource,versions:[{id:'v1'}]},null,[]));
for(const extra of [{kind:'accepted'},{kind:'deliverable'},{kind:'draft'},{status:'ready'},{confirmed:false},{competitor_ids:['other']}]) {
  assert(!context.taskExplicitSourceEligible({...publicSource,...extra},null,[]));
}
assert(context.taskExplicitSourceEligible({...publicSource,competitor_ids:['chosen','other']},null,['chosen']));
console.log(JSON.stringify({checks:'PASS'}));
"""
    result = subprocess.run([node, "-e", script], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["checks"] == "PASS"
