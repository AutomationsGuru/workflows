---
description: Telephone relay prompt 5 - Agent 1 receives guru and verifies return
argument-hint: "[token]"
---
Incoming token: ${1:-guru}

Run Agent 1's return-leg rule. Verify `Current token: guru`, append the Agent 1 return history line, and end with:

```text
USER:guru — return verified.
```
