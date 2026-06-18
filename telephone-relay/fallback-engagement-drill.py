#!/usr/bin/env python3
"""Fallback-engagement drill for RPC Bridge v2.

Points the caller-facing default route wrapper at an unavailable persistent pool
URL through routing config environment while v1 fallback is enabled. The drill
passes only if v2 records persistent-route failure attempts, selects the v1
channel, and returns relay-check-passable v1 evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class FallbackDrillResult:
    status: str
    run_id: str
    tenant_id: str
    unavailable_url: str
    bridge_exit: int = -1
    bridge_status: str | None = None
    selected_channel: str | None = None
    fallback_used: bool | None = None
    attempts: int | None = None
    retries: int | None = None
    failures: int | None = None
    successes: int | None = None
    persistent_failures: int = 0
    v1_successes: int = 0
    v1_selected_mode: str | None = None
    v1_status: str | None = None
    relay_check_ok: bool = False
    v2_receipt: str | None = None
    v1_receipt: str | None = None
    agent2_output: str | None = None
    agent3_output: str | None = None
    relay_check_capture: str | None = None
    elapsed_s: float = 0.0
    error: str | None = None
    attempt_summary: list[dict[str, Any]] = field(default_factory=list)


def run_v2(run_id: str, tenant_id: str, unavailable_url: str, timeout_s: int, max_attempts: int, out_dir: Path) -> int:
    command = [
        PYTHON,
        "caller-default-route.py",
        "--tenant-id",
        tenant_id,
        "--run-id",
        run_id,
        "--timeout",
        str(timeout_s),
        "--max-attempts",
        str(max_attempts),
        "--initial-backoff-s",
        "0.05",
    ]
    (out_dir / "caller-command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["TELEPHONE_RELAY_PERSISTENT_POOL_URL"] = unavailable_url
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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"missing JSON artifact: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"expected object JSON artifact: {path}")
    return data


def parse_rpc_outputs(stdout_path: str | None) -> tuple[str | None, str | None]:
    if not stdout_path:
        return None, None
    path = Path(stdout_path)
    if not path.exists():
        return None, None
    agent2 = None
    agent3 = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("agent2_output="):
            agent2 = line.split("=", 1)[1].strip()
        elif line.startswith("agent3_output="):
            agent3 = line.split("=", 1)[1].strip()
    return agent2, agent3


def find_v1_outputs(v1: dict[str, Any]) -> tuple[str | None, str | None, str]:
    selected_mode = v1.get("selected_mode")
    commands = v1.get("commands") if isinstance(v1.get("commands"), list) else []
    if selected_mode == "rpc":
        for command in commands:
            if isinstance(command, dict) and command.get("name") == "rpc-warm-pool":
                agent2, agent3 = parse_rpc_outputs(command.get("stdout_path"))
                return agent2, agent3, "rpc relay outputs parsed from rpc-warm-pool stdout"
    if selected_mode == "direct":
        return None, None, "direct relay selected; use baseline relay-check"
    return None, None, f"unknown v1 selected_mode={selected_mode!r}"


def run_relay_check(out_dir: Path, agent2_output: str | None, agent3_output: str | None) -> tuple[bool, Path]:
    command = [PYTHON, "relay-check.py"]
    if agent2_output and agent3_output:
        command.extend(
            [
                "--agent2-output",
                agent2_output,
                "--agent3-output",
                agent3_output,
                "--skip-exit-files",
                "--skip-session-id-check",
                "--json",
            ]
        )
    else:
        command.append("--json")
    proc = subprocess.run(
        command,
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


def summarize_attempts(v2: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    stats = v2.get("stats") if isinstance(v2.get("stats"), dict) else {}
    details = stats.get("attempts_detail") if isinstance(stats.get("attempts_detail"), list) else []
    summary: list[dict[str, Any]] = []
    persistent_failures = 0
    v1_successes = 0
    for item in details:
        if not isinstance(item, dict):
            continue
        row = {
            "channel": item.get("channel"),
            "kind": item.get("kind"),
            "attempt": item.get("attempt"),
            "status": item.get("status"),
            "error": item.get("error"),
        }
        summary.append(row)
        if item.get("kind") == "persistent" and item.get("status") != "passed":
            persistent_failures += 1
        if item.get("kind") == "v1" and item.get("status") == "passed":
            v1_successes += 1
    return summary, persistent_failures, v1_successes


def write_receipt(out_dir: Path, result: FallbackDrillResult) -> Path:
    (out_dir / "fallback-engagement-drill.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# Fallback-Engagement Drill",
        "",
        f"Status: `{result.status}`",
        f"Run ID: `{result.run_id}`",
        f"Tenant: `{result.tenant_id}`",
        f"Unavailable persistent URL: `{result.unavailable_url}`",
        f"Elapsed: {result.elapsed_s:.2f}s",
        "",
        "## Bridge v2",
        "",
        f"- bridge exit: `{result.bridge_exit}`",
        f"- bridge status: `{result.bridge_status}`",
        f"- selected channel: `{result.selected_channel}`",
        f"- fallback used: `{result.fallback_used}`",
        f"- attempts/retries: `{result.attempts}` / `{result.retries}`",
        f"- failures/successes: `{result.failures}` / `{result.successes}`",
        f"- persistent failures: `{result.persistent_failures}`",
        f"- v1 successes: `{result.v1_successes}`",
        "",
        "## v1 evidence",
        "",
        f"- v1 status: `{result.v1_status}`",
        f"- v1 selected mode: `{result.v1_selected_mode}`",
        f"- relay-check ok: `{result.relay_check_ok}`",
        f"- v2 receipt: `{result.v2_receipt}`",
        f"- v1 receipt: `{result.v1_receipt}`",
        f"- agent2 output: `{result.agent2_output}`",
        f"- agent3 output: `{result.agent3_output}`",
        f"- relay-check capture: `{result.relay_check_capture}`",
        "",
        "## Attempts",
        "",
    ]
    for attempt in result.attempt_summary:
        lines.append(
            f"- {attempt.get('channel')}/{attempt.get('kind')} attempt {attempt.get('attempt')}: "
            f"{attempt.get('status')}"
        )
        if attempt.get("error"):
            lines.append(f"  - error: `{attempt.get('error')}`")
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])
    receipt = out_dir / "fallback-engagement-drill.md"
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove v2 engages v1 fallback when persistent URL is unavailable.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tenant-id", default="fallback-engagement-drill")
    parser.add_argument("--run-id", default="fallback-engagement-drill-" + time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--unavailable-url", default="http://127.0.0.1:1")
    parser.add_argument("--max-attempts", type=int, default=2)
    args = parser.parse_args()
    if not SAFE_RUN_ID_RE.fullmatch(args.run_id):
        parser.error("--run-id may only contain letters, numbers, hyphens, and underscores")

    started = time.perf_counter()
    out_dir = ROOT / "diagnostics" / (time.strftime("%Y%m%d-%H%M%S") + "-fallback-engagement-drill")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = FallbackDrillResult(
        status="failed",
        run_id=args.run_id,
        tenant_id=args.tenant_id,
        unavailable_url=args.unavailable_url,
    )

    try:
        result.bridge_exit = run_v2(args.run_id, args.tenant_id, args.unavailable_url, args.timeout, args.max_attempts, out_dir)
        v2_path = ROOT / "bridge-v2-runs" / args.run_id / "rpc-bridge-v2-result.json"
        v2 = read_json(v2_path)
        result.v2_receipt = str(v2_path)
        result.bridge_status = v2.get("status")
        result.selected_channel = v2.get("selected_channel")
        if "fallback_used" not in v2:
            raise RuntimeError("v2 receipt missing 'fallback_used' field")
        result.fallback_used = bool(v2["fallback_used"])
        stats = v2.get("stats") if isinstance(v2.get("stats"), dict) else {}
        result.attempts = stats.get("attempts")
        result.retries = stats.get("retries")
        result.failures = stats.get("failures")
        result.successes = stats.get("successes")
        result.attempt_summary, result.persistent_failures, result.v1_successes = summarize_attempts(v2)

        v1_path = ROOT / "bridge-runs" / args.run_id / "bridge-result.json"
        v1 = read_json(v1_path)
        result.v1_receipt = str(v1_path)
        result.v1_status = v1.get("status")
        result.v1_selected_mode = v1.get("selected_mode")
        result.agent2_output, result.agent3_output, _ = find_v1_outputs(v1)

        result.relay_check_ok, capture = run_relay_check(out_dir, result.agent2_output, result.agent3_output)
        result.relay_check_capture = str(capture)

        if result.bridge_exit != 0:
            raise RuntimeError(f"v2 caller exited {result.bridge_exit}")
        if result.bridge_status != "passed":
            raise RuntimeError(f"v2 status not passed: {result.bridge_status}")
        if result.selected_channel != "v1":
            raise RuntimeError(f"expected selected_channel='v1', got {result.selected_channel!r}")
        if result.fallback_used is not True:
            raise RuntimeError(f"expected fallback_used=True, got {result.fallback_used!r}")
        if result.persistent_failures < 1:
            raise RuntimeError("expected at least one persistent-route failure attempt")
        if result.v1_successes < 1:
            raise RuntimeError("expected at least one successful v1 attempt")
        if result.v1_status != "passed":
            raise RuntimeError(f"v1 bridge result not passed: {result.v1_status}")
        if result.v1_selected_mode not in {"rpc", "direct"}:
            raise RuntimeError(f"unexpected v1 selected mode: {result.v1_selected_mode!r}")
        if not result.relay_check_ok:
            raise RuntimeError("relay-check failed for v1 fallback evidence")

        result.status = "passed"
    except Exception as exc:
        result.error = str(exc)
    finally:
        result.elapsed_s = time.perf_counter() - started

    receipt = write_receipt(out_dir, result)
    print(f"fallback-engagement-drill: {result.status.upper()}")
    print(f"selected_channel={result.selected_channel} fallback_used={result.fallback_used}")
    print(f"persistent_failures={result.persistent_failures} v1_successes={result.v1_successes}")
    print(f"relay_check_ok={result.relay_check_ok}")
    print(f"receipt={receipt}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
