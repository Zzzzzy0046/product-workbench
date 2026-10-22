"""Review handoff uses refreshed task summaries immediately after a click."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_review_and_unarchive_refresh_before_rendering_continuation():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend event checks")
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const listeners = {};
const first = {key:'fast/f1-category-user',name:'品类与用户'};
const second = {key:'fast/f1-competitor-differences',name:'竞品差异',required_upstream_all:[first.key]};
const parent = {key:'fast/new-product-analysis',assembly:'accepted_sections',section_tasks:[first.key,second.key]};
const row = {id:'first-job',task_id:first.key,version_id:'',created:'2026-10-21T00:00:00Z',status:'completed',review_decision:null,archived:0};
const context = {
  console,
  state:{packs:[{tasks:[parent,first,second]}],jobs:[{...row}]},
  projectId:'project',currentVersion:()=>null,
  document:{addEventListener:(name,fn)=>{listeners[name]=fn;}},
  $:()=>({value:'confirmed'}),toast:()=>{},error:err=>{throw err;},
};
vm.createContext(context);
for (const file of ['features/tasks.js','features/outputs.js','modules/events.js']) {
  vm.runInContext(fs.readFileSync('workbench/static/'+file,'utf8'),context);
}
(async()=>{
  let calls = [], displayed = null;
  const accepted = {...row,review_decision:'accepted',review:{decision:'accepted'}};
  context.api = async(path,payload)=>{
    calls.push('api');
    assert.equal(path,'/api/jobs/first-job/review');
    assert.equal(payload.decision,'accepted');
    return accepted;
  };
  context.refresh = async()=>{calls.push('refresh');context.state.jobs=[{...accepted}];};
  context.showJob = job=>{calls.push('show');displayed=context.f1ContinuationAction(job);};
  const click = dataset=>listeners.click({target:{closest:()=>({dataset,hasAttribute:()=>false,disabled:false})}});
  assert.equal(context.f1ContinuationAction(accepted),null);
  await click({review:'accepted',id:'first-job'});
  assert.deepEqual(calls,['api','refresh','show']);
  assert.equal(displayed.type,'prepare');
  assert.equal(displayed.taskKey,second.key);

  // Unarchiving an accepted chapter must also restore the immediate handoff;
  // rendering against the old archived state would suppress the button.
  calls=[];displayed=null;
  context.state.jobs=[{...accepted,archived:1}];
  context.api=async(path,payload)=>{
    calls.push('api');
    assert.equal(path,'/api/jobs/first-job/archive');
    assert.equal(payload.archived,false);
    return accepted;
  };
  await click({archiveJob:'first-job',archived:'false'});
  assert.deepEqual(calls,['api','refresh','show']);
  assert.equal(displayed.taskKey,second.key);
  console.log(JSON.stringify({checks:'PASS',scenarios:2}));
})().catch(err=>{console.error(err);process.exitCode=1;});
"""
    result = subprocess.run(
        [node, "-e", script], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"checks": "PASS", "scenarios": 2}
