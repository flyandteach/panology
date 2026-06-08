"""
Quality Gate Agent: Aggregates all scores against configured thresholds.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def call_llm(prompt: str, role: str = "quality_gate") -> str:
    """Not used in the quality gate (pure computation), but provided for consistency."""
    return ""


class QualityGateAgent:
    """Evaluates whether a draft meets all quality thresholds."""

    def evaluate(self, scores: dict, issues: list) -> dict:
        """
        Aggregate scores against thresholds and determine pass/fail.

        Args:
            scores: dict with keys matching SCORE_DIMENSIONS
                    e.g. {"line_edit": 8.3, "repetition": 8.7, "continuity": 9.1, "critical_audience": 8.5}
            issues: consolidated list of issues from all agents

        Returns:
            dict with keys: pass (bool), scorecard (dict), failed_thresholds (list), overall_score (float)
        """
        thresholds = config.THRESHOLDS
        scorecard = {}
        failed_thresholds = []
        score_values = []

        for dimension in config.SCORE_DIMENSIONS:
            score = scores.get(dimension, 0.0)
            score = float(score)
            threshold = thresholds.get(dimension, thresholds["min_any_score"])
            passed = score >= threshold
            score_values.append(score)

            scorecard[dimension] = {
                "score": round(score, 2),
                "threshold": threshold,
                "passed": passed,
                "label": _dimension_label(dimension),
            }

            if not passed:
                failed_thresholds.append({
                    "dimension": dimension,
                    "score": round(score, 2),
                    "threshold": threshold,
                    "gap": round(threshold - score, 2),
                })

        overall_score = round(sum(score_values) / len(score_values), 2) if score_values else 0.0
        avg_threshold = thresholds["min_average"]
        avg_passed = overall_score >= avg_threshold

        if not avg_passed:
            failed_thresholds.append({
                "dimension": "average",
                "score": overall_score,
                "threshold": avg_threshold,
                "gap": round(avg_threshold - overall_score, 2),
            })

        gate_passed = len(failed_thresholds) == 0

        return {
            "pass": gate_passed,
            "scorecard": scorecard,
            "failed_thresholds": failed_thresholds,
            "overall_score": overall_score,
            "issues_count": len(issues),
        }

    def generate_scorecard_display(self, gate_result: dict) -> str:
        """Generate a formatted scorecard string for CLI display."""
        lines = []
        width = 68

        lines.append("╔" + "═" * width + "╗")
        lines.append("║" + " QUALITY GATE SCORECARD ".center(width) + "║")
        lines.append("╠" + "═" * width + "╣")

        scorecard = gate_result.get("scorecard", {})
        for dimension, data in scorecard.items():
            label = data.get("label", dimension)
            score = data.get("score", 0.0)
            threshold = data.get("threshold", 8.0)
            passed = data.get("passed", False)
            status = "✓ PASS" if passed else "✗ FAIL"
            bar = _score_bar(score)
            row = f"  {label:<28} {score:>4.1f}/{threshold:.1f}  {bar}  {status}"
            lines.append("║" + row.ljust(width) + "║")

        lines.append("╠" + "═" * width + "╣")

        overall = gate_result.get("overall_score", 0.0)
        avg_threshold = config.THRESHOLDS["min_average"]
        avg_passed = overall >= avg_threshold
        avg_status = "✓ PASS" if avg_passed else "✗ FAIL"
        overall_bar = _score_bar(overall)
        overall_row = f"  {'OVERALL AVERAGE':<28} {overall:>4.1f}/{avg_threshold:.1f}  {overall_bar}  {avg_status}"
        lines.append("║" + overall_row.ljust(width) + "║")

        lines.append("╠" + "═" * width + "╣")

        gate_passed = gate_result.get("pass", False)
        verdict = "  VERDICT: ✓ APPROVED — All thresholds met" if gate_passed else "  VERDICT: ✗ FAILED — Revision required"
        lines.append("║" + verdict.ljust(width) + "║")

        failed = gate_result.get("failed_thresholds", [])
        if failed and not gate_passed:
            lines.append("║" + "".ljust(width) + "║")
            lines.append("║" + "  Failed thresholds:".ljust(width) + "║")
            for f in failed:
                dim = f.get("dimension", "?")
                gap = f.get("gap", 0.0)
                line = f"    - {dim}: needs +{gap:.1f} points"
                lines.append("║" + line.ljust(width) + "║")

        lines.append("╚" + "═" * width + "╝")
        return "\n".join(lines)


def _dimension_label(dimension: str) -> str:
    labels = {
        "line_edit": "Line Edit Quality",
        "repetition": "Repetition & Redundancy",
        "continuity": "Continuity",
        "critical_audience": "Critical Audience",
    }
    return labels.get(dimension, dimension.replace("_", " ").title())


def _score_bar(score: float, width: int = 10) -> str:
    """Generate a simple ASCII progress bar for a score (0-10)."""
    filled = int(round(score / 10.0 * width))
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"
