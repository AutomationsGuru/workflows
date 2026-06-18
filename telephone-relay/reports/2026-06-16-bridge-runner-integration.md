# Telephone Relay Bridge Runner Integration

Date: 2026-06-16

## Scope

Bounded integration slice for `bridge-runner.py`:

- call `rpc-warm-pool-prototype.py` from the main telephone-relay path;
- keep the proven direct relay as fallback;
- log cold/warm state and before/after timestamps;
- validate with `relay-check.py`;
- do not replace the direct relay.

## Current result

Two bridge runs were executed:

### RPC preferred path

- Run ID: `20260616-214545`
- Mode selected: `rpc`
- Status: passed
- Total elapsed: `59.09s`
- RPC prototype command elapsed: `58.95s`
- Relay-check RPC verifier elapsed: `0.10s`
- Before handoff token: `guru`
- After handoff token: `guru`
- Receipt: `bridge-runs/20260616-214545/bridge-result.md`
- Underlying RPC receipt: `rpc-runs/20260616-214545/rpc-warm-pool-result.md`

### Direct fallback proof

- Run ID: `20260616-214655`
- Mode selected: `direct`
- Status: passed
- Total elapsed: `81.22s`
- Direct relay command elapsed: `81.07s`
- Relay-check direct verifier elapsed: `0.12s`
- Receipt: `bridge-runs/20260616-214655/bridge-result.md`

## HERE

- Direct relay remains intact and verifier-backed.
- RPC warm-pool prototype remains intact as a working prototype.
- `bridge-runner.py` now provides a small typed wrapper around both paths.
- The wrapper tries RPC first, verifies it, and only falls back to direct if RPC/verifier fails.
- Direct fallback can also be exercised explicitly with `--force-direct`.

## THERE

Before broader use:

1. Add negative tests for `bridge-runner.py` fallback behavior by intentionally forcing RPC failure.
2. Add JSON directive parsing instead of substring matching.
3. Add run IDs into `handoff.md` to prevent cross-run ambiguity.
4. Promote a non-toy coding relay through the bridge.
5. Decide whether bridge receipts under `bridge-runs/` are durable artifacts or should be archived after summary.

## Notes

The RPC preferred path for this run was slower than the earlier standalone RPC run (`59.09s` vs about `41.84s`) but still faster than the direct fallback proof (`81.22s`). Variation is expected because provider latency dominates the tiny `guru` workload.
