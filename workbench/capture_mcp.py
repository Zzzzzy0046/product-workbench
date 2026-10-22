"""Restricted stdio MCP bridge for one server-created Android capture session."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

from workbench.capture_tools import CaptureTools


def create_server(session_dir: str | Path) -> FastMCP:
    tools = CaptureTools(session_dir)
    mcp = FastMCP("android-capture", instructions=(
        "只对当前会话固定的 Android 应用和设备执行按范围走查。先 capture_context，再 observe；"
        "需要启动时 launch_app。优先按返回的 controls 判断；页面身份、视觉、价格或广告信息不足时，"
        "用 view_observation 查看同一已保存观察的缩略图，不为看图重复 ADB；不盲点、不绕过输入前核验。"
        "Skill 会自动尝试安全关闭广告与外跳，只按 ads_closed 和已保存观察登记实际证据。"
        "系统权限、登录或购买阻塞且无法在当前范围继续时暂停。按模块登记真实相邻跳转和覆盖范围。"
        "预算用完停止动作、导出现有证据并 finish(paused)。最后必须 finish 写结构化结果。"
    ))

    def content(result, include_image=False):
        blocks = [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
        if include_image:
            png = tools.image_bytes(result)
            if png:
                blocks.append(ImageContent(type="image", data=base64.b64encode(png).decode("ascii"), mimeType=tools.image_mime(result)))
        return blocks

    @mcp.tool(structured_output=False)
    def capture_context():
        """Read fixed target, user scope, skill protocol, map, checkpoint and remaining budget. No device action."""
        return content(tools.context())

    @mcp.tool(structured_output=False)
    def launch_app(include_image: bool = False):
        """Launch only the confirmed package using monkey, then return compact controls. Optional saved image; no install/reset."""
        return content(tools.launch_app(), include_image)

    @mcp.tool(structured_output=False)
    def observe(include_image: bool = False):
        """Observe once, compact controls first. Read saved thumbnail with view_observation only when needed."""
        return content(tools.observe(), include_image)

    @mcp.tool(structured_output=False)
    def act_observe(observation_id: str, action: str, index: int | None = None, swipe: list[int] | None = None,
                    coordinates: list[int] | None = None, text: str | None = None, submit: bool = False, in_view: bool = False,
                    include_image: bool = False):
        """One fresh-bound tap/tap-xy/back/swipe/text; compact controls, optional saved image. No sensitive override or shell."""
        return content(tools.act_observe(observation_id, action, index, swipe, coordinates, text, submit, in_view), include_image)

    @mcp.tool(structured_output=False)
    def view_observation(observation_id: str):
        """Read only this session's already-saved observation thumbnail. No ADB, arbitrary paths, or new capture."""
        return content(tools.view_observation(observation_id), True)

    @mcp.tool(structured_output=False)
    def add_module(module_id: str, title: str):
        """Register an observed business module as pending. Existing identifiers cannot be overwritten."""
        return content(tools.add_module(module_id, title))

    @mcp.tool(structured_output=False)
    def add_page(page_id: str, module_id: str, title: str, kind: str = "page"):
        """Register a page/dialog under one primary module; reuse pages across states."""
        return content(tools.add_page(page_id, module_id, title, kind))

    @mcp.tool(structured_output=False)
    def attach_observation(observation_id: str, module_id: str, page_id: str, state_id: str, title: str):
        """Attach only an existing session observation to a new immutable page state. No arbitrary file paths."""
        return content(tools.attach_observation(observation_id, module_id, page_id, state_id, title))

    @mcp.tool(structured_output=False)
    def add_transition(transition_id: str, from_state: str, to_state: str):
        """Add an actual adjacent transition, deriving exact action and evidence from the saved target observation."""
        return content(tools.add_transition(transition_id, from_state, to_state))

    @mcp.tool(structured_output=False)
    def set_module_status(module_id: str, status: str, reason: str):
        """Set pending/partial/complete/blocked/skipped. Explain actual key-path coverage or the blocker; do not infer completion."""
        return content(tools.set_module_status(module_id, status, reason))

    @mcp.tool(structured_output=False)
    def export_flows():
        """Render current map to flow PNGs, map Markdown and deterministic review; return only this export's PNG manifest."""
        return content(tools.export_flows())

    @mcp.tool(structured_output=False)
    def finish(outcome: str, summary: str, reason: str = ""):
        """Finish completed/paused/blocked, export evidence and save agent-result.json. Incomplete evidence cannot be completed."""
        return content(tools.finish(outcome, summary, reason))

    return mcp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="Server-created session directory containing request.json")
    args = parser.parse_args()
    create_server(args.session).run(transport="stdio")


if __name__ == "__main__":
    main()
