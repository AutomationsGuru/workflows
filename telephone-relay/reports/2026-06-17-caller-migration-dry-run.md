# Caller-Migration Dry Run

Date: 2026-06-17

## Scope

Exercised the caller-facing RPC Bridge v2 CLI against a live persistent pool with v1 fallback enabled. This proves completion behavior before considering default-route promotion.

No bridge, pool, metrics, cap, or persistence behavior was changed. This slice added only the dry-run harness and this evidence report.

## Command

```powershell
python .\caller-migration-dry-run.py --timeout 300 --run-id caller-migration-dry-run-20260617-r2
```

The harness starts `persistent-warm-pool.py --port 0`, then calls:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url <pool-url> --channel default --tenant-id caller-migration-dry-run --run-id caller-migration-dry-run-20260617-r2 --timeout 300
```

Important: `--no-fallback-v1` is intentionally omitted, so v1 fallback is enabled.

## Result

- harness status: `passed`
- run ID: `caller-migration-dry-run-20260617-r2`
- tenant: `caller-migration-dry-run`
- elapsed: `42.73s`
- receipt: `diagnostics/20260617-014603-caller-migration-dry-run/caller-migration-dry-run.md`

## Acceptance evidence

| Check | Evidence | Result |
| --- | --- | --- |
| Caller surface completed | `bridge_exit=0`, `bridge_status=passed` | PASS |
| Persistent route selected | `selected_channel=default` | PASS |
| Fallback enabled but not needed | `fallback_enabled=True`, `fallback_used=False` | PASS |
| Relay verified | `relay_check_ok=True` | PASS |
| Pool completed cleanly | `pool_run_count=1`, `in_use_after=[]` | PASS |
| No PID churn | before/after PIDs stayed `agent1=38500`, `agent2=25304`, `agent3=32380` | PASS |

## Artifacts

- harness JSON: `diagnostics/20260617-014603-caller-migration-dry-run/caller-migration-dry-run.json`
- harness MD: `diagnostics/20260617-014603-caller-migration-dry-run/caller-migration-dry-run.md`
- v2 receipt: `bridge-v2-runs/caller-migration-dry-run-20260617-r2/rpc-bridge-v2-result.json`
- relay-check capture: `diagnostics/20260617-014603-caller-migration-dry-run/relay-check.json`
- Agent 2 output: `persistent-pool-runs/20260617-014604/runs/caller-migration-dry-run-20260617-r2/outputs/agent2-return.txt`
- Agent 3 output: `persistent-pool-runs/20260617-014604/runs/caller-migration-dry-run-20260617-r2/outputs/agent3-pivot.txt`
- health after: `diagnostics/20260617-014603-caller-migration-dry-run/health-after.json`

## HERE > THERE

HERE: v2 persistent route now has single-call truth proof, two-call warm-state proof, an operator runbook, and a caller-migration dry run with v1 fallback enabled but unused.

THERE: Default-route promotion should still be gated by an explicit rollback note and one failure-path drill proving fallback engages when the persistent URL is unavailable.

Next best action: run a bounded fallback-engagement drill using an unavailable persistent URL and confirm v2 selects the v1 bridge path and still returns a relay-check-passable result.
