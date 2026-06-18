# Telephone Relay Latency Budget

## Purpose

Keep the cascade bridge fast enough to feel like one apparent agent while preserving verifier-backed fallback to the direct relay.

This budget uses observable process/RPC timings only. Pi internals, provider queueing, and model-side latency are treated as black-box time unless the RPC protocol exposes more detailed telemetry later.

## Timing fields

| Field | Meaning | Current source |
| --- | --- | --- |
| `env_prep_s` | Local wrapper time to resolve paths, model/profile, command, and receipt directory before process launch. | `rpc-latency-diagnostic.py` |
| `sdk_build_s` | Observable subprocess spawn time for the Pi RPC process. Provider SDK initialization may also appear in `connection_s` if it happens after spawn. | `rpc-latency-diagnostic.py` |
| `connection_s` | Time from `get_state` request to successful response. This marks cold process becoming warm/ready. | `rpc-latency-diagnostic.py` |
| `first_byte_after_launch_s` | Time from process launch to first stdout/stderr line observed by the wrapper. | `rpc-latency-diagnostic.py` |
| `prompt_s` | Time from prompt request through `agent_end` and `get_last_assistant_text`. | `rpc-latency-diagnostic.py` |
| `startup_total_s` | Sum of three warm-pool agent startups for a full relay. | `rpc-warm-pool-prototype.py` receipts |
| `relay_elapsed_s` | Sum of all warm-pool prompt turns after startup. | `rpc-warm-pool-prototype.py` receipts |
| `total_elapsed_s` | Wall-clock time for the whole bridge or diagnostic run. | bridge/diagnostic receipts |

## Initial observed baseline

Latest diagnostic receipt: `diagnostics/20260616-215815/latency-diagnostic.md`

| Metric | Value |
| --- | ---: |
| env prep | 0.002s |
| SDK/process spawn | 0.011s |
| connection/get_state | 1.859s |
| first byte after launch | 1.870s |
| prompt round trip | 10.445s |
| diagnostic total | 12.395s |

Latest bridge receipts:

| Path | Mode | Total |
| --- | --- | ---: |
| `bridge-runs/20260616-214545/bridge-result.md` | RPC preferred | 59.09s |
| `bridge-runs/20260616-214655/bridge-result.md` | direct fallback proof | 81.22s |

Latest RPC warm-pool receipt: `rpc-runs/20260616-214545/rpc-warm-pool-result.md`

| Metric | Value |
| --- | ---: |
| startup total | 5.49s |
| relay after warm | 53.11s |
| total | 58.61s |

## Budget targets for the next slice

| Tier | Target | Reason |
| --- | ---: | --- |
| Local wrapper/env prep | < 0.10s | Should be negligible. |
| One-agent cold-to-warm connection | < 5s | Startup should not dominate over model turns. |
| First byte after launch | < 5s | Detects CLI/provider bootstrap stalls. |
| One tiny prompt round trip | < 20s | Allows 5-hop relay to stay under ~100s even without deeper optimization. |
| Three-agent startup total | < 15s | Keeps warm-pool overhead bounded. |
| Full RPC relay total | < direct fallback total | RPC should remain useful before replacing anything. |

## Regression signals

Treat any of these as YELLOW until explained:

- `first_byte_after_launch_s` missing or > 10s.
- `connection_s` > 10s for a healthy provider.
- `prompt_s` > 30s for the tiny `g` transition.
- RPC bridge slower than direct fallback in two consecutive comparable runs.
- Diagnostic leaves `handoff.md` mutated after a restored run.

## Commands

Run one-agent latency diagnostic:

```powershell
python .\rpc-latency-diagnostic.py --timeout 120
```

Run RPC bridge with direct fallback available:

```powershell
python .\bridge-runner.py --timeout 300
```

Force direct fallback proof:

```powershell
python .\bridge-runner.py --timeout 300 --force-direct
```

Verify the current relay state:

```powershell
python .\relay-check.py
```

## Next instrumentation step

Add a forced-RPC-failure bridge test and assert that fallback preserves the same final `relay-check.py` PASS evidence. After that, promote JSON directive parsing and per-agent run IDs in `handoff.md`.
