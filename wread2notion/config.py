from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(ValueError):
    """Raised when the local synchronization configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    weread_api_key: str
    notion_token: str
    notion_parent_page_id: str
    sync_mode: str = "full"
    schedule_mode: str = "daily"
    timezone: str = "Asia/Shanghai"
    weread_gateway_url: str = "https://i.weread.qq.com/api/agent/gateway"
    notion_api_url: str = "https://api.notion.com/v1"
    notion_api_version: str = "2022-06-28"
    reading_start_year: int | None = None


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"配置文件不存在: {config_path}")
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"配置文件格式错误: {exc}") from exc

    required = ("weread_api_key", "notion_token", "notion_parent_page_id")
    missing = [name for name in required if not str(raw.get(name, "")).strip()]
    if missing:
        raise ConfigError(f"缺少必要配置: {', '.join(missing)}")

    settings = Settings(
        weread_api_key=str(raw["weread_api_key"]).strip(),
        notion_token=str(raw["notion_token"]).strip(),
        notion_parent_page_id=str(raw["notion_parent_page_id"]).strip(),
        sync_mode=str(raw.get("sync_mode", "full")),
        schedule_mode=str(raw.get("schedule_mode", "daily")),
        timezone=str(raw.get("timezone", "Asia/Shanghai")),
        weread_gateway_url=str(raw.get("weread_gateway_url", Settings.weread_gateway_url)),
        notion_api_url=str(raw.get("notion_api_url", Settings.notion_api_url)),
        notion_api_version=str(raw.get("notion_api_version", Settings.notion_api_version)),
        reading_start_year=_optional_int(raw.get("reading_start_year")),
    )
    _validate_settings(settings)
    return settings


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("reading_start_year 必须是整数") from exc


def _validate_settings(settings: Settings) -> None:
    if settings.sync_mode not in {"full", "incremental"}:
        raise ConfigError("sync_mode 必须是 full 或 incremental")
    if settings.schedule_mode not in {"frequent", "daily"}:
        raise ConfigError("schedule_mode 必须是 frequent 或 daily")
    if settings.reading_start_year is not None and not 2000 <= settings.reading_start_year <= 2100:
        raise ConfigError("reading_start_year 必须在 2000 到 2100 之间")
    try:
        ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError("timezone 不是有效的 IANA 时区") from exc
