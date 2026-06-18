# RPC Warm-Pool Prototype Plan

> **For the implementing agent:** Keep this as a bounded prototype. Do not replace the direct `pi -p` relay until the RPC version passes the same `relay-check.py` verifier or an RPC-specific equivalent.

**Goal:** Reduce relay latency by keeping Agent 1, Agent 2, and Agent 3 Pi processes warm in `--mode rpc`, then sending JSONL prompt commands instead of cold-starting `pi -p` child processes.

**Architecture:** A small controller starts three long-lived Pi RPC subprocesses, one per relay role. The controller sends `prompt` JSONL commands, listens for `agent_end` / `get_last_assistant_text`, validates directives, and updates or reads `handoff.md` through agent tool calls. The controller remains a test harness; agent profiles remain the source of relay behavior.

**Tech Stack:** Python stdlib (`subprocess`, `json`, `selectors` or threads, `queue`, `pathlib`), Pi CLI `--mode rpc`, existing Markdown profiles, existing `relay-check.py`.

---

## Current baseline

- Direct autonomous smoke passes in about 87 seconds.
- Most time is cold process/model/session startup.
- Stability fixes required for child calls:
  - `--no-extensions --no-skills --tools read,bash,edit,write`
  - timestamped child `--session-id`
- `relay-check.py` is the formal verifier for current direct relay evidence.

## Prototype scope

Build a new prototype file, not a replacement:

- Create: `telephone-relay/rpc-warm-pool-prototype.py`
- Create: `telephone-relay/receipts/<timestamp>-rpc-warm-pool-*.md` after tests
- Possibly create: `telephone-relay/rpc-sessions/` for isolated RPC session dirs

Do not modify the proven `profiles/*.md` behavior unless the RPC harness exposes a profile ambiguity.

## Task plan

### Task 1: Start one RPC Pi process manually from Python

**Objective:** Prove a Python subprocess can start `pi --mode rpc` and receive a session event line.

**Command shape:**

```bash
pi --approve --mode rpc --no-extensions --no-skills --tools read,bash,edit,write --no-session --name telephone-relay-agent-3-rpc --model openai-codex/gpt-5.5 --append-system-prompt ./system-live.md --append-system-prompt ./profiles/agent-3.md
```

**Validation:**

- process starts;
- first JSON line parses;
- `get_state` command returns success.

### Task 2: Build minimal RPC client wrapper

**Objective:** Implement a tiny wrapper class:

- `start()`
- `send(command: dict)`
- `prompt(message: str)`
- `wait_agent_end(timeout_s: int)`
- `get_last_assistant_text()`
- `stop()`

**Validation:**

- Send Agent 3 `gu` against a prepared `handoff.md` with `Current token: gu`.
- Confirm output contains `NEXT:Agent 2:gur`.

### Task 3: Wire three warm agents

**Objective:** Start Agent 1/2/3 as persistent RPC processes with role profiles.

**Session choice:** Use `--no-session` for the first prototype to avoid stale history. Persist logs separately in the controller receipt.

**Validation:**

- `get_state` works for all three.
- Models match expected providers.

### Task 4: Implement controller-mediated telephone relay

**Objective:** Controller performs the same sequence without child shell launches:

1. Reset `handoff.md`.
2. Prompt Agent 1 with `g` but instruct RPC mode not to launch child shell; instead it should perform only its local write and return `NEXT:Agent 2:g`.
3. Controller validates handoff and sends `g` to Agent 2.
4. Agent 2 writes `gu` and returns `NEXT:Agent 3:gu`.
5. Controller sends `gu` to Agent 3.
6. Agent 3 writes `gur` and returns `NEXT:Agent 2:gur`.
7. Controller sends `gur` to Agent 2.
8. Agent 2 writes `guru` and returns `NEXT:Agent 1:guru`.
9. Controller sends `guru` to Agent 1.
10. Agent 1 verifies and returns `USER:guru — return verified.`

**Important:** This is a controller-mediated warm-pool relay, not the parent-owned direct shell relay. It is allowed as a speed experiment.

**Validation:**

- final handoff matches `guru`;
- expected ordered history exists;
- final Agent 1 text contains `USER:guru — return verified.`;
- elapsed time is recorded.

### Task 5: Add verifier mode

**Objective:** Extend `relay-check.py` or add an RPC-specific check that accepts controller output files instead of child `agent2-output.txt` and `agent3-output.txt`.

Preferred bounded path:

- Add optional flags to `relay-check.py`:
  - `--agent2-output <path>`
  - `--agent3-output <path>`
  - `--skip-exit-files`

**Validation:**

- Existing direct verifier still passes unchanged.
- RPC verifier passes with controller output files.

### Task 6: Compare timing

**Objective:** Record direct vs RPC timings.

**Receipt fields:**

- startup time per RPC process;
- relay execution time after warm;
- total wall-clock including warmup;
- direct baseline (~87s);
- pass/fail evidence.

## Risks / constraints

- RPC mode emits JSONL events; reader must split on `\n` only and handle partial chunks.
- Extension UI events may appear even with constrained resources; handle unknown event types safely.
- Long-lived processes need cleanup on Ctrl+C / failure.
- If agents keep context between prompts, this helps speed but may create state bleed; use fresh warm pool per run initially.
- Agent profiles currently assume child shell launch. For controller-mediated RPC, either use manual-return rules or add a small `RPC mode` section to profiles after the first proof.

## Success criteria

- `rpc-warm-pool-prototype.py` runs one full `guru` relay without cold child `pi -p` spawns.
- Final output: `USER:guru — return verified.`
- Handoff verified by `relay-check.py` or RPC-specific equivalent.
- Timing report shows whether warm RPC improves over the ~87s direct baseline.

## Non-goals

- No GUI.
- No generalized orchestrator.
- No production Agent OS integration.
- No replacement of the proven direct relay until RPC passes and is reviewed.
