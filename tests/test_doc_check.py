#!/usr/bin/env python3
"""Tests for scripts/doc-check.py, the advisory human-docs check.

The cases are the mistakes review caught in Homelab-Skills#1109 ("smart device",
"internal DNS") plus the false alarms the first run raised on real repos (a
repo's own name, an avoided word inside a glossary term). Stdlib only.

    python3 tests/test_doc_check.py
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # a cached .pyc would hide an edit made in the same second
SPEC = importlib.util.spec_from_file_location(
    "doc_check", Path(__file__).resolve().parents[1] / "scripts/doc-check.py")
dc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dc)

GLOSSARY = """# House Display

**Detected device**:
A thing Home Assistant marks for the floor plan.
_Avoid_: Smart device, entity (the HA word),
thing

**Internal namespace**:
The internal zones.
_Avoid_: internal DNS, calling every zone on the estate a namespace

**Speaker**:
A thing that plays sound.
_Avoid_: device, msd
"""

WORDS = lambda n: " ".join(["word"] * (n - 1)) + " end."


class DocCheck(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd()
        self.dir = Path(tempfile.mkdtemp()) / "msd"
        self.dir.mkdir()
        os.chdir(self.dir)
        (self.dir / "CONTEXT.md").write_text(GLOSSARY)

    def tearDown(self):
        os.chdir(self.old)

    def run_on(self, text, *flags):
        (self.dir / "README.md").write_text(text)
        avoids, names = dc.glossary()
        added = dc.added_lines("README.md", list(flags) if flags else None)
        return dc.check("README.md", avoids, names, added)

    def test_glossary_parse(self):
        avoids, names = dc.glossary()
        self.assertEqual(avoids["smart device"], "Detected device")
        self.assertIn("thing", avoids)            # a wrapped _Avoid_ line
        self.assertNotIn("entity (the ha word)", avoids)
        self.assertIn("entity", avoids)            # parenthetical stripped
        self.assertFalse(any("namespace" in a for a in avoids))  # prose item dropped
        self.assertIn("msd", names)                # the repo's own name

    def test_avoid_word_flagged(self):
        w = self.run_on("It shows smart device details.\n\nIt edits internal DNS.\n")
        self.assertEqual(len(w), 2, w)
        self.assertIn('avoid "smart device"', w[0])
        self.assertIn("README.md:3:", w[1])

    def test_allowed_names_and_code_not_flagged(self):
        text = ("# MSD\n\nEach detected device has a pin. Run `smart device` now.\n\n"
                "```\ninternal DNS\n```\n\n| internal DNS |\n")
        self.assertEqual(self.run_on(text), [])

    def test_sentence_and_step_length(self):
        text = f"{WORDS(25)}\n\n{WORDS(26)}\n\n1. {WORDS(20)}\n2. {WORDS(21)}\n"
        w = self.run_on(text)
        self.assertEqual(len(w), 2, w)
        self.assertIn("README.md:3: sentence has 26 words", w[0])
        self.assertIn("README.md:6: step has 21 words", w[1])

    def test_staged_checks_only_added_lines(self):
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                                         *a], cwd=self.dir, check=True, capture_output=True)
        git("init", "-q")
        (self.dir / "README.md").write_text(f"Old smart device text.\n\n{WORDS(30)}\n")
        git("add", "README.md")
        git("commit", "-qm", "old")
        (self.dir / "README.md").write_text(
            f"Old smart device text.\n\n{WORDS(30)}\n\nNew internal DNS text.\n")
        git("add", "README.md")
        w = dc.check("README.md", *dc.glossary(), dc.added_lines("README.md", ["--cached"]))
        self.assertEqual(len(w), 1, w)
        self.assertIn('README.md:5: avoid "internal dns"', w[0])

    def test_which_files_are_human_docs(self):
        for name in ("docs/how-to/x.md", "docs/agents/x.md", "AGENTS.md", "sub/README.md"):
            (self.dir / name).parent.mkdir(parents=True, exist_ok=True)
            (self.dir / name).write_text("x\n")
        self.assertTrue(dc.is_human_doc("docs/how-to/x.md"))
        self.assertTrue(dc.is_human_doc("sub/README.md"))
        self.assertFalse(dc.is_human_doc("docs/agents/x.md"))
        self.assertFalse(dc.is_human_doc("AGENTS.md"))
        self.assertFalse(dc.is_human_doc("CONTEXT.md"))

    def test_advisory_exit_zero(self):
        (self.dir / "README.md").write_text("It shows smart device details.\n")
        self.assertEqual(dc.main(["README.md"]), 0)


if __name__ == "__main__":
    unittest.main()
