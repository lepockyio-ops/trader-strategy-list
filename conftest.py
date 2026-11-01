"""Run against a real, separately checked-out target framework; never mock its risk base."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRAMEWORK = Path(os.environ.get("FT_FRAMEWORK_ROOT", str(ROOT.parent / "freq-trader-framework-v2.13"))).resolve()
BASE = FRAMEWORK / "user_data" / "strategies"
if not (BASE / "framework_base.py").is_file():
    raise RuntimeError("Set FT_FRAMEWORK_ROOT to your freq-trader-framework checkout before running tests.")
sys.path.insert(0, str(BASE))
for directory in sorted(ROOT.glob("packs/*/user_data/strategies")):
    sys.path.insert(0, str(directory))
