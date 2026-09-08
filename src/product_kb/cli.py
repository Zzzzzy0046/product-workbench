from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .index import HybridIndex
from .sources import discover_sources


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _parse_filters(items: list[str]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid filter `{item}`; use key=value.")
        key, value = item.split("=", 1)
        filters.setdefault(key, []).append(value)
    return filters


def _settings(args: argparse.Namespace) -> Settings:
    return Settings.load(Path(args.root))


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = _settings(args)
    errors: list[str] = []
    try:
        sources = discover_sources(settings)
    except Exception as exc:
        sources = []
        errors.append(str(exc))
    missing = [str(source.path) for source in sources if source.enabled and not source.path.is_file()]
    _print(
        {
            "root": str(settings.root),
            "knowledge_dir_exists": settings.knowledge_dir.is_dir(),
            "source_config_exists": settings.source_config.is_file(),
            "discovered_sources": len(sources),
            "missing_sources": missing,
            "dense_model": settings.dense_model,
            "sparse_model": settings.sparse_model,
            "errors": errors,
            "ok": not missing and not errors,
        }
    )
    return 0 if not missing and not errors else 1


def cmd_index(args: argparse.Namespace) -> int:
    index = HybridIndex(_settings(args))
    try:
        report = index.build(reset=args.reset)
        _print(report)
        return 0 if not report["errors"] else 2
    finally:
        index.close()


def cmd_search(args: argparse.Namespace) -> int:
    index = HybridIndex(_settings(args))
    try:
        results = index.search(args.query, args.top_k, _parse_filters(args.filter))
        _print(results)
        return 0
    finally:
        index.close()


def cmd_get(args: argparse.Namespace) -> int:
    index = HybridIndex(_settings(args))
    try:
        result = index.get_chunk(args.chunk_id)
        _print(result or {"found": False, "chunk_id": args.chunk_id})
        return 0 if result else 1
    finally:
        index.close()


def cmd_trace(args: argparse.Namespace) -> int:
    index = HybridIndex(_settings(args))
    try:
        result = index.trace_source(args.source_id)
        _print(result)
        return 0 if result.get("found") else 1
    finally:
        index.close()


def cmd_eval(args: argparse.Namespace) -> int:
    settings = _settings(args)
    eval_path = settings.root / "evals" / "questions.yaml"
    cases = yaml.safe_load(eval_path.read_text(encoding="utf-8-sig"))["questions"]
    index = HybridIndex(settings)
    rows: list[dict[str, Any]] = []
    try:
        for case in cases:
            results = index.search(case["query"], case.get("top_k", 5), case.get("filters"))
            returned = [result["source_id"] for result in results]
            expected = case["expected_sources"]
            matched = [source_id for source_id in expected if source_id in returned]
            rows.append(
                {
                    "id": case["id"],
                    "pass": bool(matched),
                    "matched": matched,
                    "expected": expected,
                    "returned": returned,
                }
            )
    finally:
        index.close()
    passed = sum(1 for row in rows if row["pass"])
    report = {
        "passed": passed,
        "total": len(rows),
        "pass_rate": round(passed / len(rows), 4) if rows else 0,
        "cases": rows,
    }
    _print(report)
    return 0 if passed == len(rows) else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="product-kb")
    parser.add_argument("--root", default=str(Path.cwd()), help="Product KB project root")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Validate configuration and source paths")
    doctor.set_defaults(func=cmd_doctor)

    index = sub.add_parser("index", help="Build or incrementally update the hybrid index")
    index.add_argument("--reset", action="store_true")
    index.set_defaults(func=cmd_index)

    search = sub.add_parser("search", help="Search active knowledge")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=8)
    search.add_argument("--filter", action="append", default=[])
    search.set_defaults(func=cmd_search)

    get = sub.add_parser("get", help="Get one indexed chunk")
    get.add_argument("chunk_id")
    get.set_defaults(func=cmd_get)

    trace = sub.add_parser("trace", help="Trace an indexed source and its chunks")
    trace.add_argument("source_id")
    trace.set_defaults(func=cmd_trace)

    evaluate = sub.add_parser("eval", help="Run retrieval regression cases")
    evaluate.set_defaults(func=cmd_eval)
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = args.func(args)
    except Exception as exc:
        _print({"error": str(exc), "type": type(exc).__name__})
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
