import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
elif (SOURCE_ROOT / "pyproject.toml").exists():
    PROJECT_ROOT = SOURCE_ROOT
else:
    PROJECT_ROOT = Path.cwd()
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
CARDS_PATH = DATA_DIR / "cards.json"
DECK_PATH = OUTPUT_DIR / "autoanki.apkg"
