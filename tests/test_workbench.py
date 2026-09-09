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
    with pytest.raises(ValueError):
        bench.prepare(p['id'],'reviews/review-analysis','')
    with bench.db() as db:
        db.execute('INSERT INTO preferences VALUES(?,?)',('pack:reviews','true'))
    job=bench.prepare(p['id'],'reviews/review-analysis','分析差评')
    assert '样本与来源' in job['prompt']
    t1=bench.prepare(p['id'],'product/new-product','')
    assert '## 0. 文档信息与一页结论' in t1['prompt']
    assert '## 12.' in t1['prompt']


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
    assert '上一版草稿数据' in revision['prompt']
    assert revision['sources'] == job['sources']
    assert not any(s['source_id']==job['id'] for s in bench.search(p['id'],'自动化测试'))


def test_cancel_failure_and_restart(bench):
    p=bench.create_project('验证','')
    job=bench.prepare(p['id'],'product/framework','')
    bench.cancel(job['id'])
    with pytest.raises(ValueError):
        bench.start(job['id'])
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
    with bench.db() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?",(job['id'],))
    restarted=app.Workbench(bench.data)
    assert restarted.job(job['id'])['status']=='interrupted'


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
    bench.cancel(first['id'])
    release.set()
    worker.join(3)
    assert bench.job(first['id'])['status']=='cancelled'
    assert bench.job(first['id'])['output']==''


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
    finally:
        server.shutdown()
        server.server_close()
