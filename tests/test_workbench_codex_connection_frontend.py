"""Offline UI checks: no login, model usage or real CLI invocation."""
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const timers = new Map(), calls = [], nodes = new Map();
let timerId = 0;
for (const name of ['#codex-connection-card', '.codex-connection-path', '#codex-binary-path', '#codex-path-candidate']) nodes.set(name, {value:'', open:false});
const available = {available:true,binary_path:'C:\\Codex\\codex.exe',source:'path',model:'sample-model',auth:{status:'unknown'},test:{status:'not_tested'},candidates:[],operation:null};
const sandbox = {
 console, projectId:'p1',tab:'capabilities',state:{integrations:{codex:available},runtime:{}},
 $:s=>nodes.get(s)||null,date:x=>x,toast:x=>{sandbox.notice=x;},
 E:x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
 window:{confirm:()=>false,addEventListener(name,callback){sandbox[name]=callback;}},
 setTimeout(fn,ms){const id=++timerId;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);},
 async api(path,body){calls.push({path,body});return sandbox.response||available;},
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('workbench/static/features/codex_connection.js','utf8'),sandbox);
const q=source=>vm.runInContext(source,sandbox);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
"""


def run_node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend behavioral checks")
    result = subprocess.run([node, "-e", HARNESS + script], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_read_only_mount_consent_and_explicit_acknowledgement():
    run_node(r"""
