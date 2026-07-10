import tempfile
import unittest
from pathlib import Path

from autoanki.build_deck import NoUnexportedCards, build_deck
from autoanki.storage import load_cards, save_cards


class BuildDeckTests(unittest.TestCase):
    def test_build_deck_marks_exported_and_skips_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cards_path = tmp_path / "cards.json"
            output_path = tmp_path / "rt_quickcap.apkg"
            save_cards(
                [
                    {
                        "id": "card-1",
                        "created": "2026-05-24T00:00:00+00:00",
                        "type": "basic",
                        "front": "What is G(s)?",
                        "back": "A transfer function.",
                        "tags": ["concept"],
                        "source": {"text": "G(s)", "image_b64": None},
                        "render_ok": True,
                    }
                ],
                cards_path,
            )

            build_deck(cards_path, output_path)
            saved = load_cards(cards_path)
            self.assertTrue(output_path.exists())
            self.assertIn("exported_at", saved[0])

            with self.assertRaises(NoUnexportedCards):
                build_deck(cards_path, output_path)

    def test_build_deck_exports_only_unexported_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cards_path = tmp_path / "cards.json"
            output_path = tmp_path / "rt_quickcap.apkg"
            save_cards(
                [
                    {
                        "id": "old-card",
                        "created": "2026-05-24T00:00:00+00:00",
                        "type": "basic",
                        "front": "Old",
                        "back": "Already exported.",
                        "tags": ["concept"],
                        "source": {"text": "old", "image_b64": None},
                        "render_ok": True,
                        "exported_at": "2026-05-24T01:00:00+00:00",
                    },
                    {
                        "id": "new-card",
                        "created": "2026-05-24T02:00:00+00:00",
                        "type": "basic",
                        "front": "New",
                        "back": "Not exported.",
                        "tags": ["concept"],
                        "source": {"text": "new", "image_b64": None},
                        "render_ok": True,
                    },
                ],
                cards_path,
            )

            build_deck(cards_path, output_path)
            saved = {card["id"]: card for card in load_cards(cards_path)}
            self.assertEqual(saved["old-card"]["exported_at"], "2026-05-24T01:00:00+00:00")
            self.assertIn("exported_at", saved["new-card"])

    def test_build_deck_can_rebuild_from_all_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cards_path = tmp_path / "cards.json"
            output_path = tmp_path / "all.apkg"
            save_cards(
                [
                    {
                        "id": "old-card",
                        "created": "2026-05-24T00:00:00+00:00",
                        "type": "basic",
                        "front": "Old",
                        "back": "Already exported.",
                        "tags": ["concept"],
                        "source": {"text": "old", "image_b64": None},
                        "render_ok": True,
                        "exported_at": "2026-05-24T01:00:00+00:00",
                    }
                ],
                cards_path,
            )

            actual_output = build_deck(cards_path, output_path, export_mode="all")

            self.assertEqual(actual_output, output_path)
            self.assertGreater(output_path.stat().st_size, 1000)

    def test_build_deck_adds_apkg_extension_to_bare_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cards_path = tmp_path / "cards.json"
            output_path = tmp_path / "deck"
            save_cards(
                [
                    {
                        "id": "card-1",
                        "created": "2026-05-24T00:00:00+00:00",
                        "type": "basic",
                        "front": "What is G(s)?",
                        "back": "A transfer function.",
                        "tags": ["concept"],
                        "source": {"text": "G(s)", "image_b64": None},
                        "render_ok": True,
                    }
                ],
                cards_path,
            )

            actual_output = build_deck(cards_path, output_path)

            self.assertEqual(actual_output, tmp_path / "deck.apkg")
            self.assertTrue(actual_output.exists())
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
