from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class NormalizedRecord:
    database: str
    source_type: str
    source_id: str
    title: str
    fields: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""

    def with_fingerprint(self) -> "NormalizedRecord":
        if self.fingerprint:
            return self
        value = json.dumps(
            {"database": self.database, "source_id": self.source_id, "fields": self.fields},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return NormalizedRecord(
            database=self.database,
            source_type=self.source_type,
            source_id=self.source_id,
            title=self.title,
            fields=self.fields,
            fingerprint=sha256(value.encode("utf-8")).hexdigest(),
        )


@dataclass
class SyncResult:
    status: str = "idle"
    mode: str = "full"
    started_at: str | None = None
    finished_at: str | None = None
    counts: dict[str, int] = field(default_factory=lambda: {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "marked_deleted": 0,
        "failed": 0,
    })
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    databases: dict[str, str] = field(default_factory=dict)

    def add_action(self, action: str, record: NormalizedRecord) -> None:
        self.counts[action] = self.counts.get(action, 0) + 1
        if len(self.records) < 200:
            self.records.append({
                "database": record.database,
                "source_type": record.source_type,
                "source_id": record.source_id,
                "title": record.title,
                "action": action,
                "fields": record.fields,
            })

    def add_error(self, message: str, record: NormalizedRecord | None = None) -> None:
        self.counts["failed"] += 1
        if record:
            self.records.append({
                "database": record.database,
                "source_id": record.source_id,
                "title": record.title,
                "action": "failed",
                "error": message,
            })
        self.errors.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "counts": self.counts,
            "records": self.records,
            "errors": self.errors,
            "databases": self.databases,
        }


def source_id(source_type: str, value: Any) -> str:
    return f"{source_type}:{value}"


def iso_date(timestamp: Any, timezone_name: str = "Asia/Shanghai") -> str | None:
    if timestamp in (None, "", 0, "0"):
        return None
    try:
        value = float(timestamp)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(ZoneInfo(timezone_name)).date().isoformat()


def iso_datetime(timestamp: Any, timezone_name: str = "Asia/Shanghai") -> str | None:
    if timestamp in (None, "", 0, "0"):
        return None
    try:
        value = float(timestamp)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(ZoneInfo(timezone_name)).isoformat()


def format_duration(seconds: Any) -> str:
    total = max(0, int(float(seconds or 0)))
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"
