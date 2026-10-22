"""Portable UI entry point and fixed Python-worker dispatch for frozen builds."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import traceback
import webbrowser

RELEASE_VERSION = '2026.10.22.3'


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])).resolve()


def bootstrap():
    root = resource_root()
    for path in (root, root / 'src', root / 'packages/competitor-collector'):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    return root


def worker_target(arguments, root):
    """Support only the two repository-owned worker scripts, never arbitrary Python."""
    args = list(arguments)
    if args[:2] == ['-X', 'utf8']:
        args = args[2:]
    if not args or not args[0].endswith('.py'):
        return None
    candidate = Path(args[0]).resolve()
    allowed = {
        (root / 'workbench/review_scraper_worker.py').resolve(): 'collector',
        (root / 'workbench/capture_mcp.py').resolve(): 'capture-mcp',
    }
    # A one-file MCP child may unpack to a different temporary directory.
    # The supplied path only selects one fixed module; its contents are never run.
    if getattr(sys, 'frozen', False) and candidate.parent.name == 'workbench':
        for fixed, kind in allowed.items():
            if candidate.name == fixed.name:
                return kind, args[1:]
    if candidate not in allowed:
        raise ValueError('此 EXE 仅支持工作台固定 worker，不是通用 Python 解释器。')
    return allowed[candidate], args[1:]


def available_port(preferred, automatic):
    candidates = range(preferred, min(preferred + 20, 65536)) if automatic else [preferred]
    for port in candidates:
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise ValueError('本机端口不可用，请通过 --port 另选端口；未停止任何已有服务。')


def self_test(root):
    modules = ['PIL', 'pypdf', 'yaml', 'docx', 'openpyxl', 'reportlab',
               'mcp.server.fastmcp', 'google_play_scraper', 'deep_translator', 'requests']
    files = ['workbench/static/index.html', 'workbench/capabilities/fast.json',
             'workbench/workflows/presets.json', 'knowledge/templates/f2-core-prd.md',
             'packages/competitor-collector/competitor_collector/engine.py',
             'packages/competitor-collector/competitor_collector/scrapers.py',
             'packages/android-capture/skill/SKILL.md',
             'packages/android-capture/skill/scripts/capture_session.py',
             'packages/android-walkthrough/skill/SKILL.md',
             'packages/android-walkthrough/skill/scripts/aw/session.py',
             'packages/android-walkthrough/skill/SOURCE-MANIFEST.json']
    results = {
        'release': RELEASE_VERSION,
        'frozen': bool(getattr(sys, 'frozen', False)),
        'dependencies': {name: importlib.util.find_spec(name) is not None for name in modules},
        'assets': {name: (root / name).is_file() for name in files},
        'retrieval_default': 'keyword',
    }
    manifest = root / 'packages/android-walkthrough/skill/SOURCE-MANIFEST.json'
    if manifest.is_file():
        results['screenshot_skill'] = json.loads(manifest.read_text(encoding='utf-8')).get('version')
    from workbench.app import Workbench
    with tempfile.TemporaryDirectory(prefix='workbench-self-test-') as directory:
        app = Workbench(data_dir=directory, runner=lambda _job: 'self-test: never called')
        try:
            results['knowledge_count'] = len(app.knowledge())
        finally:
            app.close()
    results['ok'] = all(results['dependencies'].values()) and all(results['assets'].values())
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results['ok'] else 1


def main(arguments=None):
    root = bootstrap()
    argv = list(sys.argv[1:] if arguments is None else arguments)
    worker = worker_target(argv, root)
    if worker:
        kind, remaining = worker
        sys.argv = [kind, *remaining]
        if kind == 'collector':
            from workbench.review_scraper_worker import main as collect, _configure_stdio
            _configure_stdio()
            return collect()
        from workbench.capture_mcp import main as capture
        capture()
        return 0
    parser = argparse.ArgumentParser(description='产品工作台 Windows 技术研究版（仅监听本机）')
    manifest = root / 'packages/android-walkthrough/skill/SOURCE-MANIFEST.json'
    skill_version = json.loads(manifest.read_text(encoding='utf-8')).get('version', 'unknown') if manifest.is_file() else 'legacy'
    parser.add_argument('--version', action='version', version=f'ProductWorkbench {RELEASE_VERSION} / android-walkthrough {skill_version}')
    parser.add_argument('--port', type=int, default=None, help='固定端口；默认从 8765 起自动选择空闲端口')
    parser.add_argument('--data-dir', type=Path, help='独立数据目录；默认位于本机 LocalAppData')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    parser.add_argument('--self-test', action='store_true', help='离线检查依赖与内置资源，不启动服务')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(root)
    if args.port is not None and not 1024 <= args.port <= 65535:
        parser.error('端口须为 1024–65535')
    data = args.data_dir or Path(os.environ.get('WORKBENCH_DATA') or
        str(Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) /
            'ProductWorkbenchResearch/data'))
    data = data.expanduser().resolve()
    os.environ['WORKBENCH_DATA'] = str(data)
    os.environ.setdefault('WORKBENCH_RETRIEVAL_MODE', 'keyword')
    data.mkdir(parents=True, exist_ok=True)
    port = available_port(args.port or 8765, automatic=args.port is None)
    from workbench.app import main as serve
    print('产品工作台 · 技术研究版', flush=True)
    print(f'数据目录：{data}', flush=True)
    print('关闭此窗口或按 Ctrl+C 停止本次服务。Codex/ADB 由本机单独配置。', flush=True)
    if not args.no_browser:
        timer = threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{port}/'))
        timer.daemon = True
        timer.start()
    sys.argv = ['ProductWorkbench', '--port', str(port)]
    serve()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        if not sys.argv[1:] and sys.stdin and sys.stdin.isatty():
            input('启动失败，请保留以上错误信息。按回车退出。')
        raise SystemExit(1)
