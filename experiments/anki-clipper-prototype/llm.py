"""OpenRouter API calls."""
import json
import httpx
from config import OPENROUTER_API_KEY, MODEL

SYSTEM_PROMPT = """You create Anki flashcards from content the user shares.

Rules:
- MAXIMUM 3 cards. Usually 1-2 is enough.
- Only create multiple cards when genuinely useful:
  - For a principle/term: one card "What is X?" and one describing X asking for the name
  - For a formula: one card for the formula, one for applying it
- Do NOT invent extra cards if the core concept is already covered
- The FRONT must NOT give away the answer - it should prompt recall
- Use LaTeX for math: \\(...\\) inline, \\[...\\] for blocks
- Keep cards atomic - one concept per card

Call the create_flashcards tool with your cards."""

TOOL = {
    "name": "create_flashcards",
    "description": "Create Anki flashcards from the content",
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "front": {"type": "string", "description": "Question/prompt (must not reveal answer)"},
                        "back": {"type": "string", "description": "Answer"},
                        "category": {"type": "string", "description": "Topic category for sorting"},
                        "image_placement": {
                            "type": "string",
                            "enum": ["front", "back"],
                            "description": "Where to embed the image (only if image was provided)"
                        }
                    },
                    "required": ["front", "back", "category"]
                },
                "maxItems": 3
            }
        },
        "required": ["cards"]
    }
}


def generate_cards(text: str | None, image_b64: str | None, hint: str | None = None) -> list[dict]:
    """Call OpenRouter API to generate flashcards."""
    content = []

    if image_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"}
        })

    # Build the user message
    user_text = text if text else "Create flashcard(s) from this image."
    if hint:
        user_text = f"{user_text}\n\nFocus on: {hint}"
    content.append({"type": "text", "text": user_text})

    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content}
            ],
            "tools": [{"type": "function", "function": TOOL}],
            "tool_choice": {"type": "function", "function": {"name": "create_flashcards"}}
        },
        timeout=60
    )
    resp.raise_for_status()

    data = resp.json()

    # Debug: log full response if tool_calls missing
    msg = data["choices"][0]["message"]
    if "tool_calls" not in msg or not msg["tool_calls"]:
        # Model didn't use tool, try to parse content directly
        import logging
        logging.warning(f"No tool_calls in response. Message: {msg}")
        raise ValueError(f"Model didn't return tool call. Response: {msg.get('content', 'empty')[:200]}")

    tool_call = msg["tool_calls"][0]
    args_str = tool_call["function"]["arguments"]

    if not args_str:
        raise ValueError("Empty tool arguments from model")

    args = json.loads(args_str)
    cards = args.get("cards", [])

    # Validate cards structure
    if isinstance(cards, str):
        raise ValueError(f"Model returned string instead of cards array: {cards[:100]}")

    if not isinstance(cards, list):
        raise ValueError(f"Expected cards array, got {type(cards)}")

    # Validate each card has required fields
    valid_cards = []
    for card in cards:
        if isinstance(card, dict) and "front" in card and "back" in card:
            valid_cards.append(card)

    return valid_cards[:3]  # Enforce max 3 cards
