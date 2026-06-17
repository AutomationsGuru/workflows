#!/usr/bin/env python3
"""Persistent RPC warm pool for the Telephone Relay.

Starts the RPC agents once, keeps them warm, and serves relays over localhost
HTTP. The benchmark prototype remains separate. This server persists small
logical pool state (tenants, sizes, and in-use leases) so a restart can reload
recent pool metadata with a TTL.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROTO_PATH = ROOT / "rpc-warm-pool-prototype.py"
STATE_VERSION = 1


def load_proto() -> Any:
    spec = importlib.util.spec_from_file_location("rpc_warm_pool_prototype", PROTO_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {PROTO_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


proto = load_proto()


@dataclass
class TenantState:
    tenant_id: str
    size: int
    timeout_s: int
    agent2_model: str
    run_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class PoolState:
    version: int
    saved_at: float
    expires_at: float
    tenants: dict[str, TenantState]
    sizes: dict[str, int]
    in_use: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "saved_at": self.saved_at,
            "expires_at": self.expires_at,
            "tenants": {tenant_id: asdict(state) for tenant_id, state in self.tenants.items()},
            "sizes": self.sizes,
            "in_use": self.in_use,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PoolState":
        tenants = {
            tenant_id: TenantState(**tenant_data)
            for tenant_id, tenant_data in (data.get("tenants") or {}).items()
        }
        return cls(
            version=int(data.get("version", STATE_VERSION)),
            saved_at=float(data.get("saved_at", 0)),
            expires_at=float(data.get("expires_at", 0)),
            tenants=tenants,
            sizes={str(k): int(v) for k, v in (data.get("sizes") or {}).items()},
            in_use=[str(item) for item in data.get("in_use", [])],
        )


def new_state(ttl_s: int) -> PoolState:
    now = time.time()
    return PoolState(version=STATE_VERSION, saved_at=now, expires_at=now + ttl_s, tenants={}, sizes={}, in_use=[])


def load_state(path: Path, ttl_s: int) -> tuple[PoolState, bool, str]:
    if not path.exists():
        return new_state(ttl_s), False, "missing"
    try:
        state = PoolState.from_json(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        return new_state(ttl_s), False, f"invalid: {exc}"
    now = time.time()
    if state.expires_at < now or state.saved_at + ttl_s < now:
        return new_state(ttl_s), False, "expired"
    return state, True, "loaded"


def save_state(path: Path, state: PoolState, ttl_s: int) -> None:
    now = time.time()
    state.saved_at = now
    state.expires_at = now + ttl_s
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_json(), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class PoolOverflowError(RuntimeError):
    pass


class PersistentPool:
    def __init__(
        self,
        *,
        agent2_model: str,
        timeout_s: int,
        run_root: Path,
        tenant_id: str = "default",
        pool_size: int = 1,
        state_file: Path | None = None,
        state_ttl_s: int = 300,
    ) -> None:
        self.agent2_model = agent2_model
        self.timeout_s = timeout_s
        self.run_root = run_root
        self.log_dir = run_root / "pool-logs"
        self.agents = proto.build_agents(agent2_model, timeout_s, log_dir=self.log_dir)
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.run_count = 0
        self.startup: list[Any] = []
        self.closed = False
        self.tenant_id = tenant_id
        self.pool_size = pool_size
        self.state_ttl_s = state_ttl_s
        self.state_file = state_file or (run_root / "pool-state.json")
        self.state, self.state_loaded, self.state_load_reason = load_state(self.state_file, state_ttl_s)
        self.ensure_tenant(tenant_id, pool_size, timeout_s, agent2_model)
        self.persist_state()

    def ensure_tenant(self, tenant_id: str, size: int, timeout_s: int, agent2_model: str) -> None:
        now = time.time()
        if tenant_id not in self.state.tenants:
            self.state.tenants[tenant_id] = TenantState(
                tenant_id=tenant_id,
                size=size,
                timeout_s=timeout_s,
                agent2_model=agent2_model,
                created_at=now,
                updated_at=now,
            )
        else:
            tenant = self.state.tenants[tenant_id]
            tenant.size = size
            tenant.timeout_s = timeout_s
            tenant.agent2_model = agent2_model
            tenant.updated_at = now
        self.state.sizes[tenant_id] = size

    def persist_state(self) -> None:
        with self.state_lock:
            save_state(self.state_file, self.state, self.state_ttl_s)

    def acquire(self, tenant_id: str, lease_id: str) -> None:
        with self.state_lock:
            size = self.state.sizes.get(tenant_id, self.pool_size)
            active = [item for item in self.state.in_use if item.startswith(f"{tenant_id}:")]
            if len(active) >= size:
                raise PoolOverflowError(f"tenant {tenant_id!r} pool cap reached: {len(active)}/{size}")
            if lease_id not in self.state.in_use:
                self.state.in_use.append(lease_id)
            save_state(self.state_file, self.state, self.state_ttl_s)

    def release(self, lease_id: str) -> None:
        with self.state_lock:
            self.state.in_use = [item for item in self.state.in_use if item != lease_id]
            save_state(self.state_file, self.state, self.state_ttl_s)

    def start(self) -> None:
        for agent in self.agents.values():
            self.startup.append(agent.start())

    def status(self) -> dict[str, Any]:
        return {
            "status": "warm" if not self.closed else "closed",
            "agent2_model": self.agent2_model,
            "started_at": self.started_at,
            "run_count": self.run_count,
            "pids": {name: agent.proc.pid if agent.proc else None for name, agent in self.agents.items()},
            "startup": [asdict(item) for item in self.startup],
            "state_file": str(self.state_file),
            "state_loaded": self.state_loaded,
            "state_load_reason": self.state_load_reason,
            "state_ttl_s": self.state_ttl_s,
            "tenants": {tenant_id: asdict(state) for tenant_id, state in self.state.tenants.items()},
            "sizes": self.state.sizes,
            "in_use": self.state.in_use,
        }

    def relay(self, run_id: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        tenant_id = tenant_id or self.tenant_id
        lease_id = f"{tenant_id}:{uuid.uuid4().hex}"
        with self.lock:
            if self.closed:
                raise RuntimeError("persistent pool is closed")
            self.acquire(tenant_id, lease_id)
            try:
                run_id = run_id or time.strftime("%Y%m%d-%H%M%S") + f"-{self.run_count + 1:03d}"
                run_dir = self.run_root / "runs" / run_id
                started = time.perf_counter()
                proto.reset_handoff()
                turns = [
                    self.agents["agent1"].prompt("g", "NEXT:Agent 2:g"),
                    self.agents["agent2"].prompt("g", "NEXT:Agent 3:gu"),
                    self.agents["agent3"].prompt("gu", "NEXT:Agent 2:gur"),
                    self.agents["agent2"].prompt("gur", "NEXT:Agent 1:guru"),
                    self.agents["agent1"].prompt("guru", "USER:guru — return verified."),
                ]
                agent2_output, agent3_output, agent1_output = proto.write_turn_outputs(run_dir, turns)
                final_text = proto.HANDOFF.read_text(encoding="utf-8")
                if "Current token: guru" not in final_text:
                    raise RuntimeError("final handoff did not contain Current token: guru")
                self.run_count += 1
                tenant = self.state.tenants[tenant_id]
                tenant.run_count += 1
                tenant.updated_at = time.time()
                data = {
                    "status": "passed",
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "run_count": self.run_count,
                    "pool_started_at": self.started_at,
                    "pids": {name: agent.proc.pid if agent.proc else None for name, agent in self.agents.items()},
                    "startup": [asdict(item) for item in self.startup],
                    "turns": [asdict(item) for item in turns],
                    "relay_elapsed_s": sum(turn.elapsed_s for turn in turns),
                    "total_elapsed_s": time.perf_counter() - started,
                    "agent2_output": str(agent2_output),
                    "agent3_output": str(agent3_output),
                    "agent1_output": str(agent1_output),
                }
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "persistent-pool-result.json").write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                return data
            finally:
                self.release(lease_id)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.persist_state()
        for agent in self.agents.values():
            agent.stop()


class Handler(BaseHTTPRequestHandler):
    pool: PersistentPool
    server_version = "PersistentWarmPool/0.2"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, self.pool.status())
            return
        if self.path == "/state":
            self._json(200, self.pool.state.to_json())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/relay":
            try:
                body = self._read_json()
                self._json(200, self.pool.relay(run_id=body.get("run_id"), tenant_id=body.get("tenant_id")))
            except PoolOverflowError as exc:
                self._json(429, {"status": "overflow", "error": str(exc), **self.pool.status()})
            except Exception as exc:
                self._json(500, {"status": "failed", "error": str(exc), **self.pool.status()})
            return
        if self.path == "/shutdown":
            self._json(200, {"status": "shutting_down", **self.pool.status()})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._json(404, {"error": "not found"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a persistent Telephone Relay warm pool.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--agent2-model", default="xai-oauth/grok-build-0.1")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--pool-size", type=int, default=1)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--state-ttl-s", type=int, default=300)
    args = parser.parse_args()

    run_root = ROOT / "persistent-pool-runs" / time.strftime("%Y%m%d-%H%M%S")
    pool = PersistentPool(
        agent2_model=args.agent2_model,
        timeout_s=args.timeout,
        run_root=run_root,
        tenant_id=args.tenant_id,
        pool_size=args.pool_size,
        state_file=args.state_file,
        state_ttl_s=args.state_ttl_s,
    )
    pool.start()
    Handler.pool = pool
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{server.server_port}"
    print(json.dumps({"status": "ready", "url": url, **pool.status()}), flush=True)
    try:
        server.serve_forever()
    finally:
        pool.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
