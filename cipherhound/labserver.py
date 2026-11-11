"""
labserver.py
============
A tiny, local **lab authentication server** for CIPHERHOUND.

It exists so the operator can exercise the "connect to an IP and test the
login" workflow end to end against a sandbox **they run themselves** - never a
third-party system. It:

* binds to a **loopback address only** (127.0.0.1 / ::1); any other bind host
  is refused,
* builds synthetic accounts (salted-hash stored; no plaintext retained),
* speaks the simple line protocol the ``netsim`` client expects.

Run it in one terminal:

    python -m cipherhound.labserver --port 9099 --accounts 8 --seed 1

...then, in another terminal, point a CIPHERHOUND session at 127.0.0.1:9099.

This is a research sandbox. It is intentionally minimal and must not be exposed
to any non-loopback interface.
"""

from __future__ import annotations

import argparse
import ipaddress
import socketserver
import sys
from typing import Dict, Tuple

from .collector import SessionConfig, demo_config
from .netsim import TargetRefused
from .simulator import AuthSimulator, _hash

# username -> (salt, password_hash)
AccountMap = Dict[str, Tuple[bytes, str]]


def _assert_loopback_bind(host: str) -> str:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise TargetRefused(
            f"Refused to bind to '{host}': the lab server binds to a loopback "
            "IP only (127.0.0.1 or ::1).")
    if not ip.is_loopback:
        raise TargetRefused(
            f"Refused to bind to {ip}: the lab server binds to loopback only. "
            "Exposing it on another interface is not permitted.")
    return str(ip)


def build_account_map(config: SessionConfig, num_accounts: int = 8,
                      seed: int | None = None) -> AccountMap:
    """Build synthetic accounts and return a username -> (salt, hash) map."""
    sim = AuthSimulator(seed=seed)
    sim.build_synthetic_accounts(config, num_accounts=num_accounts)
    return {a.username: (a.salt, a.password_hash) for a in sim.accounts}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        accounts: AccountMap = self.server.accounts  # type: ignore[attr-defined]
        for raw in self.rfile:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            parts = line.split("\t")
            cmd = parts[0].upper()
            if cmd == "USERS":
                self.wfile.write((",".join(accounts) + "\n").encode("utf-8"))
            elif cmd == "AUTH" and len(parts) == 3:
                _user, password = parts[1], parts[2]
                entry = accounts.get(_user)
                ok = entry is not None and _hash(password, entry[0]) == entry[1]
                self.wfile.write(b"OK\n" if ok else b"FAIL\n")
            elif cmd == "QUIT":
                break
            else:
                self.wfile.write(b"ERR\n")


class LabAuthServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, accounts: AccountMap):
        host = _assert_loopback_bind(host)
        super().__init__((host, port), _Handler)
        self.accounts = accounts


def create_server(host: str = "127.0.0.1", port: int = 0,
                  config: SessionConfig | None = None,
                  num_accounts: int = 8,
                  seed: int | None = None) -> LabAuthServer:
    """Factory used by both the CLI and the test suite."""
    cfg = config or demo_config()
    accounts = build_account_map(cfg, num_accounts=num_accounts, seed=seed)
    return LabAuthServer(host, port, accounts)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="cipherhound.labserver",
        description="CIPHERHOUND local lab authentication server "
                    "(loopback-only, synthetic accounts).")
    p.add_argument("--host", default="127.0.0.1",
                   help="Loopback bind address (default 127.0.0.1).")
    p.add_argument("--port", type=int, default=9099, help="Port (default 9099).")
    p.add_argument("--accounts", type=int, default=8,
                   help="Number of synthetic accounts (default 8).")
    p.add_argument("--seed", type=int, default=None,
                   help="Deterministic RNG seed for reproducible accounts.")
    args = p.parse_args(argv)

    try:
        server = create_server(host=args.host, port=args.port,
                               num_accounts=args.accounts, seed=args.seed)
    except TargetRefused as exc:
        print(f"[labserver] {exc}", file=sys.stderr)
        return 2

    host, port = server.server_address[0], server.server_address[1]
    print("=" * 64)
    print(" CIPHERHOUND LAB AUTH SERVER  ::  AUTHORIZED SECURITY RESEARCH")
    print(f" Listening on {host}:{port}  (loopback-only, synthetic accounts)")
    print(f" Synthetic accounts: {', '.join(server.accounts)}")
    print(" Point a CIPHERHOUND session here, e.g.:")
    print(f"   python -m cipherhound --lab-target {host} --lab-port {port} --lab-confirm")
    print(" Press Ctrl+C to stop.")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[labserver] shutting down.")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
