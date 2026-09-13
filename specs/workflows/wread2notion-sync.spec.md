# WeRead to Notion Sync Workflow Specification

## Metadata

- Version: v0.1.0
- Status: draft
- Scope: personal local workflow before GitHub Actions deployment

## Goal

Start a full or incremental synchronization from WeRead to Notion locally,
show its state in the UI, and avoid duplicate pages through stable source
identities.

## Configuration

The local process reads a Git-ignored configuration file containing:

- `weread_api_key`
- `notion_token`
- `notion_parent_page_id`
- `sync_mode` (`full` or `incremental`)
- `schedule_mode` (`frequent` or `daily`)
- `timezone` (default `Asia/Shanghai`)

The configuration file must be validated before any remote data is fetched.
Secrets must never be rendered in the UI or written to logs.

## UI Behavior

The local UI must provide these states:

1. Configuration status: configured values are present, invalid, or missing.
2. Source preview: counts and representative records from Books,
   Annotations, Reading Days, and deleted source records.
3. Notion plan: target databases, properties, source identities, and planned
   actions (`create`, `update`, `unchanged`, `mark_deleted`).
4. Automatic run: the local service starts synchronization after valid
   configuration is loaded; the UI reports progress without an approval gate.
5. Result: created, updated, unchanged, marked-deleted, skipped, and failed
   counts with per-record errors.

The status page is read-only after the run starts. A manual re-sync endpoint
may start another run, but it does not require a confirmation step.

## Notion Data Model

### Books

One page per WeRead book. Properties include title, source identity, author,
cover, category, reading state, progress percentage, current chapter, reading
seconds, last read date, source URL, and sync status.

### Annotations

One page per WeRead highlight or personal note. Properties include title,
source identity, annotation type, relation to Books, book ID, chapter UID,
chapter name, content, range, color, created date, source URL, and sync status.

### Reading Days

One page per daily reading aggregate. Properties include date, source
identity, duration seconds, formatted duration, source period, and sync
status. It does not include a book relation because the source API does not
provide reliable per-book daily duration.

Categories, authors, and chapters are properties and filtered views, not
separate databases.

## Identity and Deduplication

Each normalized record has a unique source identity:

| Entity | Identity |
|---|---|
| Book | `book:<bookId>` |
| Highlight | `highlight:<bookmarkId>` |
| Personal note | `note:<reviewId>` |
| Daily reading summary | `reading-day:<YYYY-MM-DD>` |

The sync engine queries Notion by source identity and upserts the matching
page. It must not match by title, author, or note text. Overlapping local sync
requests must be rejected or serialized.

## Preconditions

- The local configuration file exists and passes validation.
- The WeRead API key and Notion token are non-empty.
- The Notion parent page ID is configured.
- The source adapter can retrieve the required records.
- The Notion integration can read and write the configured parent page.
- The source and target clients are available.
- The local service has started a run with a valid configuration.

## Postconditions

- Every successfully synchronized record has at most one Notion page for its
  source identity.
- Updates modify the existing page instead of creating a second page.
- Deleted source records remain in Notion with a deleted status.
- A failed record does not prevent independent records from being reported.
- No Notion write occurs when configuration validation fails.

## Failure Modes

- Missing or invalid local configuration: block preview and report fields.
- WeRead authentication or rate limiting: show an actionable error and do not
  partially approve a stale preview.
- Notion permission failure: show the parent page/database requirement.
- Duplicate Notion matches for one source identity: block that record and
  report it for manual cleanup; do not create another page.
- Network interruption during write: retry safely through idempotent upsert
  and report unresolved records.

## Test Cases

1. Missing configuration blocks the preview and exposes no secret values.
2. A full preview includes all configured source records.
3. An existing source identity is classified as `update` or `unchanged`, not
   `create`.
4. A deleted source record is classified as `mark_deleted`.
5. Repeating the same sync does not increase Notion page count.
6. Duplicate Notion matches block only the affected identity.
7. Loading the status page does not start a second run while one is active.
8. A missing configuration reports an error and performs no Notion write.
