import base64
import importlib.util
import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('workbench_app', Path(__file__).parents[1]/'workbench/app.py')
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


@pytest.fixture
def bench(tmp_path):
    return app.Workbench(tmp_path,runner=lambda job:'# 测试交付物\n\n[待验证] 这是自动化测试生成的正文，不是真实产品结论。\n\n## 下一步\n补充资料。')


def test_project_isolation_and_persistence(bench):
    a = bench.create_project('项目一','本地阅读器')
    b = bench.create_project('项目二','另一个项目')
    doc = bench.add_document(a['id'],'独占材料.txt','孤独标识onlythisproject 数据'.encode())
    assert bench.search(a['id'],'onlythisproject')[0]['source_id'] == doc['id']
    assert not bench.search(b['id'],'onlythisproject')
    assert app.Workbench(bench.data).project(a['id'])['name'] == '项目一'


def test_project_delete_requires_name_and_keeps_recovery_snapshot(bench):
    project=bench.create_project('待删除项目','包含本地资料和交付物')
    other=bench.create_project('保留项目','不能被误删')
    uploaded=bench.add_document(project['id'],'研究资料.txt','这是需要随项目备份的研究资料。'.encode())
    job=bench.prepare(project['id'],'product/framework','')
    bench.complete(job['id'],'# 项目交付物\n\n这是删除项目前生成的完整交付物，应当进入可恢复快照。')
    bench.edit_output(job['id'],'# 项目交付物 V2\n\n这是编辑后的完整交付物，应当连同历史版本进入恢复快照。','更新正文')
    bench.add_comment(job['id'],{
        'version':2, 'block_id':'block-1', 'block_type':'heading',
        'block_label':'项目交付物 V2', 'quote':'# 项目交付物 V2',
        'action':'modify', 'note':'把标题改得更明确', 'author':'产品经理',
    })
    with pytest.raises(ValueError,match='名称不匹配'):
        bench.delete_project(project['id'],'错误名称')

    result=bench.delete_project(project['id'],'待删除项目')
    backup=Path(result['backup'])
    assert result['deleted'] is True
    assert backup.is_relative_to(bench.data/'trash')
    assert (backup/'project-export.json').is_file()
    assert (backup/'uploads'/(uploaded['id']+'.txt')).is_file()
    assert (backup/'runs'/job['id']/'交付物-v0002.md').is_file()
    snapshot=json.loads((backup/'project-export.json').read_text(encoding='utf-8'))
    assert snapshot['project']['name']=='待删除项目'
    assert len(snapshot['job_versions'])==2
    assert len(snapshot['document_comments'])==1
    with pytest.raises(ValueError,match='项目不存在'):
        bench.project(project['id'])
    assert bench.project(other['id'])['name']=='保留项目'
    assert not bench.rows('SELECT id FROM documents WHERE project_id=?',(project['id'],))
    assert not bench.rows('SELECT id FROM jobs WHERE project_id=?',(project['id'],))

    trash_id=backup.name
    assert bench.trash_items()[0]['id']==trash_id
    restored=bench.restore_project(trash_id)
    assert restored['id']==project['id']
    assert bench.project(project['id'])['name']=='待删除项目'
    assert bench.rows('SELECT id FROM jobs WHERE project_id=?',(project['id'],))
    assert (bench.data/'runs'/job['id']/'交付物-v0002.md').is_file()
    assert bench.trash_items()[0]['restored'] is True
    with pytest.raises(ValueError,match='已经恢复'):
        bench.restore_project(trash_id)
    with pytest.raises(ValueError,match='名称不匹配'):
        bench.permanently_delete_trash(trash_id,'错误名称')
    assert bench.permanently_delete_trash(trash_id,'待删除项目')['deleted'] is True
    assert not backup.exists()


