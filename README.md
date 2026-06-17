# Agent OS Workflows

This folder stores reusable Agent OS workflow designs before they are promoted into
runtime code, skills, or service adapters.

Workflow documents should be:

- **harness-independent** where possible;
- **local-first** and safe to run without external service mutation by default;
- **packet-oriented**, so different agent lanes can implement the same contract;
- **evidence-backed**, with explicit validation and handoff requirements.

## Current workflows

| Workflow | Purpose | Status |
| --- | --- | --- |
| [`context-cascade-workflow.md`](context-cascade-workflow.md) | Serial layered agent workflow where reasoner, organizer, and executor act as one apparent agent for long-running coding tasks. | Design v0 |
| [`telephone-relay/`](telephone-relay/) | Minimal three-agent relay experiment using one Markdown handoff file to spell `guru`. | Experiment v0 |
| [`cascade-load-relay/`](cascade-load-relay/) | Three-layer coding/dev cascade test: Agent 1 large-context anchor, Agent 2 chunker/integrator, Agent 3 per-chunk executor. | Experiment v0 |
| [`story-cascade-relay/`](story-cascade-relay/) | Advanced multi-cycle story/context smoke suite for 1M -> 512K -> 272K cascade testing. | Design + runnable spec v0 |

## Artifact types

- `*-workflow.md`: human-readable workflow contract and operating model.
- `*.schema.json`: machine-readable packet schemas for harnesses or adapters.
- Future `examples/`: sample mission packets, work packets, and evidence packets.
