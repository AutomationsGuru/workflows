# Direct Pi Commands for Telephone Relay

This file intentionally uses direct `pi` CLI invocations only. No wrapper scripts.

## Pi options confirmed

Checked with `pi --help` on 2026-06-16.

Relevant options:

| Option | Meaning |
| --- | --- |
| `--system-prompt <text>` | Replace Pi's default system prompt. |
| `--append-system-prompt <text-or-file>` | Append text or file contents to the system prompt. Can be repeated. |
| `--mode <text|json|rpc>` | Output mode. `text` is default. `rpc` is for JSONL stdin/stdout control. |
| `--print`, `-p` | Non-interactive one-shot. Required for child relay calls so parent agents can wait. |
| `--session <path|id>` | Use an existing session file or partial UUID. |
| `--session-id <id>` | Use an exact project session ID, creating it if missing. |
| `--session-dir <dir>` | Directory for session storage and lookup. |
| `--name <name>` | Human-readable session display name. |
| `--prompt-template <path>` | Load a prompt template file or directory. Invoke templates with `/prompt-name`. |
| `--model <provider/model>` | Select the model. |
| `--approve` | Trust project-local files for this run. |

Notes:

- Use `--session-id` for stable relay identities.
- Use `--session <id-or-path>` when resuming an already-created session by ID/path.
- Parent-to-child calls use `pi -p` so the parent process waits for child completion.
- Parent agents launch child calls inside local monitor loops: the parent checks the child PID and polls `handoff.md` until the child exits.
- Agent 1 is the only human-facing interactive session in the autonomous v0.
- Agent 2 and Agent 3 are launched by parent agents as foreground child Pi calls.
- Child one-shot launches use timestamped `--session-id` values to avoid stale history from earlier failed/successful runs.
- For this relay, interactive `--mode text` is the simplest starting point. `--mode rpc` is the likely next step for a controller.

## Reset the handoff

From `D:\.agentos\workflows\telephone-relay`:

```powershell
Set-Content -LiteralPath .\handoff.md -NoNewline -Encoding utf8 -Value "# Telephone Relay Handoff`n`nCurrent token:`n`nHistory:`n"
```

## Autonomous flow

Start only Agent 1 interactively:

```powershell
pi --approve `
  --mode text `
  --session-id telephone-relay-agent-1 `
  --session-dir .\sessions\agent-1 `
  --name "telephone-relay-agent-1" `
  --model minimax-oauth/MiniMax-M3 `
  --append-system-prompt .\system-live.md `
  --append-system-prompt .\profiles\agent-1.md `
  --prompt-template .\prompts\prompt1.md `
  --prompt-template .\prompts\prompt5.md
```

Then type either:

```text
g
```

or:

```text
/prompt1
```

Agent 1 should:

1. verify blank `handoff.md`;
2. write `Current token: g`;
3. launch Agent 2 with `pi -p` inside a monitor loop;
4. check that Agent 2 is still running while polling `handoff.md`;
5. wait for Agent 2 to complete the downstream relay;
6. verify `handoff.md` contains `Current token: guru`;
7. reply to you:

```text
USER:guru — return verified.
```

## Child command: Agent 1 launches Agent 2

Agent 1 should run this monitored child command from the relay root:

```bash
mkdir -p ./sessions/agent-1
run_id=$(date +%Y%m%d%H%M%S)
rm -f ./sessions/agent-1/agent2-output.txt ./sessions/agent-1/agent2-exit.txt
(pi -p --approve --mode text --no-extensions --no-skills --tools read,bash,edit,write --session-id "telephone-relay-agent-2-$run_id" --session-dir ./sessions/agent-2 --name "telephone-relay-agent-2-$run_id" --model openai-codex/gpt-5.5 --append-system-prompt ./system-live.md --append-system-prompt ./profiles/agent-2.md "g" > ./sessions/agent-1/agent2-output.txt 2>&1; echo $? > ./sessions/agent-1/agent2-exit.txt) &
child_pid=$!
while kill -0 "$child_pid" 2>/dev/null; do
  current_token=$(grep -m1 '^Current token:' ./handoff.md || true)
  echo "Agent 1 monitor: Agent 2 pid $child_pid running; ${current_token:-Current token: <missing>}"
  sleep 2
done
wait "$child_pid" || true
cat ./sessions/agent-1/agent2-output.txt
echo "Agent 2 exit code: $(cat ./sessions/agent-1/agent2-exit.txt 2>/dev/null || echo missing)"
```

Expected child output back to Agent 1:

```text
NEXT:Agent 1:guru
```

## Child command: Agent 2 launches Agent 3

Agent 2 should run this monitored child command from the relay root:

```bash
mkdir -p ./sessions/agent-2
run_id=$(date +%Y%m%d%H%M%S)
rm -f ./sessions/agent-2/agent3-output.txt ./sessions/agent-2/agent3-exit.txt
(pi -p --approve --mode text --no-extensions --no-skills --tools read,bash,edit,write --session-id "telephone-relay-agent-3-$run_id" --session-dir ./sessions/agent-3 --name "telephone-relay-agent-3-$run_id" --model openai-codex/gpt-5.5 --append-system-prompt ./system-live.md --append-system-prompt ./profiles/agent-3.md "gu" > ./sessions/agent-2/agent3-output.txt 2>&1; echo $? > ./sessions/agent-2/agent3-exit.txt) &
child_pid=$!
while kill -0 "$child_pid" 2>/dev/null; do
  current_token=$(grep -m1 '^Current token:' ./handoff.md || true)
  echo "Agent 2 monitor: Agent 3 pid $child_pid running; ${current_token:-Current token: <missing>}"
  sleep 2
done
wait "$child_pid" || true
cat ./sessions/agent-2/agent3-output.txt
echo "Agent 3 exit code: $(cat ./sessions/agent-2/agent3-exit.txt 2>/dev/null || echo missing)"
```

Expected child output back to Agent 2:

```text
NEXT:Agent 2:gur
```

## Manual fallback flow

If the autonomous child calls fail, run each session manually:

1. Agent 1: send `g`; expect it to write `g` and attempt child Agent 2.
2. Agent 2 one-shot manually:

   ```powershell
   $runId = Get-Date -Format yyyyMMddHHmmss
   pi -p --approve --mode text --no-extensions --no-skills --tools read,bash,edit,write --session-id "telephone-relay-agent-2-$runId" --session-dir .\sessions\agent-2 --name "telephone-relay-agent-2-$runId" --model openai-codex/gpt-5.5 --append-system-prompt .\system-live.md --append-system-prompt .\profiles\agent-2.md "g"
   ```

3. If needed, Agent 3 one-shot manually:

   ```powershell
   $runId = Get-Date -Format yyyyMMddHHmmss
   pi -p --approve --mode text --no-extensions --no-skills --tools read,bash,edit,write --session-id "telephone-relay-agent-3-$runId" --session-dir .\sessions\agent-3 --name "telephone-relay-agent-3-$runId" --model openai-codex/gpt-5.5 --append-system-prompt .\system-live.md --append-system-prompt .\profiles\agent-3.md "gu"
   ```

4. Return to Agent 1 and send `guru` only if `handoff.md` already reads `Current token: guru`.

## JSON/RPC note

For machine-readable event output, use `--mode json` instead of `--mode text` on one-shot calls.

For a future relay controller, use `--mode rpc` and send JSONL commands like:

```json
{"type":"prompt","message":"g"}
```
