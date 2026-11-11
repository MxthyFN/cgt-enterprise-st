"""
report.py
=========
Research logging and export.

After every session CIPHERHOUND assembles a structured research record and
writes it to the local ``logs/`` directory in three forms:

    * ``<session_id>.json``  - full machine-readable record
    * ``<session_id>.txt``   - human-readable research log
    * ``<session_id>.csv``   - tabular export (simulation matches + metrics)

No real passwords, tokens, or personal credentials are ever written. Candidate
values that appear are synthetic test strings produced locally and are labeled
as such.
"""

from __future__ import annotations

import csv
import json
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from . import __app_name__, __version__
from .analysis import PatternReport, security_recommendations
from .collector import SessionConfig
from .engine import GenerationStats
from .simulator import SimulationResult
from .storage import DEFAULT_LOG_DIR, ensure_log_dir, session_id


def build_record(config: SessionConfig, gen_stats: GenerationStats,
                 analysis: PatternReport, sim: SimulationResult,
                 when: datetime | None = None) -> Dict:
    """Assemble the full, credential-free research record for a session."""
    when = when or datetime.now()
    recs = security_recommendations(analysis, sim.match_categories)
    return {
        "application": __app_name__,
        "version": __version__,
        "session_id": session_id(when),
        "timestamp": when.isoformat(timespec="seconds"),
        "target_label": config.target_label,
        "input_categories": config.input_summary(),
        "synthetic_usernames": list(config.usernames),
        "candidates_generated": gen_stats.unique,
        "candidates_evaluated": sim.candidates_evaluated,
        "duplicates_skipped": gen_stats.duplicates,
        "generation_by_category": gen_stats.by_category,
        "accounts_total": sim.accounts_total,
        "accounts_cracked": sim.accounts_cracked,
        "crack_rate_pct": round(sim.crack_rate, 2),
        "elapsed_seconds": round(sim.elapsed_seconds, 3),
        "analysis": analysis.to_dict(),
        "simulation": sim.to_dict(),
        "recommendations": recs,
        "notice": ("Synthetic research artifact. Candidate values are locally "
                   "generated test strings, not real credentials. No external "
                   "systems were contacted."),
    }


