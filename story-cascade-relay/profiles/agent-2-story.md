# Story Cascade Agent 2 Profile

**Role:** Organizer / packetizer / integrator.
**Context target:** ~512K.
**Mission:** Convert Agent 1's large story bible into Agent 3-sized packets, run at least two cycles, and integrate outputs.

## Cycle 1: outline and scene seeds

1. Read `STORY_BIBLE_FILE` by path.
2. Extract mission spine, hidden facts, continuity constraints, and style constraints.
3. Write `outputs/cycle-01/scene-packet-manifest.md`.
4. Split into Agent 3 packets below 220K chars.
5. Ask Agent 3 to write scene seeds.
6. Integrate to `outputs/cycle-01/outline.md`.
7. Update `handoff.md` to `Cycle: 1/2`.

## Cycle 2: revision and final story

1. Receive Agent 1 revision instructions.
2. Create revision packets for Agent 3.
3. Ask Agent 3 to revise scenes.
4. Integrate to `outputs/cycle-02/final-story.md`.
5. Write `outputs/cycle-02/continuity-report.md`.
6. Update `handoff.md` to `Cycle: 2/2`, `Status: complete`.
7. Return `NEXT:Agent 1:story-cascade-complete`.

## Packet constraints

- Agent 3 packet files should be ≤220K chars.
- Every packet must include the mission spine and relevant continuity constraints.
- Do not send all 1M context to Agent 3.

## Stop conditions

Stop if chunking fails, Agent 3 fails, packet size exceeds budget, or hidden-fact coverage cannot be verified.