def test_upload_validation_and_duplicate(bench):
    p = bench.create_project('产品','')
    for name,content in [('../secret.txt',b'x'),('bad.exe',b'a'),('empty.txt',b'')]:
        with pytest.raises(ValueError):
            bench.add_document(p['id'],name,content)
    doc = bench.add_document(p['id'],'评论.csv','用户,评论\nA,很喜欢'.encode())
    assert bench.add_document(p['id'],'评论2.csv','用户,评论\nA,很喜欢'.encode())['duplicate']
    assert doc['id']


def test_docx_extraction():
    content=io.BytesIO()
    with zipfile.ZipFile(content,'w') as archive:
        archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>中文需求</w:t></w:r></w:p></w:body></w:document>')
    assert '中文需求' in app.extract('需求.docx',content.getvalue())


def test_capability_switch_and_template(bench):
    p=bench.create_project('新品','背景')
    with bench.db() as db:
        db.execute('INSERT OR REPLACE INTO preferences VALUES(?,?)',('pack:reviews','true'))
    job=bench.prepare(p['id'],'reviews/review-analysis','分析差评')
    assert '样本与来源' in job['prompt']
    t1=bench.prepare(p['id'],'product/new-product','')
    assert '## 0. 文档信息与一页结论' in t1['prompt']
    assert '## 12.' in t1['prompt']


def test_fast_path_project_profile_and_tasks(bench):
    p=bench.create_project(
        '快速新品',
        '对标竞品快速开发',
        workflow_mode='fast',
        platform='Android-first',
        team='1 产品、1 Android、设计兼职',
        timebox='10 个工作日',
    )
    assert p['workflow_mode']=='fast'
    keys={task['key'] for pack in bench.registry() for task in pack['tasks']}
    assert {'fast/new-product-analysis','fast/core-prd','fast/acceptance'} <= keys
    assert not {'fast/competitor-delta','fast/spikes','fast/acceptance-run'} & keys
    job=bench.prepare(p['id'],'fast/new-product-analysis','只做核心闭环')
    assert '# F1 新品需求分析' in job['prompt']
    assert '## 2. 行业与市场背景' in job['prompt']
    assert '## 7. 产品功能框架' in job['prompt']
    assert '## 8. 核心功能说明' in job['prompt']
    assert '## 10. 商业化策略' in job['prompt']
    assert '## 11. 进入 PRD 的交付结论' in job['prompt']
    assert '## 11. 平台、权限、数据与政策要求' not in job['prompt']
    assert 'F1 不输出平台、权限、数据或政策章节' in job['prompt']
    assert '不生成机会门、用户访谈、风险清单、假设验证矩阵、技术 Spike 或条件闭环' in job['prompt']
    assert '正文最多 16000 个中文字符' in job['prompt']
    assert 'template-t1-new-product-analysis' not in {source['source_id'] for source in job['sources']}
    assert '无法核验时用普通语言说明' in job['prompt']
    assert '1 产品、1 Android、设计兼职' in job['prompt']
    assert '10 个工作日' in job['prompt']


def test_draft_can_be_pinned_with_warning_but_not_auto_retrieved(bench):
    p=bench.create_project('并行项目','')
    draft=bench.prepare(p['id'],'fast/new-product-analysis','')
    body='# 草稿定义\n\n这是 onlydraftsignal，只允许显式引用的未评审草稿。'
    bench.complete(draft['id'],body)
    assert not any(s['source_id']==draft['id'] for s in bench.search(p['id'],'onlydraftsignal'))
    next_job=bench.prepare(p['id'],'fast/core-prd','并行准备',[draft['id']])
    assert next_job['sources'][0]['draft'] is True
    assert '尚未评审通过的草稿' in next_job['prompt']
    bench.review(draft['id'],'accepted','确认')
    accepted=bench.prepare(p['id'],'fast/core-prd','继续',[draft['id']])
    assert not accepted['sources'][0].get('draft',False)


