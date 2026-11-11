"""
storage.py
==========
Secure, local-only persistence of research-session *metadata* and history.

What is stored
--------------
* Session date/time, target label, input category counts, generation and
  simulation statistics, pattern analysis, and recommendations.

What is NEVER stored
--------------------
* Real passwords, authentication tokens, or personal credentials.
* Synthetic account plaintext (only hashes live transiently in memory).

Candidate match values are synthetic test strings; they are included in logs as
research artifacts but are clearly labeled synthetic and never represent real
secrets. The history index stored here deliberately omits them.

Storage is a JSON lines index under ``logs/`` with restrictive file
permissions (0600) where the OS supports it.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, List

DEFAULT_LOG_DIR = Path(os.environ.get("CIPHERHOUND_LOG_DIR", "logs"))
HISTORY_FILE = "research_history.jsonl"


def ensure_log_dir(log_dir: Path = DEFAULT_LOG_DIR) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _secure_chmod(path: Path) -> None:
    """Best-effort restrictive permissions (owner read/write only)."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass  # e.g. on filesystems that do not support chmod


def session_id(when: datetime) -> str:
    return when.strftime("CH-%Y%m%d-%H%M%S")


def append_history(record: Dict, log_dir: Path = DEFAULT_LOG_DIR) -> Path:
    """
    Append a compact, credential-free summary of a session to the history
    index. Returns the history file path.
    """
    log_dir = ensure_log_dir(log_dir)
    path = log_dir / HISTORY_FILE

    summary = {
        "session_id": record.get("session_id"),
        "timestamp": record.get("timestamp"),
        "target_label": record.get("target_label"),
        "candidates_generated": record.get("candidates_generated"),
        "candidates_evaluated": record.get("candidates_evaluated"),
        "accounts_total": record.get("accounts_total"),
        "accounts_cracked": record.get("accounts_cracked"),
        "crack_rate_pct": record.get("crack_rate_pct"),
        "avg_complexity": record.get("analysis", {}).get("avg_complexity"),
        "pattern_diversity": record.get("analysis", {}).get("pattern_diversity"),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")
    _secure_chmod(path)
    return path


def load_history(log_dir: Path = DEFAULT_LOG_DIR, limit: int = 50) -> List[Dict]:
    """Return the most recent session summaries (newest last)."""
    path = Path(log_dir) / HISTORY_FILE
    if not path.exists():
        return []
    records: List[Dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records[-limit:]
