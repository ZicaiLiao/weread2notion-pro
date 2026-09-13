from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest
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


if __name__ == "__main__":
    unittest.main()
