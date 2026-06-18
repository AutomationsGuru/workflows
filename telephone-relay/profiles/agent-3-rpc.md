# Telephone Relay Agent 3 RPC Profile

**Role:** RPC warm-pool pivot relay.

## Pivot rule

If incoming token is exactly `gu`:

1. Read `handoff.md`.
2. Verify `Current token: gu`.
3. Set `Current token: gur`.
4. Append:

```markdown
- Agent 3 received `gu`, verified `gu` in handoff, wrote `gur`, sent `gur` to Agent 2.
```

5. End with exactly:

```text
NEXT:Agent 2:gur
```

## Stop conditions

Stop without writing if token is not `gu`, or if the handoff token does not match the rule.
