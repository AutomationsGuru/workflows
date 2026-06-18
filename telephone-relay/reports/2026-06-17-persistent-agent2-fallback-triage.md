# Persistent /relay Agent 2 Empty Output Triage

Date: 2026-06-17

## Scope

Triage and fix the live persistent `/relay` failure where Agent 2 returned empty RPC output on the primary `xai-oauth/grok-build-0.1` model.

No bridge retry logic, pool cap, metrics backend, or persistence format was changed. The bounded fix adds an Agent 2 fallback model switch inside the persistent pool, mirroring the already-proven `rpc-warm-pool-prototype.py` behavior.

## Root cause evidence

### Symptom

Persistent caller smoke selected v1 fallback because the persistent route failed first:

- failing receipt: `diagnostics/20260617-034214-caller-migration-dry-run/caller-migration-dry-run.md`
- v2 result: `bridge-v2-runs/caller-default-config-smoke-20260617-r3/rpc-bridge-v2-result.json`
- persistent attempt error: Agent 2 expected `NEXT:Agent 3:gu` but output was empty.

### Persistent pool logs

`persistent-pool-runs/20260617-034214/pool-logs/telephone-relay-agent-2-rpc.log` showed:

```text
telephone-relay-agent-2-rpc: starting command ... --model xai-oauth/grok-build-0.1 ...
telephone-relay-agent-2-rpc: ready in 1.679s
telephone-relay-agent-2-rpc: failure: expected directive 'NEXT:Agent 3:gu' not found in output ''; exit_code=None; stderr_tail=[]
```

The model process reached RPC readiness, but the first relay prompt produced no assistant text.

### Prototype comparison

The v1 RPC prototype succeeded because it already retries Agent 2 with `openai-codex/gpt-5.5` after the same primary failure:

- run: `rpc-runs/20260617-034650/rpc-warm-pool-result.json`
- fallback recorded:

```text
Agent 2 primary model xai-oauth/grok-build-0.1 failed: ... output ''.
Retried Agent 2 with fallback model openai-codex/gpt-5.5
```

### Model slot reachability check

Direct model probe:

```powershell
pi -p --approve --mode text --no-extensions --no-skills --tools read,bash --model xai-oauth/grok-build-0.1 --session-id model-reachability-xai-20260617 --name model-reachability-xai-20260617 "Respond with exactly: OK"
```

Result:

```text
OpenAI API error (403): 403 "The OAuth2 access token could not be validated."
```

Conclusion: the primary Agent 2 model slot is currently not reliable/reachable. Persistent pool lacked the prototype's Agent 2 fallback behavior, so it surfaced as an empty Agent 2 RPC output and then v2 had to use the v1 route.

## Fix

Added bounded Agent 2 fallback support to `persistent-warm-pool.py`:

- new `--agent2-fallback-model` CLI flag, default `openai-codex/gpt-5.5`;
- on relay failure with the primary Agent 2 model, stop the current warm agents;
- rebuild the warm pool with the fallback Agent 2 model;
- reset handoff and retry the same `/relay` once;
- record `fallback_events` in `/health` and the persistent result receipt.

## Validation evidence

### Direct persistent route

```powershell
python .\persistent-v2-route-validate.py --timeout 300 --run-id persistent-agent2-fallback-fix-20260617 --no-fallback-v1
```

Result: PASS.

- selected channel: `default`
- v1 fallback used: `False`
- relay-check: `True`
- receipt: `diagnostics/20260617-035945-v2-persistent-route/persistent-v2-route-validate.md`
- v2 receipt: `bridge-v2-runs/persistent-agent2-fallback-fix-20260617/rpc-bridge-v2-result.json`
- persistent result: `persistent-pool-runs/20260617-035945/runs/persistent-agent2-fallback-fix-20260617/persistent-pool-result.json`

The persistent result records:

- `agent2_model=openai-codex/gpt-5.5`
- fallback event: primary `xai-oauth/grok-build-0.1` failed with empty output and switched to fallback.

### Caller default config smoke

```powershell
python .\caller-migration-dry-run.py --timeout 300 --run-id caller-default-config-after-agent2-fix-20260617-r2
```

Result: PASS.

- selected channel: `default`
- v1 fallback used: `False`
- pool run_count: `1`
- `in_use_after=[]`
- relay-check: `True`
- receipt: `diagnostics/20260617-040314-caller-migration-dry-run/caller-migration-dry-run.md`

### Fallback drill

```powershell
python .\fallback-engagement-drill.py --timeout 300 --run-id caller-default-config-fallback-after-agent2-fix-20260617
```

Result: PASS.

- selected channel: `v1`
- fallback used: `True`
- persistent failures: `2`
- v1 successes: `1`
- relay-check: `True`
- receipt: `diagnostics/20260617-040430-fallback-engagement-drill/fallback-engagement-drill.md`

## Risk notes

- The primary Agent 2 xAI/Grok OAuth route still needs credential/provider repair outside this code slice.
- The fallback switch intentionally causes PID churn once, because the pool restarts warm agents with the fallback Agent 2 model.
- v1 fallback remains enabled at the bridge layer.

## Next best action

Run one two-call persistent warm-state smoke after fallback activation to prove the fallback model stays warm and PIDs remain stable on the second call.
