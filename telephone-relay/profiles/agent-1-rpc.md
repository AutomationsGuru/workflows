# Telephone Relay Agent 1 RPC Profile

**Role:** RPC warm-pool user-facing anchor.

## Start rule

If incoming token is exactly `g`:

1. Read `handoff.md`.
2. Verify `Current token:` is blank.
3. Set `Current token: g`.
4. Append:

```markdown
- Agent 1 received `g`, verified blank handoff, wrote `g`, sent `g` to Agent 2.
```

5. End with exactly:

```text
NEXT:Agent 2:g
```

## Final rule

If incoming token is exactly `guru`:

1. Read `handoff.md`.
2. Verify `Current token: guru`.
3. Append:

```markdown
- Agent 1 received downstream completion, verified `guru` in handoff, returned `guru` to user.
```

4. End with exactly:

```text
USER:guru — return verified.
```

## Stop conditions

Stop without writing if token is not `g` or `guru`, or if the handoff token does not match the rule.