def test_condition_requires_owner_due_and_closing_evidence(bench):
    p=bench.create_project('条件项目','')
    with pytest.raises(ValueError):
        bench.save_condition(p['id'],{'title':'许可证结论'})
    item=bench.save_condition(p['id'],{
        'title':'许可证形成书面结论',
        'owner':'Android 研发',
        'due':'2026-09-18',
        'status':'open',
        'block_level':'internal-test',
    })
    with pytest.raises(ValueError):
        bench.save_condition(p['id'],{**item,'status':'closed','evidence':''})
    closed=bench.save_condition(p['id'],{**item,'status':'closed','evidence':'许可证清单 v1'})
    assert closed['status']=='closed'
    assert bench.conditions(p['id'])[0]['evidence']=='许可证清单 v1'
    job=bench.prepare(p['id'],'fast/new-product-analysis','')
    assert '快速模式不使用独立条件清单' in job['prompt']


def test_fast_acceptance_combines_plan_and_actual_evidence(bench):
    p=bench.create_project('开发验收','')
    plan=bench.prepare(p['id'],'fast/acceptance','',[])
    assert '同一张表填写“实测、证据和修改结果”' in plan['prompt']
    assert '正文最多 5000 个中文字符' in plan['prompt']
    evidence=bench.add_document(p['id'],'实际测试记录.txt','构建 v0.1，Pixel 设备，QA-001 实际执行失败。'.encode())
    job=bench.prepare(p['id'],'fast/acceptance','',[evidence['id']])
    assert '实际测试记录' in job['prompt']


def test_image_upload_becomes_visual_source(bench):
    p=bench.create_project('截图项目','')
    pixel=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
    screenshot=bench.add_document(p['id'],'竞品首页.png',pixel)
    job=bench.prepare(p['id'],'fast/new-product-analysis','分析截图',[screenshot['id']])
    assert job['sources'][0]['image_path'].endswith('.png')
    assert Path(job['sources'][0]['image_path']).is_file()
    assert '图片内容将在生成任务时作为视觉输入读取' in job['prompt']


def test_conditional_acceptance_requires_registered_condition(bench):
    p=bench.create_project('有条件验收','',workflow_mode='full')
    evidence=bench.add_document(p['id'],'结果.txt','实际测试记录和日志索引'.encode())
    job=bench.prepare(p['id'],'product/acceptance-run','',[evidence['id']])
    bench.complete(job['id'],'# 验收结果\n\n最终结果：`Conditional`\n\n仍有兼容性问题。')
    with pytest.raises(ValueError):
        bench.review(job['id'],'accepted','接受有条件结论')
    bench.save_condition(p['id'],{
        'title':'兼容性复测', 'owner':'QA', 'due':'2026-09-20',
        'status':'open', 'block_level':'external-release', 'evidence':''
    })
    assert bench.review(job['id'],'accepted','接受有条件结论')['review']['decision']=='accepted'


def test_fast_conditional_acceptance_must_be_closed_in_same_checklist(bench):
    p=bench.create_project('快速验收','',workflow_mode='fast')
    job=bench.prepare(p['id'],'fast/acceptance','')
    bench.complete(job['id'],'# 开发验收\n\n最终结果：`Conditional`\n\n仍有问题待复测。')
    with pytest.raises(ValueError,match='同一清单'):
        bench.review(job['id'],'accepted','先接受')


def test_context_snapshot_and_pinned_materials(bench):
    p=bench.create_project('测试','原背景')
    with bench.db() as db:
        db.execute('INSERT INTO contexts VALUES(?,?,?)',(p['id'],'仅 Android','已经决定做离线阅读'))
    d=bench.add_document(p['id'],'重点.txt',('这是重点资料。'*2500).encode())
    job=bench.prepare(p['id'],'product/prd','核心流程',[d['id']])
    assert '仅 Android' in job['prompt']
    assert job['sources'][0]['truncated']
    assert '仅 Android' in (bench.data/'runs'/job['id']/'任务包.md').read_text(encoding='utf-8')
    with bench.db() as db:
        db.execute('UPDATE contexts SET foundation=? WHERE project_id=?',('iOS',p['id']))
    assert '仅 Android' in bench.job(job['id'])['prompt']
    other=bench.create_project('其他','')
    with pytest.raises(ValueError):
        bench.prepare(other['id'],'product/prd','',[d['id']])


