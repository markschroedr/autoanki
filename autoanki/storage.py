from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import CARDS_PATH


def load_cards(path: str | Path = CARDS_PATH) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    if file_path.stat().st_size == 0:
        return []
    data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data
    raise ValueError(f"{file_path} must contain a JSON list")


def save_cards(cards: list[dict[str, Any]], path: str | Path = CARDS_PATH) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(cards, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_cards(new_cards: list[dict[str, Any]], path: str | Path = CARDS_PATH) -> list[dict[str, Any]]:
    cards = load_cards(path)
    cards.extend(new_cards)
    save_cards(cards, path)
    return cards
