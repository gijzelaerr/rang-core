"""Identity sweep of research/gemclean-memory.md section 5 (post hoc, after the
J1833 measurement, on the advisor's list): the binary before the fix
against the binary after it, on G8's tiny MS (8 antennas, 8 channels, W1's
per-correlation flags and weights, so the polarisations do not all share
rows and weights), over the polarisation options the restructure touched.
Compares the exit code, every FITS file's SHA-256, the report's `entries`
and the mask record. The Stokes I cases (no `-pol`) were added after the
first sweep.

    sweep.py BEFORE_BINARY AFTER_BINARY OUTDIR   -> OUTDIR/sweep.json
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
    }


def main():
    before, after, outdir = sys.argv[1:4]
    outdir = Path(outdir)
    ms = tiny_ms(outdir / "tiny.ms")
    results = {}
    for name, extra in CASES.items():
        a = run(before, ms, outdir / name / "before", extra)
        b = run(after, ms, outdir / name / "after", extra)
        same = {k: a[k] == b[k] for k in ("exit", "files", "entries", "mask")}
        results[name] = {
            "identical": all(same.values()),
            "same": same,
            "exit": [a["exit"], b["exit"]],
            "files": len(a["files"]),
            "stderr": [a["stderr"], b["stderr"]] if a["exit"] or b["exit"] else None,
            "spill_left": b["spill_left"],
        }
        print(
            name,
            results[name]["identical"],
            results[name]["exit"],
            results[name]["files"],
        )
    (outdir / "sweep.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
