"""Run examples/floor3_score.py with floor_tests paths from RANG_FLOOR_HELD (set by floor5_tests)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "Worktrees/rang/floor-5/examples"))
import floor5_tests  # noqa: F401  (setpaths)
import floor3_score
floor3_score.main(sys.argv[1:])
