import subprocess
import unittest
from unittest.mock import patch

from autoanki.preview import _render_katex, render_preview_html


class PreviewTests(unittest.TestCase):
    def test_preview_contains_mathjax_and_clipboard_image(self):
        html = render_preview_html(
            [
                {
                    "type": "basic",
                    "front": r"What is \(G(s)\)?",
                    "back": "Transfer function",
                    "tags": ["concept"],
                    "render_ok": True,
                    "source": {"image_b64": "abc123"},
                }
            ]
        )
        self.assertIn("mathjax@3", html)
        self.assertIn("data:image/png;base64,abc123", html)
        self.assertIn(r"What is \(G(s)\)?", html)

    @patch("autoanki.preview._render_katex", return_value='<span class="katex">G(s)</span>')
    def test_preview_pre_renders_math(self, _render_katex):
        html = render_preview_html(
            [
                {
                    "type": "basic",
                    "front": r"What is \(G(s)\)?",
                    "back": r"\[G(j\omega)\]",
                    "tags": ["concept"],
                    "render_ok": True,
                    "source": {"image_b64": None},
                }
            ]
        )
        self.assertIn('<span class="katex">G(s)</span>', html)
        self.assertNotIn(r"\(G(s)\)", html)

    def test_preview_renders_cloze_without_raw_markup(self):
        html = render_preview_html(
            [
                {
                    "type": "cloze",
                    "front": "Das ist {{c1::stationär}}.",
                    "back": "",
                    "tags": ["concept"],
                    "render_ok": True,
                    "source": {"image_b64": None},
                }
            ]
        )
        self.assertIn("cloze-answer", html)
        self.assertIn("stationär", html)
        self.assertNotIn("{{c1::", html)

    @patch("autoanki.preview._katex_executable", return_value="katex")
    @patch("autoanki.preview.subprocess.run")
    def test_katex_output_is_decoded_as_utf8(self, run, _executable):
        run.return_value = subprocess.CompletedProcess(["katex"], 0, '<span class="mord">ω</span>', "")
        self.assertIn("ω", _render_katex(r"\omega") or "")
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")


if __name__ == "__main__":
    unittest.main()
