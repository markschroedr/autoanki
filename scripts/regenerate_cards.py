from __future__ import annotations

import shutil
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoanki.generator import OpenRouterCardGenerator
from autoanki.paths import CARDS_PATH
from autoanki.quickcap import hydrate_cards
from autoanki.storage import load_cards, save_cards
from autoanki.text_clean import clean_source, clean_text
from autoanki.validate import validate_cards


REPORT_PATH = Path("regen_overwrite_report.md")


def unique_sources(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for card in cards:
        source = clean_source(card.get("source") or {})
        text = source.get("text") or ""
        image_b64 = source.get("image_b64")
        key = f"{text}\n<image:{bool(image_b64)}>"
        if key not in sources:
            sources[key] = {"text": text, "image_b64": image_b64}
    return list(sources.values())


def summarize_card(card: dict[str, Any]) -> list[str]:
    tags = ",".join(card.get("tags") or [])
    lines = [f"- [{card.get('type')} | {tags}] {clean_text(card.get('front', ''))}"]
    if card.get("back"):
        lines.append(f"  - Back: {clean_text(card.get('back', ''))}")
    errors = card.get("validation_errors") or []
    if errors:
        lines.append(f"  - Validation: {'; '.join(errors)}")
    return lines


def main() -> int:
    old_cards = load_cards(CARDS_PATH)
    sources = unique_sources(old_cards)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = Path(f"cards.backup_{timestamp}.json")
    if CARDS_PATH.exists():
        shutil.copy2(CARDS_PATH, backup_path)

    generator = OpenRouterCardGenerator()
    new_cards: list[dict[str, Any]] = []
    report = [
        "# AutoAnki Cards Regeneration Overwrite",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Backup: `{backup_path}`",
        f"Old cards: {len(old_cards)}",
        f"Unique inputs: {len(sources)}",
        "",
    ]

    for index, source in enumerate(sources, start=1):
        report.append(f"## Input {index}")
        report.append("")
        report.append("```text")
        report.append(clean_text(source.get("text") or "").strip())
        report.append("```")
        report.append("")

        result = generator.generate_result(source)
        if result.note_to_user:
            report.append(f"LLM note: {result.note_to_user}")
            report.append("")

        hydrated = hydrate_cards(result.cards, source)
        validate_cards(hydrated)
        new_cards.extend(hydrated)

        if hydrated:
            report.append("Generated cards:")
            for card in hydrated:
                report.extend(summarize_card(card))
        else:
            report.append("Generated cards: none")
        report.append("")

    save_cards(new_cards, CARDS_PATH)

    report.extend(
        [
            "## Summary",
            "",
            f"Replaced {len(old_cards)} old cards with {len(new_cards)} regenerated cards.",
        ]
    )
    REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Backed up old cards to {backup_path}")
    print(f"Replaced {len(old_cards)} old cards with {len(new_cards)} regenerated cards")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
