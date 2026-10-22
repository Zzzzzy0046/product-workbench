"""One project material page with explicit competitor and public source selection."""
from test_workbench_competitor_dossiers_frontend import ROOT, run_node


def test_single_material_page_has_inline_public_group_and_no_mode_switch():
    dossiers = (ROOT / "workbench/static/features/competitor_dossiers.js").read_text(encoding="utf-8")
    workspace = (ROOT / "workbench/static/render/workspace.js").read_text(encoding="utf-8")
    materials = (ROOT / "workbench/static/features/materials.js").read_text(encoding="utf-8")
    for source in (dossiers, workspace, materials):
        assert "data-dossier-view" not in source
        assert "materialWorkspaceView" not in source
        assert "dossierNavigation" not in source
    assert 'id="project-public-materials"' in dossiers
    assert 'drawCommonProjectMaterials("#project-public-materials")' in dossiers
    assert "返回项目资料" in dossiers
    assert "通用项目资料" not in workspace
    assert "data-dossier-public-select" in workspace
    assert "data-dossier-public-attach" in workspace
    assert "data-competitor-analysis=" not in workspace, "No bulk shortcut may inject unchecked competitor sources"
    assert dossiers.index("${dossierAnalysisPanel(session)}") < dossiers.index('id="project-material-tools"')


def test_public_inputs_are_explicit_scoped_and_do_not_need_a_selected_competitor():
    run_node(r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const sandbox={URL,console,projectId:'p',version:null,currentVersion:()=>sandbox.version,
document:{addEventListener(){}},E:x=>String(x??''),date:x=>x||'',state:{competitors:[{id:'a',title:'A'}],documents:[
{id:'common',name:'common.md',kind:'upload',versions:[]},
{id:'common-v1',name:'v1.md',kind:'upload',versions:[{id:'v1'}]},
{id:'pending',name:'pending.md',kind:'upload',status:'ready',versions:[]},
{id:'unconfirmed',name:'unconfirmed.md',kind:'upload',confirmed:false,versions:[]},
{id:'draft',name:'draft.md',kind:'draft',versions:[]},
{id:'deliverable',name:'output.md',kind:'deliverable',versions:[]},
{id:'accepted',name:'accepted.md',kind:'accepted',versions:[]},
{id:'a',name:'a.md',kind:'upload',competitor_ids:['a'],versions:[]},
{id:'a-accepted',name:'accepted-a.md',kind:'accepted',competitor_ids:['a'],versions:[]}
]}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('workbench/static/features/competitor_dossiers.js','utf8'),sandbox);
const q=x=>vm.runInContext(x,sandbox);
assert.equal(q('dossierSession().selected.size'),0);
assert.equal(q('dossierSession().inputs.size'),0);
assert.equal(q('JSON.stringify(dossierInputDocuments().map(d=>d.id))'),'["common"]');
const tree=q('dossierInputTree(dossierSession())');
assert(tree.includes('项目公共资料'));
assert(tree.includes('data-dossier-input="common"'));
for(const id of ['common-v1','pending','unconfirmed','draft','deliverable','accepted','a'])assert(!tree.includes(`data-dossier-input="${id}"`));
q("dossierSession().inputs.add('common')");
assert(q('dossierInputSummary()').includes('0 个竞品、1 份文档'));
assert(q('dossierInputSummary()').includes('含 1 份项目公共资料'));
assert(q('dossierAnalysisPanel(dossierSession())').includes('data-dossier-prepare >'));
q("dossierSession().selected.add('a')");
assert.equal(q('JSON.stringify(dossierInputDocuments().map(d=>d.id))'),'["common","a"]');
sandbox.version={id:'v1'};
assert.equal(q('dossierSession().inputs.size'),0);
q("dossierSession().inputs.add('common-v1');dossierSession().publicSelected.add('common-v1')");
sandbox.state.documents.find(d=>d.id==='common-v1').versions=[{id:'v2'}];
q('dossierPruneInputs()');
assert.equal(q('dossierSession().inputs.size'),0);
assert.equal(q('dossierSession().publicSelected.size'),0);
sandbox.version=null;
assert.equal(q('dossierSession().inputs.size'),1,'Previous scope keeps only its own explicit selection');
sandbox.state.documents.find(d=>d.id==='common').competitor_ids=['unselected'];
q('dossierPruneInputs()');
assert.equal(q('dossierSession().inputs.size'),0,'Public source moved into an unselected competitor cannot leak into input');
console.log('PASS');
""")


def test_whole_page_render_keeps_public_library_and_unique_intake_controls():
    run_node(r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{innerHTML:'',value:'',querySelectorAll:()=>[],querySelector:()=>null,addEventListener(){},classList:{add(){},remove(){}}});return nodes.get(id);}
const sandbox={URL,console,projectId:'p',version:null,currentVersion:()=>sandbox.version,tab:'materials',
document:{addEventListener(){}},$:node,E:x=>String(x??''),date:x=>x||'',kinds:{upload:'资料'},
imageSuffixes:new Set(['png']),androidCaptureRenderHistory(){},reviewFilterSummary:()=>'',scrapeStatusNames:{},
state:{competitors:[{id:'a',title:'Test App',app_id:'com.test',platform:'google_play'}],documents:[
{id:'common',name:'research.md',kind:'upload',category:'research',versions:[]},
{id:'image',name:'screen.png',kind:'upload',category:'images',versions:[]},
{id:'competitor',name:'private.md',kind:'upload',competitor_ids:['a'],versions:[]},
{id:'draft',name:'draft.md',kind:'draft',versions:[]},
{id:'other-version',name:'v2.md',kind:'upload',versions:[{id:'v2'}]}
]}};
vm.createContext(sandbox);
for(const f of ['features/materials.js','features/competitor_dossiers.js','render/workspace.js'])vm.runInContext(fs.readFileSync('workbench/static/'+f,'utf8'),sandbox);
const q=x=>vm.runInContext(x,sandbox);
q('drawCompetitorDossiers(false)');
const top=node('#view').innerHTML,common=node('#project-public-materials').innerHTML,tools=node('#project-material-tools').innerHTML;
assert(top.includes('Test App'));
assert(top.includes('未指定用途'));
assert(common.includes('项目公共资料'));
assert(common.includes('research.md'));assert(common.includes('screen.png'));
for(const name of ['private.md','draft.md','v2.md'])assert(!common.includes(name));
assert(tools.includes('实机走查记录'));assert(tools.includes('查找资料依据'));
assert(!common.includes('实机走查记录'),'Auxiliary tools follow the analysis panel, not the public group');
const markup=top+common+tools;
for(const id of ['upload','pick-materials','material-paste-zone','pending-materials','material-library','search-query'])assert.equal((markup.match(new RegExp(`id="${id}"`,'g'))||[]).length,1,`${id} must be unique`);
assert(!markup.includes('data-dossier-view'));
q("dossierSession().detail='a';renderDossierDetail(state.competitors[0],{id:'a',documents:[],scrapes:[]})");
assert(node('#view').innerHTML.includes('返回项目资料'));
assert(!node('#view').innerHTML.includes('data-dossier-view'));
console.log('PASS');
""")


