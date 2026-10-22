"""Copy a clean android-walkthrough runtime snapshot, with content hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / 'packages/android-walkthrough/skill'
TREES = {'scripts': {'.py'}, 'references': {'.md'}, 'agents': {'.yaml', '.yml'}}
FIXED = ('SKILL.md', 'README.md', 'requirements.txt')


def sync(source: Path) -> dict:
    source = source.resolve(strict=True)
    if not (source / 'scripts/aw/session.py').is_file() or not (source / 'SKILL.md').is_file():
        raise ValueError('source must be the complete android-walkthrough skill')
    selected = [source / name for name in FIXED if (source / name).is_file()]
    for folder, extensions in TREES.items():
        selected.extend(p for p in (source / folder).rglob('*') if p.is_file()
                        and not p.is_symlink() and p.suffix.lower() in extensions
                        and '__pycache__' not in p.parts and p.resolve().is_relative_to(source))
    destination = DESTINATION.resolve()
    if not destination.is_relative_to(ROOT.resolve() / 'packages'):
        raise ValueError('snapshot destination escaped packages')
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    for item in sorted(selected):
        relative = item.relative_to(source)
        target = destination / relative
        if not target.resolve().is_relative_to(destination):
            raise ValueError('snapshot target escaped destination')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)
        files.append({'path': relative.as_posix(), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    version = re.search(r'VERSION\s*=\s*[\'"]([^\'"]+)',
                        (destination / 'scripts/aw/__init__.py').read_text(encoding='utf-8'))
    manifest = {'skill': 'android-walkthrough', 'version': version[1] if version else '',
                'selection': 'Runtime source and generic protocol only; no run data or account configuration.',
                'files': files}
    (destination / 'SOURCE-MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    result = sync(args.source)
    print(json.dumps({'skill': result['skill'], 'version': result['version'], 'files': len(result['files'])}))
