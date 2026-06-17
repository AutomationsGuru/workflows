# Telephone Relay Workflow

**Status:** v0 experiment
**Goal:** Prove that three agent profiles can behave like one simple relay by spelling `guru` through a shared Markdown handoff file.

This is intentionally tiny. No orchestration, no queue, no schema, no wrapper script. Just direct Pi sessions:

```text
User -> Agent 1 -> Agent 2 -> Agent 3 -> Agent 2 -> Agent 1 -> User
```

Each agent must verify two things before acting:

1. the message it received from the previous hop; and
2. the current token written in [`handoff.md`](handoff.md).

If both match its trigger, the agent appends exactly one letter, updates `handoff.md`, and passes the new token to the next agent. In autonomous mode, Agent 1 launches Agent 2 as a synchronous child Pi call and waits; Agent 2 launches Agent 3 as a synchronous child Pi call and waits; then the return path unwinds back to Agent 1.

## Guru relay path

| Hop | Receiver | Received token | Required file token before acting | Action | Sends to |
| --- | --- | --- | --- | --- | --- |
| 1 | Agent 1 | `g` | blank | write `g` | Agent 2 |
| 2 | Agent 2 | `g` | `g` | append `u` -> `gu` | Agent 3 |
| 3 | Agent 3 | `gu` | `gu` | append `r` -> `gur` | Agent 2 |
| 4 | Agent 2 | `gur` | `gur` | append `u` -> `guru` | Agent 1 |
| 5 | Agent 1 | `guru` | `guru` | respond to user: `guru` | User |

## Direct Pi profile chats

There are no wrapper scripts. Use direct `pi` commands from this folder.

Full command details are in [`direct-pi-commands.md`](direct-pi-commands.md).

Default model slots:

| Agent | Default Pi model |
| --- | --- |
| Agent 1 | `minimax-oauth/MiniMax-M3` |
| Agent 2 | `xai-oauth/grok-build-0.1` |
| Agent 3 | `openai-codex/gpt-5.5` |

Fast start for Agent 1:

```powershell
pi --approve --mode text --session-id telephone-relay-agent-1 --session-dir .\sessions\agent-1 --name "telephone-relay-agent-1" --model minimax-oauth/MiniMax-M3 --append-system-prompt .\system-live.md --append-system-prompt .\profiles\agent-1.md --prompt-template .\prompts\prompt1.md --prompt-template .\prompts\prompt5.md
```

Then type `g` or `/prompt1`.

Keep this Agent 1 chat open. Agent 1 is the user-facing anchor: after you send `g`, it should write `g`, run Agent 2 with `pi -p`, monitor the Agent 2 child PID while polling `handoff.md`, wait while Agent 2 runs and monitors Agent 3, then re-read `handoff.md`. Child Pi calls are constrained with `--no-extensions --no-skills --tools read,bash,edit,write` to avoid unrelated extension schema failures, and use timestamped child `--session-id` values to avoid stale history from earlier runs. Only after `handoff.md` reads `Current token: guru` should Agent 1 report:

```text
USER:guru — return verified.
```

Autonomous loop:

1. Agent 1 chat: send `g` or `/prompt1`.
2. Agent 1 writes `g`, launches Agent 2 as a child process, and monitors Agent 2 while polling `handoff.md`.
3. Agent 2 writes `gu`, launches Agent 3 as a child process, and monitors Agent 3 while polling `handoff.md`.
4. Agent 3 writes `gur` and returns `NEXT:Agent 2:gur`.
5. Agent 2 resumes, writes `guru`, and returns `NEXT:Agent 1:guru`.
6. Agent 1 resumes, verifies `Current token: guru`, and returns `USER:guru — return verified.`

## Files