def test_execution_review_and_revision(bench):
    p=bench.create_project('验证','')
    job=bench.prepare(p['id'],'product/framework','')
    bench.start(job['id'])
    for _ in range(100):
        if bench.job(job['id'])['status'] not in {'running','queued'}:
            break
        time.sleep(.01)
    job=bench.job(job['id'])
    assert job['status']=='completed'
    assert (bench.data/'runs'/job['id']/'交付物.md').is_file()
    assert not any(s['source_id']==job['id'] for s in bench.search(p['id'],'自动化测试'))
    bench.review(job['id'],'accepted','确认用于后续')
    assert any(s['source_id']==job['id'] for s in bench.search(p['id'],'自动化测试'))
    bench.review(job['id'],'changes_requested','补充异常状态')
    revision=bench.revise(job['id'])
    assert revision['id'] != job['id']
    assert '补充异常状态' in revision['prompt']
    assert '上一版完整正文' in revision['prompt']
    assert revision['sources'] == job['sources']
    assert revision['parent_job_id']==job['id']
    assert revision['revision_reason']=='overall'
    assert not any(s['source_id']==job['id'] for s in bench.search(p['id'],'自动化测试'))


def test_direct_edit_creates_versions_resets_review_and_restores(bench):
    p=bench.create_project('可编辑交付物','')
    job=bench.prepare(p['id'],'product/framework','')
    original='# 第一版交付物\n\n这是第一版完整正文，用来验证编辑、版本记录与恢复能力，不代表真实产品结论。'
    edited='# 第二版交付物\n\n这是产品经理直接修改后的完整正文，应该成为新的待评审版本。'
    bench.complete(job['id'],original)
    assert bench.job(job['id'])['current_version']==1
    assert bench.versions(job['id'])[0]['source']=='generated'
    bench.review(job['id'],'accepted','第一版确认')

    updated=bench.edit_output(job['id'],edited,'删减背景并补充核心流程')
    assert updated['output']==edited
    assert updated['current_version']==2
    assert updated['review'] is None
    assert bench.rows('SELECT kind,text FROM documents WHERE id=?',(job['id'],))[0]=={'kind':'deliverable','text':edited}
    assert (bench.data/'runs'/job['id']/'交付物-v0002.md').read_text(encoding='utf-8')==edited
    with pytest.raises(ValueError,match='没有变化'):
        bench.edit_output(job['id'],edited)

    restored=bench.restore_version(job['id'],1)
    assert restored['output']==original
    assert restored['current_version']==3
    versions=bench.versions(job['id'])
    assert [item['version'] for item in versions]==[3,2,1]
    assert versions[0]['source']=='restore'
    assert versions[0]['note']=='恢复自版本 V1'


