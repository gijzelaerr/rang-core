"""Identity sweep of research/gemclean-memory2.md (phase 1's sweep.py with a
third arm): on G8's tiny MS (8 antennas, 8 channels, W1's per-correlation
flags and weights, so the polarisations do not all share rows and weights),
the baseline binary against this branch's binary without `-reorder` and
with `-reorder` (files in a separate `-temp-dir`), over phase 1's cases plus
`-channel-range` (where `-reorder` keeps the band read). Compares the exit
code, every FITS file's SHA-256, the report's `entries` and the mask
record, and lists any `.tmp` or `.spill` file left.

    sweep.py BASE_BINARY BRANCH_BINARY OUTDIR [MS CASE,CASE,...]   -> OUTDIR/sweep.json

With MS (post hoc, 2026-11-17) the given MS is used instead of G8's, with only
the named cases: the regression test's 120-dump case, read in two chunks, so
that the chunked read crosses a chunk boundary.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
from test_g8_gemclean import tiny_ms

BASE = ["-size", "128", "128", "-scale", "4asec", "-weight", "briggs", "0",
        "-niter", "2000", "-mgain", "0.8", "-auto-threshold", "3",
        "-data-column", "DATA", "-field", "0", "-no-update-model-required", "-j", "2"]  # fmt: skip
CASES = {
    "joined-iquv-mf": ["-pol", "IQUV", "-join-polarizations", "-channels-out", "2", "-join-channels"],
    "joined-iquv-masked": ["-pol", "IQUV", "-join-polarizations", "-channels-out", "2",
                           "-join-channels", "-auto-mask", "5"],
    "joined-iquv-per-channel": ["-pol", "IQUV", "-join-polarizations", "-channels-out", "2"],
    "joined-iquv-one-channel": ["-pol", "IQUV", "-join-polarizations"],
    "joined-iquv-fit": ["-pol", "IQUV", "-join-polarizations", "-channels-out", "4",
                        "-join-channels", "-fit-spectral-pol", "2"],
    "joined-iquv-no-plan-reuse": ["-pol", "IQUV", "-join-polarizations", "-channels-out", "2",
                                  "-join-channels", "-no-plan-reuse"],
    "joined-iquv-double": ["-pol", "IQUV", "-join-polarizations", "-channels-out", "2",
                           "-join-channels", "-double"],
    "joined-xx-yy": ["-pol", "XX,YY", "-join-polarizations", "-channels-out", "2", "-join-channels"],
    "joined-qu": ["-pol", "QU", "-join-polarizations", "-channels-out", "2", "-join-channels"],
    "unjoined-iquv-mf": ["-pol", "IQUV", "-channels-out", "2", "-join-channels"],
    "unjoined-iquv-per-channel": ["-pol", "IQUV", "-channels-out", "2"],
    "unjoined-iquv-one-channel": ["-pol", "IQUV"],
    "unjoined-iquv-audit": ["-pol", "IQUV", "-audit"],
    "unjoined-iquv-masked": ["-pol", "IQUV", "-auto-mask", "5"],
    # Stokes I (no -pol): the joined loop, the gridder's freed buffers and
    # the reader's chunks are shared with it.
    "stokes-i": [],
    "stokes-i-masked": ["-auto-mask", "5"],
    "stokes-i-channels": ["-channels-out", "2"],
    "stokes-i-joined": ["-channels-out", "2", "-join-channels"],
    "stokes-i-joined-masked": ["-channels-out", "2", "-join-channels", "-auto-mask", "5"],
    "stokes-i-joined-fit": ["-channels-out", "4", "-join-channels", "-fit-spectral-pol", "2"],
    "joined-iquv-channel-range": ["-pol", "IQUV", "-join-polarizations", "-channels-out", "2",
                                  "-join-channels", "-channel-range", "1", "7"],
}  # fmt: skip


def run(binary, ms, out, extra):
    out.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([binary, "-name", str(out / "g"), *BASE, *extra, str(ms)],
                       check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")  # fmt: skip
    files = {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(out.glob("*.fits"))
    }
    rep = out / "g-report.json"
    entries = (
        json.loads(rep.read_text(encoding="utf-8")).get("entries")
        if rep.is_file()
        else None
    )
    mask = out / "g-mask.json"
    return {
        "exit": p.returncode,
        "stderr": p.stderr.strip()[-300:],
        "files": files,
        "entries": entries,
        "mask": mask.read_text(encoding="utf-8") if mask.is_file() else None,
        "spill_left": sorted(f.name for f in out.glob("*.spill")),
        "tmp_left": sorted(f.name for f in out.parent.rglob("*.tmp")),
    }


def main():
    base, branch, outdir = sys.argv[1:4]
    outdir = Path(outdir)
    if len(sys.argv) > 5:
        ms, names = Path(sys.argv[4]), sys.argv[5].split(",")
    else:
        ms, names = tiny_ms(outdir / "tiny.ms"), list(CASES)
    results = {}
    for name in names:
        extra = CASES[name]
        tmp = outdir / name / "tmpdir"
        tmp.mkdir(parents=True, exist_ok=True)
        a = run(base, ms, outdir / name / "base", extra)
        b = run(branch, ms, outdir / name / "branch", extra)
        c = run(
            branch,
            ms,
            outdir / name / "reorder",
            [*extra, "-reorder", "-temp-dir", str(tmp)],
        )
        keys = ("exit", "files", "entries", "mask")
        results[name] = {
            "identical_default": all(a[k] == b[k] for k in keys),
            "identical_reorder": all(a[k] == c[k] for k in keys),
            "exit": [a["exit"], b["exit"], c["exit"]],
            "files": len(a["files"]),
            "stderr": [a["stderr"], c["stderr"]] if a["exit"] or c["exit"] else None,
            "left": b["spill_left"]
            + c["spill_left"]
            + c["tmp_left"]
            + sorted(f.name for f in tmp.iterdir()),
        }
        r = results[name]
        print(
            name,
            r["identical_default"],
            r["identical_reorder"],
            r["exit"],
            r["files"],
            r["left"],
        )
    (outdir / "sweep.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
