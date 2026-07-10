import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoanki.generator import GenerationResult
from autoanki.quickcap import process_source
from autoanki.storage import load_cards


class FakeGenerator:
    def generate(self, source, forced_tags=None):
        tags = forced_tags or ["concept"]
        return [
            {
                "type": "basic",
                "front": "Why evaluate G(s) at s = j omega for Bode plots?",
                "back": "It gives the steady-state sinusoidal frequency response.",
                "tags": tags[:1],
            }
        ]


class FakeNoteGenerator:
    def generate_result(self, source, forced_tags=None):
        return GenerationResult(cards=[], note_to_user="Unklar: Das Vorzeichen der Aussage wirkt widersprüchlich.")


class E2ETests(unittest.TestCase):
    def test_capture_generation_validation_preview_accept_persists_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_path = Path(tmp) / "cards.json"

            def accept(cards, open_browser=True):
                self.assertFalse(open_browser)
                self.assertEqual(len(cards), 1)
                self.assertTrue(cards[0]["id"])
                self.assertIn("source", cards[0])
                return cards

            accepted = process_source(
                {"text": "Bode plots use G(j omega).", "image_b64": None},
                cards_path=cards_path,
                forced_tags=["concept"],
                generator=FakeGenerator(),
                review_fn=accept,
                open_browser=False,
            )

            saved = load_cards(cards_path)
            self.assertEqual(len(accepted), 1)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["tags"], ["concept"])

    def test_generation_note_is_shown_and_no_cards_are_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_path = Path(tmp) / "cards.json"
            with patch("builtins.print") as print_mock:
                accepted = process_source(
                    {"text": "contradictory capture", "image_b64": None},
                    cards_path=cards_path,
                    generator=FakeNoteGenerator(),
                    review_fn=lambda cards, open_browser=True: cards,
                    open_browser=False,
                )

            printed = "\n".join(" ".join(str(arg) for arg in call.args) for call in print_mock.call_args_list)
            self.assertEqual(accepted, [])
            self.assertEqual(load_cards(cards_path), [])
            self.assertIn("LLM note: Unklar", printed)


if __name__ == "__main__":
    unittest.main()
