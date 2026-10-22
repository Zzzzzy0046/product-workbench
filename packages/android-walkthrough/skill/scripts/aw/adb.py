"""Thin ADB wrapper: one place for timeouts, exit codes and timing records."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Iterable

from .errors import AwError

SERIAL_RE = re.compile(r"[A-Za-z0-9_.:-]+")


def find_adb(explicit: str | None = None) -> str:
    """Resolve adb from an explicit path, PATH, or the usual SDK locations."""
    candidates: list[Path] = []
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return os.path.abspath(path)
        located = shutil.which(explicit)
        if located:
            return located
        raise AwError("ADB_NOT_FOUND", f"指定的 adb 不存在：{explicit}")
    located = shutil.which("adb")
    if located:
        return located
    name = "adb.exe" if os.name == "nt" else "adb"
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "platform-tools" / name)
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk" / "platform-tools" / name)
    candidates += [Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / name,
                   Path.home() / "Android" / "Sdk" / "platform-tools" / name]
    for candidate in candidates:
        if candidate.is_file():
            return os.path.abspath(candidate)
    raise AwError("ADB_NOT_FOUND", "未找到 adb：安装 Android platform-tools，或用 --adb 指定路径。")


class Adb:
    def __init__(self, executable: str, serial: str | None = None, timeout: float = 15):
        if serial is not None and not SERIAL_RE.fullmatch(serial):
            raise AwError("BAD_ARGS", "设备 serial 含非法字符。")
        self.executable, self.serial, self.timeout = executable, serial, timeout
        self.timings: list[dict] = []

    def run(self, args: list[str], phase: str, timeout: float | None = None,
            ok_codes: Iterable[int] = (0,)) -> bytes:
        command = [self.executable, *(["-s", self.serial] if self.serial else []), *args]
        started, ok = time.monotonic(), False
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout or self.timeout,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode not in tuple(ok_codes):
                detail = (result.stderr or result.stdout).decode("utf-8", "replace").strip()[:200]
                raise AwError("ADB_FAILED", f"ADB {phase} 失败（退出码 {result.returncode}）：{detail}")
            ok = True
            return result.stdout
        except subprocess.TimeoutExpired:
            raise AwError("ADB_TIMEOUT", f"ADB {phase} 超时。") from None
        except FileNotFoundError:
            raise AwError("ADB_NOT_FOUND", f"无法执行 adb：{self.executable}") from None
        finally:
            self.timings.append({"phase": phase, "seconds": round(time.monotonic() - started, 4), "ok": ok})

    def shell(self, command: str, phase: str, timeout: float | None = None,
              ok_codes: Iterable[int] = (0,)) -> bytes:
        # Only fixed, validated strings reach the device shell; never raw user text.
        return self.run(["shell", command], phase, timeout, ok_codes)


def list_devices(adb: Adb) -> list[dict]:
    raw = adb.run(["devices", "-l"], "devices").decode("utf-8", "replace")
    devices = []
    for line in raw.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        info = dict(part.split(":", 1) for part in parts[2:] if ":" in part)
        devices.append({"serial": parts[0], "state": parts[1], "model": info.get("model", ""),
                        "product": info.get("product", "")})
    return devices
