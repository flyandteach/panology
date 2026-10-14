import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diagnostics import analyze, to_markdown  # noqa: E402

DRAFT = """The study found a clear effect. The effect was large. The effect was robust. The effect was replicated.

Vertiport demand depends on fleet size and charging time. Vertiport demand depends on fleet size and charging time, among other factors.

The study found that peak power exceeds energy needs during turnaround."""


def test_paragraph_and_sentence_ids():
    result = analyze(DRAFT)
    assert [p["id"] for p in result["paragraphs"]] == ["P1", "P2", "P3"]
    assert result["paragraphs"][0]["sentences"] == 4
    assert result["sentence_length"]["count"] == 7


def test_flags_short_runs_openings_and_phrases():
    result = analyze(DRAFT)
    assert ["P1.S1", "P1.S2", "P1.S3", "P1.S4"] in result["short_sentence_runs"]
    openings = {r["opening"]: r for r in result["repeated_openings"]}
    assert openings["the effect"]["locations"] == ["P1.S2", "P1.S3", "P1.S4"]
    phrases = {r["phrase"] for r in result["recurring_phrases"]}
    assert "vertiport demand depends on" in phrases


def test_similar_paragraphs_and_empty_input():
    text = (
        "Battery degradation reduces available range for each aircraft over many cycles.\n\n"
        "Battery degradation over many cycles reduces available range for each aircraft type."
    )
    result = analyze(text)
    assert result["similar_paragraphs"][0]["pair"] == ["P1", "P2"]
    empty = analyze("")
    assert empty["paragraphs"] == [] and empty["sentence_length"] == {}
    assert "Method and limitations" in to_markdown(empty, "empty")
