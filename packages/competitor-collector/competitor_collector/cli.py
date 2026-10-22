"""Small portable launcher; web server and accounts are imported only on demand."""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def default_data_dir() -> Path:
    """Portable folder-local data, independent of the terminal's current folder."""
    return Path(__file__).resolve().parents[1] / "data"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="competitor-collector", description="独立竞品资料采集工具")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="启动本机独立页面")
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    serve.add_argument("--data-dir", type=Path, default=None)
    serve.add_argument("--open", action="store_true", dest="open_browser")
    for name, help_text in (("init-admin", "首次创建管理员"), ("recover-admin", "本机恢复管理员密码")):
        account = commands.add_parser(name, help=help_text)
        account.add_argument("--username")
        account.add_argument("--data-dir", type=Path, default=None)
    collect = commands.add_parser("collect", help="按指定商店链接或应用 ID 采集，不自动搜索")
    collect.add_argument("--app", action="append", required=True)
    collect.add_argument("--countries", nargs="+", default=["us"])
    collect.add_argument("--count", type=int, default=100)
    collect.add_argument("--sort", choices=("newest", "relevant"), default="newest")
    collect.add_argument("--out", type=Path, required=True)
    collect.add_argument("--date-from", default="")
    collect.add_argument("--date-to", default="")
    collect.add_argument("--no-reviews", action="store_true")
    collect.add_argument("--no-listing", action="store_true")
    collect.add_argument("--no-screenshots", action="store_true")
    collect.add_argument("--translate", choices=("google", "openai"), default=None)
    return parser


def _account(args) -> int:
    from competitor_collector.auth import AuthStore

    username = str(args.username or input("管理员用户名：")).strip()
    password = getpass.getpass("新密码：")
    repeated = getpass.getpass("再次输入新密码：")
    if password != repeated:
        raise ValueError("两次输入的密码不一致，未修改账号。")
    store = AuthStore((args.data_dir or default_data_dir()).resolve() / "auth.sqlite3")
    if args.command == "init-admin":
        store.bootstrap_admin(username, password)
        print("管理员已创建。密码不会写入命令行参数或导出文件。")
    else:
        store.recover_admin(username, password)
        print("管理员密码已恢复。")
    return 0


def _collect(args) -> int:
    from competitor_collector.engine import collect, _safe_exception_message
    from competitor_collector.exports import write_evidence
    from competitor_collector.request_spec import normalize_request

    request = normalize_request({
        "entries": args.app, "countries": args.countries, "count_per_country": args.count,
        "sort": args.sort, "date_from": args.date_from, "date_to": args.date_to,
        "collect_reviews": not args.no_reviews, "collect_listing": not args.no_listing,
        "download_screenshots": not args.no_screenshots,
        "translate": args.translate is not None, "translation_provider": args.translate,
    })
    output = args.out.expanduser().resolve() / f"collection-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for index, entry in enumerate(request["entries"], 1):
        directory = output / f"{index:02d}-{entry['platform']}-{entry['app_id']}"
        directory.mkdir()
        item_request = {key: value for key, value in request.items() if key != "entries"}
        item_request.update(entry)
        item_request["output_dir"] = str(directory / "screenshots")
        try:
            result = collect(item_request)
        except Exception as error:
            result = {"listing": None, "reviews": [], "warnings": [_safe_exception_message(error)]}
        summary = write_evidence(directory, result, item_request)
        summary["directory"] = str(directory)
        summaries.append(summary)
    payload = {"directory": str(output), "items": summaries}
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if any(item["status"] in {"completed", "partial"} for item in summaries) else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "serve":
            from competitor_collector.server import serve

            serve(data_dir=(args.data_dir or default_data_dir()).resolve(), host=args.host,
                  port=args.port, open_browser=args.open_browser)
            return 0
        if args.command in {"init-admin", "recover-admin"}:
            return _account(args)
        return _collect(args)
    except KeyboardInterrupt:
        print("已停止。", file=sys.stderr)
        return 130
    except Exception as error:
        # CLI argument/account errors are deliberate safe messages. Never print
        # third-party transport details, traceback, API settings or passwords.
        if isinstance(error, ValueError) and all(marker not in str(error) for marker in ("://", "api_key", "password=", "token=")):
            message = str(error)[:300]
        else:
            from competitor_collector.auth import AuthError
            message = str(error) if isinstance(error, AuthError) else f"执行失败：{type(error).__name__}。"
        print(message, file=sys.stderr)
        return 1
