# Bridge v1 Readiness Report

Date: 2026-06-16

## Acceptance checklist

| Check | Required evidence | Result |
| --- | --- | --- |
| Direct fallback remains intact | `bridge-runner.py --force-direct` passes and `relay-check.py` passes | PASS |
| RPC warm-pool path works independently | `rpc-warm-pool-prototype.py` passes and RPC output override `relay-check.py` passes | PASS |
| Bridge v1 selects a working path | `bridge-runner.py` passes with selected mode recorded | PASS |
| Verifier-backed handoff | final `handoff.md`, ordered history, child directives, and session hygiene pass | PASS |
| Fallback is not removed | direct fallback proof remains runnable after RPC proof | PASS |
| No migration to v2 in this slice | no v2 commands or migration changes used | PASS |
| Repo review gate available | CodeRabbit can review changed repository state | BLOCKED: not a git repo |

## Evidence runs

### 1. Direct fallback proof

Command:

```powershell
python .\bridge-runner.py --timeout 300 --force-direct --run-id bridge-v1-direct-20260616
```

Result:

- status: `passed`
- selected mode: `direct`
- total elapsed: `89.76s`
- command elapsed: `89.61s`
- verifier: `relay-check-direct`, exit `0`
- receipt: `bridge-runs/bridge-v1-direct-20260616/bridge-result.md`
- additional relay-check capture: `bridge-runs/bridge-v1-direct-20260616/relay-check-direct.txt`

### 2. RPC warm-pool proof

Command:

```powershell
python .\rpc-warm-pool-prototype.py --timeout 300
```

Result:

- run ID: `20260616-233118`
- status: `passed`
- startup total: `5.07s`
- relay after warm: `38.69s`
- total elapsed: `44.95s`
- receipt: `rpc-runs/20260616-233118/rpc-warm-pool-result.md`

Verifier:

```powershell
python .\relay-check.py --agent2-output .\rpc-runs\20260616-233118\outputs\agent2-return.txt --agent3-output .\rpc-runs\20260616-233118\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
```

Result: PASS. Capture: `rpc-runs/20260616-233118/relay-check-rpc.txt`.

### 3. Bridge-runner proof

Command:

```powershell
python .\bridge-runner.py --timeout 300 --run-id bridge-v1-runner-20260616
```

Result:

- status: `passed`
- selected mode: `rpc`
- attempted modes: `rpc`
- total elapsed: `42.97s`
- RPC command elapsed: `42.84s`
- bridge verifier: `relay-check-rpc`, exit `0`
- receipt: `bridge-runs/bridge-v1-runner-20260616/bridge-result.md`
- underlying RPC receipt: `rpc-runs/20260616-233215/rpc-warm-pool-result.md`

Additional verifier:

```powershell
python .\relay-check.py --agent2-output .\rpc-runs\20260616-233215\outputs\agent2-return.txt --agent3-output .\rpc-runs\20260616-233215\outputs\agent3-pivot.txt --skip-exit-files --skip-session-id-check
```

Result: PASS. Capture: `bridge-runs/bridge-v1-runner-20260616/relay-check-bridge-rpc.txt`.

## Readiness verdict

Bridge v1 is functionally ready for the `guru` relay scope:

- direct fallback is proven;
- independent RPC warm-pool is proven;
- bridge-runner selects and verifies RPC successfully;
- relay-check passes for every evidence path requested;
- v2 migration was not performed in this slice.

Operational readiness remains YELLOW because CodeRabbit cannot run against `D:\.agentos\workflows` while it is not a git repository.

## Next best action

Move or initialize the telephone-relay work in a git repository so CodeRabbit can review the accumulated bridge surface. If that is not desired, explicitly accept the local-review-only risk and proceed to a live v2 persistent-pool smoke after this v1 baseline is frozen.
