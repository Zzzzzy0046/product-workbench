"""Device primitives: foreground detection, capture, input and obstruction clearing."""

from __future__ import annotations

import re
import struct
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .adb import Adb
from .errors import AwError
from .ui import parse_ui

FOCUS_COMMANDS = {
    # Android 14+ only reports mCurrentFocus in the displays dump; older builds in windows.
    "displays": "dumpsys window displays | grep mCurrentFocus",
    "windows": "dumpsys window windows | grep mCurrentFocus",
}
FOCUS_RE = re.compile(r"([A-Za-z][\w.]*)/([\w.$]+)")

# Activities of ad SDKs that name themselves. Matched as class-name prefixes, so an
# app screen such as RemoveAdsActivity is never dismissed by mistake.
AD_PREFIXES = (
    "com.google.android.gms.ads.", "com.facebook.ads.", "com.applovin.", "com.unity3d.ads.",
    "com.unity3d.services.ads.", "com.ironsource.", "com.vungle.", "com.liftoff.",
    "com.bytedance.sdk.openadsdk.", "com.pangle.", "com.mbridge.msdk.", "com.mintegral.",
    "com.inmobi.", "com.chartboost.", "com.fyber.", "com.digitalturbine.", "com.yandex.mobile.ads.",
    "com.my.target.", "sg.bigo.ads.", "com.adcolony.", "com.smaato.", "com.amazon.device.ads.",
    "com.moloco.", "com.kwai.network.", "com.tapjoy.",
)
AUTO_RETURN = {"com.android.vending", "com.android.chrome", "com.android.browser", "org.mozilla.firefox",
               "com.brave.browser", "com.microsoft.emmx", "com.opera.browser", "com.sec.android.app.sbrowser",
               "com.mi.globalbrowser", "com.UCMobile.intl", "com.google.android.googlequicksearchbox"}
LAUNCHERS = {"com.google.android.apps.nexuslauncher", "com.android.launcher3", "com.android.launcher",
             "com.miui.home", "com.mi.android.globallauncher", "com.sec.android.app.launcher",
             "com.oneplus.launcher", "com.oppo.launcher", "com.bbk.launcher2", "com.huawei.android.launcher",
             "com.hihonor.android.launcher", "com.transsion.hilauncher", "com.transsion.XOSLauncher",
             "com.motorola.launcher3", "com.nothing.launcher"}
CLOSE_EXACT = {"x", "×", "✕", "✖", "close", "close ad", "skip", "skip ad", "skip video", "no thanks", "dismiss",
               "关闭", "关闭广告", "跳过", "跳过广告", "cerrar", "fechar", "tutup", "lewati", "saltar", "pular",
               "bỏ qua", "đóng", "ข้าม", "ปิด", "закрыть", "пропустить"}
CLOSE_PATTERN = re.compile(r"\b(close|skip|dismiss)\b|关闭|跳过", re.I)
CTA_PATTERN = re.compile(r"install|download|open|play|get|learn|shop|visit|安装|下载|打开|立即", re.I)


def png_valid(content: bytes) -> bool:
    if len(content) < 33 or not content.startswith(b"\x89PNG\r\n\x1a\n") or content[12:16] != b"IHDR":
        return False
    width, height = struct.unpack(">II", content[16:24])
    return 0 < width * height <= 40_000_000 and b"IEND" in content[-32:]


def png_size(content: bytes) -> list[int]:
    return list(struct.unpack(">II", content[16:24]))


def full_activity(package: str, activity: str) -> str:
    return package + activity if activity.startswith(".") else activity


def is_ad_activity(activity: str) -> bool:
    return activity.startswith(AD_PREFIXES) or activity.rsplit(".", 1)[-1] in {"AdActivity", "AudienceNetworkActivity"}


