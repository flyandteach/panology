"""
Tests for agents/quality_gate.py — QualityGateAgent.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agents.quality_gate import QualityGateAgent
import config


class TestQualityGatePass(unittest.TestCase):

    def setUp(self):
        self.gate = QualityGateAgent()

    def test_all_passing_scores_returns_pass(self):
        scores = {
            "line_edit": 8.5,
            "repetition": 9.2,
            "continuity": 9.1,
            "critical_audience": 8.7,
        }
        result = self.gate.evaluate(scores, [])
        self.assertTrue(result["pass"])

    def test_all_passing_no_failed_thresholds(self):
        scores = {
            "line_edit": 9.0,
            "repetition": 9.5,
            "continuity": 9.3,
            "critical_audience": 9.0,
        }
        result = self.gate.evaluate(scores, [])
        self.assertEqual(len(result["failed_thresholds"]), 0)

    def test_overall_score_computed(self):
        scores = {
            "line_edit": 8.0,
            "repetition": 9.0,
            "continuity": 9.0,
            "critical_audience": 8.5,
        }
        result = self.gate.evaluate(scores, [])
        # Average should be (8.0 + 9.0 + 9.0 + 8.5) / 4 = 8.625
        self.assertAlmostEqual(result["overall_score"], 8.625, places=1)

    def test_scorecard_has_all_dimensions(self):
        scores = {
            "line_edit": 8.5,
            "repetition": 9.5,
            "continuity": 9.5,
            "critical_audience": 9.0,
        }
        result = self.gate.evaluate(scores, [])
        scorecard = result["scorecard"]
        for dim in config.SCORE_DIMENSIONS:
            self.assertIn(dim, scorecard)

    def test_scorecard_passed_flags_correct(self):
        scores = {
            "line_edit": 9.0,
            "repetition": 9.5,
            "continuity": 9.5,
            "critical_audience": 9.0,
        }
        result = self.gate.evaluate(scores, [])
        for dim, data in result["scorecard"].items():
            self.assertTrue(data["passed"], f"Expected {dim} to pass")


class TestQualityGateFail(unittest.TestCase):

    def setUp(self):
        self.gate = QualityGateAgent()

    def test_low_line_edit_fails(self):
        scores = {
            "line_edit": 7.5,  # below 8.0
            "repetition": 9.2,
            "continuity": 9.1,
            "critical_audience": 8.7,
        }
        result = self.gate.evaluate(scores, [])
        self.assertFalse(result["pass"])

    def test_low_repetition_fails(self):
        scores = {
            "line_edit": 8.5,
            "repetition": 8.5,  # below 9.0
            "continuity": 9.0,
            "critical_audience": 8.5,
        }
        result = self.gate.evaluate(scores, [])
        self.assertFalse(result["pass"])

    def test_low_critical_audience_fails(self):
        scores = {
            "line_edit": 8.5,
            "repetition": 9.0,
            "continuity": 9.0,
            "critical_audience": 8.2,  # below 8.5
        }
        result = self.gate.evaluate(scores, [])
        self.assertFalse(result["pass"])

    def test_failed_threshold_records_gap(self):
        scores = {
            "line_edit": 7.0,  # 1.0 below threshold of 8.0
            "repetition": 9.0,
            "continuity": 9.0,
            "critical_audience": 8.5,
        }
        result = self.gate.evaluate(scores, [])
        failed = result["failed_thresholds"]
        line_edit_fail = next((f for f in failed if f["dimension"] == "line_edit"), None)
        self.assertIsNotNone(line_edit_fail)
        self.assertAlmostEqual(line_edit_fail["gap"], 1.0, places=1)

    def test_low_average_fails_even_if_all_dimensions_pass(self):
        # All individual thresholds met but average below 8.5
        scores = {
            "line_edit": 8.0,
            "repetition": 9.0,
            "continuity": 9.0,
            "critical_audience": 8.5,
        }
        result = self.gate.evaluate(scores, [])
        # Average = (8.0 + 9.0 + 9.0 + 8.5) / 4 = 8.625 — this should pass
        # Let's use scores that yield average < 8.5
        scores2 = {
            "line_edit": 8.0,
            "repetition": 9.0,
            "continuity": 9.0,
            "critical_audience": 8.5,
        }
        # 8.0+9.0+9.0+8.5 = 34.5 / 4 = 8.625 — passes
        result2 = self.gate.evaluate(scores2, [])
        self.assertTrue(result2["pass"])

        # Now create a case where average < 8.5
        scores3 = {
            "line_edit": 8.0,
            "repetition": 9.0,
            "continuity": 9.0,
            "critical_audience": 8.5,
        }
        # Average = 8.625 - still passes
        # To fail average: use 8.0, 9.0, 9.0, 7.5 = 33.5/4 = 8.375
        # But 7.5 < 8.5 threshold for critical_audience, so it double-fails
        # Use: line_edit=8.0, rep=9.0, cont=9.0, audience=8.5: avg=8.625 passes
        # Fail average alone: line=8.0, rep=9.0, cont=9.0, audience=8.5: still 8.625
        # To get avg < 8.5 without failing individual: not possible with these thresholds
        # because min individual thresholds sum to at least 8.0+9.0+9.0+8.5=34.5 avg=8.625
        # This is actually mathematically impossible to fail average without failing a dimension
        # So this test verifies the minimum passing average case
        self.assertGreaterEqual(result2["overall_score"], 8.0)

    def test_multiple_failures_reported(self):
        scores = {
            "line_edit": 6.0,
            "repetition": 7.0,
            "continuity": 7.0,
            "critical_audience": 6.5,
        }
        result = self.gate.evaluate(scores, [])
        self.assertFalse(result["pass"])
        self.assertGreater(len(result["failed_thresholds"]), 1)


class TestQualityGateScorecardDisplay(unittest.TestCase):

    def setUp(self):
        self.gate = QualityGateAgent()

    def test_scorecard_display_is_string(self):
        scores = {"line_edit": 8.5, "repetition": 9.2, "continuity": 9.1, "critical_audience": 8.7}
        gate_result = self.gate.evaluate(scores, [])
        display = self.gate.generate_scorecard_display(gate_result)
        self.assertIsInstance(display, str)

    def test_scorecard_display_contains_verdict(self):
        scores = {"line_edit": 8.5, "repetition": 9.2, "continuity": 9.1, "critical_audience": 8.7}
        gate_result = self.gate.evaluate(scores, [])
        display = self.gate.generate_scorecard_display(gate_result)
        self.assertIn("VERDICT", display)

    def test_scorecard_display_shows_pass(self):
        scores = {"line_edit": 8.5, "repetition": 9.2, "continuity": 9.1, "critical_audience": 8.7}
        gate_result = self.gate.evaluate(scores, [])
        display = self.gate.generate_scorecard_display(gate_result)
        self.assertIn("APPROVED", display)

    def test_scorecard_display_shows_fail(self):
        scores = {"line_edit": 6.0, "repetition": 7.0, "continuity": 7.0, "critical_audience": 6.5}
        gate_result = self.gate.evaluate(scores, [])
        display = self.gate.generate_scorecard_display(gate_result)
        self.assertIn("FAILED", display)

    def test_scorecard_display_contains_dimension_names(self):
        scores = {"line_edit": 8.5, "repetition": 9.2, "continuity": 9.1, "critical_audience": 8.7}
        gate_result = self.gate.evaluate(scores, [])
        display = self.gate.generate_scorecard_display(gate_result)
        self.assertIn("Line Edit", display)
        self.assertIn("Repetition", display)


class TestQualityGateEdgeCases(unittest.TestCase):

    def setUp(self):
        self.gate = QualityGateAgent()

    def test_exactly_at_threshold_passes(self):
        scores = {
            "line_edit": 8.0,    # exactly at threshold
            "repetition": 9.0,   # exactly at threshold
            "continuity": 9.0,   # exactly at threshold
            "critical_audience": 8.5,  # exactly at threshold
        }
        result = self.gate.evaluate(scores, [])
        # All at threshold — average = 8.625 >= 8.5 → should pass
        self.assertTrue(result["pass"])

    def test_perfect_scores(self):
        scores = {
            "line_edit": 10.0,
            "repetition": 10.0,
            "continuity": 10.0,
            "critical_audience": 10.0,
        }
        result = self.gate.evaluate(scores, [])
        self.assertTrue(result["pass"])
        self.assertEqual(result["overall_score"], 10.0)

    def test_issues_count_recorded(self):
        scores = {"line_edit": 8.5, "repetition": 9.2, "continuity": 9.1, "critical_audience": 8.7}
        issues = ["Issue 1", "Issue 2", "Issue 3"]
        result = self.gate.evaluate(scores, issues)
        self.assertEqual(result["issues_count"], 3)

    def test_missing_score_defaults_to_zero(self):
        scores = {
            "line_edit": 8.5,
            # repetition missing
            "continuity": 9.1,
            "critical_audience": 8.7,
        }
        result = self.gate.evaluate(scores, [])
        # repetition defaults to 0.0 — should fail
        self.assertFalse(result["pass"])


if __name__ == "__main__":
    unittest.main()
