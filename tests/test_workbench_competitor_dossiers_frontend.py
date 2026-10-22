"""Offline behavioral checks for dossier evidence selection and upload ownership."""
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend checks")
    result = subprocess.run([node, "-e", script], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_dossier_selection_scopes_and_source_boundaries():
    run_node(r"""
const fs=require('fs'), vm=require('vm'), assert=require('node:assert/strict');
const sandbox={URL, console, projectId:'p1', version:null, currentVersion:()=>sandbox.version,
  document:{addEventListener(){}}, E:x=>String(x??'').replaceAll('<','&lt;').replaceAll('>','&gt;'),
  date:x=>x||'', scrapeStatusNames:{ready:'待确认',completed:'已确认'}, state:{competitors:[{id:'a',app_id:'com.a',platform:'google_play'},{id:'b',app_id:'com.b',platform:'google_play'}],documents:[
    {id:'a1',name:'A.md',kind:'upload',competitor_ids:['a'],competitor_material_types:{a:'store_info'},versions:[]},
    {id:'a2',name:'A.png',kind:'upload',competitor_ids:['a'],competitor_material_types:{a:'store_screenshot'},versions:[]},
    {id:'b1',name:'B.csv',kind:'upload',competitor_ids:['b'],competitor_material_types:{b:'reviews'},versions:[]},
    {id:'pending',name:'unconfirmed.md',kind:'upload',status:'ready',competitor_ids:['a'],versions:[]},
    {id:'draft',name:'draft.md',kind:'deliverable',competitor_ids:['a'],versions:[]},
    {id:'other-version',name:'V2.md',kind:'upload',competitor_ids:['a'],versions:[{id:'v2'}]},
    {id:'common',name:'common.md',kind:'upload',versions:[]}
  ]}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('workbench/static/features/competitor_dossiers.js','utf8'),sandbox);
const q=x=>vm.runInContext(x,sandbox);
assert.equal(q('dossierSession().selected.size'),0);
assert.equal(q('dossierSession().inputs.size'),0);
q("dossierSession().selected.add('a')");
assert.equal(q('dossierSession().inputs.size'),0,'Selecting a competitor must not select every document');
assert.equal(q("JSON.stringify(dossierInputDocuments().map(d=>d.id))"),'["a1","a2","common"]');
q("dossierSession().inputs.add('a1');dossierSession().inputs.add('b1');dossierSession().inputs.add('pending');dossierPruneInputs()");
assert.equal(q("JSON.stringify([...dossierSession().inputs])"),'["a1"]');
assert(q('dossierInputSummary()').includes('1 个竞品、1 份文档、0 张截图'));
q("dossierSession().inputs.add('a2')");
assert(q('dossierInputSummary()').includes('1 张截图'));
sandbox.projectId='p2';
assert.equal(q('dossierSession().inputs.size'),0);
sandbox.projectId='p1';
assert.equal(q('dossierSession().inputs.size'),2);
sandbox.version={id:'v2'};
assert.equal(q('dossierSession().inputs.size'),0,'Version selections must be isolated');
q("dossierSession().selected.add('a')");
assert(q("dossierInputDocuments().some(d=>d.id==='other-version')"));
sandbox.version=null;
assert.equal(q("dossierDocumentTypes({competitor_material_types:{a:'store_info',b:'note'}},'b')[0]"),'note');
assert.equal(q("dossierParseIdentity('https://apps.apple.com/us/app/test/id12345','google_play').app_id"),'12345');
assert.equal(q("dossierParseIdentity('https://play.google.com/store/apps/details?id=com.a','google_play').platform"),'google_play');
for(const bad of ['javascript:alert(1)','https://evil.test/path','https://user:secret@play.google.com/store/apps/details?id=com.a']){
  assert.throws(()=>q(`dossierParseIdentity(${JSON.stringify(bad)},'google_play')`));
}
assert.equal(q("dossierRoleLabels['']"),'未指定用途');
const markup=q("dossierInputTree(dossierSession())");
assert(markup.includes('data-dossier-input="a1"'));
assert(!markup.includes('data-dossier-input="pending"'));
assert(!markup.includes('data-dossier-input="other-version"'));
assert(q("dossierFileRow({id:'x',name:'<script>bad</script>.md',created:'',material_type:'note'})").includes('&lt;script&gt;'));
const detail={id:'a',app_id:'com.a',role:'',documents:[],scrapes:[{id:'ready',status:'ready',listing:{short_description:'Not confirmed'}},{id:'done',status:'completed',listing:{short_description:'Confirmed description',long_description:'Full description'}}]};
sandbox.detail=detail;
const overview=q("dossierDetailPane(detail,'overview')");
assert(overview.includes('Confirmed description'));
assert(!overview.includes('Not confirmed'));
assert(q("dossierDetailPane({...detail,documents:[]},'images')").includes('App 实机截图'));
console.log('PASS');
""")


def test_upload_queue_freezes_dossier_and_version_at_enqueue_time():
    run_node(r"""
const fs=require('fs'), vm=require('vm'), assert=require('node:assert/strict');
const sandbox={URL:{createObjectURL:()=>'',revokeObjectURL(){}},console,projectId:'p1',version:{id:'v1'},currentVersion:()=>sandbox.version,
  document:{addEventListener(){}},$:(selector)=>selector==='#dossier-upload-type'?{value:'device_screenshot'}:null,
  E:x=>String(x??''),state:{competitors:[{id:'a',app_id:'com.a',title:'A'}],documents:[]},toast(){},error(e){throw e;},globalThis:{crypto:{randomUUID:()=>String(Math.random())}}};
vm.createContext(sandbox);
for(const f of ['competitor_dossiers.js','materials.js'])vm.runInContext(fs.readFileSync('workbench/static/features/'+f,'utf8'),sandbox);
const q=x=>vm.runInContext(x,sandbox);
q("dossierSession().detail='a'");
sandbox.file={name:'screen.png',size:10,lastModified:42,type:'image/png'};
q('queueMaterialFiles([file])');
assert.equal(q('pendingMaterialFiles[0].competitorId'),'a');
assert.equal(q('pendingMaterialFiles[0].materialType'),'device_screenshot');
q("dossierSession().detail=''");
sandbox.version={id:'v2'};
assert.equal(q('pendingMaterialFiles[0].version'),'v1');
q('clearPendingMaterials()');
assert.equal(q('pendingMaterialFiles.length'),1,'Clearing a different version cannot discard the old queue');
sandbox.version={id:'v1'};
q('clearPendingMaterials()');
assert.equal(q('pendingMaterialFiles.length'),0);
console.log('PASS');
""")


def test_collection_and_task_payloads_have_independent_explicit_flags():
    integrations = (ROOT / "workbench/static/features/integrations.js").read_text(encoding="utf-8")
    tasks = (ROOT / "workbench/static/features/tasks.js").read_text(encoding="utf-8")
    index = (ROOT / "workbench/static/index.html").read_text(encoding="utf-8")
    for name in ("scrape-collect-listing", "scrape-collect-reviews", "scrape-collect-screenshots", "scrape-collect-device"):
        assert name in integrations
    assert "collection_options" in integrations
    assert "data-collection-override" in integrations
    assert "translate: anyReviews" in integrations
    assert 'source_selection_mode: sourceSelectionMode' in tasks
    assert 'competitor_ids: competitorIds' in tasks
    assert '/features/competitor_dossiers.js' in index
