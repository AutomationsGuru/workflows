# Telephone Relay Agent 2 RPC Profile

**Role:** RPC warm-pool middle relay.

## Forward rule

If incoming token is exactly `g`:

1. Read `handoff.md`.
2. Verify `Current token: g`.
3. Set `Current token: gu`.
4. Append:

```markdown
- Agent 2 received `g`, verified `g` in handoff, wrote `gu`, sent `gu` to Agent 3.
```

5. End with exactly:

```text
NEXT:Agent 3:gu
```

## Return rule

If incoming token is exactly `gur`:

1. Read `handoff.md`.
2. Verify `Current token: gur`.
3. Set `Current token: guru`.
4. Append:

```markdown
- Agent 2 received downstream `gur`, verified `gur` in handoff, wrote `guru`, sent `guru` to Agent 1.
```

5. End with exactly:

```text
NEXT:Agent 1:guru
```

## Stop conditions

Stop without writing if token is not `g` or `gur`, or if the handoff token does not match the rule.
