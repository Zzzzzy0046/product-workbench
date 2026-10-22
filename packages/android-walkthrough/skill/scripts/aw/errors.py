"""Stable error codes. Callers (agents, the workbench) branch on `code`, not on text."""

from __future__ import annotations

from typing import Any

from . import PROTOCOL

# code -> default next step for the caller
CODES = {
    "BAD_ARGS": "fix_args",
    "NOT_INITIALIZED": "init",
    "WORKSPACE_MISMATCH": "use_new_out_dir",
    "ADB_NOT_FOUND": "install_adb",
    "DEVICE_NOT_FOUND": "connect_device",
    "DEVICE_AMBIGUOUS": "pass_serial",
    "PACKAGE_NOT_INSTALLED": "install_app",
    "ADB_FAILED": "observe",
    "ADB_TIMEOUT": "observe",
    "DEVICE_LOCKED": "wait",
    "FOCUS_UNKNOWN": "observe",
    "NOT_TARGET_APP": "manual_then_observe",
    "FOREGROUND_CHANGED": "choose_again",
    "UI_CHANGED": "choose_again",
    "AD_CLEARED": "choose_again",
    "STALE_OBSERVATION": "observe",
    "NOT_ACTIONABLE": "use_tap_xy_or_back",
    "BLOCKED_SENSITIVE": "manual_or_confirm",
    "NO_FOCUSED_INPUT": "tap_input_first",
    "SCREENSHOT_INVALID": "observe",
    "ACTION_UNCERTAIN": "observe",
    "MAP_ERROR": "fix_map",
}


class AwError(Exception):
    def __init__(self, code: str, message: str, acted: bool = False, next_step: str | None = None, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.acted = acted
        self.next_step = next_step or CODES.get(code, "observe")
        self.extra = extra

    def to_json(self) -> dict[str, Any]:
        return {"v": PROTOCOL, "ok": False, "code": self.code, "message": self.message,
                "acted": self.acted, "next": self.next_step, **self.extra}
