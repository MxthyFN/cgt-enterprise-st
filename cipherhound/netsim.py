"""
netsim.py
=========
Loopback-only "live target" client for CIPHERHOUND.

This module lets the operator run generated candidates against a *local lab
authentication server* (see ``cipherhound/labserver.py``) over a real TCP
socket - giving the full "enter an IP, connect, and test the login" workflow.

HARD SAFETY BOUNDARY
--------------------
Targets are restricted to **loopback IP addresses only** (``127.0.0.0/8`` and
``::1``). Domains and remote / public / private-LAN IPs are refused outright.
This keeps the feature to a sandbox the operator runs on their own machine and
makes it impossible to point CIPHERHOUND at a system it does not control.

Authorization confirmation is enforced separately at the UI/CLI layer; this
module additionally re-validates the target before every connection.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from typing import Iterable, List, Optional, Tuple

from .simulator import MatchRecord, SimulationResult


class TargetRefused(Exception):
    """Raised when a requested target is not an allowed loopback IP."""


def validate_loopback_target(host: str) -> str:
    """
    Return the normalized loopback IP for ``host`` or raise ``TargetRefused``.

    Only literal loopback IP addresses are accepted. Domains (anything that is
    not an IP literal) and non-loopback IPs are rejected - by design.
    """
    host = (host or "").strip()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise TargetRefused(
            f"'{host}' is not an IP address. CIPHERHOUND accepts loopback IPs "
            "only (e.g. 127.0.0.1 or ::1), never domains or remote hosts.")
    if not ip.is_loopback:
        raise TargetRefused(
            f"Refused: {ip} is not a loopback address. CIPHERHOUND only tests "
            "local lab targets you run yourself (127.0.0.0/8 or ::1). Remote, "
            "public, and LAN addresses are not permitted.")
    return str(ip)


class NetworkTargetSimulator:
    """
    Tests candidates against a loopback lab auth server over TCP.

    Protocol (line-based, UTF-8):
        -> ``USERS``                       <- ``user1,user2,...``
        -> ``AUTH\\t<user>\\t<password>``  <- ``OK`` | ``FAIL`` | ``ERR``
        -> ``QUIT``
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        # Re-validate at construction: no NetworkTargetSimulator can exist for
        # a non-loopback target.
        self.host = validate_loopback_target(host)
        self.port = int(port)
        self.timeout = timeout

    # -- low-level ----------------------------------------------------------

    def _connect(self) -> socket.socket:
        return socket.create_connection((self.host, self.port),
                                        timeout=self.timeout)

    def ping(self) -> bool:
        """Return True if the lab server is reachable."""
        try:
            with self._connect():
                return True
        except OSError:
            return False

    def fetch_users(self) -> List[str]:
        with self._connect() as s:
            rfile = s.makefile("rb")
            wfile = s.makefile("wb", buffering=0)
            wfile.write(b"USERS\n")
            line = rfile.readline().decode("utf-8", "replace").strip()
            return [u for u in line.split(",") if u]

    # -- the run ------------------------------------------------------------

    def run(self, candidates: Iterable[Tuple[str, str]],
            usernames: Optional[List[str]] = None,
            progress=None) -> SimulationResult:
        """
        Attempt ``(candidate, category)`` logins against the lab server.

        Each username is attacked until the first successful candidate; matched
        accounts are dropped from the active set. Returns a SimulationResult,
        the same shape produced by the offline simulator.
        """
        users = usernames if usernames is not None else self.fetch_users()
        result = SimulationResult(accounts_total=len(users))
        active = set(users)
        category_counter: dict[str, int] = {}
        start = time.perf_counter()
        evaluated = 0

        with self._connect() as s:
            rfile = s.makefile("rb")
            wfile = s.makefile("wb", buffering=0)

            for cand, cand_category in candidates:
                if not active:
                    break
                evaluated += 1
                matched = []
                for user in list(active):
                    wfile.write(f"AUTH\t{user}\t{cand}\n".encode("utf-8"))
                    resp = rfile.readline().decode("utf-8", "replace").strip()
                    if resp == "OK":
                        matched.append(user)
                        result.matches.append(MatchRecord(
                            username=user, candidate=cand,
                            category=cand_category, complexity=0,
                            attempts_to_match=evaluated))
                        category_counter[cand_category] = \
                            category_counter.get(cand_category, 0) + 1
                for user in matched:
                    active.discard(user)

                if progress is not None and evaluated % 500 == 0:
                    result.candidates_evaluated = evaluated
                    result.accounts_cracked = len(result.matches)
                    result.elapsed_seconds = time.perf_counter() - start
                    result.match_categories = dict(category_counter)
                    progress(result)

            try:
                wfile.write(b"QUIT\n")
            except OSError:
                pass

        result.candidates_evaluated = evaluated
        result.accounts_cracked = len(result.matches)
        result.match_categories = dict(category_counter)
        result.elapsed_seconds = time.perf_counter() - start
        if progress is not None:
            progress(result)
        return result
