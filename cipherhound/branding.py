"""
branding.py
===========
Terminal aesthetics for CIPHERHOUND: ANSI color palette, ASCII art, the
typewriter/animation helpers, and the multi-stage startup sequence.

Everything here is pure standard library so the tool runs anywhere with zero
installation. Colors degrade gracefully when the output stream is not a TTY or
when the operator requests a no-color / no-animation run.
"""

from __future__ import annotations

import os
import sys
import time

from . import __app_name__, __company__, __tagline__, __version__

# ---------------------------------------------------------------------------
# Color handling
# ---------------------------------------------------------------------------


class Palette:
    """ANSI color codes. Green/white primary with subtle red accents."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Primary palette
    GREEN = "\033[38;5;46m"       # bright matrix green
    GREEN_DIM = "\033[38;5;28m"   # darker green
    WHITE = "\033[38;5;255m"
    GRAY = "\033[38;5;244m"       # unsuccessful / muted candidates
    RED = "\033[38;5;196m"        # subtle red accents / alerts
    AMBER = "\033[38;5;214m"
    CYAN = "\033[38;5;51m"


def _supports_color(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CIPHERHOUND_NOCOLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class Theme:
    """
    Wraps the palette and respects runtime preferences.

    When ``color`` is False every styling helper returns the raw text, which is
    what we want for log files, piped output, and automated tests.
    """

    def __init__(self, color: bool | None = None, animate: bool | None = None,
                 stream=None):
        self.stream = stream or sys.stdout
        self.color = _supports_color(self.stream) if color is None else color
        # Animations only make sense on an interactive terminal.
        self.animate = self.color if animate is None else animate

    def style(self, text: str, *codes: str) -> str:
        if not self.color or not codes:
            return text
        return "".join(codes) + text + Palette.RESET

    def green(self, t: str) -> str:
        return self.style(t, Palette.GREEN)

    def green_dim(self, t: str) -> str:
        return self.style(t, Palette.GREEN_DIM)

    def white(self, t: str) -> str:
        return self.style(t, Palette.WHITE)

    def gray(self, t: str) -> str:
        return self.style(t, Palette.GRAY)

    def red(self, t: str) -> str:
        return self.style(t, Palette.RED)

    def amber(self, t: str) -> str:
        return self.style(t, Palette.AMBER)

    def cyan(self, t: str) -> str:
        return self.style(t, Palette.CYAN)

    def bold(self, t: str) -> str:
        return self.style(t, Palette.BOLD)

    # -- animation helpers --------------------------------------------------

    def write(self, text: str = "", end: str = "\n") -> None:
        self.stream.write(text + end)
        self.stream.flush()

    def typewriter(self, text: str, delay: float = 0.004, end: str = "\n") -> None:
        """Print ``text`` one character at a time for a terminal feel."""
        if not self.animate:
            self.write(text, end=end)
            return
        for ch in text:
            self.stream.write(ch)
            self.stream.flush()
            time.sleep(delay)
        self.stream.write(end)
        self.stream.flush()

    def pause(self, seconds: float) -> None:
        if self.animate:
            time.sleep(seconds)


# ---------------------------------------------------------------------------
# ASCII art
# ---------------------------------------------------------------------------

LOGO = r"""
   ____ ___ ____  _   _ _____ ____  _   _  ___  _   _ _   _ ____
  / ___|_ _|  _ \| | | | ____|  _ \| | | |/ _ \| | | | \ | |  _ \
 | |    | || |_) | |_| |  _| | |_) | |_| | | | | | | |  \| | | | |
 | |___ | ||  __/|  _  | |___|  _ <|  _  | |_| | |_| | |\  | |_| |
  \____|___|_|   |_| |_|_____|_| \_\_| |_|\___/ \___/|_| \_|____/
"""

COMPANY_BANNER = r"""
  ____ ____ _____   _____ _   _ _____ _____ ____  ____  ____  ___ ____  _____ ____
 / ___/ ___|_   _| | ____| \ | |_   _| ____|  _ \|  _ \|  _ \|_ _/ ___|| ____/ ___|
| |  | |  _  | |   |  _| |  \| | | | |  _| | |_) | |_) | |_) || |\___ \|  _| \___ \
| |__| |_| | | |   | |___| |\  | | | | |___|  _ <|  __/|  _ < | | ___) | |___ ___) |
 \____\____| |_|   |_____|_| \_| |_| |_____|_| \_\_|   |_| \_\___|____/|_____|____/
"""


def _frame(theme: Theme, width: int = 72) -> str:
    return theme.green_dim("+" + "-" * (width - 2) + "+")


# ---------------------------------------------------------------------------
# Startup sequence
# ---------------------------------------------------------------------------

_BOOT_STAGES = [
    ("Core system", "Bootstrapping kernel services", "online"),
    ("Security module", "Loading synthetic sandbox + guardrails", "armed"),
    ("Generation engine", "Spinning up pattern synthesis cores", "ready"),
    ("Testing engine", "Initializing local authentication simulator", "ready"),
    ("Research logger", "Mounting local research-log store", "ready"),
]


def startup_sequence(theme: Theme) -> None:
    """Render the animated CIPHERHOUND / CGT Enterprises boot screen."""
    theme.write()
    for line in LOGO.splitlines():
        theme.write(theme.green(line))
    theme.pause(0.15)

    for line in COMPANY_BANNER.splitlines():
        theme.write(theme.white(line))

    theme.write()
    theme.write(_frame(theme))
    title = f"{__app_name__} v{__version__}  ::  {__tagline__}"
    theme.write(theme.green_dim("|  ") + theme.bold(theme.green(title)))
    theme.write(theme.green_dim("|  ") + theme.white(f"An internal research platform by {__company__}"))
    theme.write(_frame(theme))
    theme.write()

    theme.typewriter(theme.cyan(">> Initializing secure research environment..."), delay=0.006)
    theme.pause(0.2)

    for name, desc, status in _BOOT_STAGES:
        label = f"  [ {name:<18} ] "
        theme.stream.write(theme.green_dim(label) + theme.gray(desc))
        theme.stream.flush()
        # progressive dots
        for _ in range(3):
            theme.pause(0.12)
            if theme.animate:
                theme.stream.write(theme.gray("."))
                theme.stream.flush()
        tag = theme.green(f"  [{status.upper()}]")
        theme.stream.write(tag + "\n")
        theme.stream.flush()

    theme.write()
    theme.write(_frame(theme))
    ready = "  SYSTEM READY  ::  All research modules online"
    theme.write(theme.green_dim("|") + theme.bold(theme.green(ready)))
    theme.write(_frame(theme))
    theme.write()

    # Authorization / safety banner (subtle red accent).
    theme.write(theme.red("  * AUTHORIZED USE ONLY *") + theme.gray(
        "  Local, offline, synthetic-data research sandbox."))
    theme.write(theme.gray(
        "  No external systems are contacted. No real credentials are collected."))
    theme.write()


def section(theme: Theme, title: str) -> None:
    """Print a consistent section header used throughout the app."""
    bar = "=" * max(4, 60 - len(title))
    theme.write()
    theme.write(theme.green_dim("== ") + theme.bold(theme.green(title.upper())) +
                " " + theme.green_dim(bar))
