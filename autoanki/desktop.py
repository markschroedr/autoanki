from __future__ import annotations

import threading

import webview

from .paths import CARDS_PATH, DECK_PATH
from .webui import DEFAULT_HOST, DEFAULT_PORT, WebState, make_server


def main() -> int:
    state = WebState(cards_path=CARDS_PATH, output_path=DECK_PATH)
    server = make_server(DEFAULT_HOST, DEFAULT_PORT, state)
    url = f"http://{DEFAULT_HOST}:{server.server_port}/"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    window = webview.create_window(
        "AutoAnki",
        url,
        width=1180,
        height=820,
        min_size=(360, 640),
        text_select=True,
    )
    window.events.closed += server.shutdown
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
