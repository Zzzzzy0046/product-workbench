"""New screenshot workspaces travel with evidence, without machine execution settings."""
import hashlib
import io
import json
import zipfile

from workbench.app import Workbench


def test_new_walkthrough_workspace_is_portable_on_export_and_untrusted_import(tmp_path):
    bench = Workbench(tmp_path / 'data', runner=lambda _: 'unused')
    try:
        project = bench.create_project('新版截图项目', 'Synthetic portability test')
        sid = 'b' * 32
        folder = bench.data / 'scrapes' / project['id'] / ('android-' + sid)
        folder.mkdir(parents=True)
        record = {'id': sid, 'project_id': project['id'], 'version_id': '', 'document_ids': [],
                  'package': 'test.portable.app', 'serial': 'SYNTHETIC', 'status': 'paused',
                  'title': '合成截图', 'scope': '首页', 'app_version': {'name': '1', 'code': '1'}}
        (folder / 'session.json').write_text(json.dumps(record), encoding='utf-8')
        workspace = {'v': 1, 'package': record['package'], 'serial': record['serial'], 'app_version': '1',
                     'adb': 'C:/LOCAL_ONLY/adb.exe', 'cache': {'launcher': 'private.launcher'},
                     'anim_original': {'animator_duration_scale': '0.5'}, 'token': 'LOCAL_ONLY_TOKEN'}
        original = json.dumps(workspace).encode()
        (folder / 'aw.json').write_bytes(original)
        payload, _ = bench.export_project(project['id'])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            member = next(name for name in names if name.endswith('/aw.json'))
            portable = json.loads(archive.read(member))
            assert portable == {key: workspace[key] for key in ('v', 'package', 'serial', 'app_version')}
            files = {name: archive.read(name) for name in names}
        assert (folder / 'aw.json').read_bytes() == original

        # An externally produced, otherwise valid package may still contain
        # the old machine's adb/cache/animation settings. Import must strip them.
        files[member] = original
        manifest_name = next(name for name in files if name == 'manifest.json')
        manifest = json.loads(files[manifest_name])
        for item in manifest['files']:
            if item['path'] == member:
                item.update(size=len(original), sha256=hashlib.sha256(original).hexdigest())
        files[manifest_name] = json.dumps(manifest).encode()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        imported = bench.import_project(stream.getvalue())
        copied_root = bench.data / 'scrapes' / imported['id']
        copied = next(copied_root.glob('android-*/aw.json'))
        assert json.loads(copied.read_text(encoding='utf-8')) == portable
        imported_session = json.loads((copied.parent / 'session.json').read_text(encoding='utf-8'))
        assert imported_session['id'] != sid and imported_session['status'] == 'interrupted'
    finally:
        bench.close()
