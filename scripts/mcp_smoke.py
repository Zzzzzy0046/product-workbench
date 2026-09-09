from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / ".venv" / "Scripts" / "product-kb-mcp.exe"


async def run() -> dict[str, object]:
    params = StdioServerParameters(
        command=str(SERVER),
        args=[],
        env={
            **os.environ,
            "PRODUCT_KB_ROOT": str(ROOT),
            "PYTHONUTF8": "1",
        },
    )
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tool_result = await session.list_tools()
            tool_names = sorted(tool.name for tool in tool_result.tools)
            expected = ["kb_find_similar_cases", "kb_get", "kb_search", "kb_trace"]
            if tool_names != expected:
                raise AssertionError(f"Unexpected MCP tools: {tool_names}")

            result = await session.call_tool(
                "kb_search",
                arguments={"query": "Heart Rate 新品模板的核心写法", "top_k": 3},
            )
            if result.isError:
                raise AssertionError(f"kb_search returned an error: {result.content}")
            serialised = "\n".join(getattr(item, "text", "") for item in result.content)
            if "case-heart-rate-template-evolution" not in serialised:
                raise AssertionError(f"Expected Heart Rate case was not returned: {serialised[:500]}")

            case_result = await session.call_tool(
                "kb_find_similar_cases",
                arguments={"query": "Reader-first PDF 文件打开和继续阅读", "top_k": 5},
            )
            if case_result.isError:
                raise AssertionError(
                    f"kb_find_similar_cases returned an error: {case_result.content}"
                )
            structured = getattr(case_result, "structuredContent", None) or getattr(
                case_result, "structured_content", None
            )
            cases = structured.get("result") if isinstance(structured, dict) else None
            case_text = "\n".join(getattr(item, "text", "") for item in case_result.content)
            if not isinstance(cases, list):
                cases = []
                for item in case_result.content:
                    item_text = getattr(item, "text", "")
                    if not item_text:
                        continue
                    try:
                        decoded = json.loads(item_text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(decoded, list):
                        cases.extend(decoded)
                    elif isinstance(decoded, dict):
                        cases.append(decoded)
            if not cases or any(item.get("type") != "case" for item in cases):
                returned_types = [item.get("type") for item in cases]
                raise AssertionError(
                    f"Non-case result returned; types={returned_types}: {case_text[:1000]}"
                )

            return {
                "tools": tool_names,
                "search_hit": "case-heart-rate-template-evolution",
                "similar_cases_only": True,
                "similar_case_count": len(cases),
            }


def main() -> None:
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
