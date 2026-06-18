# RPC Bridge v2 Focused Self-Review

Date: 2026-06-16

## Scope

Reviewed only the bridge surface:

- `rpc_bridge_v2.py`
- `rpc_bridge_v2_selftest.py`
- `rpc-bridge-v2.md`

Out of scope by instruction:

- persistent pool behavior;
- metrics/cap/persistence internals;
- benchmark/warm-pool prototype behavior;
- new features.

## Reference patterns checked

Focused comparison against common patterns used by small public Python HTTP/CLI libraries:

- retry policy shape similar to `urllib3.Retry` / `tenacity` style: bounded attempts, bounded exponential backoff, no retry on admission-control failure;
- transport separation similar to small API clients: typed request/result objects plus injectable transport for tests;
- CLI wrapper pattern similar to small `argparse` tools: receipt output, nonzero exit on failed result;
- public API hygiene: safe defaults, JSON response validation, no hidden mutation of unrelated subsystems.

## Findings

### F1: Negative retry/backoff values could produce an invalid sleep

Severity: low
Status: fixed

`RetryPolicy.delay_for_retry()` bounded upper delay but did not clamp negative values. A caller could create a policy with negative `initial_backoff_s` or `max_backoff_s`, which would pass a negative value to `sleep_fn` in live use.

Patch:

- clamp computed delay and `max_backoff_s` to `>= 0.0`.
- added self-test coverage for negative delay clamp.

### F2: Non-object JSON HTTP responses could break response annotation

Severity: low
Status: fixed

`post_json()` assumed every JSON response decoded to a dict before adding `http_status`. A server returning a valid JSON list/string would raise while annotating status.

Patch:

- wrap non-dict JSON bodies as `{ "body": <parsed> }` before adding `http_status`.

### F3: v1 fallback artifact writes assumed the v1 run directory existed

Severity: low
Status: fixed

`_call_v1_bridge()` wrote v2 stdout/stderr sidecar files under `bridge-runs/<run_id>/`. Normally `bridge-runner.py` creates this directory, but if the v1 subprocess failed before initialization, sidecar writes could fail and mask the original error.

Patch:

- create `bridge-runs/<run_id>/` before launching/writing v1 sidecars.

## Non-findings / kept as-is

- v1 fallback remains intact and separate; no behavior was replaced.
- Cap/overflow responses remain non-retryable.
- v2 remains a call layer, not a scheduler.
- Persistent pool, metrics, cap, and persistence code were not changed for this review.

## Verification evidence

- `python rpc_bridge_v2_selftest.py`: PASS
- `python -m py_compile ...`: PASS
- `python relay-check.py`: PASS
- RPC evidence relay-check against `rpc-runs/20260616-220619`: PASS

## Next review target

Run a live v2 call against a running persistent pool and verify returned artifacts with `relay-check.py`; this will validate transport integration beyond fake transports.
