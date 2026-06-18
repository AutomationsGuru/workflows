#!/usr/bin/env python3
"""Caller-facing default route wrapper for RPC Bridge v2.

Reads `caller-default-routing.json` and invokes `rpc_bridge_v2.py` using the
configured default route. The config prefers the persistent pool via an
environment-provided URL and intentionally keeps v1 fallback enabled.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
DEFAULT_CONFIG = ROOT / "caller-default-routing.json"


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("caller routing config must be a JSON object")
    return data


def build_command(config: dict[str, Any], args: argparse.Namespace) -> list[str]:
    default_channel = config.get("default_channel")
    routes = config.get("routes") if isinstance(config.get("routes"), dict) else {}
    default_route = routes.get(default_channel) if isinstance(default_channel, str) else None
    if not isinstance(default_route, dict):
        raise ValueError(f"missing configured default route for channel {default_channel!r}")
    if config.get("fallback_v1_enabled") is not True:
        raise ValueError("caller default route requires fallback_v1_enabled=true")
    if "v1" not in routes:
        raise ValueError("caller default route requires a v1 fallback route")
    if default_route.get("kind") != "persistent":
        raise ValueError("caller default route must use the persistent route kind")

    pool_url_env = default_route.get("pool_url_env")
    if not isinstance(pool_url_env, str) or not pool_url_env:
        raise ValueError("persistent default route requires pool_url_env")
    pool_url = os.environ.get(pool_url_env)
    if not pool_url:
        raise ValueError(f"environment variable {pool_url_env} must contain the persistent pool URL")

    command = [
        PYTHON,
        "rpc_bridge_v2.py",
        "--persistent-pool-url",
        pool_url,
        "--channel",
        default_channel,
        "--tenant-id",
        args.tenant_id,
        "--run-id",
        args.run_id,
        "--timeout",
        str(args.timeout),
        "--max-attempts",
        str(args.max_attempts),
        "--initial-backoff-s",
        str(args.initial_backoff_s),
    ]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the configured caller default route through RPC Bridge v2.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", default="caller-default")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--initial-backoff-s", type=float, default=0.25)
    args = parser.parse_args()

    if not SAFE_RUN_ID_RE.fullmatch(args.run_id):
        parser.error("--run-id may only contain letters, numbers, hyphens, and underscores")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least one")
    if args.initial_backoff_s < 0:
        parser.error("--initial-backoff-s must be non-negative")

    config = load_config(Path(args.config))
    command = build_command(config, args)
    proc = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=args.timeout + 180,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
