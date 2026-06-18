---
description: Telephone relay prompt 1 - Agent 1 starts full autonomous guru cascade
argument-hint: "[token]"
---
Incoming token: ${1:-g}

Run Agent 1's autonomous start rule. Verify the handoff is blank, write `g`, append the Agent 1 start history line, launch Agent 2 synchronously, wait for downstream completion, verify `Current token: guru`, append the Agent 1 completion history line, and end with:

```text
USER:guru — return verified.
```
