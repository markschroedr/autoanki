"""Configuration for Anki Clipper."""
from pathlib import Path
import os

# OpenRouter API
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "anthropic/claude-opus-4.6"

# Paths
PROJECT_DIR = Path(__file__).parent
CARDS_FILE = PROJECT_DIR / "cards" / "flashcards.txt"
MEDIA_DIR = PROJECT_DIR / "cards" / "media"
LOG_FILE = PROJECT_DIR / "anki-clipper.log"
