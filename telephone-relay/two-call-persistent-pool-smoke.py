#!/usr/bin/env python3
"""Two-call warm-state smoke for the persistent pool route.

Starts one persistent-warm-pool.py process, runs two sequential RPC Bridge v2
/relay calls through the same pool, verifies both outputs with relay-check.py,
and proves the second call used the already-warm pool by checking process IDs,
run_count, and startup metadata across calls.
"""

from __future__ import annotations

import argparse
import json
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


@dataclass
class CallEvidence:
    run_id: str
    bridge_exit: int
    bridge_status: str | None
    selected_channel: str | None
    fallback_used: bool | None
    pool_run_count: int | None
    pool_pids: dict[str, int | None]
    relay_check_ok: bool
    v2_result_json: str
    agent2_output: str | None
    agent3_output: str | None
    relay_check_capture: str | None
    elapsed_s: float


@dataclass
class TwoCallResult:
    status: str
    base_run_id: str
    tenant_id: str
    pool_url: str | None
    initial_pids: dict[str, int | None] = field(default_factory=dict)
    after_first_pids: dict[str, int | None] = field(default_factory=dict)
    after_second_pids: dict[str, int | None] = field(default_factory=dict)
    pids_unchanged: bool = False
    both_relay_checks_pass: bool = False
    second_call_already_warm: bool = False
    initial_run_count: int | None = None
    after_first_run_count: int | None = None
    after_second_run_count: int | None = None
    initial_startup_count: int | None = None
    after_second_startup_count: int | None = None
    calls: list[CallEvidence] = field(default_factory=list)
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


