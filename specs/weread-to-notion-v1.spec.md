# WeRead to Notion V1 Specification

## Scope

Build a personal, one-way synchronization command that imports a user's
WeRead books, reading progress, highlights, personal notes, and daily reading
aggregates into Notion.

The existing `static/` directory is a deprecated UI prototype. It is a visual
reference for the Notion information architecture and fields only. V1 does
not maintain, serve, or connect that UI to the synchronization runtime.

The first run is local and reads credentials from an ignored TOML file. The
same command is later invoked by GitHub Actions. Synchronization starts
automatically when configuration is valid; there is no approval step.

## User Outcomes

- A valid local configuration can provision the required Notion databases and
  run a full synchronization with one command.
- Later runs upsert by stable Source Identity and do not create duplicates.
- A full authoritative snapshot marks missing source pages as `已删除` while
  retaining their content. Incremental runs never infer deletion from absence.
- The command exits non-zero for configuration, source, or destination
  failures and emits a structured result without secrets.
- GitHub Actions can run the same command every two hours or daily at 01:00
  Asia/Shanghai, with concurrency protection.

## Source Data

The WeRead Agent Gateway is called with `skill_version = 1.0.4` and business
parameters at the top level of each request.

- `/shelf/sync` supplies electronic books and albums.
- `/user/notebooks` is paged with `count` and `lastSort` and identifies books
  that may have annotations.
- `/book/bookmarklist` supplies personal highlights, not bookmark-only items.
- `/review/list/mine` is paged with `synckey` and supplies personal notes and
  reviews, never public reviews.
- `/book/getprogress` supplies integer progress from 0 to 100 and cumulative
  reading seconds.
- `/readdata/detail` supplies reading duration in seconds; daily records are
  normalized to local dates in the configured timezone.

An `upgrade_info` response or non-zero `errcode` blocks the source snapshot.
Authentication, rate-limit, and network failures must not trigger deletion
marking.

## Notion Data Model

The first run creates or reuses these databases under the configured parent
page:

1. `WeRead Books`: one page per book or album, with title, author, category,
   cover, state, progress, current chapter, reading seconds, last-read date,
   deep link, source ID, fingerprint, and sync status.
2. `WeRead Annotations`: one page per highlight or personal note, with type,
   relation to Books, book ID, chapter, content, range, color, created date,
   deep link, source ID, fingerprint, and sync status.
3. `WeRead Reading Days`: one page per local date, with duration seconds,
   readable duration, source period, source ID, fingerprint, and sync status.

Categories, authors, and chapters remain properties and filtered Notion views;
they are not separate databases. Reading Days intentionally have no book
relation because the supported source response does not provide reliable
per-book daily duration.

## Identity and Synchronization

| Entity | Source Identity |
| --- | --- |
| Book | `book:<bookId>` |
| Album | `album:<albumId>` |
| Highlight | `highlight:<bookmarkId>` |
| Personal note | `note:<reviewId>` |
| Reading day | `reading-day:<YYYY-MM-DD>` |

For each record, the destination is queried by Source ID only:

- no match: create one page;
- one matching page with changed source fingerprint: update it in place;
- one matching page with the same fingerprint and normal status: unchanged;
- one matching page previously marked deleted: update it in place if the
  source record reappears;
- multiple matches: fail that record and never create another page.

The coordinator processes Books before Annotations so relations can be
written. If an annotation's book is not in the current response, it resolves
the existing book page by Source Identity before writing the relation.

The coordinator rejects overlapping local runs. A full run marks destination
pages absent from the complete source snapshot as deleted. It never hard
deletes pages. A failed source snapshot skips deletion marking entirely.

## Configuration and CLI

`config/local.toml` is ignored by Git and contains:

- `weread_api_key`
- `notion_token`
- `notion_parent_page_id`
- `sync_mode`: `full` or `incremental`
- `schedule_mode`: `frequent` or `daily`
- `timezone`, default `Asia/Shanghai`

The local entry point is:

```bash
python3 -m wread2notion --config config/local.toml
```

`--mode full|incremental` overrides the file for one run. `--json` emits the
structured result only. Missing or invalid configuration prevents all remote
requests.

## GitHub Actions

The workflow maps `WEREAD_API_KEY`, `NOTION_TOKEN`, and
`NOTION_PARENT_PAGE_ID` from repository secrets. `SYNC_MODE`, `SCHEDULE_MODE`,
and `TIMEZONE` are non-secret variables or workflow defaults.

- `frequent`: cron `0 */2 * * *`;
- `daily`: cron `0 17 * * *`, which is 01:00 Asia/Shanghai;
- both schedules are present and the selected mode is applied by the command;
- a repository-scoped concurrency group prevents overlap.

## Acceptance Criteria

1. Missing configuration exits before any network call.
2. The first successful run provisions all three databases and the
   Annotations-to-Books relation.
3. Repeating an identical run creates no additional pages.
4. Changed source records update their existing page.
5. Duplicate destination Source IDs fail only the affected record.
6. Full snapshots mark absent pages as deleted; incremental snapshots do not.
7. Failed source retrieval never marks existing pages deleted.
8. Independent record failures are included in the result and do not hide
   successful records.
9. The local command and GitHub Actions invoke the same coordinator.
10. Secrets never appear in logs, JSON results, committed files, or UI code.

## Out of Scope

- Maintaining or serving the deprecated browser UI.
- Two-way synchronization or a hosted multi-user service.
- Public WeRead reviews.
- Exporting bookmark-only content, which the source endpoint does not expose.
- Separate Notion databases for categories, authors, chapters, or sync runs.
- Hard deletion of Notion pages.
