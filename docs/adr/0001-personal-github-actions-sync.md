# ADR-0001: Personal WeRead to Notion Synchronization

## Status

Accepted

## Context

The first version synchronizes one user's WeRead highlights, notes, reading
history, and reading progress into Notion. The repository currently has no
implementation code.

## Decisions

1. GitHub Actions is the runtime and scheduler for the personal version.
2. Synchronization is one-way: WeRead is the source of truth and Notion is
   the destination.
3. The default schedule is configurable. The frequent mode runs every two
   hours; the daily mode runs at 01:00 Asia/Shanghai, represented as 17:00
   UTC in GitHub Actions.
4. The Notion workspace uses three databases aligned with the UI:
   - Books
   - Annotations (highlights and personal notes)
   - Reading Days (daily reading aggregates)
5. The application provisions the three databases and the Annotations-to-Books
   relation on the first run under a user-provided Notion parent page.
6. Credentials are supplied through GitHub Actions secrets and are not stored
   in the repository.
7. Every Notion record includes a source type and stable source ID. Books use
   `bookId`, highlights use `bookmarkId`, personal notes use `reviewId`, and
   daily reading summaries use the local calendar date as their identity.
8. Synchronization is an idempotent upsert. The workflow uses a concurrency
   group so overlapping GitHub Actions runs cannot create the same page at
   the same time. Existing pages are looked up by source identity before a
   create operation.
9. Reading Days represent daily aggregates because the available reading
   statistics API exposes bucketed durations, not individual reading-session
   events. Weekly, monthly, and annual statistics are views over these daily
   records, not additional databases.
10. If a source highlight, note, or book is deleted in WeRead, its Notion
    page is retained and marked as deleted. Synchronization never hard-deletes
    source records.
11. Development starts with a local workflow. Credentials are read from a
    local configuration file that is ignored by Git; the same settings will
    later be mapped to GitHub Actions secrets and variables.
12. A local browser UI shows source records, target Notion properties, and
    create/update/deleted actions. Synchronization starts automatically when
    the local service starts; the UI does not require an approval click.

## Consequences

- The user must provide a Notion parent page shared with the integration.
- The workflow cannot automatically change its cron expression based on an
  external API quota. Schedule mode is therefore an explicit configuration.
- The first synchronization must be idempotent so retries do not duplicate
   Notion pages.
- Notion does not enforce uniqueness on arbitrary properties, so duplicate
  prevention is implemented in the sync adapter and reinforced by workflow
  concurrency control.
- Categories, authors, and chapters are properties and filtered views rather
  than independent databases.

## Open Questions

- Which Notion parent page should own the generated databases?