def test_location_comments_are_version_bound_and_prepare_scoped_revision(bench):
    p=bench.create_project('定位批注','')
    job=bench.prepare(p['id'],'product/framework','')
    original='# 产品框架\n\n## 核心能力\n\n支持本地文件扫描和游戏启动。\n\n| 功能 | 说明 |\n|---|---|\n| 扫描 | 查找 ROM |'
    bench.complete(job['id'],original)
    comment=bench.add_comment(job['id'],{
        'version':1,
        'block_id':'block-3',
        'block_type':'paragraph',
        'block_label':'支持本地文件扫描和游戏启动。',
        'quote':'支持本地文件扫描和游戏启动。',
        'action':'modify',
        'note':'补充首次授权失败后的恢复入口。',
        'author':'Simon',
    })
    assert comment['status']=='open'
    assert bench.job(job['id'])['comments'][0]['block_id']=='block-3'
    assert bench.update_comment(job['id'],comment['id'],'resolved')['status']=='resolved'
    assert bench.update_comment(job['id'],comment['id'],'open')['status']=='open'

    revision=bench.revise_from_comments(job['id'])
    assert revision['id']!=job['id']
    assert 'block-3 / paragraph' in revision['prompt']
    assert '修改动作：修改' in revision['prompt']
    assert '补充首次授权失败后的恢复入口。' in revision['prompt']
    assert '没有批注的章节、段落和表格保持原意' in revision['prompt']
    assert '不把批注、修订记录、审计过程或工作流状态元数据写入正文' in revision['prompt']
    record=json.loads((bench.data/'runs'/revision['id']/'执行记录.json').read_text(encoding='utf-8'))
    assert record['comment_revision_of']['comment_ids']==[comment['id']]
    assert revision['parent_job_id']==job['id']
    assert revision['revision_number']==2
    assert revision['revision_reason']=='comments'
    assert revision['source_version']==1
    assert revision['workflow_mode']==job['workflow_mode']
    bench.complete(revision['id'],'# 产品框架修订版\n\n## 核心能力\n\n支持授权失败后的恢复入口。')
    assert bench.job(job['id'])['comments'][0]['status']=='resolved'

    updated=bench.edit_output(job['id'],original+'\n\n## 新版本\n\n正文版本变化后旧批注不能继续驱动修订。')
    assert updated['current_version']==2
    assert updated['comments'][0]['version']==1
    with pytest.raises(ValueError,match='当前版本没有待处理'):
        bench.revise_from_comments(job['id'])
    with pytest.raises(ValueError,match='正文版本已变化'):
        bench.add_comment(job['id'],{
            'version':1, 'block_id':'block-1', 'block_type':'heading',
            'block_label':'产品框架', 'quote':'# 产品框架',
            'action':'delete', 'note':'删除标题', 'author':'Simon',
        })


def test_cancel_failure_and_restart(bench):
    p=bench.create_project('验证','')
    job=bench.prepare(p['id'],'product/framework','')
    bench.cancel(job['id'])
    with pytest.raises(ValueError):
        bench.start(job['id'])
    restored=bench.restore_cancelled(job['id'])
    assert restored['status']=='prepared'
    with pytest.raises(ValueError,match='只有已取消'):
        bench.restore_cancelled(job['id'])
    job=bench.prepare(p['id'],'product/framework','')
    bench.runner=lambda _:(_ for _ in ()).throw(ValueError('模拟引擎失败'))
    bench.execute(job['id'])  # prepared must not be executed without start
    assert bench.job(job['id'])['status']=='prepared'
    bench.start(job['id'])
    for _ in range(100):
        if bench.job(job['id'])['status']=='failed':
            break
        time.sleep(.01)
    assert bench.job(job['id'])['status']=='failed'
    assert bench.restore_job(job['id'])['status']=='prepared'
    with bench.db() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?",(job['id'],))
    restarted=app.Workbench(bench.data)
    assert restarted.job(job['id'])['status']=='interrupted'
    assert restarted.restore_job(job['id'])['status']=='prepared'


def test_review_blocks_open_comments_and_dangling_citations(bench):
    p=bench.create_project('评审保护','')
    evidence=bench.add_document(p['id'],'资料.txt','这是可追溯的证据。'.encode())
    job=bench.prepare(p['id'],'fast/new-product-analysis','',[evidence['id']])
    with pytest.raises(ValueError,match='未进入本次资料快照'):
        bench.complete(job['id'],'# 新品分析\n\n这个结论引用了不存在的资料，因此不应通过来源完整性检查。[S999]')
    bench.complete(job['id'],'# 新品分析\n\n这个结论有依据，并且引用编号可以在本次资料快照中直接找到。[S1]')
    bench.review(job['id'],'accepted','先确认')
    bench.add_comment(job['id'],{
        'version':1,'block_id':'block-2','block_type':'paragraph',
        'block_label':'这个结论有依据','quote':'这个结论有依据，并且引用编号可以在本次资料快照中直接找到。[S1]',
        'action':'modify','note':'说明依据范围','author':'QA',
    })
    assert bench.job(job['id'])['review'] is None
    with pytest.raises(ValueError,match='待处理批注'):
        bench.review(job['id'],'accepted','确认')


