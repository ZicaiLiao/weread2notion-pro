from __future__ import annotations

import unittest

from wread2notion.domain import NormalizedRecord, source_id
from wread2notion.sync import SyncCoordinator


def record(database: str, kind: str, identifier: str, title: str, fingerprint: str) -> NormalizedRecord:
    return NormalizedRecord(
        database=database,
        source_type=kind,
        source_id=source_id(kind, identifier),
        title=title,
        fields={"Name": title},
        fingerprint=fingerprint,
    )


class FakeSource:
    def __init__(self, records: list[NormalizedRecord]):
        self.records = records

    def fetch_records(self, mode: str) -> list[NormalizedRecord]:
        return self.records


class FakeNotion:
    def __init__(self, existing: dict[str, str] | None = None):
        self.existing = existing or {}
        self.calls: list[tuple[str, str]] = []

    def ensure_databases(self) -> dict[str, str]:
        return {"books": "db-books", "annotations": "db-annotations", "reading_days": "db-days"}

    def upsert(self, item: NormalizedRecord, database_ids: dict[str, str], book_page_ids: dict[str, str]):
        self.calls.append(("upsert", item.source_id))
        previous = self.existing.get(item.source_id)
        if previous == item.fingerprint:
            return "unchanged", f"page-{item.source_id}"
        action = "updated" if previous else "created"
        self.existing[item.source_id] = item.fingerprint
        return action, f"page-{item.source_id}"

    def list_source_pages(self, database: str):
        return []

    def mark_deleted(self, page, database):
        self.calls.append(("delete", page))


class SyncCoordinatorTests(unittest.TestCase):
    def test_run_upserts_records_and_reports_actions(self):
        source = FakeSource([
            record("books", "book", "1", "一本书", "a"),
            record("annotations", "note", "2", "一条笔记", "b"),
        ])
        notion = FakeNotion()

        result = SyncCoordinator(source, notion, mode="full").run()

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.counts["created"], 2)
        self.assertEqual(result.counts["failed"], 0)
        self.assertEqual([call[1] for call in notion.calls], ["book:1", "note:2"])

    def test_repeating_run_is_idempotent(self):
        source = FakeSource([record("books", "book", "1", "一本书", "same")])
        notion = FakeNotion()
        coordinator = SyncCoordinator(source, notion, mode="incremental")

        first = coordinator.run()
        second = coordinator.run()

        self.assertEqual(first.counts["created"], 1)
        self.assertEqual(second.counts["unchanged"], 1)
        self.assertEqual(second.counts["created"], 0)

    def test_source_failure_does_not_mark_records_deleted(self):
        class FailingSource(FakeSource):
            def fetch_records(self, mode: str):
                raise RuntimeError("WeRead unavailable")

        notion = FakeNotion({"book:old": "old"})
        result = SyncCoordinator(FailingSource([]), notion, mode="full").run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.counts["marked_deleted"], 0)
        self.assertEqual(notion.calls, [])

    def test_full_run_marks_missing_pages_deleted(self):
        class DeletingNotion(FakeNotion):
            def list_source_pages(self, database):
                return [{
                    "page_id": "old-page",
                    "source_id": "book:old",
                    "source_type": "book",
                    "sync_status": "正常",
                    "title": "旧书",
                }] if database == "books" else []

        notion = DeletingNotion()
        result = SyncCoordinator(FakeSource([]), notion, mode="full").run()

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.counts["marked_deleted"], 1)
        self.assertEqual(notion.calls, [("delete", {
            "page_id": "old-page",
            "source_id": "book:old",
            "source_type": "book",
            "sync_status": "正常",
            "title": "旧书",
        })])

    def test_incremental_run_never_marks_missing_pages_deleted(self):
        class ListingNotion(FakeNotion):
            def list_source_pages(self, database):
                return [{"page_id": "old-page", "source_id": "book:old", "sync_status": "正常", "title": "旧书"}]

        notion = ListingNotion()
        result = SyncCoordinator(FakeSource([]), notion, mode="incremental").run()

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.counts["marked_deleted"], 0)
        self.assertEqual(notion.calls, [])

    def test_conflicting_source_duplicates_fail_before_writes(self):
        source = FakeSource([
            record("books", "book", "1", "一本书", "a"),
            record("books", "book", "1", "一本书的新版本", "b"),
        ])
        notion = FakeNotion()
        result = SyncCoordinator(source, notion, mode="full").run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.counts["failed"], 1)
        self.assertIn("冲突的重复 Source ID", result.errors[0])
        self.assertEqual(notion.calls, [])

    def test_coordinator_rejects_overlapping_run(self):
        source = FakeSource([])
        notion = FakeNotion()
        coordinator = SyncCoordinator(source, notion, mode="full")
        coordinator._running = True

        result = coordinator.run()

        self.assertEqual(result.status, "already_running")


if __name__ == "__main__":
    unittest.main()
