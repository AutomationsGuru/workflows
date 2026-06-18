# Telephone Relay Autonomous Smoke After Session-ID Fix

Date: 2026-06-16

## Result

Autonomous `guru` relay succeeded from a direct Agent 1 one-shot invocation.

Final output:

```text
guru — Agent 2 child returned `NEXT:Agent 1:guru`, handoff verified `Current token: guru`.

USER:guru — return verified.
```

## Command shape

Agent 1 was run with:

- `--no-extensions --no-skills --tools read,bash,edit,write`
- unique top-level smoke session id
- Agent 1 profile appended
- input token `g`

Agent 1 launched Agent 2; Agent 2 launched Agent 3.

## Evidence

- `handoff.md` final token: `Current token: guru`
- `sessions/agent-1/agent2-output.txt`: `NEXT:Agent 1:guru`
- `sessions/agent-2/agent3-output.txt`: `NEXT:Agent 2:gur`
- Latest Agent 1 smoke session duration from JSONL: about 87 seconds
- Latest Agent 2 child session duration from JSONL: about 53 seconds
- Latest Agent 3 child session duration from JSONL: about 13 seconds

## Fix validated

The run succeeded after two stability improvements:

1. Child calls use `--no-extensions --no-skills --tools read,bash,edit,write`.
2. Child calls use timestamped session IDs so stale child-session history cannot reuse old commands.
