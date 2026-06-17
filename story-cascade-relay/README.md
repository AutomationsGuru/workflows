# Story Cascade Relay Smoke Tests

**Status:** Design + runnable test spec v0  
**Purpose:** Exercise multi-cycle Context Cascade behavior with a creative story task while preserving the coding/dev bridge lessons: file-path payloads, deterministic chunking, verifier-backed handoff, and parent-owned completion.

## Why story?

A story smoke is good because it tests more than token relay:

- long-range continuity;
- style constraints;
- facts hidden in large context;
- multi-step synthesis;
- iterative improvement across cycles;
- whether Agent 2 can compress Agent 1's large context into Agent 3-sized work packets.

## Target stack

```text
Agent 1 / Reasoner / 1M context
  owns story bible, hidden facts, global constraints, final acceptance

Agent 2 / Organizer / ~512K context
  receives large context path, splits into Agent 3 packets, tracks continuity

Agent 3 / Executor / ~272K context
  drafts bounded scene/output packets from one chunk at a time
```

## Minimum target

At least **2 full cascade cycles**:

```text
Cycle 1: outline + scene seeds
User -> Agent 1 -> Agent 2 -> Agent 3... -> Agent 2 -> Agent 1

Cycle 2: revision + continuity pass
Agent 1 -> Agent 2 -> Agent 3... -> Agent 2 -> Agent 1 -> User
```

This proves the stack can do more than one descent/return and can use the first cycle's artifacts as context for the second.

## Context narrowing target

- Agent 1 can hold or reference ~1M context.
- Agent 2 receives the large context by file path and slices it into ≤512K working context.
- Agent 3 receives packets sized below 272K.

Do **not** inline the full 1M payload into child prompts. Pass file paths and chunk paths.

## Files

- [`test-suite.md`](test-suite.md) — advanced smoke/context test suite.
- [`handoff.md`](handoff.md) — durable shared state for story runs.
- [`profiles/`](profiles/) — role-specific test profiles.
- [`prompts/`](prompts/) — optional prompt templates.
- [`contexts/`](contexts/) — generated or supplied large story bibles.
- [`outputs/`](outputs/) — generated outlines/scenes/revisions.
- [`reports/`](reports/) — analysis and results.

## First recommended smoke

Run a **2-cycle story relay**:

1. Agent 1 receives a 1M-ish story bible path.
2. Agent 1 asks Agent 2 to make a 6-scene outline.
3. Agent 2 chunks the bible into Agent 3 packets.
4. Agent 3 drafts scene seeds per packet.
5. Agent 2 integrates a cycle-1 outline and returns to Agent 1.
6. Agent 1 issues cycle-2 continuity/revision constraints.
7. Agent 2 routes scene revision packets to Agent 3.
8. Agent 3 writes revised scenes.
9. Agent 2 writes final story packet and checksum.
10. Agent 1 verifies continuity and returns final directive.

Expected final directive:

```text
USER:story-cascade-complete — 2 cycles verified.
```
