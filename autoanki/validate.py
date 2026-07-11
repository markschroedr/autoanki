from __future__ import annotations

import re
import shutil
import subprocess
import os
from dataclasses import dataclass, field
from typing import Any


INLINE_MATH = re.compile(r"\\\((.*?)\\\)", re.DOTALL)
BLOCK_MATH = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)
CLOZE = re.compile(r"\{\{c\d+::.+?\}\}", re.DOTALL)
VALID_TYPES = {"basic", "cloze"}
VALID_TAGS = {
    "concept",
    "definition",
    "formula",
    "process",
    "comparison",
    "example",
    "mistake",
    "workflow",
}


def configured_tags() -> set[str]:
    raw_tags = os.environ.get("AUTOANKI_TAGS", "")
    tags = {tag.strip() for tag in raw_tags.split(",") if tag.strip()}
    return tags or set(VALID_TAGS)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def extract_math_snippets(text: str) -> list[str]:
    return INLINE_MATH.findall(text or "") + BLOCK_MATH.findall(text or "")


def has_cloze_inside_math(text: str) -> bool:
    r"""Return whether a cloze deletion is nested inside MathJax delimiters.

    Anki accepts the opposite nesting, where the cloze wrapper surrounds the
    MathJax expression (for example ``{{c1::\(x\)}}``).  Only the invalid
    ``\({{c1::x}}\)`` form is rejected here.
    """
    return any(CLOZE.search(snippet) for snippet in extract_math_snippets(text))


def _validate_katex(snippet: str) -> tuple[bool | None, str | None]:
    executable = shutil.which("katex.cmd") if os.name == "nt" else None
    executable = executable or shutil.which("katex")
    if executable is None:
        return None, "katex CLI not found; math render check skipped"
    result = subprocess.run(
        [executable],
        input=snippet,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return True, None
    return False, result.stderr.strip() or "katex render failed"


def validate_card(
    card: dict[str, Any],
    check_math: bool = True,
    allowed_tags: set[str] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    card_type = card.get("type")
    if card_type not in VALID_TYPES:
        errors.append("type must be 'basic' or 'cloze'")

    front = str(card.get("front", ""))
    back = str(card.get("back", ""))
    if not front.strip():
        errors.append("front must not be empty")
    if card_type == "basic" and not back.strip():
        errors.append("basic cards need a back")
    if card_type == "cloze" and not CLOZE.search(front + "\n" + back):
        errors.append("cloze cards need at least one {{c1::...}} deletion")

    tags = card.get("tags", [])
    if not isinstance(tags, list):
        errors.append("tags must be a list")
    else:
        clean_tags = [tag for tag in tags if isinstance(tag, str)]
        valid_tags = configured_tags() if allowed_tags is None else allowed_tags
        unknown = [tag for tag in clean_tags if tag not in valid_tags]
        if unknown:
            errors.append(f"unknown tags: {', '.join(unknown)}")
        if len(clean_tags) > 2:
            errors.append("at most two tags are allowed")

    if "$" in front or "$" in back:
        errors.append("use \\(...\\) or \\[...\\] for MathJax, never $...$")

    if has_cloze_inside_math(front + "\n" + back):
        errors.append("cloze wrapper must surround MathJax delimiters, not appear inside them")

    if check_math:
        for snippet in extract_math_snippets(front + "\n" + back):
            ok, message = _validate_katex(snippet)
            if ok is None:
                warnings.append(message or "math render check skipped")
            elif not ok:
                errors.append(message or "math render failed")

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


def validate_cards(
    cards: list[dict[str, Any]],
    check_math: bool = True,
    allowed_tags: set[str] | None = None,
) -> list[ValidationResult]:
    results = []
    for card in cards:
        result = validate_card(card, check_math=check_math, allowed_tags=allowed_tags)
        card["render_ok"] = result.ok
        card["validation_errors"] = result.errors
        card["validation_warnings"] = result.warnings
        results.append(result)
    return results
