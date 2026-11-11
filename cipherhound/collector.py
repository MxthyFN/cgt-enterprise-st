"""
collector.py
============
Interactive collection of *fictional* research inputs, plus the SessionConfig
data model that drives the rest of the pipeline.

Design notes
------------
* Every question is optional and clearly marked skippable.
* We only ever collect synthetic / fictional data (favorite colors, fake
  birthdays, fictional names, etc.). The prompts actively steer the operator
  away from real credentials or real personal data.
* A non-interactive ``demo`` configuration is provided so the whole platform
  can be exercised headlessly (CI, automated tests, scripted demos).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List

from .branding import Theme, section


# Order matters: this list defines the interactive questionnaire as well as the
# categories reported in analysis and logs. ``key`` is the SessionConfig field.
PATTERN_QUESTIONS: List[Dict[str, str]] = [
    {"key": "colors", "label": "Favorite colors", "eg": "crimson, teal, onyx"},
    {"key": "teams", "label": "Favorite sports teams", "eg": "ravens, lakers"},
    {"key": "numbers", "label": "Favorite / lucky numbers", "eg": "7, 13, 42"},
    {"key": "number_combos", "label": "Existing number combinations", "eg": "1234, 2020, 007"},
    {"key": "birthdays", "label": "Fictional birthdays (DD/MM or MMDDYYYY)", "eg": "0101, 12251990"},
    {"key": "names", "label": "Fictional names", "eg": "orion, nova, atlas"},
    {"key": "words", "label": "Common words", "eg": "dragon, shadow, vault"},
    {"key": "years", "label": "Years and dates", "eg": "1999, 2024"},
    {"key": "specials", "label": "Special characters", "eg": "!, @, #, $"},
    {"key": "capitalizations", "label": "Common capitalization patterns",
     "eg": "Title, UPPER, aLt"},
]


@dataclass
class SessionConfig:
    """Everything a research session needs, all fictional/synthetic."""

    target_label: str = "synthetic-target"
    usernames: List[str] = field(default_factory=list)

    colors: List[str] = field(default_factory=list)
    teams: List[str] = field(default_factory=list)
    numbers: List[str] = field(default_factory=list)
    number_combos: List[str] = field(default_factory=list)
    birthdays: List[str] = field(default_factory=list)
    names: List[str] = field(default_factory=list)
    words: List[str] = field(default_factory=list)
    years: List[str] = field(default_factory=list)
    specials: List[str] = field(default_factory=list)
    capitalizations: List[str] = field(default_factory=list)
    custom: List[str] = field(default_factory=list)

    target_count: int = 100_000

    # -- helpers ------------------------------------------------------------

    def pattern_fields(self) -> Dict[str, List[str]]:
        """Return the pattern input categories (excludes meta fields)."""
        keys = [q["key"] for q in PATTERN_QUESTIONS] + ["custom"]
        return {k: getattr(self, k) for k in keys}

    def input_summary(self) -> Dict[str, int]:
        """How many seed tokens were supplied per category."""
        summary = {k: len(v) for k, v in self.pattern_fields().items()}
        summary["usernames"] = len(self.usernames)
        return summary

    def total_seed_tokens(self) -> int:
        return sum(len(v) for v in self.pattern_fields().values())

    def to_dict(self) -> Dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Input parsing helpers
# ---------------------------------------------------------------------------


def _split(raw: str) -> List[str]:
    """Split a comma/space separated answer into clean tokens."""
    if not raw:
        return []
    tokens: List[str] = []
    for chunk in raw.replace(";", ",").split(","):
        for piece in chunk.split():
            piece = piece.strip()
            if piece:
                tokens.append(piece)
    # de-duplicate, preserve order
    seen = set()
    out = []
    for t in tokens:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# Interactive collection
# ---------------------------------------------------------------------------


def _ask(theme: Theme, prompt: str, example: str = "", optional: bool = True) -> str:
    hint = theme.gray(f"  (e.g. {example})") if example else ""
    tag = theme.green_dim(" [optional, Enter to skip]") if optional else theme.red(" [required]")
    theme.write(theme.green("  ? ") + theme.white(prompt) + tag + hint)
    try:
        return input(theme.green_dim("    > ")).strip()
    except (EOFError, KeyboardInterrupt):
        theme.write()
        return ""


def collect_interactive(theme: Theme) -> SessionConfig:
    """Run the full questionnaire and return a populated SessionConfig."""
    cfg = SessionConfig()

    section(theme, "New Research Session")
    theme.write(theme.gray(
        "  Provide SYNTHETIC/FICTIONAL inputs only. Do not enter real passwords,\n"
        "  real personal data, or real account credentials."))
    theme.write()

    # Target label (optional but recommended).
    label = _ask(theme, "Website / application name to label this simulation",
                 example="acme-portal", optional=True)
    if label:
        cfg.target_label = label

    # Synthetic usernames / identities.
    users = _ask(theme, "Synthetic username / email examples (test identities only)",
                 example="test.user@example.test, operator01", optional=True)
    cfg.usernames = _split(users)

    section(theme, "Password-Pattern Inputs")
    theme.write(theme.gray("  All fields are optional. Separate multiple values with commas."))
    theme.write()

    for q in PATTERN_QUESTIONS:
        raw = _ask(theme, q["label"], example=q["eg"], optional=True)
        setattr(cfg, q["key"], _split(raw))

    # Additional custom patterns.
    section(theme, "Custom Patterns")
    custom = _ask(theme, "Any additional custom test patterns / tokens",
                  example="projectx, qa-seed-2024", optional=True)
    cfg.custom = _split(custom)

    # Target volume.
    section(theme, "Engine Configuration")
    raw_count = _ask(theme,
                     "Target number of candidates to generate",
                     example="100000 (default)", optional=True)
    if raw_count:
        try:
            cfg.target_count = max(1000, int(raw_count.replace(",", "").replace("_", "")))
        except ValueError:
            theme.write(theme.red("    ! Not a number; using default 100,000."))

    # Guarantee the engine has *something* to work with even if the operator
    # skipped everything, so the platform always produces a meaningful session.
    if cfg.total_seed_tokens() == 0:
        theme.write(theme.amber(
            "    (No seeds supplied - loading a neutral synthetic starter set.)"))
        _apply_starter_seeds(cfg)

    return cfg


def _apply_starter_seeds(cfg: SessionConfig) -> None:
    """Neutral synthetic fallback so a skipped questionnaire still runs."""
    cfg.colors = cfg.colors or ["red", "blue", "green", "black"]
    cfg.words = cfg.words or ["dragon", "shadow", "vault", "cipher"]
    cfg.names = cfg.names or ["nova", "atlas", "orion"]
    cfg.numbers = cfg.numbers or ["1", "7", "13"]
    cfg.number_combos = cfg.number_combos or ["123", "1234", "2020"]
    cfg.years = cfg.years or ["1999", "2024"]
    cfg.specials = cfg.specials or ["!", "@", "#"]
    cfg.capitalizations = cfg.capitalizations or ["Title", "UPPER"]


# ---------------------------------------------------------------------------
# Non-interactive demo configuration
# ---------------------------------------------------------------------------


def demo_config(target_label: str = "acme-demo-portal",
                target_count: int = 100_000) -> SessionConfig:
    """A fully synthetic configuration used for demos, CI, and tests."""
    return SessionConfig(
        target_label=target_label,
        usernames=["test.user@example.test", "operator01", "qa.account"],
        colors=["crimson", "teal", "onyx", "silver"],
        teams=["ravens", "lakers", "rockets"],
        numbers=["7", "13", "42"],
        number_combos=["123", "1234", "2020", "007"],
        birthdays=["0101", "1225", "12251990"],
        names=["orion", "nova", "atlas", "juno"],
        words=["dragon", "shadow", "vault", "cipher", "falcon"],
        years=["1999", "2010", "2024"],
        specials=["!", "@", "#", "$"],
        capitalizations=["Title", "UPPER", "alt"],
        custom=["projectx", "qa-seed"],
        target_count=target_count,
    )
