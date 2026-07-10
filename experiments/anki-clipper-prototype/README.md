# Anki Clipper Prototype

This is the first prototype that led to AutoAnki. It is kept for reference, not as a second supported application. Generated cards and local configuration were deliberately left out.

Create Anki TSV flashcards from clipboard text or images using OpenRouter.

### Windows (uv)

1. Install `uv`: https://docs.astral.sh/uv/
2. Open PowerShell or `cmd` in this project folder.
3. Run:

```bat
run_windows.bat
```

Create a sharable zip bundle:

```bat
export_windows.bat
```

Pass the same CLI flags as the main script:

```bat
run_windows.bat --no-dialog --verbose
run_windows.bat --text "E=mc^2" --hint "focus on formula meaning"
```

### Python Entry Point

```bash
uv run python main.py
```

### Card Output

Cards are appended to `cards/flashcards.txt` as:

```text
front\tback\tcategory
```

The schema keys returned by the model remain unchanged:
- `front`
- `back`
- `category`
- `image_placement` (optional, `front` or `back`)
