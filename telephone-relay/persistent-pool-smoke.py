#!/usr/bin/env python3
"""Smoke test for the persistent warm pool.

Starts one persistent pool, calls it twice through the bridge, and verifies the
same agent PIDs survive across calls.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


@dataclass
class SmokeResult:
    status: str
    pool_url: str
    initial_pids: dict[str, int | None]
    first_pids: dict[str, int | None]
    second_pids: dict[str, int | None]
    first_bridge_run: str
    second_bridge_run: str
    first_bridge_exit: int
    second_bridge_exit: int
    survived_across_calls: bool
    elapsed_s: float
    error: str | None = None


def wait_for_ready(proc: subprocess.Popen[str], timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    assert proc.stdout is not None
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(f"persistent pool exited early with {proc.returncode}")
            time.sleep(0.1)
            continue
        data = json.loads(line)
        if data.get("status") == "ready":
            return data
    raise RuntimeError("timed out waiting for persistent pool readiness")


def post_json(url: str, payload: dict[str, Any] | None = None, timeout_s: int = 30) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def run_bridge(run_id: str, pool_url: str, timeout_s: int) -> tuple[int, Path]:
    proc = subprocess.run(
        [
            PYTHON,
            "bridge-runner.py",
            "--persistent-pool-url",
            pool_url,
            "--timeout",
            str(timeout_s),
            "--run-id",
            run_id,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s + 90,
    )
    run_dir = ROOT / "bridge-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "persistent-smoke-bridge.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (run_dir / "persistent-smoke-bridge.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode, run_dir / "bridge-result.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test persistent warm pool across bridge calls.")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = ROOT / "diagnostics" / (time.strftime("%Y%m%d-%H%M%S") + "-persistent-pool-smoke")
    out_dir.mkdir(parents=True, exist_ok=True)
    proc: subprocess.Popen[str] | None = None
    result: SmokeResult | None = None

    try:
        proc = subprocess.Popen(
            [PYTHON, "persistent-warm-pool.py", "--port", "0", "--timeout", str(args.timeout)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ready = wait_for_ready(proc, timeout_s=args.timeout)
        pool_url = str(ready["url"])
        initial_pids = ready.get("pids") or {}

        first_id = "persistent-smoke-1-" + time.strftime("%Y%m%d%H%M%S")
        first_exit, first_json = run_bridge(first_id, pool_url, args.timeout)
        first_data = json.loads(first_json.read_text(encoding="utf-8"))
        first_response = json.loads(Path(first_data["commands"][0]["stdout_path"]).read_text(encoding="utf-8"))

        second_id = "persistent-smoke-2-" + time.strftime("%Y%m%d%H%M%S")
        second_exit, second_json = run_bridge(second_id, pool_url, args.timeout)
        second_data = json.loads(second_json.read_text(encoding="utf-8"))
        second_response = json.loads(Path(second_data["commands"][0]["stdout_path"]).read_text(encoding="utf-8"))

        first_pids = first_response.get("pids") or {}
        second_pids = second_response.get("pids") or {}
        survived = bool(initial_pids and initial_pids == first_pids == second_pids)
        status = "passed" if first_exit == 0 and second_exit == 0 and survived else "failed"
        result = SmokeResult(
            status=status,
            pool_url=pool_url,
            initial_pids=initial_pids,
            first_pids=first_pids,
            second_pids=second_pids,
            first_bridge_run=str(first_json),
            second_bridge_run=str(second_json),
            first_bridge_exit=first_exit,
            second_bridge_exit=second_exit,
            survived_across_calls=survived,
            elapsed_s=time.perf_counter() - started,
        )
    except Exception as exc:
        result = SmokeResult(
            status="failed",
            pool_url="<unknown>",
            initial_pids={},
            first_pids={},
            second_pids={},
            first_bridge_run="",
            second_bridge_run="",
            first_bridge_exit=-1,
            second_bridge_exit=-1,
            survived_across_calls=False,
            elapsed_s=time.perf_counter() - started,
            error=str(exc),
        )
    finally:
        if proc is not None:
            try:
                if result and result.pool_url != "<unknown>":
                    post_json(result.pool_url.rstrip("/") + "/shutdown", timeout_s=10)
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
                proc.wait(timeout=15)
            if proc.stdout:
                remaining = proc.stdout.read()
                (out_dir / "pool.stdout.txt").write_text(remaining, encoding="utf-8")
            if proc.stderr:
                (out_dir / "pool.stderr.txt").write_text(proc.stderr.read(), encoding="utf-8")

    assert result is not None
    (out_dir / "persistent-pool-smoke.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    lines = [
        "# Persistent Pool Smoke Test",
        "",
        f"Status: `{result.status}`",
        f"Pool URL: `{result.pool_url}`",
        f"Survived across calls: `{result.survived_across_calls}`",
        f"Initial PIDs: `{result.initial_pids}`",
        f"First PIDs: `{result.first_pids}`",
        f"Second PIDs: `{result.second_pids}`",
        f"First bridge exit: `{result.first_bridge_exit}`",
        f"Second bridge exit: `{result.second_bridge_exit}`",
        f"Elapsed: {result.elapsed_s:.2f}s",
        "",
        "## Bridge receipts",
        "",
        f"- `{result.first_bridge_run}`",
        f"- `{result.second_bridge_run}`",
    ]
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])
    (out_dir / "persistent-pool-smoke.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"persistent-pool-smoke: {result.status.upper()}")
    print(f"survived_across_calls={result.survived_across_calls}")
    print(f"receipt={out_dir / 'persistent-pool-smoke.md'}")
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
