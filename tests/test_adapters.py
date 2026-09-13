from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch
from zoneinfo import ZoneInfo

from wread2notion.config import Settings
from wread2notion.domain import NormalizedRecord, source_id
from wread2notion.notion import NotionClient
from wread2notion.schema import database_definitions
from wread2notion.weread import WeReadClient, WeReadError


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class GatewayFixture:
    def __init__(self):
        self.requests: list[dict] = []

    def __call__(self, request, **_kwargs):
        payload = json.loads(request.data.decode("utf-8"))
        self.requests.append(payload)
        api_name = payload["api_name"]
        if api_name == "/shelf/sync":
            return FakeResponse({
                "books": [{"bookId": "book-1", "title": "书架标题", "author": "作者"}],
                "albums": [],
            })
        if api_name == "/user/notebooks":
            if "lastSort" not in payload:
                return FakeResponse({
                    "books": [{"bookId": "book-1", "sort": 20, "book": {"title": "书架标题"}}],
                    "hasMore": 1,
                })
            return FakeResponse({
                "books": [{"bookId": "book-2", "sort": 10, "book": {"title": "第二本"}}],
                "hasMore": "0",
            })
        if api_name == "/book/getprogress":
            return FakeResponse({"book": {"progress": 42, "recordReadingTime": 125, "chapterUid": 7}})
        if api_name == "/book/bookmarklist":
            return FakeResponse({
                "chapters": [{"chapterUid": 7, "title": "第一章"}],
                "updated": [{
                    "bookmarkId": "mark-1", "chapterUid": 7, "markText": "重要内容",
                    "range": "10-20", "colorStyle": 2, "createTime": 1725000000,
                }],
            })
        if api_name == "/review/list/mine":
            return FakeResponse({
                "reviews": [{"review": {
                    "reviewId": "review-1", "content": "我的想法", "chapterName": "第一章",
                    "createTime": 1725000001,
                }}],
                "hasMore": "0",
                "synckey": 1,
            })
        if api_name == "/readdata/detail" and payload["mode"] == "overall":
            return FakeResponse({"registTime": 0})
        if api_name == "/readdata/detail":
            return FakeResponse({"dailyReadTimes": {"1725000000": 3600}})
        raise AssertionError(f"unexpected API: {api_name}")


def settings() -> Settings:
    return Settings(
        weread_api_key="wrk-test",
        notion_token="secret-test",
        notion_parent_page_id="parent",
        reading_start_year=datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).year,
    )


class WeReadAdapterTests(unittest.TestCase):
    def test_fetch_records_paginates_and_preserves_source_semantics(self):
        fixture = GatewayFixture()
        records = WeReadClient(settings(), opener=fixture).fetch_records("full")

        by_id = {record.source_id: record for record in records}
        self.assertEqual(by_id["book:book-1"].title, "书架标题")
        self.assertEqual(by_id["book:book-1"].fields["Progress"], 42)
        self.assertEqual(by_id["highlight:mark-1"].fields["Chapter"], "第一章")
        self.assertEqual(by_id["note:review-1"].fields["Type"], "笔记")
        self.assertEqual(by_id["reading-day:2024-08-30"].fields["Duration Seconds"], 3600)
        self.assertEqual(by_id["reading-day:2024-08-30"].fields["Source Period"], "annual")

        notebook_calls = [item for item in fixture.requests if item["api_name"] == "/user/notebooks"]
        self.assertEqual(notebook_calls[1]["lastSort"], 20)
        self.assertTrue(all(item["skill_version"] == "1.0.4" for item in fixture.requests))
        self.assertIsNone(by_id["book:book-1"].fields["WeRead URL"])

    def test_upgrade_response_is_blocking(self):
        def opener(_request, **_kwargs):
            return FakeResponse({"upgrade_info": {"message": "请升级 skill"}})

        with self.assertRaisesRegex(WeReadError, "请升级 skill"):
            WeReadClient(settings(), opener=opener).call("/shelf/sync")


