#!/usr/bin/env python3
"""Tiny RPC warm-pool latency diagnostic.

Measures observable bootstrap and prompt timings for one warm-pool-style Pi RPC
agent without changing the relay benchmark or warm-pool prototype.
"""

from __future__ import annotations

import argparse
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
HANDOFF = ROOT / "handoff.md"
RESET_HANDOFF = "# Telephone Relay Handoff\n\nCurrent token:\n\nHistory:\n"
PI_CMD = shutil.which("pi.cmd") or shutil.which("pi") or "pi"


@dataclass
class LatencyBreakdown:
    env_prep_s: float
    sdk_build_s: float
    connection_s: float
    prompt_s: float
    first_byte_after_launch_s: float | None
    total_s: float


@dataclass
class DiagnosticResult:
    run_id: str
    status: str
    cold_state: str
    warm_state: str
    model: str
    profile: str
    prompt: str
    expected: str
    started_at: str
    warm_ready_at: str | None
    completed_at: str
    breakdown: LatencyBreakdown
    assistant_text: str
    command: list[str]
    error: str | None = None


class RpcProbe:
    def __init__(self, command: list[str], timeout_s: int) -> None:
        self.command_line = command
        self.timeout_s = timeout_s
        self.proc: subprocess.Popen[str] | None = None
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.stderr_lines: queue.Queue[str] = queue.Queue()
        self.first_byte_at: float | None = None
        self._threads: list[threading.Thread] = []

    def launch(self) -> float:
        started = time.perf_counter()
        self.proc = subprocess.Popen(
            self.command_line,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        spawn_s = time.perf_counter() - started
        self._start_readers()
        return spawn_s

    def _mark_first_byte(self) -> None:
        if self.first_byte_at is None:
            self.first_byte_at = time.perf_counter()

    def _start_readers(self) -> None:
        assert self.proc and self.proc.stdout and self.proc.stderr

        def stdout_reader() -> None:
            assert self.proc and self.proc.stdout
            for line in self.proc.stdout:
                self._mark_first_byte()
                line = line.rstrip("\r\n")
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "raw", "line": line}
                self.events.put(event)

        def stderr_reader() -> None:
            assert self.proc and self.proc.stderr
            for line in self.proc.stderr:
                self._mark_first_byte()
                self.stderr_lines.put(line.rstrip("\r\n"))

        for target in (stdout_reader, stderr_reader):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def send(self, command: dict[str, Any]) -> str:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("RPC process is not running")
        request_id = command.get("id") or f"diag-{uuid.uuid4().hex}"
        payload = {**command, "id": request_id}
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return str(request_id)

    def wait_for(self, predicate, timeout_s: int) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=0.2)
            except queue.Empty:
                if self.proc and self.proc.poll() is not None:
                    continue
                continue
            if predicate(event):
                return event
        return None

    def request(self, command: dict[str, Any], timeout_s: int) -> dict[str, Any]:
        request_id = self.send(command)
        response = self.wait_for(
            lambda event: event.get("type") == "response" and event.get("id") == request_id,
            timeout_s,
        )
        if response is None:
            raise RuntimeError(f"timed out waiting for {command.get('type')} response")
        return response

    def stop(self) -> None:
        if not self.proc:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_command(name: str, model: str, profile: Path) -> list[str]:
    return [
        PI_CMD,
        "--approve",
        "--mode",
        "rpc",
        "--no-extensions",
        "--no-skills",
        "--no-context-files",
        "--tools",
        "read,bash,edit,write",
        "--no-session",
        "--name",
        name,
        "--model",
        model,
        "--append-system-prompt",
        str(ROOT / "system-rpc.md"),
        "--append-system-prompt",
        str(profile),
    ]


