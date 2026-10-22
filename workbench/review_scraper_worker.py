"""Compatibility entry point for the extracted competitor collector.

The implementation lives only in packages/competitor-collector.  Keep this
historical script path because existing workbench subprocesses call it directly.

Execute the fixed, repository-owned engine in THIS module namespace rather than
forwarding imported functions: callers load this file with importlib and patch
private provider helpers.  Their patches must remain visible through the shared
function globals (including when the loader does not register sys.modules).
This is not a dynamic plugin loader; neither stdin nor a configured legacy root
can choose the source file executed here.
"""
from __future__ import annotations

from pathlib import Path as _BridgePath
import sys as _bridge_sys


_COLLECTOR_PACKAGE_ROOT = (
    _BridgePath(__file__).resolve().parents[1] / "packages" / "competitor-collector"
)
_COLLECTOR_ENGINE = _COLLECTOR_PACKAGE_ROOT / "competitor_collector" / "engine.py"
if not _COLLECTOR_ENGINE.is_file():
    raise RuntimeError(
        "Missing bundled competitor collector: packages/competitor-collector/"
        "competitor_collector/engine.py"
    )

# Resolve absolute competitor_collector imports without relying on the caller's
# current working directory or installing the workbench itself.
_bridge_sys.path.insert(0, str(_COLLECTOR_PACKAGE_ROOT))
exec(compile(_COLLECTOR_ENGINE.read_bytes(), str(_COLLECTOR_ENGINE), "exec"), globals(), globals())
