# Glossary

## WeRead

The source system that owns books, highlights, notes, reading progress, and
reading activity.

## Notion Parent Page

The existing Notion page shared with the integration under which the
application creates the Books, Highlights, and Reading Sessions databases.

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

## Sync Preview

The local UI view that compares source records with their planned Notion
representation before any write operation occurs.

## Automatic Sync Start

The local service starts a synchronization in the background after loading a
valid configuration. The UI reports its progress and result but does not gate
the write operation.

## Source Identity

The pair of source type and stable source ID used for idempotent matching,
such as `highlight:bookmarkId` or `note:reviewId`.
