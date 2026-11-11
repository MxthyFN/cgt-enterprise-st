"""
dashboard.py
============
Terminal-style live dashboard: generation counter, progress bar, candidates
evaluated, simulation match counter, pattern distribution, and session timer.

The renderer draws a multi-line frame and updates it in place using ANSI cursor
movement. When animation is disabled (non-TTY / tests) it falls back to simple
periodic status lines so nothing breaks in logs or CI.
"""

from __future__ import annotations

import shutil
import time
from typing import Dict, Optional

from .branding import Palette, Theme
from .engine import GenerationStats


def _term_width(default: int = 76) -> int:
    try:
        return min(shutil.get_terminal_size().columns, 100)
    except Exception:
        return default


def progress_bar(fraction: float, width: int, theme: Theme) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    bar = "#" * filled + "-" * (width - filled)
    pct = f"{fraction * 100:5.1f}%"
    return theme.green("[") + theme.green(bar[:filled]) + theme.gray(bar[filled:]) \
        + theme.green("] ") + theme.white(pct)


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def category_distribution(dist: Dict[str, int], theme: Theme,
                          width: int, top: int = 6) -> list[str]:
    """Render a small horizontal bar chart of the top categories."""
    lines: list[str] = []
    if not dist:
        return [theme.gray("    (no data yet)")]
    total = sum(dist.values()) or 1
    ordered = sorted(dist.items(), key=lambda kv: kv[1], reverse=True)[:top]
    label_w = max(len(k) for k, _ in ordered)
    bar_w = max(10, width - label_w - 22)
    for name, count in ordered:
        frac = count / total
        filled = int(round(frac * bar_w))
        bar = theme.green_dim("#" * filled) + theme.gray("." * (bar_w - filled))
        lines.append(
            "    " + theme.white(f"{name:<{label_w}}") + " " + bar +
            theme.gray(f" {count:>8,} ({frac*100:4.1f}%)"))
    return lines


class Dashboard:
    """Live, in-place terminal dashboard for a research session."""

    def __init__(self, theme: Theme, target_label: str, target_count: int):
        self.theme = theme
        self.target_label = target_label
        self.target_count = target_count
        self.start = time.perf_counter()
        self._lines_drawn = 0
        self._last_render = 0.0

    # -- frame construction -------------------------------------------------

    def _build_frame(self, phase: str, gen: GenerationStats,
                     evaluated: int, accounts_total: int,
                     matches: int, match_categories: Dict[str, int]) -> list[str]:
        t = self.theme
        width = _term_width()
        inner = width - 2
        elapsed = time.perf_counter() - self.start

        def row(text: str) -> str:
            return t.green_dim("|") + text

        top = t.green_dim("+" + "-" * inner + "+")
        lines = [top]

        header = f" CIPHERHOUND :: live research dashboard  "
        meta = f"target={self.target_label}  phase={phase} "
        pad = inner - len(header) - len(meta)
        lines.append(row(t.bold(t.green(header)) + t.gray(" " * max(1, pad)) +
                         t.cyan(meta)))
        lines.append(t.green_dim("|" + "-" * inner + "|"))

        # Generation stats + progress bar
        gen_frac = gen.unique / self.target_count if self.target_count else 0
        lines.append(row(t.white("  Generated   : ") +
                         t.green(_fmt_int(gen.unique)) +
                         t.gray(f" / {_fmt_int(self.target_count)} target") +
                         t.gray(f"   (dupes skipped: {_fmt_int(gen.duplicates)})")))
        lines.append(row("  " + progress_bar(gen_frac, max(20, inner - 24), t)))

        # Evaluation + matches
        lines.append(row(t.white("  Evaluated   : ") + t.green(_fmt_int(evaluated))))
        match_txt = t.green(_fmt_int(matches)) if matches else t.gray("0")
        lines.append(row(t.white("  Matches     : ") + match_txt +
                         t.gray(f" / {accounts_total} synthetic accounts")))

        rate = evaluated / elapsed if elapsed > 0 else 0
        lines.append(row(t.white("  Throughput  : ") +
                         t.gray(f"{rate:,.0f} candidates/sec")))
        lines.append(row(t.white("  Duration    : ") +
                         t.gray(f"{elapsed:6.2f}s")))

        lines.append(t.green_dim("|" + "-" * inner + "|"))
        lines.append(row(t.white("  Pattern distribution (top categories):")))
        src = match_categories if (phase in ("simulate", "target") and match_categories) \
            else gen.by_category
        for bar_line in category_distribution(
                {k: v for k, v in src.items() if v}, t, inner):
            lines.append(row(bar_line))

        lines.append(t.green_dim("+" + "-" * inner + "+"))
        return lines

    # -- rendering ----------------------------------------------------------

    def render(self, phase: str, gen: GenerationStats, evaluated: int = 0,
               accounts_total: int = 0, matches: int = 0,
               match_categories: Optional[Dict[str, int]] = None,
               force: bool = False, min_interval: float = 0.08) -> None:
        now = time.perf_counter()
        if not force and (now - self._last_render) < min_interval:
            return
        self._last_render = now

        frame = self._build_frame(phase, gen, evaluated, accounts_total,
                                   matches, match_categories or {})

        if not self.theme.animate:
            # Non-interactive: emit a compact one-line status instead of redraw.
            self.theme.write(self.theme.gray(
                f"  [{phase}] generated={gen.unique:,} evaluated={evaluated:,} "
                f"matches={matches}/{accounts_total}"))
            return

        out = self.theme.stream
        if self._lines_drawn:
            out.write(f"\033[{self._lines_drawn}A")  # cursor up
        for line in frame:
            out.write("\033[2K" + line + "\n")       # clear line + draw
        out.flush()
        self._lines_drawn = len(frame)

    def finish(self) -> None:
        """Leave the final frame in place and move the cursor below it."""
        self.theme.write()
