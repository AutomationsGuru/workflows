---
description: Agent 3 execute one cascade chunk
argument-hint: "<chunk-id> <chunk-file> <output-file> [mission]"
---
CHUNK_ID: $1
CHUNK_FILE: $2
OUTPUT_FILE: $3
MISSION: ${@:4}

Run the Agent 3 executor procedure for this chunk only. Write the output file and return `NEXT:Agent 2:chunk-complete:$1`.
