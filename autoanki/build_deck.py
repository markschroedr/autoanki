from __future__ import annotations

import base64
import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .paths import CARDS_PATH, DECK_PATH
from .storage import load_cards, save_cards
from .text_clean import clean_text


DECK_ID = 2052420240
BASIC_MODEL_ID = 2052420241
CLOZE_MODEL_ID = 2052420242
DEFAULT_DECK_NAME = "AutoAnki::Quickcap"


class NoUnexportedCards(RuntimeError):
    pass


ExportMode = Literal["new", "all"]


def _stable_guid(card_id: str) -> str:
    return hashlib.sha1(card_id.encode("utf-8")).hexdigest()


def _media_filename(card: dict[str, Any]) -> str | None:
    image_b64 = (card.get("source") or {}).get("image_b64")
    if not image_b64:
        return None
    digest = hashlib.sha1(image_b64.encode("ascii")).hexdigest()[:16]
    return f"quickcap_{digest}.png"


def _with_source_image(html: str, card: dict[str, Any]) -> str:
    filename = _media_filename(card)
    if not filename:
        return html
    return f'{html}<br><img src="{filename}">'


def _unexported_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [card for card in cards if not card.get("exported_at")]


def _cards_for_export(cards: list[dict[str, Any]], export_mode: ExportMode) -> list[dict[str, Any]]:
    if export_mode == "all":
        return cards
    if export_mode == "new":
        return _unexported_cards(cards)
    raise ValueError(f"Unknown export mode: {export_mode}")


def apkg_output_path(output_path: str | Path) -> Path:
    output = Path(output_path)
    if output.suffix.lower() != ".apkg":
        output = output.with_name(f"{output.name}.apkg")
    return output


def build_deck(
    cards_path: str | Path = CARDS_PATH,
    output_path: str | Path = DECK_PATH,
    export_mode: ExportMode = "new",
) -> Path:
    try:
        import genanki
    except ImportError as exc:
        raise RuntimeError("genanki is missing; install dependencies with: uv sync") from exc

    cards = load_cards(cards_path)
    export_cards = _cards_for_export(cards, export_mode)
    if not export_cards:
        if export_mode == "all":
            raise NoUnexportedCards("No cards to export.")
        raise NoUnexportedCards("No new unexported cards to export.")

    deck = genanki.Deck(DECK_ID, os.environ.get("AUTOANKI_DECK_NAME", DEFAULT_DECK_NAME))
    basic_model = genanki.Model(
        BASIC_MODEL_ID,
        "Quickcap Basic",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[
            {
                "name": "Card 1",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=\"answer\">{{Back}}",
            }
        ],
    )
    cloze_model = genanki.Model(
        CLOZE_MODEL_ID,
        "Quickcap Cloze",
        fields=[{"name": "Text"}, {"name": "Back Extra"}],
        templates=[
            {
                "name": "Cloze",
                "qfmt": "{{cloze:Text}}",
                "afmt": "{{cloze:Text}}<br>{{Back Extra}}",
            }
        ],
        model_type=genanki.Model.CLOZE,
    )

    media_files: list[str] = []
    with tempfile.TemporaryDirectory(prefix="quickcap_media_") as media_dir:
        media_path = Path(media_dir)
        for card in export_cards:
            filename = _media_filename(card)
            if filename:
                full_path = media_path / filename
                full_path.write_bytes(base64.b64decode((card.get("source") or {})["image_b64"]))
                media_files.append(str(full_path))

            card_id = str(card["id"])
            tags = card.get("tags") or []
            if card.get("type") == "cloze":
                note = genanki.Note(
                    model=cloze_model,
                    fields=[
                        _with_source_image(clean_text(card.get("front", "")), card),
                        clean_text(card.get("back", "")),
                    ],
                    tags=tags,
                    guid=_stable_guid(card_id),
                )
            else:
                note = genanki.Note(
                    model=basic_model,
                    fields=[
                        clean_text(card.get("front", "")),
                        _with_source_image(clean_text(card.get("back", "")), card),
                    ],
                    tags=tags,
                    guid=_stable_guid(card_id),
                )
            deck.add_note(note)

        output = apkg_output_path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        genanki.Package(deck, media_files=media_files).write_to_file(str(output))

    exported_at = datetime.now(timezone.utc).isoformat()
    exported_ids = {card.get("id") for card in export_cards}
    for card in cards:
        if card.get("id") in exported_ids:
            card["exported_at"] = exported_at
    save_cards(cards, cards_path)
    return output


if __name__ == "__main__":
    print(build_deck())
