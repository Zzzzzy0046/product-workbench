"""Build an isolated one-file Windows EXE; include only explicit reusable assets."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'work/exe-build/bin')
    parser.add_argument('--edition', choices=['full', 'collection'], default='full')
    args = parser.parse_args()
    collection = args.edition == 'collection'
    build = ROOT / ('work/collector-exe-build' if collection else 'work/exe-build')
    resources = build / 'resources' / uuid.uuid4().hex
    folders = ['workbench/static', 'workbench/capabilities', 'workbench/workflows',
               'workbench/templates', 'knowledge/templates', 'knowledge/wiki/methods',
               'knowledge/wiki/patterns', 'packages/android-capture/skill',
               'packages/android-walkthrough/skill',
               'packages/competitor-collector/competitor_collector']
    if collection:
        folders = ['workbench/collection_static', 'packages/android-walkthrough/skill',
                   'packages/competitor-collector/competitor_collector']
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
               '--console', '--name', 'DataCollector' if collection else 'ProductWorkbench', '--distpath', str(args.output.resolve()),
               '--workpath', str(build / 'pyinstaller'), '--specpath', str(build),
               '--paths', str(ROOT), '--paths', str(ROOT / 'src'), '--paths', str(ROOT / 'packages/competitor-collector'),
               '--paths', str(ROOT / 'packages/android-walkthrough/skill/scripts'),
               '--collect-all', 'google_play_scraper', '--collect-all', 'reportlab',
               '--collect-submodules', 'competitor_collector', '--collect-submodules', 'aw',
               '--hidden-import', 'deep_translator', '--hidden-import', 'yaml',
               '--hidden-import', 'PIL.Image', '--hidden-import', 'pypdf',
               '--hidden-import', 'docx', '--hidden-import', 'openpyxl',
               '--hidden-import', 'workbench.exporters', '--hidden-import', 'workbench.capture_mcp',
               '--hidden-import', 'workbench.review_scraper_worker', '--hidden-import', 'product_kb.frontmatter']
    for module in ['fastembed', 'qdrant_client', 'torch', 'numpy', 'pytest', 'openai']:
        command += ['--exclude-module', module]
    if collection:
        for module in ['workbench.app', 'workbench.services.job_service',
                       'workbench.services.capability_service', 'workbench.services.workflow_router_service',
                       'workbench.services.retrieval_service']:
            command += ['--exclude-module', module]
    for folder in folders:
        source = ROOT / folder
        target = resources / folder
        for path in source.rglob('*'):
            if not path.is_file() or any(part in {'__pycache__', 'data', '.venv', '.git'} for part in path.relative_to(source).parts):
                continue
            if path.suffix.lower() not in {'.py', '.json', '.md', '.txt', '.html', '.css', '.js', '.ps1', '.yaml', '.yml'}:
                continue
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        command += ['--add-data', f'{target}:{folder}']
    if collection:
        shared = ['style.css', 'features/android_capture.js', 'features/integrations.js',
                  'features/competitor_discovery.js', 'features/competitor_revenue.js']
        for name in shared:
            target = resources / 'workbench/static' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / 'workbench/static' / name, target)
        command += ['--add-data', f'{resources / "workbench/static"}:workbench/static']
    command.append(str(ROOT / 'scripts/packaging' / ('collection_launcher.py' if collection else 'workbench_launcher.py')))
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
