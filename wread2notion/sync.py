from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Protocol

from .domain import NormalizedRecord, SyncResult


class SourceClient(Protocol):
    def fetch_records(self, mode: str) -> list[NormalizedRecord]: ...


class NotionClient(Protocol):
    def ensure_databases(self, parent_page_id: str | None = None) -> dict[str, str]: ...

    def upsert(
        self,
        item: NormalizedRecord,
        database_ids: dict[str, str],
        book_page_ids: dict[str, str],
    ) -> tuple[str, str]: ...

    def list_source_pages(self, database: str) -> list[dict[str, Any]]: ...

    def mark_deleted(self, page: dict[str, Any], database: str) -> None: ...


class SyncCoordinator:
    """The single public seam for local and scheduled synchronization."""

    def __init__(self, source: SourceClient, notion: NotionClient, mode: str = "full"):
        if mode not in {"full", "incremental"}:
            raise ValueError("mode must be full or incremental")
        self.source = source
        self.notion = notion
        self.mode = mode
        self._lock = threading.Lock()
        self._running = False
        self.last_result = SyncResult(mode=mode)

    def run(self) -> SyncResult:
        if self._running:
            return SyncResult(status="already_running", mode=self.mode)
        if not self._lock.acquire(blocking=False):
            return SyncResult(status="already_running", mode=self.mode)
        self._running = True
        result = SyncResult(
            status="running",
            mode=self.mode,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        try:
            records = _unique_records(self.source.fetch_records(self.mode))
            databases = self.notion.ensure_databases()
            result.databases = databases
            book_page_ids: dict[str, str] = {}
            for item in _ordered_records(records):
                try:
                    action, page_id = self.notion.upsert(item, databases, book_page_ids)
                    if item.database == "books":
                        book_page_ids[item.source_id] = page_id
                    result.add_action(action, item)
                except Exception as exc:  # one bad record must not hide independent records
                    result.add_error(f"{item.source_id}: {exc}", item)

            if self.mode == "full":
                current_ids = {item.source_id for item in records}
                self._mark_missing(result, databases, current_ids)
            result.status = "failed" if result.counts["failed"] else "succeeded"
        except Exception as exc:
            result.status = "failed"
            result.counts["failed"] += 1
            result.errors.append(str(exc))
        finally:
            result.finished_at = datetime.now(timezone.utc).isoformat()
            self.last_result = result
            self._running = False
            self._lock.release()
        return result

    def _mark_missing(
        self,
        result: SyncResult,
        databases: dict[str, str],
        current_ids: set[str],
    ) -> None:
        for database in ("books", "annotations", "reading_days"):
            try:
                pages = self.notion.list_source_pages(database)
                for page in pages:
                    if page.get("source_id") in current_ids or page.get("sync_status") == "已删除":
                        continue
                    self.notion.mark_deleted(page, database)
                    deleted_record = NormalizedRecord(
                        database=database,
                        source_type=page.get("source_type", "source"),
                        source_id=page["source_id"],
                        title=page.get("title", page["source_id"]),
                        fields={"Sync Status": "已删除"},
                    )
                    result.add_action("marked_deleted", deleted_record)
            except Exception as exc:
                result.errors.append(f"{database} 删除标记失败: {exc}")
                result.counts["failed"] += 1


def _ordered_records(records: list[NormalizedRecord]) -> list[NormalizedRecord]:
    order = {"books": 0, "annotations": 1, "reading_days": 2}
    return sorted(records, key=lambda item: order.get(item.database, 99))


def _unique_records(records: list[NormalizedRecord]) -> list[NormalizedRecord]:
    """Reject conflicting source duplicates before any destination write."""
    seen: dict[str, NormalizedRecord] = {}
    for item in records:
        previous = seen.get(item.source_id)
        if previous and previous.fingerprint != item.fingerprint:
            raise ValueError(f"源数据包含冲突的重复 Source ID: {item.source_id}")
        if not previous:
            seen[item.source_id] = item
    return list(seen.values())
