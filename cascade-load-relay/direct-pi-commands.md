# Direct Pi Commands for Cascade Load Relay

Run these from:

```powershell
cd D:\.agentos\workflows\cascade-load-relay
```

## Start Agent 1 only

Agent 1 is the only interactive user-facing session. It launches Agent 2; Agent 2 launches Agent 3 once per chunk.

```powershell
pi --approve --mode text --session-id cascade-load-agent-1 --session-dir .\sessions\agent-1 --name "cascade-load-agent-1" --model minimax-oauth/MiniMax-M3 --append-system-prompt .\system-live.md --append-system-prompt .\profiles\agent-1.md --prompt-template .\prompts\agent1-start.md
```

Then send:

```text
/agent1-start ./payloads/sample-350k-context.md For each chunk, produce a compact coding-context execution note with summary, constraints, and TODO-like action items.
```

## Agent 1 child call to Agent 2

Agent 1 runs this internally after resolving the payload and mission:

```bash
mkdir -p ./sessions/agent-1
rm -f ./sessions/agent-1/agent2-output.txt ./sessions/agent-1/agent2-exit.txt
(pi -p --approve --mode text --session-id cascade-load-agent-2 --session-dir ./sessions/agent-2 --name "cascade-load-agent-2" --model openai-codex/gpt-5.5 --append-system-prompt ./system-live.md --append-system-prompt ./profiles/agent-2.md "PAYLOAD_FILE: ./payloads/sample-350k-context.md
MISSION: For each chunk, produce a compact coding-context execution note with summary, constraints, and TODO-like action items." > ./sessions/agent-1/agent2-output.txt 2>&1; echo $? > ./sessions/agent-1/agent2-exit.txt) &
child_pid=$!
while kill -0 "$child_pid" 2>/dev/null; do
  status=$(grep -m1 '^Status:' ./handoff.md || true)
  completed=$(grep -m1 '^Completed chunks:' ./handoff.md || true)
  echo "Agent 1 monitor: Agent 2 pid $child_pid running; ${status:-Status: <missing>}; ${completed:-Completed chunks: <missing>}"
  sleep 5
done
wait "$child_pid" || true
cat ./sessions/agent-1/agent2-output.txt
echo "Agent 2 exit code: $(cat ./sessions/agent-1/agent2-exit.txt 2>/dev/null || echo missing)"
```

## Agent 2 child calls to Agent 3

Agent 2 generates one command per chunk using this template:

```bash
mkdir -p ./sessions/agent-2
rm -f ./sessions/agent-2/agent3-<CHUNK_ID>-output.txt ./sessions/agent-2/agent3-<CHUNK_ID>-exit.txt
(pi -p --approve --mode text --no-extensions --no-skills --tools read,bash,write --session-id cascade-load-agent-3 --session-dir ./sessions/agent-3 --name "cascade-load-agent-3" --model openai-codex/gpt-5.5 --append-system-prompt ./system-live.md --append-system-prompt ./profiles/agent-3.md "CHUNK_ID: <CHUNK_ID>
CHUNK_FILE: <CHUNK_FILE>
OUTPUT_FILE: <OUTPUT_FILE>
MISSION: <MISSION>" > ./sessions/agent-2/agent3-<CHUNK_ID>-output.txt 2>&1; echo $? > ./sessions/agent-2/agent3-<CHUNK_ID>-exit.txt) &
child_pid=$!
while kill -0 "$child_pid" 2>/dev/null; do
  status=$(grep -m1 '^Status:' ./handoff.md || true)
  completed=$(grep -m1 '^Completed chunks:' ./handoff.md || true)
  echo "Agent 2 monitor: Agent 3 chunk <CHUNK_ID> pid $child_pid running; ${status:-Status: <missing>}; ${completed:-Completed chunks: <missing>}"
  sleep 5
done
wait "$child_pid" || true
cat ./sessions/agent-2/agent3-<CHUNK_ID>-output.txt
echo "Agent 3 chunk <CHUNK_ID> exit code: $(cat ./sessions/agent-2/agent3-<CHUNK_ID>-exit.txt 2>/dev/null || echo missing)"
```
