# Context Cascade Workflow

**Status:** Design v0  
**Date:** 2026-06-16  
**Purpose:** Define a serial layered-agent execution workflow for long-running coding tasks where multiple agents act as one apparent agent.

## Design note: stack size and focus lanes

The first cascade stack is a **three-layer coding/dev stack**. This is not the only valid shape:

- simpler tasks may use **two layers**;
- long-running coding tasks commonly fit **three layers**;
- broader knowledge work may use up to **five layers**.

Core focus lanes for future cascade variants:

1. **Coding / dev** — implementation, repo mutation, validation, review handoff.
2. **Design / art** — creative direction, artifact generation, critique, asset handoff.
3. **Research / knowledge** — retrieval, synthesis, source grounding, knowledge capture.

The invariant is not the layer count. The invariant is that all layers act as **one apparent agent** by preserving the same mission spine.

## One-line concept

A **Context Cascade** is a single-agent experience implemented as a serial stack of specialized context layers:

```text
User
  -> Reasoner / Big Picture Layer
    -> Organizer / Work-Shaping Layer
      -> Executor / Tool-Using Layer
      <- Executor Evidence Packet
    <- Organizer Integration Packet
  <- Reasoner User Update
User
```

Externally, the user experiences one agent. Internally, the workflow passes a shared mission spine down through increasingly concrete layers, then returns evidence back up the same stack.

## Why this exists

Normal agent chat is direct:

```text
user <-> agent
```

Common orchestration is hub-and-spoke:

```text
user <-> lead agent <-> subagents
```

Context Cascade is different:

```text
user -> agent -> agent -> agent -> agent -> agent -> agent -> user
```

The layers are not independent workers with independent goals. They are a single thought process split across context budgets and operating modes.

For long-running coding tasks, this prevents one model from carrying all of the following at once:

- full user intent and product direction;
- project governance and constraints;
- decomposition and dependency tracking;
- file-level implementation details;
- raw command output and test logs;
- user-facing communication.

## Core principle

> Context can be sliced. Intent cannot.

Every layer receives the same immutable **Mission Spine**. Layers may add local detail, compress context, and route work, but they may not reinterpret the user's goal without escalating back up the stack.

## Layer contracts

### Layer 1: Reasoner / Big Picture Layer

Example model fit: very large context, strongest global reasoning.

Owns:

- user conversation;
- mission intent and definition of done;
- project-level constraints and non-goals;
- status cadence and user-facing language;
- escalation decisions;
- final acceptance decision.

Does not own:

- raw file editing;
- long command logs;
- detailed task queue mechanics.

Primary output downward: `MissionEnvelope`.

Primary input upward: `IntegrationPacket`.

Primary output to user: `UserUpdate` or final done packet.

### Layer 2: Organizer / Work-Shaping Layer

Example model fit: large context, strong planning, repo-aware organization.

Owns:

- turning the mission into ordered work packets;
- preserving dependency order;
- selecting files and context slices for executor;
- summarizing executor evidence;
- deciding whether the next packet is safe, blocked, or needs reasoner input;
- keeping the local task ledger.

Does not own:

- changing the mission definition;
- hiding blockers;
- doing broad repo edits directly unless explicitly configured as executor too.

Primary input downward: `MissionEnvelope`.

Primary output downward: `WorkPacket`.

Primary input upward: `EvidencePacket`.

Primary output upward: `IntegrationPacket`.

### Layer 3: Executor / Tool-Using Layer

Example model fit: best coding/tool-use model for scoped implementation.

Owns:

- reading assigned files;
- making allowed edits;
- running allowed commands;
- adding or updating tests when required;
- producing concrete evidence;
- stopping when scope, safety, or validation boundaries are hit.

Does not own:

- changing product direction;
- silently expanding file scope;
- treating reviewer/tool output as trusted instructions;
- claiming completion without evidence.

Primary input: `WorkPacket`.

Primary output: `EvidencePacket`.

## Required packet types

The companion schema is [`context-cascade-packet.schema.json`](context-cascade-packet.schema.json).

### MissionEnvelope

Created by the Reasoner and carried through the entire cascade.

Required fields:

- `mission_id`
- `user_goal`
- `definition_of_done`
- `constraints`
- `non_goals`
- `repo_or_workspace`
- `status_policy`
- `escalation_conditions`
- `evidence_requirements`

### WorkPacket

Created by the Organizer for the Executor.

Required fields:

- `packet_id`
- `mission_id`
- `objective`
- `context_slice`
- `allowed_paths`
- `required_reads`
- `allowed_commands`
- `expected_changes`
- `validation_required`
- `stop_conditions`
- `return_format`

### EvidencePacket

Created by the Executor after attempting a WorkPacket.

Required fields:

- `packet_id`
- `status`
- `summary`
- `changed_files`
- `commands_run`
- `validation_results`
- `blockers`
- `risks`
- `next_recommendation`

