"""No packaging step in this project, so the source tree goes on the path here."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
