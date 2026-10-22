"""Fresh package docs, exact EXE/report identity, and immutable output targets."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.packaging import package_portable as portable


@pytest.fixture
def package_inputs(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    for relative, content in {
        'packages/android-walkthrough/skill/SOURCE-MANIFEST.json': '{"version":"1.0.1"}',
        'scripts/packaging/api_client_example.py': '# current example',
        'docs/WORKBENCH-HTTP-API.md': '# Current API\n\n/api/competitors/inputs\nschema 3',
        'docs/WORKBENCH-COMPETITOR-DOSSIERS.md': '# 当前档案说明',
        'docs/WORKBENCH-CODEX-CONNECTION.md': '# Codex 连接与首次使用',
    }.items():
        file = source / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding='utf-8')
    (source / '.env').write_text('DO_NOT_SHIP=private-fixture', encoding='utf-8')
    reference = tmp_path / 'old reference'
    tech = reference / '技术参考'
    tech.mkdir(parents=True)
    for name in ('THIRD-PARTY-NOTICES.txt', 'PYTHON-LICENSE.txt'):
        (tech / name).write_text('license fixture', encoding='utf-8')
    (tech / 'API接口说明.html').write_text('stale reference API', encoding='utf-8')
    exe = tmp_path / 'ProductWorkbench.exe'
    exe.write_bytes(b'MZ-fake-exe-only-for-package-tests')
    report = tmp_path / 'verified.json'
    report.write_text(json.dumps({'ok': True, 'checks': {'synthetic': True},
                                 'exe_identity': {'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}}), encoding='utf-8')
    monkeypatch.setattr(portable, 'ROOT', source)
    return exe, reference, report


def test_portable_package_refreshes_docs_and_checks_all_archive_files(tmp_path, package_inputs):
    exe, reference, report = package_inputs
    output = tmp_path / 'workbench.v3'
    result = portable.package(exe, output, reference, [report])
    archive = Path(result['zip'])
    assert archive.name == 'workbench.v3.zip'
    assert result['release'] == portable.RELEASE_VERSION
    api = (output / '技术参考/API接口说明.html').read_text(encoding='utf-8')
    assert '/api/competitors/inputs' in api and 'stale reference API' not in api
    assert (output / '竞品档案与勾选说明.md').is_file()
    guide = (output / '使用说明.html').read_text(encoding='utf-8')
    assert '项目公共资料' in guide and portable.RELEASE_VERSION in guide
    manifest = json.loads((output / '技术参考/文件校验.json').read_text(encoding='utf-8'))
    assert manifest['exe_identity']['sha256'] == result['exe_sha256']
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for record in manifest['files']:
            data = bundle.read(output.name + '/' + record['path'])
            assert len(data) == record['bytes']
            assert hashlib.sha256(data).hexdigest() == record['sha256']
        assert not any('.env' in name for name in bundle.namelist())
    with pytest.raises(ValueError, match='输出已存在'):
        portable.package(exe, output, reference, [report])


@pytest.mark.parametrize('mutation', ['missing_identity', 'wrong_identity', 'empty_checks', 'failed_check', 'missing_ok'])
def test_portable_package_rejects_unbound_or_failed_reports(tmp_path, package_inputs, mutation):
    exe, reference, report = package_inputs
    result = json.loads(report.read_text(encoding='utf-8'))
    if mutation == 'missing_identity':
        result.pop('exe_identity')
    elif mutation == 'wrong_identity':
        result['exe_identity']['sha256'] = '0' * 64
    elif mutation == 'empty_checks':
        result['checks'] = {}
    elif mutation == 'failed_check':
        result['checks']['synthetic'] = False
    else:
        result.pop('ok')
    report.write_text(json.dumps(result), encoding='utf-8')
    output = tmp_path / 'not-created'
    with pytest.raises(ValueError):
        portable.package(exe, output, reference, [report])
    assert not output.exists()
