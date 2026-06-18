# Telephone Relay Loop Review

Date: 2026-06-16

## Scope

Reviewed `D:\.agentos\workflows\telephone-relay\sessions` and ran a fresh autonomous Agent 1 smoke test.

## Current status

The autonomous loop works:

```text
User/Tester -> Agent 1 -> monitored Agent 2 -> monitored Agent 3 -> Agent 2 -> Agent 1 -> final response
```

Fresh smoke final directive:

```text
USER:guru — return verified.
```

## Findings from session history

### 1. Stale session history can override updated profile instructions

The failed smoke used fixed child session IDs. Agent 2 continued with old history and reused the old Agent 3 launch command without `--no-extensions --no-skills`, even though the profile file had been updated.

Fix applied:

- Agent 1 now launches Agent 2 with timestamped `--session-id`.
- Agent 2 now launches Agent 3 with timestamped `--session-id`.

### 2. Extension/tool schema can break child model calls

Failed runs showed invalid schema for `pyautogui_screen` against Codex:

```text
Invalid schema for function 'pyautogui_screen'
```

Fix applied:

- Child calls now use `--no-extensions --no-skills --tools read,bash,edit,write`.

Recommendation:

- Use the same constrained tool flags for automated test invocations of Agent 1 unless explicitly testing extension compatibility.

### 3. Parent-owned wait loop is correct

Successful runs prove the parent must monitor both:

- child PID / exit code;
- shared handoff token.

Do not rely on `NEXT` as a chat-only instruction. `NEXT` is a directive to be verified through process output and shared state.

### 4. Cold start dominates runtime

Observed latest run durations from JSONL:

- Agent 1 smoke: ~87s
- Agent 2 child: ~53s
- Agent 3 child: ~13s

The letter task is trivial; most time is process/model startup and session reload.

## Speed improvements

1. **RPC warm pool**: keep Agent 1/2/3 alive in `--mode rpc`; send JSONL prompts instead of spawning `pi -p` for each hop.
2. **No child session persistence for micro-tests**: use `--no-session` for Agent 2/3 when logs are not needed. This reduces stale-history risk and may reduce overhead.
3. **Run-scoped session directories**: use `sessions/runs/<run_id>/agent-N/` so logs are grouped and lookup is faster.
4. **Reduce polling noise**: increase poll interval for long tasks; keep 1–2s only for tiny smoke tests.
5. **Provider preflight**: before running the chain, test each model with a tiny `pi -p --no-extensions --no-skills --tools read,bash,edit,write "ok"`.
6. **JSON directives**: move from free text directives to one-line JSON directives for easier parsing.

## Reliability improvements

1. Add a `run_id` to `handoff.md` and require every agent to echo it.
2. Add expected previous token + next token fields to `handoff.md`.
3. Add timeout policy per child call.
4. Add a failure receipt file per failed run, not only successful runs.
5. Use separate `handoff.md` and `handoff.lock` or atomic write pattern for higher concurrency.
6. Add a small verifier script that checks final handoff/history shape after every run.

## Testing ladder

1. **Smoke**: `g -> guru` autonomous loop.
2. **Recovery**: start from `Current token: g`, rerun Agent 1 and ensure it can continue or gives a precise recovery instruction.
3. **Bad input**: send `x`; expect no mutation.
4. **Bad handoff**: send `g` while `Current token: gu`; expect mismatch and no mutation.
5. **Extension isolation**: run once with default extensions and once with constrained tools; compare failures.
6. **Model fallback**: intentionally use a bad Agent 2 model; verify fallback instructions are clear.
7. **Payload relay**: `cascade-load-relay` 350k payload test.
8. **Coding task relay**: Agent 1 mission, Agent 2 packetization, Agent 3 one small file edit/test.

## Complexity upgrades

1. Spell a longer word/phrase with 5–7 hops.
2. Add checksum verification to each token transition.
3. Move handoff from Markdown to Markdown + JSON frontmatter.
4. Add Agent 2 chunk fan-out/fan-in for independent chunks.
5. Add a real coding task: Agent 3 edits one fixture file and returns diff/test evidence.
6. Add review pass: Agent 2 verifies Agent 3 output before Agent 1 returns.

## Recommended next implementation

Build a tiny `relay-check` verifier script or prompt that validates:

- final token is expected;
- history has expected ordered lines;
- child output directives match expected values;
- child exit files are zero;
- no stale fixed session IDs appear in latest child commands.
