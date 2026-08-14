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

    def test_cloze_wrapper_outside_mathjax_is_allowed(self):
        result = validate_card(
            {"type": "cloze", "front": r"{{c1::\(x^2\)}}", "back": "", "tags": ["formula"]},
            check_math=False,
        )
        self.assertTrue(result.ok)

    def test_cloze_inside_mathjax_is_rejected(self):
        result = validate_card(
            {"type": "cloze", "front": r"\({{c1::x^2}}\)", "back": "", "tags": ["formula"]},
            check_math=False,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("cloze wrapper must surround MathJax delimiters" in error for error in result.errors))

    def test_invalid_math_marks_card_invalid(self):
        result = validate_card(
            {"type": "basic", "front": r"What is \(\frac{1}{\)?", "back": "Nope", "tags": ["formula"]},
            check_math=True,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("KaTeX parse error" in error for error in result.errors))

    def test_valid_math_is_checked_without_external_cli(self):
        result = validate_card(
            {"type": "basic", "front": r"What is \(G(j\omega)\)?", "back": "A frequency response.", "tags": ["formula"]},
            check_math=True,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])

    def test_unknown_math_command_marks_card_invalid(self):
        result = validate_card(
            {"type": "basic", "front": r"What is \(\unknowncommand{x}\)?", "back": "Nope", "tags": ["formula"]},
            check_math=True,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("Undefined control sequence" in error for error in result.errors))

    @patch.dict("os.environ", {"AUTOANKI_TAGS": "command,workflow"}, clear=True)
    def test_validation_uses_configured_tags(self):
        result = validate_card(
            {"type": "basic", "front": "How do you run a script?", "back": "Use the configured command.", "tags": ["command"]},
            check_math=False,
        )
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
