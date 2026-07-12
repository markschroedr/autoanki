import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if getattr(sys, "frozen", False):
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin" and executable.parent.name == "MacOS":
        PROJECT_ROOT = executable.parents[3]
    else:
        PROJECT_ROOT = executable.parent
elif (SOURCE_ROOT / "pyproject.toml").exists():
    PROJECT_ROOT = SOURCE_ROOT
else:
    PROJECT_ROOT = Path.cwd()
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / ("exports" if getattr(sys, "frozen", False) else "output")
CARDS_PATH = DATA_DIR / "cards.json"
DECK_PATH = OUTPUT_DIR / "autoanki.apkg"
CUSTOM_PROMPT_PATH = DATA_DIR / "custom_prompt.txt"
