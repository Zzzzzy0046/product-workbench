"""Single entry point. Every command prints one JSON object on stdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

from . import PROTOCOL, VERSION
from .adb import Adb, find_adb, list_devices
from .device import Device
from .doctor import run_doctor, valid_package
from .errors import AwError
from . import mapstore
from .session import Session, brief
from .workspace import Workspace, device_lock, now_iso

ANIMATION_KEYS = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AwError("BAD_ARGS", message)


def _parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="aw", description="Android walkthrough capture (JSON in, JSON out)")
    parser.add_argument("--version", action="version", version=f"android-walkthrough {VERSION}")
    parser.add_argument("--ascii", action="store_true", help="ASCII-escaped JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    out = argparse.ArgumentParser(add_help=False)
    out.add_argument("--out", required=True, help="采集目录（每个 App+设备一个）")
    capture = argparse.ArgumentParser(add_help=False)
    capture.add_argument("--full", action="store_true", help="输出完整观察（默认精简）")
    capture.add_argument("--limit", type=int, default=60, help="精简输出最多列出的控件数")
    capture.add_argument("--no-auto-dismiss", action="store_true", help="不自动关闭广告/外跳")
    capture.add_argument("--return-pkg", action="append", default=[], help="额外允许自动返回的外部包名")
    capture.add_argument("--settle", type=float, default=8, help="出现加载转圈时最多等待秒数")
    capture.add_argument("--dump-timeout", type=float, default=7, help="单次 UI dump 超时秒数")
    capture.add_argument("--as", dest="as_state", help="登记为状态 id（或 auto）")
    capture.add_argument("--page", help="状态所属页面 id（配合 --as）")
    capture.add_argument("--title", default="", help="状态标题（配合 --as）")
    capture.add_argument("--label", default="", help="箭头显示文字（配合 --as，默认由动作生成）")

    doctor = sub.add_parser("doctor", help="环境自检")
    doctor.add_argument("--adb")
    doctor.add_argument("--serial")
    doctor.add_argument("--package")

    init = sub.add_parser("init", parents=[out], help="初始化采集目录")
    init.add_argument("--package", required=True)
    init.add_argument("--serial")
    init.add_argument("--adb")

    launch = sub.add_parser("launch", parents=[out, capture], help="启动目标 App 并观察")
    launch.add_argument("--wait", type=float, default=3)
    sub.add_parser("observe", parents=[out, capture], help="观察当前页")

    act = sub.add_parser("act", parents=[out, capture], help="执行一个动作并观察")
    act.add_argument("--obs", required=True, help="最新观察 id")
    act.add_argument("action", choices=("tap", "tap-xy", "back", "swipe", "text"))
    act.add_argument("params", nargs="*", help="tap N | tap-xy X Y | swipe X1 Y1 X2 Y2 | text VALUE")
    act.add_argument("--submit", action="store_true", help="text 之后按回车")
    act.add_argument("--view", action="store_true", help="tap-xy/swipe 坐标取自缩略图 view，自动换算为设备像素")
    act.add_argument("--confirm-sensitive", action="store_true", help="允许点击疑似购买/订阅控件（仍不会代为支付）")
    act.add_argument("--fresh", type=float, default=8, help="兼容旧调用的参数；tap/text/坐标点击始终重新核对当前控件")
    act.add_argument("--wait", type=float, default=0.5, help="动作后等待秒数再观察")

    mapper = sub.add_parser("map", parents=[out], help="维护模块/页面/状态/跳转")
    msub = mapper.add_subparsers(dest="map_command", required=True)
    module = msub.add_parser("module")
    module.add_argument("--id", required=True)
    module.add_argument("--title", required=True)
    page = msub.add_parser("page")
    page.add_argument("--id", required=True)
    page.add_argument("--module", required=True)
    page.add_argument("--title", required=True)
    page.add_argument("--kind", default="page", help="page / dialog / sheet / external")
    status = msub.add_parser("status")
    status.add_argument("--module", required=True)
    status.add_argument("--status", required=True, choices=sorted(mapstore.STATUSES))
    status.add_argument("--reason", default="")
    state = msub.add_parser("state", help="把已有观察登记为状态")
    state.add_argument("--obs", required=True)
    state.add_argument("--as", dest="as_state", required=True)
    state.add_argument("--page", required=True)
    state.add_argument("--title", default="")
    state.add_argument("--label", default="")
    edge = msub.add_parser("edge", help="手动连接两个相邻状态（动作取自记录）")
    edge.add_argument("--from", dest="source", required=True)
    edge.add_argument("--to", dest="target", required=True)
    edge.add_argument("--label", default="")
    msub.add_parser("show", help="紧凑查看当前地图")

    build = sub.add_parser("build", parents=[out], help="校验 + app-map.md + 流程拼图 + 交付检查")
    build.add_argument("--title", default="Android App")
    build.add_argument("--rows", type=int, default=4)

    docx = sub.add_parser("export-docx", parents=[out], help="把 product_summary.md 导出为 Word（可选）")
    docx.add_argument("--input-md")
    docx.add_argument("--mode", choices=("compact", "full"), default="compact")

    anim = sub.add_parser("anim", parents=[out], help="临时关闭/恢复系统动画（会修改设备设置）")
    anim.add_argument("mode", choices=("off", "restore"))
    return parser


# ---------------------------------------------------------------- helpers

def _device(ws: Workspace, config: dict[str, Any]) -> tuple[Adb, Device]:
    adb = Adb(config["adb"], config["serial"])
    return adb, Device(adb, config["package"], config.setdefault("cache", {}))


def _session(ws: Workspace, config: dict[str, Any], args: argparse.Namespace) -> Session:
    _, device = _device(ws, config)
    return Session(ws, device, settle_timeout=args.settle, dump_timeout=args.dump_timeout,
                   fresh_seconds=getattr(args, "fresh", 8), post_action_wait=getattr(args, "wait", 0.5)
                   if args.command == "act" else 0.5, auto_dismiss=not args.no_auto_dismiss,
                   extra_return=set(args.return_pkg))


def _payload(observation: dict[str, Any], ws: Workspace, args: argparse.Namespace) -> dict[str, Any]:
    if args.full:
        return {k: v for k, v in observation.items() if k != "guards"}
    return brief(observation, ws.root, max(1, args.limit))


def _attach(ws: Workspace, observation: dict[str, Any], state_id: str, page_id: str | None, title: str,
            label: str) -> dict[str, Any]:
    if not page_id:
        return {"map_error": "--as 需要同时给 --page"}
    try:
        data = mapstore.load_map(ws.map_path)
        if state_id == "auto":
            state_id = mapstore.next_id(data, "states", "S")
        mapstore.attach(data, observation, page_id, state_id, title, ws.root)
        edge = mapstore.auto_edge(data, state_id, label)
        mapstore.save_map(ws.map_path, data)
    except (mapstore.MapError, OSError, json.JSONDecodeError) as error:
        return {"map_error": str(error)}
    result: dict[str, Any] = {"state": state_id, "edge": edge}
    if edge is None and observation.get("previous_observation_id"):
        result["edge_note"] = "上一步观察未登记为状态，未连箭头"
    return result


def _init(args: argparse.Namespace, ws: Workspace) -> dict[str, Any]:
    if not valid_package(args.package):
        raise AwError("BAD_ARGS", "包名格式无效。")
    if ws.initialized:
        config = ws.config()
        if config["package"] != args.package or (args.serial and args.serial != config["serial"]):
            raise AwError("WORKSPACE_MISMATCH", "该目录已属于其他包名或设备，请换一个 --out。")
        return {"ok": True, "existing": True, "config": config}
    executable = find_adb(args.adb)
    ready = [d for d in list_devices(Adb(executable)) if d["state"] == "device"]
    if args.serial:
        if not any(d["serial"] == args.serial for d in ready):
            raise AwError("DEVICE_NOT_FOUND", f"设备 {args.serial} 不在线。", devices=ready)
        serial = args.serial
    elif len(ready) == 1:
        serial = ready[0]["serial"]
    elif not ready:
        raise AwError("DEVICE_NOT_FOUND", "没有在线设备：连接手机并开启 USB 调试。")
    else:
        raise AwError("DEVICE_AMBIGUOUS", "多台设备在线，请用 --serial 指定。", devices=ready)
    adb = Adb(executable, serial)
    if not adb.shell(f"pm path {args.package}", "pm", ok_codes=(0, 1)).strip():
        raise AwError("PACKAGE_NOT_INSTALLED", f"{serial} 上未安装 {args.package}。")
    version = adb.shell(f"dumpsys package {args.package} | grep -m1 versionName", "version",
                        ok_codes=(0, 1)).decode("utf-8", "replace").strip().replace("versionName=", "")
    model = adb.shell("getprop ro.product.model", "model").decode("utf-8", "replace").strip()
    home = adb.shell("cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME",
                     "launcher", ok_codes=(0, 1, 255)).decode("utf-8", "replace").strip().splitlines()
    launcher = home[-1].split("/", 1)[0] if home and "/" in home[-1] else ""
    config = {"v": PROTOCOL, "package": args.package, "serial": serial, "adb": executable, "model": model,
              "app_version": version, "created_at": now_iso(), "cache": {"launcher": launcher} if launcher else {}}
    ws.save_config(config)
    if not ws.map_path.is_file():
        mapstore.save_map(ws.map_path, mapstore.create_map(args.package, serial))
    return {"ok": True, "config": config, "next": "launch 或 observe"}


def _anim(args: argparse.Namespace, ws: Workspace, config: dict[str, Any]) -> dict[str, Any]:
    adb, _ = _device(ws, config)
    if args.mode == "off":
        original = config.get("anim_original") or {
            key: adb.shell(f"settings get global {key}", "settings").decode().strip() for key in ANIMATION_KEYS}
        config["anim_original"] = original
        ws.save_config(config)
        for key in ANIMATION_KEYS:
            adb.shell(f"settings put global {key} 0", "settings")
        return {"ok": True, "animations": "off", "original": original,
                "note": "采集结束后务必运行 aw anim restore --out <目录>"}
    original = config.get("anim_original") or {}
    if not original:
        return {"ok": True, "animations": "restored", "values": {}, "changed": False,
                "note": "没有待恢复的动画备份，设备设置保持不变。"}
    for key in ANIMATION_KEYS:
        value = original.get(key, "1")
        value = value if value not in ("", "null") and value.replace(".", "", 1).isdigit() else "1"
        adb.shell(f"settings put global {key} {value}", "settings")
    config.pop("anim_original", None)
    ws.save_config(config)
    return {"ok": True, "animations": "restored", "values": original, "changed": True}


def _map(args: argparse.Namespace, ws: Workspace) -> dict[str, Any]:
    data = mapstore.load_map(ws.map_path)
    command, result = args.map_command, {"ok": True}
    if command == "show":
        observations = {o["id"]: o for o in data["observations"]}
        return {"ok": True, "modules": [[m["id"], m["title"], m["status"]] for m in data["modules"]],
                "pages": [[p["id"], p["module_id"], p["title"]] for p in data["pages"]],
                "states": [[s["id"], s["page_id"], s["title"], s["observation_id"]] for s in data["states"]],
                "transitions": [[t["id"], t["from_state"], t["to_state"], t.get("label") or mapstore.action_label(t["action"])]
                                for t in data["transitions"]],
                "last_observation": ws.checkpoint().get("last_observation_id"),
                "observations": len(observations)}
    if command == "module":
        mapstore.add_module(data, args.id, args.title)
    elif command == "page":
        mapstore.add_page(data, args.id, args.module, args.title, args.kind)
    elif command == "status":
        mapstore.set_status(data, args.module, args.status, args.reason)
    elif command == "state":
        observation = ws.observation(args.obs)
        state_id = mapstore.next_id(data, "states", "S") if args.as_state == "auto" else args.as_state
        mapstore.attach(data, observation, args.page, state_id, args.title, ws.root)
        result.update(state=state_id, edge=mapstore.auto_edge(data, state_id, args.label))
    elif command == "edge":
        transition_id = mapstore.next_id(data, "transitions", "T")
        mapstore.add_transition(data, transition_id, args.source, args.target, args.label)
        result["edge"] = transition_id
    mapstore.save_map(ws.map_path, data)
    return result


def _build(args: argparse.Namespace, ws: Workspace) -> dict[str, Any]:
    from .montage import build_montages
    from .review import review
    data = mapstore.load_map(ws.map_path)
    mapstore.atomic_text(ws.root / "app-map.md", mapstore.render_markdown(data))
    outputs = build_montages(ws.root, args.title, args.rows)
    report = review(ws.root)
    return {"ok": report["status"] == "PASS", "review": report["status"], "issues": report["issues"],
            "warnings": report["warnings"][:10], "flow_pngs": [str(o["path"]) for o in outputs],
            "app_map": str(ws.root / "app-map.md"), "report": report["report"]}


def _capture(args: argparse.Namespace, ws: Workspace, config: dict[str, Any], phases: list) -> dict[str, Any]:
    session = _session(ws, config, args)
    try:
        return _run_capture(args, ws, session)
    finally:
        phases.extend(session.device.adb.timings)


def _run_capture(args: argparse.Namespace, ws: Workspace, session: Session) -> dict[str, Any]:
    if args.command == "launch":
        session.device.launch()
        session.sleep(max(0.0, args.wait))
        observation = session.observe()
    elif args.command == "observe":
        observation = session.observe()
    else:
        params, coords, index, value = args.params, None, None, None
        try:
            if args.action == "tap":
                index = int(params[0])
            elif args.action in ("tap-xy", "swipe"):
                coords = [int(v) for v in params]
            elif args.action == "text":
                value = " ".join(params)
        except (IndexError, ValueError):
            raise AwError("BAD_ARGS", "动作参数无效：tap N | tap-xy X Y | swipe X1 Y1 X2 Y2 | text VALUE") from None
        observation = session.act(args.obs, args.action, index=index, coords=coords, value=value,
                                  submit=args.submit, confirm_sensitive=args.confirm_sensitive, in_view=args.view)
    result = {"ok": True, **_payload(observation, ws, args)}
    if args.as_state:
        result.update(_attach(ws, observation, args.as_state, args.page, args.title, args.label))
    return result


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    started, phases, ok = time.monotonic(), [], False
    args, ws = None, None
    ascii_output = "--ascii" in (sys.argv[1:] if argv is None else argv)
    try:
        args = _parser().parse_args(argv)
        ws = Workspace(args.out) if hasattr(args, "out") else None
        if args.command == "doctor":
            if args.package and not valid_package(args.package):
                raise AwError("BAD_ARGS", "包名格式无效。")
            result = run_doctor(args.adb, args.serial, args.package)
        elif args.command == "init":
            result = _init(args, ws)
        elif args.command == "map":
            result = _map(args, ws)
        elif args.command == "build":
            result = _build(args, ws)
        elif args.command == "export-docx":
            from .docx_export import export_docx
            source = Path(args.input_md) if args.input_md else ws.root / "product_summary.md"
            if not source.is_file():
                raise AwError("BAD_ARGS", f"找不到 {source}")
            images, missing = export_docx(source.resolve(), source.with_suffix(".docx").resolve(), 4, args.mode, 3)
            result = {"ok": not missing, "docx": str(source.with_suffix(".docx")), "images": images, "missing": missing}
        else:
            config = ws.config()
            with device_lock(config["serial"]):
                if args.command == "anim":
                    result = _anim(args, ws, config)
                else:
                    try:
                        result = _capture(args, ws, config, phases)
                    finally:
                        ws.save_config(config)  # persists the learned focus command

        ok = bool(result.get("ok", True))
        output = {"v": PROTOCOL, **result}
    except AwError as error:
        output = error.to_json()
        observation = error.extra.get("observation")
        if observation is not None and ws is not None:
            output["observation"] = _payload(observation, ws, args)
    except mapstore.MapError as error:
        output = AwError("MAP_ERROR", str(error)).to_json()
    except (OSError, ValueError) as error:
        output = AwError("BAD_ARGS", f"{type(error).__name__}: {error}").to_json()
    print(json.dumps(output, ensure_ascii=ascii_output, separators=(",", ":")))
    if ws is not None and args is not None and args.command in ("launch", "observe", "act"):
        ws.log_timing(args.command, ok, time.monotonic() - started, phases)
    return 0 if ok else 1
