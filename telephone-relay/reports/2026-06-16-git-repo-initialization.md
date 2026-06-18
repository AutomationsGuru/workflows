# Workflow Bridge Git Repository Initialization

Date: 2026-06-16

## Scope

Initialized `D:\.agentos\workflows` as the git repository for the workflow bridge surface so CodeRabbit can review committed changes.

## Included in source commit

- workflow bridge docs and schemas;
- Telephone Relay bridge v1/v2 source files;
- persistent warm-pool source files and logical tests;
- cascade-load and story-cascade workflow source/spec files;
- plans, reports, receipts, profiles, prompts, and examples.

## Ignored runtime artifacts

The repository intentionally ignores generated/runtime directories:

- `**/sessions/`
- `**/rpc-runs/`
- `**/bridge-runs/`
- `**/bridge-v2-runs/`
- `**/diagnostics/`
- `**/persistent-pool-runs/`
- `__pycache__/`

These remain on disk as local evidence but are not committed as source.

## Commit

Initial commit message:

```text
chore: initialize workflow bridge repository
```

## Notes

This slice did not add bridge features and did not migrate to v2. It only created a git boundary, added ignore rules, and committed the current source bridge surface for review.
