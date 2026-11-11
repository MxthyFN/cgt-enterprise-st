"""
analysis.py
===========
Password-pattern analysis utilities.

These functions turn raw candidates and simulation results into the insights
CIPHERHOUND reports: complexity scoring, predictable-substitution detection,
repeated-sequence detection, pattern diversity, and category distribution.

All analysis is statistical / structural. It never stores or echoes real
secrets and operates only on the synthetic candidates produced locally.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from .engine import LEET_MAP

_LEET_VALUES = set(LEET_MAP.values())
_REPEAT_RE = re.compile(r"(.+?)\1{2,}")           # xyxyxy / aaaa
_SEQ_DIGITS_RE = re.compile(r"\d{3,}")


def shannon_entropy(text: str) -> float:
    """Shannon entropy (bits) of the character distribution of ``text``."""
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def charset_size(text: str) -> int:
    """Approximate the character-space a password draws from."""
    size = 0
    if any(c.islower() for c in text):
        size += 26
    if any(c.isupper() for c in text):
        size += 26
    if any(c.isdigit() for c in text):
        size += 10
    if any(not c.isalnum() for c in text):
        size += 32
    return size or 1


def estimated_bits(text: str) -> float:
    """Rough brute-force strength estimate: log2(charset ** length)."""
    return len(text) * math.log2(charset_size(text))


def complexity_score(text: str) -> Tuple[int, str]:
    """
    Return ``(score_0_100, label)`` summarizing password complexity.

    Combines length, character-class diversity, and estimated strength, then
    penalizes obvious predictability (leet, repeats, digit runs).
    """
    if not text:
        return 0, "empty"

    length = len(text)
    classes = sum([
        any(c.islower() for c in text),
        any(c.isupper() for c in text),
        any(c.isdigit() for c in text),
        any(not c.isalnum() for c in text),
    ])

    score = 0.0
    score += min(length, 16) / 16 * 45          # length up to 45 pts
    score += (classes / 4) * 30                 # class diversity up to 30 pts
    score += min(estimated_bits(text), 80) / 80 * 25   # strength up to 25 pts

    # Predictability penalties.
    if has_leet(text):
        score -= 6
    if has_repeat(text):
        score -= 10
    if _SEQ_DIGITS_RE.search(text):
        score -= 6

    score = max(0, min(100, int(round(score))))
    return score, _complexity_label(score)


def _complexity_label(score: int) -> str:
    if score < 20:
        return "very weak"
    if score < 40:
        return "weak"
    if score < 60:
        return "moderate"
    if score < 80:
        return "strong"
    return "very strong"


def has_leet(text: str) -> bool:
    """Detect predictable leet substitutions (letters swapped for symbols)."""
    return any(c in _LEET_VALUES for c in text) and any(c.isalpha() for c in text)


def has_repeat(text: str) -> bool:
    """Detect repeated sub-sequences (aaaa, abcabcabc)."""
    return bool(_REPEAT_RE.search(text))


def repeated_digit_runs(text: str) -> List[str]:
    """Return digit runs of length >= 3 (predictable number sequences)."""
    return _SEQ_DIGITS_RE.findall(text)


@dataclass
class PatternReport:
    """Aggregate analysis across a set of candidates."""

    sample_size: int = 0
    category_distribution: Dict[str, int] = field(default_factory=dict)
    complexity_histogram: Dict[str, int] = field(default_factory=dict)
    avg_complexity: float = 0.0
    avg_length: float = 0.0
    predictable_substitution_pct: float = 0.0
    repeated_sequence_pct: float = 0.0
    digit_run_pct: float = 0.0
    pattern_diversity: float = 0.0
    unique_lengths: int = 0

    def to_dict(self) -> Dict:
        return {
            "sample_size": self.sample_size,
            "category_distribution": self.category_distribution,
            "complexity_histogram": self.complexity_histogram,
            "avg_complexity": round(self.avg_complexity, 2),
            "avg_length": round(self.avg_length, 2),
            "predictable_substitution_pct": round(self.predictable_substitution_pct, 2),
            "repeated_sequence_pct": round(self.repeated_sequence_pct, 2),
            "digit_run_pct": round(self.digit_run_pct, 2),
            "pattern_diversity": round(self.pattern_diversity, 3),
            "unique_lengths": self.unique_lengths,
        }


def analyze_candidates(candidates: Iterable[Tuple[str, str]],
                       max_sample: int = 20_000) -> PatternReport:
    """
    Build a PatternReport from ``(candidate, category)`` pairs.

    For performance on 100k sets we sample up to ``max_sample`` candidates for
    the per-string metrics while category distribution uses the full stream.
    """
    report = PatternReport()
    category_counter: Counter = Counter()
    complexity_bins: Counter = Counter()
    lengths: set[int] = set()

    total_complexity = 0.0
    total_length = 0
    leet_count = 0
    repeat_count = 0
    digit_run_count = 0
    sampled = 0

    for i, (cand, category) in enumerate(candidates):
        category_counter[category] += 1
        if sampled < max_sample:
            sampled += 1
            score, label = complexity_score(cand)
            complexity_bins[label] += 1
            total_complexity += score
            total_length += len(cand)
            lengths.add(len(cand))
            if has_leet(cand):
                leet_count += 1
            if has_repeat(cand):
                repeat_count += 1
            if repeated_digit_runs(cand):
                digit_run_count += 1

    report.sample_size = sampled
    report.category_distribution = dict(category_counter)
    report.complexity_histogram = dict(complexity_bins)
    if sampled:
        report.avg_complexity = total_complexity / sampled
        report.avg_length = total_length / sampled
        report.predictable_substitution_pct = leet_count / sampled * 100
        report.repeated_sequence_pct = repeat_count / sampled * 100
        report.digit_run_pct = digit_run_count / sampled * 100
    report.unique_lengths = len(lengths)
    # Pattern diversity = normalized Shannon entropy over category distribution.
    report.pattern_diversity = _distribution_entropy(category_counter)
    return report


def _distribution_entropy(counter: Counter) -> float:
    """Normalized entropy (0..1) of a category distribution - 'pattern diversity'."""
    total = sum(counter.values())
    if total == 0 or len(counter) <= 1:
        return 0.0
    probs = [c / total for c in counter.values()]
    ent = -sum(p * math.log2(p) for p in probs)
    return ent / math.log2(len(counter))


def security_recommendations(report: PatternReport,
                             match_categories: Dict[str, int]) -> List[str]:
    """Generate human-readable, defensive security recommendations."""
    recs: List[str] = []

    if report.avg_complexity < 50:
        recs.append(
            "Average candidate complexity is low; enforce a minimum length of "
            "14+ characters with mixed character classes.")
    if report.predictable_substitution_pct > 15:
        recs.append(
            "High rate of predictable 'leet' substitutions (e.g. a->@, o->0). "
            "These add negligible strength; block dictionary words regardless "
            "of substitution.")
    if report.repeated_sequence_pct > 10:
        recs.append(
            "Repeated sequences detected (e.g. 'aaaa', 'abcabc'). Reject "
            "passwords containing 3+ repeated units.")
    if report.digit_run_pct > 20:
        recs.append(
            "Frequent digit runs (1234, 2024). Disallow sequential or "
            "year-based numeric suffixes.")

    if match_categories:
        top = sorted(match_categories.items(), key=lambda kv: kv[1], reverse=True)
        habit = top[0][0].replace("_", " ")
        recs.append(
            f"Simulated matches were dominated by the '{habit}' habit; target "
            "user education and password-policy rules at this pattern first.")

    recs.append(
        "Adopt a passphrase policy, enforce a breached-password blocklist, and "
        "require MFA so that predictable patterns cannot be used alone.")
    recs.append(
        "Deploy rate limiting and account lockout so that high-volume guessing "
        "(as simulated here) is infeasible against real systems.")
    return recs
