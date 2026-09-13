# Issue Tracker: GitHub

Issues and specs for this repository live as GitHub Issues in
`ZicaiLiao/weread2notion-pro`. Use the `gh` CLI for issue operations.

## Conventions

- Create an issue with `gh issue create`.
- Read an issue with `gh issue view <number> --comments`.
- List issues with `gh issue list` and include labels when selecting work.
- Apply or remove labels with `gh issue edit <number> --add-label` or
  `--remove-label`.
- Close an issue with `gh issue close` after posting any resolution comment.

PRs are not a request surface for triage in this repository.

When a skill says to publish to the issue tracker, create a GitHub Issue in
this repository. When a skill says to publish blocking edges, prefer GitHub's
native issue dependencies; if unavailable, include explicit `Blocked by` text
in the issue body.
