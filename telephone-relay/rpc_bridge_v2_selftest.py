#!/usr/bin/env python3
"""Fast self-test for rpc_bridge_v2 channel routing, retry/backoff, and stats."""

from __future__ import annotations

import json
from pathlib import Path

from rpc_bridge_v2 import ChannelRoute, RetryPolicy, RpcBridgeV2Client, RpcBridgeV2Request, write_receipt

ROOT = Path(__file__).resolve().parent


def test_retry_then_success() -> dict[str, object]:
    calls = {"count": 0}
    slept: list[float] = []

    def persistent_transport(route: ChannelRoute, request: RpcBridgeV2Request) -> dict[str, object]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("synthetic transient failure")
        return {"status": "passed", "run_id": request.run_id, "channel": route.name}

    client = RpcBridgeV2Client(
        routes={"default": ChannelRoute(name="default", kind="persistent", url="http://example.invalid")},
        retry_policy=RetryPolicy(max_attempts=2, initial_backoff_s=0.01),
        fallback_v1=False,
        sleep_fn=slept.append,
        persistent_transport=persistent_transport,
    )
    result = client.call(RpcBridgeV2Request(run_id="selftest-retry"))
    assert result.status == "passed"
    assert result.selected_channel == "default"
    assert result.stats.attempts == 2
    assert result.stats.retries == 1
    assert len(slept) == 1
    return {"name": "retry_then_success", "status": "passed", "attempts": result.stats.attempts, "retries": result.stats.retries}


def test_persistent_to_v1_fallback() -> dict[str, object]:
    slept: list[float] = []

    def persistent_transport(route: ChannelRoute, request: RpcBridgeV2Request) -> dict[str, object]:
        return {"status": "failed", "error": "synthetic persistent failure"}

    def v1_transport(route: ChannelRoute, request: RpcBridgeV2Request) -> dict[str, object]:
        return {"status": "passed", "run_id": request.run_id, "selected_mode": "direct"}

    client = RpcBridgeV2Client(
        routes={
            "default": ChannelRoute(name="default", kind="persistent", url="http://example.invalid"),
            "v1": ChannelRoute(name="v1", kind="v1"),
        },
        retry_policy=RetryPolicy(max_attempts=1, initial_backoff_s=0.01),
        fallback_v1=True,
        sleep_fn=slept.append,
        persistent_transport=persistent_transport,
        v1_transport=v1_transport,
    )
    result = client.call(RpcBridgeV2Request(run_id="selftest-fallback"))
    assert result.status == "passed"
    assert result.selected_channel == "v1"
    assert result.fallback_used is True
    assert result.stats.attempts == 2
    assert result.stats.failures == 1
    assert result.stats.successes == 1
    receipt = write_receipt(result)
    assert receipt.exists()
    return {"name": "persistent_to_v1_fallback", "status": "passed", "receipt": str(receipt)}


def test_retry_policy_clamps_negative_delay() -> dict[str, object]:
    policy = RetryPolicy(initial_backoff_s=-1.0, max_backoff_s=-2.0)
    assert policy.delay_for_retry(1) == 0.0
    return {"name": "retry_policy_clamps_negative_delay", "status": "passed"}


def main() -> int:
    results = [test_retry_then_success(), test_persistent_to_v1_fallback(), test_retry_policy_clamps_negative_delay()]
    out_dir = ROOT / "diagnostics" / "rpc-bridge-v2-selftest"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rpc-bridge-v2-selftest.json").write_text(json.dumps({"status": "passed", "tests": results}, indent=2), encoding="utf-8")
    print("rpc-bridge-v2-selftest: PASS")
    for item in results:
        print(f"- {item['name']}: {item['status']}")
    print(f"receipt={out_dir / 'rpc-bridge-v2-selftest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
