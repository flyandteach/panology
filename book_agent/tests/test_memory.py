"""
Tests for utils/memory.py — ProjectMemory class.
"""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.memory import ProjectMemory


class TestProjectMemoryCreate(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_memory(self) -> ProjectMemory:
        os.makedirs(os.path.join(self.tmpdir, "memory"), exist_ok=True)
        m = ProjectMemory.load(self.tmpdir)
        m.create_new(
            title="Test Book",
            genre="nonfiction",
            audience="general readers",
            tone="analytical",
            style_profile="Clear and direct",
        )
        return m

    def test_create_new_sets_title(self):
        m = self._make_memory()
        self.assertEqual(m.project["title"], "Test Book")

    def test_create_new_sets_status_planning(self):
        m = self._make_memory()
        self.assertEqual(m.project["status"], "planning")

    def test_create_new_sets_all_fields(self):
        m = self._make_memory()
        proj = m.project
        self.assertEqual(proj["genre"], "nonfiction")
        self.assertEqual(proj["audience"], "general readers")
        self.assertEqual(proj["tone"], "analytical")
        self.assertEqual(proj["style_profile"], "Clear and direct")

    def test_empty_approved_sections_on_create(self):
        m = self._make_memory()
        self.assertEqual(m.get_approved_sections(), [])

    def test_empty_outline_on_create(self):
        m = self._make_memory()
        self.assertEqual(m.get_outline(), [])


class TestProjectMemorySaveLoad(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "memory"), exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_reload(self):
        m = ProjectMemory.load(self.tmpdir)
        m.create_new("Save Test", "fiction", "young adults", "whimsical", "Playful")
        m.save()

        m2 = ProjectMemory.load(self.tmpdir)
        self.assertEqual(m2.project["title"], "Save Test")
        self.assertEqual(m2.project["genre"], "fiction")

    def test_memory_file_exists_after_save(self):
        m = ProjectMemory.load(self.tmpdir)
        m.create_new("X", "Y", "Z", "A", "B")
        m.save()
        self.assertTrue(os.path.exists(m.path))

    def test_memory_file_is_valid_json(self):
        m = ProjectMemory.load(self.tmpdir)
        m.create_new("JSON Test", "nonfiction", "professionals", "formal", "Dense")
        m.save()
        with open(m.path, "r") as fh:
            data = json.load(fh)
        self.assertIn("project", data)
        self.assertIn("memory", data)


class TestProjectMemoryApprovedSections(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "memory"), exist_ok=True)
        self.m = ProjectMemory.load(self.tmpdir)
        self.m.create_new("Book", "nonfiction", "anyone", "neutral", "Plain")
        self.m.set_outline([
            {"id": "intro", "title": "Introduction", "status": "pending"},
            {"id": "ch01", "title": "Chapter 1", "status": "pending"},
        ])

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_approved_section(self):
        self.m.add_approved_section(
            section_id="intro",
            title="Introduction",
            summary="This is the intro summary.",
            content="Full introduction content goes here. " * 20,
        )
        approved = self.m.get_approved_sections()
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["id"], "intro")
        self.assertEqual(approved[0]["title"], "Introduction")

    def test_add_approved_section_records_word_count(self):
        content = "word " * 100
        self.m.add_approved_section("ch01", "Chapter 1", "Summary.", content)
        approved = self.m.get_approved_sections()
        self.assertEqual(approved[0]["word_count"], 100)

    def test_add_approved_section_marks_outline_status(self):
        self.m.add_approved_section("intro", "Introduction", "Summary.", "content")
        outline = self.m.get_outline()
        intro = next(s for s in outline if s["id"] == "intro")
        self.assertEqual(intro["status"], "approved")

    def test_multiple_approved_sections(self):
        self.m.add_approved_section("intro", "Introduction", "S1", "content1")
        self.m.add_approved_section("ch01", "Chapter 1", "S2", "content2")
        self.assertEqual(len(self.m.get_approved_sections()), 2)

    def test_get_next_unstarted_section(self):
        section = self.m.get_next_unstarted_section()
        self.assertIsNotNone(section)
        self.assertEqual(section["id"], "intro")

    def test_get_next_unstarted_after_approval(self):
        self.m.add_approved_section("intro", "Introduction", "S", "c")
        section = self.m.get_next_unstarted_section()
        self.assertEqual(section["id"], "ch01")

    def test_get_next_unstarted_returns_none_when_all_done(self):
        self.m.add_approved_section("intro", "Introduction", "S", "c")
        self.m.add_approved_section("ch01", "Chapter 1", "S", "c")
        section = self.m.get_next_unstarted_section()
        self.assertIsNone(section)


class TestProjectMemoryPhrases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "memory"), exist_ok=True)
        self.m = ProjectMemory.load(self.tmpdir)
        self.m.create_new("B", "g", "a", "t", "s")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_update_phrases_to_avoid(self):
        self.m.update_phrases_to_avoid(["in today's world", "it goes without saying"])
        pta = self.m.data["memory"]["phrases_to_avoid"]
        self.assertIn("in today's world", pta)
        self.assertIn("it goes without saying", pta)

    def test_phrases_to_avoid_deduplicates(self):
        self.m.update_phrases_to_avoid(["phrase one"])
        self.m.update_phrases_to_avoid(["phrase one", "phrase two"])
        pta = self.m.data["memory"]["phrases_to_avoid"]
        self.assertEqual(pta.count("phrase one"), 1)

    def test_update_used_metaphors(self):
        self.m.update_used_metaphors(["life is a river", "time is money"])
        um = self.m.data["memory"]["used_metaphors"]
        self.assertIn("life is a river", um)

    def test_update_key_terms(self):
        self.m.update_key_terms({"recursion": "a function that calls itself"})
        kt = self.m.data["memory"]["key_terms"]
        self.assertEqual(kt["recursion"], "a function that calls itself")

    def test_add_revision_history(self):
        self.m.add_revision_history({"section_id": "intro", "action": "approved"})
        hist = self.m.data["revision_history"]
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["action"], "approved")
        self.assertIn("timestamp", hist[0])

    def test_get_context_for_agent_returns_string(self):
        ctx = self.m.get_context_for_agent()
        self.assertIsInstance(ctx, str)
        self.assertIn("PROJECT CONTEXT", ctx)


if __name__ == "__main__":
    unittest.main()
