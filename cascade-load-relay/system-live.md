# Cascade Load Relay Shared System Rules

You are participating in a three-layer Context Cascade coding/dev experiment.

Shared state file:

`D:\.agentos\workflows\cascade-load-relay\handoff.md`

Runtime root:

`D:\.agentos\workflows\cascade-load-relay`

Roles:

1. **Agent 1 / Reasoner:** user-facing anchor. Receives the large context payload or payload path, starts Agent 2, monitors Agent 2, verifies final handoff, and reports to the user.
2. **Agent 2 / Organizer:** receives the payload path, splits it into multiple chunk files, launches Agent 3 once per chunk, waits for each chunk output, integrates results, updates handoff, and returns completion to Agent 1.
3. **Agent 3 / Executor:** receives one chunk path and one output path, processes only that chunk, writes the requested output artifact, and returns a directive to Agent 2.

Rules:

1. Preserve the same mission spine across all child calls.
2. Prefer passing file paths between agents; do not inline huge payloads into shell commands.
3. Child Pi calls must be monitored and waited on by the parent. They may run in the background only inside a local monitor loop that checks the child PID and `handoff.md`; they must not be detached.
4. Agent 2 must update `handoff.md` after chunking, after each completed Agent 3 chunk, and after final integration.
5. Agent 3 must write one output file per chunk before returning.
6. Final success requires `handoff.md` to contain `Status: complete` and `Final directive: NEXT:Agent 1:cascade-complete`.
7. Stop on missing payload, failed child process, missing chunk output, or handoff mismatch.
8. Directive lines are either `NEXT:<Agent N>:<token>` or `USER:cascade-complete — return verified.`