(async()=>{
 q('codexConnectionBeforeDraw();codexConnectionMount()');await settle();
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/integrations/codex');
 assert.equal(calls[0].body,undefined,'Mount must only GET, never check/login/test');
 assert.equal(timers.size,0,'No running operation means no status polling');
 await q("codexConnectionAction('login')");await q("codexConnectionAction('test')");
 assert.equal(calls.length,1,'Cancelling confirmation must not send any request');
 sandbox.window.confirm=()=>true;
 await q("codexConnectionAction('login')");
 assert.equal(calls[1].path,'/api/integrations/codex/login');
 assert.equal(calls[1].body.confirmed,true);
 await q("codexConnectionAction('test')");
 assert.equal(calls[2].path,'/api/integrations/codex/test');
 assert.equal(calls[2].body.confirmed,true);
 await q("codexConnectionAction('check')");
 assert.equal(calls[3].path,'/api/integrations/codex/check');
 assert.equal(Object.keys(calls[3].body).length,0);
 console.log('PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_running_poll_lifecycle_leaving_scope_and_cancellation():
    run_node(r"""
(async()=>{
 sandbox.response={...available,operation:{id:'op1',kind:'check',status:'running'}};
 q('codexConnectionBeforeDraw();codexConnectionMount()');await settle();
 assert.equal(timers.size,1);
 await q("codexConnectionAction('test')");assert.equal(calls.length,1,'Cannot overlap running commands');
 await q("codexConnectionAction('cancel',{dataset:{operationId:'old'}})");
 assert.equal(calls.length,1,'Stale operation ID must not cancel a newer command');
 sandbox.response={...available,operation:{id:'op1',kind:'check',status:'cancelled'}};
 await q("codexConnectionAction('cancel',{dataset:{operationId:'op1'}})");
 assert.equal(calls[1].path,'/api/integrations/codex/cancel');
 assert.equal(calls[1].body.operation_id,'op1');assert.equal(timers.size,0);
 sandbox.response={...available,operation:{id:'op2',kind:'login',status:'running'}};
 await q('codexConnectionRead(codexConnectionScope())');assert.equal(timers.size,1);
 const fn=[...timers.values()][0];
 q('codexConnectionBeforeDraw()');sandbox.tab='overview';
 assert.equal(timers.size,0);const previous=calls.length;await fn();
 assert.equal(calls.length,previous,'Leaving connection page stops further requests');
 sandbox.tab='capabilities';q('codexConnectionMount()');await settle();
 const pending=[...timers.values()][0];sandbox.projectId='p2';
 await pending();assert.equal(calls.length,previous+1,'Changing project invalidates old polling scope');
 console.log('PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_status_evidence_levels_escaping_candidates_and_path_save():
    run_node(r"""
(async()=>{
 let html=q('codexConnectionCard()');assert(html.includes('尚未检查'));assert(html.includes('尚未测试'));assert(!html.includes('已连接 · 已验证'));
 sandbox.sample={...available,auth:{status:'logged_in',method:'chatgpt'},test:{status:'not_tested'}};
 html=q('codexConnectionCard(sample)');assert(html.includes('已登录'));assert(!html.includes('已连接 · 已验证'));
 sandbox.sample.test.status='passed';assert(q('codexConnectionCard(sample)').includes('已连接 · 已验证'));
 sandbox.sample={...available,available:false,source:'missing',binary_path:'<img src=x onerror=alert(1)>',message:'<script>bad</script>',candidates:[{path:'C:\\bad"<x>\\codex.exe',label:'<b>bad</b>'},{path:'C:\\npm\\codex.js',label:'unsafe-js-candidate'}]};
 html=q('codexConnectionCard(sample)');assert(html.includes('官方 Codex CLI 指引'));assert(html.includes('&lt;script&gt;'));assert(!html.includes('<img src=x'));assert(html.includes('&quot;&lt;x&gt;'));assert(!html.includes('unsafe-js-candidate'));
 q('codexConnectionBeforeDraw();codexConnectionMount()');await settle();
 nodes.get('#codex-binary-path').value='C:\\Tools\\codex.exe';
 await q("codexConnectionAction('save')");
 assert.equal(calls.at(-1).path,'/api/integrations/codex');assert.equal(calls.at(-1).body.binary_path,'C:\\Tools\\codex.exe');
 assert.equal(sandbox.state.runtime.available,true);assert.equal(sandbox.state.runtime.model,'sample-model');
 await q("codexConnectionAction('auto')");assert.equal(calls.at(-1).body.binary_path,'');
 sandbox.response={...available,env_managed:true};await q('codexConnectionRead(codexConnectionScope())');
 const count=calls.length;await q("codexConnectionAction('save')");assert.equal(calls.length,count);
 console.log('PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_stale_get_or_page_response_cannot_overwrite_newer_action():
    run_node(r"""
(async()=>{
 const reads=[];
 sandbox.api=(path,body)=>{calls.push({path,body});if(body===undefined)return new Promise(resolve=>{reads.push(resolve);});return Promise.resolve({...available,operation:{id:'new',kind:'check',status:'running'}});};
 q('codexConnectionBeforeDraw();codexConnectionMount()');
 await q("codexConnectionAction('check')");
 reads[0](available);await settle();
 assert.equal(q('codexConnectionSnapshot().operation.id'),'new','Late GET cannot clear a newer operation');
 const scope=q('codexConnectionScope()');sandbox.oldScope=scope;
 const pending=q('codexConnectionRead(oldScope)');
 q('codexConnectionBeforeDraw();codexConnectionMount()');
 reads[2]({...available,operation:{id:'other-view',kind:'check',status:'succeeded'}});await settle();
 reads[1](available);await pending;
 assert.equal(q('codexConnectionSnapshot().operation.id'),'other-view','An old view response cannot replace a newer view');
 assert.equal(q('codexConnectionView.generation'),2);
 q('codexConnectionBeforeDraw()');sandbox.pagehide();assert.equal(timers.size,0);
 console.log('PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_status_errors_are_escaped_and_read_only_retry_remains_available():
    run_node(r"""
(async()=>{
 sandbox.response={...available,operation:{id:'busy',kind:'check',status:'running'}};
 q('codexConnectionBeforeDraw();codexConnectionMount()');await settle();
 sandbox.api=async(path,body)=>{calls.push({path,body});throw Error('<img src=x onerror=bad()>');};
 await q('codexConnectionRead(codexConnectionScope())');
 let html=q('codexConnectionCard()');assert(html.includes('&lt;img src=x'));assert(!html.includes('<img src=x'));assert(html.includes('data-codex-connection="refresh"'));
 sandbox.api=async(path,body)=>{calls.push({path,body});return {...available,operation:{id:'busy',kind:'check',status:'succeeded'}};};
 await q("codexConnectionAction('refresh')");
 assert.equal(calls.at(-1).body,undefined,'Status retry must not restart the CLI or model');
 assert.equal(q('codexConnectionSnapshot().operation.status'),'succeeded');
 console.log('PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_static_wiring_and_no_credential_fields():
    index = (ROOT / "workbench/static/index.html").read_text(encoding="utf-8")
    workspace = (ROOT / "workbench/static/render/workspace.js").read_text(encoding="utf-8")
    events = (ROOT / "workbench/static/modules/events.js").read_text(encoding="utf-8")
    feature = (ROOT / "workbench/static/features/codex_connection.js").read_text(encoding="utf-8")
    assert index.index("/features/codex_connection.js") < index.index("/modules/events.js")
    assert 'codexConnectionBeforeDraw()' in workspace
    assert 'codexConnectionMount()' in workspace
    assert 'await codexConnectionAction(b.dataset.codexConnection, b)' in events
    assert 'type="password"' not in feature
    assert 'type="file"' not in feature
    assert '/logout' not in feature
