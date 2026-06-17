---
description: Start cascade load relay from Agent 1
argument-hint: "<payload-file> [mission]"
---
PAYLOAD_FILE: $1
MISSION: ${@:2}

Run the Agent 1 cascade procedure. If mission is blank, use the default mission from your profile. Start Agent 2, monitor it, verify final handoff, and return only after cascade completion.
