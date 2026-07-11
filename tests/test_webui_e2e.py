import json
import tempfile
import threading
import unittest
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

from autoanki.generator import GenerationResult
from autoanki.storage import load_cards, save_cards
from autoanki.webui import WebState, make_server


class FakeGenerator:
    def generate(self, source, forced_tags=None):
        return [
            {
                "type": "basic",
                "front": r"Why use \(G(j\omega)\)?",
                "back": "It describes the sinusoidal steady-state frequency response.",
                "tags": ["concept"],
            }
        ]


class FakeUnclearGenerator:
    def generate_result(self, source, forced_tags=None):
        return GenerationResult(cards=[], note_to_user="Quelle unklar: bitte den fehlenden Kontext zu G(jw) ergänzen.")


class WebUiE2ETests(unittest.TestCase):
    def post(self, url, path, data=None):
        body = urllib.parse.urlencode(data or {}).encode("utf-8")
        request = urllib.request.Request(f"{url}{path}", data=body, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")

    def get(self, url, path):
        with urllib.request.urlopen(f"{url}{path}", timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")

    def multipart_post(self, url, path, fields=None, files=None):
        boundary = f"----autoanki-{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in (fields or {}).items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
        for field_name, filename, content_type, data in (files or []):
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8")
            )
            body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
            body.extend(data)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        request = urllib.request.Request(
            f"{url}{path}",
            data=bytes(body),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8", errors="replace")

    def test_webui_capture_preview_accept_export_and_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(
                cards_path=tmp_path / "cards.json",
                output_path=tmp_path / "rt_quickcap.apkg",
                generator_factory=lambda: FakeGenerator(),
                capture_fn=lambda: {"text": "Bode uses G(j omega).", "image_b64": None},
            )
            server = make_server("127.0.0.1", 0, state)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                home = self.get(url, "/")
                self.assertIn("Capture Clipboard", home)
                self.assertIn("How does this work?", home)
                self.assertNotIn("local study tool", home)
                self.assertNotIn("saved cards /", home)
                self.assertNotIn("Capture from the clipboard or drop", home)

                self.post(url, "/capture")
                home = self.get(url, "/")
                self.assertIn("sinusoidal steady-state", home)
                self.assertIn("Pending cards", home)
                self.assertIn("katex", home.lower())
                self.assertIn("Accept</button>", home)
                self.assertNotIn("Accept Pending", home)

                self.post(url, "/accept")
                saved = load_cards(state.cards_path)
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["tags"], ["concept"])

                self.post(url, "/export")
                self.assertTrue(state.output_path.exists())
                self.assertGreater(state.output_path.stat().st_size, 1000)
                saved_after_export = load_cards(state.cards_path)
                self.assertIn("exported_at", saved_after_export[0])

                with urllib.request.urlopen(f"{url}/deck", timeout=10) as response:
                    deck = response.read()
                    self.assertEqual(response.headers["Content-Type"], "application/vnd.anki")
                    self.assertIn(
                        'attachment; filename="rt_quickcap.apkg"',
                        response.headers["Content-Disposition"],
                    )
                self.assertGreater(len(deck), 1000)

                deck_again = urllib.request.urlopen(
                    urllib.request.Request(f"{url}/export", data=b"", method="POST"),
                    timeout=10,
                ).read()
                self.assertGreater(len(deck_again), 1000)

                stopped = self.post(url, "/stop")
                self.assertIn("AutoAnki stopped", stopped)
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            finally:
                if thread.is_alive():
                    server.shutdown()
                    thread.join(timeout=5)
                server.server_close()

    def test_home_shows_recent_saved_cards_newest_first_with_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cards = []
            for index in range(12):
                cards.append(
                    {
                        "id": str(index),
                        "created": f"2026-05-24T10:{index:02d}:00+00:00",
                        "type": "basic",
                        "front": f"front {index}",
                        "back": f"back {index}",
                        "tags": ["concept"],
                        "source": {"text": None, "image_b64": None},
                        "render_ok": True,
                    }
                )
            cards_path = tmp_path / "cards.json"
            save_cards(cards, cards_path)
            state = WebState(cards_path=cards_path, output_path=tmp_path / "rt_quickcap.apkg")

            html = self.get_from_server(state, "/")
            self.assertLess(html.index("front 11"), html.index("front 2"))
            self.assertIn("1-10 of 12", html)
            self.assertNotIn("front 1</section>", html)
            self.assertNotIn("front 0</section>", html)

            older_html = self.get_from_server(state, "/?offset=10")
            self.assertIn("front 1", older_html)
            self.assertIn("front 0", older_html)
            self.assertIn("Newer", older_html)

    def test_webui_shows_llm_note_without_saving_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(
                cards_path=tmp_path / "cards.json",
                output_path=tmp_path / "rt_quickcap.apkg",
                generator_factory=lambda: FakeUnclearGenerator(),
                capture_fn=lambda: {"text": "G(jw) maybe equals something?", "image_b64": None},
            )
            server = make_server("127.0.0.1", 0, state)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                self.post(url, "/capture")
                home = self.get(url, "/")
                self.assertIn("LLM note", home)
                self.assertIn("Quelle unklar", home)
                self.assertIn("Generated 0 pending card", home)
                self.assertEqual(load_cards(state.cards_path), [])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_capture_appends_to_pending_cards_and_logs_each_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(
                cards_path=tmp_path / "cards.json",
                output_path=tmp_path / "autoanki.apkg",
                generator_factory=lambda: FakeGenerator(),
                capture_fn=lambda: {"text": "Bode uses G(j omega).", "image_b64": None},
            )
            server = make_server("127.0.0.1", 0, state)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                self.post(url, "/capture")
                self.post(url, "/capture")

                self.assertEqual(len(state.pending), 2)
                log_lines = (tmp_path / "pending_generations.jsonl").read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(log_lines), 2)
                self.assertTrue(all(len(json.loads(line)["cards"]) == 1 for line in log_lines))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_pending_card_accept_button_saves_that_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(
                cards_path=tmp_path / "cards.json",
                output_path=tmp_path / "rt_quickcap.apkg",
                generator_factory=lambda: FakeGenerator(),
                capture_fn=lambda: {"text": "Bode uses G(j omega).", "image_b64": None},
            )
            server = make_server("127.0.0.1", 0, state)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                self.post(url, "/capture")
                self.post(
                    url,
                    "/accept-one",
                    {
                        "index": "0",
                        "type": "basic",
                        "front": "Edited front",
                        "back": "Edited back",
                        "tags": "concept",
                    },
                )
                saved = load_cards(state.cards_path)
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["front"], "Edited front")
                self.assertEqual(state.pending, [])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_help_page_explains_usage_and_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(cards_path=tmp_path / "cards.json", output_path=tmp_path / "rt_quickcap.apkg")
            html = self.get_from_server(state, "/help")
            self.assertIn("Put useful study material in", html)
            self.assertIn("screenshot of handwriting", html)
            self.assertIn("useful part of an LLM answer", html)
            self.assertIn("API keys stay in your local", html)
            self.assertIn("Back to AutoAnki", html)

    def test_provider_settings_form_is_rendered_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(cards_path=tmp_path / "cards.json", output_path=tmp_path / "rt_quickcap.apkg")
            server = make_server("127.0.0.1", 0, state)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                home = self.get(url, "/")
                self.assertIn('name="provider"', home)
                self.assertIn('name="model"', home)
                self.assertIn('name="target_card_count"', home)
                self.assertIn("Load models", home)
                self.assertIn('<details class="provider-panel" data-provider-panel>', home)
                self.assertNotIn('<details class="provider-panel" data-provider-panel open>', home)

                with patch("autoanki.webui.set_provider_model", return_value=tmp_path / ".env") as set_provider_model:
                    self.post(
                        url,
                        "/config",
                        {"provider": "openrouter", "model": "google/gemini-3.5-flash", "target_card_count": "4"},
                    )
                set_provider_model.assert_called_once_with("openrouter", "google/gemini-3.5-flash", "4")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_models_route_returns_provider_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(cards_path=tmp_path / "cards.json", output_path=tmp_path / "rt_quickcap.apkg")
            with patch("autoanki.webui.list_provider_models", return_value=["model-a", "model-b"]):
                html = self.get_from_server(state, "/models?provider=openrouter")
            self.assertIn('"model-a"', html)
            self.assertIn('"model-b"', html)

    def test_webui_upload_text_file_generates_pending_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = WebState(
                cards_path=tmp_path / "cards.json",
                output_path=tmp_path / "rt_quickcap.apkg",
                generator_factory=lambda: FakeGenerator(),
                capture_fn=lambda: {"text": "unused clipboard", "image_b64": None},
            )
            server = make_server("127.0.0.1", 0, state)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                self.multipart_post(
                    url,
                    "/upload",
                    fields={"text": "Dropped plain text about Bode plots."},
                    files=[("files", "notes.md", "text/markdown", b"Frequency response notes.")],
                )
                home = self.get(url, "/")
                self.assertIn("Pending cards", home)
                self.assertIn("sinusoidal steady-state", home)
                self.assertIn("Drop notes here", home)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def get_from_server(self, state, path):
        server = make_server("127.0.0.1", 0, state)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            return self.get(f"http://127.0.0.1:{server.server_port}", path)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
