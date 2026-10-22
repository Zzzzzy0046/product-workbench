"""Assemble the small end-user EXE package without local projects or credentials."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

try:
    from .workbench_launcher import RELEASE_VERSION
except ImportError:
    from workbench_launcher import RELEASE_VERSION

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(exe: Path, output: Path, reference_package: Path, reports: list[Path]) -> dict:
    exe, output, reference_package = exe.resolve(strict=True), output.absolute(), reference_package.resolve(strict=True)
    archive = output.with_name(output.name + '.zip')
    if output.exists() or archive.exists():
        raise ValueError('输出已存在；请换一个新名称，不能覆盖旧包。')
    if exe.read_bytes()[:2] != b'MZ':
        raise ValueError('EXE 文件无效。')
    manifest = json.loads((ROOT / 'packages/android-walkthrough/skill/SOURCE-MANIFEST.json').read_text(encoding='utf-8'))
    if manifest.get('version') != '1.0.1':
        raise ValueError('本次交付应使用修复后的 android-walkthrough 1.0.1。')
    if not reports or any(not p.is_file() for p in reports):
        raise ValueError('必须先完成验证并提供实际报告。')
    summaries = []
    for report in reports:
        result = json.loads(report.read_text(encoding='utf-8'))
        checks = result.get('checks', [])
        passed = bool(checks) and (all(checks.values()) if isinstance(checks, dict) else all(c.get('passed') for c in checks))
        if result.get('ok') is not True or not passed:
            raise ValueError(f'验证报告未通过：{report.name}')
        identity = result.get('exe_identity', {})
        if identity.get('sha256') != digest(exe):
            raise ValueError(f'报告不是本次 EXE：{report.name}')
        summaries.append((report.name, len(checks)))
    output.mkdir(parents=True)
    tech = output / '技术参考'
    tech.mkdir()
    shutil.copy2(exe, output / 'ProductWorkbench.exe')
    for name in ('THIRD-PARTY-NOTICES.txt', 'PYTHON-LICENSE.txt'):
        shutil.copyfile(reference_package / '技术参考' / name, tech / name)
    shutil.copyfile(ROOT / 'scripts/packaging/api_client_example.py', tech / 'api_client_example.py')
    shutil.copyfile(ROOT / 'docs/WORKBENCH-HTTP-API.md', tech / 'API接口说明.md')
    shutil.copyfile(ROOT / 'docs/WORKBENCH-COMPETITOR-DOSSIERS.md', output / '竞品档案与勾选说明.md')
    for source_name, target_name in (('WORKBENCH-DOSSIER-VERIFICATION.md', '资料页验证说明.md'), ('WORKBENCH-REPACKAGE-20261022.md', '本次对比与打包说明.md')):
        source = ROOT / 'docs' / source_name
        if source.is_file():
            shutil.copyfile(source, tech / target_name)
    shutil.copyfile(ROOT / 'packages/android-walkthrough/skill/SOURCE-MANIFEST.json', tech / '截图Skill源码校验.json')
    for index, report in enumerate(reports, 1):
        shutil.copyfile(report, tech / f'验证-{index}-{report.name}')
    verification = ROOT / 'docs/WORKBENCH-EXE-VERIFICATION.md'
    if verification.is_file():
        (tech / '验证说明.md').write_text(verification.read_text(encoding='utf-8'), encoding='utf-8-sig')
    style = '''body{margin:0;background:#f5f4ef;color:#203d34;font:16px/1.9 system-ui,"Microsoft YaHei",sans-serif}main{max-width:930px;margin:40px auto;padding:38px 44px;background:white;border:1px solid #dce1d9;border-radius:14px}h1{font-size:28px}h2{font-size:21px;margin-top:32px}a{color:#a34c34}li{padding:4px 0}code{font:14px Consolas,monospace;background:#edf1e9;padding:3px 6px;border-radius:4px;overflow-wrap:anywhere}.note{padding:18px 22px;background:#edf1e9;border-radius:8px}small{color:#63756c}@media(max-width:700px){main{margin:15px;padding:22px}}'''
    validation = '<h1>本次 EXE · 验证记录</h1><p>ProductWorkbench ' + RELEASE_VERSION + ' / android-walkthrough 1.0.1</p><p><code>SHA256: ' + digest(exe) + '</code></p><ul>'
    for index, (name, count) in enumerate(summaries, 1):
        label = ('独立启动、资料和文档导出', '新版截图工具握手', '模拟设备截图到确认入库')[index-1] if index <= 3 else name
        validation += '<li>'+html.escape(label)+f'：{count} 项通过。</li>'
    validation += '</ul><p>报告均绑定上面的最终 EXE，不沿用旧文件的检查结果。验证为本机隔离环境、合成资料与 FakeAdb；具体覆盖和进程清理以各 JSON 报告为准。未调用真实模型、手机或外网商店。</p><p>不等于真实目标 App 全范围走查，也未在同事电脑或全新 Windows 虚拟机验证。</p><p>原始检查报告与文件校验 JSON 同放在本目录。</p>'
    (tech / '验证说明.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EXE 验证记录</title><style>'+style+'</style></head><body><main>'+validation+'</main></body></html>', encoding='utf-8')
    api_text = (ROOT / 'docs/WORKBENCH-HTTP-API.md').read_text(encoding='utf-8-sig')
    (tech / 'API接口说明.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>工作台 API 接口说明</title><style>' + style + 'pre{white-space:pre-wrap;word-break:break-word;font:14px/1.8 Consolas,"Microsoft YaHei",monospace}</style></head><body><main><h1>工作台 API 接口说明</h1><p>与本次源码同步，包含竞品档案、明确勾选的资料输入和 schema 3 项目包。</p><pre>' + html.escape(api_text) + '</pre></main></body></html>', encoding='utf-8')
    body = '''<h1>产品工作台 · Windows 版</h1>
<p class="note"><strong>先解压 ZIP，再双击 <code>ProductWorkbench.exe</code>。</strong><br>程序自动打开本机浏览器；不需要站点账号、配对码或单独安装 Python。</p>
<h2>这次更新</h2><ul><li>统一“项目资料”页面：各竞品档案和项目公共资料同页展示，不再切换两个分类标签。</li><li>每个竞品分别整理商店长短描述、评论、商店截图、实机截图、模块流程和附件；一份原件可关联多个档案，不重复复制。</li><li>采集范围与分析输入分别勾选。公共资料可以单独进入分析，不要求先选竞品。最多 12 份明确输入，不自动混入未勾选的竞品资料。</li><li>保留连续 Ctrl+V 粘贴、批量上传、分类、归入竞品档案、编辑交付物及 Word/PDF/Excel/CSV 导出。</li><li>新品分析按章节生成与确认，保留 PRD、埋点、验收和完整项目导入导出。</li><li>内置 android-walkthrough 1.0.1，保留实机走查、模块流程 PNG、暂停续跑和确认入库。</li></ul>
<h2>开始使用</h2><ol><li>双击 <code>ProductWorkbench.exe</code>，等待启动，保留控制台窗口。</li><li>浏览器打开后，新建或选择项目，在“资料”中上传资料、采集评论或进入实机截图。</li><li>截图时选定设备，填 App 包名和本轮范围。结果先预览，确认后加入项目资料。</li></ol>
<p>浏览器没自动打开时，在控制台找到实际地址。默认从 <code>http://127.0.0.1:8765/</code> 选择空闲端口。关闭控制台或按 <code>Ctrl+C</code> 停止；仅关闭浏览器不会停止。</p>
<h2>运行条件</h2><ul><li>完整工作台、Python、原生评论采集器、截图 Skill 和导出依赖均已内置，不依赖作者 D 盘或个人 Skill 目录。</li><li>文档生成和自动截图仍使用本机已安装、登录的 Codex CLI；手机截图还需要 ADB 和已授权 USB 调试的 Android 手机或模拟器。</li><li>本包不附模型账号、登录凭据或既有项目资料。评论采集和模型调用需要网络。</li></ul>
<h2>项目保存</h2><p>默认新数据保存在 <code>%LOCALAPPDATA%\\ProductWorkbenchResearch\\data</code>；如果此前本地 EXE 版已在此保存项目，会继续读取。显式指定的数据目录优先。源码版原项目库不自动迁入。</p>
<h2>说明与验证</h2><p><a href="竞品档案与勾选说明.md">竞品档案与勾选说明</a> · <a href="技术参考/API接口说明.html">HTTP API 接口说明</a> · <a href="技术参考/验证说明.html">验证记录与边界</a></p><p>这是完整工作台程序包，不是项目数据备份。包内不包含你的账号、项目、评论或截图。验证使用模拟设备和合成资料；真实目标 App 的页面覆盖和稳定性需要配置手机后验证。</p>'''
    body += '<small>Windows x64 免安装版 · ProductWorkbench ' + RELEASE_VERSION + ' · android-walkthrough 1.0.1</small>'
    (output / '使用说明.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>产品工作台 · 新版截图</title><style>'+style+'</style></head><body><main>'+body+'</main></body></html>', encoding='utf-8')
    files = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(output.rglob('*')) if p.is_file()]
    result = {'release': RELEASE_VERSION, 'screenshot_skill': 'android-walkthrough 1.0.1',
              'exe_identity': {'sha256': digest(exe), 'bytes': exe.stat().st_size},
              'manifest_scope': 'All package files except 技术参考/文件校验.json itself.',
              'created_at': datetime.now().astimezone().isoformat(), 'files': files}
    (tech / '文件校验.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                bundle.write(p, Path(output.name) / p.relative_to(output))
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or hashlib.sha256(bundle.read(output.name+'/ProductWorkbench.exe')).hexdigest() != digest(exe):
            raise ValueError('ZIP 校验失败。')
    return {'folder': str(output), 'zip': str(archive), 'release': RELEASE_VERSION, 'zip_bytes': archive.stat().st_size, 'exe_sha256': digest(exe), 'file_count': len(files)+1}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-package', type=Path, required=True)
    parser.add_argument('--report', action='append', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.exe, args.output, args.reference_package, args.report), ensure_ascii=False))