def _secure(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass


def export_json(record: Dict, log_dir: Path = DEFAULT_LOG_DIR) -> Path:
    log_dir = ensure_log_dir(log_dir)
    path = log_dir / f"{record['session_id']}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    _secure(path)
    return path


def export_txt(record: Dict, log_dir: Path = DEFAULT_LOG_DIR) -> Path:
    log_dir = ensure_log_dir(log_dir)
    path = log_dir / f"{record['session_id']}.txt"
    lines: List[str] = []
    w = lines.append

    w("=" * 72)
    w(f"{record['application']} v{record['version']} - RESEARCH LOG")
    w("CGT ENTERPRISES :: Internal Password-Security Research (synthetic)")
    w("=" * 72)
    w(f"Session ID      : {record['session_id']}")
    w(f"Timestamp       : {record['timestamp']}")
    w(f"Research target : {record['target_label']}")
    w("")
    w("-- INPUT CATEGORIES --------------------------------------------------")
    for k, v in record["input_categories"].items():
        w(f"  {k:<16}: {v} seed value(s)")
    if record["synthetic_usernames"]:
        w(f"  synthetic ids   : {', '.join(record['synthetic_usernames'])}")
    w("")
    w("-- GENERATION --------------------------------------------------------")
    w(f"  Candidates generated : {record['candidates_generated']:,}")
    w(f"  Candidates evaluated : {record['candidates_evaluated']:,}")
    w(f"  Duplicates skipped   : {record['duplicates_skipped']:,}")
    w("  By category:")
    for cat, n in sorted(record["generation_by_category"].items(),
                         key=lambda kv: kv[1], reverse=True):
        if n:
            w(f"    - {cat:<20}: {n:,}")
    w("")
    w("-- SIMULATION (local, synthetic accounts) ----------------------------")
    w(f"  Synthetic accounts   : {record['accounts_total']}")
    w(f"  Simulated matches    : {record['accounts_cracked']}")
    w(f"  Crack rate           : {record['crack_rate_pct']}%")
    w(f"  Elapsed              : {record['elapsed_seconds']}s")
    if record["simulation"]["matches"]:
        w("  Matched synthetic accounts:")
        for m in record["simulation"]["matches"]:
            w(f"    [MATCH] {m['username']:<22} via '{m['candidate']}' "
              f"(category={m['category']}, "
              f"attempt #{m['attempts_to_match']:,})")
    else:
        w("  No synthetic accounts matched.")
    w("")
    w("-- PATTERN ANALYSIS --------------------------------------------------")
    a = record["analysis"]
    w(f"  Sample size              : {a['sample_size']:,}")
    w(f"  Avg complexity (0-100)   : {a['avg_complexity']}")
    w(f"  Avg length               : {a['avg_length']}")
    w(f"  Predictable substitutions: {a['predictable_substitution_pct']}%")
    w(f"  Repeated sequences       : {a['repeated_sequence_pct']}%")
    w(f"  Digit runs               : {a['digit_run_pct']}%")
    w(f"  Pattern diversity (0-1)  : {a['pattern_diversity']}")
    w("  Complexity histogram:")
    for label, n in a["complexity_histogram"].items():
        w(f"    - {label:<12}: {n:,}")
    w("")
    w("-- SECURITY RECOMMENDATIONS ------------------------------------------")
    for i, r in enumerate(record["recommendations"], 1):
        w(f"  {i}. {r}")
    w("")
    w("-- NOTICE ------------------------------------------------------------")
    w(f"  {record['notice']}")
    w("=" * 72)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _secure(path)
    return path


def export_csv(record: Dict, log_dir: Path = DEFAULT_LOG_DIR) -> Path:
    """
    CSV export. Row-per-synthetic-account for matches, followed by a summary
    metrics block, so the file is useful in a spreadsheet.
    """
    log_dir = ensure_log_dir(log_dir)
    path = log_dir / f"{record['session_id']}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["section", "key", "value", "detail"])

        meta = [
            ("meta", "session_id", record["session_id"], ""),
            ("meta", "timestamp", record["timestamp"], ""),
            ("meta", "target_label", record["target_label"], ""),
            ("meta", "candidates_generated", record["candidates_generated"], ""),
            ("meta", "candidates_evaluated", record["candidates_evaluated"], ""),
            ("meta", "accounts_total", record["accounts_total"], ""),
            ("meta", "accounts_cracked", record["accounts_cracked"], ""),
            ("meta", "crack_rate_pct", record["crack_rate_pct"], ""),
            ("meta", "elapsed_seconds", record["elapsed_seconds"], ""),
        ]
        for r in meta:
            writer.writerow(r)

        for cat, n in record["generation_by_category"].items():
            writer.writerow(["generation_category", cat, n, ""])

        a = record["analysis"]
        for key in ("avg_complexity", "avg_length", "predictable_substitution_pct",
                    "repeated_sequence_pct", "digit_run_pct", "pattern_diversity"):
            writer.writerow(["analysis", key, a[key], ""])

        for m in record["simulation"]["matches"]:
            writer.writerow([
                "match", m["username"], m["candidate"],
                f"category={m['category']};attempt={m['attempts_to_match']}",
            ])

        for i, rec in enumerate(record["recommendations"], 1):
            writer.writerow(["recommendation", f"rec_{i}", rec, ""])

    _secure(path)
    return path


def export_all(record: Dict,
               log_dir: Path = DEFAULT_LOG_DIR) -> Dict[str, Path]:
    """Write JSON, TXT and CSV. Returns a mapping of format -> path."""
    return {
        "json": export_json(record, log_dir),
        "txt": export_txt(record, log_dir),
        "csv": export_csv(record, log_dir),
    }
