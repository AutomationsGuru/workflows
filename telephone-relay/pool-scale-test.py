#!/usr/bin/env python3
"""Scale test for persistent warm-pool tenant acquire/release bookkeeping.

This test intentionally does not start Pi RPC agents. It exercises the logical
persistent pool path for 100 tenants: tenant registration, acquire, hard-cap
overflow, release, state persistence, and leak detection.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POOL_PATH = ROOT / "persistent-warm-pool.py"
# Pi CLI model IDs include the provider route; this is not a raw OpenAI API model name.
DEFAULT_AGENT2_MODEL = "openai-codex/gpt-5.5"


@dataclass
class TenantTiming:
    tenant_id: str
    acquire_ms: float
    overflow_check_ms: float
    release_ms: float
    cap_enforced: bool


@dataclass
class ScaleSummary:
    status: str
    tenant_count: int
    pool_size: int
    acquired: int
    released: int
    cap_checks: int
    cap_violations: int
    leaked_leases: int
    state_file: str
    raw_timings_csv: str
    p50_acquire_ms: float
    p95_acquire_ms: float
    max_acquire_ms: float
    p50_release_ms: float
    p95_release_ms: float
    max_release_ms: float
    elapsed_s: float
    error: str | None = None


def load_pool_module() -> Any:
    spec = importlib.util.spec_from_file_location("persistent_warm_pool", POOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {POOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def write_outputs(out_dir: Path, timings: list[TenantTiming], summary: ScaleSummary) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = Path(summary.raw_timings_csv)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["tenant_id", "acquire_ms", "overflow_check_ms", "release_ms", "cap_enforced"],
        )
        writer.writeheader()
        for item in timings:
            writer.writerow(asdict(item))

    (out_dir / "pool-scale-summary.json").write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    lines = [
        "# Persistent Pool Scale Test",
        "",
        f"Status: `{summary.status}`",
        f"Tenants: `{summary.tenant_count}`",
        f"Pool size per tenant: `{summary.pool_size}`",
        f"Acquired: `{summary.acquired}`",
        f"Released: `{summary.released}`",
        f"Cap checks: `{summary.cap_checks}`",
        f"Cap violations: `{summary.cap_violations}`",
        f"Leaked leases: `{summary.leaked_leases}`",
        f"Elapsed: {summary.elapsed_s:.3f}s",
        "",
        "## Acquire latency",
        "",
        f"- p50: {summary.p50_acquire_ms:.3f} ms",
        f"- p95: {summary.p95_acquire_ms:.3f} ms",
        f"- max: {summary.max_acquire_ms:.3f} ms",
        "",
        "## Release latency",
        "",
        f"- p50: {summary.p50_release_ms:.3f} ms",
        f"- p95: {summary.p95_release_ms:.3f} ms",
        f"- max: {summary.max_release_ms:.3f} ms",
        "",
        "## Artifacts",
        "",
        f"- Raw timings CSV: `{summary.raw_timings_csv}`",
        f"- State file: `{summary.state_file}`",
    ]
    if summary.error:
        lines.extend(["", "## Error", "", "```text", summary.error, "```"])
    (out_dir / "pool-scale-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise persistent pool acquire/release scale for many tenants.")
    parser.add_argument("--tenants", type=int, default=100)
    parser.add_argument("--pool-size", type=int, default=1)
    parser.add_argument("--state-ttl-s", type=int, default=300)
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = ROOT / "diagnostics" / (time.strftime("%Y%m%d-%H%M%S") + "-pool-scale")
    state_file = out_dir / "pool-state.json"
    raw_csv = out_dir / "pool-scale-timings.csv"
    timings: list[TenantTiming] = []
    error: str | None = None

    try:
        module = load_pool_module()
        pool = module.PersistentPool(
            agent2_model=DEFAULT_AGENT2_MODEL,
            timeout_s=30,
            run_root=out_dir / "run-root",
            tenant_id="tenant-bootstrap",
            pool_size=args.pool_size,
            state_file=state_file,
            state_ttl_s=args.state_ttl_s,
        )

        for index in range(args.tenants):
            tenant_id = f"tenant-{index:03d}"
            pool.ensure_tenant(tenant_id, args.pool_size, 30, DEFAULT_AGENT2_MODEL)

            lease_id = f"{tenant_id}:lease-primary"
            acquire_started = time.perf_counter_ns()
            pool.acquire(tenant_id, lease_id)
            acquire_ms = (time.perf_counter_ns() - acquire_started) / 1_000_000

            overflow_started = time.perf_counter_ns()
            cap_enforced = False
            try:
                pool.acquire(tenant_id, f"{tenant_id}:lease-overflow")
            except module.PoolOverflowError:
                cap_enforced = True
            overflow_ms = (time.perf_counter_ns() - overflow_started) / 1_000_000

            release_started = time.perf_counter_ns()
            pool.release(lease_id)
            release_ms = (time.perf_counter_ns() - release_started) / 1_000_000

            timings.append(
                TenantTiming(
                    tenant_id=tenant_id,
                    acquire_ms=acquire_ms,
                    overflow_check_ms=overflow_ms,
                    release_ms=release_ms,
                    cap_enforced=cap_enforced,
                )
            )

        pool.persist_state()
        leaked_leases = len(pool.state.in_use)
        cap_violations = sum(1 for item in timings if not item.cap_enforced)
        status = "passed" if len(timings) == args.tenants and leaked_leases == 0 and cap_violations == 0 else "failed"
    except Exception as exc:
        status = "failed"
        leaked_leases = -1
        cap_violations = -1
        error = str(exc)

    acquire_values = [item.acquire_ms for item in timings]
    release_values = [item.release_ms for item in timings]
    summary = ScaleSummary(
        status=status,
        tenant_count=args.tenants,
        pool_size=args.pool_size,
        acquired=len(timings),
        released=len(timings),
        cap_checks=len(timings),
        cap_violations=cap_violations,
        leaked_leases=leaked_leases,
        state_file=str(state_file),
        raw_timings_csv=str(raw_csv),
        p50_acquire_ms=statistics.median(acquire_values) if acquire_values else 0.0,
        p95_acquire_ms=percentile(acquire_values, 95),
        max_acquire_ms=max(acquire_values) if acquire_values else 0.0,
        p50_release_ms=statistics.median(release_values) if release_values else 0.0,
        p95_release_ms=percentile(release_values, 95),
        max_release_ms=max(release_values) if release_values else 0.0,
        elapsed_s=time.perf_counter() - started,
        error=error,
    )
    write_outputs(out_dir, timings, summary)
    print(f"pool-scale-test: {summary.status.upper()}")
    print(f"tenants={summary.tenant_count}")
    print(f"cap_violations={summary.cap_violations}")
    print(f"leaked_leases={summary.leaked_leases}")
    print(f"p95_acquire_ms={summary.p95_acquire_ms:.3f}")
    print(f"p95_release_ms={summary.p95_release_ms:.3f}")
    print(f"receipt={out_dir / 'pool-scale-report.md'}")
    return 0 if summary.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
