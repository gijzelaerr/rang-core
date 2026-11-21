"""apply-calwt (#48), research/apply-calwt.md section 5 (O): CASA applycal on
the same MS with the calls rebuilt from rang's apply summary (tables,
gainfield, interp, calwt as rang applied them; E2's `e2_post.applycal_spec`),
restricted to the target ASKAPJ1745, run by apptainer on nash
(`e2n_nash.py`'s `P.docker`).

    python calwt_oracle.py MS R      # R/rang-run -> the MS's run directory
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "research" / "results" / "e2n-scripts"),
                str(ROOT / "research" / "results" / "e2-acceptance-scripts")]  # fmt: skip

import e2n_nash  # noqa: E402,F401  (patches e2_post.docker to apptainer)
import e2_post as P  # noqa: E402

TARGET = "ASKAPJ1745"


def main(ms, r):
    ms, r = Path(ms), Path(r)
    calls = [c for c in P.applycal_spec(r, f"/c/{ms.name}") if c["field"] == TARGET]
    if len(calls) != 1 or not any(calls[0]["calwt"]):
        raise SystemExit(f"expected one target call with calwt: {calls}")
    P.write(r / "applycal-spec.json", calls)
    (r / "e2p_applycal.py").write_text(P.APPLY_PY, encoding="utf-8")
    return P.docker(r, P.CASA_IMAGE, P.inplace_mounts(ms, r),
                    "/opt/casa/bin/python -I /p/e2p_applycal.py /p/applycal-spec.json "
                    "/p/applycal-result.json", "casa-applycal", 4)  # fmt: skip


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
