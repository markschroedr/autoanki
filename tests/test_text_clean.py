import unittest

from autoanki.text_clean import clean_text


class TextCleanTests(unittest.TestCase):
    def test_repairs_common_utf8_as_cp1252_mojibake(self):
        self.assertEqual(clean_text("fÃ¼r G(jÏ‰) und Ãœbertragung"), "für G(jω) und Übertragung")

    def test_repairs_mixed_valid_unicode_and_mojibake(self):
        self.assertEqual(clean_text("Während G(jÏ‰) stationär ist"), "Während G(jω) stationär ist")

    def test_leaves_normal_text_unchanged(self):
        self.assertEqual(clean_text("für G(jω)"), "für G(jω)")


if __name__ == "__main__":
    unittest.main()
