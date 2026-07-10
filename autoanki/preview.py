from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Callable

from .text_clean import clean_text


MATH_PATTERN = re.compile(r"\\\((.*?)\\\)|\\\[(.*?)\\\]", re.DOTALL)
CLOZE_PATTERN = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.DOTALL)


def _katex_executable() -> str | None:
    if os.name == "nt":
        return shutil.which("katex.cmd") or shutil.which("katex")
    return shutil.which("katex")


def _render_katex(snippet: str, display: bool = False) -> str | None:
    executable = _katex_executable()
    if not executable:
        return None
    command = [executable]
    if display:
        command.append("--display-mode")
    result = subprocess.run(
        command,
        input=snippet,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _render_plain(value: str) -> str:
    rendered = []
    last = 0
    for match in CLOZE_PATTERN.finditer(value or ""):
        rendered.append(html.escape(value[last : match.start()]))
        number = html.escape(match.group(1))
        answer = html.escape(match.group(2))
        hint = match.group(3)
        hint_html = f'<span class="cloze-hint"> ({html.escape(hint)})</span>' if hint else ""
        rendered.append(f'<mark class="cloze-answer"><span>c{number}</span>{answer}{hint_html}</mark>')
        last = match.end()
    rendered.append(html.escape((value or "")[last:]))
    return "".join(rendered)


def _render_text(value: str) -> str:
    value = clean_text(value)
    rendered = []
    last = 0
    for match in MATH_PATTERN.finditer(value or ""):
        rendered.append(_render_plain(value[last : match.start()]))
        inline_snippet = match.group(1)
        block_snippet = match.group(2)
        snippet = inline_snippet if inline_snippet is not None else block_snippet
        katex_html = _render_katex(snippet, display=block_snippet is not None)
        if katex_html:
            rendered.append(katex_html)
        else:
            rendered.append(html.escape(match.group(0)))
        last = match.end()
    rendered.append(_render_plain((value or "")[last:]))
    return "".join(rendered).replace("\n", "<br>")


def _card_image_html(card: dict[str, Any]) -> str:
    image_b64 = (card.get("source") or {}).get("image_b64")
    if not image_b64:
        return ""
    return f'<figure><img src="data:image/png;base64,{image_b64}" alt="clipboard image"></figure>'


def render_cards_html(cards: list[dict[str, Any]]) -> str:
    rendered_cards = []
    for index, card in enumerate(cards, start=1):
        status = "ok" if card.get("render_ok") else "bad"
        errors = card.get("validation_errors") or []
        warnings = card.get("validation_warnings") or []
        error_html = ""
        if errors:
            error_html = "<ul class=\"errors\">" + "".join(f"<li>{html.escape(err)}</li>" for err in errors) + "</ul>"
        warning_html = ""
        if warnings:
            warning_html = "<ul class=\"warnings\">" + "".join(
                f"<li>{html.escape(warning)}</li>" for warning in warnings
            ) + "</ul>"
        tags = ", ".join(card.get("tags") or [])
        front = _render_text(card.get("front") or "")
        back = _render_text(card.get("back") or "")
        rendered_cards.append(
            f"""
            <article class="card {status}">
              <header>
                <strong>{index}. {html.escape(card.get("type", "?"))}</strong>
                <span>{html.escape(tags)}</span>
              </header>
              <section class="front">{front}</section>
              <section class="back">{back}</section>
              {_card_image_html(card)}
              {error_html}
              {warning_html}
            </article>
            """
        )
    return "".join(rendered_cards)


def render_preview_html(cards: list[dict[str, Any]]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>anki-quickcap preview</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.17.0/dist/katex.min.css">
  <script>
    window.MathJax = {{ tex: {{ inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']] }} }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
  <style>
    :root {{ color-scheme: light dark; font-family: Segoe UI, system-ui, sans-serif; }}
    body {{ margin: 0; background: Canvas; color: CanvasText; }}
    main {{ width: min(980px, calc(100vw - 32px)); margin: 24px auto; }}
    h1 {{ font-size: 22px; margin: 0 0 16px; }}
    .card {{ border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 8px; padding: 16px; margin: 12px 0; }}
    .card.bad {{ border-color: #c62828; box-shadow: inset 4px 0 0 #c62828; }}
    header {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; font-size: 14px; color: color-mix(in srgb, CanvasText 72%, transparent); }}
    .front {{ font-size: 18px; margin-bottom: 12px; }}
    .back {{ border-top: 1px solid color-mix(in srgb, CanvasText 12%, transparent); padding-top: 12px; }}
    .cloze-answer {{ background: color-mix(in srgb, #f0b429 24%, Canvas); color: CanvasText; border: 1px solid color-mix(in srgb, #f0b429 55%, transparent); border-radius: 4px; padding: 0 4px; }}
    .cloze-answer span:first-child {{ font-size: 12px; font-weight: 700; margin-right: 4px; color: color-mix(in srgb, CanvasText 60%, transparent); }}
    .cloze-hint {{ color: color-mix(in srgb, CanvasText 70%, transparent); }}
    img {{ max-width: 100%; height: auto; border: 1px solid color-mix(in srgb, CanvasText 16%, transparent); border-radius: 6px; }}
    .errors {{ color: #c62828; }}
    .warnings {{ color: #a66b22; }}
  </style>
</head>
<body>
  <main>
    <h1>anki-quickcap preview</h1>
    {render_cards_html(cards)}
  </main>
</body>
</html>
"""


def write_preview(cards: list[dict[str, Any]], directory: str | Path | None = None) -> Path:
    output_dir = Path(directory) if directory else Path(tempfile.gettempdir())
    fd, path = tempfile.mkstemp(prefix=".quickcap_preview_", suffix=".html", dir=output_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(render_preview_html(cards))
    return Path(path)


def open_preview(cards: list[dict[str, Any]], open_browser: bool = True) -> Path:
    path = write_preview(cards)
    if open_browser:
        webbrowser.open(path.resolve().as_uri())
        print(f"Preview opened in browser: {path}")
    else:
        print(f"Preview written: {path}")
    return path


def edit_card(card: dict[str, Any], editor: str | None = None) -> dict[str, Any]:
    editor_command = editor or os.environ.get("EDITOR") or os.environ.get("VISUAL") or "notepad"
    fd, path = tempfile.mkstemp(prefix="quickcap_card_", suffix=".json")
    file_path = Path(path)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(card, ensure_ascii=False, indent=2))
    subprocess.run([editor_command, str(file_path)], check=False)
    return json.loads(file_path.read_text(encoding="utf-8"))


def review_cards(
    cards: list[dict[str, Any]],
    input_fn: Callable[[str], str] = input,
    open_browser: bool = True,
) -> list[dict[str, Any]] | None:
    if open_browser:
        open_preview(cards, open_browser=True)
    else:
        print("Terminal preview shown above. Press p to write an HTML preview file.")
    current = list(cards)
    while True:
        choice = input_fn("[a]ccept all, [p]review file, [e]dit N, [d]iscard N, [s]kip > ").strip()
        if choice in {"", "a"}:
            return current
        if choice == "p":
            open_preview(current, open_browser=open_browser)
            continue
        if choice == "s":
            return None
        parts = choice.split()
        if len(parts) >= 2 and parts[0] == "d":
            index = int(parts[1]) - 1
            if 0 <= index < len(current):
                current.pop(index)
            continue
        if len(parts) >= 2 and parts[0] == "e":
            index = int(parts[1]) - 1
            if 0 <= index < len(current):
                current[index] = edit_card(current[index])
            continue
        print("Unknown command.")
