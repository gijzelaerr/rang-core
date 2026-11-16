"""E2-N gate 3b's score: E2-B's `e2_score3b.py` with the secondary J1744-5144
(E2-B: J1833-2103) and without E2-B's seal (6.7 of e2-acceptance.md, which
does not apply to E2-N). Rang's tables R/rang-run/calibrate against CASA's
R/casa/tables (e2n_casa3b.py); class B per term and the composites.

    python e2n_score3b.py R MS        -> R/g3b.json
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "e2-acceptance-scripts"))

import e2_score3b as S

S.GCAL = os.environ.get("E2N_GCAL", "J1744-5144")  # E2N_GCAL: the dry run only
S.guard = lambda r, dev: None

if __name__ == "__main__":
    sys.exit(S.main(sys.argv[1:]))
