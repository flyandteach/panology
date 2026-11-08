import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils import state


def test_key_is_stable_and_case_insensitive():
    k1 = state._key_for("A Title", "http://Example.com/x")
    k2 = state._key_for("a title", "http://example.com/x")
    assert k1 == k2


def test_key_differs_for_different_articles():
    k1 = state._key_for("Title One", "http://example.com/1")
    k2 = state._key_for("Title Two", "http://example.com/2")
    assert k1 != k2


def test_mark_and_check_seen():
    seen = {}
    assert not state.is_seen(seen, "Some Article", "http://example.com/a")
    state.mark_seen(seen, "Some Article", "http://example.com/a")
    assert state.is_seen(seen, "Some Article", "http://example.com/a")
    assert not state.is_seen(seen, "Some Other Article", "http://example.com/b")
