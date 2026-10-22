"""Android walkthrough frontend contract, scope and async-action checks."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_android_capture_frontend_scope_actions_and_preview():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend checks")
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const elements = new Map();
let currentVersionId = '', rootHTML = '', pendingAPI = null, apiCalls = [], refreshed = 0;
let timerId = 0;
const timers = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, {
    value:'', dataset:{}, open:selector === '#modal',
    addEventListener(){}, querySelectorAll(){ return []; },
    set innerHTML(value) { this.html=value; if (selector === '#android-capture-console') rootHTML=value; },
    get innerHTML(){ return this.html || ''; },
  });
  return elements.get(selector);
}
const sandbox = {
  console, projectId:'p1', currentVersion:() => currentVersionId ? {id:currentVersionId,name:currentVersionId} : null,
  $:element, E:value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  date:value=>String(value || ''), toast(){}, close(){ element('#modal').open=false; },
  setTimeout:fn=>{ const id=++timerId; timers.set(id,fn); return id; }, clearTimeout:id=>timers.delete(id),
  api:async(path,body)=>{ apiCalls.push({path,body}); return pendingAPI ? await pendingAPI(path,body) : {}; },
  refresh:async()=>{ refreshed++; },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('workbench/static/features/android_capture.js','utf8'),sandbox);
const run = source => vm.runInContext(source,sandbox);
function mount(status='prepared') {
  element('#modal').open=true;
  element('#android-capture-console').dataset.instance='1';
  run(`androidCaptureModal={token:1,scope:androidCaptureScope(),project:projectId,version:currentVersion()?.id||'',request:0,busy:false,loading:false,timer:null,error:'',draft:androidCaptureDraft(),settings:{adb_available:true,codex_available:true,skill_available:true},devices:[{serial:'serial1',state:'device'}],session:{id:'s1',project_id:projectId,version_id:currentVersion()?.id||'',title:'<img src=x onerror=alert(1)>',package:'com.example.app',scope:'首页与订阅',status:${JSON.stringify(status)},progress:[],observations:[],modules:[],composites:[]}}`);
}
(async()=>{
  // Drafts are project + product-version scoped and survive opening/rerendering.
  run("androidCaptureDraft().package='com.saved.app'");
  currentVersionId='v1'; assert.equal(run('androidCaptureDraft().package'),'');
  run("androidCaptureDraft().scope='只走首页'");
  sandbox.projectId='p2'; assert.equal(run('androidCaptureDraft().scope'),'');
  sandbox.projectId='p1'; assert.equal(run('androidCaptureDraft().scope'),'只走首页');
  currentVersionId=''; assert.equal(run('androidCaptureDraft().package'),'com.saved.app');
  assert.equal(run("androidCaptureSelectSerial([{serial:'a',state:'device'},{serial:'b',state:'unauthorized'}])"),'a');
  assert.equal(run("androidCaptureSelectSerial([{serial:'a',state:'device'},{serial:'b',state:'device'}])"),'');
  assert.equal(run("androidCaptureSelectSerial([{serial:'a',state:'device'},{serial:'b',state:'device'}],'b')"),'b');
  assert.equal(run("androidCaptureFileUrl({id:'session one'},{path:'modules/首页 拼图.png'})"),'/api/android-capture/sessions/session%20one/file?path=modules%2F%E9%A6%96%E9%A1%B5%20%E6%8B%BC%E5%9B%BE.png');
  assert.equal(run("androidCaptureFileUrl({id:'s1'},{url:'javascript:alert(1)'})"),'');
  assert.equal(run("androidCaptureFileUrl({id:'s1'},{url:'/api/android-capture/sessions/other/file?path=x'})"),'');
  assert.equal(run("androidCaptureAppVersion({name:'2.8.1',code:81})"),'2.8.1 (81)');
  assert.equal(run("androidCaptureAppVersion({name:'2.8.1'})"),'2.8.1');
  assert.equal(run("androidCaptureAppVersion('1.0')"),'1.0');
  const history=run("androidCaptureHistoryHtml([{id:'list',package:'com.app',app_version:{name:'2.8.1',code:81},composite_count:4,composites:[],status:'ready'}])");
  assert(history.includes('App 2.8.1 (81)'));
  assert(history.includes('4 张模块拼图'));
  assert(!history.includes('[object Object]'));

  // Paused/blocked tasks expose handoff and permit confirming partial evidence
  // only after real images exist. They retain their paused/blocked status.
  mount('paused');
  run("androidCaptureModal.session.pause_reason='请在手机上完成登录'; androidCaptureModal.session.app_version={name:'2.8.1',code:81}; androidCaptureRenderSession(androidCaptureModal)");
  assert(rootHTML.includes('请在手机上完成登录'));
  assert(rootHTML.includes('data-capture-operation="resume"'));
  assert(!rootHTML.includes('data-capture-operation="confirm"'));
  assert(!rootHTML.includes('data-capture-operation="tap"'));
  assert(rootHTML.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert(rootHTML.includes('App 2.8.1 (81)'));
  assert(!rootHTML.includes('[object Object]'));
  run("androidCaptureModal.session.observations=[{id:'o1',path:'observations/home.png'}]; androidCaptureRenderSession(androidCaptureModal)");
  assert(rootHTML.includes('确认当前部分证据'));
  assert(rootHTML.includes('data-capture-operation="confirm"'));
  assert(rootHTML.includes('范围和模块缺口会一同保留'));
  assert(rootHTML.includes('等待你接管'));
  assert(!rootHTML.includes('待确认入库'));
  mount('blocked');
  run('androidCaptureRenderSession(androidCaptureModal)');
  assert(!rootHTML.includes('data-capture-operation="confirm"'));
  run("androidCaptureModal.session.composites=[{path:'modules/partial.png',title:'部分流程'}]; androidCaptureRenderSession(androidCaptureModal)");
  assert(rootHTML.includes('确认当前部分证据'));
  assert(rootHTML.includes('需要你处理'));
  assert(!rootHTML.includes('待确认入库'));
  mount('cancelled');
  run('androidCaptureRenderSession(androidCaptureModal)');
  assert(rootHTML.includes('data-capture-operation="resume"'));
  assert(rootHTML.includes('继续自动走查'));
  assert(!rootHTML.includes('data-capture-operation="confirm"'));
  mount('ready');
  run("androidCaptureModal.session.composites=[{path:'modules/home.png',title:'首页流程'}]; androidCaptureModal.session.modules=[{title:'付款',status:'blocked',reason:'未执行真实购买'}]; androidCaptureRenderSession(androidCaptureModal)");
  assert(rootHTML.includes('data-capture-operation="confirm"'));
  assert(rootHTML.includes('首页流程'));
  assert(rootHTML.includes('未执行真实购买'));
  assert(rootHTML.includes('/s1/export'));

  // Double click creates one task, starts it once, and pins the creation scope.
  mount();
  run("androidCaptureModal.session=null; Object.assign(androidCaptureModal.draft,{package:'com.example.app',scope:'首页',title:'走查',serial:'serial1'})");
  apiCalls=[];
  let resolveCreate;
  pendingAPI=async(path,body)=>{
    if(path==='/api/android-capture/sessions') return await new Promise(resolve=>{resolveCreate=resolve;});
    if(path.endsWith('/start')) return {id:'created',status:'running',package:'com.example.app',progress:[]};
    return {sessions:[]};
  };
  const first=run('androidCaptureCreate(androidCaptureModal)');
  const second=run('androidCaptureCreate(androidCaptureModal)');
  await second;
  assert.equal(apiCalls.filter(item=>item.path==='/api/android-capture/sessions').length,1);
  assert.equal(apiCalls[0].body.project_id,'p1');
  assert.equal(apiCalls[0].body.version_id,'');
  resolveCreate({id:'created',status:'prepared',package:'com.example.app',progress:[]});
  await first;
  assert.equal(apiCalls.filter(item=>item.path.endsWith('/start')).length,1);

  // Explicit action invalidates older polling responses and refreshes materials
  // only after server confirmation has succeeded.
  mount('ready'); apiCalls=[]; refreshed=0;
  pendingAPI=async(path)=>path.endsWith('/confirm')?{id:'s1',status:'confirmed',document_ids:['d1']}:{sessions:[]};
  await run("androidCaptureOperation(androidCaptureModal,'confirm')");
  assert.equal(refreshed,1);
  assert.equal(run('androidCaptureModal.session.status'),'confirmed');
  assert.equal(run('androidCaptureModal.request'),1);
  assert(rootHTML.includes('已加入当前项目资料'));
  assert(!rootHTML.includes('data-capture-operation="confirm"'));

  // A project/version change closes the old view before another poll can read it.
  mount('running'); apiCalls=[];
  run('androidCaptureSchedule(androidCaptureModal)');
  assert(timers.size>0);
  const latestTimer=[...timers.values()].at(-1);
  currentVersionId='different';
  await latestTimer();
  assert.equal(element('#modal').open,false);
  assert.equal(apiCalls.length,0);
  console.log(JSON.stringify({checks:'PASS',scenarios:6}));
})().catch(error=>{ console.error(error); process.exitCode=1; });
"""
    result = subprocess.run(
        [node, "-e", script], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"checks": "PASS", "scenarios": 6}


def test_android_capture_assets_and_entry_are_loaded():
    html = (ROOT / "workbench/static/index.html").read_text(encoding="utf-8")
    workspace = (ROOT / "workbench/static/render/workspace.js").read_text(encoding="utf-8")
    dossiers = (ROOT / "workbench/static/features/competitor_dossiers.js").read_text(encoding="utf-8")
    events = (ROOT / "workbench/static/modules/events.js").read_text(encoding="utf-8")
    assert '/features/android_capture.js' in html
    assert html.index('/features/android_capture.js') < html.index('/modules/events.js')
    assert 'data-action="android-capture"' in dossiers
    assert 'id="android-capture-history"' in workspace
    assert 'androidCaptureRenderHistory();' in workspace
    assert 'await openAndroidCapture(b.dataset.androidCaptureSession)' in events
