# RPC Bridge v2 Migration Plan

Date: 2026-06-16

## Goal

Migrate Telephone Relay bridge callers from the v1 bridge wrapper (`bridge-runner.py`) to the typed v2 call layer (`rpc_bridge_v2.py`) while preserving the proven v1/direct relay fallback.

## Non-goals

- Do not remove `bridge-runner.py`.
- Do not replace `rpc-warm-pool-prototype.py` as benchmark evidence.
- Do not change persistent-pool metrics, cap, persistence, or sizing semantics.
- Do not promote persistent pool to production multi-user service.

## What moves from v1 to v2

| v1 surface | v2 equivalent | Migration note |
| --- | --- | --- |
| `python bridge-runner.py --timeout 300` | `python rpc_bridge_v2.py --run-id <id> --timeout 300` | Uses v1 route by default when no persistent URL is provided. |
| `--persistent-pool-url <url>` on v1 bridge | `--persistent-pool-url <url>` on v2 bridge | v2 wraps the call with retry/backoff and stats. |
| v1 receipt under `bridge-runs/<id>/` | v2 receipt under `bridge-v2-runs/<id>/` plus any v1 fallback receipt | Keep both during migration. |
| ad hoc mode interpretation | `RpcBridgeV2Result` + `CallStats` | Use typed status, selected channel, attempts, retries, failures. |
| manual fallback reasoning | explicit `fallback_used` and attempts detail | Audit fallback from receipt JSON. |

## Ordering

### Phase 0: Keep v1 as source of truth

Current state. `bridge-runner.py` and direct relay remain accepted fallback evidence.

Checks:

```powershell
python .\bridge-runner.py --timeout 300 --force-direct
python .\relay-check.py
```

### Phase 1: v2 self-test gate

Run fake-transport v2 tests before any live routing.

```powershell
python .\rpc_bridge_v2_selftest.py
```

Pass criteria:

- retry-then-success test passes;
- persistent-to-v1 fallback test passes;
- negative backoff clamp test passes.

### Phase 2: v2 via v1 route only

Use v2 with no persistent pool URL. This exercises the typed API and receipts while still routing through v1.

```powershell
python .\rpc_bridge_v2.py --run-id v2-v1-smoke-001 --timeout 300
```

Pass criteria:

- v2 result status is `passed`;
- selected channel is `v1`;
- v1 receipt under `bridge-runs/v2-v1-smoke-001/` passes normal review;
- `python .\relay-check.py` passes.

### Phase 3: v2 persistent route with v1 fallback enabled

Start a persistent pool, then call v2 with persistent routing.

```powershell
python .\persistent-warm-pool.py --port 8765 --tenant-id relay-v2 --pool-size 1 --timeout 240
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:8765 --tenant-id relay-v2 --run-id v2-persistent-smoke-001 --timeout 300
```

Pass criteria:

- v2 result status is `passed`;
- selected channel is `default` for persistent success, or `v1` if fallback was needed;
- `fallback_used` value is understood and recorded;
- returned Agent 2/Agent 3 output paths pass `relay-check.py --skip-exit-files --skip-session-id-check`.

### Phase 4: caller migration

For each caller currently invoking `bridge-runner.py` directly:

1. switch the caller to `rpc_bridge_v2.py` or `RpcBridgeV2Client`;
2. keep `fallback_v1=True`;
3. keep the same timeout value first;
4. preserve old v1 receipts for comparison;
5. record before/after latency and selected channel.

### Phase 5: optional v1 default demotion

Only after repeated live v2 persistent passes:

- make persistent channel the normal path for selected callers;
- keep v1 route configured;
- do not delete v1 bridge.

## Rollback

Rollback is simple because v1 remains intact.

Immediate rollback options:

```powershell
python .\bridge-runner.py --timeout 300
python .\bridge-runner.py --timeout 300 --force-direct
```

For code callers:

- switch command back to `bridge-runner.py`; or
- configure v2 route to `v1` only; or
- run v2 without `--persistent-pool-url`.

Rollback triggers:

- v2 selected channel is unexpected;
- retry count exceeds expected budget;
- fallback rate is unexplained;
- relay-check fails on returned outputs;
- persistent pool reports non-empty `in_use` when idle;
- direct relay verifier fails after v2 call.

## Smoke checks

Minimum pre-migration smoke:

```powershell
python .\rpc_bridge_v2_selftest.py
python .\relay-check.py
python .\relay-check.py --agent2-output .\rpc-runs\20260616-220619\outputs\agent2-return.txt --agent3-output .\rpc-runs\20260616-220619\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
```

Live persistent smoke, when a pool is available:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:8765 --tenant-id relay-v2 --run-id v2-persistent-smoke-001 --timeout 300
```

Then inspect `bridge-v2-runs/v2-persistent-smoke-001/rpc-bridge-v2-result.json` for:

- `status == "passed"`;
- `stats.attempts >= 1`;
- `stats.failures == 0` for clean persistent success, or fallback reason documented;
- `selected_channel` is expected.

## Evidence to retain

For each migration wave, retain:

- v2 receipt JSON/Markdown;
- v1 fallback receipt if fallback occurred;
- `relay-check.py` output;
- persistent pool `/health` snapshot if persistent route was used;
- before/after latency summary.

## Risks

| Risk | Mitigation |
| --- | --- |
| Persistent pool unavailable | v2 falls back to v1 when enabled. |
| Misrouted channel | Use explicit `channel`, inspect `selected_channel` in receipt. |
| Retry hides instability | Track `stats.retries`, `stats.failures`, and fallback rate. |
| Output verifier mismatch | Keep `relay-check.py` as required gate. |
| Receipt fragmentation | Store v2 receipts under `bridge-v2-runs/` and retain linked v1 receipts. |

## Exit criteria for migration readiness

- v2 self-test passes.
- v2-through-v1 smoke passes.
- one live v2 persistent smoke passes or cleanly falls back to v1 with documented reason.
- `relay-check.py` passes after smoke.
- rollback path is demonstrated with `bridge-runner.py --force-direct`.
