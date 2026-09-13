# WeRead to Notion Sync Workflow Specification

## Metadata

- Version: v1.0.0
- Status: implementation-ready
- Scope: local CLI first, GitHub Actions second

## Command Flow

1. Load and validate the ignored TOML configuration.
2. Construct the WeRead source client and Notion destination client.
3. Fetch a complete source snapshot for the configured sync mode.
4. Provision or discover Books, Annotations, and Reading Days under the
   configured Notion parent page.
5. Upsert Books, then Annotations, then Reading Days by Source Identity.
6. In full mode, list destination pages and mark missing source IDs deleted.
7. Emit a JSON-compatible result and exit non-zero when the run failed.

The deprecated `static/` UI is not part of this flow. The command begins
automatically after valid configuration is loaded and requires no approval.

## Configuration

Required values are `weread_api_key`, `notion_token`, and
`notion_parent_page_id`. Optional values are `sync_mode`, `schedule_mode`,
`timezone`, and `reading_start_year`. Secrets are never printed.

## Idempotency

Destination lookup uses the database plus the exact `Source ID` property. A
title, author, content, or cover is never used as an identity. One match is
updated or skipped by fingerprint; multiple matches fail that record. A
reappearing deleted record is restored by writing its current source-owned
properties and normal sync status.

## Deletion Semantics

Only a successfully fetched full snapshot is authoritative for deletion. A
missing page is retained and patched with `Sync Status = 已删除`; Books also
receive `State = 已删除`. Incremental runs never mark a page deleted because
it was absent from a partial response.

## Failure Semantics

- Invalid configuration: exit before source or destination requests.
- Source authentication, rate limiting, upgrade, malformed response, or
  network failure: fail the run and skip deletion marking.
- Destination permission or network failure: fail the affected operation and
  report it; record-level failures do not hide independent records.
- Overlapping local runs: return `already_running` without writing.

## Local Verification

```bash
cp config/local.example.toml config/local.toml
# fill the three credentials and optional settings
python3 -m wread2notion --config config/local.toml --mode full --json
```

The first local full run is the verification point before enabling the
workflow. Do not commit `config/local.toml`.

## Scheduled Verification

The GitHub Actions workflow uses the same module entry point, repository
secrets, a repository-scoped concurrency group, and either `0 */2 * * *` or
`0 17 * * *` depending on the selected schedule configuration.
