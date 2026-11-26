"""E2-N follow-up, job 1 (research/e2n-followup.md): CASA's 3b sequence with
each solve on the flags rang's own solve of that term saw ("seen", post hoc).

E2-N's `e2n_casa3b.py prep` gave every CASA solve FLAG after rang's calibrate
stage, which includes calibrate's `extendflags` on J1939-6342 and J1331+3030
(CARACal's polcal step, after crosscal). rang solved K, G, B and Gsec before
that step. Here:

    python fu_casa3b.py prep-a  MS R   FLAG = rang's "before calibrate" version (after flag)
    python fu_casa3b.py run-a   MS R   setjy x2, K, G, B, Gsec        -> R/casa/tables/
    python fu_casa3b.py prep-b  MS R   FLAG = rang's "before apply" version (after calibrate),
                                       E2-N's casa3b-n-prep state (hash checked)
    python fu_casa3b.py run-b   MS R   Gapp, fluxscale, Gpol, Kcross, Xf, Df, clip
    python fu_casa3b.py k-only  MS R VERSION LABEL [REFANT]   K alone on VERSION -> R/k-only-LABEL/

Every CASA call, refant list, minsnr and minblperant is e2n_casa3b.casa_calls
unchanged; only the flag state per call changes. `corr-prep` and `applycal`
are e2n_casa3b.py's, unchanged (applycal runs on the "before apply" flags, as
E2-N's).
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "research" / "results" / "e2n-scripts"),
                str(ROOT / "research" / "results" / "e2-acceptance-scripts")]  # fmt: skip

import e2_post as P
import e2n_casa3b as C
import e2n_nash  # noqa: F401  (patches e2_post.docker to apptainer)

SPLIT = 6  # casa_calls[:6] = setjy, setjy, K, G, B, Gsec; the rest after extendflags
E2N_PREP_HASH = "581207506477b3ccc7ff5f9ee27977f33b554449c0f759eeda985af87f501705"


def versions(r):
    s = json.loads((Path(r) / "rang-run" / "state.json").read_text())["stages"]
    return s["calibrate"]["flag_version"], s["apply"]["flag_version"]


def _restore(ms, r, version, label):
    from rang import core_writeback

    rows = core_writeback.restore_flags(Path(ms), version)
    h = P.flag_hash(Path(ms))
    P.write(
        Path(r) / f"fu-{label}.json", {"flag_version": version, "rows": rows, "hash": h}
    )
    return h


def _tasks(ms, r, calls, label):
    r = Path(r)
    P.write(r / f"{label}-spec.json", calls)
    rc = P.docker(r, P.CASA_IMAGE, [*P.inplace_mounts(ms, r), (ROOT / "examples", "/ex")],
                  f"/opt/casa/bin/python -I /ex/oracle_pol.py tasks /p/{label}-spec.json "
                  f"/p/{label}-tasks.json", label, 4)  # fmt: skip
    tasks = json.loads((r / f"{label}-tasks.json").read_text())
    errors = [(t["task"], t["error"]) for t in tasks if t["error"]]
    P.log(r, f"{label} tasks {len(tasks)} errors {errors}")
    return rc or (3 if errors else 0)


def prep_a(ms, r):
    C.restored_only(Path(ms))
    _restore(ms, r, versions(r)[0], "prep-a")
    return 0


def run_a(ms, r):
    r = Path(r)
    if not (r / "fu-prep-a.json").is_file():
        raise SystemExit("prep-a has not run")
    shutil.rmtree(r / "casa" / "tables", ignore_errors=True)
    (r / "casa" / "tables").mkdir(parents=True)
    calls = C.casa_calls(f"/c/{Path(ms).name}", C.refant_names(r))
    return _tasks(ms, r, calls[:SPLIT], "casa3b-fu-a")


def prep_b(ms, r):
    h = _restore(ms, r, versions(r)[1], "prep-b")
    if h["flag_sha256"] != E2N_PREP_HASH:
        raise SystemExit(f"FLAG after calibrate differs from E2-N's casa3b-n-prep: {h}")
    # e2n_casa3b.corr_prep / applycal and e2_rows_a read these names
    P.write(Path(r) / "casa3b-n-prep.json", {"flag_version": versions(r)[1], "hash": h})
    return 0


def run_b(ms, r):
    r = Path(r)
    if not (r / "fu-prep-b.json").is_file():
        raise SystemExit("prep-b has not run")
    calls = C.casa_calls(f"/c/{Path(ms).name}", C.refant_names(r))
    rc = _tasks(ms, r, calls[SPLIT:], "casa3b-fu-b")
    a = json.loads((r / "casa3b-fu-a-tasks.json").read_text())
    b = json.loads((r / "casa3b-fu-b-tasks.json").read_text())
    P.write(r / "casa3b-n-spec.json", calls)
    P.write(r / "casa3b-n-tasks.json", a + b)
    return rc


def k_only(ms, r, version, label, refant=None):
    """Mechanism probe only (not the fix): CASA's K call alone on VERSION,
    optionally with another refant list."""
    r = Path(r)
    _restore(ms, r, version, f"k-only-{label}")
    calls = C.casa_calls(f"/c/{Path(ms).name}", refant or C.refant_names(r))
    k = dict(calls[2])
    assert k["task"] == "gaincal" and k["args"]["gaintype"] == "K"
    k["args"] = {**k["args"], "caltable": f"/p/k-only-{label}/K"}
    shutil.rmtree(r / f"k-only-{label}", ignore_errors=True)
    (r / f"k-only-{label}").mkdir(parents=True)
    return _tasks(ms, r, [k], f"k-only-{label}")


if __name__ == "__main__":
    step, ms, r, *rest = sys.argv[1:]
    sys.exit({"prep-a": prep_a, "run-a": run_a, "prep-b": prep_b, "run-b": run_b,
              "k-only": k_only}[step](ms, r, *rest))  # fmt: skip
