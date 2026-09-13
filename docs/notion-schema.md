# Notion Schema

The application creates these databases below the configured parent page. The
property names are stable integration identifiers; display labels may be
localized later without changing source identity or sync behavior.

It also creates one idempotent `WeRead 阅读中枢` page below the parent page. The
page provides navigation links to the three databases and records the intended
views for the bookshelf, annotations, and reading statistics. Notion's public
API does not expose database-view configuration, so filters and grouping are
still configured in the database itself.

## Books

| Property | Notion type | Meaning |
|---|---|---|
| Name | title | Book title |
| Source ID | rich_text | `book:<bookId>` |
| Fingerprint | rich_text | Hash of source-owned fields used for unchanged detection |
| Author | rich_text | Author name |
| Category | select | Source category |
| Cover | url | Cover image URL |
| State | select | `在读`, `已读`, `想读`, `已删除` |
| Progress | number | Integer percentage from 0 to 100 |
| Current Chapter | rich_text | Current chapter UID or title |
| Reading Seconds | number | Cumulative reading seconds |
| Last Read | date | Last reading date |
| WeRead URL | url | Deep link returned by WeRead when available |
| Sync Status | select | `正常` or `已删除` |
| Source Updated | date | Source update timestamp |
| Last Synced | date | Local sync timestamp |

## Annotations

| Property | Notion type | Meaning |
|---|---|---|
| Name | title | Highlight excerpt or note excerpt |
| Source ID | rich_text | `highlight:<bookmarkId>` or `note:<reviewId>` |
| Type | select | `划线` or `笔记` |
| Book | relation | Relation to Books |
| Book ID | rich_text | WeRead book ID |
| Chapter UID | rich_text | WeRead chapter UID when available |
| Chapter | rich_text | Chapter title or review scope |
| Content | rich_text | Full highlight or note content |
| Range | rich_text | WeRead range when available |
| Color | rich_text | Highlight color style when available |
| Created At | date | Source creation timestamp |
| WeRead URL | url | Deep link returned by WeRead when available |
| Sync Status | select | `正常` or `已删除` |
| Source Updated | date | Source update timestamp |
| Last Synced | date | Local sync timestamp |

## Reading Days

| Property | Notion type | Meaning |
|---|---|---|
| Name | title | Local date label, such as `2026-09-12` |
| Source ID | rich_text | `reading-day:<YYYY-MM-DD>` |
| Date | date | Local calendar date in configured timezone |
| Duration Seconds | number | Reading duration in seconds |
| Duration Display | rich_text | Human-readable hours/minutes |
| Source Period | select | `daily`, `monthly`, or `annual` |
| Sync Status | select | `正常` or `已删除` |
| Source Updated | date | Source statistic retrieval timestamp |
| Last Synced | date | Local sync timestamp |

## Deliberate Omissions

- No separate Categories database: `Category` is a Books property and a view
  filter.
- No separate Authors database: `Author` is a Books property and a view
  filter.
- No separate Chapters database: chapter fields live on Annotations.
- No separate Sync Runs database in the first version: run state and errors
  remain in the CLI JSON result and process log until an audit history is needed.
- Reading Days do not relate to Books because the supported reading statistics
  interface does not provide reliable per-book daily duration.
