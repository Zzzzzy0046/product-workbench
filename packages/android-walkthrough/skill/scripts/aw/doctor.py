"""Environment self-check with a concrete fix for every failure."""

from __future__ import annotations

import importlib.util
import re
import sys
from typing import Any

from .adb import Adb, find_adb, list_devices
from .errors import AwError
from .montage import find_font


def run_doctor(adb_path: str | None = None, serial: str | None = None, package: str | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, fix: str = "", required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail, **({"fix": fix} if not ok else {})})

    add("python", sys.version_info >= (3, 9), sys.version.split()[0], "安装 Python 3.9 或更高版本")
    add("pillow", importlib.util.find_spec("PIL") is not None, "截图缩略图与流程拼图",
        "python -m pip install Pillow")
    add("python-docx", importlib.util.find_spec("docx") is not None, "仅 export-docx 需要",
        "python -m pip install python-docx", required=False)
    font = find_font()
    add("cjk-font", bool(font), font or "未找到", "Windows 自带微软雅黑；Linux: 安装 fonts-noto-cjk")
    devices: list[dict] = []
    try:
        executable = find_adb(adb_path)
        adb = Adb(executable)
        version = adb.run(["version"], "version").decode("utf-8", "replace").splitlines()[0]
        add("adb", True, f"{executable} · {version}")
        devices = list_devices(adb)
        ready = [d for d in devices if d["state"] == "device"]
        others = [f"{d['serial']}={d['state']}" for d in devices if d["state"] != "device"]
        add("device", bool(ready), "；".join(f"{d['serial']} {d['model']}" for d in ready) or "无可用设备",
            "USB 连接手机并开启开发者选项里的 USB 调试；弹出授权框时点允许"
            + (f"（当前：{', '.join(others)}，unauthorized 需在手机上授权）" if others else ""))
        if serial:
            add("serial", any(d["serial"] == serial for d in ready), serial, "用 adb devices 查看正确的 serial")
        target = serial or (ready[0]["serial"] if len(ready) == 1 else None)
        if package and target:
            device = Adb(executable, target)
            path = device.shell(f"pm path {package}", "pm", ok_codes=(0, 1)).decode("utf-8", "replace").strip()
            info = device.shell(f"dumpsys package {package} | grep -m1 versionName", "version",
                                ok_codes=(0, 1)).decode("utf-8", "replace").strip() if path else ""
            add("package", bool(path), info.replace("versionName=", "版本 ") or "未安装",
                f"先在 {target} 上安装 {package}")
    except AwError as error:
        add("adb", False, error.message, "安装 Android SDK platform-tools，或用 --adb 指定 adb 路径")
    ok = all(check["ok"] for check in checks if check["required"])
    return {"ok": ok, "checks": checks, "devices": devices}


def valid_package(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", value or ""))
