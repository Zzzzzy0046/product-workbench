"""Real stdio initialize/list/context handshake, without Codex, ADB, or models."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from pathlib import Path
import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_real_capture_mcp_stdio_initialize_list_and_context_only(tmp_path):
    root = Path(__file__).resolve().parents[1]
    request = {"adb_path": str(tmp_path / "ADB-MUST-NEVER-RUN.exe"), "serial": "SYNTHETIC-NO-DEVICE",
               "package": "test.handshake.app", "title": "合成握手", "scope": "只验证协议握手，不读取设备。",
               "app_version": {"name": "synthetic", "code": "0"}, "attempt_id": "handshake-only",
               "max_actions": 1, "budget_seconds": 30}
    (tmp_path / "request.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", str(root / "workbench/capture_mcp.py"), "--session", str(tmp_path)],
        cwd=str(tmp_path),
        env={"CODEX_HOME": str(tmp_path / "empty-codex-home"), "PYTHONUTF8": "1"},
    )

    async def handshake():
        with anyio.fail_after(25):
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "android-capture"
                    listing = await session.list_tools()
                    names = {tool.name for tool in listing.tools}
                    assert names == {"capture_context", "launch_app", "observe", "act_observe", "add_module", "add_page",
                                     "attach_observation", "add_transition", "set_module_status", "export_flows", "finish", "view_observation"}
                    response = await session.call_tool("capture_context", {})
                    assert not response.isError
                    assert [block.type for block in response.content] == ["text"]
                    context = json.loads(response.content[0].text)
                    assert context["ok"] and context["target"]["package"] == request["package"]
                    assert context["target"]["app_version"] == request["app_version"]
                    assert context["skill_source"] == "bundled"
                    assert context["backend"] == "android-walkthrough"
                    assert context["actions_used"] == 0 and context["map"]["observations"] == []
                    assert "SKILL.md" in context["protocol"]
                    assert "adb_path" not in context["target"]

    asyncio.run(handshake())
    assert not (tmp_path / "observations").exists()
    assert not (tmp_path / "capture-session.json").exists()
    assert not (tmp_path / "agent-result.json").exists()
    events = [json.loads(line) for line in (tmp_path / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {event["tool"] for event in events} == {"capture_context"}
    assert all(event["actions_used"] == 0 for event in events)
