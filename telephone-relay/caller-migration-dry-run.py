#!/usr/bin/env python3
"""Caller-migration dry run for RPC Bridge v2 persistent routing.

This harness exercises the caller-facing default route wrapper with a persistent
pool URL supplied through routing config environment, leaving v1 fallback enabled.
It proves that the healthy persistent route completes without needing fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
HANDOFF = ROOT / "handoff.md"
RESET_HANDOFF = "# Telephone Relay Handoff\n\nCurrent token:\n\nHistory:\n"


def reset_handoff() -> None:
    HANDOFF.write_text(RESET_HANDOFF, encoding="utf-8")


@dataclass
class CallerMigrationResult:
    status: str
    run_id: str
    tenant_id: str
    pool_url: str | None = None
    fallback_enabled: bool = True
    bridge_exit: int = -1
    bridge_status: str | None = None
    selected_channel: str | None = None
    fallback_used: bool | None = None
    pool_run_count: int | None = None
    in_use_after: list[str] = field(default_factory=list)
    pids_before: dict[str, int | None] = field(default_factory=dict)
    pids_after: dict[str, int | None] = field(default_factory=dict)
    pool_fallback_events: list[str] = field(default_factory=list)
    relay_check_ok: bool = False
    v2_receipt: str | None = None
    agent2_output: str | None = None
    agent3_output: str | None = None
    relay_check_capture: str | None = None
    elapsed_s: float = 0.0
    error: str | None = None


def pipe_reader(stream, output_path: Path, lines: queue.Queue[str] | None = None) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        for line in stream:
            handle.write(line)
            handle.flush()
            if lines is not None:
                lines.put(line.rstrip("\r\n"))


def wait_for_ready(proc: subprocess.Popen[str], lines: queue.Queue[str], timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"persistent pool exited early with {proc.returncode}")
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("url") and data.get("status") in {"ready", "warm"}:
            return data
    raise RuntimeError("timed out waiting for persistent pool readiness")


def get_json(url: str, timeout_s: int = 15) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any] | None = None, timeout_s: int = 15) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def run_caller_surface(run_id: str, tenant_id: str, pool_url: str, timeout_s: int, out_dir: Path) -> int:
    command = [
        PYTHON,
        "caller-default-route.py",
        "--tenant-id",
        tenant_id,
        "--run-id",
        run_id,
        "--timeout",
        str(timeout_s),
    ]
    (out_dir / "caller-command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["TELEPHONE_RELAY_PERSISTENT_POOL_URL"] = pool_url
    proc = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s + 180,
    )
    (out_dir / "rpc_bridge_v2.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "rpc_bridge_v2.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode


def run_relay_check(agent2_output: str, agent3_output: str, out_dir: Path) -> tuple[bool, Path]:
    proc = subprocess.run(
        [
            PYTHON,
            "relay-check.py",
            "--agent2-output",
            agent2_output,
            "--agent3-output",
            agent3_output,
            "--skip-exit-files",
            "--skip-session-id-check",
            "--json",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    capture = out_dir / "relay-check.json"
    capture.write_text(proc.stdout, encoding="utf-8")
    if proc.stderr:
        (out_dir / "relay-check.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode == 0, capture


def stop_process_tree(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform.startswith("win"):
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()
    proc.wait(timeout=15)


def write_receipt(out_dir: Path, result: CallerMigrationResult) -> Path:
    (out_dir / "caller-migration-dry-run.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# Caller-Migration Dry Run",
        "",
        f"Status: `{result.status}`",
        f"Run ID: `{result.run_id}`",
        f"Tenant: `{result.tenant_id}`",
        f"Pool URL: `{result.pool_url}`",
        f"Elapsed: {result.elapsed_s:.2f}s",
        "",
        "## Caller surface",
        "",
        "- command: `caller-default-route.py --run-id <id> ...` with `TELEPHONE_RELAY_PERSISTENT_POOL_URL=<pool>`",
        f"- v1 fallback enabled: `{result.fallback_enabled}`",
        f"- bridge exit: `{result.bridge_exit}`",
        f"- bridge status: `{result.bridge_status}`",
        f"- selected channel: `{result.selected_channel}`",
        f"- fallback used: `{result.fallback_used}`",
        "",
        "## Persistent pool evidence",
        "",
        f"- pids before: `{result.pids_before}`",
        f"- pids after: `{result.pids_after}`",
        f"- pool run_count: `{result.pool_run_count}`",
        f"- in_use after completion: `{result.in_use_after}`",
        f"- pool fallback events: `{result.pool_fallback_events}`",
        "",
        "## Verifier",
        "",
        f"- relay-check ok: `{result.relay_check_ok}`",
        f"- v2 receipt: `{result.v2_receipt}`",
        f"- agent2 output: `{result.agent2_output}`",
        f"- agent3 output: `{result.agent3_output}`",
        f"- relay-check capture: `{result.relay_check_capture}`",
    ]
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])
    receipt = out_dir / "caller-migration-dry-run.md"
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise caller-facing v2 persistent route with v1 fallback enabled.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tenant-id", default="caller-migration-dry-run")
    parser.add_argument("--run-id", default="caller-migration-dry-run-" + time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--agent2-model", default="xai-oauth/grok-build-0.1")
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = ROOT / "diagnostics" / (time.strftime("%Y%m%d-%H%M%S") + "-caller-migration-dry-run")
    out_dir.mkdir(parents=True, exist_ok=True)
    pool_lines: queue.Queue[str] = queue.Queue()
    proc: subprocess.Popen[str] | None = None
    result = CallerMigrationResult(status="failed", run_id=args.run_id, tenant_id=args.tenant_id)

    try:
        proc = subprocess.Popen(
            [
                PYTHON,
                "persistent-warm-pool.py",
                "--port",
                "0",
                "--timeout",
                str(args.timeout),
                "--tenant-id",
                args.tenant_id,
                "--agent2-model",
                args.agent2_model,
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None and proc.stderr is not None
        threading.Thread(target=pipe_reader, args=(proc.stdout, out_dir / "pool.stdout.txt", pool_lines), daemon=True).start()
        threading.Thread(target=pipe_reader, args=(proc.stderr, out_dir / "pool.stderr.txt", None), daemon=True).start()

        ready = wait_for_ready(proc, pool_lines, timeout_s=args.timeout)
        result.pool_url = str(ready["url"])
        health_before = get_json(result.pool_url.rstrip("/") + "/health")
        (out_dir / "health-before.json").write_text(json.dumps(health_before, indent=2), encoding="utf-8")
        result.pids_before = health_before.get("pids") or {}

        reset_handoff()
        result.bridge_exit = run_caller_surface(args.run_id, args.tenant_id, result.pool_url, args.timeout, out_dir)

        v2_json = ROOT / "bridge-v2-runs" / args.run_id / "rpc-bridge-v2-result.json"
        if not v2_json.exists():
            raise RuntimeError(f"missing v2 receipt: {v2_json}")
        v2 = json.loads(v2_json.read_text(encoding="utf-8"))
        result.v2_receipt = str(v2_json)
        result.bridge_status = v2.get("status")
        result.selected_channel = v2.get("selected_channel")
        if "fallback_used" not in v2:
            raise RuntimeError("v2 receipt missing 'fallback_used' field")
        result.fallback_used = bool(v2["fallback_used"])
        response = v2.get("response") if isinstance(v2.get("response"), dict) else {}
        result.pool_run_count = response.get("run_count")
        result.agent2_output = response.get("agent2_output")
        result.agent3_output = response.get("agent3_output")

        health_after = get_json(result.pool_url.rstrip("/") + "/health")
        (out_dir / "health-after.json").write_text(json.dumps(health_after, indent=2), encoding="utf-8")
        result.pids_after = health_after.get("pids") or {}
        result.in_use_after = list(health_after.get("in_use") or [])
        result.pool_fallback_events = list(health_after.get("fallback_events") or [])

        if result.bridge_exit != 0:
            raise RuntimeError(f"caller surface exited {result.bridge_exit}")
        if result.bridge_status != "passed":
            raise RuntimeError(f"bridge status not passed: {result.bridge_status}")
        if result.selected_channel != "default":
            raise RuntimeError(f"expected persistent default channel, got {result.selected_channel!r}")
        if result.fallback_used:
            raise RuntimeError("fallback was available but should not be needed on healthy persistent route")
        if result.pool_run_count != 1:
            raise RuntimeError(f"expected pool run_count 1, got {result.pool_run_count!r}")
        if result.in_use_after:
            raise RuntimeError(f"pool leases still in use after completion: {result.in_use_after!r}")
        if result.pids_before != result.pids_after and not result.pool_fallback_events:
            raise RuntimeError("pool PIDs changed during caller dry run without a recorded pool fallback event")
        if not isinstance(result.agent2_output, str) or not isinstance(result.agent3_output, str):
            raise RuntimeError("missing Agent 2/3 output paths in bridge response")

        relay_ok, relay_capture = run_relay_check(result.agent2_output, result.agent3_output, out_dir)
        result.relay_check_ok = relay_ok
        result.relay_check_capture = str(relay_capture)
        if not relay_ok:
            raise RuntimeError("relay-check failed")

        result.status = "passed"
    except Exception as exc:
        result.error = str(exc)
    finally:
        result.elapsed_s = time.perf_counter() - started
        if proc is not None:
            try:
                if result.pool_url:
                    post_json(result.pool_url.rstrip("/") + "/shutdown", timeout_s=10)
                proc.wait(timeout=15)
            except Exception:
                stop_process_tree(proc)

    receipt = write_receipt(out_dir, result)
    print(f"caller-migration-dry-run: {result.status.upper()}")
    print(f"fallback_enabled={result.fallback_enabled} selected_channel={result.selected_channel} fallback_used={result.fallback_used}")
    print(f"relay_check_ok={result.relay_check_ok}")
    print(f"receipt={receipt}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
