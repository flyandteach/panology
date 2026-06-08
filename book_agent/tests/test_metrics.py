"""
Tests for utils/metrics.py — TextMetrics class.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.metrics import TextMetrics

SAMPLE_TEXT = """The history of science is not a smooth arc of progress. It lurches and stumbles.
Great discoveries are often ignored for decades. Brilliant theories get buried under institutional inertia.

Consider what happened when Barry Marshall proposed that ulcers were caused by bacteria.
The medical establishment dismissed him. He was young, he was unknown, and his claim contradicted forty years
of accepted teaching. The prevailing explanation blamed stress. Stress was the cause. Stress was the answer.
Everyone agreed.

Marshall did not accept the consensus. Instead, he drank a beaker of Helicobacter pylori and gave himself an ulcer.
He documented the process, treated himself with antibiotics, and recovered fully.
It was one of the most audacious self-experiments in the history of medicine.

The point is not that established science is usually wrong. It is not. The point is that it is sometimes wrong,
and that the people who notice tend to be dismissed rather than celebrated — at least at first.
This pattern repeats itself. The outsider arrives with evidence. The insiders resist. Eventually, if the evidence
is strong enough, consensus shifts. But the shift takes time, and during that time, the correct answer sits
available but unaccepted."""

REPETITIVE_TEXT = """The system was broken. The system had been broken for years. The system needed fixing.
Everyone knew the system was broken. The system could not fix itself. Only outside pressure could fix the system.
The system resisted change. The system had always resisted change. The system would continue to resist change."""


class TestTextMetricsBasic(unittest.TestCase):

    def setUp(self):
        self.metrics = TextMetrics()

    def test_returns_dict(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertIsInstance(result, dict)

    def test_word_count_reasonable(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        wc = result["word_count"]
        self.assertGreater(wc, 100)
        self.assertLess(wc, 400)

    def test_sentence_count_positive(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertGreater(result["sentence_count"], 5)

    def test_paragraph_count(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        # Sample text has 4 paragraphs separated by blank lines
        self.assertGreaterEqual(result["paragraph_count"], 3)

    def test_avg_sentence_length_positive(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertGreater(result["avg_sentence_length"], 0)

    def test_type_token_ratio_between_0_and_1(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        ttr = result["type_token_ratio"]
        self.assertGreater(ttr, 0.0)
        self.assertLessEqual(ttr, 1.0)

    def test_readability_score_is_float(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertIsInstance(result["readability_score"], float)

    def test_passive_voice_estimate_non_negative(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertGreaterEqual(result["passive_voice_estimate"], 0)

    def test_repeated_3grams_is_list(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertIsInstance(result["repeated_3grams"], list)

    def test_repeated_4grams_is_list(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertIsInstance(result["repeated_4grams"], list)

    def test_repeated_sentence_openings_is_list(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertIsInstance(result["repeated_sentence_openings"], list)

    def test_top_repeated_words_is_list(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertIsInstance(result["top_repeated_words"], list)

    def test_top_repeated_words_max_10(self):
        result = self.metrics.analyze(SAMPLE_TEXT)
        self.assertLessEqual(len(result["top_repeated_words"]), 10)


class TestTextMetricsRepetition(unittest.TestCase):

    def setUp(self):
        self.metrics = TextMetrics()

    def test_repetitive_text_has_low_ttr(self):
        result = self.metrics.analyze(REPETITIVE_TEXT)
        # Highly repetitive text should have low type-token ratio
        self.assertLess(result["type_token_ratio"], 0.6)

    def test_repetitive_text_detects_ngrams(self):
        result = self.metrics.analyze(REPETITIVE_TEXT)
        # "the system" should appear many times — should show up in 3-grams or repeated words
        top_words = [w for w, _ in result["top_repeated_words"]]
        self.assertIn("system", top_words)

    def test_sentence_opening_repetition(self):
        # All sentences in REPETITIVE_TEXT start with "The"
        result = self.metrics.analyze(REPETITIVE_TEXT)
        openings = result["repeated_sentence_openings"]
        # "the" or "The" should appear as a repeated opening
        lower_openings = [o.lower() for o in openings]
        self.assertIn("the", lower_openings)


class TestTextMetricsEmpty(unittest.TestCase):

    def setUp(self):
        self.metrics = TextMetrics()

    def test_empty_string_returns_zeros(self):
        result = self.metrics.analyze("")
        self.assertEqual(result["word_count"], 0)
        self.assertEqual(result["sentence_count"], 0)
        self.assertEqual(result["readability_score"], 0.0)

    def test_whitespace_only_returns_zeros(self):
        result = self.metrics.analyze("   \n\n   ")
        self.assertEqual(result["word_count"], 0)


class TestTextMetricsShortText(unittest.TestCase):

    def setUp(self):
        self.metrics = TextMetrics()

    def test_single_sentence(self):
        result = self.metrics.analyze("The quick brown fox jumps over the lazy dog.")
        self.assertGreater(result["word_count"], 0)
        self.assertGreater(result["sentence_count"], 0)

    def test_all_required_keys_present(self):
        required_keys = [
            "word_count", "sentence_count", "avg_sentence_length",
            "sentence_length_std", "paragraph_count", "avg_paragraph_length",
            "paragraph_length_std", "type_token_ratio", "repeated_3grams",
            "repeated_4grams", "repeated_sentence_openings", "top_repeated_words",
            "readability_score", "passive_voice_estimate",
        ]
        result = self.metrics.analyze("Short text to test.")
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")


if __name__ == "__main__":
    unittest.main()
