# Portable Windows Release

AutoAnki can be bundled as an unzip-and-run desktop app. It uses a native
webview while keeping the local Python server and all user files on disk.

Build locally:

```bash
powershell -ExecutionPolicy Bypass -File scripts/build_portable.ps1
```

Output:

```text
release/AutoAnki-Portable-Windows-x64.zip
```

Run:

```bash
Unzip the archive and double-click AutoAnki.exe.
```

Provider settings and API keys can be entered in the app. They are stored only
in the portable folder's `.env` file.

The archive contains only the entry point and runtime support at its top level,
plus `data/` for cards and `exports/` for generated Anki packages. Keep the
whole folder together when moving it between computers.
