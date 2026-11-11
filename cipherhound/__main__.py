"""
__main__.py
===========
Command-line entry point for CIPHERHOUND.

Usage
-----
    python -m cipherhound                 # interactive research session
    python -m cipherhound --demo          # non-interactive synthetic demo
    python -m cipherhound --demo --count 100000
    python -m cipherhound --history       # show past sessions and exit

Run ``python -m cipherhound --help`` for the full option list.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __app_name__, __tagline__, __version__
from .app import run
from .branding import Theme
from .collector import collect_interactive, demo_config
from .storage import DEFAULT_LOG_DIR, load_history


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cipherhound",
        description=f"{__app_name__} - {__tagline__} (CGT Enterprises, local/offline).",
        epilog="Authorized, offline, synthetic-data research only. No external "
               "systems are ever contacted.",
    )
    p.add_argument("--demo", action="store_true",
                   help="Run a non-interactive session with synthetic demo data.")
    p.add_argument("--count", type=int, default=None, metavar="N",
                   help="Target number of candidates to generate (default 100000).")
    p.add_argument("--accounts", type=int, default=8, metavar="N",
                   help="Number of synthetic accounts to build (default 8).")
    p.add_argument("--target", default=None, metavar="LABEL",
                   help="Label for the synthetic research target (demo mode).")
    p.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), metavar="DIR",
                   help="Directory for research logs/exports (default ./logs).")
    p.add_argument("--seed", type=int, default=None,
                   help="Deterministic RNG seed for reproducible simulations.")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    p.add_argument("--no-animation", action="store_true",
                   help="Disable animations and live redraws.")
    p.add_argument("--no-startup", action="store_true",
                   help="Skip the animated startup sequence.")
    p.add_argument("--history", action="store_true",
                   help="Print recent research session history and exit.")
    p.add_argument("--version", action="version",
                   version=f"{__app_name__} {__version__}")
    return p


def _print_history(theme: Theme, log_dir: Path) -> int:
    history = load_history(log_dir)
    if not history:
        theme.write(theme.gray("No research history found."))
        return 0
    theme.write(theme.bold(theme.green(f"{__app_name__} :: research history")))
    theme.write(theme.green_dim(
        f"{'session':<20}{'target':<22}{'generated':>12}{'crack%':>9}"))
    for h in history:
        theme.write(
            theme.white(f"{str(h.get('session_id','?')):<20}") +
            theme.gray(f"{str(h.get('target_label',''))[:20]:<22}") +
            theme.green(f"{(h.get('candidates_generated') or 0):>12,}") +
            theme.amber(f"{(h.get('crack_rate_pct') or 0):>8}%"))
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    theme = Theme(
        color=False if args.no_color else None,
        animate=False if (args.no_animation or args.demo) else None,
    )
    log_dir = Path(args.log_dir)

    if args.history:
        return _print_history(theme, log_dir)

    try:
        if args.demo:
            config = demo_config(
                target_label=args.target or "acme-demo-portal",
                target_count=args.count or 100_000,
            )
        else:
            config = collect_interactive(theme)
            if args.count:
                config.target_count = args.count

        run(theme, config, log_dir=log_dir, num_accounts=args.accounts,
            seed=args.seed, show_startup=not args.no_startup)
        return 0
    except KeyboardInterrupt:
        theme.write()
        theme.write(theme.red("  Session aborted by operator."))
        return 130


if __name__ == "__main__":
    sys.exit(main())
