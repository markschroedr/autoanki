import unittest

from autoanki.preview import render_preview_html


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

    def test_preview_places_basic_source_image_before_back_when_requested(self):
        html = render_preview_html(
            [
                {
                    "type": "basic",
                    "front": "Which curve is correct?",
                    "back": "Curve II.",
                    "tags": ["concept"],
                    "render_ok": True,
                    "source": {
                        "image_b64": "front-image",
                        "image_side": "front",
                    },
                }
            ]
        )

        image_position = html.index("data:image/png;base64,front-image")
        back_position = html.index('<section class="back">')
        self.assertLess(image_position, back_position)

    def test_preview_leaves_math_for_browser_typesetting(self):
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
        self.assertIn(r"\(G(s)\)", html)
        self.assertNotIn('<span class="katex">G(s)</span>', html)

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

    def test_preview_renders_math_inside_clozes_and_anki_line_breaks(self):
        html = render_preview_html(
            [
                {
                    "type": "cloze",
                    "front": (
                        r"Für \(\dot{x}=Ax+bu\) ergibt sich<br><br>"
                        r"{{c1::\(u=-K_{RC}^{T}x\)}}<br>und damit<br>"
                        r"{{c2::\(\dot{x}=(A-bK_{RC}^{T})x\)}}."
                    ),
                    "back": "",
                    "tags": ["formula"],
                    "render_ok": True,
                    "source": {"image_b64": None},
                }
            ]
        )

        self.assertEqual(html.count('class="cloze-answer"'), 2)
        self.assertIn(r"\(u=-K_{RC}^{T}x\)", html)
        self.assertIn("ergibt sich<br><br>", html)
        self.assertNotIn("{{c1::", html)
        self.assertNotIn("&lt;br&gt;", html)

    def test_preview_escapes_arbitrary_html(self):
        html = render_preview_html(
            [
                {
                    "type": "basic",
                    "front": '<script>alert("x")</script><br>safe',
                    "back": "answer",
                    "tags": ["concept"],
                    "render_ok": True,
                    "source": {"image_b64": None},
                }
            ]
        )

        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;<br>safe', html)

if __name__ == "__main__":
    unittest.main()
