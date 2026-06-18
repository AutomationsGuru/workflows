# Persistent Pool Operator Runbook

## Scope

This runbook covers bounded local operation of `persistent-warm-pool.py` for the Telephone Relay bridge. It is for localhost validation and evidence collection only.

Do not change bridge, pool, metrics, cap, or persistence settings while following this runbook unless a separate approved slice explicitly requires it.

## Lifecycle

### Start a pool

Use a fixed port for manual operation or `--port 0` for harness-managed ephemeral operation.

```powershell
cd D:\.agentos\workflows\telephone-relay
python .\persistent-warm-pool.py --host 127.0.0.1 --port 8765 --timeout 300 --tenant-id operator-smoke --pool-size 1 --state-ttl-s 300
```

Expected first useful stdout line is JSON with:

- `status`: `warm` or `ready`
- `url`: pool URL, for example `http://127.0.0.1:8765`
- `pids`: warm Agent 1/2/3 process IDs
- `startup`: one startup record per warm agent

### Check health

```powershell
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/state
```

Healthy idle state:

- `/health.status` is `warm`
- `/health.pids` has `agent1`, `agent2`, `agent3`
- `/health.startup` has three records
- `/health.in_use` is empty after each completed relay
- `/health.run_count` increments after successful relays

### Run a v2 persistent relay

Use fallback disabled when validating persistent-route truth:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:8765 --channel default --tenant-id operator-smoke --run-id operator-smoke-001 --timeout 300 --no-fallback-v1
```

Use fallback enabled only for caller-migration dry runs where preserving completion is the point:

```powershell
python .\rpc_bridge_v2.py --persistent-pool-url http://127.0.0.1:8765 --channel default --tenant-id operator-smoke --run-id operator-smoke-001 --timeout 300
```

### Shutdown

Prefer graceful shutdown:

```powershell
curl -X POST http://127.0.0.1:8765/shutdown
```

After shutdown, confirm there are no remaining pool-owned child processes from the captured `/health.pids` list.

## Timeout triage

When a relay or harness times out, preserve evidence first. Do not restart or clean up until stdout, stderr, health, and state are captured where practical.

1. Capture health and state if the HTTP server still responds:

   ```powershell
   curl http://127.0.0.1:8765/health > .\diagnostics\operator-health-timeout.json
   curl http://127.0.0.1:8765/state > .\diagnostics\operator-state-timeout.json
   ```

2. Inspect whether a lease is stuck:

   - `/health.in_use` non-empty after timeout means a relay lease may still be active or leaked.
   - `/health.run_count` unchanged means the relay did not complete successfully.
   - `/health.pids` unchanged means the warm pool did not churn, even if the relay failed.

3. Check bridge and pool receipts:

   - `bridge-v2-runs/<run-id>/rpc-bridge-v2-result.json`
   - `diagnostics/<run>/pool.stdout.txt`
   - `diagnostics/<run>/pool.stderr.txt`
   - `persistent-pool-runs/<run>/runs/<run-id>/outputs/`

4. Run `relay-check.py` only if both Agent 2 and Agent 3 output files exist:

   ```powershell
   python .\relay-check.py --agent2-output .\persistent-pool-runs\<pool-run>\runs\<run-id>\outputs\agent2-return.txt --agent3-output .\persistent-pool-runs\<pool-run>\runs\<run-id>\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
   ```

5. If HTTP is down or the process exited, record the process exit and preserved stdout/stderr before cleanup.

## Stale-process cleanup

Use narrow cleanup only. Kill the specific PIDs reported by this pool's `/health.pids` or by the harness receipt. Do not run broad process-kill commands against all `pi`, `python`, or `node` processes.

### Preferred cleanup

```powershell
curl -X POST http://127.0.0.1:8765/shutdown
```

### Windows process-tree cleanup by known PID

If graceful shutdown fails, terminate only the known pool parent PID or known child PIDs captured in evidence:

```powershell
taskkill /PID <known-pool-or-child-pid> /T /F
```

Then verify the exact PIDs are gone:

```powershell
Get-Process -Id <pid> -ErrorAction SilentlyContinue
```

### Before restarting

- Confirm the old port is free or choose `--port 0`.
- Preserve the previous `pool-state.json`, stdout, stderr, and harness receipt.
- If persisted state shows stale `in_use`, treat it as diagnostic evidence; do not manually edit persistence unless a separate slice authorizes it.

## Evidence collection

For each validation run, keep these artifacts together:

- command line used to start the pool;
- first readiness JSON line from pool stdout;
- `/health` before relay;
- `/health` after relay;
- `/state` if persistence behavior is relevant;
- `bridge-v2-runs/<run-id>/rpc-bridge-v2-result.json`;
- Agent outputs returned by the bridge response;
- `relay-check.py` output for those Agent 2/3 files;
- pool stdout/stderr;
- final shutdown result.

For warm-state validation, include:

- initial PIDs;
- after-call PIDs;
- `run_count` progression;
- `startup` count before and after;
- statement whether fallback was enabled or disabled.

Existing focused harnesses:

```powershell
python .\persistent-v2-route-validate.py --timeout 300 --run-id live-v2-persistent-<date> --no-fallback-v1
python .\two-call-persistent-pool-smoke.py --timeout 300 --run-id two-call-v2-persistent-<date>
```

Acceptance for promotion-style evidence:

- relay status is `passed`;
- `selected_channel` is `default` for persistent route;
- `fallback_used` is `False` when validating persistent truth;
- relay-check passes;
- `in_use` is empty after completion;
- no unexpected PID churn occurred unless the test intentionally restarted the pool.
