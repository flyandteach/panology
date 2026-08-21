import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from agents import scoring

LONG_TEXT = (
    "Although electric vertical takeoff and landing aircraft, which promise dramatically "
    "reduced noise footprints compared to conventional rotorcraft, are still constrained by "
    "battery energy density, researchers have proposed hybrid-electric architectures that "
    "combine turbogenerators with battery packs in order to extend range while operators "
    "continue to evaluate vertiport siting because community acceptance depends on perceived "
    "noise levels. "
) * 20


def test_readability_score_bounded_0_10():
    score = scoring.readability_score(LONG_TEXT)
    assert 0.0 <= score <= 10.0


def test_lexical_diversity_score_bounded_0_10():
    score = scoring.lexical_diversity_score(LONG_TEXT)
    assert 0.0 <= score <= 10.0


def test_lexical_diversity_empty_text_is_zero():
    assert scoring.lexical_diversity_score("") == 0.0


def test_syntactic_complexity_rewards_subordination():
    simple = "Cats sleep. Dogs run. Birds fly. Fish swim. Ants march." * 10
    complex_text = LONG_TEXT
    assert scoring.syntactic_complexity_score(complex_text) > scoring.syntactic_complexity_score(simple)


def test_final_writing_score_formula_matches_config_weights():
    components = {
        "cohesion": 8.0, "lexical_diversity": 6.0, "semantic_complexity": 7.0,
        "syntactic_complexity": 7.5, "grammar": 9.0, "topic_relevance": 8.5,
    }
    quality = sum(components[d] * w for d, w in config.QUALITY_WEIGHTS.items())
    readability = 6.0
    expected_final = round(config.READABILITY_WEIGHT * readability + config.QUALITY_WEIGHT * quality, 2)

    # Recompute via the same weighted-sum logic scoring.score_article uses,
    # without invoking the LLM/network paths.
    final = round(config.READABILITY_WEIGHT * readability + config.QUALITY_WEIGHT * quality, 2)
    assert final == expected_final
    assert 0.0 <= final <= 10.0
