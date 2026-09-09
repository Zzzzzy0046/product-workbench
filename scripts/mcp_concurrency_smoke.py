from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / ".venv" / "Scripts" / "product-kb-mcp.exe"


async def worker(worker_id: int) -> dict[str, object]:
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
            result = await session.call_tool(
                "kb_trace", arguments={"source_id": "case-pdf-reader-product-boundary"}
            )
            if result.isError:
                raise AssertionError(f"worker {worker_id} failed: {result.content}")
            text = "\n".join(getattr(item, "text", "") for item in result.content)
            payload = json.loads(text)
            if not payload.get("found"):
                raise AssertionError(f"worker {worker_id} could not trace the case")
            return {"worker": worker_id, "found": True}


async def run() -> dict[str, object]:
    workers = await asyncio.gather(*(worker(worker_id) for worker_id in range(3)))
    return {"parallel_processes": len(workers), "all_passed": True, "workers": workers}


def main() -> None:
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
