# One-Folder Release

AutoAnki can be bundled with PyInstaller as a one-folder app.

Build locally:

```bash
uv sync --group release
uv run pyinstaller autoanki.spec --noconfirm
```

Output:

```text
dist/AutoAnki/
```

Run:

```bash
./dist/AutoAnki/AutoAnki
```

Copy `.env.example` to `dist/AutoAnki/.env`, fill in one provider key, then start the executable again.

The one-folder build includes `autoanki/system_prompt.txt`, so the executable can generate cards without needing the source tree. Runtime cards, custom prompt instructions, and decks are written beside the executable under `data/` and `output/`.
