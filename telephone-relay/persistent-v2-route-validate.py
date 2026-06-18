#!/usr/bin/env python3
"""Live validation for the direct v2 -> persistent-warm-pool -> /relay route.

This closes the gap noted in
`reports/2026-06-16-live-v2-v1-rpc-validation.md` (the v2-through-v1 route was
proven; the direct persistent channel was not). It:

1. starts one persistent warm pool (`persistent-warm-pool.py --port 0`);
2. drives a relay through RPC Bridge v2 on the persistent `default` channel with
   v1 fallback disabled, so a persistent-route failure surfaces instead of being
   masked by the v1 fallback;
3. verifies the relay evidence with `relay-check.py`;
4. shuts the pool down and writes a combined receipt.

It does not modify the bridge, the pool, or the verifier. It only exercises and
records the existing direct persistent route.
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
# Pi CLI model IDs include the provider route; this is not a raw OpenAI API model name.
DEFAULT_AGENT2_MODEL = "openai-codex/gpt-5.5"


@dataclass
class RouteResult:
    status: str
    run_id: str
    tenant_id: str
    pool_url: str
    pool_pids: dict[str, int | None] = field(default_factory=dict)
    bridge_exit: int = -1
    selected_channel: str | None = None
    fallback_used: bool = True
    bridge_status: str | None = None
    pool_run_count: int | None = None
    relay_check_ok: bool = False
    agent2_output: str | None = None
    agent3_output: str | None = None
    v2_receipt: str | None = None
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


def post_json(url: str, payload: dict[str, Any] | None = None, timeout_s: int = 30) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def run_bridge(
    run_id: str,
    tenant_id: str,
    pool_url: str,
    timeout_s: int,
    out_dir: Path,
    no_fallback_v1: bool,
) -> tuple[int, str, str]:
    command = [
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
    ]
    if no_fallback_v1:
        command.append("--no-fallback-v1")
    proc = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s + 120,
    )
    (out_dir / "bridge-v2.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "bridge-v2.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def run_relay_check(agent2_output: Path, agent3_output: Path, out_dir: Path) -> tuple[bool, Path]:
    proc = subprocess.run(
        [
            PYTHON,
            "relay-check.py",
            "--agent2-output",
            str(agent2_output),
            "--agent3-output",
            str(agent3_output),
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


def write_receipt(out_dir: Path, result: RouteResult) -> Path:
    (out_dir / "persistent-v2-route-validate.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# Live v2 -> Persistent Warm-Pool -> /relay Validation",
        "",
        f"Status: `{result.status}`",
        f"Run ID: `{result.run_id}`",
        f"Tenant: `{result.tenant_id}`",
        f"Pool URL: `{result.pool_url}`",
        f"Pool PIDs: `{result.pool_pids}`",
        "",
        "## Bridge v2",
        "",
        f"- bridge exit: `{result.bridge_exit}`",
        f"- bridge status: `{result.bridge_status}`",
        f"- selected channel: `{result.selected_channel}`",
        f"- fallback used: `{result.fallback_used}`",
        f"- pool run_count: `{result.pool_run_count}`",
        f"- v2 receipt: `{result.v2_receipt}`",
        "",
        "## Verifier",
        "",
        f"- relay-check ok: `{result.relay_check_ok}`",
        f"- agent2 output: `{result.agent2_output}`",
        f"- agent3 output: `{result.agent3_output}`",
        f"- relay-check capture: `{result.relay_check_capture}`",
        "",
        f"Elapsed: {result.elapsed_s:.2f}s",
    ]
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])
    receipt = out_dir / "persistent-v2-route-validate.md"
    receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the direct v2 -> persistent pool -> /relay route live.")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tenant-id", default="live-v2-persistent")
    parser.add_argument("--run-id", default="live-v2-persistent-" + time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--agent2-model", default=DEFAULT_AGENT2_MODEL)
    parser.add_argument("--no-fallback-v1", action="store_true", help="Force persistent truth by disabling v1 fallback")
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = ROOT / "diagnostics" / (time.strftime("%Y%m%d-%H%M%S") + "-v2-persistent-route")
    out_dir.mkdir(parents=True, exist_ok=True)
    proc: subprocess.Popen[str] | None = None
    pool_lines: queue.Queue[str] = queue.Queue()
    result = RouteResult(
        status="failed",
        run_id=args.run_id,
        tenant_id=args.tenant_id,
        pool_url="<unknown>",
    )

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
        result.pool_pids = ready.get("pids") or {}

        bridge_exit, _, _ = run_bridge(
            args.run_id,
            args.tenant_id,
            result.pool_url,
            args.timeout,
            out_dir,
            no_fallback_v1=args.no_fallback_v1,
        )
        result.bridge_exit = bridge_exit

        v2_json = ROOT / "bridge-v2-runs" / args.run_id / "rpc-bridge-v2-result.json"
        if not v2_json.exists():
            raise RuntimeError(f"v2 receipt not found: {v2_json}")
        v2 = json.loads(v2_json.read_text(encoding="utf-8"))
        result.v2_receipt = str(v2_json)
        result.bridge_status = v2.get("status")
        result.selected_channel = v2.get("selected_channel")
        result.fallback_used = bool(v2.get("fallback_used"))
        response = v2.get("response") or {}
        result.pool_run_count = response.get("run_count")
        result.agent2_output = response.get("agent2_output")
        result.agent3_output = response.get("agent3_output")

        if result.bridge_status != "passed":
            raise RuntimeError(f"bridge v2 status not passed: {result.bridge_status}")
        if result.selected_channel != "default":
            raise RuntimeError(f"expected persistent 'default' channel, got {result.selected_channel!r}")
        if result.fallback_used:
            raise RuntimeError("v1 fallback was used; persistent route did not serve the call")
        if not result.agent2_output or not result.agent3_output:
            raise RuntimeError("pool response missing agent2/agent3 output paths")

        ok, capture = run_relay_check(Path(result.agent2_output), Path(result.agent3_output), out_dir)
        result.relay_check_ok = ok
        result.relay_check_capture = str(capture)
        if not ok:
            raise RuntimeError("relay-check failed for persistent-route outputs")

        result.status = "passed"
    except Exception as exc:
        result.error = str(exc)
    finally:
        if proc is not None:
            try:
                if result.pool_url != "<unknown>":
                    post_json(result.pool_url.rstrip("/") + "/shutdown", timeout_s=10)
                proc.wait(timeout=15)
            except Exception:
                stop_process_tree(proc)

    result.elapsed_s = time.perf_counter() - started
    receipt = write_receipt(out_dir, result)
    print(f"persistent-v2-route-validate: {result.status.upper()}")
    print(f"selected_channel={result.selected_channel} fallback_used={result.fallback_used}")
    print(f"relay_check_ok={result.relay_check_ok}")
    print(f"receipt={receipt}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
