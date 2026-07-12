from __future__ import annotations

import argparse
import base64
import email
import html
import io
import json
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from .build_deck import NoUnexportedCards, apkg_output_path, build_deck, stack_output_path
from .generator import (
    OpenRouterCardGenerator,
    configured_target_card_count,
    image_to_b64,
    list_provider_models,
    load_custom_prompt,
    provider_status,
    save_custom_prompt,
    set_provider_model,
)
from .paths import CARDS_PATH, CUSTOM_PROMPT_PATH, DECK_PATH
from .preview import _render_text, render_cards_html
from .quickcap import capture_clipboard, generate_with_note, hydrate_cards
from .storage import (append_cards, create_stack, delete_stack, get_stack, load_cards,
                      load_store, rename_stack, save_cards, save_store, select_stack)
from .validate import configured_tags, validate_cards


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RECENT_PAGE_SIZE = 10


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Refuse duplicate listeners instead of load-balancing broken app instances."""

    allow_reuse_address = False
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect width="32" height="32" rx="8" fill="#211914"/>
<path d="M8.5 23.5 14.9 8.8h2.9l6.4 14.7h-3.8l-1.2-3.1h-5.8l-1.2 3.1H8.5Zm6.2-6h3.2l-1.6-4.2-1.6 4.2Z" fill="#d99b72"/>
<path d="M22.2 8.7h2.7" stroke="#f5efe7" stroke-width="2" stroke-linecap="round"/>
</svg>"""
FAVICON_DATA_URI = "data:image/svg+xml," + urllib.parse.quote(FAVICON_SVG, safe="")


def _default_runtime_path(path: str | Path) -> Path:
    file_path = Path(path)
    if file_path.is_absolute():
        return file_path
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / file_path
    return file_path


@dataclass
class WebState:
    cards_path: Path = CARDS_PATH
    output_path: Path = DECK_PATH
    custom_prompt_path: Path = CUSTOM_PROMPT_PATH
    generator_factory: Callable[[], Any] = OpenRouterCardGenerator
    capture_fn: Callable[[], dict[str, Any]] = capture_clipboard
    llm_note: str = ""
    message: str = ""
    error: str = ""
    last_export: Path | None = None

    @property
    def store(self) -> dict[str, Any]:
        return load_store(self.cards_path)

    @property
    def active_stack(self) -> dict[str, Any]:
        return get_stack(self.store)

    @property
    def pending(self) -> list[dict[str, Any]]:
        return self.active_stack["pending"]

    @pending.setter
    def pending(self, cards: list[dict[str, Any]]) -> None:
        store = self.store; get_stack(store)["pending"] = cards; save_store(store, self.cards_path)


def _persist_pending(state: WebState, cards: list[dict[str, Any]], stack_id: str | None = None) -> None:
    store = state.store; stack = get_stack(store, stack_id); stack["pending"] = cards; save_store(store, state.cards_path)


