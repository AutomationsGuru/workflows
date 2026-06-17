# Persistent Warm Pool API Reference

## Scope

`persistent-warm-pool.py` is the local HTTP wrapper for keeping Telephone Relay RPC agents warm across calls. It is separate from `rpc-warm-pool-prototype.py`, which remains the benchmark/prototype path.

The pool is intended for localhost, single-machine experimentation. It is not a production multi-user service.

## Start command

```powershell
python .\persistent-warm-pool.py --host 127.0.0.1 --port 8765 --timeout 240 --tenant-id default --pool-size 1 --state-ttl-s 300
```

Use `--port 0` to request an ephemeral port. The server prints a first-line JSON readiness object with the selected URL.

## Configuration

| Flag | Default | Meaning |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Bind address. Keep localhost unless explicitly testing remote access. |
| `--port` | `8765` | HTTP port. `0` lets the OS choose. |
| `--timeout` | `240` | Per-turn RPC timeout in seconds. Also stored in tenant state. |
| `--agent2-model` | `xai-oauth/grok-build-0.1` | Primary Agent 2 model for the pool. Agent 1 and 3 use the warm-pool prototype defaults. |
| `--agent2-fallback-model` | `openai-codex/gpt-5.5` | Agent 2 model to switch to if the primary Agent 2 RPC model fails during relay. |
| `--tenant-id` | `default` | Bootstrap tenant ID. Requests may override with `tenant_id`. |
| `--pool-size` | `1` | Per-tenant hard cap for concurrent leases. |
| `--state-file` | `<run_root>/pool-state.json` | Optional path for persisted logical pool state. |
| `--state-ttl-s` | `300` | TTL for reloading persisted state on restart. |

## Sizing model

Current implementation starts one warm set of three RPC agents and serializes relay execution with an internal lock. The `pool_size` field is a logical per-tenant lease cap used for admission control and persistence bookkeeping.

Practical guidance:

- `pool_size=1`: safest default; one in-flight lease per tenant.
- Increase only after an HTTP-level overflow test and real concurrent relay routing exist.
- Use separate server processes for truly independent live pools until concurrent agent sets are implemented.

## Cap and overflow behavior

Each relay call creates a lease ID shaped like:

```text
<tenant_id>:<uuid>
```

The pool compares active leases for that tenant against the tenant's configured size.

If the tenant is at cap, `/relay` returns HTTP `429` with JSON similar to:

```json
{
  "status": "overflow",
  "error": "tenant 'default' pool cap reached: 1/1"
}
```

Successful or failed relay paths release the lease in a `finally` block. The scale test verifies no leaked leases after 100 acquire/release cycles.

## HTTP API

### `GET /health`

Returns live pool status and observability fields.

Important fields:

| Field | Meaning |
| --- | --- |
| `status` | `warm` or `closed`. |
| `agent2_model` | Active Agent 2 model. |
| `started_at` | Pool start time. |
| `run_count` | Total successful relay calls in this process. |
| `pids` | Agent process IDs keyed by `agent1`, `agent2`, `agent3`. |
| `startup` | Startup timing records for warm agents. |
| `state_file` | Current persistence path. |
| `state_loaded` | Whether persisted state was loaded on startup. |
| `state_load_reason` | `loaded`, `missing`, `expired`, or `invalid: ...`. |
| `state_ttl_s` | Persistence TTL. |
| `tenants` | Tenant metadata map. |
| `sizes` | Per-tenant configured caps. |
| `in_use` | Active lease IDs. Should be empty after idle relay completion. |

### `GET /state`

Returns the serialized logical pool state:

```json
{
  "version": 1,
  "saved_at": 0,
  "expires_at": 0,
  "tenants": {},
  "sizes": {},
  "in_use": []
}
```

Use this for persistence debugging rather than health checking.

### `POST /relay`

Runs one Telephone Relay through the warm pool.

Request body:

```json
{
  "tenant_id": "default",
  "run_id": "optional-run-id"
}
```

Response on success:

```json
{
  "status": "passed",
  "run_id": "optional-run-id",
  "tenant_id": "default",
  "run_count": 1,
  "relay_elapsed_s": 42.0,
  "total_elapsed_s": 43.0,
  "agent2_output": ".../agent2-return.txt",
  "agent3_output": ".../agent3-pivot.txt",
  "agent1_output": ".../agent1-final.txt"
}
```

The bridge can call this path with:

```powershell
python .\bridge-runner.py --persistent-pool-url http://127.0.0.1:8765 --timeout 300
```

### `POST /shutdown`

Requests graceful shutdown. The pool persists state and stops child RPC process trees.

## Metrics / observability

Current metrics are JSON fields exposed via `/health`, `/state`, and test receipts rather than a Prometheus endpoint.

Available live counters/gauges:

| Source | Field | Meaning |
| --- | --- | --- |
| `/health` | `run_count` | Successful relay count in this process. |
| `/health` | `tenants.<id>.run_count` | Successful relay count for a tenant. |
| `/health` | `sizes` | Configured per-tenant cap. |
| `/health` | `in_use` | Active leases. Non-empty while a relay is in flight. |
| `/health` | `startup` | Warm-agent startup timings. |
| `/health` | `fallback_events` | Agent 2 fallback switch reasons, if the primary model failed and the fallback model was used. |
| `/health` | `pids` | Child process IDs for leak checks. |
| `pool-scale-test.py` | CSV timing rows | Per-tenant acquire, cap-check, and release latency. |

The logical scale test writes raw CSV and a markdown report:

```powershell
python .\pool-scale-test.py --tenants 100 --pool-size 1
```

## Persistence

The pool persists logical state to `--state-file` on initialization, acquire, release, and close.

Persisted state includes:

- `version`
- `saved_at`
- `expires_at`
- `tenants`
- `sizes`
- `in_use`

Reload behavior:

- if the file is missing: start fresh with `state_load_reason=missing`;
- if invalid: start fresh with `state_load_reason=invalid: ...`;
- if expired by `expires_at` or `saved_at + --state-ttl-s`: start fresh with `state_load_reason=expired`;
- otherwise reload with `state_load_reason=loaded`.

Persisted `in_use` is logical metadata, not proof that an old process survived. After a real crash/restart, operators should inspect `in_use` and apply cleanup policy before accepting new production-like work.

## Tiny example

Terminal 1:

```powershell
python .\persistent-warm-pool.py --port 8765 --tenant-id demo --pool-size 1 --state-file .\persistent-pool-runs\demo-state.json --state-ttl-s 300
```

Terminal 2:

```powershell
python .\bridge-runner.py --persistent-pool-url http://127.0.0.1:8765 --timeout 300 --run-id demo-persistent-001
python .\relay-check.py --agent2-output .\persistent-pool-runs\<run>\runs\demo-persistent-001\outputs\agent2-return.txt --agent3-output .\persistent-pool-runs\<run>\runs\demo-persistent-001\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
```

Inspect status:

```powershell
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/state
```

Shutdown:

```powershell
curl -X POST http://127.0.0.1:8765/shutdown
```

## Known limits

- Relay execution is still serialized by one lock.
- `pool_size` is currently logical admission control, not live parallel agent-set allocation.
- No auth; bind to localhost.
- Metrics are JSON/CSV artifacts, not Prometheus/OpenTelemetry.
- The direct relay remains the safety fallback.