class Device:
    def __init__(self, adb: Adb, package: str, cache: dict[str, Any] | None = None,
                 sleep: Callable[[float], None] | None = None):
        self.adb, self.package = adb, package
        self.cache = cache if cache is not None else {}
        self.sleep = sleep or time.sleep

    # ---------- foreground ----------
    def _focus_lines(self) -> list[str]:
        order = [self.cache.get("focus_cmd", "displays")]
        order += [name for name in FOCUS_COMMANDS if name not in order]
        for name in order:
            raw = self.adb.shell(FOCUS_COMMANDS[name], "foreground", ok_codes=(0, 1)).decode("utf-8", "replace")
            lines = [line for line in raw.splitlines() if "mCurrentFocus" in line]
            if lines:
                self.cache["focus_cmd"] = name
                return lines
        return []

    def resumed_activity(self) -> tuple[str, str] | None:
        raw = self.adb.shell("dumpsys activity activities | grep -E 'topResumedActivity|ResumedActivity:'",
                             "foreground", ok_codes=(0, 1)).decode("utf-8", "replace")
        for line in raw.splitlines():
            match = FOCUS_RE.search(line)
            if match:
                return match.group(1), full_activity(match.group(1), match.group(2))
        return None

    def focus(self) -> tuple[str, str]:
        """Return (package, full activity) of the single focused window, or raise.

        Activity switches and ad overlays briefly report no focus; only that empty case is
        retried. Two different focused windows, or an unparseable value, fail at once.
        mFocusedApp is never used: it stays on the app behind dialogs and other apps.
        """
        for attempt in range(4):
            focused, popup = set(), False
            for line in self._focus_lines():
                value = line.split("mCurrentFocus=", 1)[-1].strip()
                if value == "null":
                    continue
                match = FOCUS_RE.search(value)
                if match:
                    focused.add((match.group(1), full_activity(match.group(1), match.group(2))))
                elif "PopupWindow:" in value:
                    popup = True  # same-app dropdown/overflow menus report no package
                else:
                    raise AwError("FOCUS_UNKNOWN", f"无法识别前台窗口：{value[:80]}")
            if not focused and popup:
                resolved = self.resumed_activity()
                if resolved:
                    focused.add(resolved)
            if len(focused) == 1:
                return next(iter(focused))
            if len(focused) > 1:
                raise AwError("FOCUS_UNKNOWN", "同时存在多个前台窗口，无法唯一判断。")
            if attempt < 3:
                self.sleep(0.4)
        raise AwError("FOCUS_UNKNOWN", "前台窗口为空（可能是锁屏或过渡中），已暂停。")

    # ---------- capture ----------
    def screencap(self) -> bytes:
        content = self.adb.run(["exec-out", "screencap", "-p"], "screenshot")
        if not png_valid(content):
            raise AwError("SCREENSHOT_INVALID", "截图未通过 PNG 校验（可能是安全页面禁止截屏）。")
        return content

    def dump(self, timeout: float) -> dict[str, Any]:
        remote = "/sdcard/aw_" + uuid.uuid4().hex + ".xml"
        command = f"uiautomator dump {remote} >/dev/null 2>&1 && cat {remote}; rm -f {remote}"
        return parse_ui(self.adb.shell(command, "ui", timeout=timeout))

    # ---------- input ----------
    def tap(self, x: int, y: int) -> None:
        self.adb.shell(f"input tap {int(x)} {int(y)}", "tap")

    def back(self) -> None:
        self.adb.shell("input keyevent 4", "back")

    def enter(self) -> None:
        self.adb.shell("input keyevent 66", "key")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        self.adb.shell(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration)}", "swipe")

    def text(self, value: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9 @._+,:/=-]{1,200}", value):
            raise AwError("BAD_ARGS", "text 仅支持 ASCII 字母数字、空格和 @._+,:/=- ，最长 200 字符。")
        self.adb.shell("input text " + value.replace(" ", "%s"), "text")

    def launch(self) -> None:
        self.adb.shell(f"monkey -p {self.package} -c android.intent.category.LAUNCHER 1", "launch")

    # ---------- obstruction clearing ----------
    def _evidence(self, evidence_dir: Path, prefix: str) -> str:
        try:
            content = self.screencap()
        except AwError:
            return ""
        name = f"{prefix}-{uuid.uuid4().hex[:12]}.png"
        (evidence_dir / name).write_bytes(content)
        return f"observations/{name}"

    def _close_button(self) -> tuple[int, int] | None:
        try:
            parsed = self.dump(timeout=4)
        except AwError:
            return None
        for control in parsed["controls"]:
            label = " ".join(control["label"].lower().split()).strip(" ›>»")
            if label in CLOSE_EXACT or (CLOSE_PATTERN.search(label) and not CTA_PATTERN.search(label)):
                return tuple(control["center"])
        return None

    def is_launcher(self, package: str) -> bool:
        return package in LAUNCHERS or package == self.cache.get("launcher")

    def clear(self, current: tuple[str, str], evidence_dir: Path, extra_return: set[str] = frozenset()
              ) -> tuple[list[dict[str, Any]], tuple[str, str]]:
        """Dismiss app-owned ad windows and ad-style external jumps, max 3 rounds.

        Only exact close/skip labels or the back key are used; ad CTAs never match.
        Relaunch from the launcher happens only when this call caused the exit.
        Unknown foreign apps, permission dialogs and pickers are left to the operator.
        """
        dismissed: list[dict[str, Any]] = []
        for _ in range(3):
            package, activity = current
            if package == self.package and not is_ad_activity(activity):
                break
            record: dict[str, Any] = {"package": package, "activity": activity}
            if package == self.package:
                record["kind"] = "ad"
                record["screenshot"] = self._evidence(evidence_dir, "ad")
                self.back()
                self.sleep(0.8)
                current = self.focus()
                record["by"] = "back"
                if current[0] == self.package and is_ad_activity(current[1]):
                    point = self._close_button()
                    if point:
                        self.tap(*point)
                        record["by"] = "close"
                        self.sleep(0.8)
                        current = self.focus()
            elif package in AUTO_RETURN or package in extra_return:
                record.update(kind="external_jump", by="back", screenshot=self._evidence(evidence_dir, "jump"))
                self.back()
                self.sleep(1.0)
                current = self.focus()
            elif self.is_launcher(package) and dismissed:
                record.update(kind="app_exited", by="relaunch")
                self.launch()
                self.sleep(2.0)
                current = self.focus()
            else:
                break
            dismissed.append(record)
        return dismissed, current
