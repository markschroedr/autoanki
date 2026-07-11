# AutoAnki

Copy something worth remembering, get Anki cards back — reviewed by you before anything is saved.

AutoAnki is a small local tool. It takes text or screenshots from your clipboard, has an LLM of your choice draft a few cards, and shows them in a browser UI where you edit, discard, or accept them. Accepted cards export as a normal `.apkg` deck.

I built it for a control-engineering exam, but it's topic-agnostic: formulas, terminal commands, lecture notes, worked solutions, language learning.

## Why not just ask ChatGPT for cards?

Two reasons, both baked into the prompt (`autoanki/` — it's editable):

**The prompt is designed around what makes cards actually work.** LLMs naturally produce cards that look good but test nothing — the question implies the answer, or asks vocabulary instead of the crux. The system prompt forces two checks on every card: could someone *without* the knowledge guess the answer from the phrasing, and can someone *with* the knowledge answer it unambiguously. It also keeps fronts faithful to your material while letting backs explain and derive.

**You review before anything is saved.** No card enters your deck unseen. One bad card you rehearse for weeks costs more than the whole tool.

The model will also flag errors in your source material instead of carding them — useful when your notes were wrong in the first place.

## Install

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Anki for importing.

```bash
uv sync
cp .env.example .env
```

Fill in `.env`:

```bash
AUTOANKI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-5.6-sol
AUTOANKI_TARGET_CARD_COUNT=3
```

OpenRouter, OpenAI, Anthropic, and Gemini are supported — see `docs/providers.md`. Provider, model, and card count can be switched from the UI; keys stay in `.env` (git-ignored).

Optional: `bun add --global katex` for stricter math render checks.

## Use

```bash
uv run autoanki-web
```

1. Copy material (or drop a screenshot / text file into the UI)
2. Capture → review the drafted cards
3. Edit or discard weak ones, accept the rest
4. Export and import the `.apkg` into Anki

Saved cards stay editable in the UI and live in a single inspectable `data/cards.json`. `uv run autoanki --rebuild` regenerates the deck from saved cards; `--export-mode all` rebuilds everything.

There's also a CLI (`uv run autoanki`) and Windows `.cmd` launchers.

## Customize

The UI has a **Custom prompt** section for subject-specific instructions, appended to the generic prompt and stored locally in `data/custom_prompt.txt`. Example for a specific subject:

```bash
AUTOANKI_SUBJECT=programming workflows
AUTOANKI_TAGS=command,setup,debugging,workflow,mistake,concept
```

Different models produce noticeably different cards — frontier models catch source errors and find better cruxes. Worth testing a few against each other before settling; card generation is cheap either way.

## Data

Everything stays local. `.env`, `data/`, and `output/` are git-ignored. Card format: `examples/cards.example.json`.

AutoAnki only works from your clipboard — it doesn't scrape or bypass study platforms. Use it with material you're allowed to use.

## Development

```bash
uv run python -m unittest discover -s tests        # test suite
uv run python -m scripts.real_webui_e2e            # real-provider smoke test
```

```text
autoanki/    application package and editable prompts
scripts/     maintenance and smoke tests
tests/       test suite
```

PyInstaller build: `docs/release.md`.
