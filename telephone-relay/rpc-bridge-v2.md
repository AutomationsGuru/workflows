# RPC Bridge v2 API

## Purpose

`rpc_bridge_v2.py` is a small typed call layer above the existing relay paths. It adds:

- channel routing;
- retry/backoff;
- per-call stats;
- explicit v1 bridge fallback.

It does not replace `bridge-runner.py`. The v1 bridge remains the fallback path.

## Typed objects

| Type | Purpose |
| --- | --- |
| `RetryPolicy` | `max_attempts`, `initial_backoff_s`, `multiplier`, `max_backoff_s`. |
| `ChannelRoute` | Named route with `kind`: `persistent` or `v1`. Persistent routes require `url`. |
| `RpcBridgeV2Request` | `run_id`, `channel`, `tenant_id`, and `timeout_s`. |
| `CallAttempt` | One attempt record: channel, kind, attempt number, status, elapsed, error, backoff. |
| `CallStats` | Aggregate counters: attempts, retries, successes, failures, fallback, total backoff, elapsed. |
| `RpcBridgeV2Result` | Final status, selected channel, response payload, stats, and error. |

## Channel routing

Routes are keyed by channel name:

```python
routes = {
    "default": ChannelRoute(name="default", kind="persistent", url="http://127.0.0.1:8765"),
    "v1": ChannelRoute(name="v1", kind="v1"),
}
```

A request names its desired channel:

```python
request = RpcBridgeV2Request(run_id="demo-v2-001", channel="default", tenant_id="demo")
```

If the requested channel is missing, v2 uses `default`. If the selected persistent route fails and `fallback_v1=True`, v2 calls the existing `bridge-runner.py` path.

## Retry/backoff

Persistent and v1 routes share the same retry wrapper.

Default policy:

```python
RetryPolicy(max_attempts=3, initial_backoff_s=0.25, multiplier=2.0, max_backoff_s=2.0)
```

Non-passed statuses are retried except clean cap/overflow responses:

- `status == "overflow"`
- `http_status == 429`

Those are treated as clean admission-control failures and are not retried.

## Call stats

Every call returns `CallStats`:

```json
{
  "attempts": 2,
  "retries": 1,
  "successes": 1,
  "failures": 1,
  "fallback_used": false,
  "backoff_total_s": 0.25,
  "elapsed_s": 1.23,
  "attempts_detail": []
}
```

Receipts are written under:

```text
bridge-v2-runs/<run_id>/rpc-bridge-v2-result.json
bridge-v2-runs/<run_id>/rpc-bridge-v2-result.md
```

## CLI examples

Use a persistent pool channel:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:8765 --tenant-id demo --run-id demo-v2-001 --timeout 300
```

Use v1 path directly:

```powershell
python .\rpc_bridge_v2.py --run-id demo-v2-v1 --timeout 300
```

Disable v1 fallback:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:8765 --no-fallback-v1
```

Tune retry/backoff:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:8765 --max-attempts 2 --initial-backoff-s 0.1
```

## Fast self-test

The self-test uses fake transports. It does not launch Pi or the persistent pool.

```powershell
python .\rpc_bridge_v2_selftest.py
```

It proves:

1. a transient persistent-channel failure retries and then succeeds;
2. a persistent-channel failure falls back to the v1 route when enabled;
3. call stats record attempts, retries, failures, successes, and fallback state.

## Limits

- v2 is a call layer, not a scheduler.
- It does not change the persistent pool, cap, metrics, or persistence model.
- Live persistent-pool reliability still depends on `/relay` and `relay-check.py` evidence.