def _require_stack(state: WebState, form: dict[str, str]) -> dict[str, Any]:
    stack = state.active_stack
    if form.get("stack_id") and form["stack_id"] != stack["id"]:
        raise ValueError("The active stack changed. Reload the page and try again.")
    return stack


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="icon" type="image/svg+xml" href="{FAVICON_DATA_URI}">
  <script>
    window.MathJax = {{ tex: {{ inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']] }} }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #121212;
      color: #f0ede9;
      --surface: rgba(26, 26, 25, 0.78);
      --text: #f0ede9;
      --text-soft: #d6d1cb;
      --muted: #aaa6a0;
      --line: rgba(240, 237, 233, 0.11);
      --ochre: #c78f6b;
      --ochre-strong: #ad6847;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: flow-root;
      overflow-x: hidden;
      background:
        radial-gradient(circle at 12% -8%, rgba(173, 104, 71, 0.065), transparent 34rem),
        linear-gradient(145deg, #121212 0%, #171716 54%, #111212 100%);
      color: var(--text);
    }}
    main {{ width: min(1160px, calc(100vw - 48px)); margin: 38px auto 72px; }}
    header.top {{ display: flex; align-items: center; justify-content: space-between; gap: 30px; margin-bottom: 26px; }}
    h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: clamp(38px, 4.6vw, 56px); font-weight: 400; line-height: 0.98; margin: 0; letter-spacing: -0.025em; text-wrap: balance; }}
    .actions {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; align-items: center; }}
    button, a.button {{
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(245, 239, 231, 0.035);
      color: var(--text);
      min-height: 38px;
      padding: 8px 13px;
      font: inherit;
      font-size: 14px;
      text-decoration: none;
      cursor: pointer;
      transition: border-color 140ms ease, background 140ms ease, transform 140ms ease;
    }}
    button:hover, a.button:hover {{ border-color: rgba(199, 143, 107, 0.48); background: rgba(245, 245, 245, 0.065); transform: translateY(-1px); }}
    button:disabled {{ opacity: 0.42; cursor: not-allowed; transform: none; }}
    button:focus-visible, a.button:focus-visible, summary:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible {{ outline: 2px solid rgba(199, 143, 107, 0.72); outline-offset: 2px; }}
    button.primary {{ background: var(--ochre-strong); border-color: #c27b59; color: #16110e; font-weight: 700; }}
    button.danger {{ background: rgba(107, 48, 43, 0.42); border-color: rgba(240, 128, 111, 0.32); color: #ffe9e4; }}
    button.small {{ min-height: 32px; padding: 5px 10px; font-size: 13px; }}
    h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.105em; color: var(--ochre); margin: 32px 0 12px; }}
    .section-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 16px; margin-top: 32px; }}
    .section-head h2 {{ margin: 0 0 10px; }}
    .section-head span {{ color: var(--muted); font-size: 14px; }}
    .pager {{ margin-top: 12px; justify-content: flex-end; }}
    .notice, .error {{ border-radius: 6px; padding: 10px 12px; margin: 12px 0; }}
    .llm-note {{ border-radius: 8px; padding: 12px 14px; margin: 12px 0; background: rgba(217, 155, 114, 0.14); border: 1px solid rgba(217, 155, 114, 0.35); }}
    .notice {{ background: rgba(72, 123, 96, 0.22); border: 1px solid rgba(112, 177, 139, 0.38); }}
    .error {{ background: rgba(147, 52, 43, 0.24); border: 1px solid rgba(240, 128, 111, 0.42); }}
    .async-status {{ position: fixed; right: 18px; bottom: 18px; z-index: 20; max-width: min(380px, calc(100vw - 36px)); border: 1px solid rgba(217, 155, 114, 0.42); border-radius: 8px; padding: 10px 13px; background: rgba(38, 27, 21, 0.96); color: #f5efe7; box-shadow: 0 14px 36px rgba(0, 0, 0, 0.3); }}
    .async-status.error {{ border-color: rgba(240, 128, 111, 0.55); color: #ffd8d0; }}
    form.async-busy {{ opacity: 0.62; pointer-events: none; }}
    .summary {{ color: var(--muted); margin: 12px 0 0; max-width: 610px; line-height: 1.5; }}
    .surface, .card, .empty, .provider-panel {{
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--surface);
      box-shadow: 0 18px 48px rgba(0, 0, 0, 0.11);
      backdrop-filter: blur(8px);
    }}
    .stack-bar {{ padding: 16px 18px; margin: 0 0 16px; }}
    .stack-main {{ display: grid; grid-template-columns: minmax(180px, 1fr) auto; gap: 12px; align-items: end; }}
    .stack-picker {{ display: grid; gap: 6px; }}
    .stack-picker label {{ color: var(--ochre); font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }}
    .stack-picker select {{ min-height: 42px; background: rgba(12, 12, 12, 0.72); font-weight: 600; }}
    .stack-meta {{ display: flex; gap: 7px; padding-bottom: 9px; white-space: nowrap; }}
    .stack-count {{ border: 1px solid var(--line); border-radius: 999px; padding: 4px 8px; color: var(--muted); font-size: 12px; }}
    .stack-manage {{ margin-top: 10px; border-top: 1px solid var(--line); }}
    .stack-manage > summary {{ width: fit-content; padding: 11px 0 1px; color: var(--text-soft); cursor: pointer; list-style: none; font-size: 13px; }}
    .stack-manage > summary::before {{ content: "›"; display: inline-block; margin-right: 7px; color: var(--ochre); font-size: 18px; vertical-align: -1px; transition: transform 140ms ease; }}
    .stack-manage[open] > summary::before {{ transform: rotate(90deg); }}
    .stack-manage > summary::-webkit-details-marker {{ display: none; }}
    .stack-management-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding-top: 14px; }}
    .stack-tool {{ display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: end; padding: 13px; border: 1px solid var(--line); border-radius: 8px; background: rgba(10, 10, 10, 0.22); }}
    .stack-tool label {{ display: grid; gap: 5px; min-width: 0; color: var(--muted); font-size: 12px; }}
    .stack-tool input {{ min-height: 39px; }}
    .stack-danger {{ grid-column: 1 / -1; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: end; padding: 13px; border: 1px solid rgba(240, 128, 111, 0.22); border-radius: 8px; background: rgba(107, 48, 43, 0.12); }}
    .stack-danger-copy {{ display: grid; gap: 5px; }}
    .stack-danger-copy strong {{ color: #ffd8d0; font-size: 13px; }}
    .stack-danger-copy span {{ color: var(--muted); font-size: 12px; line-height: 1.4; }}
    .stack-danger-controls {{ display: flex; gap: 8px; align-items: end; }}
    .stack-danger-controls label {{ display: grid; gap: 5px; color: #d8aaa2; font-size: 12px; }}
    .stack-danger-controls input {{ width: 190px; min-height: 39px; }}
    .export-menu {{ position: relative; }}
    .export-menu > summary {{ display: inline-flex; min-height: 38px; align-items: center; justify-content: center; gap: 8px; padding: 8px 13px; border: 1px solid var(--line); border-radius: 8px; background: rgba(245, 239, 231, 0.035); color: var(--text); cursor: pointer; list-style: none; font-size: 14px; line-height: 1; }}
    .export-menu > summary::-webkit-details-marker {{ display: none; }}
    .export-menu > summary::after {{ content: "⌄"; display: inline-flex; height: 14px; align-items: center; color: var(--ochre); font-size: 13px; line-height: 1; transform: translateY(-1px); }}
    .export-menu[open] > summary {{ border-color: rgba(199, 143, 107, 0.48); background: rgba(245, 245, 245, 0.065); }}
    .export-popover {{ position: absolute; z-index: 30; top: calc(100% + 8px); left: 0; width: min(270px, calc(100vw - 24px)); padding: 7px; border: 1px solid rgba(199, 143, 107, 0.26); border-radius: 10px; background: #191817; box-shadow: 0 20px 55px rgba(0, 0, 0, 0.42); }}
    .export-option {{ display: block; }}
    .export-option + .export-option {{ margin-top: 3px; }}
    .export-option button {{ display: flex; width: 100%; min-height: 45px; align-items: center; justify-content: space-between; gap: 12px; border-color: transparent; background: transparent; text-align: left; }}
    .export-option button:hover {{ border-color: var(--line); background: rgba(245, 239, 231, 0.055); transform: none; }}
    .export-option-name {{ font-weight: 600; }}
    .export-option-count {{ color: var(--muted); font-size: 12px; font-weight: 400; }}
    .stop-action {{ margin-left: 7px; padding-left: 14px; border-left: 1px solid var(--line); }}
    .latest-export {{ display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px 9px 4px; border-top: 1px solid var(--line); }}
    .latest-export span {{ min-width: 0; overflow: hidden; color: var(--muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }}
    .capture-grid {{ display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(300px, 0.75fr); gap: 14px; align-items: stretch; margin: 12px 0 10px; }}
    .ingest-panel {{ display: grid; align-content: start; padding: 18px; }}
    .ingest-heading {{ display: flex; justify-content: space-between; gap: 14px; align-items: baseline; margin-bottom: 11px; }}
    .ingest-heading strong {{ font-family: Georgia, "Times New Roman", serif; font-size: 24px; font-weight: 400; }}
    .ingest-heading span {{ color: var(--muted); font-size: 12px; }}
    .drop-zone {{ display: grid; gap: 10px; }}
    .drop-zone.dragging {{ border-radius: 8px; outline: 2px solid rgba(199, 143, 107, 0.62); outline-offset: 5px; }}
    .ingest-text {{ min-height: 126px; resize: vertical; line-height: 1.5; }}
    .ingest-footer {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .ingest-actions {{ display: flex; gap: 8px; align-items: center; margin-left: auto; padding-left: 12px; border-left: 1px solid var(--line); }}
    .capture-primary {{ min-height: 42px; padding-inline: 17px; }}
    .capture-primary span {{ display: block; font-size: 11px; font-weight: 500; opacity: 0.72; }}
    .file-picker-button {{ display: inline-flex; min-height: 38px; align-items: center; padding: 8px 13px; border: 1px solid var(--line); border-radius: 8px; background: rgba(245, 239, 231, 0.035); color: var(--text); cursor: pointer; font-size: 14px; }}
    .file-picker-button:hover {{ border-color: rgba(199, 143, 107, 0.48); background: rgba(245, 245, 245, 0.065); }}
    .file-picker-button input {{ position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }}
    .drop-copy {{ color: var(--muted); font-size: 12px; }}
    [hidden] {{ display: none !important; }}
    .provider-panel {{ overflow: hidden; }}
    .provider-panel > summary {{ display: flex; min-height: 70px; align-items: center; justify-content: space-between; gap: 12px; padding: 15px 18px; cursor: pointer; list-style: none; }}
    .provider-panel > summary::-webkit-details-marker {{ display: none; }}
    .provider-panel > summary::before {{ content: "›"; color: #d99b72; font-size: 22px; line-height: 1; transition: transform 140ms ease; }}
    .provider-panel[open] > summary::before {{ transform: rotate(90deg); }}
    .provider-panel > summary strong {{ margin-right: auto; font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; color: #d99b72; }}
    .provider-summary-meta {{ color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .provider-panel-body {{ padding: 4px 18px 18px; border-top: 1px solid rgba(245, 239, 231, 0.075); }}
    .prompt-panel {{ margin: 12px 0 20px; }}
    .prompt-panel > summary {{ min-height: 56px; }}
    .prompt-panel textarea {{ min-height: 230px; resize: vertical; line-height: 1.45; }}
    .prompt-panel .prompt-copy {{ display: grid; gap: 7px; padding-top: 14px; }}
    .prompt-panel .prompt-copy strong {{ color: var(--text-soft); }}
    .provider-row {{ display: grid; grid-template-columns: 88px 1fr auto; gap: 10px; align-items: center; padding: 8px 0; border-top: 1px solid rgba(245, 239, 231, 0.08); }}
    .provider-row:first-of-type {{ border-top: 0; }}
    .provider-config {{ display: grid; gap: 9px; margin-top: 14px; }}
    .provider-config label {{ display: grid; gap: 5px; color: var(--muted); font-size: 13px; }}
    .provider-config .inline-actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .model-status {{ min-height: 20px; color: #8f8174; font-size: 13px; }}
    .pill {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 3px 8px; font-size: 12px; border: 1px solid rgba(245, 239, 231, 0.14); color: #cbbcac; }}
    .pill.active {{ color: #26150e; background: #d99b72; border-color: #d99b72; }}
    .pill.missing {{ color: #ffb5a6; border-color: rgba(255, 181, 166, 0.35); }}
    .card {{ padding: 18px 20px; margin: 12px 0; }}
    .card.bad {{ border-color: rgba(240, 128, 111, 0.5); box-shadow: inset 4px 0 0 #b95d4d, 0 14px 44px rgba(0, 0, 0, 0.12); }}
    .card header {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; font-size: 14px; color: var(--muted); }}
    .pending-card {{ display: grid; gap: 12px; }}
    .pending-card header {{ align-items: center; margin-bottom: 0; }}
    .pending-fields {{ display: grid; grid-template-columns: 100px minmax(0, 1fr) 190px; gap: 8px; align-items: start; }}
    .pending-fields label {{ display: grid; gap: 5px; color: var(--muted); font-size: 13px; }}
    .pending-fields label:nth-child(2) {{ grid-column: span 2; }}
    .pending-content-field {{ grid-column: span 2; }}
    .field-preview {{ min-height: 62px; padding: 12px; border: 1px solid rgba(245, 239, 231, 0.1); border-radius: 7px; background: rgba(18, 15, 13, 0.52); color: #f5efe7; line-height: 1.5; }}
    .field-preview .katex {{ font-size: 1em; }}
    .field-source {{ margin-top: 7px; }}
    .field-source > summary {{ color: #b8a99b; cursor: pointer; font-size: 12px; list-style: none; }}
    .field-source > summary::before {{ content: "✎ "; color: #d99b72; }}
    .field-source > summary::-webkit-details-marker {{ display: none; }}
    .field-source textarea {{ margin-top: 7px; min-height: 108px; resize: vertical; }}
    .pending-card textarea {{ min-height: 92px; resize: vertical; }}
    .pending-card footer {{ display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }}
    .saved-card-actions {{ display: grid; grid-template-columns: max-content max-content; justify-content: end; gap: 8px; margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(245, 239, 231, 0.075); }}
    .saved-edit > summary, .saved-delete > summary {{ border: 1px solid rgba(245, 239, 231, 0.14); border-radius: 6px; padding: 6px 9px; color: #f5efe7; cursor: pointer; list-style: none; font-size: 13px; }}
    .saved-edit > summary::-webkit-details-marker, .saved-delete > summary::-webkit-details-marker {{ display: none; }}
    .saved-edit > summary:hover {{ border-color: rgba(244, 171, 119, 0.42); background: rgba(245, 239, 231, 0.06); }}
    .saved-delete > summary {{ color: #ffe9e4; border-color: rgba(240, 128, 111, 0.32); background: rgba(107, 48, 43, 0.25); }}
    .saved-delete > summary:hover {{ border-color: rgba(240, 128, 111, 0.58); background: rgba(107, 48, 43, 0.42); }}
    .saved-edit[open], .saved-delete[open] {{ grid-column: 1 / -1; min-width: min(720px, calc(100vw - 80px)); }}
    .saved-edit-form {{ display: grid; gap: 10px; margin-top: 10px; padding-top: 12px; border-top: 1px solid rgba(245, 239, 231, 0.1); }}
    .saved-edit-form .inline-actions {{ display: flex; justify-content: flex-end; }}
    .saved-delete-confirm {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 9px; margin-top: 10px; padding: 12px; border: 1px solid rgba(240, 128, 111, 0.28); border-radius: 7px; background: rgba(107, 48, 43, 0.18); }}
    .saved-delete-confirm span {{ margin-right: auto; color: #ffd8d0; }}
    .front {{ max-width: 92ch; font-size: 17px; line-height: 1.56; margin-bottom: 14px; }}
    .back {{ max-width: 92ch; border-top: 1px solid var(--line); padding-top: 14px; color: var(--text-soft); line-height: 1.56; }}
    .cloze-answer {{ background: rgba(217, 155, 114, 0.22); color: #fff3e8; border: 1px solid rgba(217, 155, 114, 0.55); border-radius: 4px; padding: 0 4px; }}
    .cloze-answer span:first-child {{ font-size: 12px; font-weight: 700; margin-right: 4px; color: #d99b72; }}
    .cloze-hint {{ color: #b8a99b; }}
    .errors {{ color: #ff9f8d; }}
    .warnings {{ color: #d99b72; }}
    textarea, input, select {{ width: 100%; border-radius: 8px; border: 1px solid rgba(240, 237, 233, 0.16); background: rgba(16, 16, 16, 0.78); color: var(--text); padding: 10px; font: inherit; }}
    textarea:focus, input:focus, select:focus {{ border-color: rgba(199, 143, 107, 0.52); }}
    .empty {{ border-style: dashed; padding: 24px 22px; color: var(--muted); }}
    .help-page {{ display: grid; gap: 18px; max-width: 920px; }}
    .help-page .surface {{ padding: 22px; }}
    .help-page h1 {{ margin-bottom: 12px; }}
    .help-page h2 {{ margin-top: 0; }}
    .help-page p, .help-page li {{ color: #dacabb; line-height: 1.62; }}
    .help-page ul {{ margin: 0; padding-left: 20px; }}
    .help-page code {{ color: #ffd0ad; background: rgba(245, 239, 231, 0.08); border-radius: 5px; padding: 2px 5px; }}
    @media (max-width: 900px) {{
      main {{ width: min(100% - 32px, 760px); margin-top: 28px; }}
      header.top {{ align-items: flex-start; flex-direction: column; gap: 20px; }}
      .actions {{ justify-content: flex-start; }}
      .pending-fields, .capture-grid {{ grid-template-columns: 1fr; }}
      .stack-management-grid {{ grid-template-columns: 1fr; }}
      .stack-danger {{ grid-column: auto; grid-template-columns: 1fr; }}
      .pending-fields label:nth-child(2), .pending-content-field {{ grid-column: auto; }}
      .provider-panel > summary {{ min-height: 58px; }}
    }}
    @media (max-width: 760px) {{
      .ingest-footer {{ display: grid; grid-template-columns: auto minmax(0, 1fr); }}
      .ingest-actions {{ grid-column: 1 / -1; justify-content: flex-end; margin-left: 0; padding: 10px 0 0; border-top: 1px solid var(--line); border-left: 0; }}
    }}
    @media (max-width: 560px) {{
      main {{ width: min(100% - 22px, 520px); margin: 22px auto 48px; }}
      h1 {{ font-size: clamp(36px, 12vw, 48px); }}
      .actions {{ display: grid; width: 100%; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .actions form, .actions a.button, .actions button {{ width: 100%; }}
      .actions a.button, .actions button {{ text-align: center; }}
      .capture-grid {{ gap: 10px; }}
      .ingest-panel {{ padding: 14px; }}
      .ingest-heading {{ align-items: flex-start; flex-direction: column; gap: 3px; }}
      .ingest-footer {{ grid-template-columns: 1fr; }}
      .ingest-footer .file-picker-button {{ width: 100%; text-align: center; justify-content: center; }}
      .drop-copy {{ text-align: center; }}
      .ingest-actions {{ grid-column: 1 / -1; display: grid; grid-template-columns: 1fr; margin-left: 0; padding: 10px 0 0; border-left: 0; border-top: 1px solid var(--line); }}
      .ingest-actions button {{ width: 100%; text-align: center; justify-content: center; }}
      .capture-primary {{ grid-row: 1; }}
      .provider-panel > summary {{ padding-inline: 14px; }}
      .provider-summary-meta {{ max-width: 48%; }}
      .card {{ padding: 16px; }}
      .section-head {{ align-items: flex-start; flex-direction: column; gap: 2px; }}
      .saved-card-actions {{ grid-template-columns: 1fr 1fr; }}
      .saved-edit > summary, .saved-delete > summary {{ text-align: center; }}
      .saved-edit[open], .saved-delete[open] {{ min-width: 0; }}
      .stack-bar .actions, .stack-tool, .stack-danger-controls {{ display: grid; grid-template-columns: 1fr; }}
      .stack-main {{ grid-template-columns: 1fr; }}
      .stack-meta {{ padding: 0; }}
      .stack-danger-controls input {{ width: 100%; }}
      .export-menu {{ position: static; }}
      .export-menu > summary {{ text-align: center; }}
      .export-popover {{ position: fixed; inset: auto 11px 11px; width: auto; max-height: calc(100vh - 22px); overflow-y: auto; }}
      .stop-action {{ margin-left: 0; padding-left: 0; border-left: 0; }}
    }}
  </style>
  <script>
    function showAsyncStatus(message, isError = false) {{
      let status = document.querySelector('[data-async-status]');
      if (!status) {{
        status = document.createElement('div');
        status.dataset.asyncStatus = 'true';
        document.body.appendChild(status);
      }}
      status.className = isError ? 'async-status error' : 'async-status';
      status.textContent = message;
    }}
    async function replacePageFromResponse(response) {{
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/vnd.anki')) {{
        const blob = await response.blob();
        const disposition = response.headers.get('content-disposition') || '';
        const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filenameMatch ? filenameMatch[1] : 'autoanki.apkg';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
        await refreshPage();
        return;
      }}
      const html = await response.text();
      const documentFromResponse = new DOMParser().parseFromString(html, 'text/html');
      const scrollTop = window.scrollY;
      document.title = documentFromResponse.title;
      document.body.replaceWith(documentFromResponse.body);
      window.scrollTo(0, scrollTop);
      installInteractions();
      if (window.MathJax && typeof window.MathJax.typesetPromise === 'function') {{
        await window.MathJax.typesetPromise([document.body]);
      }}
    }}
    async function refreshPage() {{
      const response = await fetch(window.location.href, {{ headers: {{ 'X-Requested-With': 'fetch' }} }});
      await replacePageFromResponse(response);
    }}
    async function requestAndRefresh(action, body, form, label) {{
      if (form) form.classList.add('async-busy');
      showAsyncStatus(label || 'Working...');
      try {{
        const response = await fetch(action, {{
          method: 'POST',
          body,
          headers: {{ 'X-Requested-With': 'fetch' }}
        }});
        if (!response.ok) throw new Error('Request failed (' + response.status + ')');
        await replacePageFromResponse(response);
      }} catch (error) {{
        if (form) form.classList.remove('async-busy');
        showAsyncStatus(error.message || 'Request failed.', true);
      }}
    }}
    async function submitDrop(formData) {{
      await requestAndRefresh('/upload', formData, document.querySelector('[data-drop-zone]'), 'Generating cards...');
    }}
    function installAsyncForms() {{
      document.querySelectorAll('form[method="post"]').forEach(form => {{
        form.addEventListener('submit', event => {{
          event.preventDefault();
          const submitter = event.submitter;
          const buttonAction = submitter && submitter.getAttribute('formaction');
          const formAction = form.getAttribute('action');
          const action = buttonAction || formAction || window.location.pathname;
          const formData = new FormData(form);
          if (submitter && submitter.name && !formData.has(submitter.name)) {{
            formData.append(submitter.name, submitter.value);
          }}
          const body = (form.enctype || '').toLowerCase() === 'multipart/form-data'
            ? formData
            : new URLSearchParams(formData);
          const label = (submitter && submitter.textContent.trim()) || 'Saving...';
          requestAndRefresh(action, body, form, label);
        }});
      }});
    }}
    function installDropZone() {{
      const zone = document.querySelector('[data-drop-zone]');
      const picker = document.querySelector('[data-file-picker]');
      const fileStatus = document.querySelector('[data-file-status]');
      const textInput = zone && zone.querySelector('textarea[name="text"]');
      const generateButton = zone && zone.querySelector('[data-generate-input]');
      if (!zone || !picker || !textInput || !generateButton) return;
      const supportedFile = file => {{
        const name = file.name.toLowerCase();
        return ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.txt', '.md'].some(extension => name.endsWith(extension));
      }};
      const updateInputState = () => {{
        const hasInput = Boolean(textInput.value.trim()) || picker.files.length > 0;
        generateButton.hidden = !hasInput;
        if (!fileStatus) return;
        fileStatus.textContent = picker.files.length
          ? picker.files.length + (picker.files.length === 1 ? ' supported file selected' : ' supported files selected')
          : 'or drop images, .txt, or .md';
      }};
      picker.addEventListener('change', () => {{
        updateInputState();
      }});
      textInput.addEventListener('input', updateInputState);
      for (const eventName of ['dragenter', 'dragover']) {{
        zone.addEventListener(eventName, event => {{
          event.preventDefault();
          zone.classList.add('dragging');
        }});
      }}
      for (const eventName of ['dragleave', 'drop']) {{
        zone.addEventListener(eventName, () => zone.classList.remove('dragging'));
      }}
      zone.addEventListener('drop', event => {{
        event.preventDefault();
        const text = event.dataTransfer.getData('text/plain');
        const files = Array.from(event.dataTransfer.files);
        const unsupported = files.filter(file => !supportedFile(file));
        if (unsupported.length) {{
          if (fileStatus) fileStatus.textContent = 'Unsupported: ' + unsupported.map(file => file.name).join(', ');
          return;
        }}
        if (files.length) {{
          const transfer = new DataTransfer();
          files.forEach(file => transfer.items.add(file));
          picker.files = transfer.files;
        }}
        if (text && !files.length) textInput.value = [textInput.value.trim(), text.trim()].filter(Boolean).join('\n\n');
        updateInputState();
      }});
      updateInputState();
    }}
    async function loadModels() {{
      const provider = document.querySelector('[data-provider-select]');
      const modelInput = document.querySelector('[data-model-input]');
      const list = document.querySelector('#model-options');
      const status = document.querySelector('[data-model-status]');
      if (!provider || !modelInput || !list || !status) return;
      status.textContent = 'Loading models...';
      list.innerHTML = '';
      try {{
        const response = await fetch('/models?provider=' + encodeURIComponent(provider.value));
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not load models');
        for (const model of data.models) {{
          const option = document.createElement('option');
          option.value = model;
          list.appendChild(option);
        }}
        status.textContent = data.models.length ? data.models.length + ' models available. You can still type any slug.' : 'No models returned. Type a slug manually.';
      }} catch (error) {{
        status.textContent = error.message + '. Type the model slug manually.';
      }}
    }}
    function installProviderConfig() {{
      const provider = document.querySelector('[data-provider-select]');
      const loadButton = document.querySelector('[data-load-models]');
      const panel = document.querySelector('[data-provider-panel]');
      if (!provider || !loadButton) return;
      provider.addEventListener('change', loadModels);
      loadButton.addEventListener('click', loadModels);
      if (panel) {{
        panel.addEventListener('toggle', () => {{
          if (panel.open && !panel.dataset.modelsLoaded) {{
            panel.dataset.modelsLoaded = 'true';
            loadModels();
          }}
        }});
      }}
    }}
    function installInteractions() {{
      installDropZone();
      installProviderConfig();
      installAsyncForms();
    }}
    window.addEventListener('DOMContentLoaded', installInteractions);
  </script>
</head>
<body>
  <main>{body}</main>
</body>
</html>
""".encode("utf-8")


def _parse_offset(raw_value: str | None) -> int:
    try:
        return max(0, int(raw_value or "0"))
    except ValueError:
        return 0


def _recent_cards(cards: list[dict[str, Any]], offset: int, limit: int = RECENT_PAGE_SIZE) -> tuple[list[dict[str, Any]], bool, bool]:
    newest_first = list(reversed(cards))
    page = newest_first[offset : offset + limit]
    has_newer = offset > 0
    has_older = offset + limit < len(newest_first)
    return page, has_newer, has_older


def _saved_card_actions_html(card: dict[str, Any], offset: int, stack_id: str = "") -> str:
    card_id = str(card.get("id") or "")
    if not card_id:
        return '<div class="warnings">This legacy card has no ID and cannot be edited safely.</div>'
    tags = ",".join(card.get("tags") or [])
    type_options = []
    for card_type in ("basic", "cloze"):
        selected = " selected" if card.get("type") == card_type else ""
        type_options.append(f'<option value="{card_type}"{selected}>{card_type}</option>')
    return f"""
    <footer class="saved-card-actions">
      <details class="saved-edit">
        <summary>Edit</summary>
        <form class="saved-edit-form" method="post" action="/saved/update">
          <input type="hidden" name="stack_id" value="{html.escape(stack_id)}">
          <input type="hidden" name="card_id" value="{html.escape(card_id)}">
          <input type="hidden" name="offset" value="{offset}">
          <div class="pending-fields">
            <label>
              Type
              <select name="type">{''.join(type_options)}</select>
            </label>
            <label>
              Tags
              <input name="tags" value="{html.escape(tags)}" aria-label="saved card tags">
            </label>
            <label>
              Front
              <textarea name="front">{html.escape(card.get("front", ""))}</textarea>
            </label>
            <label>
              Back
              <textarea name="back">{html.escape(card.get("back", ""))}</textarea>
            </label>
          </div>
          <div class="inline-actions">
            <button class="small primary" type="submit">Save changes</button>
          </div>
        </form>
      </details>
      <details class="saved-delete">
        <summary>Delete</summary>
        <div class="saved-delete-confirm">
          <span>Delete this local saved card permanently? Existing Anki imports are not changed.</span>
          <button class="small" type="button" onclick="this.closest('details').removeAttribute('open')">Cancel</button>
          <form method="post" action="/saved/delete">
            <input type="hidden" name="stack_id" value="{html.escape(stack_id)}">
            <input type="hidden" name="card_id" value="{html.escape(card_id)}">
            <input type="hidden" name="offset" value="{offset}">
            <button class="small danger" type="submit">Yes, delete</button>
          </form>
        </div>
      </details>
    </footer>
    """


def _recent_cards_html(saved_cards: list[dict[str, Any]], offset: int, stack_id: str = "") -> str:
    page_cards, has_newer, has_older = _recent_cards(saved_cards, offset)
    if not saved_cards:
        return '<section><h2>Saved cards</h2><div class="empty">No saved cards yet.</div></section>'

    start = offset + 1
    end = offset + len(page_cards)
    nav = []
    if has_newer:
        newer_offset = max(0, offset - RECENT_PAGE_SIZE)
        nav.append(f'<a class="button" href="/?offset={newer_offset}">Newer</a>')
    if has_older:
        older_offset = offset + RECENT_PAGE_SIZE
        nav.append(f'<a class="button" href="/?offset={older_offset}">Older</a>')
    nav_html = f'<div class="actions pager">{"".join(nav)}</div>' if nav else ""

    return f"""
    <section>
      <div class="section-head">
        <h2>Saved cards</h2>
        <span>{start}-{end} of {len(saved_cards)} / newest first</span>
      </div>
      {render_cards_html(page_cards, start_index=start, card_footer=lambda card: _saved_card_actions_html(card, offset, stack_id))}
      {nav_html}
    </section>
    """


def _pending_log_path(cards_path: Path) -> Path:
    return cards_path.with_name("pending_generations.jsonl")


def _log_pending_generation(
    cards_path: Path,
    source: dict[str, Any],
    cards: list[dict[str, Any]],
    llm_note: str,
    stack: dict[str, Any] | None = None,
) -> None:
    if not cards:
        return
    log_path = _pending_log_path(cards_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"source": source, "cards": cards, "llm_note": llm_note}
    if stack: record.update({"stack_id": stack["id"], "stack_name": stack["name"]})
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _provider_panel_html() -> str:
    rows = []
    active_provider = ""
    active_model = ""
    for item in provider_status():
        if item["active"]:
            active_provider = item["name"]
            active_model = item["model"]
        active = '<span class="pill active">active</span>' if item["active"] else ""
        key_state = '<span class="pill">key set</span>' if item["key_set"] else '<span class="pill missing">no key</span>'
        model = html.escape(item["model"] or "set model env")
        rows.append(
            f"""
            <div class="provider-row">
              <strong>{html.escape(item["name"])}</strong>
              <span class="muted">{model}</span>
              <span>{active}{key_state}</span>
            </div>
            """
        )
    provider_options = []
    for item in provider_status():
        selected = " selected" if item["name"] == active_provider else ""
        provider_options.append(f'<option value="{html.escape(item["name"])}"{selected}>{html.escape(item["name"])}</option>')
    return f"""
    <details class="provider-panel" data-provider-panel>
      <summary>
        <strong>Model provider</strong>
        <span class="provider-summary-meta">{html.escape(active_provider)} · {html.escape(active_model)}</span>
      </summary>
      <div class="provider-panel-body">
        {''.join(rows)}
        <form class="provider-config" method="post" action="/config">
          <label>
            Provider
            <select name="provider" data-provider-select>{''.join(provider_options)}</select>
          </label>
          <label>
            Model
            <input name="model" data-model-input list="model-options" value="{html.escape(active_model)}" placeholder="model slug">
            <datalist id="model-options"></datalist>
          </label>
          <label>
            Cards to aim for
            <input name="target_card_count" type="number" min="1" max="12" step="1" value="{configured_target_card_count()}">
          </label>
          <div class="inline-actions">
            <button class="small" type="submit">Save</button>
            <button class="small" type="button" data-load-models>Load models</button>
          </div>
          <div class="model-status" data-model-status></div>
        </form>
        <p class="muted">Keys stay in your local .env file. The UI only saves provider, model, and card count.</p>
      </div>
    </details>
    """


def _custom_prompt_panel_html(path: str | Path = CUSTOM_PROMPT_PATH) -> str:
    custom_prompt = load_custom_prompt(path)
    status = "Custom instructions active" if custom_prompt else "Generic prompt only"
    return f"""
    <details class="provider-panel prompt-panel" data-custom-prompt-panel>
      <summary>
        <strong>Custom prompt</strong>
        <span class="provider-summary-meta">{status}</span>
      </summary>
      <div class="provider-panel-body">
        <div class="prompt-copy">
          <strong>The generic prompt always stays enabled.</strong>
          <span class="muted">Add subject-specific guidance here, or clear the field to return to generic-only generation.</span>
        </div>
        <form class="provider-config" method="post" action="/prompt">
          <label>
            Additional system-prompt instructions
            <textarea name="custom_prompt" maxlength="20000" placeholder="Example: Write cards in German and focus on control-engineering distinctions.">{html.escape(custom_prompt)}</textarea>
          </label>
          <div class="inline-actions">
            <button class="small primary" type="submit" name="action" value="save">Save custom prompt</button>
            <button class="small" type="submit" name="action" value="clear">Generic only</button>
          </div>
        </form>
      </div>
    </details>
    """


def _pending_card_editor(card: dict[str, Any], index: int, stack_id: str = "") -> str:
    tags = ",".join(card.get("tags") or [])
    type_options = []
    for card_type in ("basic", "cloze"):
        selected = " selected" if card.get("type") == card_type else ""
        type_options.append(f'<option value="{card_type}"{selected}>{card_type}</option>')
    errors = card.get("validation_errors") or []
    warnings = card.get("validation_warnings") or []
    error_html = "<ul class=\"errors\">" + "".join(f"<li>{html.escape(error)}</li>" for error in errors) + "</ul>" if errors else ""
    warning_html = (
        "<ul class=\"warnings\">" + "".join(f"<li>{html.escape(warning)}</li>" for warning in warnings) + "</ul>"
        if warnings
        else ""
    )
    status = "ok" if card.get("render_ok") else "bad"
    front = card.get("front", "")
    back = card.get("back", "")
    front_preview = _render_text(front) or '<span class="muted">No front text</span>'
    back_preview = _render_text(back) or '<span class="muted">No back text</span>'

    def source_field(label: str, name: str, raw: str, rendered: str) -> str:
        return f"""
        <label class="pending-content-field">
          {label}
          <div class="field-preview">{rendered}</div>
          <details class="field-source">
            <summary>Edit source</summary>
            <textarea name="{name}">{html.escape(raw)}</textarea>
          </details>
        </label>
        """

    return f"""
    <form class="card pending-card {status}" method="post" action="/update">
      <input type="hidden" name="stack_id" value="{html.escape(stack_id)}">
      <input type="hidden" name="card_id" value="{html.escape(str(card.get('id', '')))}">
      <header>
        <strong>{index + 1}. Pending card</strong>
        <span>{html.escape(tags)}</span>
      </header>
      <input type="hidden" name="index" value="{index}">
      <div class="pending-fields">
        <label>
          Type
          <select name="type">{''.join(type_options)}</select>
        </label>
        <label>
          Tags
          <input name="tags" value="{html.escape(tags)}" aria-label="tags">
        </label>
        {source_field("Front", "front", front, front_preview)}
        {source_field("Back", "back", back, back_preview)}
      </div>
      {error_html}
      {warning_html}
      <footer>
        <button class="small" type="submit">Save</button>
        <button class="small primary" formaction="/accept-one" name="index" value="{index}">Accept</button>
        <button class="small" formaction="/discard" name="index" value="{index}">Discard</button>
      </footer>
    </form>
    """


def _capture_html(custom_prompt_path: str | Path = CUSTOM_PROMPT_PATH) -> str:
    return f"""
    <section class="capture-grid">
      <div class="surface ingest-panel">
        <div class="ingest-heading"><strong>Add study material</strong><span>Type, paste, drop, or capture</span></div>
        <form class="drop-zone" data-drop-zone method="post" action="/upload" enctype="multipart/form-data">
          <textarea class="ingest-text" name="text" placeholder="Type or paste notes here…" aria-label="Study material"></textarea>
          <div class="ingest-footer">
            <label class="file-picker-button">Choose files<input data-file-picker type="file" name="files" multiple accept=".png,.jpg,.jpeg,.webp,.gif,.txt,.md,image/png,image/jpeg,image/webp,image/gif,text/plain,text/markdown"></label>
            <span class="drop-copy" data-file-status>or drop images, .txt, or .md</span>
            <div class="ingest-actions" aria-label="Generate cards">
              <button type="submit" data-generate-input hidden>Generate from notes / files</button>
              <button class="primary capture-primary" type="submit" formaction="/capture">Capture clipboard &amp; generate<span>Text or image</span></button>
            </div>
          </div>
        </form>
      </div>
      {_provider_panel_html()}
    </section>
    {_custom_prompt_panel_html(custom_prompt_path)}
    """


def render_help() -> bytes:
    body = """
    <section class="help-page">
      <header class="top">
        <div>
          <h1>Put useful study material in. Keep the cards that work.</h1>
          <div class="summary">AutoAnki is a local review loop for turning rough material into Anki cards.</div>
        </div>
        <div class="actions">
          <a class="button primary" href="/">Back to AutoAnki</a>
        </div>
      </header>

      <article class="surface">
        <h2>What to drop in</h2>
        <p>Use whatever you already have while studying: a screenshot of handwriting, a photo of a whiteboard, a chunk of a worked solution, a paragraph from notes, or the useful part of an LLM answer.</p>
        <p>You can also copy something and hit <code>Capture Clipboard</code>. That is usually fastest for screenshots and short snippets.</p>
      </article>

      <article class="surface">
        <h2>What happens</h2>
        <ul>
          <li>AutoAnki reads the dropped file or clipboard content on your machine.</li>
          <li>It sends that one capture to the model provider you configured.</li>
          <li>The model drafts 1-3 cards as structured JSON.</li>
          <li>You review, edit, discard, or accept the cards.</li>
          <li>Accepted cards are saved locally in <code>cards.json</code>.</li>
          <li><code>Export .apkg</code> builds a normal Anki deck you can import yourself.</li>
        </ul>
      </article>

      <article class="surface">
        <h2>Why it is safe enough for this job</h2>
        <p>Your API keys stay in your local <code>.env</code> file. They are never written into cards, decks, prompts, or logs.</p>
        <p>AutoAnki sends only the material you choose to the active model provider. Saved cards and exported decks stay local unless you move them somewhere else.</p>
        <p>You still approve the cards. The model is doing the annoying drafting step, not silently filling your Anki deck.</p>
      </article>

      <article class="surface">
        <h2>How to get good cards</h2>
        <ul>
          <li>Drop the smallest useful chunk, not a whole chapter.</li>
          <li>Add a short focus note when the screenshot is ambiguous.</li>
          <li>Keep cards that match what you actually wanted to remember.</li>
          <li>Delete cards that feel clever but would not help you tomorrow.</li>
          <li>Tune <code>AUTOANKI_TAGS</code> if you want subject-specific tags.</li>
        </ul>
      </article>
    </section>
    """
    return _page("How AutoAnki works", body)


def render_home(state: WebState, offset: int = 0) -> bytes:
    store = state.store; active = get_stack(store); stack_id = active["id"]
    pending_count = len(active["pending"])
    saved_cards = active["cards"]
    saved_count = len(saved_cards)
    unexported_count = sum(1 for card in saved_cards if not card.get("exported_at"))
    all_saved_count = sum(len(stack["cards"]) for stack in store["stacks"])
    message = f'<div class="notice">{html.escape(state.message)}</div>' if state.message else ""
    error = f'<div class="error">{html.escape(state.error)}</div>' if state.error else ""
    llm_note = f'<div class="llm-note"><strong>LLM note:</strong> {html.escape(state.llm_note)}</div>' if state.llm_note else ""
    export_link = ""
    existing_export = state.last_export
    if existing_export and existing_export.exists():
        state.last_export = existing_export
        export_link = f'<div class="latest-export"><span title="{html.escape(existing_export.name)}">Latest: {html.escape(existing_export.name)}</span><a class="button" href="/deck">Download again</a></div>'

    if active["pending"]:
        pending_cards = "".join(_pending_card_editor(card, index, stack_id) for index, card in enumerate(active["pending"]))
        pending_html = f"""
        <section>
          <div class="section-head">
            <h2>Pending cards</h2>
            <form method="post" action="/accept"><input type="hidden" name="stack_id" value="{stack_id}"><button type="submit">Accept all</button></form>
          </div>
          {pending_cards}
        </section>
        """
    else:
        pending_html = '<section><h2>Pending cards</h2><div class="empty">No pending cards. Copy text or an image, then capture.</div></section>'

    saved_html = _recent_cards_html(saved_cards, offset, stack_id)
    options = "".join(f'<option value="{s["id"]}"{" selected" if s["id"] == stack_id else ""}>{html.escape(s["name"])}</option>' for s in store["stacks"])
    stack_panel = f"""
    <section class="surface stack-bar">
      <div class="stack-main">
        <form method="post" action="/stacks/select" class="stack-picker">
          <label for="active-stack">Card stack</label>
          <select id="active-stack" name="stack_id" onchange="this.form.requestSubmit()">{options}</select>
        </form>
        <div class="stack-meta" aria-label="Stack totals">
          <span class="stack-count">{saved_count} saved</span>
          <span class="stack-count">{pending_count} pending</span>
        </div>
      </div>
      <details class="stack-manage"><summary>Manage stacks</summary>
        <div class="stack-management-grid">
          <form method="post" action="/stacks/create" class="stack-tool">
            <label>New stack<input name="name" maxlength="80" placeholder="e.g. Control theory" required></label>
            <button type="submit">Create</button>
          </form>
          <form method="post" action="/stacks/rename" class="stack-tool">
            <input type="hidden" name="stack_id" value="{stack_id}">
            <label>Rename current stack<input name="name" maxlength="80" value="{html.escape(active['name'])}" required></label>
            <button type="submit">Rename</button>
          </form>
          <div class="stack-danger">
            <div class="stack-danger-copy"><strong>Delete “{html.escape(active['name'])}”</strong><span>Permanently removes its local drafts and cards. Existing Anki imports are not affected.</span></div>
            <form method="post" action="/stacks/delete" class="stack-danger-controls">
              <input type="hidden" name="stack_id" value="{stack_id}">
              <label>Type the stack name<input name="confirmation" placeholder="{html.escape(active['name'])}" required></label>
              <button class="danger" type="submit">Delete</button>
            </form>
          </div>
        </div>
      </details>
    </section>"""

    export_menu = f"""
      <details class="export-menu">
        <summary>Export</summary>
        <div class="export-popover">
          <form method="post" action="/export" class="export-option"><input type="hidden" name="mode" value="new"><input type="hidden" name="scope" value="selected"><input type="hidden" name="stack_id" value="{stack_id}"><button type="submit"{' disabled' if unexported_count == 0 else ''}><span class="export-option-name">New cards</span><span class="export-option-count">{unexported_count}</span></button></form>
          <form method="post" action="/export" class="export-option"><input type="hidden" name="mode" value="all"><input type="hidden" name="scope" value="selected"><input type="hidden" name="stack_id" value="{stack_id}"><button type="submit"{' disabled' if saved_count == 0 else ''}><span class="export-option-name">All cards</span><span class="export-option-count">{saved_count} in {html.escape(active['name'])}</span></button></form>
          <form method="post" action="/export" class="export-option"><input type="hidden" name="mode" value="all"><input type="hidden" name="scope" value="all"><button type="submit"{' disabled' if all_saved_count == 0 else ''}><span class="export-option-name">All stacks</span><span class="export-option-count">{all_saved_count} total</span></button></form>
          {export_link}
        </div>
      </details>"""

    body = f"""
    <header class="top">
      <div>
        <h1>AutoAnki Quickcap</h1>
      </div>
      <div class="actions">
        {export_menu}
        <a class="button" href="/help">How does this work?</a>
        <form method="post" action="/stop" class="stop-action"><button class="danger" type="submit">Stop</button></form>
      </div>
    </header>
    {message}
    {error}
    {llm_note}
    {stack_panel}
    {_capture_html(state.custom_prompt_path)}
    {pending_html}
    {saved_html}
    """
    return _page("AutoAnki Quickcap", body)


class QuickcapHandler(BaseHTTPRequestHandler):
    state: WebState

    def log_message(self, format: str, *args: Any) -> None:
        print(f"webui: {self.address_string()} - {format % args}")

    def _send(
        self,
        body: bytes,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str = "/") -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        data = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] for key, values in data.items()}

    def _multipart_source(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        message = email.message_from_bytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + raw
        )
        source: dict[str, Any] = {"text": None, "image_b64": None}
        text_parts: list[str] = []
        unsupported_files: list[str] = []
        if not message.is_multipart():
            raise ValueError("Upload must be multipart form data")
        for part in message.get_payload():
            disposition = part.get("Content-Disposition", "")
            if "form-data" not in disposition:
                continue
            name = part.get_param("name", header="Content-Disposition")
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            media_type = (part.get_content_type() or "").lower()
            if name == "text" and payload.strip():
                text_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                continue
            if not filename or not payload:
                continue
            suffix = Path(filename).suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"} and media_type.startswith("image/"):
                if source["image_b64"] is None:
                    try:
                        from PIL import Image

                        with Image.open(io.BytesIO(payload)) as image:
                            source["image_b64"] = image_to_b64(image.convert("RGB"))
                    except Exception as exc:
                        raise ValueError(f"Could not read image file: {filename}") from exc
                continue
            if suffix in {".txt", ".md"}:
                text_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                continue
            unsupported_files.append(filename)
        if unsupported_files:
            names = ", ".join(unsupported_files)
            raise ValueError(f"Unsupported file type: {names}. Use images, .txt, or .md files.")
        text = "\n\n".join(part.strip() for part in text_parts if part.strip()).strip()
        if text:
            source["text"] = text
        if not source["text"] and not source["image_b64"]:
            raise ValueError("Drop a text file, markdown file, image, or plain text selection.")
        return source

    def _generate_pending(self, source: dict[str, Any]) -> None:
        generator = self.state.generator_factory()
        generation = generate_with_note(generator, source, forced_tags=None)
        self.state.llm_note = generation.note_to_user
        new_pending = hydrate_cards(generation.cards, source)
        stack = self.state.active_stack; pending = stack["pending"]
        previous_count = len(pending); pending.extend(new_pending); validate_cards(pending)
        _persist_pending(self.state, pending, stack["id"])
        _log_pending_generation(self.state.cards_path, source, new_pending, self.state.llm_note, stack)
        self.state.message = (
            f"Added {len(new_pending)} pending card(s). Total pending: {len(pending)}."
            if previous_count
            else f"Generated {len(new_pending)} pending card(s)."
        )

    def _update_pending_card(self, index: int, form: dict[str, str]) -> None:
        tags = [tag.strip() for tag in form.get("tags", "").split(",") if tag.strip()]
        unknown = [tag for tag in tags if tag not in configured_tags()]
        if unknown:
            raise ValueError(f"Unknown tags: {', '.join(unknown)}")
        pending = self.state.pending
        pending[index].update(
            {
                "type": form.get("type", "basic"),
                "front": form.get("front", ""),
                "back": form.get("back", ""),
                "tags": tags[:2],
            }
        )
        _persist_pending(self.state, pending, self.state.active_stack["id"])

    def _saved_card_index(self, cards: list[dict[str, Any]], card_id: str) -> int:
        for index, card in enumerate(cards):
            if str(card.get("id") or "") == card_id:
                return index
        raise ValueError("Saved card was not found. Reload the page and try again.")

    def _saved_card_redirect(self, requested_offset: str, card_count: int) -> None:
        offset = _parse_offset(requested_offset)
        last_page_offset = ((card_count - 1) // RECENT_PAGE_SIZE) * RECENT_PAGE_SIZE if card_count else 0
        self._redirect(f"/?offset={min(offset, last_page_offset)}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            query = urllib.parse.parse_qs(parsed.query)
            offset = _parse_offset((query.get("offset") or [None])[-1])
            self._send(render_home(self.state, offset=offset))
            return
        if parsed.path == "/preview":
            self._redirect("/")
            return
        if parsed.path == "/help":
            self._send(render_help())
            return
        if parsed.path == "/models":
            query = urllib.parse.parse_qs(parsed.query)
            provider = (query.get("provider") or [""])[-1]
            try:
                models = list_provider_models(provider)
                body = json.dumps({"models": models}, ensure_ascii=False).encode("utf-8")
                self._send(body, content_type="application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(body, HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8")
            return
        if parsed.path == "/deck" and self.state.last_export and self.state.last_export.exists():
            data = self.state.last_export.read_bytes()
            filename = self.state.last_export.name
            quoted_filename = urllib.parse.quote(filename)
            self._send(
                data,
                content_type="application/vnd.anki",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_filename}',
                },
            )
            return
        self._send(b"Not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        self.state.error = ""
        self.state.message = ""
        try:
            if self.path == "/stacks/select":
                form = self._form(); stack = select_stack(form.get("stack_id", ""), self.state.cards_path)
                self.state.last_export = None; self.state.message = f"Switched to {stack['name']}."; self._redirect(); return
            if self.path == "/stacks/create":
                form = self._form(); stack = create_stack(form.get("name", ""), self.state.cards_path)
                self.state.last_export = None; self.state.message = f"Created {stack['name']}."; self._redirect(); return
            if self.path == "/stacks/rename":
                form = self._form(); _require_stack(self.state, form); stack = rename_stack(form["stack_id"], form.get("name", ""), self.state.cards_path)
                self.state.message = f"Renamed stack to {stack['name']}."; self._redirect(); return
            if self.path == "/stacks/delete":
                form = self._form(); _require_stack(self.state, form); stack = delete_stack(form["stack_id"], form.get("confirmation", ""), self.state.cards_path)
                self.state.last_export = None; self.state.message = f"Deleted {stack['name']}."; self._redirect(); return
            if self.path == "/capture":
                source = self.state.capture_fn()
                self._generate_pending(source)
                self._redirect()
                return
            if self.path == "/upload":
                source = self._multipart_source()
                self._generate_pending(source)
                self._redirect()
                return
            if self.path == "/accept":
                form = self._form(); stack = _require_stack(self.state, form); pending = stack["pending"]
                if pending:
                    total = append_cards(pending, self.state.cards_path, stack["id"])
                    count = len(pending); _persist_pending(self.state, [], stack["id"])
                    self.state.llm_note = ""
                    self.state.message = f"Saved {count} card(s). Total: {len(total)}."
                else:
                    self.state.message = "No pending cards to accept."
                self._redirect()
                return
            if self.path == "/config":
                form = self._form()
                path = set_provider_model(form.get("provider", ""), form.get("model", ""), form.get("target_card_count"))
                self.state.generator_factory = OpenRouterCardGenerator
                self.state.message = f"Saved provider settings to {path.name}."
                self._redirect()
                return
            if self.path == "/prompt":
                form = self._form()
                action = form.get("action", "save")
                if action == "clear":
                    value = ""
                    message = "Cleared custom instructions. Generic prompt only."
                elif action == "save":
                    value = form.get("custom_prompt", "")
                    message = "Saved custom prompt instructions."
                else:
                    raise ValueError("Unknown custom prompt action.")
                save_custom_prompt(value, self.state.custom_prompt_path)
                self.state.message = message
                self._redirect()
                return
            if self.path == "/accept-one":
                form = self._form()
                stack = _require_stack(self.state, form); pending = stack["pending"]
                index = int(form.get("index", "-1"))
                if 0 <= index < len(pending) and (not form.get("card_id") or pending[index].get("id") == form.get("card_id")):
                    self._update_pending_card(index, form)
                    pending = self.state.pending; card = pending.pop(index)
                    validate_cards([card])
                    _persist_pending(self.state, pending, stack["id"]); total = append_cards([card], self.state.cards_path, stack["id"])
                    self.state.message = f"Saved 1 card. Total: {len(total)}."
                self._redirect()
                return
            if self.path == "/saved/update":
                form = self._form()
                stack = _require_stack(self.state, form); cards = load_cards(self.state.cards_path, stack["id"])
                index = self._saved_card_index(cards, form.get("card_id", ""))
                tags = [tag.strip() for tag in form.get("tags", "").split(",") if tag.strip()]
                updated = {
                    **cards[index],
                    "type": form.get("type", "basic"),
                    "front": form.get("front", ""),
                    "back": form.get("back", ""),
                    "tags": tags,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                updated.pop("exported_at", None)
                result = validate_cards([updated], allowed_tags=set(tags))[0]
                if not result.ok:
                    raise ValueError("Could not save card: " + "; ".join(result.errors))
                cards[index] = updated
                save_cards(cards, self.state.cards_path, stack["id"])
                self.state.message = "Updated saved card. It will be included in the next new-card export."
                self._saved_card_redirect(form.get("offset", "0"), len(cards))
                return
            if self.path == "/saved/delete":
                form = self._form()
                stack = _require_stack(self.state, form); cards = load_cards(self.state.cards_path, stack["id"])
                index = self._saved_card_index(cards, form.get("card_id", ""))
                cards.pop(index)
                save_cards(cards, self.state.cards_path, stack["id"])
                self.state.message = f"Deleted saved card. Total: {len(cards)}."
                self._saved_card_redirect(form.get("offset", "0"), len(cards))
                return
            if self.path == "/discard":
                form = self._form()
                stack = _require_stack(self.state, form); pending = stack["pending"]
                index = int(form.get("index", "-1"))
                if 0 <= index < len(pending) and (not form.get("card_id") or pending[index].get("id") == form.get("card_id")):
                    pending.pop(index); _persist_pending(self.state, pending, stack["id"])
                    self.state.message = "Discarded card."
                self._redirect()
                return
            if self.path == "/update":
                form = self._form()
                stack = _require_stack(self.state, form); pending = stack["pending"]
                index = int(form.get("index", "-1"))
                if 0 <= index < len(pending) and (not form.get("card_id") or pending[index].get("id") == form.get("card_id")):
                    self._update_pending_card(index, form)
                    pending = self.state.pending; validate_cards(pending); _persist_pending(self.state, pending, stack["id"])
                    self.state.message = "Updated card."
                self._redirect()
                return
            if self.path == "/export":
                form = self._form()
                export_mode = form.get("mode", "new")
                scope = form.get("scope", "selected")
                if export_mode not in {"new", "all"}:
                    raise ValueError("Unknown export mode.")
                if scope not in {"selected", "all"}: raise ValueError("Unknown export scope.")
                if scope == "selected": _require_stack(self.state, form)
                try:
                    output_path = self.state.output_path
                    if scope == "selected" and apkg_output_path(output_path).name == apkg_output_path(DECK_PATH).name:
                        output_path = stack_output_path(output_path, self.state.active_stack)
                    self.state.last_export = build_deck(
                        self.state.cards_path,
                        output_path,
                        export_mode=export_mode,
                        stack_id=form.get("stack_id") or None,
                        scope=scope,
                    )
                    self._redirect("/deck")
                    return
                except NoUnexportedCards:
                    self.state.message = (
                        "No new unexported cards to export, and no deck file exists yet."
                        if export_mode == "new"
                        else "No saved cards to export."
                    )
                self._redirect()
                return
            if self.path == "/stop":
                body = _page("AutoAnki stopped", "<h1>AutoAnki stopped</h1><p>You can close this tab.</p>")
                self._send(body)
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
        except Exception as exc:
            self.state.error = str(exc)
            self._redirect()
            return
        self._send(b"Not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")


def make_server(host: str, port: int, state: WebState) -> ThreadingHTTPServer:
    class Handler(QuickcapHandler):
        pass

    Handler.state = state
    return ExclusiveThreadingHTTPServer((host, port), Handler)


def run_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    cards_path: str | Path = CARDS_PATH,
    output_path: str | Path = DECK_PATH,
    open_browser: bool = True,
) -> None:
    state = WebState(cards_path=_default_runtime_path(cards_path), output_path=_default_runtime_path(output_path))
    server = make_server(host, port, state)
    url = f"http://{host}:{server.server_port}/"
    print(f"AutoAnki WebUI running at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        print("AutoAnki WebUI stopped.")


def stop_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    request = urllib.request.Request(f"http://{host}:{port}/stop", data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except OSError as exc:
        raise RuntimeError(f"No AutoAnki WebUI responded at http://{host}:{port}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AutoAnki local WebUI.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--cards", default=CARDS_PATH)
    parser.add_argument("--output", default=DECK_PATH)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--stop", action="store_true", help="stop the local WebUI on this port")
    args = parser.parse_args(argv)

    if args.stop:
        stop_server(args.host, args.port)
        print("Stop requested.")
        return 0
    try:
        run_server(
            host=args.host,
            port=args.port,
            cards_path=args.cards,
            output_path=args.output,
            open_browser=not args.no_browser,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or getattr(exc, "errno", None) in {48, 98}:
            print(f"AutoAnki is already running at http://{args.host}:{args.port}/")
            return 1
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
