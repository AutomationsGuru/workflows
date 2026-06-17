# First Story Cascade Run Plan

## Goal

Run Smoke A: two-cycle story relay using `contexts/story-bible-1m.md`.

## Target result

```text
USER:story-cascade-complete — 2 cycles verified.
```

## Bounded execution plan

1. Reset `handoff.md`.
2. Agent 1 receives:

   ```text
   RUN_ID: story-smoke-001
   STORY_BIBLE_FILE: ./contexts/story-bible-1m.md
   CYCLES: 2
   SCENES: 6
   ```

3. Agent 1 launches Agent 2 for cycle 1.
4. Agent 2 creates ≤220K Agent 3 packets and scene-seed manifest.
5. Agent 3 writes scene seeds under `outputs/cycle-01/`.
6. Agent 2 writes `outputs/cycle-01/outline.md` and returns to Agent 1.
7. Agent 1 sends cycle 2 revision constraints.
8. Agent 2 creates revision packets.
9. Agent 3 writes revised scenes under `outputs/cycle-02/scenes/`.
10. Agent 2 writes:
    - `outputs/cycle-02/final-story.md`
    - `outputs/cycle-02/continuity-report.md`
11. Agent 1 verifies and returns final directive.

## Verification checklist

- [ ] `handoff.md` has `Status: complete`.
- [ ] `handoff.md` has `Cycle: 2/2`.
- [ ] packet files are ≤220K chars.
- [ ] final story exists.
- [ ] continuity report exists.
- [ ] at least 8/10 hidden facts preserved.
- [ ] no explicit hidden-fact contradiction.

## Stop conditions

- Any agent exceeds packet budget.
- Agent 3 fails to write output.
- Cycle 1 does not return to Agent 1.
- Cycle 2 does not return to Agent 1.
- Hidden-fact verification fails.