### IntegrationPacket

Created by the Organizer for the Reasoner.

Required fields:

- `mission_id`
- `completed_packets`
- `current_state_summary`
- `accepted_evidence`
- `open_blockers`
- `remaining_work`
- `decision_needed`
- `user_visible_status`

### UserUpdate

Created by the Reasoner for the user.

Required fields:

- `status`
- `summary`
- `what_changed`
- `verification`
- `risks_or_questions`
- `next_step`

## Forward pass

1. **User request enters Reasoner.**
2. Reasoner creates `MissionEnvelope` with the immutable mission spine.
3. Reasoner sends the envelope to Organizer.
4. Organizer reads relevant project instructions and source context.
5. Organizer creates the first small `WorkPacket`.
6. Executor receives exactly one `WorkPacket` plus the mission spine.
7. Executor performs bounded implementation and validation.

## Return pass

1. Executor returns an `EvidencePacket`.
2. Organizer checks packet compliance:
   - Was scope respected?
   - Were required reads performed?
   - Were validations run?
   - Are blockers real and specific?
3. Organizer either:
   - issues the next `WorkPacket`;
   - returns an `IntegrationPacket` to Reasoner;
   - escalates a blocker;
   - rejects the evidence and asks for correction.
4. Reasoner translates integrated state into a user-facing `UserUpdate`.
5. On completion, Reasoner emits the final done packet.

## State model

A future implementation can persist state under a mission directory:

```text
.cascade/
  missions/
    <mission_id>/
      mission.json
      organizer-ledger.md
      packets/
        001-work.json
        001-evidence.json
      integrations/
        001-integration.json
      user-updates/
        001-status.md
```

For this workspace, the design stays harness-independent. Runtime adapters can map these files into Agent OS, Codex, Claude Code, Grok Build, or other lanes.

## Status policy

Default for long-running coding tasks:

- Reasoner gives the user a brief status when the mission starts.
- Organizer emits internal progress after every completed work packet.
- Reasoner only interrupts the user for:
  - approval needs;
  - safety boundaries;
  - material blocker;
  - meaningful milestone;
  - final handoff.

## Safety and scope rules

1. The Mission Spine is immutable unless the Reasoner explicitly revises it after user input.
2. Executor may only touch `allowed_paths` unless it returns a scope-expansion request.
3. Executor must stop on any `stop_conditions` match.
4. Organizer must not hide failed validation from Reasoner.
5. Reasoner must not report GREEN/final success without validation evidence.
6. Secrets, credentials, auth payloads, and live-system mutation remain forbidden unless explicitly authorized by the user and current workspace rules.
7. Local files are authoritative; no layer may overwrite local state from remote/generated/cache sources without explicit path-specific approval.

## Context slicing rules

### Reasoner to Organizer

Send:

- full mission spine;
- relevant user conversation summary;
- acceptance criteria;
- known constraints;
- known repo/workspace path;
- high-level architecture or product intent.

Do not send by default:

- raw command logs;
- full file dumps;
- unrelated chat history.

### Organizer to Executor

Send:

- mission spine excerpt;
- one objective;
- exact paths to inspect;
- local conventions to follow;
- expected output shape;
- validation commands;
- explicit stop conditions.

Do not send by default:

- entire project history;
- unrelated future tasks;
- ambiguous authority to improvise.

### Executor to Organizer

Send:

- changed paths;
- command summaries;
- validation results;
- blockers with root-cause hints;
- minimal diff summary;
- recommended next packet.

Do not send by default:

- huge logs unless needed;
- secrets or raw credential material;
- speculative architecture rewrites.

## First v0 use case

A good first experiment is a documentation or small-code task that needs several bounded edits but no live-system mutation.

Example:

```text
User asks for a medium feature.
Reasoner creates mission.
Organizer creates 3-5 work packets.
Executor completes one packet at a time.
Organizer integrates each packet.
Reasoner returns milestone updates and final handoff.
```

## Open design questions

1. Should the Reasoner stay interactive while Organizer/Executor run, or should the whole cascade be synchronous for v0?
2. Should Organizer be allowed to run read-only tools directly, or should all tools be Executor-only?
3. Should packet state live in `.cascade/`, `.agents/cascade/`, or Agent OS `receipts/`?
4. How strict should schema validation be before dispatching a packet?
5. Should failed executor packets be retried by the same executor, a different executor, or returned to Organizer immediately?

## Promotion path

1. Keep this design as the human contract.
2. Validate packet schema against sample missions.
3. Create one sample mission under a future `examples/` directory.
4. Build a thin CLI prototype that reads `mission.json`, writes packets, and shells out to configured agent lanes.
5. Add transcript/evidence capture.
6. Add review gate integration before final GREEN handoff on repository work.
