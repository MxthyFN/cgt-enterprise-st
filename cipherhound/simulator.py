"""
simulator.py
============
A completely local, in-memory authentication simulator.

It builds synthetic accounts whose test passwords are derived from the same
fictional seed data, stores them only as salted hashes (never plaintext), and
lets the engine's candidates be tested against them offline.

CRITICAL SAFETY PROPERTIES
--------------------------
* No network sockets are opened. Nothing leaves the process.
* "Authentication" is a local salted-hash comparison, modeling how a real
  system would verify a password - purely for research insight.
* Synthetic account plaintext exists only transiently while seeding the
  simulator and is never persisted to disk or to logs.
"""

from __future__ import annotations

import hashlib
import os
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .collector import SessionConfig


def _hash(password: str, salt: bytes) -> str:
    """
    Local salted hash used by the simulator to model password verification.

    A fast salted SHA-256 is used deliberately: the research simulator must be
    able to evaluate up to ~100k candidates against many accounts offline in a
    reasonable time. Real production systems should instead use a *slow*,
    memory-hard KDF (bcrypt/scrypt/Argon2) precisely to make the high-volume
    guessing demonstrated here infeasible - this is itself a key finding the
    tool is designed to illustrate.
    """
    return hashlib.sha256(salt + password.encode("utf-8")).hexdigest()


@dataclass
class SyntheticAccount:
    username: str
    salt: bytes
    password_hash: str
    # The construction category of the seed password, kept for post-hoc
    # attribution of matches. This is metadata, not the secret itself.
    seed_category: str = "unknown"
    complexity: int = 0

    def verify(self, candidate: str) -> bool:
        return _hash(candidate, self.salt) == self.password_hash


@dataclass
class MatchRecord:
    username: str
    candidate: str
    category: str
    complexity: int
    attempts_to_match: int


@dataclass
class SimulationResult:
    candidates_evaluated: int = 0
    accounts_total: int = 0
    accounts_cracked: int = 0
    matches: List[MatchRecord] = field(default_factory=list)
    match_categories: Dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    @property
    def crack_rate(self) -> float:
        if self.accounts_total == 0:
            return 0.0
        return self.accounts_cracked / self.accounts_total * 100

    def to_dict(self) -> Dict:
        return {
            "candidates_evaluated": self.candidates_evaluated,
            "accounts_total": self.accounts_total,
            "accounts_cracked": self.accounts_cracked,
            "crack_rate_pct": round(self.crack_rate, 2),
            "match_categories": self.match_categories,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "matches": [
                {
                    "username": m.username,
                    # Note: candidate is a synthetic test value, not a real secret.
                    "candidate": m.candidate,
                    "category": m.category,
                    "complexity": m.complexity,
                    "attempts_to_match": m.attempts_to_match,
                }
                for m in self.matches
            ],
        }


class AuthSimulator:
    """Holds synthetic accounts and tests candidates against them locally."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self.accounts: List[SyntheticAccount] = []

    # -- account construction ----------------------------------------------

    def build_synthetic_accounts(self, config: SessionConfig,
                                 num_accounts: int = 8) -> None:
        """
        Create synthetic accounts with configurable test passwords.

        Passwords are drawn from a mix of weak seed-derived patterns and a few
        deliberately strong ones, so the simulation shows both easy matches and
        resilient accounts. All plaintext is discarded after hashing.
        """
        from .engine import PasswordEngine  # local import avoids cycle

        # Build a modest pool of realistic weak passwords from the seeds.
        engine = PasswordEngine(config)
        weak_pool: List[Tuple[str, str]] = []
        for cand, category in engine.generate(limit=4000):
            weak_pool.append((cand, category))
        if not weak_pool:
            weak_pool = [("password123", "keyboard_walk")]

        usernames = list(config.usernames) or [
            f"user{i:02d}" for i in range(1, num_accounts + 1)]
        # Ensure we have enough usernames.
        while len(usernames) < num_accounts:
            usernames.append(f"user{len(usernames)+1:02d}")

        self.accounts.clear()
        for i in range(num_accounts):
            username = usernames[i]
            # 75% of synthetic accounts use weak, guessable passwords; the rest
            # use a strong random password that the engine should NOT match.
            if self._rng.random() < 0.75:
                plaintext, category = self._rng.choice(weak_pool)
            else:
                plaintext, category = self._strong_password(), "strong_random"
            self._add_account(username, plaintext, category)
            # plaintext goes out of scope here; only the hash is retained.

        self._rng.shuffle(self.accounts)

    def _add_account(self, username: str, plaintext: str, category: str) -> None:
        from .analysis import complexity_score
        salt = os.urandom(16)
        score, _ = complexity_score(plaintext)
        self.accounts.append(SyntheticAccount(
            username=username,
            salt=salt,
            password_hash=_hash(plaintext, salt),
            seed_category=category,
            complexity=score,
        ))

    def _strong_password(self) -> str:
        alphabet = ("abcdefghijklmnopqrstuvwxyz"
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    "0123456789!@#$%^&*()-_=+")
        return "".join(self._rng.choice(alphabet) for _ in range(self._rng.randint(16, 22)))

    # -- testing ------------------------------------------------------------

    def run(self, candidates: Iterable[Tuple[str, str]],
            progress=None) -> SimulationResult:
        """
        Test an iterable of ``(candidate, category)`` against all accounts.

        ``progress`` is an optional callable invoked periodically with the
        running SimulationResult (used to drive the live dashboard).

        Each account is matched at most once (first successful candidate).
        """
        result = SimulationResult(accounts_total=len(self.accounts))
        start = time.perf_counter()

        # Map each live account to its index; drop from the active set on match.
        active = {idx: acct for idx, acct in enumerate(self.accounts)}
        category_counter: Dict[str, int] = {}

        evaluated = 0
        for cand, cand_category in candidates:
            if not active:
                break  # every account cracked; stop early
            evaluated += 1
            matched_idx = []
            for idx, acct in active.items():
                if acct.verify(cand):
                    matched_idx.append(idx)
                    result.matches.append(MatchRecord(
                        username=acct.username,
                        candidate=cand,
                        category=cand_category,
                        complexity=acct.complexity,
                        attempts_to_match=evaluated,
                    ))
                    category_counter[cand_category] = \
                        category_counter.get(cand_category, 0) + 1
            for idx in matched_idx:
                del active[idx]

            if progress is not None and evaluated % 2000 == 0:
                result.candidates_evaluated = evaluated
                result.accounts_cracked = len(result.matches)
                result.elapsed_seconds = time.perf_counter() - start
                result.match_categories = dict(category_counter)
                progress(result)

        result.candidates_evaluated = evaluated
        result.accounts_cracked = len(result.matches)
        result.match_categories = dict(category_counter)
        result.elapsed_seconds = time.perf_counter() - start
        if progress is not None:
            progress(result)
        return result
