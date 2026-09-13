from __future__ import annotations

import argparse
from dataclasses import replace
import json
import sys

from .config import ConfigError, load_settings
from .notion import NotionClient
from .sync import SyncCoordinator
from .weread import WeReadClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步微信读书数据到 Notion")
    parser.add_argument("--config", default="config/local.toml", help="TOML 配置文件路径")
    parser.add_argument("--mode", choices=("full", "incremental"), help="覆盖配置中的同步模式")
    parser.add_argument("--json", action="store_true", help="只输出 JSON 同步结果")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.mode:
            settings = replace(settings, sync_mode=args.mode)
        source = WeReadClient(settings)
        notion = NotionClient(
            settings.notion_token,
            api_url=settings.notion_api_url,
            api_version=settings.notion_api_version,
            parent_page_id=settings.notion_parent_page_id,
        )
        result = SyncCoordinator(source, notion, mode=settings.sync_mode).run()
    except ConfigError as exc:
        return _report_error(str(exc), args.json)
    except Exception as exc:
        return _report_error(f"启动同步失败: {exc}", args.json)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_human_summary(result.to_dict()))
        if result.errors:
            for error in result.errors:
                print(f"错误: {error}", file=sys.stderr)
    return 0 if result.status == "succeeded" else 1


def _report_error(message: str, json_only: bool) -> int:
    if json_only:
        print(json.dumps({"status": "failed", "errors": [message]}, ensure_ascii=False))
    else:
        print(message, file=sys.stderr)
    return 2


def _human_summary(payload: dict[str, object]) -> str:
    counts = payload.get("counts", {})
    return (
        f"同步{('成功' if payload.get('status') == 'succeeded' else '失败')} "
        f"created={counts.get('created', 0)} "
        f"updated={counts.get('updated', 0)} "
        f"unchanged={counts.get('unchanged', 0)} "
        f"marked_deleted={counts.get('marked_deleted', 0)} "
        f"failed={counts.get('failed', 0)}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