class NotionAdapterTests(unittest.TestCase):
    def test_schema_keeps_integer_progress_and_relation(self):
        definitions = database_definitions("books-db")
        self.assertEqual(definitions[0].properties["Progress"], {"number": {"format": "number"}})
        self.assertEqual(
            definitions[1].properties["Book"]["relation"]["database_id"],
            "books-db",
        )

    def test_first_run_provisions_three_databases_under_parent(self):
        calls: list[tuple[str, dict]] = []

        def opener(request, **_kwargs):
            payload = json.loads(request.data.decode("utf-8")) if request.data else {}
            calls.append((request.full_url, payload))
            if request.full_url.endswith("/search"):
                return FakeResponse({"results": []})
            if request.full_url.endswith("/databases"):
                title = payload["title"][0]["text"]["content"]
                return FakeResponse({"id": {"WeRead Books": "books-db", "WeRead Annotations": "annotations-db", "WeRead Reading Days": "days-db"}[title]})
            raise AssertionError(request.full_url)

        client = NotionClient("secret", parent_page_id="parent", opener=opener)
        ids = client.ensure_databases()

        self.assertEqual(ids, {"books": "books-db", "annotations": "annotations-db", "reading_days": "days-db"})
        create_payloads = [payload for url, payload in calls if url.endswith("/databases")]
        self.assertTrue(all(payload["parent"]["page_id"] == "parent" for payload in create_payloads))
        annotation = next(payload for payload in create_payloads if payload["title"][0]["text"]["content"] == "WeRead Annotations")
        self.assertEqual(annotation["properties"]["Book"]["relation"]["database_id"], "books-db")

    def test_upsert_queries_source_id_and_writes_relation(self):
        calls: list[tuple[str, dict]] = []

        def opener(request, **_kwargs):
            payload = json.loads(request.data.decode("utf-8")) if request.data else {}
            calls.append((request.full_url, payload))
            if "/query" in request.full_url:
                return FakeResponse({"results": []})
            if request.full_url.endswith("/pages"):
                return FakeResponse({"id": "annotation-page"})
            raise AssertionError(request.full_url)

        client = NotionClient("secret", opener=opener)
        item = NormalizedRecord(
            "annotations", "note", source_id("note", "1"), "一条笔记",
            {"Book ID": "42", "Type": "笔记", "Progress": 42}, "fingerprint",
        )
        action, page_id = client.upsert(item, {"books": "books-db", "annotations": "annotations-db"}, {"book:42": "book-page"})

        self.assertEqual((action, page_id), ("created", "annotation-page"))
        page_payload = next(payload for url, payload in calls if url.endswith("/pages"))
        self.assertEqual(page_payload["properties"]["Book"]["relation"], [{"id": "book-page"}])
        self.assertEqual(page_payload["properties"]["Source ID"]["rich_text"][0]["text"]["content"], "note:1")

    def test_prepare_sync_loads_source_index_once(self):
        calls: list[str] = []

        def opener(request, **_kwargs):
            calls.append(request.full_url)
            return FakeResponse({
                "results": [{
                    "id": "book-page",
                    "properties": {
                        "Name": {"title": [{"plain_text": "一本书"}]},
                        "Source ID": {"rich_text": [{"plain_text": "book:1"}]},
                        "Fingerprint": {"rich_text": [{"plain_text": "fingerprint"}]},
                        "Sync Status": {"select": {"name": "正常"}},
                    },
                }],
                "has_more": False,
            })

        client = NotionClient("secret", opener=opener)
        client.prepare_sync({"books": "books-db"})

        matches = client.find_by_source_id("books-db", "book:1")
        self.assertEqual([match.page_id for match in matches], ["book-page"])
        self.assertEqual(len(calls), 1)

    def test_request_retries_notion_rate_limit(self):
        attempts = 0
        headers = Message()
        headers["Retry-After"] = "0"

        def opener(_request, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise urllib.error.HTTPError("https://notion.test/x", 429, "rate limited", headers, None)
            return FakeResponse({"ok": True})

        client = NotionClient("secret", opener=opener)
        with patch("wread2notion.notion.time.sleep") as sleep:
            self.assertEqual(client.request("GET", "/x"), {"ok": True})

        self.assertEqual(attempts, 2)
        sleep.assert_called_once_with(0.0)

    def test_dashboard_is_created_once_with_database_links(self):
        calls: list[tuple[str, dict]] = []

        def opener(request, **_kwargs):
            payload = json.loads(request.data.decode("utf-8")) if request.data else {}
            calls.append((request.full_url, payload))
            if request.full_url.endswith("/search"):
                return FakeResponse({"results": []})
            if request.full_url.endswith("/pages"):
                return FakeResponse({"id": "dashboard-page"})
            raise AssertionError(request.full_url)

        client = NotionClient("secret", parent_page_id="parent", opener=opener)
        dashboard_id = client.ensure_dashboard({
            "books": "books-db",
            "annotations": "annotations-db",
            "reading_days": "days-db",
        })

        self.assertEqual(dashboard_id, "dashboard-page")
        page_payload = next(payload for url, payload in calls if url.endswith("/pages"))
        links = [
            block["link_to_page"]["database_id"]
            for block in page_payload["children"]
            if block["type"] == "link_to_page"
        ]
        self.assertEqual(links, ["books-db", "annotations-db", "days-db"])


if __name__ == "__main__":
    unittest.main()
