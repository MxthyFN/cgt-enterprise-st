"""
Test suite for CIPHERHOUND.

Pure stdlib (unittest) so it runs with ``python -m unittest`` or ``pytest``
with zero extra dependencies. Covers generation volume, categorization,
de-duplication, the local simulator, analysis metrics, and log/export output.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from cipherhound.analysis import (analyze_candidates, complexity_score,
                                   has_leet, has_repeat, repeated_digit_runs,
                                   security_recommendations)
from cipherhound.collector import SessionConfig, demo_config, _split
from cipherhound.engine import (CATEGORIES, PasswordEngine, generate_candidates)
from cipherhound.report import build_record, export_all
from cipherhound.simulator import AuthSimulator, _hash
from cipherhound.storage import append_history, load_history


class EngineTests(unittest.TestCase):
    def test_reaches_target_volume(self):
        cfg = demo_config(target_count=100_000)
        cands, stats = generate_candidates(cfg)
        self.assertEqual(stats.unique, 100_000)
        self.assertEqual(len(cands), 100_000)

    def test_candidates_are_unique(self):
        cfg = demo_config(target_count=20_000)
        cands, _ = generate_candidates(cfg)
        values = [c for c, _ in cands]
        self.assertEqual(len(values), len(set(values)))

    def test_small_limit_respected(self):
        cfg = demo_config(target_count=500)
        cands, stats = generate_candidates(cfg, limit=500)
        self.assertEqual(len(cands), 500)
        self.assertEqual(stats.unique, 500)

    def test_categories_are_known(self):
        cfg = demo_config(target_count=5_000)
        cands, _ = generate_candidates(cfg)
        cats = {cat for _, cat in cands}
        self.assertTrue(cats.issubset(set(CATEGORIES)))
        # Several distinct habits should be represented.
        self.assertGreaterEqual(len(cats), 5)

    def test_duplicates_tracked(self):
        cfg = demo_config(target_count=100_000)
        _, stats = generate_candidates(cfg)
        self.assertGreater(stats.duplicates, 0)
        self.assertEqual(sum(stats.by_category.values()), stats.unique)

    def test_empty_config_still_generates(self):
        # No seeds at all -> engine still yields habit-based candidates.
        cfg = SessionConfig(target_count=1_000)
        cands, stats = generate_candidates(cfg)
        self.assertGreater(stats.unique, 0)


class AnalysisTests(unittest.TestCase):
    def test_complexity_bounds(self):
        score, label = complexity_score("a")
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        strong, slabel = complexity_score("Xk9#mQ2!vZ7wLp4$")
        weak, wlabel = complexity_score("123456")
        self.assertGreater(strong, weak)

    def test_leet_detection(self):
        self.assertTrue(has_leet("p@ssw0rd"))
        self.assertFalse(has_leet("password"))

    def test_repeat_detection(self):
        self.assertTrue(has_repeat("abcabcabc"))
        self.assertTrue(has_repeat("aaaa"))
        self.assertFalse(has_repeat("abcdef"))

    def test_digit_runs(self):
        self.assertEqual(repeated_digit_runs("vault1234"), ["1234"])
        self.assertEqual(repeated_digit_runs("vault"), [])

    def test_report_fields(self):
        cfg = demo_config(target_count=10_000)
        cands, _ = generate_candidates(cfg)
        report = analyze_candidates(iter(cands))
        self.assertGreater(report.sample_size, 0)
        self.assertGreaterEqual(report.pattern_diversity, 0.0)
        self.assertLessEqual(report.pattern_diversity, 1.0)
        self.assertTrue(report.category_distribution)

    def test_recommendations_nonempty(self):
        cfg = demo_config(target_count=5_000)
        cands, _ = generate_candidates(cfg)
        report = analyze_candidates(iter(cands))
        recs = security_recommendations(report, {"special_suffix": 5})
        self.assertTrue(recs)
        self.assertTrue(any("MFA" in r for r in recs))


class SimulatorTests(unittest.TestCase):
    def test_hash_is_salted(self):
        self.assertNotEqual(_hash("secret", b"a"), _hash("secret", b"b"))
        self.assertEqual(_hash("secret", b"a"), _hash("secret", b"a"))

    def test_build_and_run(self):
        cfg = demo_config(target_count=50_000)
        sim = AuthSimulator(seed=1)
        sim.build_synthetic_accounts(cfg, num_accounts=10)
        self.assertEqual(len(sim.accounts), 10)
        cands, _ = generate_candidates(cfg)
        result = sim.run(iter(cands))
        self.assertEqual(result.accounts_total, 10)
        self.assertGreaterEqual(result.accounts_cracked, 1)
        self.assertLessEqual(result.accounts_cracked, 10)
        self.assertGreater(result.candidates_evaluated, 0)

    def test_no_plaintext_persisted_in_accounts(self):
        cfg = demo_config(target_count=2_000)
        sim = AuthSimulator(seed=1)
        sim.build_synthetic_accounts(cfg, num_accounts=5)
        for acct in sim.accounts:
            # Only salt + hash are retained; no plaintext attribute exists.
            self.assertFalse(hasattr(acct, "password"))
            self.assertFalse(hasattr(acct, "plaintext"))
            self.assertEqual(len(acct.password_hash), 64)  # sha256 hex

    def test_strong_accounts_resist(self):
        cfg = demo_config(target_count=100_000)
        sim = AuthSimulator(seed=3)
        sim.build_synthetic_accounts(cfg, num_accounts=30)
        cands, _ = generate_candidates(cfg)
        result = sim.run(iter(cands))
        # With ~25% strong-random accounts, not everything should crack.
        self.assertLess(result.accounts_cracked, result.accounts_total)


class ReportTests(unittest.TestCase):
    def _record(self):
        cfg = demo_config(target_count=10_000)
        engine = PasswordEngine(cfg)
        cands = list(engine.generate())
        sim = AuthSimulator(seed=2)
        sim.build_synthetic_accounts(cfg, num_accounts=6)
        result = sim.run(iter(cands))
        report = analyze_candidates(iter(cands))
        return build_record(cfg, engine.stats, report, result)

    def test_record_has_no_real_credentials_field(self):
        rec = self._record()
        self.assertIn("notice", rec)
        self.assertIn("synthetic", rec["notice"].lower())
        # History summary must not contain candidate match strings or the
        # per-match detail block (only aggregate metrics belong in the index).
        with tempfile.TemporaryDirectory() as d:
            append_history(rec, Path(d))
            hist = load_history(Path(d))
            self.assertEqual(len(hist), 1)
            blob = json.dumps(hist[0])
            self.assertNotIn("matches", hist[0])
            for m in rec["simulation"]["matches"]:
                self.assertNotIn(m["candidate"], blob)

    def test_exports_written(self):
        rec = self._record()
        with tempfile.TemporaryDirectory() as d:
            paths = export_all(rec, Path(d))
            self.assertEqual(set(paths), {"json", "txt", "csv"})
            for p in paths.values():
                self.assertTrue(p.exists())
                self.assertGreater(p.stat().st_size, 0)
            # JSON round-trips.
            data = json.loads(paths["json"].read_text())
            self.assertEqual(data["candidates_generated"], rec["candidates_generated"])
            # CSV parses and has a header.
            rows = list(csv.reader(paths["csv"].read_text().splitlines()))
            self.assertEqual(rows[0], ["section", "key", "value", "detail"])


class CollectorTests(unittest.TestCase):
    def test_split_dedup(self):
        self.assertEqual(_split("red, blue, red  green"), ["red", "blue", "green"])
        self.assertEqual(_split(""), [])

    def test_input_summary(self):
        cfg = demo_config()
        summary = cfg.input_summary()
        self.assertEqual(summary["colors"], 4)
        self.assertIn("usernames", summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)
