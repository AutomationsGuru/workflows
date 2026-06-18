# Telephone Relay Handoff

Current token: guru

History:
- Agent 1 received `g`, verified blank handoff, wrote `g`, sent `g` to Agent 2.
- Agent 2 received `g`, verified `g` in handoff, wrote `gu`, sent `gu` to Agent 3.
- Agent 3 received `gu`, verified `gu` in handoff, wrote `gur`, sent `gur` to Agent 2.
- Agent 2 received downstream `gur`, verified `gur` in handoff, wrote `guru`, sent `guru` to Agent 1.
- Agent 1 received downstream completion, verified `guru` in handoff, returned `guru` to user.
