---
description: Telephone relay prompt 2 - Agent 2 receives g, runs Agent 3, and returns guru
argument-hint: "[token]"
---
Incoming token: ${1:-g}

Run Agent 2's autonomous middle rule. Verify `Current token: g`, write `gu`, append the Agent 2 forward history line, launch Agent 3 synchronously, wait for `NEXT:Agent 2:gur`, verify `Current token: gur`, write `guru`, append the Agent 2 return history line, and end with:

```text
NEXT:Agent 1:guru
```
