# Live RPC Bridge v2 -> v1 -> RPC Warm-Pool Validation

Date: 2026-06-16

## Scope

Validate the bounded live call path:

```text
rpc_bridge_v2.py -> bridge-runner.py (v1 route) -> rpc-warm-pool-prototype.py -> relay-check.py
```

No bridge features were added. No v2 migration was performed. `persistent-warm-pool.py`, metrics, cap, and persistence code were not changed.

## Command

```powershell
python .\rpc_bridge_v2.py --run-id live-v2-v1-rpc-20260616 --timeout 300
```

## Result

- v2 status: `passed`
- selected v2 channel: `v1`
- fallback used by v2: `False`
- v2 attempts: `1`
- v2 retries: `0`
- v2 failures: `0`
- v2 elapsed: `48.18s`
- v2 receipt: `bridge-v2-runs/live-v2-v1-rpc-20260616/rpc-bridge-v2-result.md`

## v1 bridge evidence

- v1 status: `passed`
- selected v1 mode: `rpc`
- attempted modes: `rpc`
- v1 elapsed: `47.98s`
- RPC warm-pool command elapsed: `47.83s`
- v1 receipt: `bridge-runs/live-v2-v1-rpc-20260616/bridge-result.md`
- underlying RPC warm-pool receipt: `rpc-runs/20260616-234035/rpc-warm-pool-result.md`

## Verifier evidence

Bridge-runner invoked `relay-check.py` automatically with RPC output overrides and exit `0`.

Manual verifier capture:

```powershell
python .\relay-check.py --agent2-output .\rpc-runs\20260616-234035\outputs\agent2-return.txt --agent3-output .\rpc-runs\20260616-234035\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
```

Result: PASS.

Capture: `bridge-v2-runs/live-v2-v1-rpc-20260616/relay-check-live-v2-v1-rpc.txt`

## Acceptance

| Check | Result |
| --- | --- |
| v2 routes through v1 without code changes | PASS |
| v1 selects RPC warm-pool path | PASS |
| RPC warm-pool completes guru relay | PASS |
| relay-check verifies handoff and outputs | PASS |
| persistent pool/metrics/cap/persistence unchanged | PASS |

## Note

This validates the requested v2-through-v1 live route. It does not validate the separate direct `v2 -> persistent-warm-pool.py -> /relay` route; that remains a later smoke if needed.
