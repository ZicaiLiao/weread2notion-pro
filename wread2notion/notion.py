from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import IncompleteRead, RemoteDisconnected
import json
import time
from typing import Any
import ssl
import urllib.error
import urllib.request

from .domain import NormalizedRecord
from .schema import DatabaseDefinition, database_definitions


class NotionError(RuntimeError):
    """Raised when a Notion request or response cannot be handled."""


@dataclass(frozen=True)
class PageMatch:
    page_id: str
    source_id: str
    fingerprint: str
    sync_status: str
    title: str


class NotionClient:
    def __init__(
        self,
        token: str,
        api_url: str = "https://api.notion.com/v1",
        api_version: str = "2022-06-28",
        parent_page_id: str | None = None,
        opener: Any = urllib.request.urlopen,
    ):
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.api_version = api_version
        self.parent_page_id = parent_page_id
        self.opener = opener
        self.context = _ssl_context()
        self.database_ids: dict[str, str] = {}
        self._source_index: dict[str, dict[str, list[PageMatch]]] = {}
        self._source_index_ready: set[str] = set()

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.api_version,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        for attempt in range(6):
            try:
                with self.opener(request, timeout=45, context=self.context) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise NotionError("Notion 返回了非对象 JSON")
                return payload
            except urllib.error.HTTPError as exc:
                try:
                    details = json.loads(exc.read().decode("utf-8"))
                    message = details.get("message", str(exc))
                except (ValueError, AttributeError):
                    message = str(exc)
                if exc.code != 429 or attempt == 5:
                    raise NotionError(f"Notion 请求失败: {message}") from exc
                retry_delay = _retry_after(exc)
                delay = retry_delay if retry_delay is not None else min(2 ** attempt, 30)
                time.sleep(delay)
            except (urllib.error.URLError, IncompleteRead, RemoteDisconnected, ConnectionResetError, TimeoutError) as exc:
                if attempt == 5:
                    raise NotionError(f"Notion 网络请求失败: {exc}") from exc
                time.sleep(min(2 ** attempt, 8))
            except ValueError as exc:
                raise NotionError(f"Notion 网络请求失败: {exc}") from exc
        raise NotionError(f"Notion 请求失败: {method} {path}")

    def ensure_databases(self, parent_page_id: str | None = None) -> dict[str, str]:
        parent_id = parent_page_id or self.parent_page_id
        if not parent_id:
            raise NotionError("未配置 Notion parent page ID")
        books = self._find_or_create_database(parent_id, database_definitions()[0])
        definitions = database_definitions(books)
        annotations = self._find_or_create_database(parent_id, definitions[1])
        reading_days = self._find_or_create_database(parent_id, definitions[2])
        self.database_ids = {"books": books, "annotations": annotations, "reading_days": reading_days}
        self._source_index.clear()
        self._source_index_ready.clear()
        return self.database_ids

    def prepare_sync(self, database_ids: dict[str, str]) -> None:
        """Load each destination database once before record-level upserts."""
        self._source_index.clear()
        self._source_index_ready.clear()
        for database_id in database_ids.values():
            pages = self._paginate("POST", f"/databases/{database_id}/query", {"page_size": 100})
            index: dict[str, list[PageMatch]] = {}
            for page in pages:
                match = _page_match(page)
                if match.source_id:
                    index.setdefault(match.source_id, []).append(match)
            self._source_index[database_id] = index
            self._source_index_ready.add(database_id)

    def ensure_dashboard(self, database_ids: dict[str, str], parent_page_id: str | None = None) -> str:
        parent_id = parent_page_id or self.parent_page_id
        if not parent_id:
            raise NotionError("未配置 Notion parent page ID")
        title = "WeRead 阅读中枢"
        existing = self._search_page(parent_id, title)
        if existing:
            return existing
        response = self.request("POST", "/pages", {
            "parent": {"type": "page_id", "page_id": parent_id},
            "icon": {"type": "emoji", "emoji": "📚"},
            "properties": {"title": {"title": _rich_text(title)}},
            "children": _dashboard_blocks(database_ids),
        })
        if not response.get("id"):
            raise NotionError("创建 Notion 阅读中枢失败")
        return response["id"]

    def _find_or_create_database(self, parent_page_id: str, definition: DatabaseDefinition) -> str:
        existing = self._search_database(parent_page_id, definition.title)
        if existing:
            return existing
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": definition.title}}],
            "properties": definition.properties,
        }
        response = self.request("POST", "/databases", payload)
        if not response.get("id"):
            raise NotionError(f"创建 Notion 数据库失败: {definition.title}")
        return response["id"]

    def _search_database(self, parent_page_id: str, title: str) -> str | None:
        payload = {
            "query": title,
            "filter": {"property": "object", "value": "database"},
            "page_size": 100,
        }
        for result in self._paginate("POST", "/search", payload):
            if _title_text(result.get("title", [])) != title:
                continue
            result_parent = result.get("parent", {})
            if result_parent.get("type") != "page_id":
                continue
            if _normalise_id(result_parent.get("page_id")) != _normalise_id(parent_page_id):
                continue
            return result.get("id")
        return None

    def _paginate(self, method: str, path: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_payload = dict(payload)
        seen_cursors: set[str] = set()
        while True:
            response = self.request(method, path, next_payload)
            results.extend(item for item in response.get("results", []) if isinstance(item, dict))
            if not response.get("has_more"):
                return results
            cursor = response.get("next_cursor")
            if not cursor or cursor in seen_cursors:
                raise NotionError(f"Notion 分页游标没有前进: {path}")
            seen_cursors.add(cursor)
            next_payload["start_cursor"] = cursor

    def upsert(
        self,
        item: NormalizedRecord,
        database_ids: dict[str, str],
        book_page_ids: dict[str, str],
    ) -> tuple[str, str]:
        database_id = database_ids[item.database]
        matches = self.find_by_source_id(database_id, item.source_id)
        if len(matches) > 1:
            raise NotionError(f"Source ID 存在多个 Notion 页面: {item.source_id}")
        properties = self._properties_for(item, database_ids, book_page_ids)
        if matches:
            match = matches[0]
            if match.fingerprint == item.fingerprint and match.sync_status == "正常":
                return "unchanged", match.page_id
            self.request("PATCH", f"/pages/{match.page_id}", {"properties": properties})
            self._cache_match(database_id, PageMatch(
                match.page_id,
                item.source_id,
                item.fingerprint,
                str(item.fields.get("Sync Status", "正常")),
                item.title or item.source_id,
            ))
            return "updated", match.page_id
        response = self.request("POST", "/pages", {
            "parent": {"database_id": database_id},
            "properties": properties,
        })
        if not response.get("id"):
            raise NotionError(f"创建 Notion 页面失败: {item.source_id}")
        self._cache_match(database_id, PageMatch(
            response["id"],
            item.source_id,
            item.fingerprint,
            str(item.fields.get("Sync Status", "正常")),
            item.title or item.source_id,
        ))
        return "created", response["id"]

    def find_by_source_id(self, database_id: str, source_id: str) -> list[PageMatch]:
        if database_id in self._source_index_ready:
            return list(self._source_index.get(database_id, {}).get(source_id, []))
        pages = self._paginate("POST", f"/databases/{database_id}/query", {
            "filter": {"property": "Source ID", "rich_text": {"equals": source_id}},
            "page_size": 100,
        })
        return [_page_match(page) for page in pages]

    def list_source_pages(self, database: str) -> list[dict[str, Any]]:
        database_id = self.database_ids[database]
        if database_id in self._source_index_ready:
            matches = [match for values in self._source_index[database_id].values() for match in values]
        else:
            pages = self._paginate("POST", f"/databases/{database_id}/query", {"page_size": 100})
            matches = [_page_match(page) for page in pages]
        result = []
        for match in matches:
            if match.source_id:
                result.append({
                    "page_id": match.page_id,
                    "source_id": match.source_id,
                    "source_type": match.source_id.split(":", 1)[0],
                    "sync_status": match.sync_status,
                    "title": match.title,
                })
        return result

    def mark_deleted(self, page: dict[str, Any], database: str) -> None:
        properties: dict[str, Any] = {"Sync Status": {"select": {"name": "已删除"}}}
        if database == "books":
            properties["State"] = {"select": {"name": "已删除"}}
        self.request("PATCH", f"/pages/{page['page_id']}", {"properties": properties})
        self._cache_match_for_page(page["page_id"], sync_status="已删除")

    def _properties_for(
        self,
        item: NormalizedRecord,
        database_ids: dict[str, str],
        book_page_ids: dict[str, str],
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "Name": {"title": _rich_text(item.title or item.source_id)},
            "Source ID": {"rich_text": _rich_text(item.source_id)},
            "Fingerprint": {"rich_text": _rich_text(item.fingerprint)},
            "Last Synced": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        }
        for name, value in item.fields.items():
            properties[name] = _property_payload(name, value)
        if item.database == "annotations":
            book_id = item.fields.get("Book ID")
            related_page = book_page_ids.get(f"book:{book_id}") or book_page_ids.get(f"album:{book_id}")
            if not related_page and book_id:
                related_page = self._find_book_page(database_ids["books"], str(book_id))
            properties["Book"] = {"relation": [{"id": related_page}]} if related_page else {"relation": []}
        return properties

    def _find_book_page(self, database_id: str, book_id: str) -> str | None:
        for candidate in (f"book:{book_id}", f"album:{book_id}"):
            matches = self.find_by_source_id(database_id, candidate)
            if len(matches) > 1:
                raise NotionError(f"Source ID 存在多个 Notion 页面: {candidate}")
            if matches:
                return matches[0].page_id
        return None

    def _search_page(self, parent_page_id: str, title: str) -> str | None:
        payload = {
            "query": title,
            "filter": {"property": "object", "value": "page"},
            "page_size": 100,
        }
        for result in self._paginate("POST", "/search", payload):
            if _title_text(result.get("properties", {}).get("title", {}).get("title", [])) != title:
                continue
            result_parent = result.get("parent", {})
            if result_parent.get("type") != "page_id":
                continue
            if _normalise_id(result_parent.get("page_id")) == _normalise_id(parent_page_id):
                return result.get("id")
        return None

    def _cache_match(self, database_id: str, match: PageMatch) -> None:
        if database_id not in self._source_index_ready:
            return
        self._source_index.setdefault(database_id, {}).setdefault(match.source_id, [])
        matches = self._source_index[database_id][match.source_id]
        for index, existing in enumerate(matches):
            if existing.page_id == match.page_id:
                matches[index] = match
                return
        matches.append(match)

    def _cache_match_for_page(self, page_id: str, sync_status: str) -> None:
        for index in self._source_index.values():
            for source_id, matches in index.items():
                for position, match in enumerate(matches):
                    if match.page_id == page_id:
                        matches[position] = PageMatch(
                            match.page_id, match.source_id, match.fingerprint, sync_status, match.title,
                        )
                        return


def _page_match(page: dict[str, Any]) -> PageMatch:
    props = page.get("properties", {})
    return PageMatch(
        page_id=page["id"],
        source_id=_property_text(props.get("Source ID", {})),
        fingerprint=_property_text(props.get("Fingerprint", {})),
        sync_status=_property_select(props.get("Sync Status", {})) or "正常",
        title=_property_text(props.get("Name", {})) or _property_text(props.get("title", {})),
    )


def _property_payload(name: str, value: Any) -> dict[str, Any]:
    selects = {"Sync Status", "State", "Type", "Category", "Kind", "Source Period"}
    numbers = {"Progress", "Reading Seconds", "Duration Seconds"}
    urls = {"Cover", "WeRead URL"}
    dates = {"Last Read", "Source Updated", "Last Synced", "Created At", "Date"}
    if name in selects:
        return {"select": {"name": str(value)}} if value not in (None, "") else {"select": None}
    if name in numbers:
        return {"number": float(value)} if value not in (None, "") else {"number": None}
    if name in urls:
        return {"url": str(value)} if value not in (None, "") else {"url": None}
    if name in dates:
        return {"date": {"start": str(value)}} if value not in (None, "") else {"date": None}
    return {"rich_text": _rich_text(str(value))} if value not in (None, "") else {"rich_text": []}


def _property_text(property_value: dict[str, Any]) -> str:
    values = property_value.get("title") or property_value.get("rich_text") or []
    return "".join(item.get("plain_text", item.get("text", {}).get("content", "")) for item in values)


def _property_select(property_value: dict[str, Any]) -> str:
    return (property_value.get("select") or {}).get("name", "")


def _title_text(values: list[dict[str, Any]] | None) -> str:
    return _property_text({"rich_text": values or []})


def _rich_text(value: str) -> list[dict[str, Any]]:
    chunks = [value[index:index + 1900] for index in range(0, len(value), 1900)] or [""]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return max(0.0, min(float(value), 60.0)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _dashboard_blocks(database_ids: dict[str, str]) -> list[dict[str, Any]]:
    def text_block(block_type: str, content: str) -> dict[str, Any]:
        return {"object": "block", "type": block_type, block_type: {"rich_text": [{"type": "text", "text": {"content": content}}]}}

    blocks: list[dict[str, Any]] = [
        text_block("heading_1", "WeRead 阅读中枢"),
        text_block("paragraph", "微信读书数据会自动同步到下方数据库。"),
        {"object": "block", "type": "divider", "divider": {}},
        text_block("heading_2", "数据入口"),
    ]
    labels = (("books", "书架 / 阅读进度"), ("annotations", "笔记与划线"), ("reading_days", "阅读统计"))
    for key, label in labels:
        blocks.append(text_block("paragraph", label))
        blocks.append({
            "object": "block",
            "type": "link_to_page",
            "link_to_page": {"type": "database_id", "database_id": database_ids[key]},
        })
    blocks.extend([
        text_block("heading_2", "推荐视图"),
        text_block("bulleted_list_item", "书架：按 State 分组，按 Last Read 倒序"),
        text_block("bulleted_list_item", "笔记与划线：按 Type 分组，按 Created At 倒序"),
        text_block("bulleted_list_item", "阅读统计：按 Date 倒序，查看每日阅读时长"),
    ])
    return blocks


def _normalise_id(value: str | None) -> str:
    return (value or "").replace("-", "").lower()


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
