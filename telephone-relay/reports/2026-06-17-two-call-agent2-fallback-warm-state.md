# Two-Call Agent 2 Fallback Warm-State Smoke

Date: 2026-06-17

## Scope

Validated that after the persistent pool activates the Agent 2 fallback model, the fallback Agent 2 model stays warm and the second call reuses the same warm pool PIDs.

No bridge, pool, metrics, cap, or persistence behavior was changed. This slice added only the focused warm-state harness and this evidence report.

## Command

```powershell
python .\two-call-agent2-fallback-warm-smoke.py --timeout 300 --run-id two-call-agent2-fallback-20260617
```

The harness starts one `persistent-warm-pool.py` process with:

- primary Agent 2 model: `xai-oauth/grok-build-0.1`
- fallback Agent 2 model: `openai-codex/gpt-5.5`

Then it drives two sequential calls through the config-backed caller surface:

```powershell
python .\caller-default-route.py --tenant-id two-call-agent2-fallback --run-id <call-id> --timeout 300
```

with `TELEPHONE_RELAY_PERSISTENT_POOL_URL=<ephemeral-pool-url>`.

## Result

- harness status: `passed`
- base run ID: `two-call-agent2-fallback-20260617`
- tenant: `two-call-agent2-fallback`
- elapsed: `110.83s`
- receipt: `diagnostics/20260617-043149-two-call-agent2-fallback-warm/two-call-agent2-fallback-warm-smoke.md`

## Acceptance evidence

| Check | Evidence | Result |
| --- | --- | --- |
| Agent 2 fallback activated on first call | Agent 2 model changed from `xai-oauth/grok-build-0.1` to `openai-codex/gpt-5.5`; fallback event recorded | PASS |
| Second call reused fallback pool | after-first and after-second PIDs both `agent1=21184`, `agent2=29264`, `agent3=26592` | PASS |
| Persistent route selected for both calls | both calls `selected_channel=default` | PASS |
| v1 fallback not used | both calls `fallback_used=False` | PASS |
| Both relay-checks pass | per-call relay-check JSON captures under diagnostics receipt dir | PASS |
| Run count progressed | `0 -> 1 -> 2` | PASS |
| Pool idle after second call | `in_use=[]` in `health-after-call2.json` | PASS |

## Call evidence

### Call 1

- run ID: `two-call-agent2-fallback-20260617-call1`
- bridge status: `passed`
- selected channel: `default`
- v1 fallback used: `False`
- pool run_count: `1`
- Agent 2 model: `openai-codex/gpt-5.5`
- relay-check: `True`
- elapsed: `64.75s`
- v2 result: `bridge-v2-runs/two-call-agent2-fallback-20260617-call1/rpc-bridge-v2-result.json`
- relay-check capture: `diagnostics/20260617-043149-two-call-agent2-fallback-warm/two-call-agent2-fallback-20260617-call1/relay-check.json`

### Call 2

- run ID: `two-call-agent2-fallback-20260617-call2`
- bridge status: `passed`
- selected channel: `default`
- v1 fallback used: `False`
- pool run_count: `2`
- Agent 2 model: `openai-codex/gpt-5.5`
- relay-check: `True`
- elapsed: `40.29s`
- v2 result: `bridge-v2-runs/two-call-agent2-fallback-20260617-call2/rpc-bridge-v2-result.json`
- relay-check capture: `diagnostics/20260617-043149-two-call-agent2-fallback-warm/two-call-agent2-fallback-20260617-call2/relay-check.json`

## HERE > THERE

HERE: The persistent pool can recover from the broken primary Agent 2 model, complete through the persistent default route, and keep the fallback Agent 2 model warm for the next call without PID churn.

THERE: The remaining risk is provider credentials for the primary xAI/Grok Agent 2 model; operationally, either repair that credential path or intentionally configure the fallback model as primary in a separate approved slice.

Next best action: decide whether to repair the xAI/Grok OAuth route or update the operator default Agent 2 model to `openai-codex/gpt-5.5` in a separate bounded config slice.