- [`direct-pi-commands.md`](direct-pi-commands.md) — exact direct Pi commands and option notes.
- [`system-live.md`](system-live.md) — shared system-level rules appended to every relay session.
- [`handoff.md`](handoff.md) — the only durable shared state for the experiment.
- [`profiles/agent-1.md`](profiles/agent-1.md) — start/finish relay profile for the proven direct relay.
- [`profiles/agent-2.md`](profiles/agent-2.md) — middle relay profile for the proven direct relay.
- [`profiles/agent-3.md`](profiles/agent-3.md) — pivot profile for the proven direct relay.
- [`profiles/agent-1-rpc.md`](profiles/agent-1-rpc.md), [`profiles/agent-2-rpc.md`](profiles/agent-2-rpc.md), [`profiles/agent-3-rpc.md`](profiles/agent-3-rpc.md) — controller-mediated RPC warm-pool profiles.
- [`prompts/prompt1.md`](prompts/prompt1.md) through [`prompts/prompt5.md`](prompts/prompt5.md) — optional Pi prompt templates for each hop.
- [`relay-check.py`](relay-check.py) — formal verifier for final handoff, ordered history, child outputs/exits, and stale child session IDs; also supports RPC output overrides.
- [`rpc-warm-pool-prototype.py`](rpc-warm-pool-prototype.py) — bounded RPC speed prototype; does not replace the direct relay.
- [`bridge-runner.py`](bridge-runner.py) — v1 bridge wrapper that tries RPC first and falls back to the proven direct relay.
- [`rpc_bridge_v2.py`](rpc_bridge_v2.py) and [`rpc-bridge-v2.md`](rpc-bridge-v2.md) — typed v2 bridge API with channel routing, retry/backoff, call stats, and v1 fallback.
- [`rpc_bridge_v2_selftest.py`](rpc_bridge_v2_selftest.py) — fast fake-transport self-test for v2 retry and fallback behavior.
- [`rpc-latency-diagnostic.py`](rpc-latency-diagnostic.py) — one-agent RPC cold/warm, first-byte, connection, and prompt timing diagnostic.
- [`warm-pool-cleanup-selftest.py`](warm-pool-cleanup-selftest.py) — process-tree cleanup self-test that proves spawned children are not leaked.
- [`pool-scale-test.py`](pool-scale-test.py) — logical persistent-pool scale test for 100 tenant acquire/release paths, cap enforcement, and leak checks.
- [`pool-api-reference.md`](pool-api-reference.md) — persistent warm-pool API reference covering config, sizing, cap, metrics, persistence, and examples.
- [`latency-budget.md`](latency-budget.md) — current latency budget, observed baseline, and regression signals.
- [`examples/guru-completed.md`](examples/guru-completed.md) — expected completed handoff shape.
- [`receipts/`](receipts/) — successful run receipts and verifier output.
- [`rpc-runs/`](rpc-runs/) — RPC prototype run evidence.
- [`reports/2026-06-16-loop-review.md`](reports/2026-06-16-loop-review.md) — loop review, speed/reliability improvements, and testing ladder.
- [`reports/2026-06-16-rpc-warm-pool-gap-analysis.md`](reports/2026-06-16-rpc-warm-pool-gap-analysis.md) — HERE > THERE gap analysis after the RPC prototype.
- [`reports/2026-06-16-bridge-runner-integration.md`](reports/2026-06-16-bridge-runner-integration.md) — bridge wrapper integration evidence and HERE > THERE notes.
- [`reports/2026-06-16-rpc-bridge-v2-self-review.md`](reports/2026-06-16-rpc-bridge-v2-self-review.md) — focused self-review findings and bounded patch notes for RPC Bridge v2.
- [`plans/2026-06-16-rpc-warm-pool-prototype-plan.md`](plans/2026-06-16-rpc-warm-pool-prototype-plan.md) — RPC speed prototype plan.
- [`plans/2026-06-16-rpc-bridge-v2-migration-plan.md`](plans/2026-06-16-rpc-bridge-v2-migration-plan.md) — migration ordering, rollback, and smoke checks for moving callers from v1 to v2.

## Verifier

Run the direct relay verifier:

```powershell
python .\relay-check.py
```

Run a one-agent latency diagnostic:

```powershell
python .\rpc-latency-diagnostic.py --timeout 120
```

Run the process-tree cleanup self-test:

```powershell
python .\warm-pool-cleanup-selftest.py --timeout 5
```

Run the logical pool scale test:

```powershell
python .\pool-scale-test.py --tenants 100 --pool-size 1
```

Run the bridge wrapper with RPC preferred and direct fallback available:

```powershell
python .\bridge-runner.py --timeout 300
```

Run the RPC Bridge v2 self-test:

```powershell
python .\rpc_bridge_v2_selftest.py
```

Run RPC Bridge v2 through v1 fallback/default routing:

```powershell
python .\rpc_bridge_v2.py --run-id demo-v2-v1 --timeout 300
```

Force the direct fallback path for proof:

```powershell
python .\bridge-runner.py --timeout 300 --force-direct
```

Run the RPC evidence verifier for the current successful warm-pool run:

```powershell
python .\relay-check.py --agent2-output .\rpc-runs\20260616-212211\outputs\agent2-return.txt --agent3-output .\rpc-runs\20260616-212211\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
```

## Reset

Before a fresh run, reset `handoff.md` to:

```markdown
# Telephone Relay Handoff

Current token:

History:
```

Then send `g` to Agent 1.
