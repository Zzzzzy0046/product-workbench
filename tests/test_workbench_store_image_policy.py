"""Public store images work without opening script or API destinations."""

import io
from types import SimpleNamespace

from workbench.api.handler import Handler


def test_store_image_policy_is_limited_to_store_cdns():
    headers = {}
    fake = SimpleNamespace(
        send_response=lambda status: None,
        send_header=lambda key, value: headers.__setitem__(key, value),
        end_headers=lambda: None,
        wfile=io.BytesIO(),
    )
    Handler.respond(fake, b"test", content_type="text/html; charset=utf-8")
    policy = headers["Content-Security-Policy"]
    assert "img-src 'self' blob: https://play-lh.googleusercontent.com https://lh3.googleusercontent.com https://*.mzstatic.com" in policy
    assert "script-src 'self';" in policy and "connect-src 'self';" in policy
    assert "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    assert "img-src https:" not in policy
