# Model Providers

AutoAnki uses one active provider at a time. Pick it in `.env`:

```bash
AUTOANKI_PROVIDER=openrouter
AUTOANKI_TAGS=concept,definition,formula,process,comparison,example,mistake,workflow
AUTOANKI_TARGET_CARD_COUNT=3
```

You can also switch provider, model, and target card count in the web UI. The UI can load model names from provider list endpoints where available, and the model field always accepts a manually typed slug. API keys are not edited in the UI.

Supported values:

- `openrouter`
- `openai`
- `anthropic`
- `gemini`

Keys stay on your machine in `.env`. AutoAnki reads the clipboard or dropped file locally, sends only that capture to the active provider, then saves accepted cards to your local `data/cards.json`.

## OpenRouter

OpenRouter is the easiest default because one key can call Gemini, Claude, OpenAI, and open models.

```bash
AUTOANKI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=google/gemini-3.5-flash
```

## OpenAI

Use this if you already have OpenAI API billing enabled.

```bash
AUTOANKI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

Set the model explicitly so you choose the current price/performance point yourself.

## Anthropic

Use this for first-party Claude access.

```bash
AUTOANKI_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

## Gemini

Use this for first-party Google AI Studio / Gemini API access.

```bash
AUTOANKI_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash
```

## Safety

- The app is local-first.
- `.env` is ignored by Git.
- Dropped files are not uploaded anywhere except the selected model provider.
- Saved cards stay in `data/cards.json` unless you choose another path.
- Exported decks are normal `.apkg` files you import into Anki yourself.
