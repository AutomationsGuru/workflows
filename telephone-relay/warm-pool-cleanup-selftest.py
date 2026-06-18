#!/usr/bin/env python3
"""Self-test warm-pool process-tree cleanup without launching Pi."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROTO_PATH = ROOT / "rpc-warm-pool-prototype.py"


@dataclass
class CleanupSelfTestResult:
    status: str
    parent_pid: int
    child_pid: int
    parent_alive_after_cleanup: bool
    child_alive_after_cleanup: bool
    cleanup_log: str
    elapsed_s: float


def load_proto() -> Any:
    spec = importlib.util.spec_from_file_location("rpc_warm_pool_prototype", PROTO_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {PROTO_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_pid_file(path: Path, timeout_s: float) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return int(value)
        time.sleep(0.05)
    raise RuntimeError(f"timed out waiting for child pid file {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove warm-pool process-tree cleanup does not leak children.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Cleanup timeout")
    args = parser.parse_args()

    proto = load_proto()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="warm-pool-cleanup-") as tmp:
        tmp_path = Path(tmp)
        pid_file = tmp_path / "child.pid"
        log_path = tmp_path / "cleanup.log"
        child_script = tmp_path / "spawn_child.py"
        child_script.write_text(
            textwrap.dedent(
                f"""
                import subprocess
                import sys
                import time
                from pathlib import Path

                child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                Path({str(pid_file)!r}).write_text(str(child.pid), encoding="utf-8")
                try:
                    time.sleep(60)
                finally:
                    if child.poll() is None:
                        child.terminate()
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        popen_kwargs: dict[str, Any] = {}
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        else:
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        parent = subprocess.Popen([sys.executable, str(child_script)], **popen_kwargs)
        child_pid = wait_for_pid_file(pid_file, timeout_s=args.timeout)

        proto.terminate_process_tree(parent, timeout_s=args.timeout, label="cleanup-selftest", log_path=log_path)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and (is_process_alive(parent.pid) or is_process_alive(child_pid)):
            time.sleep(0.05)

        parent_alive = is_process_alive(parent.pid)
        child_alive = is_process_alive(child_pid)
        result = CleanupSelfTestResult(
            status="passed" if not parent_alive and not child_alive else "failed",
            parent_pid=parent.pid,
            child_pid=child_pid,
            parent_alive_after_cleanup=parent_alive,
            child_alive_after_cleanup=child_alive,
            cleanup_log=log_path.read_text(encoding="utf-8") if log_path.exists() else "",
            elapsed_s=time.perf_counter() - started,
        )

    out_dir = ROOT / "diagnostics" / time.strftime("%Y%m%d-%H%M%S-cleanup")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cleanup-selftest.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    lines = [
        "# Warm-Pool Cleanup Self-Test",
        "",
        f"Status: `{result.status}`",
        f"Parent PID: `{result.parent_pid}`",
        f"Child PID: `{result.child_pid}`",
        f"Parent alive after cleanup: `{result.parent_alive_after_cleanup}`",
        f"Child alive after cleanup: `{result.child_alive_after_cleanup}`",
        f"Elapsed: {result.elapsed_s:.3f}s",
        "",
        "## Cleanup log",
        "",
        "```text",
        result.cleanup_log,
        "```",
    ]
    (out_dir / "cleanup-selftest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"warm-pool-cleanup-selftest: {result.status.upper()}")
    print(f"parent_alive_after_cleanup={result.parent_alive_after_cleanup}")
    print(f"child_alive_after_cleanup={result.child_alive_after_cleanup}")
    print(f"receipt={out_dir / 'cleanup-selftest.md'}")
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
