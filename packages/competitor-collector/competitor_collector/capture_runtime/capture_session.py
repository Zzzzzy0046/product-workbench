"""Bounded, snapshot-bound Android observations. No autonomous exploration."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET


class CaptureError(RuntimeError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def parse_ui(raw):
    start, end = raw.find(b"<hierarchy"), raw.rfind(b"</hierarchy>")
    if start < 0 or end < start:
        raise CaptureError("设备未返回有效 UI XML；保留截图，但不要按旧元素继续点击。")
    xml = raw[start:end + len(b"</hierarchy>")]
    root = ET.fromstring(xml)
    nodes, actionable = [], []

    def visit(element, parent=None, depth=0):
        for child in element:
            attrs = child.attrib
            node = {"node_id": len(nodes), "parent_id": parent, "depth": depth,
                    **{key: attrs.get(key, "") for key in ("text", "content-desc", "resource-id", "class", "bounds", "package")},
                    **{key: attrs.get(key) == "true" for key in ("clickable", "scrollable", "enabled", "selected", "checked", "password")}}
            nodes.append(node)
            if node["clickable"] and node["enabled"]:
                actionable.append({**node, "index": len(actionable)})
            visit(child, node["node_id"], depth + 1)

    visit(root)
    fingerprint = hashlib.sha256(json.dumps(nodes, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    loading = any("ProgressBar" in n["class"] for n in nodes)
    return xml, nodes, actionable, fingerprint, loading


def png_valid(content):
    if len(content) < 32 or not content.startswith(b"\x89PNG\r\n\x1a\n") or content[12:16] != b"IHDR":
        return False
    width, height = struct.unpack(">II", content[16:24])
    return 0 < width * height <= 40_000_000 and b"IEND" in content[-32:]


def clickable_context(nodes, row):
    """Include non-clickable descendant labels in a clickable container."""
    subtree, descendant_ids = [row], {row["node_id"]}
    for node in nodes:
        if node.get("parent_id") in descendant_ids:
            descendant_ids.add(node["node_id"])
            subtree.append(node)
    return subtree


def tap_block_reason(nodes, row):
    if any(node.get("password") for node in nodes):
        return "当前页面含密码输入框，请人工完成账号操作后重新观察。"
    subtree = clickable_context(nodes, row)
    text = " ".join(node.get(key, "") for node in subtree for key in ("text", "content-desc", "resource-id"))
    if re.search(r"\b(?:buy|purchase|subscribe|install|login|logout|delete|uninstall|reset)\b|sign\s*(?:in|up|out)|start\s+(?:free\s+)?trial|购买|支付|开通|订阅|安装|开始.{0,5}试用|登录|登陆|注册|退出账号|注销|删除|清空|重置|允许权限", text, re.I):
        return "该控件可能涉及购买/试用/安装、账号或破坏性操作，不自动点击，请人工接管。"
    return ""


class AdbClient:
    def __init__(self, executable, serial, timeout=15):
        located = shutil.which(executable)
        self.executable = str(Path(executable).resolve()) if Path(executable).is_file() else located
        if not self.executable:
            raise CaptureError("未找到 ADB；请提供存在的 adb.exe 路径。")
        if not serial or not re.fullmatch(r"[A-Za-z0-9_.:-]+", serial):
            raise CaptureError("新采集接口必须明确指定设备 serial。")
        self.serial, self.timeout, self.timings = serial, timeout, []

    def run(self, args, phase, timeout=None):
        started = time.monotonic()
        result = None
        try:
            result = subprocess.run([self.executable, "-s", self.serial, *args], capture_output=True,
                                    timeout=min(self.timeout, timeout or self.timeout),
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise CaptureError(f"ADB {phase} 失败（退出码 {result.returncode}）；未自动重复操作。")
            if len(result.stdout) > 24 * 1024 * 1024:
                raise CaptureError("设备输出超过 24 MiB；已停止读取本次结果。")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise CaptureError(f"ADB {phase} 超时；请检查页面/设备后重新观察。") from None
        finally:
            self.timings.append({"phase": phase, "seconds": round(time.monotonic() - started, 4),
                                 "ok": result is not None and result.returncode == 0})


@contextmanager
def device_lock(serial):
    directory = Path(tempfile.gettempdir()) / "codex-android-capture-locks"
    directory.mkdir(exist_ok=True)
    path = directory / (hashlib.sha256(serial.encode()).hexdigest()[:24] + ".lock")
    try:
        handle = path.open("x", encoding="utf-8")
    except FileExistsError:
        raise CaptureError("该设备已有采集操作，或上次异常退出遗留锁。确认无采集进程后再清理对应设备锁，不要并行操作。") from None
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        path.unlink(missing_ok=True)


class CaptureSession:
    def __init__(self, client, output_dir, package, settle_timeout=8, poll_interval=.15):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", package):
            raise CaptureError("目标包名无效。")
        self.client, self.root, self.package = client, Path(output_dir).resolve(), package
        self.settle_timeout, self.poll_interval = settle_timeout, poll_interval
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "observations").mkdir(exist_ok=True)
        checkpoint = self.root / "capture-session.json"
        if checkpoint.is_file():
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            if saved.get("package") != package or saved.get("serial") != client.serial:
                raise CaptureError("输出目录属于其他包名或设备，请使用独立目录。")

    def focus(self):
        raw = self.client.run(["shell", "dumpsys", "window", "windows"], "foreground").decode("utf-8", "replace")
        # mFocusedApp can remain the target behind a permission dialog or another
        # focused window. Do not use it as a fallback when foreground ownership
        # cannot be proven, including older dumps without mCurrentFocus.
        lines = [line for line in raw.splitlines() if "mCurrentFocus" in line]
        focused = set()
        for line in lines:
            match = re.search(r"([A-Za-z][\w.]*)/([\w.$]+)", line)
            if not match:
                raise CaptureError("mCurrentFocus 为空或无法识别，已安全暂停；不使用后台 mFocusedApp 代替。")
            focused.add((match.group(1), match.group(2)))
        if len(focused) == 1:
            return next(iter(focused))
        raise CaptureError("无法唯一识别 mCurrentFocus；未执行点击。仅有 mFocusedApp 的设备需人工处理。")

    def dump(self, timeout=None):
        # Only this generated temporary path enters a fixed Android shell command.
        # User text, selectors and host paths are never interpolated into shell.
        remote = "/sdcard/codex_research_" + uuid.uuid4().hex + ".xml"
        command = f"uiautomator dump {remote} >/dev/null 2>&1 && cat {remote}; rm -f {remote}"
        return parse_ui(self.client.run(["shell", command], "ui", timeout))

    def screenshot(self, observation_id):
        content = self.client.run(["exec-out", "screencap", "-p"], "screenshot")
        if not png_valid(content):
            remote = "/sdcard/codex_research_" + uuid.uuid4().hex + ".png"
            local = self.root / "observations" / (observation_id + ".png")
            try:
                self.client.run(["shell", "screencap", "-p", remote], "screenshot_fallback")
                self.client.run(["pull", remote, str(local)], "screenshot_pull")
                content = local.read_bytes()
            finally:
                self.client.run(["shell", "rm", "-f", remote], "screenshot_cleanup")
        if not png_valid(content):
            raise CaptureError("截图未通过 PNG 校验；不能当成已采集页面。")
        return content

    def observe(self, previous=None, action=None):
        started = time.monotonic()
        checkpoint_path = self.root / "capture-session.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {}
        package, activity = self.focus()
        if package != self.package:
            raise CaptureError("前台不是目标应用，已暂停。系统选择器/权限或外部页面请人工处理后重新观察。")
        deadline, stable = time.monotonic() + self.settle_timeout, None
        parsed, ui_error = None, ""
        while time.monotonic() < deadline:
            try:
                parsed = self.dump(timeout=max(.1, deadline - time.monotonic()))
            except (CaptureError, ET.ParseError) as error:
                ui_error = str(error)
                break
            # A normal snapshot needs no second expensive uiautomator dump.
            # The next action always revalidates the complete UI fingerprint.
            # Only an explicit loading indicator causes bounded polling here.
            if not parsed[4]:
                break
            time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
        observation_id = "obs-" + uuid.uuid4().hex[:16]
        content = self.screenshot(observation_id)
        screenshot = "observations/" + observation_id + ".png"
        # Preserve successfully captured pixels even if a later foreground check
        # fails; the service will not present them as an actionable observation.
        (self.root / screenshot).write_bytes(content)
        if self.focus() != (package, activity):
            raise CaptureError("采集期间前台页面已变化，本次图文未登记；请重新观察。")
        ui_xml = ""
        if parsed:
            ui_xml = "observations/" + observation_id + ".xml"
            (self.root / ui_xml).write_bytes(parsed[0])
        item = {"schema_version": 1, "id": observation_id, "package": package, "serial": self.client.serial,
                "activity": activity, "captured_at": timestamp(), "files": {"screenshot": screenshot, "ui_xml": ui_xml},
                "ui_fingerprint": parsed[3] if parsed else "", "nodes": parsed[1] if parsed else [],
                "clickables": parsed[2] if parsed else [], "stable": stable,
                "stability_check": "single_snapshot_with_foreground_check",
                "actionable": bool(parsed) and not parsed[4],
                "status": "observed" if parsed and not parsed[4] else "visual_only" if not parsed else "loading",
                "ui_error": ui_error, "seconds": round(time.monotonic() - started, 4)}
        if previous:
            item.update(previous_observation_id=previous, action=action)
        unresolved = list(checkpoint.get("unresolved_actions", []))
        pending = checkpoint.get("pending_action")
        if pending:
            if previous == pending["source_observation_id"] and action == pending["action"]:
                item["action_id"] = pending["id"]
            else:
                # Recovery observation proves only the current screen. An action
                # whose post-state was lost must not become a confirmed edge.
                item["unresolved_action"] = pending
                if not any(entry["id"] == pending["id"] for entry in unresolved):
                    unresolved.append(pending)
        atomic_json(self.root / "observations" / (observation_id + ".json"), item)
        atomic_json(checkpoint_path, {"package": self.package, "serial": self.client.serial,
                    "status": "ready", "last_observation_id": observation_id,
                    "unresolved_actions": unresolved, "updated_at": timestamp()})
        return item

    def act_observe(self, observation_id, action, index=None, swipe=None):
        if not re.fullmatch(r"obs-[a-f0-9]{16}", observation_id):
            raise CaptureError("必须提供有效 observation_id，不能用裸编号或旧坐标操作。")
        path = self.root / "observations" / (observation_id + ".json")
        if not path.is_file():
            raise CaptureError("找不到指定观察记录。")
        saved = json.loads(path.read_text(encoding="utf-8"))
        checkpoint = json.loads((self.root / "capture-session.json").read_text(encoding="utf-8"))
        if checkpoint.get("pending_action") or checkpoint.get("last_observation_id") != observation_id or not saved.get("actionable"):
            raise CaptureError("不是最新可操作观察，或页面仍在加载；请重新观察。")
        if saved["package"] != self.package or saved["serial"] != self.client.serial:
            raise CaptureError("观察记录的应用/设备不匹配。")
        if self.focus() != (saved["package"], saved["activity"]):
            raise CaptureError("前台页面已变化，未执行操作，请重新观察。")
        current = self.dump()
        if current[3] != saved["ui_fingerprint"]:
            raise CaptureError("UI 已变化，未执行旧元素操作，请重新观察。")
        details = {"type": action}
        if action == "tap":
            rows = saved["clickables"]
            if index is None or not 0 <= index < len(rows):
                raise CaptureError("请指定当前观察中的有效元素 index。")
            row = rows[index]
            # Android commonly exposes a clickable container with its label in a
            # non-clickable child. Guard the entire selected subtree, not just
            # the empty container's attributes.
            blocked = tap_block_reason(saved.get("nodes", []), row)
            if blocked:
                raise CaptureError(blocked)
            bounds = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", row["bounds"])
            if not bounds:
                raise CaptureError("元素坐标无效。")
            x1, y1, x2, y2 = map(int, bounds.groups())
            if x2 <= x1 or y2 <= y1:
                raise CaptureError("元素范围为空。")
            # A clickable container often has no text of its own. Keep the
            # observed descendant label in the action evidence so exported
            # arrows say "点击 Next", not just an opaque control number.
            label = row["text"] or row["content-desc"]
            if not label:
                context = clickable_context(saved.get("nodes", []), row)
                label = next((item.get(key, "").strip() for item in context
                              for key in ("text", "content-desc") if item.get(key, "").strip()), "")
            details.update(index=index, resource_id=row["resource-id"], text=label[:160])
            command, phase = ["shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2)], "tap"
        elif action == "back":
            command, phase = ["shell", "input", "keyevent", "4"], "back"
        elif action == "swipe":
            if not swipe or len(swipe) != 4 or any(not isinstance(v, int) or v < 0 or v > 20000 for v in swipe):
                raise CaptureError("swipe 需要四个非负有效坐标。")
            details["coordinates"] = swipe
            command, phase = ["shell", "input", "swipe", *map(str, swipe), "250"], "swipe"
        else:
            raise CaptureError("只允许 tap、back、swipe；不接受任意 ADB shell。")
        # Invalidate before sending input: a timeout or failed screenshot does
        # not prove that the input did not run. Only a fresh observe restores
        # actionability, while retaining uncertain action evidence.
        atomic_json(self.root / "capture-session.json", {"package": self.package, "serial": self.client.serial,
                    "status": "pending_action", "last_observation_id": None,
                    "unresolved_actions": checkpoint.get("unresolved_actions", []),
                    "pending_action": {"id": "action-" + uuid.uuid4().hex[:16],
                                       "source_observation_id": observation_id, "action": details,
                                       "requested_at": timestamp(), "outcome": "unknown"},
                    "updated_at": timestamp()})
        self.client.run(command, phase)
        return self.observe(previous=observation_id, action=details)


def main():
    # Windows console defaults may be GBK. Preserve Chinese/emoji JSON without
    # letting an output encoding error turn a completed capture into a failure.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("observe", "act-observe"))
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--observation-id")
    parser.add_argument("--action", choices=("tap", "back", "swipe"))
    parser.add_argument("--index", type=int)
    parser.add_argument("--swipe", type=int, nargs=4)
    parser.add_argument("--settle-timeout", type=float, default=8)
    args = parser.parse_args()
    if not .2 <= args.settle_timeout <= 30:
        parser.error("settle-timeout 需在 0.2–30 秒内")
    client, started, result = None, time.monotonic(), None
    try:
        client = AdbClient(args.adb, args.serial)
        with device_lock(args.serial):
            session = CaptureSession(client, args.out_dir, args.package, args.settle_timeout)
            if args.command == "observe":
                result = session.observe()
            else:
                result = session.act_observe(args.observation_id or "", args.action, args.index, args.swipe)
        print(json.dumps({"ok": True, "observation": result, "adb_calls": len(client.timings)}, ensure_ascii=False))
        return 0
    except (CaptureError, OSError, ValueError, ET.ParseError) as error:
        print(json.dumps({"ok": False, "error": str(error), "action_may_have_run": bool(client and any(t["phase"] in {"tap", "back", "swipe"} for t in client.timings)), "hint": "先观察当前位置，不要直接重复上一动作。"}, ensure_ascii=False))
        return 1
    finally:
        if client:
            destination = Path(args.out_dir).resolve()
            destination.mkdir(parents=True, exist_ok=True)
            with (destination / "timings.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"at": timestamp(), "command": args.command, "ok": result is not None,
                    "seconds": round(time.monotonic()-started, 4), "adb_calls": len(client.timings), "phases": client.timings}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
