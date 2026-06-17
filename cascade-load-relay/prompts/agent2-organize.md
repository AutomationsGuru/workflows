---
description: Agent 2 organize/chunk payload and run Agent 3
argument-hint: "<payload-file> [mission]"
---
PAYLOAD_FILE: $1
MISSION: ${@:2}

Run the Agent 2 organizer procedure. Split payload into chunks, run Agent 3 for each chunk, update handoff after each output, integrate, and return `NEXT:Agent 1:cascade-complete`.
