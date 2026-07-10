import subprocess
import unittest
from unittest.mock import patch

from autoanki.validate import extract_math_snippets, validate_card


class ValidateTests(unittest.TestCase):
    def test_extracts_inline_and_block_math(self):
        snippets = extract_math_snippets(r"Use \(G(j\omega)\) and \[\frac{1}{s+1}\]")
        self.assertEqual(snippets, [r"G(j\omega)", r"\frac{1}{s+1}"])

    def test_cloze_requires_deletion(self):
        result = validate_card({"type": "cloze", "front": "No deletion", "back": "", "tags": ["concept"]}, check_math=False)
        self.assertFalse(result.ok)
        self.assertIn("cloze cards need at least one {{c1::...}} deletion", result.errors)

    @patch("autoanki.validate.shutil.which", return_value="katex")
    @patch("autoanki.validate.subprocess.run")
    def test_katex_error_marks_card_invalid(self, run, _which):
        run.return_value = subprocess.CompletedProcess(["katex"], 1, "", "ParseError")
        result = validate_card(
            {"type": "basic", "front": r"What is \(bad\)?", "back": "Nope", "tags": ["formula"]},
            check_math=True,
        )
        self.assertFalse(result.ok)
        self.assertIn("ParseError", result.errors)

    @patch("autoanki.validate.shutil.which", return_value=None)
    def test_missing_katex_is_warning_not_error(self, _which):
        result = validate_card(
            {"type": "basic", "front": r"What is \(G(j\omega)\)?", "back": "A frequency response.", "tags": ["formula"]},
            check_math=True,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])
        self.assertIn("math render check skipped", result.warnings[0])

    @patch.dict("os.environ", {"AUTOANKI_TAGS": "command,workflow"}, clear=True)
    def test_validation_uses_configured_tags(self):
        result = validate_card(
            {"type": "basic", "front": "How do you run a script?", "back": "Use the configured command.", "tags": ["command"]},
            check_math=False,
        )
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
