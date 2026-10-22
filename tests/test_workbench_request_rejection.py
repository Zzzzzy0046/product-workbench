"""Rejected POST bodies are never parsed and cannot cause unbounded reads."""
import io
from types import SimpleNamespace

import pytest

from workbench.api.handler import Handler


class Connection:
    def __init__(self):
        self.timeout = None
        self.calls = []

    def gettimeout(self):
        return self.timeout

    def settimeout(self, timeout):
        self.calls.append(timeout)
        self.timeout = timeout


@pytest.mark.parametrize('headers', [
    {}, {'X-Workbench-Token': 'wrong'},
    {'X-Workbench-Token': 'fixture', 'Origin': 'https://foreign.example'},
    {'X-Workbench-Token': 'fixture', 'Host': 'foreign.example'},
])
def test_rejected_small_post_is_drained_without_dispatch(headers):
    request = object.__new__(Handler)
    body = b'{"confirmed":true}'
    request.headers = {'Host': '127.0.0.1:8765', 'Content-Length': str(len(body)), **headers}
    request.server = SimpleNamespace(server_port=8765, app=SimpleNamespace(token='fixture'))
    request.path = '/api/integrations/codex/login'
    request.rfile = io.BytesIO(body)
    request.connection = Connection()
    responses = []
    request.respond = lambda data, status: responses.append((data, status))
    request.do_POST()
    assert responses == [({'error': '请求校验失败，请刷新工作台。'}, 403)]
    assert request.rfile.tell() == len(body)
    assert request.connection.calls == [0.5, None]
    assert request.close_connection is True


@pytest.mark.parametrize('length', ['garbage', '-1', str(16 * 1024 + 1)])
def test_unauthenticated_large_or_invalid_length_is_not_read(length):
    request = object.__new__(Handler)
    request.headers = {'Content-Length': length}
    request.rfile = io.BytesIO(b'body-is-not-parsed')
    request.connection = Connection()
    request.discard_rejected_body()
    assert request.rfile.tell() == 0
    assert request.connection.calls == []
