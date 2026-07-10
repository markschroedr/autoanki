# AutoAnki

AutoAnki turns clipboard snippets into reviewable Anki cards.

It is a small local tool for studying: copy a paragraph, formula, or screenshot, click capture, let an LLM draft a few cards, review them, then export an `.apkg` deck for Anki.

I first built it for control-engineering notes, but the default setup is topic-agnostic. You can use it for equations, terminal commands, lecture notes, worked solutions, language learning, or practical workflows.

## What it does

- Captures text and images from the clipboard.
- Accepts drag-and-drop images, text files, markdown files, and plain text selections in the web UI.
- Sends the capture to OpenRouter, OpenAI, Anthropic, or Gemini.
- Shows pending cards in a local browser UI before saving them.
- Validates Anki card shape and MathJax syntax.
- Exports new cards or rebuilds a deck from every saved card.
- Stores cards in one inspectable `data/cards.json` file.

## Install

Requirements:

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Anki, for importing the exported `.apkg`
- Optional: KaTeX CLI for math render checks

```bash
uv sync
```

For stricter MathJax/LaTeX feedback, install the KaTeX CLI separately:

```bash
bun add --global katex
```

## Configure

Create a local `.env` file:

```bash
cp .env.example .env
```

Then fill in:

```bash
AUTOANKI_PROVIDER=openrouter
AUTOANKI_TAGS=concept,definition,formula,process,comparison,example,mistake,workflow
AUTOANKI_TARGET_CARD_COUNT=3
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=google/gemini-3.5-flash
```

The `.env` file is ignored by Git. Do not commit API keys.

You can switch provider, model, and target card count from the web UI. API keys still stay in `.env`; the UI only writes `AUTOANKI_PROVIDER`, the selected provider's model variable, and `AUTOANKI_TARGET_CARD_COUNT`.

See `docs/providers.md` for OpenAI, Anthropic, and Gemini setup.

Optional subject-specific setup:

```bash
AUTOANKI_SUBJECT=programming workflows
AUTOANKI_TAGS=command,setup,debugging,workflow,mistake,concept
```

## Run

Browser UI:

```bash
uv run autoanki-web
```

CLI:

```bash
uv run autoanki
```

Rebuild the Anki deck from saved cards:

```bash
uv run autoanki --rebuild
```

Use `uv run autoanki --rebuild --export-mode all` to rebuild from every saved card. The deck is written to `output/autoanki.apkg`.

On Windows, the three `.cmd` launchers start the browser UI, start the CLI, or stop the running browser UI.

## Workflow

1. Copy study material into the clipboard.
2. Click `Capture Clipboard` in the local web UI, or drop a screenshot / text file / markdown file into the drop zone.
3. Review the generated cards.
4. Edit or discard weak cards.
5. Accept the good cards.
6. Export the `.apkg`.
7. Import it into Anki.

Use this with material you are allowed to use. AutoAnki does not scrape or bypass study platforms; it only works from your clipboard.

## Tests

```bash
uv run python -m unittest discover -s tests
```

Real OpenRouter smoke test:

```bash
uv run python -m scripts.real_webui_e2e
```

That smoke test calls the configured model, generates real cards, saves them in a temporary file, exports a temporary deck, and verifies the download path.

## Data

Generated local files are intentionally ignored:

- `.env`
- `data/` (cards, pending-generation recovery log, and backups)
- `output/` (generated Anki decks)
- regeneration reports
- preview HTML files

See `examples/cards.example.json` for the card format.

## Project structure

```text
autoanki/    application package and editable LLM prompt
scripts/     maintenance and real-provider smoke tests
tests/       automated test suite
experiments/ earlier prototypes kept for reference
data/        local cards and recovery data (ignored)
output/      generated Anki decks (ignored)
```

The original Anki Clipper prototype is preserved under `experiments/anki-clipper-prototype`. It used direct TSV output and a small focus-hint dialog. AutoAnki replaced that flow with reviewed cards, validation, provider choice, and `.apkg` export.

## One-folder app

The PyInstaller build path is documented in `docs/release.md`.
