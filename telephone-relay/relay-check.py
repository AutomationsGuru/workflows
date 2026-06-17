#!/usr/bin/env python3
"""Verify the Telephone Relay autonomous handoff.

This checker validates the current relay evidence without running any agents:
- final handoff token;
- ordered history lines;
- child process output directives;
- child process exit files;
- latest child session ids are timestamped, not stale fixed ids;
- profile/docs child commands avoid fixed child session ids.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

EXPECTED_HISTORY = [
    "- Agent 1 received `g`, verified blank handoff, wrote `g`, sent `g` to Agent 2.",
    "- Agent 2 received `g`, verified `g` in handoff, wrote `gu`, sent `gu` to Agent 3.",
    "- Agent 3 received `gu`, verified `gu` in handoff, wrote `gur`, sent `gur` to Agent 2.",
    "- Agent 2 received downstream `gur`, verified `gur` in handoff, wrote `guru`, sent `guru` to Agent 1.",
    "- Agent 1 received downstream completion, verified `guru` in handoff, returned `guru` to user.",
]

EXPECTED_OUTPUTS = {
    "sessions/agent-1/agent2-output.txt": "NEXT:Agent 1:guru",
    "sessions/agent-2/agent3-output.txt": "NEXT:Agent 2:gur",
}

EXPECTED_EXITS = {
    "sessions/agent-1/agent2-exit.txt": "0",
    "sessions/agent-2/agent3-exit.txt": "0",
}

STATIC_COMMAND_FILES = [
    "profiles/agent-1.md",
    "profiles/agent-2.md",
    "direct-pi-commands.md",
]

FIXED_CHILD_SESSION_RE = re.compile(
    r"--session-id\s+(?:\"telephone-relay-agent-[23]\"|'telephone-relay-agent-[23]'|telephone-relay-agent-[23])(?=\s|$)"
)

TIMESTAMPED_CHILD_ID_RE = {
    "agent-2": re.compile(r"^telephone-relay-agent-2-\d{14}$"),
    "agent-3": re.compile(r"^telephone-relay-agent-3-\d{14}$"),
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def result(name: str, ok: bool, detail: str) -> CheckResult:
    return CheckResult(name=name, ok=ok, detail=detail)


def ordered_subsequence(expected: Iterable[str], actual: list[str]) -> tuple[bool, str]:
    index = 0
    for line in actual:
        if index < len(EXPECTED_HISTORY) and line == EXPECTED_HISTORY[index]:
            index += 1
    if index == len(EXPECTED_HISTORY):
        return True, f"found {index}/{len(EXPECTED_HISTORY)} expected history lines in order"
    missing = EXPECTED_HISTORY[index]
    return False, f"missing or out of order at expected line {index + 1}: {missing}"


def check_handoff(root: Path, expected_token: str) -> list[CheckResult]:
    path = root / "handoff.md"
    if not path.exists():
        return [result("handoff.exists", False, f"missing {path}")]

    text = read_text(path)
    checks: list[CheckResult] = [result("handoff.exists", True, str(path))]

    match = re.search(r"^Current token:\s*(.*)$", text, flags=re.MULTILINE)
    token = match.group(1).strip() if match else "<missing>"
    checks.append(
        result(
            "handoff.final_token",
            token == expected_token,
            f"Current token: {token!r}; expected {expected_token!r}",
        )
    )

    history = [line.strip() for line in text.splitlines() if line.strip().startswith("- Agent")]
    ok, detail = ordered_subsequence(EXPECTED_HISTORY, history)
    checks.append(result("handoff.ordered_history", ok, detail))
    return checks


def check_child_artifacts(
    root: Path,
    agent2_output: Path | None = None,
    agent3_output: Path | None = None,
    skip_exit_files: bool = False,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    output_specs = {
        agent2_output or root / "sessions/agent-1/agent2-output.txt": "NEXT:Agent 1:guru",
        agent3_output or root / "sessions/agent-2/agent3-output.txt": "NEXT:Agent 2:gur",
    }

    for path, expected in output_specs.items():
        label = path if path.is_absolute() else path
        if not path.exists():
            checks.append(result(f"child_output.{label}", False, "missing"))
            continue
        text = read_text(path)
        checks.append(
            result(
                f"child_output.{label}",
                expected in text,
                f"expected directive {expected!r}; size={len(text)} chars",
            )
        )

    if skip_exit_files:
        checks.append(result("child_exit.skipped", True, "exit file checks skipped by request"))
        return checks

    for rel, expected in EXPECTED_EXITS.items():
        path = root / rel
        if not path.exists():
            checks.append(result(f"child_exit.{rel}", False, "missing"))
            continue
        value = read_text(path).strip()
        checks.append(
            result(
                f"child_exit.{rel}",
                value == expected,
                f"exit={value!r}; expected {expected!r}",
            )
        )

    return checks


def latest_session_file(root: Path, agent: str) -> Path | None:
    session_dir = root / "sessions" / agent
    files = list(session_dir.glob("*.jsonl"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def session_header_id(path: Path) -> str | None:
    try:
        first = read_text(path).splitlines()[0]
        data = json.loads(first)
        return data.get("id")
    except Exception:
        return None


def check_session_ids(root: Path) -> list[CheckResult]:
    checks: list[CheckResult] = []

    for agent in ("agent-2", "agent-3"):
        path = latest_session_file(root, agent)
        if path is None:
            checks.append(result(f"session_id.latest_{agent}", False, "no session jsonl found"))
            continue
        sid = session_header_id(path)
        regex = TIMESTAMPED_CHILD_ID_RE[agent]
        checks.append(
            result(
                f"session_id.latest_{agent}",
                bool(sid and regex.match(sid)),
                f"latest={path.name}; id={sid!r}; expected {regex.pattern}",
            )
        )

        text = read_text(path)
        checks.append(
            result(
                f"session_id.no_fixed_child_command_in_latest_{agent}",
                not FIXED_CHILD_SESSION_RE.search(text),
                "latest session contains no exact fixed child --session-id" if not FIXED_CHILD_SESSION_RE.search(text) else "found exact fixed child --session-id in latest session",
            )
        )

    return checks


def check_static_commands(root: Path) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for rel in STATIC_COMMAND_FILES:
        path = root / rel
        if not path.exists():
            checks.append(result(f"static.{rel}", False, "missing"))
            continue
        text = read_text(path)
        fixed = FIXED_CHILD_SESSION_RE.search(text)
        has_run_id = "run_id=$(date +%Y%m%d%H%M%S)" in text or "$runId = Get-Date -Format yyyyMMddHHmmss" in text
        checks.append(
            result(
                f"static.no_fixed_child_session_id.{rel}",
                fixed is None,
                "no exact fixed child --session-id" if fixed is None else f"found {fixed.group(0)!r}",
            )
        )
        if rel in {"profiles/agent-1.md", "profiles/agent-2.md", "direct-pi-commands.md"}:
            checks.append(
                result(
                    f"static.has_timestamped_child_id_pattern.{rel}",
                    has_run_id,
                    "timestamp run_id pattern present" if has_run_id else "missing timestamp run_id pattern",
                )
            )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Telephone Relay evidence without running agents.")
    parser.add_argument("--root", default=Path(__file__).resolve().parent, type=Path, help="Telephone relay root directory")
    parser.add_argument("--expected-token", default="guru", help="Expected final handoff token")
    parser.add_argument("--agent2-output", type=Path, help="Override Agent 2 output evidence path")
    parser.add_argument("--agent3-output", type=Path, help="Override Agent 3 output evidence path")
    parser.add_argument("--skip-exit-files", action="store_true", help="Skip child exit-file checks, useful for RPC controller runs")
    parser.add_argument("--skip-session-id-check", action="store_true", help="Skip latest child session-id checks, useful for --no-session RPC runs")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    args = parser.parse_args()

    root = args.root.resolve()
    agent2_output = args.agent2_output.resolve() if args.agent2_output else None
    agent3_output = args.agent3_output.resolve() if args.agent3_output else None

    checks: list[CheckResult] = []
    checks.extend(check_handoff(root, args.expected_token))
    checks.extend(check_child_artifacts(root, agent2_output, agent3_output, args.skip_exit_files))
    if args.skip_session_id_check:
        checks.append(result("session_id.skipped", True, "session-id checks skipped by request"))
    else:
        checks.extend(check_session_ids(root))
    checks.extend(check_static_commands(root))

    ok = all(check.ok for check in checks)

    if args.json:
        print(json.dumps({"ok": ok, "root": str(root), "checks": [asdict(c) for c in checks]}, indent=2))
    else:
        print(f"relay-check: {'PASS' if ok else 'FAIL'}")
        print(f"root: {root}")
        for check in checks:
            icon = "PASS" if check.ok else "FAIL"
            print(f"[{icon}] {check.name}: {check.detail}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
