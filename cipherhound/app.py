"""
app.py
======
Orchestration: wires the collector, engine, simulator, analysis, dashboard,
reporting, and storage modules into a single research session.

Pipeline
--------
    collect inputs -> generate candidates (live) -> simulate against synthetic
    accounts (live) -> analyze -> report/export -> persist history -> summary.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from . import __app_name__
from .analysis import analyze_candidates
from .branding import Theme, section, startup_sequence
from .collector import SessionConfig
from .dashboard import Dashboard
from .engine import PasswordEngine
from .report import build_record, export_all
from .simulator import AuthSimulator
from .storage import DEFAULT_LOG_DIR, load_history


class ResearchApp:
    """A single CIPHERHOUND research platform instance."""

    def __init__(self, theme: Theme, log_dir: Path = DEFAULT_LOG_DIR,
                 num_accounts: int = 8, seed: Optional[int] = None):
        self.theme = theme
        self.log_dir = Path(log_dir)
        self.num_accounts = num_accounts
        self.seed = seed

    # -- phases -------------------------------------------------------------

    def _phase_generate(self, config: SessionConfig,
                        dashboard: Dashboard) -> Tuple[List[Tuple[str, str]], PasswordEngine]:
        section(self.theme, "Generation Engine")
        engine = PasswordEngine(config)
        candidates: List[Tuple[str, str]] = []
        for cand in engine.generate():
            candidates.append(cand)
            if engine.stats.unique % 1500 == 0:
                dashboard.render("generate", engine.stats,
                                 accounts_total=self.num_accounts)
        dashboard.render("generate", engine.stats,
                         accounts_total=self.num_accounts, force=True)
        dashboard.finish()
        self.theme.write(self.theme.green(
            f"  >> Generated {engine.stats.unique:,} unique candidates "
            f"({engine.stats.duplicates:,} duplicates skipped)."))
        return candidates, engine

    def _phase_simulate(self, config: SessionConfig,
                        candidates: List[Tuple[str, str]],
                        engine: PasswordEngine, dashboard: Dashboard):
        section(self.theme, "Authentication Simulation (local / synthetic)")
        simulator = AuthSimulator(seed=self.seed)
        simulator.build_synthetic_accounts(config, num_accounts=self.num_accounts)
        self.theme.write(self.theme.gray(
            f"  Built {len(simulator.accounts)} synthetic accounts "
            "(passwords stored as salted hashes only)."))

        def progress(result):
            dashboard.render("simulate", engine.stats,
                             evaluated=result.candidates_evaluated,
                             accounts_total=result.accounts_total,
                             matches=result.accounts_cracked,
                             match_categories=result.match_categories)

        result = simulator.run(iter(candidates), progress=progress)
        dashboard.render("simulate", engine.stats,
                         evaluated=result.candidates_evaluated,
                         accounts_total=result.accounts_total,
                         matches=result.accounts_cracked,
                         match_categories=result.match_categories, force=True)
        dashboard.finish()
        self._print_matches(result)
        return result

    def _phase_network_target(self, config: SessionConfig,
                              candidates: List[Tuple[str, str]],
                              engine: PasswordEngine, dashboard: Dashboard):
        """Run candidates against the operator's loopback lab server."""
        from .netsim import NetworkTargetSimulator, TargetRefused

        section(self.theme, "Live Lab Target (loopback-only)")
        t = self.theme
        try:
            netsim = NetworkTargetSimulator(config.lab_host, config.lab_port)
        except TargetRefused as exc:
            t.write(t.red(f"  ! {exc}"))
            return None

        t.write(t.red("  * AUTHORIZED SECURITY RESEARCH *") +
                t.gray(f"  target {config.lab_host}:{config.lab_port} (loopback)"))
        if not netsim.ping():
            t.write(t.red(
                f"  ! No lab server reachable at {config.lab_host}:{config.lab_port}."))
            t.write(t.gray(
                "    Start one first:  python -m cipherhound.labserver "
                f"--port {config.lab_port}"))
            return None

        users = netsim.fetch_users()
        t.write(t.gray(f"  Connected. Target exposes {len(users)} synthetic account(s)."))

        def progress(result):
            dashboard.render("target", engine.stats,
                             evaluated=result.candidates_evaluated,
                             accounts_total=result.accounts_total,
                             matches=result.accounts_cracked,
                             match_categories=result.match_categories)

        result = netsim.run(iter(candidates), usernames=users, progress=progress)
        dashboard.render("target", engine.stats,
                         evaluated=result.candidates_evaluated,
                         accounts_total=result.accounts_total,
                         matches=result.accounts_cracked,
                         match_categories=result.match_categories, force=True)
        dashboard.finish()
        self._print_matches(result, live=True)
        return result

    def _print_matches(self, result, live: bool = False) -> None:
        t = self.theme
        where = "lab-target accounts" if live else "synthetic accounts"
        if result.matches:
            t.write(t.green(
                f"  >> {result.accounts_cracked}/{result.accounts_total} "
                f"{where} matched ({result.crack_rate:.1f}% crack rate)."))
            for m in result.matches:
                t.write("     " + t.green("[MATCH] ") +
                        t.white(f"{m.username:<20}") +
                        t.green(f" <- {m.candidate}") +
                        t.gray(f"  ({m.category})"))
        else:
            t.write(t.gray(
                f"  >> No synthetic accounts matched "
                f"({result.accounts_total} accounts resisted {result.candidates_evaluated:,} "
                "candidates)."))

    # -- reporting / summary ------------------------------------------------

    def _report(self, config, engine, analysis, result, network_result=None):
        from .storage import append_history
        section(self.theme, "Research Logging & Export")
        record = build_record(config, engine.stats, analysis, result,
                              when=datetime.now(), network_sim=network_result)
        paths = export_all(record, self.log_dir)
        append_history(record, self.log_dir)
        for fmt, path in paths.items():
            self.theme.write(self.theme.green("  [saved] ") +
                             self.theme.white(f"{fmt.upper():<4}") +
                             self.theme.gray(f" -> {path}"))
        return record

    def _summary(self, record) -> None:
        t = self.theme
        section(t, "Session Summary & Recommendations")
        t.write(t.white("  Theoretical risk assessment vs. simulated matches are "
                        "reported separately:"))
        t.write(t.gray("    - Simulated matches  : confirmed hits against local synthetic accounts."))
        t.write(t.gray("    - Pattern analysis   : theoretical risk from candidate structure."))
        t.write()
        for i, rec in enumerate(record["recommendations"], 1):
            t.write(t.green(f"  {i}. ") + t.white(rec))
        t.write()

    def _history(self) -> None:
        t = self.theme
        history = load_history(self.log_dir)
        if not history:
            return
        section(t, "Historical Research Sessions")
        t.write(t.green_dim(
            "  " + f"{'session':<20}{'target':<22}{'gen':>10}{'crack%':>9}"))
        for h in history[-10:]:
            t.write("  " + t.white(f"{str(h.get('session_id','?')):<20}") +
                    t.gray(f"{str(h.get('target_label',''))[:20]:<22}") +
                    t.green(f"{(h.get('candidates_generated') or 0):>10,}") +
                    t.amber(f"{(h.get('crack_rate_pct') or 0):>8}%"))
        t.write()

    # -- public entrypoint --------------------------------------------------

    def run_session(self, config: SessionConfig):
        dashboard = Dashboard(self.theme, config.target_label, config.target_count)
        candidates, engine = self._phase_generate(config, dashboard)
        result = self._phase_simulate(config, candidates, engine, dashboard)

        network_result = None
        if config.lab_host:
            network_result = self._phase_network_target(
                config, candidates, engine, dashboard)

        section(self.theme, "Pattern Analysis")
        self.theme.write(self.theme.gray("  Analyzing candidate structure and habits..."))
        analysis = analyze_candidates(iter(candidates))
        self.theme.write(self.theme.green(
            f"  >> Pattern diversity {analysis.pattern_diversity:.3f}, "
            f"avg complexity {analysis.avg_complexity:.1f}/100."))

        record = self._report(config, engine, analysis, result,
                              network_result=network_result)
        self._summary(record)
        self._history()
        return record


def run(theme: Theme, config: SessionConfig, log_dir: Path = DEFAULT_LOG_DIR,
        num_accounts: int = 8, seed: Optional[int] = None,
        show_startup: bool = True):
    """Top-level convenience: optional startup screen + one research session."""
    if show_startup:
        startup_sequence(theme)
    app = ResearchApp(theme, log_dir=log_dir, num_accounts=num_accounts, seed=seed)
    return app.run_session(config)