def write_receipt(run_dir: Path, result: DiagnosticResult) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "latency-diagnostic.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    b = result.breakdown
    lines = [
        "# RPC Latency Diagnostic Receipt",
        "",
        f"Run ID: `{result.run_id}`",
        f"Status: `{result.status}`",
        f"Model: `{result.model}`",
        f"Profile: `{result.profile}`",
        "",
        "## State",
        "",
        f"- cold: {result.cold_state}",
        f"- warm: {result.warm_state}",
        f"- started: `{result.started_at}`",
        f"- warm ready: `{result.warm_ready_at}`",
        f"- completed: `{result.completed_at}`",
        "",
        "## Timing breakdown",
        "",
        f"- env prep: {b.env_prep_s:.3f}s",
        f"- SDK/process spawn: {b.sdk_build_s:.3f}s",
        f"- connection/get_state: {b.connection_s:.3f}s",
        f"- first byte after launch: {b.first_byte_after_launch_s:.3f}s" if b.first_byte_after_launch_s is not None else "- first byte after launch: <none>",
        f"- prompt round trip: {b.prompt_s:.3f}s",
        f"- total: {b.total_s:.3f}s",
        "",
        "## Assistant text",
        "",
        "```text",
        result.assistant_text,
        "```",
    ]
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])
    (run_dir / "latency-diagnostic.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a tiny RPC warm-pool latency diagnostic.")
    parser.add_argument("--timeout", type=int, default=120, help="Per-step timeout in seconds")
    parser.add_argument("--name", default="telephone-relay-agent-1-rpc-diagnostic", help="Pi agent name")
    parser.add_argument("--model", default="minimax-oauth/MiniMax-M3", help="Model to probe")
    parser.add_argument("--profile", type=Path, default=ROOT / "profiles/agent-1-rpc.md", help="Warm-pool profile to probe")
    parser.add_argument("--prompt", default="g", help="Prompt to send after warm readiness")
    parser.add_argument("--expected", default="NEXT:Agent 2:g", help="Expected substring in assistant text")
    parser.add_argument("--run-id", help="Optional diagnostic run id")
    parser.add_argument("--no-restore-handoff", action="store_true", help="Do not restore handoff.md after the prompt probe")
    args = parser.parse_args()

    run_id = args.run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "diagnostics" / run_id
    total_started = time.perf_counter()
    started_at = now_iso()
    warm_ready_at: str | None = None
    assistant_text = ""
    error: str | None = None
    status = "failed"
    original_handoff = HANDOFF.read_text(encoding="utf-8") if HANDOFF.exists() else ""

    env_started = time.perf_counter()
    profile = args.profile if args.profile.is_absolute() else (ROOT / args.profile)
    command = build_command(args.name, args.model, profile)
    run_dir.mkdir(parents=True, exist_ok=True)
    env_prep_s = time.perf_counter() - env_started

    probe = RpcProbe(command, args.timeout)
    sdk_build_s = 0.0
    connection_s = 0.0
    prompt_s = 0.0
    launch_started_at_perf: float | None = None

    try:
        HANDOFF.write_text(RESET_HANDOFF, encoding="utf-8")
        cold_state = "cold: no diagnostic RPC process before launch"
        launch_started_at_perf = time.perf_counter()
        sdk_build_s = probe.launch()

        connection_started = time.perf_counter()
        state = probe.request({"type": "get_state"}, timeout_s=args.timeout)
        connection_s = time.perf_counter() - connection_started
        if not state.get("success"):
            raise RuntimeError(f"get_state failed: {state}")
        warm_ready_at = now_iso()
        warm_state = "warm: get_state succeeded; process is ready for prompt"

        prompt_started = time.perf_counter()
        prompt_response = probe.request({"type": "prompt", "message": args.prompt}, timeout_s=args.timeout)
        if not prompt_response.get("success"):
            raise RuntimeError(f"prompt rejected: {prompt_response}")
        agent_end = probe.wait_for(lambda event: event.get("type") == "agent_end", timeout_s=args.timeout)
        if agent_end is None:
            raise RuntimeError("timed out waiting for agent_end")
        text_response = probe.request({"type": "get_last_assistant_text"}, timeout_s=args.timeout)
        assistant_text = (text_response.get("data") or {}).get("text") or ""
        prompt_s = time.perf_counter() - prompt_started
        if args.expected and args.expected not in assistant_text:
            raise RuntimeError(f"expected {args.expected!r} not found in assistant text {assistant_text!r}")
        status = "passed"
    except Exception as exc:
        cold_state = "cold: no diagnostic RPC process before launch"
        warm_state = "failed before warm readiness" if warm_ready_at is None else "warm before failure"
        error = str(exc)
    finally:
        probe.stop()
        if not args.no_restore_handoff:
            HANDOFF.write_text(original_handoff, encoding="utf-8")

    completed_at = now_iso()
    first_byte = None
    if probe.first_byte_at is not None and launch_started_at_perf is not None:
        first_byte = probe.first_byte_at - launch_started_at_perf
    result = DiagnosticResult(
        run_id=run_id,
        status=status,
        cold_state=cold_state,
        warm_state=warm_state,
        model=args.model,
        profile=str(profile),
        prompt=args.prompt,
        expected=args.expected,
        started_at=started_at,
        warm_ready_at=warm_ready_at,
        completed_at=completed_at,
        breakdown=LatencyBreakdown(
            env_prep_s=env_prep_s,
            sdk_build_s=sdk_build_s,
            connection_s=connection_s,
            prompt_s=prompt_s,
            first_byte_after_launch_s=first_byte,
            total_s=time.perf_counter() - total_started,
        ),
        assistant_text=assistant_text,
        command=command,
        error=error,
    )
    write_receipt(run_dir, result)

    b = result.breakdown
    print(f"rpc-latency-diagnostic: {status.upper()} run_id={run_id}")
    print(f"cold_state={result.cold_state}")
    print(f"warm_state={result.warm_state}")
    print(f"env_prep_s={b.env_prep_s:.3f}")
    print(f"sdk_build_s={b.sdk_build_s:.3f}")
    print(f"connection_s={b.connection_s:.3f}")
    print("first_byte_after_launch_s=" + (f"{b.first_byte_after_launch_s:.3f}" if b.first_byte_after_launch_s is not None else "<none>"))
    print(f"prompt_s={b.prompt_s:.3f}")
    print(f"total_s={b.total_s:.3f}")
    print(f"receipt={run_dir / 'latency-diagnostic.md'}")
    if error:
        print(f"error={error}", file=sys.stderr)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
