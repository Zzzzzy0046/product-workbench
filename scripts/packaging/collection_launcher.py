"""Independent Windows entry point for the data collection edition."""
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
from http.server import ThreadingHTTPServer


def bootstrap():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])).resolve()
    for folder in (root, root / 'src', root / 'packages/competitor-collector'):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    return root


def dispatch_worker(arguments, root):
    argv = list(arguments)
    if argv[:2] == ['-X', 'utf8']:
        argv = argv[2:]
    if not argv or not argv[0].endswith('.py'):
        return None
    script = Path(argv[0]).resolve()
    allowed = {'review_scraper_worker.py': 'collector', 'capture_mcp.py': 'capture-mcp'}
    valid = script.parent == (root / 'workbench').resolve()
    if getattr(sys, 'frozen', False):
        valid = script.parent.name == 'workbench'
    if not valid or script.name not in allowed:
        raise ValueError('数据采集版只支持内置采集 worker。')
    return allowed[script.name], argv[1:]


def choose_port(preferred=None):
    for port in ([preferred] if preferred is not None else range(8775, 8795)):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise ValueError('本机端口不可用，请通过 --port 另选端口。')


def self_test(root):
    from workbench.collection_app import CollectionWorkbench, EDITION, RELEASE
    files = ['workbench/collection_static/index.html', 'workbench/collection_static/collection.js',
             'workbench/collection_static/collection.css', 'workbench/static/style.css',
             'workbench/static/features/android_capture.js', 'workbench/static/features/integrations.js',
             'workbench/static/features/competitor_discovery.js', 'workbench/static/features/competitor_revenue.js',
             'packages/android-walkthrough/skill/SOURCE-MANIFEST.json',
             'packages/android-walkthrough/skill/scripts/aw/session.py',
             'packages/competitor-collector/competitor_collector/engine.py']
    modules = ['PIL', 'pypdf', 'yaml', 'docx', 'mcp.server.fastmcp', 'google_play_scraper', 'deep_translator']
    result = {'edition': EDITION, 'release': RELEASE, 'frozen': bool(getattr(sys, 'frozen', False)),
              'assets': {file: (root / file).is_file() for file in files},
              'dependencies': {module: importlib.util.find_spec(module) is not None for module in modules}}
    with tempfile.TemporaryDirectory(prefix='collector-self-test-') as directory:
        app = CollectionWorkbench(directory)
        try:
            result['empty_database'] = not app.state()['projects']
            result['document_generation_service'] = hasattr(app, 'job_service')
        finally:
            app.close()
    result['ok'] = all(result['assets'].values()) and all(result['dependencies'].values()) and not result['document_generation_service']
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


def main(arguments=None):
    root = bootstrap()
    argv = list(sys.argv[1:] if arguments is None else arguments)
    worker = dispatch_worker(argv, root)
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
    parser = argparse.ArgumentParser(description='数据采集工作台（本机独立版）')
    parser.add_argument('--version', action='version', version='DataCollector 2026.10.22.1 / android-walkthrough 1.0.1')
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(root)
    if args.port is not None and not 1024 <= args.port <= 65535:
        parser.error('端口须为 1024–65535')
    data = args.data_dir or Path(os.environ.get('COLLECTOR_DATA') or str(
        Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'ProductWorkbenchCollector/data'))
    data = data.expanduser().resolve()
    os.environ['WORKBENCH_DATA'] = str(data)
    os.environ['WORKBENCH_RETRIEVAL_MODE'] = 'keyword'
    port = choose_port(args.port)
    from workbench.collection_app import CollectionWorkbench, CollectionHandler
    app = CollectionWorkbench(data)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), CollectionHandler)
        server.app = app
        print(f'数据采集工作台：http://127.0.0.1:{port}/', flush=True)
        print(f'资料保存：{data}', flush=True)
        print('关闭此窗口或按 Ctrl+C 停止。自动实机走查使用本机 ADB 与已登录的 Codex CLI。', flush=True)
        if not args.no_browser:
            timer = threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{port}/'))
            timer.daemon = True
            timer.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        app.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        if not sys.argv[1:] and sys.stdin and sys.stdin.isatty():
            input('启动失败，请保留以上错误信息。按回车退出。')
        raise SystemExit(1)
