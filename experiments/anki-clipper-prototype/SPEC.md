# Anki Clipper - Technical Spec

## Purpose
Hotkey-triggered tool that captures clipboard content (text or image), sends it to an LLM, and generates Anki-compatible flashcards stored in an append-only file.

## Architecture
**Zero-idle-cost design**: No Python process runs until needed.
- `skhd` (lightweight C daemon, ~2MB RAM) listens for hotkey
- On keypress, spawns `uv run python main.py`
- Script does its job and exits immediately

## Core Flow
1. `skhd` detects `Ctrl+Shift+A`
2. Spawns Python script via `uv run`
3. Script grabs clipboard (text or image)
4. **Popup dialog** asks for optional focus hint (can be skipped)
5. Sends to OpenRouter API (Claude Opus 4.5) with tool call
6. LLM returns structured cards: `{front, back, category, image_placement?}`
7. Appends to `cards/flashcards.txt` in Anki-importable TSV format
8. Shows macOS notification with preview
9. Script exits

## Decisions
- **Hotkey**: `Ctrl+Shift+A` via skhd (`~/.skhdrc`)
- **Feedback**: macOS notification with card preview
- **Focus hint**: Optional popup dialog to guide LLM
- **Images**: Sent to LLM; LLM can embed on front or back via tool param
- **Model**: `anthropic/claude-opus-4.6` via OpenRouter (env: `OPENROUTER_API_KEY`)
- **Storage**: `cards/` folder with `media/` subfolder for images

## Constraints
- Max 3 cards per trigger
- Front side must NOT give away the answer
- LaTeX: `\(...\)` inline, `\[...\]` block

## Output Format
Tab-separated (Anki import format):
```
front\tback\tcategory
```

Images embedded as `<img src="filename.png">` in front or back.

## Stack
- `skhd` — hotkey daemon (brew install)
- Python 3.10+ via `uv`
- `httpx` — API calls
- `Pillow` — image handling
- `pyobjc-framework-Cocoa` — clipboard reading

## CLI Usage
```bash
cd anki-clipper

# From clipboard with popup dialog
uv run python main.py

# Skip dialog, use clipboard directly
uv run python main.py --no-dialog

# Use specific text with hint
uv run python main.py --text "E=mc²" --hint "focus on the formula"

# Dry run: generate cards but don't save
uv run python main.py --dry-run --verbose

# Combine flags
uv run python main.py -t "content" -H "hint" -n -v -q
```

**Flags:**
- `--text, -t` — Use this text instead of clipboard
- `--hint, -H` — Focus hint for the LLM
- `--no-dialog, -q` — Skip the focus hint popup
- `--dry-run, -n` — Show cards without saving
- `--verbose, -v` — Print cards to stdout

## Logging
All runs logged to `anki-clipper.log` with timestamps and full tracebacks on error.

```bash
tail -f anki-clipper.log  # Watch live
```

## Setup
1. Ensure `OPENROUTER_API_KEY` is set in `~/.zshrc`
2. Start skhd: `skhd --start-service`
3. Press `Ctrl+Shift+A` with content in clipboard
