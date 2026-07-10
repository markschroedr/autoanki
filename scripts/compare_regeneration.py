from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoanki.generator import OpenRouterCardGenerator
from autoanki.paths import CARDS_PATH
from autoanki.storage import load_cards
from autoanki.text_clean import clean_source, clean_text
from autoanki.validate import validate_cards


REPORT_PATH = Path("regen_comparison.md")


def card_line(card: dict[str, Any]) -> list[str]:
    tags = ",".join(card.get("tags") or [])
    lines = [f"- [{card.get('type')} | {tags}]"]
    lines.append(f"  - Front: {clean_text(card.get('front', ''))}")
    if card.get("back"):
        lines.append(f"  - Back: {clean_text(card.get('back', ''))}")
    errors = card.get("validation_errors") or []
    if errors:
        lines.append(f"  - Validation: {'; '.join(errors)}")
    return lines


def group_cards(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        source = clean_source(card.get("source") or {})
        key = source.get("text") or f"<image:{bool(source.get('image_b64'))}>"
        groups[str(key)].append(card)
    return dict(groups)


def render_existing(cards: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        by_run[str(card.get("created", "unknown"))].append(card)
    for created, run_cards in sorted(by_run.items()):
        lines.append(f"### Before Run: `{created}`")
        for card in run_cards:
            lines.extend(card_line(card))
        lines.append("")
    return lines


def main() -> int:
    cards = load_cards(CARDS_PATH)
    groups = group_cards(cards)
    generator = OpenRouterCardGenerator()

    lines = [
        "# AutoAnki Regeneration Comparison",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Unique inputs: {len(groups)}",
        f"Existing cards: {len(cards)}",
        "",
        "This report does not modify `cards.json`.",
        "",
    ]

    for index, (source_text, existing_cards) in enumerate(groups.items(), start=1):
        source = {"text": source_text, "image_b64": None}
        result = generator.generate_result(source)
        regenerated = []
        for card in result.cards:
            regenerated.append(
                {
                    **card,
                    "render_ok": False,
                    "validation_errors": [],
                }
            )
        validate_cards(regenerated)

        lines.append(f"## Input {index}")
        lines.append("")
        lines.append("### Source")
        lines.append("")
        lines.append("```text")
        lines.append(source_text.strip())
        lines.append("```")
        lines.append("")
        lines.extend(render_existing(existing_cards))

        lines.append("### After: Regenerated With Current Prompt")
        if result.note_to_user:
            lines.append(f"- LLM note: {result.note_to_user}")
        if not regenerated:
            lines.append("- No cards generated.")
        for card in regenerated:
            lines.extend(card_line(card))
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
