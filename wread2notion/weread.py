from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
import urllib.error
import urllib.request
import ssl
from zoneinfo import ZoneInfo

from .config import Settings
from .domain import (
    NormalizedRecord,
    format_duration,
    iso_date,
    iso_datetime,
    source_id,
)


SKILL_VERSION = "1.0.4"


class WeReadError(RuntimeError):
    """Raised when the WeRead gateway cannot provide a valid response."""


class WeReadClient:
    def __init__(self, settings: Settings, opener: Any = urllib.request.urlopen):
        self.settings = settings
        self.opener = opener
        self.context = _ssl_context()

    def call(self, api_name: str, **params: Any) -> dict[str, Any]:
        body = {"api_name": api_name, **params, "skill_version": SKILL_VERSION}
        request = urllib.request.Request(
            self.settings.weread_gateway_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.weread_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=45, context=self.context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise WeReadError(f"微信读书请求失败: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise WeReadError(f"微信读书网络请求失败: {exc}") from exc

        if not isinstance(payload, dict):
            raise WeReadError("微信读书返回了非对象 JSON")
        if payload.get("upgrade_info"):
            upgrade = payload["upgrade_info"]
            if isinstance(upgrade, dict):
                message = upgrade.get("message", "微信读书 skill 需要升级")
                upgrade_url = upgrade.get("upgrade_url") or upgrade.get("url")
                latest_version = upgrade.get("version") or upgrade.get("latest_version")
                details = []
                if latest_version:
                    details.append(f"latest_version={latest_version}")
                if upgrade_url:
                    details.append(f"upgrade_url={upgrade_url}")
                if details:
                    message = f"{message} ({', '.join(details)})"
            else:
                message = str(upgrade)
            raise WeReadError(message)
        if payload.get("errcode", 0) not in (0, "0", None):
            raise WeReadError(payload.get("errmsg", f"微信读书接口错误: {payload['errcode']}"))
        return payload

    def fetch_records(self, mode: str) -> list[NormalizedRecord]:
        shelf = self.call("/shelf/sync")
        shelf_books = list(shelf.get("books", []))
        notebooks = self._notebook_books()
        by_book_id = {str(item.get("bookId")): item for item in shelf_books if item.get("bookId") is not None}
        for item in notebooks:
            book = item.get("book", {})
            merged = {**book, **{key: value for key, value in item.items() if key != "book"}}
            if merged.get("bookId") is not None:
                by_book_id[str(merged["bookId"])] = merged
        records: list[NormalizedRecord] = []

        for raw in by_book_id.values():
            book_id = str(raw["bookId"])
            progress = self._safe_progress(book_id)
            records.append(self._book_record(raw, progress, "电子书"))

        for album in shelf.get("albums", []):
            info = album.get("albumInfo", album)
            extra = album.get("albumInfoExtra", {})
            album_id = str(info.get("albumId", album.get("albumId", "")))
            if not album_id:
                continue
            fields = {
                "Author": info.get("authorName", ""),
                "Category": "有声书",
                "Cover": info.get("cover", ""),
                "State": "已读" if info.get("finish") == 1 else "想读",
                "Progress": 100 if info.get("finish") == 1 else 0,
                "Current Chapter": "",
                "Reading Seconds": 0,
                "Last Read": iso_date(extra.get("lectureReadUpdateTime"), self.settings.timezone),
                "WeRead URL": info.get("deepLink") or album.get("deepLink"),
                "Kind": "专辑",
                "Source Updated": iso_datetime(info.get("updateTime"), self.settings.timezone),
                "Sync Status": "正常",
            }
            records.append(NormalizedRecord("books", "album", source_id("album", album_id), info.get("name", album_id), fields).with_fingerprint())

        for notebook in notebooks:
            book_id = str(notebook.get("bookId", ""))
            if not book_id:
                continue
            bookmarks = self.call("/book/bookmarklist", bookId=book_id)
            chapters = {
                str(chapter.get("chapterUid")): chapter.get("title", "")
                for chapter in bookmarks.get("chapters", [])
            }
            for item in bookmarks.get("updated", []):
                if not item.get("bookmarkId"):
                    raise WeReadError(f"书籍 {book_id} 返回了没有 bookmarkId 的划线")
                records.append(self._highlight_record(item, chapters, book_id))
            for review in self._reviews(book_id):
                if not (review.get("review", review).get("reviewId") or review.get("reviewId")):
                    raise WeReadError(f"书籍 {book_id} 返回了没有 reviewId 的笔记")
                records.append(self._note_record(review, book_id))

        records.extend(self._reading_day_records())
        return records

    def _notebook_books(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        last_sort: int | None = None
        seen_sorts: set[int] = set()
        while True:
            params: dict[str, Any] = {"count": 100}
            if last_sort is not None:
                params["lastSort"] = last_sort
            page = self.call("/user/notebooks", **params)
            result.extend(page.get("books", []))
            if not page.get("hasMore"):
                break
            page_books = page.get("books", [])
            if not page_books:
                break
            next_sort = page_books[-1].get("sort")
            if next_sort is None:
                raise WeReadError("微信读书笔记本分页游标没有前进")
            next_sort_value = int(next_sort)
            if next_sort_value in seen_sorts:
                raise WeReadError("微信读书笔记本分页游标没有前进")
            seen_sorts.add(next_sort_value)
            last_sort = next_sort_value
        return result

    def _reviews(self, book_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        synckey = 0
        seen_keys: set[int] = set()
        while True:
            page = self.call("/review/list/mine", bookid=book_id, synckey=synckey, count=100)
            result.extend(page.get("reviews", []))
            if not page.get("hasMore"):
                break
            next_key = page.get("synckey")
            if next_key in seen_keys or next_key is None:
                raise WeReadError(f"书籍 {book_id} 的点评分页游标没有前进")
            seen_keys.add(next_key)
            synckey = next_key
        return result

    def _safe_progress(self, book_id: str) -> dict[str, Any]:
        return self.call("/book/getprogress", bookId=book_id).get("book", {})

    def _book_record(self, raw: dict[str, Any], progress: dict[str, Any], kind: str) -> NormalizedRecord:
        book_id = str(raw["bookId"])
        title = raw.get("title") or raw.get("name") or book_id
        percentage = int(progress.get("progress", raw.get("readingProgress", 0)) or 0)
        state = "已读" if percentage == 100 or raw.get("finishReading") == 1 else "在读" if percentage > 0 else "想读"
        fields = {
            "Author": raw.get("author", ""),
            "Category": raw.get("category", ""),
            "Cover": raw.get("cover", ""),
            "State": state,
            "Progress": max(0, min(100, percentage)),
            "Current Chapter": str(progress.get("chapterUid", "")),
            "Reading Seconds": int(progress.get("recordReadingTime", 0) or 0),
            "Last Read": iso_date(progress.get("updateTime", raw.get("readUpdateTime")), self.settings.timezone),
            "WeRead URL": raw.get("deepLink") or progress.get("deepLink"),
            "Kind": kind,
            "Source Updated": iso_datetime(raw.get("updateTime", raw.get("readUpdateTime")), self.settings.timezone),
            "Sync Status": "正常",
        }
        return NormalizedRecord("books", "book", source_id("book", book_id), title, fields).with_fingerprint()

    def _highlight_record(self, item: dict[str, Any], chapters: dict[str, str], book_id: str) -> NormalizedRecord:
        chapter_uid = item.get("chapterUid", "")
        bookmark_id = str(item.get("bookmarkId", ""))
        fields = {
            "Type": "划线",
            "Book ID": book_id,
            "Chapter UID": str(chapter_uid),
            "Chapter": chapters.get(str(chapter_uid), ""),
            "Content": item.get("markText", ""),
            "Range": item.get("range", ""),
            "Color": str(item.get("colorStyle", "")),
            "Created At": iso_datetime(item.get("createTime"), self.settings.timezone),
            "WeRead URL": item.get("deepLink"),
            "Source Updated": iso_datetime(item.get("createTime"), self.settings.timezone),
            "Sync Status": "正常",
        }
        return NormalizedRecord("annotations", "highlight", source_id("highlight", bookmark_id), item.get("markText", bookmark_id), fields).with_fingerprint()

    def _note_record(self, item: dict[str, Any], book_id: str) -> NormalizedRecord:
        review = item.get("review", item)
        review_id = str(review.get("reviewId", item.get("reviewId", "")))
        chapter_uid = review.get("chapterUid", "")
        fields = {
            "Type": "笔记",
            "Book ID": str(review.get("bookId", book_id)),
            "Chapter UID": str(chapter_uid),
            "Chapter": review.get("chapterName", "整本书"),
            "Content": review.get("content", ""),
            "Range": review.get("range", ""),
            "Color": "",
            "Created At": iso_datetime(review.get("createTime"), self.settings.timezone),
            "WeRead URL": review.get("deepLink"),
            "Source Updated": iso_datetime(review.get("createTime"), self.settings.timezone),
            "Sync Status": "正常",
        }
        return NormalizedRecord("annotations", "note", source_id("note", review_id), review.get("content", review_id), fields).with_fingerprint()

    def _reading_day_records(self) -> list[NormalizedRecord]:
        local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(self.settings.timezone))
        now = local_now.year
        overall = self.call("/readdata/detail", mode="overall")
        registration = overall.get("registTime")
        start_year = self.settings.reading_start_year or _year_from_timestamp(registration) or now
        result: list[NormalizedRecord] = []
        for year in range(start_year, now + 1):
            annual = self.call("/readdata/detail", mode="annually", baseTime=_year_timestamp(year))
            daily = annual.get("dailyReadTimes")
            if isinstance(daily, dict):
                result.extend(self._reading_bucket_records(daily, "annual"))
                continue
            for month in range(1, 13):
                if year == now and month > local_now.month:
                    break
                monthly = self.call("/readdata/detail", mode="monthly", baseTime=_month_timestamp(year, month))
                result.extend(self._reading_bucket_records(monthly.get("readTimes", {}), "monthly"))
        return _deduplicate_records(result)

    def _reading_bucket_records(self, buckets: Any, period: str) -> list[NormalizedRecord]:
        if not isinstance(buckets, dict):
            return []
        result = []
        for timestamp, seconds in buckets.items():
            date_value = iso_date(timestamp, self.settings.timezone)
            if not date_value:
                continue
            duration = int(seconds or 0)
            fields = {
                "Date": date_value,
                "Duration Seconds": duration,
                "Duration Display": format_duration(duration),
                "Source Period": period,
                "Source Updated": date_value,
                "Sync Status": "正常",
            }
            result.append(NormalizedRecord("reading_days", "reading-day", source_id("reading-day", date_value), date_value, fields).with_fingerprint())
        return result


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _year_timestamp(year: int) -> int:
    return int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())


def _month_timestamp(year: int, month: int) -> int:
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())


def _year_from_timestamp(value: Any) -> int | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).year
    except (TypeError, ValueError, OverflowError):
        return None


def _deduplicate_records(records: list[NormalizedRecord]) -> list[NormalizedRecord]:
    by_id: dict[str, NormalizedRecord] = {}
    for item in records:
        by_id[item.source_id] = item
    return list(by_id.values())
