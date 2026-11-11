"""
engine.py
=========
The CIPHERHOUND password-research engine.

Given a SessionConfig of fictional seed tokens, it synthesizes large volumes of
candidate passwords (target ~100,000 per session) that mirror the *habits*
people fall into when choosing passwords:

    base token -> capitalization -> leet substitution -> affix (numbers / years
    / specials / combos) -> token pairing -> keyboard walks -> date patterns.

Each candidate is tagged with the construction category responsible for it so
downstream analysis and simulation can attribute matches to a habit.

Efficiency
----------
Candidates are produced lazily via a generator and de-duplicated with a set,
stopping as soon as ``target_count`` unique candidates are reached. This keeps
generation of 100k entries fast (well under a second) and memory bounded.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Tuple

from .collector import SessionConfig

# Candidate construction categories (stable identifiers used everywhere).
CATEGORIES = [
    "base_token",
    "capitalization",
    "leet_substitution",
    "numeric_suffix",
    "year_suffix",
    "special_suffix",
    "prefix_affix",
    "token_pair",
    "date_pattern",
    "repeated_sequence",
    "keyboard_walk",
    "custom_pattern",
]

# Classic "leet" character substitutions - predictable swaps people rely on.
LEET_MAP = {
    "a": "@", "A": "@",
    "e": "3", "E": "3",
    "i": "1", "I": "1",
    "o": "0", "O": "0",
    "s": "$", "S": "$",
    "t": "7", "T": "7",
}

# Common keyboard walks / sequences - habit patterns, not seed-derived.
KEYBOARD_WALKS = [
    "qwerty", "asdf", "zxcv", "qazwsx", "1q2w3e", "qwerty123",
    "password", "passw0rd", "letmein", "admin", "welcome", "iloveyou",
]

# Suffixes appended as "number habits" even without explicit seeds.
COMMON_NUMERIC_SUFFIXES = [
    "1", "12", "123", "1234", "12345", "0", "01", "00", "69", "007", "321",
    "111", "222", "999", "101", "100", "666", "777", "2020", "2021", "2022",
    "2023", "2024", "2025",
]


@dataclass
class GenerationStats:
    """Live-updating counters consumed by the dashboard and the logger."""

    generated: int = 0
    unique: int = 0
    duplicates: int = 0
    by_category: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in CATEGORIES})

    def record(self, category: str) -> None:
        self.generated += 1
        self.unique += 1
        self.by_category[category] = self.by_category.get(category, 0) + 1

    def record_duplicate(self) -> None:
        self.generated += 1
        self.duplicates += 1


class PasswordEngine:
    """Synthesizes categorized candidate passwords from fictional seeds."""

    def __init__(self, config: SessionConfig):
        self.config = config
        self.stats = GenerationStats()
        self._base_tokens = self._collect_base_tokens()

    # -- seed assembly ------------------------------------------------------

    def _collect_base_tokens(self) -> List[str]:
        """Flatten the word-like seed categories into unique base tokens."""
        tokens: List[str] = []
        for group in (self.config.colors, self.config.teams, self.config.names,
                      self.config.words, self.config.custom):
            tokens.extend(group)
        # Keyboard walks are always-present habit tokens.
        tokens.extend(KEYBOARD_WALKS)
        seen = set()
        unique = []
        for t in tokens:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                unique.append(t)
        return unique

    def _numeric_tokens(self) -> List[str]:
        nums = list(self.config.numbers) + list(self.config.number_combos) \
            + list(self.config.years) + list(self.config.birthdays)
        nums.extend(COMMON_NUMERIC_SUFFIXES)
        seen, out = set(), []
        for n in nums:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _special_tokens(self) -> List[str]:
        specials = list(self.config.specials) or ["!", "@", "#", "$", "1!"]
        return specials

    # -- transformation primitives ----------------------------------------

    @staticmethod
    def _capitalizations(token: str) -> Iterator[Tuple[str, str]]:
        """Yield (variant, category) capitalization forms of ``token``."""
        yield token, "base_token"
        lowered = token.lower()
        variants = {
            lowered.capitalize(),
            token.upper(),
            lowered,
        }
        # alternating caps (aLtErNaTe)
        alt = "".join(c.upper() if i % 2 else c.lower()
                      for i, c in enumerate(lowered))
        variants.add(alt)
        for v in variants:
            if v != token:
                yield v, "capitalization"

    @staticmethod
    def _leet(token: str) -> Iterator[str]:
        """Yield predictable leet-substituted forms of ``token``."""
        if not any(c in LEET_MAP for c in token):
            return
        # Full substitution.
        full = "".join(LEET_MAP.get(c, c) for c in token)
        if full != token:
            yield full
        # Vowel-only substitution (very common partial habit).
        vowel = "".join(LEET_MAP[c] if c in "aeiouAEIOU" and c in LEET_MAP else c
                        for c in token)
        if vowel != token and vowel != full:
            yield vowel

    # -- the generator ------------------------------------------------------

    def generate(self, limit: int | None = None) -> Iterator[Tuple[str, str]]:
        """
        Lazily yield unique ``(candidate, category)`` tuples until ``limit``
        (defaults to config.target_count) unique candidates are produced.

        The generator updates ``self.stats`` as it goes.
        """
        target = limit or self.config.target_count
        seen: set[str] = set()
        numeric = self._numeric_tokens()
        specials = self._special_tokens()

        def emit(candidate: str, category: str):
            """Yield candidate if new; maintain stats + dedup set."""
            if not candidate:
                return None
            if candidate in seen:
                self.stats.record_duplicate()
                return None
            seen.add(candidate)
            self.stats.record(category)
            return candidate, category

        for candidate, category in self._raw_stream(numeric, specials):
            if self.stats.unique >= target:
                break
            result = emit(candidate, category)
            if result is not None:
                yield result

    def _raw_stream(self, numeric: List[str],
                    specials: List[str]) -> Iterator[Tuple[str, str]]:
        """Undeduplicated candidate stream, ordered from most to least likely."""
        bases = self._base_tokens

        # 1. Keyboard walks & standalone habit tokens first (high realism).
        for walk in KEYBOARD_WALKS:
            yield walk, "keyboard_walk"

        # 2. Repeated sequences (aaa, 111111, abcabc) - a distinct habit.
        for base in bases[:40]:
            yield base + base, "repeated_sequence"
        for n in ("0", "1", "7", "9"):
            yield n * 6, "repeated_sequence"
            yield n * 8, "repeated_sequence"

        # 3. Date patterns from birthdays / years.
        for b in self.config.birthdays:
            for y in (self.config.years or ["2024"]):
                yield b + y, "date_pattern"
                yield y + b, "date_pattern"

        # 4. The main combinatorial body.
        #    base -> {capitalization, leet} stems -> affixes.
        #
        #    Each capitalization variant AND its leet forms become "stems" that
        #    then receive the full affix treatment (suffixes, prefixes, and
        #    number x special cross-products). This mirrors how people layer
        #    habits (Capitalize -> substitute -> append number + symbol) and
        #    gives the engine the breadth to reach ~100k combinations.
        for base in bases:
            for cap_variant, cap_cat in self._capitalizations(base):
                # Build the stem set for this capitalization variant.
                stems: List[Tuple[str, str]] = [(cap_variant, cap_cat)]
                for leet in self._leet(cap_variant):
                    stems.append((leet, "leet_substitution"))

                for stem, stem_cat in stems:
                    # 4a. the bare stem
                    yield stem, stem_cat

                    # 4b. numeric suffixes
                    for num in numeric:
                        yield stem + num, self._numeric_category(num)

                    # 4c. special-char suffixes
                    for sp in specials:
                        yield stem + sp, "special_suffix"

                    # 4d. number x special cross-products (both orders) - the
                    #     single most common "complex" password habit.
                    for num in numeric:
                        for sp in specials:
                            yield stem + num + sp, "special_suffix"
                            yield stem + sp + num, "special_suffix"

                    # 4e. prefix affixes
                    for num in numeric[:6]:
                        yield num + stem, "prefix_affix"
                    for sp in specials[:3]:
                        yield sp + stem, "prefix_affix"

        # 5. Token pairing with separators (word1word2, word1.word2, ...).
        separators = ["", ".", "_", "-", "@"]
        pair_suffixes = ["", "1", "12", "123", "2024", "!", "01", "99"]
        for a, b in itertools.permutations(bases[:32], 2):
            for sep in separators:
                pair = a + sep + b
                yield pair, "token_pair"
                yield pair.capitalize(), "token_pair"
                for suffix in pair_suffixes:
                    if suffix:
                        yield pair + suffix, "token_pair"

        # 6. Pure custom patterns (verbatim + light decoration).
        for c in self.config.custom:
            yield c, "custom_pattern"
            yield c + "123", "custom_pattern"
            yield c.capitalize() + "!", "custom_pattern"

    def _numeric_category(self, num: str) -> str:
        if num in set(self.config.years) or (len(num) == 4 and num.isdigit()
                                             and num.startswith(("19", "20"))):
            return "year_suffix"
        return "numeric_suffix"


def generate_candidates(config: SessionConfig,
                        limit: int | None = None) -> Tuple[List[Tuple[str, str]], GenerationStats]:
    """
    Convenience wrapper: fully materialize candidates into a list.

    Returns ``(candidates, stats)``. Prefer the streaming ``PasswordEngine``
    for the dashboard; this helper is handy for tests and small runs.
    """
    engine = PasswordEngine(config)
    candidates = list(engine.generate(limit=limit))
    return candidates, engine.stats
