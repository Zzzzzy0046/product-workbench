"""Portable launch dispatch and JSON download contracts; no devices or network."""
import json
from pathlib import Path
import socket

import pytest

from scripts.packaging.workbench_launcher import worker_target, available_port
from workbench.api.serializers import encode_body


def test_only_fixed_worker_scripts_can_be_dispatched(tmp_path):
    script = tmp_path / 'workbench/capture_mcp.py'
    assert worker_target(['-X', 'utf8', str(script), '--session', 'fixture'], tmp_path) == ('capture-mcp', ['--session', 'fixture'])
    assert worker_target([str(tmp_path / 'workbench/review_scraper_worker.py')], tmp_path) == ('collector', [])
    assert worker_target(['--self-test'], tmp_path) is None
    with pytest.raises(ValueError, match='固定 worker'):
        worker_target([str(tmp_path / 'untrusted.py')], tmp_path)


def test_port_selection_does_not_stop_existing_listener():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        with pytest.raises(ValueError, match='端口不可用'):
            available_port(port, False)
        assert listener.getsockname()[1] == port


def test_frozen_child_dispatches_fixed_module_after_fresh_unpack(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    parent_path = tmp_path / 'old-unpack/workbench/capture_mcp.py'
    assert worker_target([str(parent_path), '--session', 'fixture'], tmp_path / 'new-unpack') == ('capture-mcp', ['--session', 'fixture'])


def test_json_download_bytes_are_not_json_encoded_twice():
    body = '{"模块":"首页"}'.encode('utf-8')
    assert encode_body(body, 'application/json; charset=utf-8') == body
    assert json.loads(encode_body({'模块': '首页'}, 'application/json')) == {'模块': '首页'}
