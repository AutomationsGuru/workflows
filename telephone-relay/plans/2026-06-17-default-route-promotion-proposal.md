# Default-Route Promotion Proposal

Date: 2026-06-17

## Decision proposed

Promote the caller default for Telephone Relay Bridge v2 to prefer the live persistent-pool route while keeping v1 fallback enabled.

This is a proposal only. It does not change `rpc_bridge_v2.py`, `persistent-warm-pool.py`, metrics, pool caps, or persistence behavior.

## Promotion criteria

All criteria below should remain true immediately before any promotion slice:

1. **Persistent truth path passes**
   - Evidence: `reports/2026-06-17-live-v2-persistent-route-validation.md`.
   - Required: `selected_channel=default`, `fallback_used=False`, relay-check passes.

2. **Warm-state reuse passes**
   - Evidence: `reports/2026-06-17-two-call-persistent-pool-warm-state.md`.
   - Required: two sequential calls pass, PIDs unchanged, startup count stable, run_count progresses `0 -> 1 -> 2`.

3. **Caller-migration dry run passes**
   - Evidence: `reports/2026-06-17-caller-migration-dry-run.md`.
   - Required: v1 fallback enabled but unused, persistent route selected, pool `in_use=[]` after completion.

4. **Fallback engagement passes**
   - Evidence: `reports/2026-06-17-fallback-engagement-drill.md`.
   - Required: unavailable persistent URL causes v2 to select `v1`, `fallback_used=True`, relay-check-passable evidence returned.

5. **Operator runbook exists**
   - Evidence: `persistent-pool-operator-runbook.md`.
   - Required: lifecycle, timeout triage, stale-process cleanup, and evidence collection documented.

6. **Fallback remains enabled**
   - Promotion must not use `--no-fallback-v1` for caller-facing default behavior.

## Proposed promotion shape

Bounded promotion should be one small config/caller-surface slice:

- route caller default to pass `--persistent-pool-url <configured-local-pool-url>` into `rpc_bridge_v2.py`;
- keep `--channel default`;
- keep v1 fallback enabled;
- do not change pool sizing, retry semantics, metrics, persistence, or bridge internals;
- keep direct and v1 RPC evidence paths available for rollback.

## Smoke checks after promotion

Run in this order:

1. **Baseline repo checks**

   ```powershell
   python -m py_compile fallback-engagement-drill.py caller-migration-dry-run.py two-call-persistent-pool-smoke.py persistent-v2-route-validate.py rpc_bridge_v2.py persistent-warm-pool.py relay-check.py
   python .\relay-check.py
   git diff --check
   ```

2. **Persistent caller smoke**

   ```powershell
   python .\caller-migration-dry-run.py --timeout 300 --run-id post-promotion-caller-smoke-<date>
   ```

   Required: `selected_channel=default`, `fallback_used=False`, relay-check passes, `in_use_after=[]`.

3. **Fallback drill**

   ```powershell
   python .\fallback-engagement-drill.py --timeout 300 --run-id post-promotion-fallback-smoke-<date>
   ```

   Required: `selected_channel=v1`, `fallback_used=True`, relay-check passes.

4. **Manual evidence review**

   Confirm the receipts point to the expected `bridge-v2-runs/`, `bridge-runs/`, `persistent-pool-runs/`, or `rpc-runs/` directories and that no unexpected child processes remain.

5. **CodeRabbit review**

   Run CodeRabbit for the promotion diff before GREEN handoff.

## Rollback criteria

Rollback immediately to v1/default behavior if any of these occur:

- persistent caller smoke fails relay-check;
- persistent route is selected but returns malformed output paths;
- `fallback_used=True` during a healthy persistent caller smoke without a known transient pool issue;
- pool `in_use` is non-empty after completion;
- PIDs churn unexpectedly during warm-state checks;
- fallback drill fails to select `v1` or fails relay-check;
- operator cannot collect `/health`, `/state`, v2 receipt, and relay-check evidence for a failed run.

## Rollback action

Revert only the caller/default routing change from the promotion slice. Do not edit pool internals, persistence files, metrics, or caps as rollback cleanup.

After rollback, verify:

```powershell
python .\rpc_bridge_v2.py --run-id rollback-v1-smoke-<date> --timeout 300
python .\relay-check.py
```

Required: v2 uses the v1 route and relay-check passes.

## Risks

- **Persistent pool is still serialized.** `pool_size` remains logical admission control, not live parallel agent-set allocation.
- **Localhost-only service.** The pool has no auth and should remain bound to `127.0.0.1`.
- **Runtime dependency risk.** Provider/OAuth failures can still affect child agents; fallback only helps route failure, not every provider failure.
- **Process hygiene risk.** Stale child processes must be cleaned by known PID only, using the operator runbook.
- **Evidence directories are ignored.** Receipts must be preserved locally or promoted into reports when needed for audit.

## Recommendation

Proceed to a promotion implementation only as a separate bounded slice, with v1 fallback enabled and no pool behavior changes.