def test_embedded_deliverable_sources_are_flattened_and_renumbered(bench):
    p=bench.create_project('来源闭环','')
    raw=bench.add_document(p['id'],'竞品资料.txt','竞品资料原文。'.encode())
    parent=bench.prepare(p['id'],'fast/new-product-analysis','',[raw['id']])
    bench.complete(parent['id'],'# 新品分析\n\n这条竞品结论直接来自已经进入项目的原始研究资料。[S1]')
    bench.review(parent['id'],'accepted','确认')
    downstream=bench.prepare(p['id'],'fast/core-prd','',[parent['id']])
    assert downstream['sources'][0]['source_id']==parent['id']
    assert any(source['source_id']==raw['id'] for source in downstream['sources'])
    raw_source=next(source for source in downstream['sources'] if source['source_id']==raw['id'])
    assert f"[{raw_source['citation']}]" in downstream['sources'][0]['text']
    assert not bench.citation_issues(downstream['sources'][0]['text'],downstream['sources'])


def test_job_archive_and_mode_snapshot(bench):
    p=bench.create_project('模式快照','',workflow_mode='fast')
    job=bench.prepare(p['id'],'fast/new-product-analysis','')
    bench.update_project(p['id'],'',workflow_mode='full')
    assert bench.job(job['id'])['workflow_mode']=='fast'
    assert bench.state(p['id'])['mode_mismatch_count']==1
    assert bench.archive_job(job['id'],True)['archived']==1
    assert bench.archive_job(job['id'],False)['archived']==0


def test_frontmatter_review_state_is_migrated_without_losing_comment(bench):
    p=bench.create_project('元数据迁移','')
    job=bench.prepare(p['id'],'fast/new-product-analysis','')
    clean='# 新品分析\n\n这段正文需要保留定位批注，并且迁移后仍然属于当前版本。'
    bench.complete(job['id'],clean)
    comment=bench.add_comment(job['id'],{
        'version':1,'block_id':'block-2','block_type':'paragraph',
        'block_label':'这段正文需要保留定位批注','quote':'这段正文需要保留定位批注，并且迁移后仍然属于当前版本。',
        'action':'compress','note':'压缩表达','author':'PM',
    })
    legacy='---\nstatus: draft-for-f2\nreviewed_at: 2026-09-10\ntype: deliverable\n---\n\n'+clean
    with bench.db() as db:
        db.execute('UPDATE jobs SET output=? WHERE id=?',(legacy,job['id']))
        db.execute('UPDATE documents SET text=? WHERE id=?',(legacy,job['id']))
        db.execute('UPDATE job_versions SET output=? WHERE job_id=? AND version=1',(legacy,job['id']))
        db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?,?)',(job['id'],'accepted','旧状态',app.now()))
        db.execute("UPDATE documents SET kind='accepted' WHERE id=?",(job['id'],))
    migrated=app.Workbench(bench.data)
    current=migrated.job(job['id'])
    assert current['current_version']==2
    assert current['open_comment_count']==1
    assert current['comments'][0]['id']==comment['id']
    assert current['comments'][0]['version']==2
    assert current['review'] is None
    assert 'status:' not in current['output']
    assert 'reviewed_at:' not in current['output']
    assert 'type: deliverable' in current['output']


def test_cancel_running_job_and_serial_execution(bench):
    started, release = threading.Event(),threading.Event()
    def delayed(_):
        started.set()
        release.wait(3)
        return '# 测试结果\n\n这条结果在取消后不得保存到交付物中。必须保持取消状态。'
    bench.runner=delayed
    p=bench.create_project('取消测试','')
    first=bench.prepare(p['id'],'product/framework','')
    second=bench.prepare(p['id'],'product/framework','')
    bench.start(first['id'])
    assert started.wait(2)
    worker=bench.threads[first['id']]
    with pytest.raises(ValueError):
        bench.start(second['id'])
    with pytest.raises(ValueError,match='运行中'):
        bench.delete_project(p['id'],'取消测试')
    bench.cancel(first['id'])
    with pytest.raises(ValueError,match='仍在停止中'):
        bench.restore_cancelled(first['id'])
    release.set()
    worker.join(3)
    assert bench.job(first['id'])['status']=='cancelled'
    assert bench.job(first['id'])['output']==''
    assert bench.restore_cancelled(first['id'])['status']=='prepared'


