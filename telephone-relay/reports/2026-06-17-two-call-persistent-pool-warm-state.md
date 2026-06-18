# Two-Call Persistent Pool Warm-State Smoke

Date: 2026-06-17

## Scope

Validated that one `persistent-warm-pool.py` process can serve two sequential RPC Bridge v2 `/relay` calls without process churn.

No bridge, pool, metrics, cap, or persistence behavior was changed. This slice added only the test harness and this evidence report.

## Command

```powershell
python .\two-call-persistent-pool-smoke.py --timeout 300 --run-id two-call-v2-persistent-20260617
```

## Result

- harness status: `passed`
- base run ID: `two-call-v2-persistent-20260617`
- tenant: `two-call-v2-persistent`
- pool URL: ephemeral localhost `http://127.0.0.1:55571`
- total elapsed: `123.43s`
- receipt: `diagnostics/20260617-010030-two-call-persistent-pool/two-call-persistent-pool-smoke.md`

## Warm-state evidence

| Check | Evidence | Result |
| --- | --- | --- |
| Same pool PIDs across both calls | initial/after-first/after-second PIDs all `agent1=6496`, `agent2=29580`, `agent3=34768` | PASS |
| Both relay-checks pass | per-call relay-check JSON captures under diagnostics receipt dir | PASS |
| Second call uses already-warm pool | run_count progressed `0 -> 1 -> 2`; startup count stayed `3 -> 3`; PIDs unchanged | PASS |
| v2 persistent channel used | both calls selected channel `default`, fallback `False` | PASS |

## Call evidence

### Call 1

- run ID: `two-call-v2-persistent-20260617-call1`
- bridge status: `passed`
- selected channel: `default`
- fallback used: `False`
- pool run_count: `1`
- relay-check: `True`
- elapsed: `61.66s`
- v2 result: `bridge-v2-runs/two-call-v2-persistent-20260617-call1/rpc-bridge-v2-result.json`
- relay-check capture: `diagnostics/20260617-010030-two-call-persistent-pool/two-call-v2-persistent-20260617-call1/relay-check.json`

### Call 2

- run ID: `two-call-v2-persistent-20260617-call2`
- bridge status: `passed`
- selected channel: `default`
- fallback used: `False`
- pool run_count: `2`
- relay-check: `True`
- elapsed: `55.96s`
- v2 result: `bridge-v2-runs/two-call-v2-persistent-20260617-call2/rpc-bridge-v2-result.json`
- relay-check capture: `diagnostics/20260617-010030-two-call-persistent-pool/two-call-v2-persistent-20260617-call2/relay-check.json`

## HERE > THERE

HERE: Direct v2 persistent route is proven for one call and now proven across two sequential calls on the same warm pool. The pool kept the same PIDs, increased run_count to `2`, and did not re-run startup.

THERE: Before caller migration/default promotion, add a short operator runbook for lifecycle commands, timeout triage, stale-process cleanup, and evidence collection.

Next best action: write the operator runbook and then perform one caller-migration dry run using the v2 persistent route with v1 fallback still enabled.
