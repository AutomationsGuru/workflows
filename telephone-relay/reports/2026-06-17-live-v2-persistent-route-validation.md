# Live v2 -> Persistent Warm-Pool -> /relay Route Validation

Date: 2026-06-17

## Scope

Validated the direct persistent route:

```text
rpc_bridge_v2.py --persistent-pool-url <ephemeral> --channel default --no-fallback-v1
  -> persistent-warm-pool.py /relay
  -> relay-check.py
```

No bridge, pool, metrics, cap, or persistence behavior was changed. This slice added only the validation harness and this evidence report.

## Command

```powershell
python .\persistent-v2-route-validate.py --timeout 300 --run-id live-v2-persistent-20260617 --no-fallback-v1
```

## Result

- harness status: `passed`
- run ID: `live-v2-persistent-20260617`
- selected v2 channel: `default`
- v1 fallback used: `False`
- bridge exit: `0`
- bridge status: `passed`
- persistent pool run_count: `1`
- elapsed: `67.20s`
- harness receipt: `diagnostics/20260617-003903-v2-persistent-route/persistent-v2-route-validate.md`
- v2 receipt: `bridge-v2-runs/live-v2-persistent-20260617/rpc-bridge-v2-result.json`

## Persistent pool evidence

- pool URL: ephemeral localhost `http://127.0.0.1:59756`
- tenant: `live-v2-persistent`
- pool PIDs at run: `agent1=20736`, `agent2=34564`, `agent3=30844`
- pool response HTTP status: `200`
- relay elapsed inside pool: `59.77s`
- total pool `/relay` elapsed: `60.06s`
- returned outputs:
  - `persistent-pool-runs/20260617-003903/runs/live-v2-persistent-20260617/outputs/agent2-return.txt`
  - `persistent-pool-runs/20260617-003903/runs/live-v2-persistent-20260617/outputs/agent3-pivot.txt`

## Verifier evidence

Harness relay-check JSON:

- `diagnostics/20260617-003903-v2-persistent-route/relay-check.json`
- result: `ok=true`

Manual relay-check command:

```powershell
python .\relay-check.py --agent2-output .\persistent-pool-runs\20260617-003903\runs\live-v2-persistent-20260617\outputs\agent2-return.txt --agent3-output .\persistent-pool-runs\20260617-003903\runs\live-v2-persistent-20260617\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
```

Result: PASS. Capture: `diagnostics/20260617-003903-v2-persistent-route/relay-check-manual.txt`.

## Acceptance

| Check | Result |
| --- | --- |
| v2 routes through persistent `default` channel | PASS |
| v1 fallback disabled and unused | PASS |
| persistent pool completes guru relay | PASS |
| relay-check verifies returned outputs | PASS |
| bridge/pool/metrics/cap/persistence unchanged | PASS |

## HERE > THERE gap

HERE: Bridge v1 baseline is proven; v2-through-v1-to-RPC is proven; now the direct v2 persistent route is proven with fallback disabled.

THERE: Promote the route only after repeated stability runs and a small operator runbook for pool lifecycle, timeout triage, and stale process cleanup.

Next best action: run a two-call persistence smoke on the same live pool to prove the pool stays warm across sequential v2 `/relay` calls without process churn.
