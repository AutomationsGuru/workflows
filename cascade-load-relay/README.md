# Cascade Load Relay Workflow

**Status:** Experiment v0  
**Goal:** Scale the successful `guru` telephone relay into a three-layer coding/dev Context Cascade that passes a large context payload from Agent 1 to Agent 2, then in chunks from Agent 2 to Agent 3.

## Shape

```text
User
  -> Agent 1 / Reasoner receives large context or payload path
    -> Agent 2 / Organizer receives payload path, chunks it, monitors Agent 3
      -> Agent 3 / Executor processes chunk 001 and writes output 001
      -> Agent 3 / Executor processes chunk 002 and writes output 002
      -> ...
    <- Agent 2 integrates outputs, updates handoff complete
  <- Agent 1 verifies handoff and reports to user
```

The parent agent owns the wait loop at each layer:

- Agent 1 launches Agent 2 with `pi -p`, monitors Agent 2 PID, and polls `handoff.md`.
- Agent 2 launches Agent 3 with `pi -p` once per chunk, monitors Agent 3 PID, and updates `handoff.md` after each output.
- Agent 3 processes exactly one chunk and returns to Agent 2.

## Files

- [`system-live.md`](system-live.md) — shared cascade rules.
- [`handoff.md`](handoff.md) — shared durable state.
- [`profiles/agent-1.md`](profiles/agent-1.md) — Reasoner / user-facing anchor.
- [`profiles/agent-2.md`](profiles/agent-2.md) — Organizer / chunker / integrator.
- [`profiles/agent-3.md`](profiles/agent-3.md) — Executor / per-chunk processor.
- [`prompts/`](prompts/) — optional prompt templates.
- [`payloads/sample-350k-context.md`](payloads/sample-350k-context.md) — synthetic large-context payload (~367 KB) for first test.
- `chunks/` — generated chunk files.
- `outputs/` — generated Agent 3 outputs.
- `sessions/` — Pi session files and child process logs.

## Reset before a test

From `D:\.agentos\workflows\cascade-load-relay`:

```powershell
Set-Content -LiteralPath .\handoff.md -NoNewline -Encoding utf8 -Value "# Cascade Load Relay Handoff`n`nStatus: blank`nMission:`nPayload file:`nChunk count:`nCompleted chunks:`nFinal directive:`n`nHistory:`n"
Remove-Item -Force .\chunks\chunk-*.md, .\outputs\chunk-*.md, .\outputs\integration-summary.md -ErrorAction SilentlyContinue
```

## Start Agent 1

```powershell
pi --approve --mode text --session-id cascade-load-agent-1 --session-dir .\sessions\agent-1 --name "cascade-load-agent-1" --model minimax-oauth/MiniMax-M3 --append-system-prompt .\system-live.md --append-system-prompt .\profiles\agent-1.md --prompt-template .\prompts\agent1-start.md
```

Then send:

```text
/agent1-start ./payloads/sample-350k-context.md For each chunk, produce a compact coding-context execution note with summary, constraints, and TODO-like action items.
```

Expected final response from Agent 1:

```text
USER:cascade-complete — return verified.
```

## Success criteria

- `handoff.md` contains `Status: complete`.
- `handoff.md` contains `Final directive: NEXT:Agent 1:cascade-complete`.
- `outputs/chunk-*.md` exists for every generated chunk.
- `outputs/integration-summary.md` lists all chunk outputs.
- Agent 1 returns `USER:cascade-complete — return verified.`

## First successful run

The first successful load-relay run completed in about 5 minutes:

- payload: `payloads/sample-350k-context.md` (~366,744 bytes);
- chunks: 4;
- outputs: `outputs/chunk-001.md` through `outputs/chunk-004.md` plus `outputs/integration-summary.md`;
- final directive: `USER:cascade-complete — return verified.`

Runtime notes:

- Initial Agent 2 route `xai-oauth/grok-build-0.1` failed with `403` invalid OAuth; use `openai-codex/gpt-5.5` as the known-good Agent 2 fallback until xAI OAuth is refreshed.
- Agent 3 succeeded after constraining child launches with `--no-extensions --no-skills --tools read,bash,write` to avoid an unrelated Pi extension schema error.

## Expected performance

The `guru` relay took about 90 seconds with cold Pi sessions. The first load relay took about 5 minutes for 4 chunks. Cold reload is acceptable for this experiment; warm sessions or RPC can optimize later.
