#!/usr/bin/env python3
"""Anki Clipper - capture clipboard and create flashcards."""
import argparse
import logging
import sys
import traceback
import uuid

from config import CARDS_FILE, MEDIA_DIR, LOG_FILE

# Set up logging
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)


def save_image(b64: str) -> str:
    """Save image to media folder, return filename."""
    import base64
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"img_{uuid.uuid4().hex[:8]}.png"
    path = MEDIA_DIR / filename
    path.write_bytes(base64.b64decode(b64))
    log.info(f"Saved image: {filename}")
    return filename


def save_cards(cards: list[dict], image_filename: str | None):
    """Append cards to flashcards.txt."""
    CARDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(CARDS_FILE, "a", encoding="utf-8") as f:
        for card in cards:
            front = card["front"]
            back = card["back"]
            category = card.get("category", "General")

            if image_filename and card.get("image_placement"):
                img_tag = f'<img src="{image_filename}">'
                if card["image_placement"] == "front":
                    front = f"{img_tag}<br>{front}"
                else:
                    back = f"{img_tag}<br>{back}"

            front = front.replace("\t", " ").replace("\n", "<br>")
            back = back.replace("\t", " ").replace("\n", "<br>")
            category = category.replace("\t", " ").replace("\n", " ")

            f.write(f"{front}\t{back}\t{category}\n")

    log.info(f"Saved {len(cards)} card(s) to {CARDS_FILE}")


def run(text: str | None = None, hint: str | None = None, dry_run: bool = False, verbose: bool = False, skip_dialog: bool = False):
    """Main logic. If text is None, reads from clipboard."""
    from clipboard import get_clipboard
    from llm import generate_cards
    from notify import notify
    from prompt import ask_focus_hint

    # Get content
    if text is not None:
        clip_text, image_b64 = text, None
        log.info(f"Using provided text: {text[:50]}...")
    else:
        clip_text, image_b64 = get_clipboard()
        log.info(f"Clipboard: text={bool(clip_text)}, image={bool(image_b64)}")

    if not clip_text and not image_b64:
        msg = "Clipboard is empty"
        log.warning(msg)
        if not dry_run:
            notify("Anki Clipper", msg)
        return 1

    # Ask for focus hint via dialog (unless skipped or provided via CLI)
    if hint is None and not skip_dialog:
        hint = ask_focus_hint()
        if hint is None and not clip_text and not image_b64:
            log.info("User cancelled dialog")
            return 0  # User cancelled

    if hint:
        log.info(f"Focus hint: {hint}")

    # Generate cards
    log.info("Calling LLM...")
    cards = generate_cards(clip_text, image_b64, hint=hint)
    log.info(f"Generated {len(cards)} card(s)")

    if verbose or dry_run:
        print(f"\n{'='*50}")
        print(f"Generated {len(cards)} card(s):")
        for i, card in enumerate(cards, 1):
            print(f"\n--- Card {i} [{card.get('category', 'General')}] ---")
            print(f"Front: {card['front']}")
            print(f"Back: {card['back']}")
            if card.get("image_placement"):
                print(f"Image: {card['image_placement']}")
        print(f"{'='*50}\n")

    if not cards:
        msg = "No cards generated"
        log.warning(msg)
        if not dry_run:
            notify("Anki Clipper", msg)
        return 1

    if dry_run:
        print("[dry-run] Would save cards, but skipping.")
        return 0

    # Save
    image_filename = save_image(image_b64) if image_b64 else None
    save_cards(cards, image_filename)

    # Notify
    preview = cards[0]["front"][:80] + ("..." if len(cards[0]["front"]) > 80 else "")
    notify(f"Anki Clipper ({len(cards)} card{'s' if len(cards) > 1 else ''})", preview)

    return 0


def main():
    parser = argparse.ArgumentParser(description="Anki Clipper - create flashcards from clipboard")
    parser.add_argument("--text", "-t", help="Use this text instead of clipboard")
    parser.add_argument("--hint", "-H", help="Focus hint for the LLM")
    parser.add_argument("--no-dialog", "-q", action="store_true", help="Skip the focus hint dialog")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show cards but don't save")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print cards to stdout")
    args = parser.parse_args()

    log.info(f"=== Anki Clipper started (args: {vars(args)}) ===")

    try:
        return run(text=args.text, hint=args.hint, dry_run=args.dry_run, verbose=args.verbose, skip_dialog=args.no_dialog)
    except Exception as e:
        log.error(f"Error: {e}\n{traceback.format_exc()}")
        if not args.dry_run:
            from notify import notify
            notify("Anki Clipper Error", str(e)[:100])
        if args.verbose or args.dry_run:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
