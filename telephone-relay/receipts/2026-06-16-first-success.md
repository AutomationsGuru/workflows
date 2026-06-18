# Telephone Relay First Successful Run

Date: 2026-06-16

## Result

`guru` relay succeeded.

Final user-facing directive:

```text
USER:guru — return verified.
```

## Observed flow

```text
User -> Agent 1
Agent 1 -> monitored Agent 2 child Pi process
Agent 2 -> monitored Agent 3 child Pi process
Agent 3 -> Agent 2
Agent 2 -> Agent 1
Agent 1 -> User
```

## Evidence summary

- Agent 1 received `g`.
- Agent 1 wrote `Current token: g` to `handoff.md`.
- Agent 1 launched Agent 2 via `pi -p` and monitored the child PID plus `handoff.md`.
- Agent 2 launched Agent 3 via `pi -p` and completed the downstream relay.
- Agent 1 monitor observed `Current token: guru` while Agent 2 was running.
- Agent 2 returned `NEXT:Agent 1:guru` with exit code `0`.
- Agent 1 verified `Current token: guru` in `handoff.md`.
- Agent 1 appended final history and returned `USER:guru — return verified.`

## Timing

Approximate elapsed time: 90 seconds.

Reason: cold Pi session reloads. This was expected and acceptable for v0. The path between Agent 2 and Agent 3 was warmer than full three-way chat would be, because Agent 1 relied on final handoff changes instead of a live three-way chat.

## Design lesson

The parent agent must own the wait loop. Emitting `NEXT` is not enough. The parent must monitor the child process and shared state before returning to the user.
