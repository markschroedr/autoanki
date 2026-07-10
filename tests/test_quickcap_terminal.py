import unittest

from autoanki.quickcap import render_terminal_math


class QuickcapTerminalTests(unittest.TestCase):
    def test_terminal_math_simplifies_common_symbols(self):
        text = render_terminal_math(r"Substitute \(s = j\omega\) and use \[\frac{1}{s+1}\].")
        self.assertIn("s = jω", text)
        self.assertIn("(1)/(s+1)", text)
        self.assertNotIn(r"\(", text)


if __name__ == "__main__":
    unittest.main()
