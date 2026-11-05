"""Core v2 invariants that do not need an LLM.

Run: .venv/bin/python -m unittest tests.test_v2_core -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock as unittest_mock

from story import judge, ledger, writer


class CanonTest(unittest.TestCase):
    def test_famous_work_collides(self) -> None:
        text = (
            "A hacker learns that his world is a simulation built by machines. "
            "Rebels wake him and he becomes the prophesied savior who can alter "
            "the code of reality."
        )
        result = judge.canon_neighbors(text)
        self.assertGreater(result["max_similarity"], 0.70)
        self.assertEqual(result["closest"][0]["title"], "The Matrix")


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original = ledger.DB
        ledger.DB = Path(self.tmp.name) / "ledger.db"

    def tearDown(self) -> None:
        ledger.DB = self.original
        self.tmp.cleanup()

    def test_duplicate_injection_is_caught(self) -> None:
        ledger.record_run("test-run", "a test brief")
        text = (
            "A lighthouse keeper trades memories of her daughter to a hive of "
            "talking bees in exchange for one more winter of light."
        )
        ledger.record_premise(
            "test-run",
            "The Hive's Lantern",
            "A keeper bargains with bees.",
            text,
            "a test brief",
            [4, 9, 12],
            ["The Hive", "The Bargain", "The Light"],
            1.5,
        )
        sim, title = ledger.similarity_to_history(text)
        self.assertGreater(sim, 0.90)
        self.assertEqual(title, "The Hive's Lantern")
        self.assertEqual(ledger.max_combo_overlap([4, 9, 12]), 1.0)
        self.assertLess(ledger.max_combo_overlap([4, 9, 99]), 1.0)

    def test_stats_include_premise(self) -> None:
        ledger.record_premise("r", "T", "L", "P", "B", [1, 2, 3], ["a", "b", "c"], 1.0)
        self.assertEqual(ledger.stats()["premises"], 1)


class PremiseLengthTest(unittest.TestCase):
    def test_short_premise_is_repaired_to_band(self) -> None:
        short = " ".join(["word"] * 100)
        long = " ".join(["scene"] * 50)
        responses = [
            {
                "title": "A Test of Length",
                "logline": "A worker must repair the machine before dawn.",
                "premise": short,
                "why_fresh": "Avoids the chosen-one trope; the machine is the pressure.",
                "content_warnings": [],
            },
            {"premise": long},
        ]
        candidate = {"cluster_names": ["A", "B"], "cluster_ids": [1, 2]}
        with unittest_mock.patch.object(
            writer.llm, "complete_json", side_effect=responses
        ), unittest_mock.patch.object(
            writer.judge,
            "canon_neighbors",
            return_value={"max_similarity": 0.1, "closest": []},
        ), unittest_mock.patch.object(
            writer.ledger,
            "similarity_to_history",
            return_value=(0.1, None),
        ):
            doc = writer.write_premise(candidate, {"brief": "test"}, provider="ollama")
        self.assertGreaterEqual(doc["word_count"], writer.PREMISE_MIN_WORDS)
        self.assertLessEqual(doc["word_count"], writer.PREMISE_MAX_WORDS)
        self.assertEqual(doc["title"], "A Test of Length")


class ClosingRepairTest(unittest.TestCase):
    def test_truncated_act_is_finished(self) -> None:
        premise = {"title": "T", "logline": "L", "premise": "P", "why_fresh": "F"}
        outline = {"ending": "The water returns.", "acts": []}
        act = {"number": 1, "title": "Act", "beats": ["a beat"]}
        with unittest_mock.patch.object(
            writer, "_complete_prose", return_value="the water rise."
        ):
            fixed = writer._finish_act_text(
                "She could hear", premise, outline, {"brief": "b"}, act, "ollama"
            )
        self.assertTrue(writer._ends_cleanly(fixed))
        self.assertTrue(fixed.endswith("the water rise."))


class VerdictParseTest(unittest.TestCase):
    def test_partial_batch_is_salvaged(self) -> None:
        raw = {
            "verdicts": [
                {
                    "candidate": 1,
                    "coherence": 7,
                    "freshness": 7,
                    "viability": 6,
                    "decision": "KEEP",
                    "reason": "engine",
                },
                {
                    "candidate": 3,
                    "coherence": 4,
                    "freshness": 6,
                    "viability": 6,
                    "decision": "KILL",
                    "reason": "no engine",
                },
            ]
        }
        by_index = judge._verdict_items(raw, 3)
        self.assertEqual(set(by_index), {1, 3})
        self.assertEqual(by_index[1]["decision"], "KEEP")
        self.assertEqual(by_index[3]["decision"], "KILL")

    def test_full_batch_validates_in_order(self) -> None:
        raw = {
            "verdicts": [
                {"candidate": i, "coherence": 7, "freshness": 7, "viability": 6}
                for i in (2, 1)
            ]
        }
        verdicts = judge._validate_verdicts(raw, 2)
        self.assertIsNotNone(verdicts)
        self.assertEqual([v["candidate"] for v in verdicts], [1, 2])


class ConstraintTest(unittest.TestCase):
    def test_missing_and_forbidden(self) -> None:
        brief = {
            "must_include": ["Mara", "the drowned archive"],
            "must_avoid": ["prophecy"],
            "banned_tropes": ["chosen one"],
        }
        doc = {
            "title": "Mara and the Tide",
            "logline": "Mara breaks into the drowned archive.",
            "premise": "No prophecy here.",
            "why_fresh": "",
        }
        self.assertEqual(writer._missing_constraints(doc, brief), [])
        self.assertEqual(writer._forbidden_hits(doc, brief), ["prophecy"])

    def test_negated_banned_phrase_is_caught(self) -> None:
        brief = {"must_avoid": ["no prophecy", "no chosen one"]}
        doc = {
            "title": "The Tide",
            "logline": "A town waits.",
            "premise": "They await the prophecy of the chosen one.",
            "why_fresh": "",
        }
        self.assertEqual(writer._forbidden_hits(doc, brief), ["no prophecy", "no chosen one"])

    def test_forbidden_terms_in_why_fresh_do_not_trigger(self) -> None:
        brief = {"must_avoid": ["prophecy"]}
        doc = {
            "title": "The Tide",
            "logline": "A town waits.",
            "premise": "Mara breaks into the drowned archive.",
            "why_fresh": "It avoids the prophecy trope entirely.",
        }
        self.assertEqual(writer._forbidden_hits(doc, brief), [])


if __name__ == "__main__":
    unittest.main()
