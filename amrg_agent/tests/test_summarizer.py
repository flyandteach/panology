import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents import summarizer


def _score_result(**overrides):
    components = {
        "cohesion": 8.0, "lexical_diversity": 8.0, "semantic_complexity": 8.0,
        "syntactic_complexity": 8.0, "grammar": 8.0, "topic_relevance": 8.0,
    }
    components.update(overrides)
    return {
        "readability_score": 8.0,
        "components": components,
        "comprehensive_writing_quality_score": 8.0,
        "final_writing_score": 8.0,
    }


def test_recommendations_target_weakest_dimensions():
    result = _score_result(lexical_diversity=2.0, grammar=3.0)
    recs = summarizer.generate_recommendations(result, top_n=2)
    assert summarizer.RECOMMENDATION_LIBRARY["lexical_diversity"] in recs
    assert summarizer.RECOMMENDATION_LIBRARY["grammar"] in recs


def test_recommendations_can_flag_readability():
    result = _score_result()
    result["readability_score"] = 1.0
    recs = summarizer.generate_recommendations(result, top_n=1)
    assert recs == [summarizer.RECOMMENDATION_LIBRARY["readability"]]