def test_public_only_preparation_keeps_empty_competitors_and_explicit_documents():
    run_node(r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const choice={dataset:{dossierChosenTask:'fast/f1-category-user'}};
const sandbox={URL,console,projectId:'p',currentVersion:()=>null,
document:{addEventListener(){},querySelectorAll:()=>[choice]},E:x=>String(x??''),modal(){},
state:{competitors:[],documents:[{id:'public',name:'research.md',kind:'upload',versions:[]}],packs:[{tasks:[{key:'fast/f1-category-user',name:'品类与用户'}]}]},
api:async(path,payload)=>{sandbox.sent={path,payload};return {document_ids:payload.document_ids,competitor_ids:[]};},
prepareTask:(key,options)=>{sandbox.prepared={key,options};}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('workbench/static/features/competitor_dossiers.js','utf8'),sandbox);
const q=x=>vm.runInContext(x,sandbox);
(async()=>{
q("dossierSession().inputs.add('public')");
await q('dossierPrepare({disabled:false})');
assert.equal(sandbox.sent.path,'/api/competitors/inputs');
assert.equal(JSON.stringify(sandbox.sent.payload.competitor_ids),'[]');
assert.equal(JSON.stringify(sandbox.sent.payload.document_ids),'["public"]');
choice.onclick();
assert.equal(sandbox.prepared.options.sourceSelectionMode,'explicit');
assert.equal(JSON.stringify(sandbox.prepared.options.competitorIds),'[]');
assert.equal(JSON.stringify(sandbox.prepared.options.documentIds),'["public"]');
console.log('PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
