from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DatabaseDefinition:
    key: str
    title: str
    properties: dict[str, dict[str, Any]]


def text_property() -> dict[str, Any]:
    return {"rich_text": {}}


def select_property(options: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"select": {}}
    if options:
        payload["select"]["options"] = [{"name": option} for option in options]
    return payload


def date_property() -> dict[str, Any]:
    return {"date": {}}


def common_properties() -> dict[str, dict[str, Any]]:
    return {
        "Source ID": text_property(),
        "Fingerprint": text_property(),
        "Sync Status": select_property(["正常", "已删除"]),
        "Source Updated": date_property(),
        "Last Synced": date_property(),
    }


def database_definitions(books_database_id: str | None = None) -> list[DatabaseDefinition]:
    books = common_properties()
    books.update({
        "Name": {"title": {}},
        "Author": text_property(),
        "Category": select_property(),
        "Cover": {"url": {}},
        "State": select_property(["在读", "已读", "想读", "已删除"]),
        # Keep the source's integer 0-100 semantics. Notion's percent format
        # expects a 0-1 value and would silently change the meaning.
        "Progress": {"number": {"format": "number"}},
        "Current Chapter": text_property(),
        "Reading Seconds": {"number": {}},
        "Last Read": date_property(),
        "WeRead URL": {"url": {}},
        "Kind": select_property(["电子书", "专辑"]),
    })

    annotations = common_properties()
    annotations.update({
        "Name": {"title": {}},
        "Type": select_property(["划线", "笔记"]),
        "Book ID": text_property(),
        "Chapter UID": text_property(),
        "Chapter": text_property(),
        "Content": text_property(),
        "Range": text_property(),
        "Color": text_property(),
        "Created At": date_property(),
        "WeRead URL": {"url": {}},
    })
    if books_database_id:
        annotations["Book"] = {
            "relation": {
                "database_id": books_database_id,
                "type": "single_property",
                "single_property": {},
            }
        }

    reading_days = common_properties()
    reading_days.update({
        "Name": {"title": {}},
        "Date": date_property(),
        "Duration Seconds": {"number": {}},
        "Duration Display": text_property(),
        "Source Period": select_property(["daily", "monthly", "annual"]),
    })
    return [
        DatabaseDefinition("books", "WeRead Books", books),
        DatabaseDefinition("annotations", "WeRead Annotations", annotations),
        DatabaseDefinition("reading_days", "WeRead Reading Days", reading_days),
    ]
