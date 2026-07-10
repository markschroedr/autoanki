# AutoAnki Development Notes

- Use `uv` for Python workflows. Do not add pip, Poetry, or Conda instructions.
- Keep `.env`, generated cards, exported decks, backups, and regeneration reports out of Git.
- Do not treat fake or mocked LLM paths as product verification. Unit tests may use fakes; user-facing verification should use `python -m scripts.real_webui_e2e` with a real OpenRouter key.
- Keep the app local-first. Do not add scraping, platform bypassing, browser automation against study websites, or hidden upload flows.
- Preserve the simple model: clipboard source, generated pending cards, reviewed saved cards, exported Anki deck.
