# Telephone Relay RPC Warm-Pool Rules

You are participating in the RPC warm-pool version of the Telephone Relay experiment.

Shared state file:

`D:\.agentos\workflows\telephone-relay\handoff.md`

Important difference from the direct relay:

- Do **not** launch child `pi` processes.
- Do **not** run monitor loops.
- The external RPC controller owns routing and waiting.
- Each agent performs exactly one local transition per prompt, updates `handoff.md`, and returns one directive line.

Directive lines:

- `NEXT:Agent 2:g`
- `NEXT:Agent 3:gu`
- `NEXT:Agent 2:gur`
- `NEXT:Agent 1:guru`
- `USER:guru — return verified.`

Rules:

1. Before writing, verify the incoming token and current `handoff.md` token match your profile's rule.
2. Edit only `handoff.md`.
3. Stop on mismatch and explain the mismatch.
4. End every successful turn with exactly one directive line and no prose after it.
