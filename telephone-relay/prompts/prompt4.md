---
description: Telephone relay prompt 4 - Agent 2 receives gur and writes guru
argument-hint: "[token]"
---
Incoming token: ${1:-gur}

Run Agent 2's return-leg rule. Verify `Current token: gur`, write `guru`, append the Agent 2 return history line, and end with:

```text
NEXT:Agent 1:guru
```
