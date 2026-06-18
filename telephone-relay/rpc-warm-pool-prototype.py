#!/usr/bin/env python3
"""RPC warm-pool prototype for the Telephone Relay.

This is a bounded speed experiment. It does not replace the proven direct relay.
It starts three long-lived `pi --mode rpc` processes and controller-routes the
same `g -> gu -> gur -> guru` handoff without cold child `pi -p` launches.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
HANDOFF = ROOT / "handoff.md"
DEFAULT_TIMEOUT = 240
PI_CMD = shutil.which("pi.cmd") or shutil.which("pi") or "pi"

RESET_HANDOFF = "# Telephone Relay Handoff\n\nCurrent token:\n\nHistory:\n"


@dataclass
class TurnResult:
    agent: str
    prompt: str
    expected: str
    output: str
    elapsed_s: float


@dataclass
class AgentTiming:
    name: str
    model: str
    startup_s: float


class RpcError(RuntimeError):
    pass


def append_log(path: Path | None, message: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(path.read_text(encoding="utf-8") + message if path.exists() else message, encoding="utf-8")


def terminate_process_tree(
    proc: subprocess.Popen[Any], *, timeout_s: float = 5.0, label: str = "process", log_path: Path | None = None
) -> None:
    """Terminate a process and its descendants with a bounded wait."""
    pid = proc.pid
    if proc.poll() is not None:
        append_log(log_path, f"{label}: already exited with code {proc.returncode}\n")
        return

    append_log(log_path, f"{label}: terminating pid={pid}\n")
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        proc.wait(timeout=timeout_s)
        append_log(log_path, f"{label}: exited with code {proc.returncode}\n")
        return
    except subprocess.TimeoutExpired:
        append_log(log_path, f"{label}: terminate timed out after {timeout_s:.1f}s; killing\n")
    except Exception as exc:
        append_log(log_path, f"{label}: terminate failed: {exc}\n")

    if proc.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout_s,
                    check=False,
                )
            else:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait(timeout=timeout_s)
            append_log(log_path, f"{label}: killed with code {proc.returncode}\n")
        except Exception as exc:
            append_log(log_path, f"{label}: kill failed: {exc}\n")
            raise RpcError(f"{label}: failed to stop process tree pid={pid}: {exc}") from exc


class RpcAgent:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        profile: Path,
        timeout_s: int = DEFAULT_TIMEOUT,
        log_dir: Path | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.profile = profile
        self.timeout_s = timeout_s
        self.log_path = log_dir / f"{name}.log" if log_dir else None
        self.proc: subprocess.Popen[str] | None = None
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.stderr_lines: queue.Queue[str] = queue.Queue()
        self._reader_threads: list[threading.Thread] = []
        self.startup_s = 0.0

    def start(self) -> AgentTiming:
        cmd = [
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
            self.name,
            "--model",
            self.model,
            "--append-system-prompt",
            str(ROOT / "system-rpc.md"),
            "--append-system-prompt",
            str(self.profile),
        ]
        started = time.perf_counter()
        append_log(self.log_path, f"{self.name}: starting command {cmd!r}\n")
        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        self.proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **popen_kwargs,
        )
        append_log(self.log_path, f"{self.name}: started pid={self.proc.pid}\n")
        self._start_readers()
        # Current Pi RPC mode may not emit a session header until commands are sent.
        # Treat get_state as the readiness probe.
        state = self.command({"type": "get_state"}, timeout_s=30)
        if not state.get("success"):
            self.log_failure(f"get_state failed: {state}")
            raise RpcError(f"{self.name}: get_state failed: {state}")
        self.startup_s = time.perf_counter() - started
        append_log(self.log_path, f"{self.name}: ready in {self.startup_s:.3f}s\n")
        return AgentTiming(name=self.name, model=self.model, startup_s=self.startup_s)

    def _start_readers(self) -> None:
        assert self.proc and self.proc.stdout and self.proc.stderr

        def stdout_reader() -> None:
            assert self.proc and self.proc.stdout
            for line in self.proc.stdout:
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
                self.stderr_lines.put(line.rstrip("\r\n"))

        for target in (stdout_reader, stderr_reader):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._reader_threads.append(thread)

    def _send(self, command: dict[str, Any]) -> str:
        if not self.proc or not self.proc.stdin:
            raise RpcError(f"{self.name}: process not started")
        request_id = command.get("id") or f"{self.name}-{uuid.uuid4().hex}"
        command = {**command, "id": request_id}
        self.proc.stdin.write(json.dumps(command, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return str(request_id)

    def log_failure(self, reason: str) -> None:
        stderr = self.collect_stderr()
        exit_code = self.proc.poll() if self.proc else None
        append_log(
            self.log_path,
            f"{self.name}: failure: {reason}; exit_code={exit_code}; stderr_tail={stderr[-10:]}\n",
        )

    def command(self, command: dict[str, Any], timeout_s: int | None = None) -> dict[str, Any]:
        request_id = self._send(command)
        response = self._wait_for(
            lambda e: e.get("type") == "response" and e.get("id") == request_id,
            timeout_s=timeout_s or self.timeout_s,
            waiting_for=f"response to {command.get('type')}",
        )
        if not response:
            reason = f"timed out waiting for response to {command.get('type')}"
            self.log_failure(reason)
            raise RpcError(f"{self.name}: {reason}")
        return response

    def prompt(self, message: str, expected: str) -> TurnResult:
        started = time.perf_counter()
        response = self.command({"type": "prompt", "message": message}, timeout_s=30)
        if not response.get("success"):
            raise RpcError(f"{self.name}: prompt rejected: {response}")

        agent_end = self._wait_for(
            lambda e: e.get("type") == "agent_end",
            timeout_s=self.timeout_s,
            waiting_for="agent_end",
        )
        elapsed = time.perf_counter() - started
        if not agent_end:
            self.log_failure("timed out waiting for agent_end")
            raise RpcError(f"{self.name}: timed out waiting for agent_end")

        output_response = self.command({"type": "get_last_assistant_text"}, timeout_s=30)
        output = (output_response.get("data") or {}).get("text") or ""
        if expected not in output:
            self.log_failure(f"expected directive {expected!r} not found in output {output!r}")
            stderr = self.collect_stderr()
            raise RpcError(
                f"{self.name}: expected directive {expected!r} not found in output {output!r}. "
                f"stderr tail={stderr[-5:]}"
            )
        append_log(self.log_path, f"{self.name}: prompt {message!r} completed in {elapsed:.3f}s\n")
        return TurnResult(agent=self.name, prompt=message, expected=expected, output=output, elapsed_s=elapsed)

    def _wait_for(self, predicate, timeout_s: int, waiting_for: str) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc and self.proc.poll() is not None:
                reason = f"process exited while waiting for {waiting_for}"
                self.log_failure(reason)
                raise RpcError(f"{self.name}: {reason}; exit_code={self.proc.returncode}")
            try:
                event = self.events.get(timeout=0.2)
            except queue.Empty:
                continue
            if predicate(event):
                return event
        self.log_failure(f"timeout after {timeout_s}s waiting for {waiting_for}")
        return None

    def collect_stderr(self) -> list[str]:
        lines: list[str] = []
        while True:
            try:
                lines.append(self.stderr_lines.get_nowait())
            except queue.Empty:
                return lines

    def stop(self) -> None:
        if not self.proc:
            return
        terminate_process_tree(self.proc, timeout_s=5.0, label=self.name, log_path=self.log_path)


def reset_handoff() -> None:
    HANDOFF.write_text(RESET_HANDOFF, encoding="utf-8")


def write_receipt(run_dir: Path, data: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "rpc-warm-pool-result.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# RPC Warm-Pool Prototype Receipt",
        "",
        f"Run ID: `{data['run_id']}`",
        f"Status: `{data['status']}`",
        "",
        "## Timing",
        "",
        f"- startup total: {data.get('startup_total_s', 0):.2f}s",
        f"- relay time after warm: {data.get('relay_elapsed_s', 0):.2f}s",
        f"- total wall time: {data.get('total_elapsed_s', 0):.2f}s",
        "- direct relay baseline: ~87s",
        "",
        "## Agent startup",
        "",
    ]
    for item in data.get("startup", []):
        lines.append(f"- {item['name']} / `{item['model']}`: {item['startup_s']:.2f}s")
    lines.extend(["", "## Turns", ""])
    for turn in data.get("turns", []):
        lines.append(f"- {turn['agent']} `{turn['prompt']}` -> `{turn['expected']}` in {turn['elapsed_s']:.2f}s")
    if data.get("fallbacks"):
        lines.extend(["", "## Fallbacks", ""])
        for item in data["fallbacks"]:
            lines.append(f"- {item}")
    if data.get("process_logs"):
        lines.extend(["", "## Process logs", ""])
        for item in data["process_logs"]:
            lines.append(f"- `{item}`")
    if data.get("error"):
        lines.extend(["", "## Error", "", "```text", data["error"], "```"])
    lines.extend(["", "## Artifacts", "", f"- `{run_dir / 'rpc-warm-pool-result.json'}`"])
    (run_dir / "rpc-warm-pool-result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_turn_outputs(run_dir: Path, turns: list[TurnResult]) -> tuple[Path, Path, Path]:
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for index, turn in enumerate(turns, start=1):
        path = outputs_dir / f"{index:02d}-{turn.agent}.txt"
        path.write_text(turn.output, encoding="utf-8")
        paths[f"{index:02d}-{turn.agent}"] = path

    agent2_return = outputs_dir / "agent2-return.txt"
    agent3_pivot = outputs_dir / "agent3-pivot.txt"
    agent1_final = outputs_dir / "agent1-final.txt"
    for turn in turns:
        if turn.expected == "NEXT:Agent 1:guru":
            agent2_return.write_text(turn.output, encoding="utf-8")
        if turn.expected == "NEXT:Agent 2:gur":
            agent3_pivot.write_text(turn.output, encoding="utf-8")
        if turn.expected == "USER:guru — return verified.":
            agent1_final.write_text(turn.output, encoding="utf-8")
    return agent2_return, agent3_pivot, agent1_final


def build_agents(agent2_model: str, timeout_s: int, log_dir: Path | None = None) -> dict[str, RpcAgent]:
    return {
        "agent1": RpcAgent(
            name="telephone-relay-agent-1-rpc",
            model="minimax-oauth/MiniMax-M3",
            profile=ROOT / "profiles/agent-1-rpc.md",
            timeout_s=timeout_s,
            log_dir=log_dir,
        ),
        "agent2": RpcAgent(
            name="telephone-relay-agent-2-rpc",
            model=agent2_model,
            profile=ROOT / "profiles/agent-2-rpc.md",
            timeout_s=timeout_s,
            log_dir=log_dir,
        ),
        "agent3": RpcAgent(
            name="telephone-relay-agent-3-rpc",
            model="openai-codex/gpt-5.5",
            profile=ROOT / "profiles/agent-3-rpc.md",
            timeout_s=timeout_s,
            log_dir=log_dir,
        ),
    }


def run_relay(agent2_model: str, timeout_s: int, log_dir: Path | None = None) -> tuple[list[AgentTiming], list[TurnResult]]:
    agents = build_agents(agent2_model, timeout_s, log_dir=log_dir)
    timings: list[AgentTiming] = []
    try:
        for agent in agents.values():
            timings.append(agent.start())

        turns = [
            agents["agent1"].prompt("g", "NEXT:Agent 2:g"),
            agents["agent2"].prompt("g", "NEXT:Agent 3:gu"),
            agents["agent3"].prompt("gu", "NEXT:Agent 2:gur"),
            agents["agent2"].prompt("gur", "NEXT:Agent 1:guru"),
            agents["agent1"].prompt("guru", "USER:guru — return verified."),
        ]
        return timings, turns
    finally:
        for agent in agents.values():
            agent.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Telephone Relay through warm Pi RPC processes.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-turn timeout in seconds")
    parser.add_argument("--agent2-model", default="xai-oauth/grok-build-0.1", help="Primary Agent 2 model")
    parser.add_argument("--agent2-fallback-model", default="openai-codex/gpt-5.5", help="Fallback Agent 2 model")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset handoff.md before running")
    args = parser.parse_args()

    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "rpc-runs" / run_id
    log_dir = run_dir / "logs"
    total_started = time.perf_counter()
    data: dict[str, Any] = {
        "run_id": run_id,
        "status": "started",
        "fallbacks": [],
        "startup": [],
        "turns": [],
        "process_logs": [],
    }

    if not args.no_reset:
        reset_handoff()

    try:
        try:
            startup, turns = run_relay(args.agent2_model, args.timeout, log_dir=log_dir)
        except Exception as exc:
            data["fallbacks"].append(f"Agent 2 primary model {args.agent2_model} failed: {exc}")
            data["process_logs"] = [str(path) for path in sorted(log_dir.glob("*.log"))]
            reset_handoff()
            startup, turns = run_relay(args.agent2_fallback_model, args.timeout, log_dir=log_dir)
            data["fallbacks"].append(f"Retried Agent 2 with fallback model {args.agent2_fallback_model}")

        relay_elapsed = sum(turn.elapsed_s for turn in turns)
        total_elapsed = time.perf_counter() - total_started
        agent2_output, agent3_output, agent1_output = write_turn_outputs(run_dir, turns)

        final_text = HANDOFF.read_text(encoding="utf-8")
        if "Current token: guru" not in final_text:
            raise RpcError("final handoff did not contain Current token: guru")
        if "USER:guru — return verified." not in agent1_output.read_text(encoding="utf-8"):
            raise RpcError("Agent 1 final output missing USER directive")

        data.update(
            {
                "status": "passed",
                "startup": [asdict(item) for item in startup],
                "turns": [asdict(item) for item in turns],
                "startup_total_s": sum(item.startup_s for item in startup),
                "relay_elapsed_s": relay_elapsed,
                "total_elapsed_s": total_elapsed,
                "agent2_output": str(agent2_output),
                "agent3_output": str(agent3_output),
                "agent1_output": str(agent1_output),
                "process_logs": [str(path) for path in sorted(log_dir.glob("*.log"))],
            }
        )
        write_receipt(run_dir, data)
        print(f"RPC warm-pool relay PASS: {run_id}")
        print(f"startup_total_s={data['startup_total_s']:.2f}")
        print(f"relay_elapsed_s={relay_elapsed:.2f}")
        print(f"total_elapsed_s={total_elapsed:.2f}")
        print(f"agent2_output={agent2_output}")
        print(f"agent3_output={agent3_output}")
        print(f"receipt={run_dir / 'rpc-warm-pool-result.md'}")
        return 0
    except Exception as exc:
        data["status"] = "failed"
        data["error"] = str(exc)
        data["total_elapsed_s"] = time.perf_counter() - total_started
        data["process_logs"] = [str(path) for path in sorted(log_dir.glob("*.log"))]
        write_receipt(run_dir, data)
        print(f"RPC warm-pool relay FAIL: {run_id}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(f"receipt={run_dir / 'rpc-warm-pool-result.md'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
