---
description: Telephone relay prompt 3 - Agent 3 receives gu and writes gur
argument-hint: "[token]"
---
Incoming token: ${1:-gu}

Run Agent 3's pivot rule. Verify `Current token: gu`, write `gur`, append the Agent 3 history line, and end with:

```text
NEXT:Agent 2:gur
```
