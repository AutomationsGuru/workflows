# Agent 2 OpenAI Primary Configuration

Date: 2026-06-17

## Scope

Configured `openai-codex/gpt-5.5` as the primary Agent 2 model for the live persistent-pool/default-caller path because `xai-oauth/grok-build-0.1` has current OAuth failures.

This slice changes only model defaults/configuration and related documentation/test harness defaults. It does not change bridge routing logic, pool metrics, cap enforcement, or persistence behavior.

## Changed defaults

- `persistent-warm-pool.py --agent2-model`: `openai-codex/gpt-5.5`
- persistent validation harness default Agent 2 model: `openai-codex/gpt-5.5`
- caller migration smoke default Agent 2 model: `openai-codex/gpt-5.5`
- generic two-call persistent smoke default Agent 2 model: `openai-codex/gpt-5.5`
- logical pool scale test model label: `openai-codex/gpt-5.5`
- direct relay command docs/profile snippets: `openai-codex/gpt-5.5`
- `pool-api-reference.md` default model documentation updated.

The dedicated fallback-activation harness remains intentionally configured with `xai-oauth/grok-build-0.1` as primary so it can continue proving the fallback path.

## Validation evidence

### Persistent caller smoke

```powershell
python .\caller-migration-dry-run.py --timeout 300 --run-id agent2-openai-primary-caller-smoke-20260617
```

Result: PASS.

- selected channel: `default`
- v1 fallback used: `False`
- pool run_count: `1`
- pool fallback events: `[]`
- PIDs before/after unchanged: `agent1=31380`, `agent2=35408`, `agent3=37324`
- relay-check: `True`
- receipt: `diagnostics/20260617-045347-caller-migration-dry-run/caller-migration-dry-run.md`

### Two-call persistent warm-state smoke

```powershell
python .\two-call-persistent-pool-smoke.py --timeout 300 --run-id agent2-openai-primary-two-call-20260617
```

Result: PASS.

- PIDs unchanged: `True`
- both relay-checks pass: `True`
- second call already warm: `True`
- run_count progression: `0 -> 1 -> 2`
- Agent 2 model after second call: `openai-codex/gpt-5.5`
- fallback events: `[]`
- stable PIDs: `agent1=9804`, `agent2=34000`, `agent3=33948`
- receipt: `diagnostics/20260617-045440-two-call-persistent-pool/two-call-persistent-pool-smoke.md`

### Fallback drill

```powershell
python .\fallback-engagement-drill.py --timeout 300 --run-id agent2-openai-primary-fallback-drill-20260617
```

Result: PASS.

- selected channel: `v1`
- v1 fallback used: `True`
- persistent failures: `2`
- v1 successes: `1`
- relay-check: `True`
- receipt: `diagnostics/20260617-045628-fallback-engagement-drill/fallback-engagement-drill.md`

## Risk notes

- `xai-oauth/grok-build-0.1` remains documented in historical reports as a previous primary/failing route.
- `rpc-warm-pool-prototype.py` remains unchanged as requested benchmark/prototype path; it still contains its own primary/fallback behavior.
- If the xAI/Grok OAuth route is repaired later, restoring it as primary should be a separate bounded config slice with the same caller and fallback smoke checks.

## Next best action

Run one final clean default-caller promotion smoke on a fresh pool and then archive the validated default-route evidence into a short readiness summary.
