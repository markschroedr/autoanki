from __future__ import annotations

import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from autoanki.generator import OpenRouterCardGenerator
from autoanki.storage import load_cards
from autoanki.webui import WebState, make_server


def post(url: str, path: str, data: dict[str, str] | None = None) -> str:
    body = urllib.parse.urlencode(data or {}).encode("utf-8")
    request = urllib.request.Request(f"{url}{path}", data=body, method="POST")
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", errors="replace")


def get(url: str, path: str) -> bytes:
    with urllib.request.urlopen(f"{url}{path}", timeout=90) as response:
        return response.read()


def main() -> int:
    sample_text = (
        "For Bode plots, evaluate the transfer function G(s) on the imaginary "
        "axis by substituting s = j omega. This gives the frequency response "
        "G(j omega), which describes the steady-state output to sinusoidal inputs."
    )

    with tempfile.TemporaryDirectory(prefix="quickcap_real_webui_") as tmp:
        tmp_path = Path(tmp)
        state = WebState(
            cards_path=tmp_path / "cards.json",
            output_path=tmp_path / "rt_quickcap.apkg",
            generator_factory=OpenRouterCardGenerator,
            capture_fn=lambda: {"text": sample_text, "image_b64": None},
        )
        server = make_server("127.0.0.1", 0, state)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            get(url, "/")
            post(url, "/capture")
            if not state.pending:
                raise RuntimeError("real API generated no pending cards")
            if not all(card.get("render_ok") for card in state.pending):
                raise RuntimeError(f"render validation failed: {state.pending}")

            home_preview = get(url, "/").decode("utf-8", errors="replace")
            if "Pending cards" not in home_preview or "katex" not in home_preview.lower():
                raise RuntimeError("home route did not render pending card preview")

            generated = [
                {
                    "type": card.get("type"),
                    "tags": card.get("tags"),
                    "front": (card.get("front") or "")[:90],
                }
                for card in state.pending
            ]
            post(url, "/accept")
            saved = load_cards(state.cards_path)
            if len(saved) != len(generated):
                raise RuntimeError("accepted cards were not persisted")
            saved_home = get(url, "/").decode("utf-8", errors="replace")
            expected_range = f"1-{len(saved)} of {len(saved)}"
            if "Saved cards" not in saved_home or expected_range not in saved_home:
                raise RuntimeError("home route did not render saved cards newest-first preview")

            post(url, "/export")
            if not state.output_path.exists() or state.output_path.stat().st_size < 1000:
                raise RuntimeError("deck export failed")
            deck = get(url, "/deck")
            if len(deck) < 1000:
                raise RuntimeError("deck download failed")

            post(url, "/stop")
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("server did not stop")

            print(f"real webui e2e ok: generated={len(generated)}, deck_bytes={len(deck)}")
            for index, card in enumerate(generated, start=1):
                print(f"{index}. [{card['type']} | {','.join(card['tags'] or [])}] {card['front']}")
            return 0
        finally:
            if thread.is_alive():
                server.shutdown()
                thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
