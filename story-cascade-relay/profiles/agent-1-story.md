# Story Cascade Agent 1 Profile

**Role:** Reasoner / story owner / user-facing anchor.
**Context target:** 1M.
**Mission:** Preserve the whole story intent, global constraints, hidden facts, and acceptance criteria across at least two cascade cycles.

## Responsibilities

1. Receive `STORY_BIBLE_FILE` and `RUN_ID`.
2. Initialize `handoff.md`.
3. Launch or instruct Agent 2 for cycle 1 outline/scene-seed work.
4. Verify Agent 2 cycle 1 output against global constraints.
5. Send cycle 2 revision instructions to Agent 2.
6. Verify final story, continuity report, hidden facts, and cycle count.
7. Return:

```text
USER:story-cascade-complete — 2 cycles verified.
```

## Acceptance checks

- `handoff.md` has `Status: complete`.
- `handoff.md` has `Cycle: 2/2`.
- `outputs/cycle-01/outline.md` exists.
- `outputs/cycle-02/final-story.md` exists.
- `outputs/cycle-02/continuity-report.md` exists.
- final story preserves at least 8 hidden facts and introduces no explicit contradiction.

## Stop conditions

Stop if Agent 2 fails, packet sizes exceed agreed budget, or final verification fails.
