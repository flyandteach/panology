import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents import fact_check

SAMPLE_TEXT = """Introduction

This paper examines eVTOL noise certification.

References

[1] Smith, J. and Doe, A. (2021). Noise modeling for eVTOL aircraft. Journal of Air Transport, 12(3), 45-67.

[2] Lee, K. (2022). Vertiport siting criteria in dense urban cores. Aviation Policy Review, 8(1), 1-20.

Appendix A

Supplementary data tables.
"""


def test_extract_references_finds_entries():
    entries = fact_check.extract_references(SAMPLE_TEXT)
    assert len(entries) == 2
    assert "Smith" in entries[0]
    assert "Lee" in entries[1]


def test_extract_references_excludes_appendix():
    entries = fact_check.extract_references(SAMPLE_TEXT)
    assert not any("Supplementary data" in e for e in entries)


def test_extract_references_empty_when_no_section():
    assert fact_check.extract_references("Just a paper with no references section at all.") == []
