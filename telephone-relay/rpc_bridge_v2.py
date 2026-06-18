#!/usr/bin/env python3
"""Typed RPC Bridge v2 for Telephone Relay.

v2 adds channel routing, call stats, and retry/backoff while keeping the v1
`bridge-runner.py` path intact as fallback.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

ChannelKind = Literal["persistent", "v1"]
CallStatus = Literal["passed", "failed"]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_s: float = 0.25
    multiplier: float = 2.0
    max_backoff_s: float = 2.0

    def delay_for_retry(self, retry_index: int) -> float:
        raw_delay = self.initial_backoff_s * (self.multiplier ** max(0, retry_index - 1))
        return max(0.0, min(max(0.0, self.max_backoff_s), raw_delay))


@dataclass(frozen=True)
class ChannelRoute:
    name: str
    kind: ChannelKind
    url: str | None = None


@dataclass(frozen=True)
class RpcBridgeV2Request:
    run_id: str
    channel: str = "default"
    tenant_id: str = "default"
    timeout_s: int = 300


@dataclass
class CallAttempt:
    channel: str
    kind: ChannelKind
    attempt: int
    status: str
    elapsed_s: float
    error: str | None = None
    backoff_s: float = 0.0


@dataclass
class CallStats:
    started_at: str
    completed_at: str = ""
    elapsed_s: float = 0.0
    attempts: int = 0
    retries: int = 0
    successes: int = 0
    failures: int = 0
    fallback_used: bool = False
    backoff_total_s: float = 0.0
    attempts_detail: list[CallAttempt] = field(default_factory=list)


@dataclass
class RpcBridgeV2Result:
    status: CallStatus
    run_id: str
    selected_channel: str | None
    fallback_used: bool
    response: dict[str, object]
    stats: CallStats
    receipt_dir: str | None = None
    error: str | None = None


Transport = Callable[[ChannelRoute, RpcBridgeV2Request], dict[str, object]]
SleepFn = Callable[[float], None]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(url: str, payload: dict[str, object], timeout_s: int) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read().decode("utf-8")
            status_code = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status_code = exc.code
    parsed = json.loads(body) if body else {}
    data = parsed if isinstance(parsed, dict) else {"body": parsed}
    data["http_status"] = status_code
    return data


class RpcBridgeV2Client:
    def __init__(
        self,
        *,
        routes: dict[str, ChannelRoute],
        retry_policy: RetryPolicy | None = None,
        fallback_v1: bool = True,
        sleep_fn: SleepFn = time.sleep,
        persistent_transport: Transport | None = None,
        v1_transport: Transport | None = None,
    ) -> None:
        self.routes = routes
        self.retry_policy = retry_policy or RetryPolicy()
        self.fallback_v1 = fallback_v1
        self.sleep_fn = sleep_fn
        self.persistent_transport = persistent_transport or self._call_persistent
        self.v1_transport = v1_transport or self._call_v1_bridge

    def call(self, request: RpcBridgeV2Request) -> RpcBridgeV2Result:
        started_perf = time.perf_counter()
        stats = CallStats(started_at=now_iso())
        response: dict[str, object] = {}
        selected_channel: str | None = None
        error: str | None = None

        route = self.routes.get(request.channel)
        if route is None:
            route = self.routes.get("default")
        if route is None:
            raise ValueError(f"no route for channel {request.channel!r} and no default route")

        route_result = self._call_route_with_retry(route, request, stats)
        if route_result.get("status") == "passed":
            response = route_result
            selected_channel = route.name
        elif self.fallback_v1 and route.kind != "v1":
            stats.fallback_used = True
            fallback = self.routes.get("v1") or ChannelRoute(name="v1", kind="v1")
            route_result = self._call_route_with_retry(fallback, request, stats)
            response = route_result
            selected_channel = fallback.name if route_result.get("status") == "passed" else None
        else:
            response = route_result

        status: CallStatus = "passed" if response.get("status") == "passed" else "failed"
        if status == "failed":
            error = str(response.get("error") or "bridge v2 call failed")

        stats.completed_at = now_iso()
        stats.elapsed_s = time.perf_counter() - started_perf
        return RpcBridgeV2Result(
            status=status,
            run_id=request.run_id,
            selected_channel=selected_channel,
            fallback_used=stats.fallback_used,
            response=response,
            stats=stats,
            error=error,
        )

    def _call_route_with_retry(
        self, route: ChannelRoute, request: RpcBridgeV2Request, stats: CallStats
    ) -> dict[str, object]:
        last_response: dict[str, object] = {"status": "failed", "error": "not attempted"}
        attempts = max(1, self.retry_policy.max_attempts)
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                if route.kind == "persistent":
                    response = self.persistent_transport(route, request)
                else:
                    response = self.v1_transport(route, request)
                elapsed = time.perf_counter() - started
                ok = response.get("status") == "passed"
                stats.attempts += 1
                stats.successes += 1 if ok else 0
                stats.failures += 0 if ok else 1
                stats.attempts_detail.append(
                    CallAttempt(
                        channel=route.name,
                        kind=route.kind,
                        attempt=attempt,
                        status=str(response.get("status") or "unknown"),
                        elapsed_s=elapsed,
                        error=None if ok else str(response.get("error") or "non-passed status"),
                    )
                )
                last_response = response
                if ok or not self._should_retry(response):
                    return response
            except Exception as exc:
                elapsed = time.perf_counter() - started
                stats.attempts += 1
                stats.failures += 1
                stats.attempts_detail.append(
                    CallAttempt(
                        channel=route.name,
                        kind=route.kind,
                        attempt=attempt,
                        status="failed",
                        elapsed_s=elapsed,
                        error=str(exc),
                    )
                )
                last_response = {"status": "failed", "error": str(exc)}

            if attempt < attempts:
                delay = self.retry_policy.delay_for_retry(attempt)
                stats.retries += 1
                stats.backoff_total_s += delay
                stats.attempts_detail[-1].backoff_s = delay
                self.sleep_fn(delay)

        return last_response

    def _should_retry(self, response: dict[str, object]) -> bool:
        if response.get("status") == "passed":
            return False
        if response.get("status") == "overflow" or response.get("http_status") == 429:
            return False
        return True

    def _call_persistent(self, route: ChannelRoute, request: RpcBridgeV2Request) -> dict[str, object]:
        if not route.url:
            raise ValueError(f"persistent route {route.name!r} is missing url")
        return post_json(
            route.url.rstrip("/") + "/relay",
            {"run_id": request.run_id, "tenant_id": request.tenant_id},
            timeout_s=request.timeout_s,
        )

    def _call_v1_bridge(self, route: ChannelRoute, request: RpcBridgeV2Request) -> dict[str, object]:
        run_dir = ROOT / "bridge-runs" / request.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [PYTHON, "bridge-runner.py", "--timeout", str(request.timeout_s), "--run-id", request.run_id],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=request.timeout_s + 120,
        )
        (run_dir / "rpc-bridge-v2-v1.stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (run_dir / "rpc-bridge-v2-v1.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        result_path = run_dir / "bridge-result.json"
        data: dict[str, object] = {"status": "failed", "exit_code": proc.returncode}
        if result_path.exists():
            data.update(json.loads(result_path.read_text(encoding="utf-8")))
        if proc.returncode == 0 and data.get("status") == "passed":
            data["status"] = "passed"
        return data


def write_receipt(result: RpcBridgeV2Result) -> Path:
    run_dir = ROOT / "bridge-v2-runs" / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result.receipt_dir = str(run_dir)
    (run_dir / "rpc-bridge-v2-result.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# RPC Bridge v2 Result",
        "",
        f"Run ID: `{result.run_id}`",
        f"Status: `{result.status}`",
        f"Selected channel: `{result.selected_channel}`",
        f"Fallback used: `{result.fallback_used}`",
        "",
        "## Call stats",
        "",
        f"- attempts: {result.stats.attempts}",
        f"- retries: {result.stats.retries}",
        f"- successes: {result.stats.successes}",
        f"- failures: {result.stats.failures}",
        f"- backoff total: {result.stats.backoff_total_s:.3f}s",
        f"- elapsed: {result.stats.elapsed_s:.3f}s",
        "",
        "## Attempts",
        "",
    ]
    for attempt in result.stats.attempts_detail:
        lines.append(
            f"- {attempt.channel}/{attempt.kind} attempt {attempt.attempt}: "
            f"{attempt.status}, {attempt.elapsed_s:.3f}s, backoff {attempt.backoff_s:.3f}s"
        )
        if attempt.error:
            lines.append(f"  - error: `{attempt.error}`")
    if result.error:
        lines.extend(["", "## Error", "", "```text", result.error, "```"])
    (run_dir / "rpc-bridge-v2-result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run_dir / "rpc-bridge-v2-result.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Telephone Relay through RPC Bridge v2.")
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--channel", default="default")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--persistent-pool-url", help="Persistent pool URL for the default channel")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--initial-backoff-s", type=float, default=0.25)
    parser.add_argument("--no-fallback-v1", action="store_true")
    args = parser.parse_args()

    routes: dict[str, ChannelRoute] = {"v1": ChannelRoute(name="v1", kind="v1")}
    if args.persistent_pool_url:
        routes["default"] = ChannelRoute(name="default", kind="persistent", url=args.persistent_pool_url)
    else:
        routes["default"] = routes["v1"]

    client = RpcBridgeV2Client(
        routes=routes,
        retry_policy=RetryPolicy(max_attempts=args.max_attempts, initial_backoff_s=args.initial_backoff_s),
        fallback_v1=not args.no_fallback_v1,
    )
    result = client.call(
        RpcBridgeV2Request(
            run_id=args.run_id,
            channel=args.channel,
            tenant_id=args.tenant_id,
            timeout_s=args.timeout,
        )
    )
    receipt = write_receipt(result)
    print(f"rpc-bridge-v2: {result.status.upper()} channel={result.selected_channel} run_id={result.run_id}")
    print(f"attempts={result.stats.attempts} retries={result.stats.retries} fallback_used={result.fallback_used}")
    print(f"receipt={receipt}")
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
