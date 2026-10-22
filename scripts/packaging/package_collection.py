"""Package a verified collection-only EXE, instructions and its actual test reports."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STYLE = 'body{margin:0;background:#f5f3ee;color:#233832;font:16px/1.85 system-ui,"Microsoft YaHei",sans-serif}main{max-width:960px;margin:36px auto;padding:36px 44px;background:#fffefb;border:1px solid #dcded5;border-radius:14px}h1{font-size:30px}h2{font-size:21px;margin-top:30px}a{color:#a34d34}li{padding:4px 0}code,pre{font:14px/1.65 Consolas,"Microsoft YaHei",monospace;background:#eef1e9;padding:3px 6px;border-radius:4px;overflow-wrap:anywhere}pre{padding:18px;overflow:auto;white-space:pre-wrap}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;border:1px solid #dcded5;text-align:left;vertical-align:top}.note{padding:18px;background:#e9eee6;border-radius:9px}small{color:#6a7771}@media(max-width:700px){main{margin:12px;padding:22px}}'


def page(title, content):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>' + STYLE + '</style></head><body><main>' + content + '</main></body></html>'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(exe, output, reports, reference, preview=None):
    exe, output, reference = exe.resolve(strict=True), output.absolute(), reference.resolve(strict=True)
    archive = output.with_suffix('.zip')
    if output.exists() or archive.exists():
        raise ValueError('交付目标已存在，请使用新的名称。')
    if exe.read_bytes()[:2] != b'MZ':
        raise ValueError('不是有效 Windows EXE。')
    if len(reports) < 2:
        raise ValueError('必须提供实际 HTTP 与截图流程的验证报告。')
    checks_count = []
    for report in reports:
        result = json.loads(report.read_text(encoding='utf-8'))
        if not result.get('ok') or not result.get('checks') or not all(item['passed'] for item in result['checks']):
            raise ValueError(f'报告未通过：{report}')
        if result.get('exe_identity', {}).get('sha256') != digest(exe):
            raise ValueError(f'报告不属于这份 EXE：{report}')
        checks_count.append(len(result['checks']))
    output.mkdir(parents=True)
    tech = output / '技术参考'
    tech.mkdir()
    shutil.copy2(exe, output / '数据采集工作台.exe')
    for name in ('THIRD-PARTY-NOTICES.txt', 'PYTHON-LICENSE.txt'):
        shutil.copy2(reference / '技术参考' / name, tech / name)
    shutil.copy2(ROOT / 'packages/android-walkthrough/skill/SOURCE-MANIFEST.json', tech / '截图Skill校验.json')
    for index, report in enumerate(reports, 1):
        shutil.copy2(report, tech / f'验证报告-{index}.json')
    if preview and preview.is_file():
        shutil.copy2(preview, tech / '界面预览.png')

    guide = '''<h1>数据采集工作台 · 独立版</h1>
<p class="note"><strong>先解压 ZIP，再双击「数据采集工作台.exe」。</strong><br>程序自动打开本机浏览器，不需要安装 Python、登录站点或填写配对码。</p>
<h2>包含的能力</h2><ul><li><strong>找竞品：</strong>按关键词、平台和市场搜索，由你手选应用。</li><li><strong>商店资料采集：</strong>批量收集应用长短描述、商店信息、宣传截图和原始评论；支持多国家、日期、评分、关键词等筛选，以及可选中文翻译。</li><li><strong>Android 实机截图：</strong>内置 android-walkthrough 1.0.1，给出包名和范围，自动记录页面、分支、截图及模块流程 PNG；支持暂停续跑。</li><li><strong>预览、保存和导出：</strong>确认后加入本机采集资料库，可下载单份原文件、实机证据 ZIP 或完整采集数据包。</li><li><strong>收入资料补充：</strong>找竞品页面提供来源入口与人工记录，当前未接入收入自动采集 API。</li></ul>
<h2>第一次使用</h2><ol><li>双击「数据采集工作台.exe」，保留启动窗口。</li><li>新建采集项目，按需要选择找竞品、粘贴链接采集或实机截图。</li><li>商店资料填国家、评论范围，点击开始；完成后先预览，再确认保存。</li><li>实机截图填写已安装 App 的包名和走查范围，选择在线设备后开始。</li><li>在已保存资料中下载原文件，或点击「导出采集数据包」交接。</li></ol>
<h2>连接手机</h2><p>支持 Android 手机和模拟器。先开启开发者选项与 USB 调试，使用数据线连接电脑，并在手机上点击允许；建议勾选始终允许这台电脑。</p><p>程序会自动查找 PATH、Android SDK 和桌面常见 scrcpy 工具目录中的 ADB；如果这台电脑的完整版配置过 ADB，会读取并复用有效路径。换 Android 手机无需更改 ADB 路径；多台设备同时连接时需明确选择。</p><p>未找到 ADB 时，在截图窗口展开「ADB 路径配置」，填写 adb.exe 完整路径。这个包没有附带 ADB、Codex CLI 或账号凭据。自动走查需要本机安装并登录 Codex CLI；首次 USB 授权仍需你在手机上完成。iPhone 不适用这套 ADB 走查。</p>
<h2>运行与数据保存</h2><p>默认从 <code>http://127.0.0.1:8775/</code> 选择空闲端口，仅监听本机。如果没有自动打开浏览器，复制启动窗口显示的地址。关闭启动窗口或按 Ctrl+C 停止；只关闭浏览器不会停止。</p><p>数据独立保存在 <code>%LOCALAPPDATA%\\ProductWorkbenchCollector\\data</code>，重启后仍保留。既有项目资料不会自动迁入。原来的完整版可继续使用。</p><p>商店采集需要网络，无需模型账号。中文翻译通过 Google 翻译，原评论始终保留；自动实机走查使用本机 Codex 账户。App Store 的实际可用性取决于公开接口，本次未新增成功验证。此包未在另一台电脑或全新 Windows 虚拟机验证。</p>
<h2>技术交接</h2><p><a href="技术参考/API接口说明.html">采集 API 与调用示例</a> · <a href="技术参考/验证说明.html">本次验证记录</a></p><p>Windows x64 免安装版。DataCollector 2026.10.22.1 / android-walkthrough 1.0.1。专用版不提供产品分析、PRD、原型交接、埋点或验收文档生成。</p>'''
    (output / '使用说明.html').write_text(page('数据采集工作台使用说明', guide), encoding='utf-8')

    routes = [
        ('GET', '/api/state?project=ID', '读取采集项目、资料和采集任务；无文档生成流程。'),
        ('POST', '/api/projects', '新建采集项目：name、brief。'),
        ('POST', '/api/competitors/search', '商店搜索：project_id、query、platform、country、lang、limit。'),
        ('POST', '/api/competitors/detail', '应用详情：project_id、platform、app_id、country。'),
        ('POST', '/api/competitors/collect', '批量采集：project_id、entries、countries、count_per_country、sort、translate。'),
        ('GET', '/api/reviews/scrape/ID', '读取单个采集任务、状态、评论样例和商店资料。'),
        ('POST', '/api/reviews/scrape/ID/confirm', '将待确认结果保存到资料库。'),
        ('POST', '/api/reviews/scrape/ID/cancel 或 retry', '停止或重试采集。'),
        ('GET', '/api/documents/ID 或 /download', '读取资料预览或下载原文件。'),
        ('POST', '/api/documents/ID/translate', '补充中文翻译；每次最多处理 500 条待翻译评论。'),
        ('GET', '/api/assets/PROJECT_ID/DOCUMENT_ID', '读取保存的图片。'),
        ('GET', '/api/projects/ID/export', '导出兼容完整版的 workbench-project-v1 ZIP，数据结构版本 2。'),
        ('GET/POST', '/api/competitors/revenue', '读取／保存人工收入资料，不调用收费来源 API。'),
        ('GET/POST', '/api/android-capture/settings', '检查连接条件／保存 adb_path；读取时自动查找有效 ADB。'),
        ('GET', '/api/android-capture/devices', '列出设备型号、serial 与在线授权状态。'),
        ('GET', '/api/android-capture/sessions?project_id=ID', '列出本项目实机走查。'),
        ('POST', '/api/android-capture/sessions', '准备走查：project_id、package、serial、scope、title。'),
        ('GET', '/api/android-capture/sessions/ID', '读取进度、覆盖缺口、原始截图与模块 PNG。'),
        ('POST', '/api/android-capture/sessions/ID/start 或 resume', '开始或继续自动走查；实际操作所选设备并调用本机 Codex。'),
        ('POST', '/api/android-capture/sessions/ID/cancel 或 confirm', '停止走查或确认保存已采集证据。'),
        ('GET', '/api/android-capture/sessions/ID/file?path=相对路径', '读取本会话允许导出的原始证据。'),
        ('GET', '/api/android-capture/sessions/ID/export', '下载当前会话证据 ZIP。'),
    ]
    api = '<h1>数据采集专用版 · HTTP API</h1><p>以启动窗口的实际本机地址为准。所有 POST 都要求 JSON，并附带由 <code>GET /api/state</code> 返回的 <code>X-Workbench-Token</code>；此临时令牌随进程重启变化，不是模型 API Key。若发送 Origin，必须是本机服务地址。</p><p>成功通常为 200，创建为 201，异步任务为 202；错误返回 <code>{"error":"说明"}</code>。采集状态为 queued、running、ready、completed、empty、failed、cancelled。ready 需确认后进入资料库；截图的 ready 需 confirm 后变为 confirmed。</p><table><thead><tr><th>方法</th><th>路径</th><th>说明</th></tr></thead><tbody>'
    api += ''.join('<tr><td>'+html.escape(method)+'</td><td><code>'+html.escape(path)+'</code></td><td>'+html.escape(description)+'</td></tr>' for method, path, description in routes)
    api += '</tbody></table><h2>Python 调用</h2><p>同目录附 <code>api调用示例.py</code>，仅使用 Python 标准库。运行示例会创建测试项目，并在你显式提供 <code>--app-id</code> 后启动公开商店采集，不自动操作手机。</p><h2>采集输出与下游衔接</h2><p>输入指定 App、国家、评论范围或设备走查范围 → 原始结果暂存 → 人工预览确认 → 商店信息 Markdown、评论 CSV、图片与实机索引 → 单文件或 ZIP 导出。评论原文与译文分字段保存。完整 ZIP 可在完整版工作台导入后用于后续产品分析。</p><p>本版不开放 /api/prepare、/api/jobs/*、/api/assemble、/api/packs、/api/search 等产品文档及知识库流程；也不提供站点配对或远程执行端。</p><h2>启动参数</h2><pre>数据采集工作台.exe --port 8775 --no-browser\n数据采集工作台.exe --data-dir D:\\CollectorData\n数据采集工作台.exe --self-test\n数据采集工作台.exe --version</pre><p>桌面包不含个人数据、账号、Cookie 或密钥。调用日志和请求头中的临时令牌请按本地运行信息处理。</p>'
    (tech / 'API接口说明.html').write_text(page('数据采集 API 接口说明', api), encoding='utf-8')
    example = '''"""Python standard-library client. Requires a running local collection EXE."""
import argparse
import json
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8775')
parser.add_argument('--app-id', help='Optional Google Play package; starts collection only when supplied.')
args = parser.parse_args()
base = args.url.rstrip('/')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
token = ''

def request(path, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json', 'X-Workbench-Token': token}
    with opener.open(urllib.request.Request(base + path, data=body, headers=headers), timeout=90) as response:
        return json.load(response)

token = request('/api/state')['token']
project = request('/api/projects', {'name': 'API example collection', 'brief': 'Created by the supplied example.'})
print(json.dumps({'project_id': project['id']}, ensure_ascii=False))
if args.app_id:
    result = request('/api/competitors/collect', {'project_id': project['id'], 'entries': [args.app_id],
                     'countries': ['us'], 'count_per_country': 20, 'sort': 'newest', 'translate': False})
    print(json.dumps({'count': result['count'], 'scrape_ids': [item['id'] for item in result['items']]}, ensure_ascii=False))
'''
    (tech / 'api调用示例.py').write_text(example, encoding='utf-8')
    first = json.loads(reports[0].read_text(encoding='utf-8'))
    live = first.get('live_store', {})
    validation = '<h1>本次 EXE 验证</h1><ul>'
    validation += ''.join(f'<li>{html.escape(label)}：{count} 项通过。</li>' for label, count in zip(('独立启动、接口收敛、采集保存与导出', '模拟设备截图完整链路'), checks_count))
    validation += '</ul><p>Google Play 小样本：'+html.escape(str(live.get('app_id', '未执行'))) + f'，采集 {int(live.get("reviews", 0))} 条评论、{int(live.get("screenshots", 0))} 张商店截图，并确认保存、导出校验。</p><p>采集专用版与打包定向测试 22 项通过，原采集/截图相关回归 119 项通过。截图链路使用本地模拟设备，实际运行冻结 worker 完成观察、操作、地图、模块 PNG、finish 和确认保存；仅模型最终状态交接模拟，未调用真实模型和手机。</p><p>浏览器检查覆盖采集首页、找竞品、商店采集表单与截图入口。实际测试进程和端口均已清理。未在同事电脑或全新 Windows 虚拟机验证；未新增 App Store 或真实目标 App 全范围验证。</p><p>本包没有包含验证时的 Google Play 评论或任何用户既有资料；原始报告同目录保存。</p><p>EXE SHA-256：<code>' + digest(exe) + '</code></p>'
    (tech / '验证说明.html').write_text(page('数据采集版验证说明', validation), encoding='utf-8')
    files = [{'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)}
             for path in sorted(output.rglob('*')) if path.is_file()]
    manifest = {'edition': 'data-collection', 'release': '2026.10.22.1', 'screenshot_skill': 'android-walkthrough 1.0.1',
                'created_at': datetime.now().astimezone().isoformat(), 'files': files}
    (tech / '文件校验.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                bundle.write(path, output.name + '/' + path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or hashlib.sha256(bundle.read(output.name + '/数据采集工作台.exe')).hexdigest() != digest(exe):
            raise ValueError('交付 ZIP 校验失败。')
    return {'folder': str(output), 'zip': str(archive), 'zip_bytes': archive.stat().st_size,
            'exe_bytes': exe.stat().st_size, 'exe_sha256': digest(exe), 'file_count': len(files) + 1}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', action='append', type=Path, required=True)
    parser.add_argument('--reference-package', type=Path, required=True)
    parser.add_argument('--preview', type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.exe, args.output, args.report, args.reference_package, args.preview), ensure_ascii=False, indent=2))
