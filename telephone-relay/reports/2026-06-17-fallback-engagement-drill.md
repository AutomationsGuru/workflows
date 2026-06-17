# Fallback-Engagement Drill

Date: 2026-06-17

## Scope

Exercised the caller-facing RPC Bridge v2 CLI with an unavailable persistent pool URL and v1 fallback enabled. This proves v2 can engage the v1 bridge path and still return relay-check-passable evidence when the persistent route is unavailable.

No bridge, pool, metrics, cap, or persistence behavior was changed. This slice added only the drill harness and this evidence report.

## Command

```powershell
python .\fallback-engagement-drill.py --timeout 300 --run-id fallback-engagement-drill-20260617-r2
```

The harness calls:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:1 --channel default --tenant-id fallback-engagement-drill --run-id fallback-engagement-drill-20260617-r2 --timeout 300 --max-attempts 2 --initial-backoff-s 0.05
```

Important: `--no-fallback-v1` is intentionally omitted, so v1 fallback is enabled.

## Result

- harness status: `passed`
- run ID: `fallback-engagement-drill-20260617-r2`
- unavailable persistent URL: `http://127.0.0.1:1`
- elapsed: `97.54s`
- receipt: `diagnostics/20260617-031033-fallback-engagement-drill/fallback-engagement-drill.md`

## Acceptance evidence

| Check | Evidence | Result |
| --- | --- | --- |
| Persistent route failed first | two `default/persistent` attempts failed with connection refused | PASS |
| v2 selected fallback | `selected_channel=v1` | PASS |
| fallback flag set | `fallback_used=True` | PASS |
| v1 bridge completed | v1 `bridge-result.json` has `status=passed` | PASS |
| v1 returned passable relay evidence | independent harness relay-check over v1 RPC outputs passed | PASS |
| v1 selected mode recorded | `selected_mode=rpc` | PASS |

## Artifacts

- harness JSON: `diagnostics/20260617-031033-fallback-engagement-drill/fallback-engagement-drill.json`
- harness MD: `diagnostics/20260617-031033-fallback-engagement-drill/fallback-engagement-drill.md`
- v2 receipt: `bridge-v2-runs/fallback-engagement-drill-20260617-r2/rpc-bridge-v2-result.json`
- v1 receipt: `bridge-runs/fallback-engagement-drill-20260617-r2/bridge-result.json`
- harness relay-check capture: `diagnostics/20260617-031033-fallback-engagement-drill/relay-check.json`
- v1 bridge relay-check capture: `bridge-runs/fallback-engagement-drill-20260617-r2/relay-check-rpc.stdout.txt`
- Agent 2 output: `rpc-runs/20260617-031038/outputs/agent2-return.txt`
- Agent 3 output: `rpc-runs/20260617-031038/outputs/agent3-pivot.txt`

## HERE > THERE

HERE: v2 persistent route now has truth proof, warm-state proof, caller migration proof, and fallback-engagement proof. The v1 safety path remains effective when the persistent URL is unavailable.

THERE: Default-route promotion can be considered only with an explicit rollback note and a bounded config change that keeps v1 fallback enabled.

Next best action: prepare a short default-route promotion proposal with rollback criteria, not the promotion itself.
