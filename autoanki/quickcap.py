from __future__ import annotations

import argparse
import re
import shutil
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .build_deck import ExportMode, NoUnexportedCards, build_deck
from .generator import GenerationResult, OpenRouterCardGenerator, image_to_b64
from .paths import CARDS_PATH, DECK_PATH
from .preview import review_cards
from .storage import append_cards, get_stack, load_store
from .text_clean import clean_cards, clean_source
from .validate import configured_tags, validate_cards


MATH_PATTERN = re.compile(r"\\\((.*?)\\\)|\\\[(.*?)\\\]", re.DOTALL)
LATEX_SYMBOLS = {
    r"\omega": "ω",
    r"\Omega": "Ω",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\Delta": "Δ",
    r"\phi": "φ",
    r"\varphi": "φ",
    r"\tau": "τ",
    r"\zeta": "ζ",
    r"\infty": "∞",
    r"\rightarrow": "→",
    r"\to": "→",
    r"\leftarrow": "←",
    r"\Rightarrow": "⇒",
    r"\cdot": "·",
    r"\times": "×",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\approx": "≈",
    r"\pm": "±",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_tags(value: str) -> list[str]:
    cleaned = value.strip()
    if cleaned.startswith("t "):
        cleaned = cleaned[2:].strip()
    tags = [tag.strip() for tag in cleaned.split(",") if tag.strip()]
    unknown = [tag for tag in tags if tag not in configured_tags()]
    if unknown:
        raise ValueError(f"unknown tags: {', '.join(unknown)}")
    return tags[:2]


def capture_clipboard() -> dict[str, Any]:
    source: dict[str, Any] = {"text": None, "image_b64": None}

    try:
        from PIL import ImageGrab

        image = ImageGrab.grabclipboard()
        if image is not None and hasattr(image, "save"):
            source["image_b64"] = image_to_b64(image)
    except Exception:
        pass

    try:
        import pyperclip

        text = pyperclip.paste()
        if text and text.strip():
            source["text"] = text
    except Exception:
        pass

    if not source.get("text") and not source.get("image_b64"):
        raise RuntimeError("clipboard did not contain text or an image")
    return source


def hydrate_cards(cards: list[dict[str, Any]], source: dict[str, Any]) -> list[dict[str, Any]]:
    source = clean_source(source)
    cards = clean_cards(cards)
    hydrated = []
    for card in cards:
        hydrated.append(
            {
                "id": card.get("id") or str(uuid.uuid4()),
                "created": card.get("created") or now_iso(),
                "type": card.get("type"),
                "front": card.get("front", ""),
                "back": card.get("back", ""),
                "tags": card.get("tags") or [],
                "source": {"text": source.get("text"), "image_b64": source.get("image_b64")},
                "render_ok": False,
            }
        )
    return hydrated


def render_terminal_math(text: str) -> str:
    def simplify_snippet(snippet: str) -> str:
        simplified = snippet
        simplified = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", simplified)
        simplified = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", simplified)
        for latex, symbol in LATEX_SYMBOLS.items():
            simplified = simplified.replace(latex, symbol)
        simplified = simplified.replace(r"\,", " ")
        simplified = simplified.replace(r"\;", " ")
        simplified = simplified.replace("{", "").replace("}", "")
        simplified = re.sub(r"\s+", " ", simplified)
        return simplified.strip()

    def replace(match: re.Match[str]) -> str:
        snippet = match.group(1) if match.group(1) is not None else match.group(2)
        return simplify_snippet(snippet or "")

    return MATH_PATTERN.sub(replace, text or "")


def wrapped(label: str, value: str, width: int) -> list[str]:
    text = render_terminal_math(value)
    initial = f"{label}: "
    subsequent = " " * len(initial)
    return textwrap.wrap(
        text,
        width=max(40, width),
        initial_indent=initial,
        subsequent_indent=subsequent,
        break_long_words=False,
        replace_whitespace=False,
    ) or [initial]


def print_cards(cards: list[dict[str, Any]]) -> None:
    width = min(shutil.get_terminal_size((100, 24)).columns, 120)
    for index, card in enumerate(cards, start=1):
        tags = ",".join(card.get("tags") or [])
        print(f"\n{index}. [{card.get('type')} | {tags}] MathJax render: {'OK' if card.get('render_ok') else 'FAIL'}")
        for line in wrapped("Front", card.get("front", ""), width):
            print(line)
        if card.get("back"):
            for line in wrapped("Back ", card.get("back", ""), width):
                print(line)
        for error in card.get("validation_errors") or []:
            print(f"      ! {error}")


def generate_with_note(generator: Any, source: dict[str, Any], forced_tags: list[str] | None = None) -> GenerationResult:
    if hasattr(generator, "generate_result"):
        return generator.generate_result(source, forced_tags=forced_tags)
    return GenerationResult(cards=generator.generate(source, forced_tags=forced_tags), note_to_user="")


def process_source(
    source: dict[str, Any],
    cards_path: str | Path = CARDS_PATH,
    forced_tags: list[str] | None = None,
    generator: Any | None = None,
    review_fn: Callable[..., list[dict[str, Any]] | None] = review_cards,
    open_browser: bool = False,
) -> list[dict[str, Any]]:
    generator = generator or OpenRouterCardGenerator()
    generation = generate_with_note(generator, source, forced_tags=forced_tags)
    if generation.note_to_user:
        print(f"\nLLM note: {generation.note_to_user}")
    raw_cards = generation.cards
    cards = hydrate_cards(raw_cards, source)
    validate_cards(cards)
    print_cards(cards)
    if not cards:
        print("No cards generated.")
        return []

    accepted = review_fn(cards, open_browser=open_browser)
    if not accepted:
        print("Skipped.")
        return []
    validate_cards(accepted)
    total = append_cards(accepted, cards_path)
    print(f"Saved {len(accepted)} cards -> {cards_path} (total: {len(total)})")
    return accepted


def parse_export_mode(command: str) -> ExportMode | None:
    parts = command.split()
    if not parts or parts[0] not in {"r", "rebuild", "export"}:
        return None
    if len(parts) == 1:
        return "new"
    if len(parts) == 2 and parts[1] in {"new", "all"}:
        return parts[1]  # type: ignore[return-value]
    raise ValueError("Use export, export new, or export all.")


def run_loop(cards_path: str | Path = CARDS_PATH, open_browser: bool = False) -> None:
    print("ready (Enter = capture clipboard, q/stop = quit, export [new|all] = rebuild deck, web = browser UI)")
    generator = OpenRouterCardGenerator()
    while True:
        command = input("> ").strip()
        if command in {"q", "quit", "stop", "close"}:
            return
        try:
            export_mode = parse_export_mode(command)
        except ValueError as exc:
            print(str(exc))
            continue
        if export_mode:
            try:
                print(f"Built deck: {build_deck(cards_path, export_mode=export_mode)}")
            except NoUnexportedCards as exc:
                print(str(exc))
            continue
        if command == "web":
            from .webui import run_server

            run_server(cards_path=cards_path, open_browser=open_browser)
            continue
        if command:
            print("Unknown command. Use Enter, q/stop, export [new|all], or web.")
            continue

        try:
            source = capture_clipboard()
            if source.get("image_b64"):
                print("read clipboard: image (PNG)")
            if source.get("text"):
                print(f"read clipboard: text ({len(source['text'])} chars)")
            print("generating cards...")
            process_source(
                source,
                cards_path=cards_path,
                forced_tags=None,
                generator=generator,
                open_browser=open_browser,
            )
        except Exception as exc:
            print(f"Error: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quickly turn clipboard captures into Anki cards.")
    parser.add_argument("--rebuild", action="store_true", help="rebuild an Anki deck from saved cards")
    parser.add_argument("--cards", default=CARDS_PATH, help="path to cards.json")
    parser.add_argument("--output", default=DECK_PATH, help="deck output path")
    parser.add_argument("--export-mode", choices=["new", "all"], default="new", help="export only new cards or all cards")
    parser.add_argument("--stack", help="stack name or stable ID (defaults to the active stack)")
    parser.add_argument("--all-stacks", action="store_true", help="export every stack as separate Anki decks")
    parser.add_argument("--browser", action="store_true", help="open the HTML preview from the CLI")
    args = parser.parse_args(argv)

    if args.rebuild:
        try:
            stack_id = None
            if args.stack:
                store = load_store(args.cards)
                try: stack_id = get_stack(store, args.stack)["id"]
                except ValueError: stack_id = get_stack(store, stack_name=args.stack)["id"]
            print(build_deck(args.cards, args.output, export_mode=args.export_mode, stack_id=stack_id, scope="all" if args.all_stacks else "selected"))
        except NoUnexportedCards as exc:
            print(str(exc))
        return 0
    run_loop(args.cards, open_browser=args.browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
