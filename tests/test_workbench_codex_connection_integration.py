"""The connection setting also controls actual workbench runners and guards."""
from types import SimpleNamespace

import pytest

from workbench.app import Workbench


@pytest.mark.parametrize('kind', ['login', 'test'])
def test_connection_operation_blocks_new_document_and_capture_work(tmp_path, monkeypatch, kind):
    app = Workbench(tmp_path, runner=lambda _: 'unused')
    try:
        project = app.create_project('合成连接互斥', '')
        job = app.prepare(project['id'], 'fast/product-baseline', '不执行模型')
        monkeypatch.setattr(app.codex_connection, 'snapshot', lambda: {'operation': {'kind': kind, 'status': 'running'}})
        with pytest.raises(ValueError, match='登录或测试连接'):
            app.start(job['id'])
        assert app.job(job['id'])['status'] == 'prepared'
        with pytest.raises(ValueError, match='登录或测试连接'):
            app.android_capture.start('no-device-or-session-needed')
    finally:
        app.close()


def test_document_preflight_uses_connection_command_not_global_discovery(tmp_path, monkeypatch):
    app = Workbench(tmp_path, runner=lambda _: 'unused')
    try:
        project = app.create_project('合成命令预检', '')
        job = app.prepare(project['id'], 'fast/product-baseline', '不执行模型')
        app.runner = app.run_codex
        monkeypatch.setattr(app.codex_connection, 'command', lambda: None)
        with pytest.raises(ValueError, match='能力与工具中连接 Codex'):
            app.start(job['id'])
        assert not app.processes
        assert app.job(job['id'])['status'] == 'prepared'
    finally:
        app.close()
