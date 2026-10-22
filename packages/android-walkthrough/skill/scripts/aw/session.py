"""Observe / act: one bounded step at a time, every step bound to fresh evidence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
import time
import uuid
from typing import Any, Callable

from .device import Device, png_size
from .errors import AwError
from .ui import actionable_signature, actionable_structure, parse_bounds
from .workspace import Workspace, atomic_json, now_iso

SENSITIVE = re.compile(
    r"\b(buy|purchase|subscribe|install|upgrade|unlock)\b|start\s+(?:my\s+|your\s+)?(?:free\s+)?trial|free\s+trial"
    r"|try\s+(?:it\s+)?(?:for\s+)?free|get\s+premium|go\s+premium|claim\s+(?:offer|now)"
    r"|购买|支付|开通|订阅|安装|试用|升级|解锁|comprar|assinar|suscrib|langganan|beli\b",
    re.I)
VIEW_WIDTH = 480


def _targets(controls, action, index=None, point=None):
    if action == "tap":
        return [controls[index]]
    if action == "text":
        return [control for control in controls if control.get("kind") == "edit" and control.get("focused")]
    hits = []
    for control in controls:
        box = parse_bounds(control.get("bounds", ""))
        if box and box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]:
            hits.append(((box[2] - box[0]) * (box[3] - box[1]), control))
    if not hits:
        return []
    area = min(item[0] for item in hits)
    return [control for size, control in hits if size == area]


def write_view(png_path, view_path) -> bool:
    """A small JPEG for the agent to look at; the PNG stays the delivery evidence."""
    try:
        from PIL import Image
    except ImportError:
        return False
    with Image.open(png_path) as image:
        image = image.convert("RGB")
        if image.width > VIEW_WIDTH:
            image = image.resize((VIEW_WIDTH, round(image.height * VIEW_WIDTH / image.width)), Image.Resampling.LANCZOS)
        image.save(view_path, "JPEG", quality=72, optimize=True)
    return True


class Session:
    def __init__(self, workspace: Workspace, device: Device, settle_timeout: float = 8, dump_timeout: float = 7,
                 fresh_seconds: float = 8, post_action_wait: float = 0.5, auto_dismiss: bool = True,
                 extra_return: set[str] = frozenset(), sleep: Callable[[float], None] | None = None):
        self.ws, self.device = workspace, device
        self.settle_timeout, self.dump_timeout, self.fresh_seconds = settle_timeout, dump_timeout, fresh_seconds
        self.post_action_wait, self.auto_dismiss, self.extra_return = post_action_wait, auto_dismiss, extra_return
        self.sleep = sleep or time.sleep
        self.ws.observations.mkdir(parents=True, exist_ok=True)

    @property
    def package(self) -> str:
        return self.device.package

    # ------------------------------------------------------------------ observe
    def _foreground(self) -> tuple[list[dict[str, Any]], tuple[str, str]]:
        current = self.device.focus()
        if not self.auto_dismiss:
            return [], current
        return self.device.clear(current, self.ws.observations, set(self.extra_return))

    def observe(self, previous: str | None = None, action: dict[str, Any] | None = None,
                cleared: tuple[list[dict[str, Any]], tuple[str, str]] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        dismissed, current = cleared if cleared else self._foreground()
        if current[0] != self.package:
            launcher = self.device.is_launcher(current[0])
            raise AwError("NOT_TARGET_APP", f"前台是 {current[0]}/{current[1]}，不是目标应用。",
                          next_step="launch" if launcher else "manual_then_observe",
                          foreground=current[0], activity=current[1], ads_closed=_brief_ads(dismissed))
        parsed, ui_error = None, ""
        # Screenshot and UI dump run concurrently; they are independent device processes.
        with ThreadPoolExecutor(max_workers=1) as pool:
            shot_future = pool.submit(self.device.screencap)
            try:
                parsed = self.device.dump(self.dump_timeout)
            except AwError as error:
                ui_error = error.message
            content = shot_future.result()
        if parsed and parsed["loading"]:
            deadline = time.monotonic() + self.settle_timeout
            while parsed["loading"] and time.monotonic() < deadline:
                self.sleep(0.3)
                try:
                    parsed = self.device.dump(max(1.0, min(self.dump_timeout, deadline - time.monotonic() + 1)))
                except AwError as error:
                    ui_error = error.message
                    break
            content = self.device.screencap()
        after = self.device.focus()
        if after != current:
            raise AwError("FOREGROUND_CHANGED", f"采集期间前台从 {current[1]} 变为 {after[1]}，本次未登记。",
                          next_step="observe")
        observation_id = "obs-" + uuid.uuid4().hex[:16]
        stem = self.ws.observations / observation_id
        stem.with_suffix(".png").write_bytes(content)
        files = {"screenshot": f"observations/{observation_id}.png", "ui_xml": ""}
        if parsed:
            stem.with_suffix(".xml").write_bytes(parsed["xml"])
            files["ui_xml"] = f"observations/{observation_id}.xml"
        if write_view(stem.with_suffix(".png"), stem.with_suffix(".view.jpg")):
            files["view"] = f"observations/{observation_id}.view.jpg"
        status = "visual_only" if not parsed else "loading" if parsed["loading"] else "observed"
        item: dict[str, Any] = {
            "schema_version": 1, "id": observation_id, "package": current[0], "serial": self.device.adb.serial,
            "activity": current[1], "captured_at": now_iso(), "files": files, "status": status,
            "screen": png_size(content), "ui_error": ui_error,
            "ui_fingerprint": parsed["fingerprint"] if parsed else "",
            "controls": [{k: v for k, v in c.items() if k not in ("guard_text",)} for c in parsed["controls"]] if parsed else [],
            "guards": [c["guard_text"] for c in parsed["controls"]] if parsed else [],
            "nodes": [{k: v for k, v in n.items() if k != "box"} for n in parsed["nodes"]] if parsed else [],
            "seconds": round(time.monotonic() - started, 3)}
        if previous:
            item.update(previous_observation_id=previous, action=action)
        if dismissed:
            item["auto_dismissed"] = dismissed
        checkpoint = self.ws.checkpoint()
        unresolved = list(checkpoint.get("unresolved_actions", []))
        pending = checkpoint.get("pending_action")
        if pending:
            if previous == pending["source_observation_id"] and action == pending["action"]:
                item["action_id"] = pending["id"]
            else:
                item["unresolved_action"] = pending
                if not any(entry["id"] == pending["id"] for entry in unresolved):
                    unresolved.append(pending)
        atomic_json(stem.with_suffix(".json"), item)
        self.ws.save_checkpoint({"package": self.package, "serial": self.device.adb.serial, "status": "ready",
                                 "last_observation_id": observation_id, "unresolved_actions": unresolved})
        return item

    # ------------------------------------------------------------------ act
    def _recover(self, code: str, message: str, cleared=None) -> AwError:
        """Re-observe after a refused action so the caller can choose again in one round trip."""
        try:
            fresh = self.observe(cleared=cleared)
        except AwError as error:
            return error
        return AwError(code, message, next_step="choose_again", observation=fresh)

    def act(self, observation_id: str, action: str, index: int | None = None, coords: list[int] | None = None,
            value: str | None = None, submit: bool = False, confirm_sensitive: bool = False,
            in_view: bool = False) -> dict[str, Any]:
        saved = self.ws.observation(observation_id)
        if in_view and coords:
            # Coordinates read off the small view JPEG -> device pixels.
            width = (saved.get("screen") or [VIEW_WIDTH])[0]
            scale = width / min(width, VIEW_WIDTH)
            coords = [round(value * scale) for value in coords]
        checkpoint = self.ws.checkpoint()
        if checkpoint.get("pending_action") or checkpoint.get("last_observation_id") != observation_id:
            raise AwError("STALE_OBSERVATION", "这不是最新观察，序号和坐标已失效；请用最新 obs 或重新 observe。")
        if saved.get("package") != self.package or saved.get("serial") != self.device.adb.serial:
            raise AwError("WORKSPACE_MISMATCH", "观察记录的应用或设备与当前不一致。")
        guards = saved.get("guards", [])
        controls = [{**control, "guard_text": guards[i] if i < len(guards) else control.get("guard_text", control.get("label", ""))}
                    for i, control in enumerate(saved.get("controls", []))]
        details: dict[str, Any] = {"type": action}
        if action == "tap":
            if not controls:
                raise AwError("NOT_ACTIONABLE", "该观察没有控件树（visual_only），请用 tap-xy、back 或 swipe。")
            if index is None or not 0 <= index < len(controls):
                raise AwError("BAD_ARGS", f"序号无效；当前可用 0–{len(controls) - 1}。")
            control = controls[index]
            details.update(index=index, label=control["label"], rid=control["rid"])
            point = control["center"]
        elif action == "tap-xy":
            width, height = saved.get("screen") or [0, 0]
            if not coords or len(coords) != 2 or not (0 <= coords[0] < width and 0 <= coords[1] < height):
                raise AwError("BAD_ARGS", f"tap-xy 坐标需在截图范围内（{width}x{height}）。")
            details.update(x=coords[0], y=coords[1])
            point = coords
        elif action == "swipe":
            if not coords or len(coords) != 4 or any(not 0 <= v <= 20000 for v in coords):
                raise AwError("BAD_ARGS", "swipe 需要 x1 y1 x2 y2 四个非负坐标。")
            details["coordinates"] = coords
        elif action == "text":
            focused = [c for c in controls if c.get("kind") == "edit" and c.get("focused")]
            if not focused:
                raise AwError("NO_FOCUSED_INPUT", "当前观察没有获得焦点的输入框；先 tap 输入框，再 text。")
            details.update(value=value or "", submit=bool(submit))
        elif action != "back":
            raise AwError("BAD_ARGS", "动作只支持 tap、tap-xy、back、swipe、text。")

        cleared = self._foreground()
        if cleared[0]:
            raise self._recover("AD_CLEARED", "操作前出现了广告/外跳并已自动关闭，未执行动作；请按新观察重新选择。", cleared)
        current = cleared[1]
        if current != (saved["package"], saved["activity"]):
            raise self._recover("FOREGROUND_CHANGED", "前台页面已变化，未执行动作；请按新观察重新选择。", cleared)
        if action in ("tap", "tap-xy", "text"):
            # Never skip input validation because an observation is only seconds
            # old. Compose/WebView buttons can change meaning in the same slot.
            parsed = None
            try:
                parsed = self.device.dump(self.dump_timeout)
            except AwError:
                if action != "tap-xy" or saved.get("status") != "visual_only" or controls:
                    raise self._recover("UI_CHANGED", "当前控件无法重新核对，未执行动作；请按新观察重新选择。")
            if parsed is not None:
                latest = parsed["controls"]
                if (actionable_structure(controls) != actionable_structure(latest)
                        or actionable_signature(_targets(controls, action, index, point if action == "tap-xy" else None))
                        != actionable_signature(_targets(latest, action, index, point if action == "tap-xy" else None))):
                    raise self._recover("UI_CHANGED", "页面控件、文字或输入焦点已变化，未执行动作；请按新观察重新选择。")
                controls = parsed["controls"]
            if self.device.focus() != current:
                raise self._recover("FOREGROUND_CHANGED", "核对控件期间前台已变化，未执行动作；请按新观察重新选择。")

            # Coordinates use the most specific actionable control at the point;
            # a clickable ancestor may cover unrelated controls on the page.
            guarded = _targets(controls, action, index, point if action == "tap-xy" else None)
            for control in guarded:
                if control.get("guard_password") or control.get("password"):
                    raise AwError("BLOCKED_SENSITIVE", "目标是密码类输入控件，不自动操作。")
                if action != "text" and SENSITIVE.search(control.get("guard_text", "")) and not confirm_sensitive:
                    raise AwError("BLOCKED_SENSITIVE", f"控件疑似购买/订阅/安装/试用：「{control['label'] or control['rid']}」。"
                                  "确需查看后续页面（如 Play 结算弹窗价格）时加 --confirm-sensitive；不会也不能代为完成支付。")

        # Invalidate before sending input: a timeout does not prove the input did not run.
        pending = {"id": "action-" + uuid.uuid4().hex[:16], "source_observation_id": observation_id,
                   "action": details, "requested_at": now_iso(), "outcome": "unknown"}
        self.ws.save_checkpoint({"package": self.package, "serial": self.device.adb.serial, "status": "pending_action",
                                 "last_observation_id": None, "pending_action": pending,
                                 "unresolved_actions": checkpoint.get("unresolved_actions", [])})
        try:
            if action in ("tap", "tap-xy"):
                self.device.tap(*point)
            elif action == "back":
                self.device.back()
            elif action == "swipe":
                self.device.swipe(*coords)
            else:
                self.device.text(value or "")
                if submit:
                    self.device.enter()
        except AwError as error:
            raise AwError("ACTION_UNCERTAIN", f"发送动作时出错：{error.message}", acted=True) from None
        self.sleep(self.post_action_wait)
        try:
            return self.observe(previous=observation_id, action=details)
        except AwError as error:
            error.acted = True
            if error.code not in ("NOT_TARGET_APP",):
                error.next_step = "observe"
            raise


def _brief_ads(dismissed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"kind": d.get("kind"), "pkg": d.get("package"), "by": d.get("by"), "shot": d.get("screenshot", "")}
            for d in dismissed]


def brief(observation: dict[str, Any], root, limit: int = 60) -> dict[str, Any]:
    """The default agent-facing payload: about 1-2 KB instead of the full UI tree."""
    from .ui import control_rows
    activity = observation["activity"]
    package = observation["package"]
    result: dict[str, Any] = {
        "obs": observation["id"], "status": observation["status"],
        "activity": activity[len(package):] if activity.startswith(package + ".") else activity,
        "view": str((root / observation["files"].get("view", observation["files"]["screenshot"])).resolve()),
        "screen": observation.get("screen")}
    if observation.get("auto_dismissed"):
        result["ads_closed"] = _brief_ads(observation["auto_dismissed"])
    if observation.get("unresolved_action"):
        result["unresolved_action"] = observation["unresolved_action"]["action"]
    if observation.get("ui_error"):
        result["ui_error"] = observation["ui_error"]
    controls = observation.get("controls", [])
    if controls:
        result["controls"] = control_rows(controls, limit)
        if len(controls) > limit:
            result["controls_more"] = len(controls) - limit
    return result
