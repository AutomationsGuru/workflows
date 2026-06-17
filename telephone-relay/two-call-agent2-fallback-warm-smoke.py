#!/usr/bin/env python3
"""Two-call persistent warm-state smoke after Agent 2 fallback activation.

Starts one persistent pool with the primary Agent 2 model, drives two sequential
caller-default route calls, and proves:

1. call 1 activates the persistent pool's Agent 2 fallback model;
2. both calls still complete through the persistent default route without v1
   bridge fallback;
3. call 2 reuses the already-warm fallback-model pool with stable PIDs.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
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
SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class CallEvidence:
    run_id: str
    bridge_exit: int
    bridge_status: str | None
    selected_channel: str | None
    fallback_used: bool | None
    pool_run_count: int | None
    agent2_model: str | None
    pool_pids: dict[str, int | None]
    fallback_events: list[str]
    relay_check_ok: bool
    v2_result_json: str
    agent2_output: str | None
    agent3_output: str | None
    relay_check_capture: str | None
    elapsed_s: float


@dataclass
class FallbackWarmStateResult:
    status: str
    base_run_id: str
    tenant_id: str
    pool_url: str | None = None
    initial_pids: dict[str, int | None] = field(default_factory=dict)
    after_first_pids: dict[str, int | None] = field(default_factory=dict)
    after_second_pids: dict[str, int | None] = field(default_factory=dict)
    initial_agent2_model: str | None = None
    after_first_agent2_model: str | None = None
    after_second_agent2_model: str | None = None
    initial_run_count: int | None = None
    after_first_run_count: int | None = None
    after_second_run_count: int | None = None
    fallback_activated: bool = False
    fallback_pids_stable_on_second: bool = False
    both_relay_checks_pass: bool = False
    second_call_already_warm: bool = False
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


def run_caller_default(run_id: str, tenant_id: str, pool_url: str, timeout_s: int, out_dir: Path) -> tuple[int, float]:
    call_dir = out_dir / run_id
    call_dir.mkdir(parents=True, exist_ok=True)
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
    (call_dir / "caller-command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["TELEPHONE_RELAY_PERSISTENT_POOL_URL"] = pool_url
    started = time.perf_counter()
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
    (call_dir / "caller-default-route.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (call_dir / "caller-default-route.stderr.txt").write_text(proc.stderr, encoding="utf-8")
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
        agent2_model=response.get("agent2_model") if isinstance(response.get("agent2_model"), str) else None,
        pool_pids=response.get("pids") if isinstance(response.get("pids"), dict) else {},
        fallback_events=list(response.get("fallback_events") or []),
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


def write_receipt(out_dir: Path, result: FallbackWarmStateResult) -> Path:
    (out_dir / "two-call-agent2-fallback-warm-smoke.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# Two-Call Agent 2 Fallback Warm-State Smoke",
        "",
        f"Status: `{result.status}`",
        f"Base run ID: `{result.base_run_id}`",
        f"Tenant: `{result.tenant_id}`",
        f"Pool URL: `{result.pool_url}`",
        f"Initial Agent 2 model: `{result.initial_agent2_model}`",
        f"After first Agent 2 model: `{result.after_first_agent2_model}`",
        f"After second Agent 2 model: `{result.after_second_agent2_model}`",
        "",
        "## Acceptance",
        "",
        f"- fallback activated on first call: `{result.fallback_activated}`",
        f"- fallback PIDs stable on second call: `{result.fallback_pids_stable_on_second}`",
        f"- both relay-checks pass: `{result.both_relay_checks_pass}`",
        f"- second call already warm: `{result.second_call_already_warm}`",
        f"- run_count progression: `{result.initial_run_count} -> {result.after_first_run_count} -> {result.after_second_run_count}`",
        f"- initial PIDs: `{result.initial_pids}`",
        f"- after first PIDs: `{result.after_first_pids}`",
        f"- after second PIDs: `{result.after_second_pids}`",
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
                f"- v1 fallback used: `{call.fallback_used}`",
                f"- pool run_count: `{call.pool_run_count}`",
                f"- Agent 2 model: `{call.agent2_model}`",
                f"- pool PIDs: `{call.pool_pids}`",
                f"- fallback events: `{call.fallback_events}`",
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
    receipt = out_dir / "two-call-agent2-fallback-warm-smoke.md"
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove Agent 2 fallback pool stays warm across the second call.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tenant-id", default="two-call-agent2-fallback")
    parser.add_argument("--run-id", default="two-call-agent2-fallback-" + time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--agent2-model", default="xai-oauth/grok-build-0.1")
    parser.add_argument("--agent2-fallback-model", default="openai-codex/gpt-5.5")
    args = parser.parse_args()

    if not SAFE_RUN_ID_RE.fullmatch(args.run_id):
        parser.error("--run-id may only contain letters, numbers, hyphens, and underscores")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    started = time.perf_counter()
    out_dir = ROOT / "diagnostics" / (time.strftime("%Y%m%d-%H%M%S") + "-two-call-agent2-fallback-warm")
    out_dir.mkdir(parents=True, exist_ok=True)
    pool_lines: queue.Queue[str] = queue.Queue()
    proc: subprocess.Popen[str] | None = None
    result = FallbackWarmStateResult(status="failed", base_run_id=args.run_id, tenant_id=args.tenant_id)

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
                "--agent2-fallback-model",
                args.agent2_fallback_model,
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
        result.initial_agent2_model = health0.get("agent2_model")
        result.initial_run_count = health0.get("run_count")

        run_id_1 = args.run_id + "-call1"
        exit1, elapsed1 = run_caller_default(run_id_1, args.tenant_id, pool_url, args.timeout, out_dir)
        call1 = collect_call_evidence(run_id_1, exit1, elapsed1, out_dir)
        result.calls.append(call1)
        health1 = get_json(pool_url.rstrip("/") + "/health")
        (out_dir / "health-after-call1.json").write_text(json.dumps(health1, indent=2), encoding="utf-8")
        result.after_first_pids = health1.get("pids") or {}
        result.after_first_agent2_model = health1.get("agent2_model")
        result.after_first_run_count = health1.get("run_count")

        run_id_2 = args.run_id + "-call2"
        exit2, elapsed2 = run_caller_default(run_id_2, args.tenant_id, pool_url, args.timeout, out_dir)
        call2 = collect_call_evidence(run_id_2, exit2, elapsed2, out_dir)
        result.calls.append(call2)
        health2 = get_json(pool_url.rstrip("/") + "/health")
        (out_dir / "health-after-call2.json").write_text(json.dumps(health2, indent=2), encoding="utf-8")
        result.after_second_pids = health2.get("pids") or {}
        result.after_second_agent2_model = health2.get("agent2_model")
        result.after_second_run_count = health2.get("run_count")

        fallback_events_1 = list(health1.get("fallback_events") or [])
        fallback_events_2 = list(health2.get("fallback_events") or [])
        result.fallback_activated = (
            result.initial_agent2_model == args.agent2_model
            and result.after_first_agent2_model == args.agent2_fallback_model
            and result.initial_pids != result.after_first_pids
            and len(fallback_events_1) >= 1
        )
        result.fallback_pids_stable_on_second = result.after_first_pids == result.after_second_pids
        result.both_relay_checks_pass = len(result.calls) == 2 and all(call.relay_check_ok for call in result.calls)
        result.second_call_already_warm = (
            result.fallback_activated
            and result.fallback_pids_stable_on_second
            and result.after_first_run_count == 1
            and result.after_second_run_count == 2
            and result.after_second_agent2_model == args.agent2_fallback_model
            and fallback_events_1 == fallback_events_2
            and call1.bridge_exit == 0
            and call2.bridge_exit == 0
            and call1.selected_channel == "default"
            and call2.selected_channel == "default"
            and call1.fallback_used is False
            and call2.fallback_used is False
            and call2.pool_pids == result.after_second_pids
        )
        if result.fallback_activated and result.second_call_already_warm and result.both_relay_checks_pass:
            result.status = "passed"
        else:
            result.error = "two-call Agent 2 fallback warm-state acceptance failed"
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
    print(f"two-call-agent2-fallback-warm-smoke: {result.status.upper()}")
    print(f"fallback_activated={result.fallback_activated}")
    print(f"fallback_pids_stable_on_second={result.fallback_pids_stable_on_second}")
    print(f"both_relay_checks_pass={result.both_relay_checks_pass}")
    print(f"second_call_already_warm={result.second_call_already_warm}")
    print(f"receipt={receipt}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
