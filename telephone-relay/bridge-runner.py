#!/usr/bin/env python3
"""Telephone Relay bridge runner.

Bounded integration wrapper:
- tries the working RPC warm-pool prototype first;
- verifies RPC evidence with relay-check;
- falls back to the proven direct relay if RPC fails;
- records cold/warm timing evidence and receipts.

This does not replace rpc-warm-pool-prototype.py or the direct relay profiles.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent
HANDOFF = ROOT / "handoff.md"
RESET_HANDOFF = "# Telephone Relay Handoff\n\nCurrent token:\n\nHistory:\n"
PYTHON = sys.executable
PI_CMD = shutil.which("pi.cmd") or shutil.which("pi") or "pi"

Mode = Literal["persistent", "rpc", "direct"]
Status = Literal["passed", "failed", "skipped"]


@dataclass
class CommandEvidence:
    name: str
    command: list[str]
    started_at: str
    ended_at: str
    elapsed_s: float
    exit_code: int
    stdout_path: str
    stderr_path: str


@dataclass
class BridgeResult:
    run_id: str
    status: Status
    selected_mode: Mode | None
    attempted_modes: list[Mode]
    cold_start_at: str
    completed_at: str
    total_elapsed_s: float
    rpc_state: str
    direct_state: str
    before_handoff_token: str
    after_handoff_token: str
    commands: list[CommandEvidence] = field(default_factory=list)
    verifier_commands: list[CommandEvidence] = field(default_factory=list)
    fallback_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_token() -> str:
    if not HANDOFF.exists():
        return "<missing>"
    for line in HANDOFF.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("Current token:"):
            return line.split(":", 1)[1].strip() or "<blank>"
    return "<missing>"


def reset_handoff() -> None:
    HANDOFF.write_text(RESET_HANDOFF, encoding="utf-8")


def run_command(name: str, command: list[str], run_dir: Path, timeout_s: int) -> CommandEvidence:
    started = time.perf_counter()
    started_at = now_iso()
    stdout_path = run_dir / f"{name}.stdout.txt"
    stderr_path = run_dir / f"{name}.stderr.txt"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    elapsed = time.perf_counter() - started
    return CommandEvidence(
        name=name,
        command=command,
        started_at=started_at,
        ended_at=now_iso(),
        elapsed_s=elapsed,
        exit_code=proc.returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def parse_rpc_outputs(stdout: str) -> tuple[str | None, str | None, str | None]:
    agent2 = None
    agent3 = None
    receipt = None
    for line in stdout.splitlines():
        if line.startswith("agent2_output="):
            agent2 = line.split("=", 1)[1].strip()
        elif line.startswith("agent3_output="):
            agent3 = line.split("=", 1)[1].strip()
        elif line.startswith("receipt="):
            receipt = line.split("=", 1)[1].strip()
    return agent2, agent3, receipt


def run_relay_check_for_rpc(run_dir: Path, agent2_output: str, agent3_output: str, timeout_s: int) -> CommandEvidence:
    return run_command(
        "relay-check-rpc",
        [
            PYTHON,
            "relay-check.py",
            "--agent2-output",
            agent2_output,
            "--agent3-output",
            agent3_output,
            "--skip-exit-files",
            "--skip-session-id-check",
        ],
        run_dir,
        timeout_s,
    )


def run_relay_check_direct(run_dir: Path, timeout_s: int) -> CommandEvidence:
    return run_command("relay-check-direct", [PYTHON, "relay-check.py"], run_dir, timeout_s)


def run_rpc_path(run_dir: Path, timeout_s: int) -> tuple[CommandEvidence, CommandEvidence | None, str | None]:
    reset_handoff()
    command = [PYTHON, "rpc-warm-pool-prototype.py", "--timeout", str(timeout_s)]
    evidence = run_command("rpc-warm-pool", command, run_dir, timeout_s + 90)
    stdout = read_file(evidence.stdout_path)
    agent2_output, agent3_output, receipt = parse_rpc_outputs(stdout)
    verifier = None
    if evidence.exit_code == 0 and agent2_output and agent3_output:
        verifier = run_relay_check_for_rpc(run_dir, agent2_output, agent3_output, timeout_s=60)
    return evidence, verifier, receipt


def run_persistent_path(run_dir: Path, url: str, timeout_s: int) -> tuple[CommandEvidence, CommandEvidence | None, dict[str, object]]:
    started = time.perf_counter()
    started_at = now_iso()
    stdout_path = run_dir / "persistent-pool.stdout.txt"
    stderr_path = run_dir / "persistent-pool.stderr.txt"
    command = ["POST", f"{url.rstrip('/')}/relay"]
    payload = json.dumps({"run_id": run_dir.name}).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/relay",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    exit_code = 1
    data: dict[str, object] = {}
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read().decode("utf-8")
        stdout_path.write_text(body, encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        data = json.loads(body)
        exit_code = 0 if data.get("status") == "passed" else 1
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        stdout_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        stderr_path.write_text(str(exc), encoding="utf-8")
    elapsed = time.perf_counter() - started
    evidence = CommandEvidence(
        name="persistent-pool",
        command=command,
        started_at=started_at,
        ended_at=now_iso(),
        elapsed_s=elapsed,
        exit_code=exit_code,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )
    verifier = None
    agent2_output = data.get("agent2_output")
    agent3_output = data.get("agent3_output")
    if exit_code == 0 and isinstance(agent2_output, str) and isinstance(agent3_output, str):
        verifier = run_relay_check_for_rpc(run_dir, agent2_output, agent3_output, timeout_s=60)
    return evidence, verifier, data


def run_direct_path(run_dir: Path, timeout_s: int) -> tuple[CommandEvidence, CommandEvidence]:
    reset_handoff()
    run_id = time.strftime("%Y%m%d%H%M%S")
    command = [
        PI_CMD,
        "-p",
        "--approve",
        "--mode",
        "text",
        "--no-extensions",
        "--no-skills",
        "--tools",
        "read,bash,edit,write",
        "--session-id",
        f"telephone-relay-agent-1-bridge-{run_id}",
        "--session-dir",
        "./sessions/agent-1",
        "--name",
        f"telephone-relay-agent-1-bridge-{run_id}",
        "--model",
        "minimax-oauth/MiniMax-M3",
        "--append-system-prompt",
        "./system-live.md",
        "--append-system-prompt",
        "./profiles/agent-1.md",
        "g",
    ]
    evidence = run_command("direct-relay", command, run_dir, timeout_s)
    verifier = run_relay_check_direct(run_dir, timeout_s=60)
    return evidence, verifier


def write_result(run_dir: Path, result: BridgeResult) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "bridge-result.json").write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Telephone Relay Bridge Runner Receipt",
        "",
        f"Run ID: `{result.run_id}`",
        f"Status: `{result.status}`",
        f"Selected mode: `{result.selected_mode}`",
        "",
        "## Timing",
        "",
        f"- cold start at: `{result.cold_start_at}`",
        f"- completed at: `{result.completed_at}`",
        f"- total elapsed: {result.total_elapsed_s:.2f}s",
        f"- before handoff token: `{result.before_handoff_token}`",
        f"- after handoff token: `{result.after_handoff_token}`",
        "",
        "## Cold/warm state",
        "",
        f"- RPC state: {result.rpc_state}",
        f"- Direct state: {result.direct_state}",
        "",
        "## Commands",
        "",
    ]
    for command in result.commands:
        lines.append(f"- {command.name}: exit {command.exit_code}, {command.elapsed_s:.2f}s")
        lines.append(f"  - stdout: `{command.stdout_path}`")
        lines.append(f"  - stderr: `{command.stderr_path}`")
    lines.extend(["", "## Verifiers", ""])
    for command in result.verifier_commands:
        lines.append(f"- {command.name}: exit {command.exit_code}, {command.elapsed_s:.2f}s")
        lines.append(f"  - stdout: `{command.stdout_path}`")
        lines.append(f"  - stderr: `{command.stderr_path}`")
    if result.fallback_reason:
        lines.extend(["", "## Fallback reason", "", result.fallback_reason])
    if result.notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in result.notes)
    (run_dir / "bridge-result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Telephone Relay through RPC warm-pool with direct fallback.")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout for each relay mode in seconds")
    parser.add_argument("--force-direct", action="store_true", help="Skip RPC and run the direct fallback path")
    parser.add_argument("--persistent-pool-url", help="Use an already-started single-tenant persistent warm pool first")
    parser.add_argument("--run-id", help="Optional run id")
    args = parser.parse_args()

    run_id = args.run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "bridge-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    cold_start_at = now_iso()
    before_token = current_token()
    attempted: list[Mode] = []
    commands: list[CommandEvidence] = []
    verifiers: list[CommandEvidence] = []
    selected_mode: Mode | None = None
    fallback_reason: str | None = None
    notes: list[str] = []

    rpc_state = "skipped by --force-direct" if args.force_direct else "cold start requested; warm after RPC processes report get_state"
    if args.persistent_pool_url:
        rpc_state = f"persistent pool requested at {args.persistent_pool_url}; agents should already be warm"
    direct_state = "cold fallback available; starts fresh pi -p Agent 1 if needed"

    try:
        if args.persistent_pool_url and not args.force_direct:
            attempted.append("persistent")
            persistent_evidence, persistent_verifier, persistent_data = run_persistent_path(
                run_dir, args.persistent_pool_url, args.timeout
            )
            commands.append(persistent_evidence)
            if persistent_verifier:
                verifiers.append(persistent_verifier)
            notes.append(f"Persistent pool response: run_count={persistent_data.get('run_count')}; pids={persistent_data.get('pids')}")
            if persistent_evidence.exit_code == 0 and persistent_verifier and persistent_verifier.exit_code == 0:
                selected_mode = "persistent"
            else:
                fallback_reason = (
                    f"Persistent pool failed or verifier did not pass: pool_exit={persistent_evidence.exit_code}, "
                    f"verifier_exit={persistent_verifier.exit_code if persistent_verifier else 'missing'}"
                )

        if not args.force_direct and selected_mode is None and not args.persistent_pool_url:
            attempted.append("rpc")
            rpc_evidence, rpc_verifier, rpc_receipt = run_rpc_path(run_dir, args.timeout)
            commands.append(rpc_evidence)
            if rpc_verifier:
                verifiers.append(rpc_verifier)
            if rpc_receipt:
                notes.append(f"RPC prototype receipt: {rpc_receipt}")
            if rpc_evidence.exit_code == 0 and rpc_verifier and rpc_verifier.exit_code == 0:
                selected_mode = "rpc"
            else:
                fallback_reason = (
                    f"RPC path failed or verifier did not pass: rpc_exit={rpc_evidence.exit_code}, "
                    f"verifier_exit={rpc_verifier.exit_code if rpc_verifier else 'missing'}"
                )

        if selected_mode is None:
            attempted.append("direct")
            direct_evidence, direct_verifier = run_direct_path(run_dir, args.timeout)
            commands.append(direct_evidence)
            verifiers.append(direct_verifier)
            if direct_evidence.exit_code == 0 and direct_verifier.exit_code == 0:
                selected_mode = "direct"
            else:
                raise RuntimeError(
                    f"Direct fallback failed: direct_exit={direct_evidence.exit_code}, verifier_exit={direct_verifier.exit_code}"
                )

        status: Status = "passed"
    except Exception as exc:
        status = "failed"
        notes.append(f"Error: {exc}")

    completed_at = now_iso()
    result = BridgeResult(
        run_id=run_id,
        status=status,
        selected_mode=selected_mode,
        attempted_modes=attempted,
        cold_start_at=cold_start_at,
        completed_at=completed_at,
        total_elapsed_s=time.perf_counter() - started,
        rpc_state=rpc_state,
        direct_state=direct_state,
        before_handoff_token=before_token,
        after_handoff_token=current_token(),
        commands=commands,
        verifier_commands=verifiers,
        fallback_reason=fallback_reason,
        notes=notes,
    )
    write_result(run_dir, result)
    print(f"bridge-runner: {status.upper()} mode={selected_mode} run_id={run_id}")
    print(f"receipt={run_dir / 'bridge-result.md'}")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
