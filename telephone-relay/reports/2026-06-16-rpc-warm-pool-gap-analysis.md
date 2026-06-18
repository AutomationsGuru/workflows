# RPC Warm-Pool Prototype Gap Analysis

Date: 2026-06-16
Run ID: `20260616-212211`

## HERE

The proven direct relay remains intact and is not replaced.

Current validated assets:

- Direct relay verifier: `relay-check.py`
- Direct relay profiles: `profiles/agent-1.md`, `profiles/agent-2.md`, `profiles/agent-3.md`
- RPC-specific profiles: `profiles/agent-1-rpc.md`, `profiles/agent-2-rpc.md`, `profiles/agent-3-rpc.md`
- RPC controller prototype: `rpc-warm-pool-prototype.py`
- RPC pass receipt: `rpc-runs/20260616-212211/rpc-warm-pool-result.md`
- RPC verifier output: `rpc-runs/20260616-212211/relay-check-rpc.json`

Measured RPC result:

- startup total: `5.01s`
- relay after warm: `36.81s`
- total wall time: `41.84s`
- direct baseline: about `87s`
- final directive: `USER:guru — return verified.`

RPC model stack used:

- Agent 1: `minimax-oauth/MiniMax-M3`
- Agent 2: `xai-oauth/grok-build-0.1`
- Agent 3: `openai-codex/gpt-5.5`

## THERE

A stable cascade bridge should support:

1. warm reusable agent pools;
2. typed/directive-safe routing between layers;
3. verifier-backed completion gates;
4. recovery from provider/model failure;
5. clean run isolation and receipts;
6. promotion from toy token relay to real coding-task relay.

## Gap analysis

| Gap | Current state | Needed next |
| --- | --- | --- |
| Controller maturity | Prototype Python controller works for `guru`. | Harden into a small reusable relay harness with clearer command-line options and tests. |
| Verification | `relay-check.py` supports RPC output overrides and passes. | Add negative tests for bad handoff, bad directives, and missing output files. |
| Recovery | Agent 2 fallback model path exists in prototype. | Exercise fallback intentionally and record receipt. |
| State isolation | RPC uses `--no-session`; outputs go to `rpc-runs/<run_id>/`. | Add run-id to `handoff.md` for multi-run safety. |
| Directive format | Free text directive substrings. | Move to one-line JSON directives for robust parsing. |
| Speed | RPC total ~42s vs direct ~87s. | Measure repeat warm-pool runs without process startup and compare. |
| Complexity | Token relay only. | Next: small coding-task relay with Agent 3 writing a fixture output and Agent 2 reviewing it. |
| Production safety | Prototype only, direct relay untouched. | Keep direct relay as baseline until RPC passes negative tests and coding-task relay. |

## Recommended next bounded slice

Add negative tests and verifier fixtures for `relay-check.py`:

1. copy current passing handoff to a temp dir;
2. mutate final token to `gu` and assert verifier fails;
3. remove an expected history line and assert verifier fails;
4. replace Agent 3 output directive and assert verifier fails;
5. record results in `receipts/`.

After that, run a second RPC benchmark with the same warm pool idea but a slightly more complex payload, such as spelling a longer phrase or producing one small output file.