def run_bridge_call(run_id: str, tenant_id: str, pool_url: str, timeout_s: int, out_dir: Path) -> tuple[int, float]:
    call_dir = out_dir / run_id
    call_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.run(
        [
            PYTHON,
            "rpc_bridge_v2.py",
            "--persistent-pool-url",
            pool_url,
            "--channel",
            "default",
            "--tenant-id",
            tenant_id,
            "--run-id",
            run_id,
            "--timeout",
            str(timeout_s),
            "--no-fallback-v1",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s + 120,
    )
    (call_dir / "rpc_bridge_v2.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (call_dir / "rpc_bridge_v2.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode, time.perf_counter() - started


def run_relay_check(agent2_output: str, agent3_output: str, out_dir: Path, run_id: str) -> tuple[bool, Path]:
    call_dir = out_dir / run_id
    call_dir.mkdir(parents=True, exist_ok=True)
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
    capture = call_dir / "relay-check.json"
    capture.write_text(proc.stdout, encoding="utf-8")
    if proc.stderr:
        (call_dir / "relay-check.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode == 0, capture


def collect_call_evidence(run_id: str, bridge_exit: int, elapsed_s: float, out_dir: Path) -> CallEvidence:
    v2_result_path = ROOT / "bridge-v2-runs" / run_id / "rpc-bridge-v2-result.json"
    if not v2_result_path.exists():
        raise RuntimeError(f"missing v2 result: {v2_result_path}")
    v2 = json.loads(v2_result_path.read_text(encoding="utf-8"))
    response = v2.get("response") if isinstance(v2.get("response"), dict) else {}
    agent2_output = response.get("agent2_output")
    agent3_output = response.get("agent3_output")
    relay_ok = False
    relay_capture: Path | None = None
    if isinstance(agent2_output, str) and isinstance(agent3_output, str):
        relay_ok, relay_capture = run_relay_check(agent2_output, agent3_output, out_dir, run_id)
    return CallEvidence(
        run_id=run_id,
        bridge_exit=bridge_exit,
        bridge_status=v2.get("status"),
        selected_channel=v2.get("selected_channel"),
        fallback_used=bool(v2.get("fallback_used")),
        pool_run_count=response.get("run_count"),
        pool_pids=response.get("pids") if isinstance(response.get("pids"), dict) else {},
        relay_check_ok=relay_ok,
        v2_result_json=str(v2_result_path),
        agent2_output=agent2_output if isinstance(agent2_output, str) else None,
        agent3_output=agent3_output if isinstance(agent3_output, str) else None,
        relay_check_capture=str(relay_capture) if relay_capture else None,
        elapsed_s=elapsed_s,
    )


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


def write_receipt(out_dir: Path, result: TwoCallResult) -> Path:
    (out_dir / "two-call-persistent-pool-smoke.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# Two-Call Persistent Pool Warm-State Smoke",
        "",
        f"Status: `{result.status}`",
        f"Base run ID: `{result.base_run_id}`",
        f"Tenant: `{result.tenant_id}`",
        f"Pool URL: `{result.pool_url}`",
        f"Initial PIDs: `{result.initial_pids}`",
        f"After first PIDs: `{result.after_first_pids}`",
        f"After second PIDs: `{result.after_second_pids}`",
        "",
        "## Acceptance",
        "",
        f"- PIDs unchanged: `{result.pids_unchanged}`",
        f"- both relay-checks pass: `{result.both_relay_checks_pass}`",
        f"- second call already warm: `{result.second_call_already_warm}`",
        f"- run_count progression: `{result.initial_run_count} -> {result.after_first_run_count} -> {result.after_second_run_count}`",
        f"- startup count stable: `{result.initial_startup_count} -> {result.after_second_startup_count}`",
        "",
        "## Calls",
        "",
    ]
    for call in result.calls:
        lines.extend(
            [
                f"### `{call.run_id}`",
                "",
                f"- bridge status: `{call.bridge_status}`",
                f"- selected channel: `{call.selected_channel}`",
                f"- fallback used: `{call.fallback_used}`",
                f"- pool run_count: `{call.pool_run_count}`",
                f"- relay-check ok: `{call.relay_check_ok}`",
                f"- elapsed: {call.elapsed_s:.2f}s",
                f"- v2 result: `{call.v2_result_json}`",
                f"- relay-check capture: `{call.relay_check_capture}`",
                "",
            ]
        )
    lines.append(f"Elapsed: {result.elapsed_s:.2f}s")
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])
    receipt = out_dir / "two-call-persistent-pool-smoke.md"
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Run two sequential v2 /relay calls through one persistent pool.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tenant-id", default="two-call-v2-persistent")
    parser.add_argument("--run-id", default="two-call-v2-persistent-" + time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--agent2-model", default="xai-oauth/grok-build-0.1")
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = ROOT / "diagnostics" / (time.strftime("%Y%m%d-%H%M%S") + "-two-call-persistent-pool")
    out_dir.mkdir(parents=True, exist_ok=True)
    pool_lines: queue.Queue[str] = queue.Queue()
    proc: subprocess.Popen[str] | None = None
    result = TwoCallResult(status="failed", base_run_id=args.run_id, tenant_id=args.tenant_id, pool_url=None)

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
        pool_url = str(ready["url"])
        result.pool_url = pool_url
        health0 = get_json(pool_url.rstrip("/") + "/health")
        (out_dir / "health-before.json").write_text(json.dumps(health0, indent=2), encoding="utf-8")
        result.initial_pids = health0.get("pids") or {}
        result.initial_run_count = health0.get("run_count")
        result.initial_startup_count = len(health0.get("startup") or [])

        run_id_1 = args.run_id + "-call1"
        exit1, elapsed1 = run_bridge_call(run_id_1, args.tenant_id, pool_url, args.timeout, out_dir)
        call1 = collect_call_evidence(run_id_1, exit1, elapsed1, out_dir)
        result.calls.append(call1)
        health1 = get_json(pool_url.rstrip("/") + "/health")
        (out_dir / "health-after-call1.json").write_text(json.dumps(health1, indent=2), encoding="utf-8")
        result.after_first_pids = health1.get("pids") or {}
        result.after_first_run_count = health1.get("run_count")

        run_id_2 = args.run_id + "-call2"
        exit2, elapsed2 = run_bridge_call(run_id_2, args.tenant_id, pool_url, args.timeout, out_dir)
        call2 = collect_call_evidence(run_id_2, exit2, elapsed2, out_dir)
        result.calls.append(call2)
        health2 = get_json(pool_url.rstrip("/") + "/health")
        (out_dir / "health-after-call2.json").write_text(json.dumps(health2, indent=2), encoding="utf-8")
        result.after_second_pids = health2.get("pids") or {}
        result.after_second_run_count = health2.get("run_count")
        result.after_second_startup_count = len(health2.get("startup") or [])

        result.pids_unchanged = result.initial_pids == result.after_first_pids == result.after_second_pids
        result.both_relay_checks_pass = len(result.calls) == 2 and all(call.relay_check_ok for call in result.calls)
        result.second_call_already_warm = (
            result.after_first_run_count == 1
            and result.after_second_run_count == 2
            and result.initial_startup_count == result.after_second_startup_count
            and result.pids_unchanged
            and call2.selected_channel == "default"
            and call2.fallback_used is False
        )
        if result.pids_unchanged and result.both_relay_checks_pass and result.second_call_already_warm:
            result.status = "passed"
        else:
            result.error = "two-call warm-state acceptance failed"
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
    print(f"two-call-persistent-pool-smoke: {result.status.upper()}")
    print(f"pids_unchanged={result.pids_unchanged}")
    print(f"both_relay_checks_pass={result.both_relay_checks_pass}")
    print(f"second_call_already_warm={result.second_call_already_warm}")
    print(f"receipt={receipt}")
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