def test_http_real_upload_prepare_review_download(bench):
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    server.app=bench
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def request(path,payload=None,token=True,origin=None):
        headers={'Content-Type':'application/json'}
        if token: headers['X-Workbench-Token']=bench.token
        if origin: headers['Origin']=origin
        req=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
        with urllib.request.urlopen(req) as result:
            return result.read()
    try:
        assert b'app.js' in request('/')
        with pytest.raises(urllib.error.HTTPError) as denied:
            request('/api/projects',{'name':'bad'},token=False)
        assert denied.value.code==403
        with pytest.raises(urllib.error.HTTPError):
            request('/api/projects',{'name':'bad'},origin='https://other.example')
        p=json.loads(request('/api/projects',{'name':'真实接口测试','brief':'准备'}))
        d=json.loads(request('/api/documents',{'project_id':p['id'],'name':'评论.txt','content':base64.b64encode('需求证据'.encode()).decode()}))
        j=json.loads(request('/api/prepare',{'project_id':p['id'],'task':'product/prd','document_ids':[d['id']]}))
        result='# 中文交付物\n\n这是一份完整链路测试的文档，仅用于验证保存与下载，不表示真实产品结论。'
        request('/api/jobs/'+j['id']+'/import',{'output':result})
        assert request('/api/jobs/'+j['id']+'/download').decode()==result
        request('/api/jobs/'+j['id']+'/review',{'decision':'accepted','note':'检查通过'})
        assert json.loads(request('/api/jobs/'+j['id']))['review']['decision']=='accepted'
        edited=result+'\n\n## 手工补充\n这是在工作台中直接编辑后保存的新内容。'
        edited_job=json.loads(request('/api/jobs/'+j['id']+'/edit',{'output':edited,'note':'补充验收说明'}))
        assert edited_job['current_version']==2
        assert edited_job['review'] is None
        versions=json.loads(request('/api/jobs/'+j['id']+'/versions'))
        assert [item['version'] for item in versions]==[2,1]
        assert 'output' not in versions[0]
        assert json.loads(request('/api/jobs/'+j['id']+'/versions/1'))['output']==result
        restored=json.loads(request('/api/jobs/'+j['id']+'/versions/1',{}))
        assert restored['output']==result
        assert restored['current_version']==3
        comment=json.loads(request('/api/jobs/'+j['id']+'/comments',{
            'version':3, 'block_id':'block-2', 'block_type':'paragraph',
            'block_label':'完整链路测试', 'quote':'这是一份完整链路测试的文档',
            'action':'compress', 'note':'压缩成一句话', 'author':'接口测试',
        }))
        assert comment['status']=='open'
        resolved=json.loads(request('/api/jobs/'+j['id']+'/comments/'+comment['id'],{'status':'resolved'}))
        assert resolved['status']=='resolved'
        request('/api/jobs/'+j['id']+'/comments/'+comment['id'],{'status':'open'})
        comment_revision=json.loads(request('/api/jobs/'+j['id']+'/revise-comments',{}))
        assert comment_revision['status']=='prepared'
        assert '压缩成一句话' in comment_revision['prompt']
        cancelled=json.loads(request('/api/prepare',{'project_id':p['id'],'task':'product/prd'}))
        assert json.loads(request('/api/jobs/'+cancelled['id']+'/cancel',{}))['status']=='cancelled'
        assert json.loads(request('/api/jobs/'+cancelled['id']+'/restore-cancelled',{}))['status']=='prepared'
        deleted=json.loads(request('/api/project/delete',{'id':p['id'],'confirmation':'真实接口测试'}))
        assert deleted['deleted'] is True
        projects=json.loads(request('/api/state'))['projects']
        assert p['id'] not in {item['id'] for item in projects}
    finally:
        server.shutdown()
        server.server_close()
