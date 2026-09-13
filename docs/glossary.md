# Glossary

## WeRead

The source system that owns books, highlights, notes, reading progress, and
reading activity.

## Notion Parent Page

The existing Notion page shared with the integration under which the
application creates the Books, Annotations, and Reading Days databases.

## Books Database

One Notion row per source book, including metadata and the latest reading
progress.

## Annotations Database

One Notion row per WeRead highlight or personal note, including an annotation
type, book relation, chapter properties, source timestamps, and a deep link
back to WeRead when available.

## Reading Days Database

One Notion row per normalized daily reading summary. Weekly, monthly, and
annual statistics are views or aggregations over these rows.

## Full Synchronization

The initial import of all records in the configured scope, followed by an
incremental synchronization on later runs.

## Incremental Synchronization

A synchronization that requests records changed since the last successful
cursor or timestamp and upserts them by a stable source identity.

## Deleted Source Record

A record no longer present in WeRead. Its Notion page remains available and
is marked as deleted instead of being removed.

## Schedule Mode

The explicit workflow configuration selecting either frequent synchronization
or daily synchronization.

## Sync Result

The structured result emitted by the CLI after a run, including status, counts,
database IDs, record actions, and safe error messages.

## Automatic Sync Start

The CLI starts synchronization immediately after loading a valid
configuration. There is no approval gate or UI dependency.

## Source Identity

The pair of source type and stable source ID used for idempotent matching,
such as `highlight:bookmarkId` or `note:reviewId`.
