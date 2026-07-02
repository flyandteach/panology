from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evtol_fleet.opensky import iter_windows


def test_iter_windows_single_window_when_under_limit():
    windows = list(iter_windows(0, 1000, max_window_seconds=2000))
    assert windows == [(0, 1000)]


def test_iter_windows_splits_long_ranges():
    windows = list(iter_windows(0, 100, max_window_seconds=30))
    assert windows == [(0, 30), (30, 60), (60, 90), (90, 100)]


def test_iter_windows_covers_full_range_without_gaps_or_overlap():
    begin, end = 0, 1000
    windows = list(iter_windows(begin, end, max_window_seconds=37))
    assert windows[0][0] == begin
    assert windows[-1][1] == end
    for (start_a, end_a), (start_b, _end_b) in zip(windows, windows[1:]):
        assert end_a == start_b  # contiguous, no gap or overlap


def test_iter_windows_empty_range_yields_nothing():
    assert list(iter_windows(100, 100)) == []
