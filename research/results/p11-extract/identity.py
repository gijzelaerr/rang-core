"""P11 live-chain identity: compare two suite output directories file by file.

Usage: python identity.py BEFORE AFTER OUT.json

Every file of BEFORE must exist in AFTER and vice versa (coverage data, logs
and `.time` files aside). JSON files are compared value by value after the
run directory prefix is normalised; every differing leaf is classified by the
keys on its path as `volatile` (timings, RSS, load), `provenance` (the
receipt fields research/p11-extract.md names) or `unexpected`. Other files are
compared by SHA256. Step exit statuses come from `timings.tsv`. Exit 0 when
nothing is unexpected.
"""

import hashlib
import json
import sys
from pathlib import Path

VOLATILE = {
    "seconds", "wall_seconds", "max_rss_mb", "max_rss_kb", "decode_seconds", "step_seconds",
    "timings", "elapsed", "started", "finished", "date", "load", "rust_seconds",
    "read_seconds", "ms_read_seconds", "seconds_total", "wall_seconds_excluding_decode",
    "process_max_rss_mb", "self_maxrss_mb", "peak_rss_mb", "max_rss_mb_self", "cost",
    "wall", "cpu", "rss", "time", "runtime", "duration", "started_utc", "cores_busy",
    "available_gib_at_start", "wall_excluding_decode", "git_status_unchanged",
    "parts_median", "parts_min",  # bench f timings
}
# Leaves that differed between two runs of the same commit (-01 and -01r):
# digests over results that contain timings, and the L1 cost ratio of timings.
CALIBRATION = None
PROVENANCE = {
    "module_sha256", "runtime_receipts", "code_sha256", "commit", "environment",
    # rang receipts (P9): directory digests over (path, size, mtime) and output
    # trees that include timing fields; the files themselves are compared directly
    "inputs", "outputs", "command",
    # the imaging comparator hashes core_imaging.py, whose import lines P11 edits
    "comparator_sha256",
    "git_head",
    # the extension file: check-all's ext-build rebuilt it between -03 and -04
    # from unchanged Rust sources (maturin builds are not byte-reproducible)
    "library_sha256", "core_library_sha256", "native_library_sha256",
}
SKIP_SUFFIX = {".log", ".time"}


def volatile_key(k):
    return k in VOLATILE or k.endswith(("_seconds", "_gbps")) or k.endswith("_s") and k[:-2] in VOLATILE


def walk(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append((path + [k], a.get(k, "<missing>"), b.get(k, "<missing>")))
            else:
                walk(a[k], b[k], path + [k], out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, path + [i], out)
    elif a != b:
        out.append((path, a, b))


def norm(text, root):
    return text.replace(str(root.resolve()), "<RUN>").replace(str(root), "<RUN>")


def classify(path, rel=None):
    keys = [k for k in path if isinstance(k, str)]
    if CALIBRATION and (rel, tuple(keys)) in CALIBRATION:
        return "volatile"
    if any(volatile_key(k) for k in keys):
        return "volatile"
    if any(k in PROVENANCE for k in keys):
        return "provenance"
    return "unexpected"


def main(before, after, out):
    before, after = Path(before), Path(after)
    files = lambda root: {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if (p.is_file() or p.is_symlink() and p.resolve().is_file())
        and not p.name.startswith(".coverage")
        and p.suffix not in SKIP_SUFFIX
        and p.name not in {"coverage.json", "coverage-report.txt", "timings.tsv"}
        and "/oracle/" not in "/" + p.relative_to(root).as_posix()
    }
    fa, fb = files(before), files(after)
    report = {"before": str(before), "after": str(after), "missing": sorted(fa - fb),
              "extra": sorted(fb - fa), "files": len(fa & fb), "json_files": 0,
              "binary_equal": 0, "differences": {"volatile": [], "provenance": [], "unexpected": []}}
    for rel in sorted(fa & fb):
        pa, pb = before / rel, after / rel
        if rel.endswith(".json"):
            report["json_files"] += 1
            try:
                ja = json.loads(norm(pa.read_text(), before))
                jb = json.loads(norm(pb.read_text(), after))
            except json.JSONDecodeError:
                ja, jb = pa.read_bytes(), pb.read_bytes()
            diffs = []
            walk(ja, jb, [], diffs)
            for p, x, y in diffs:
                report["differences"][classify(p, rel)].append(
                    {"file": rel, "path": p, "before": str(x)[:120], "after": str(y)[:120]})
        else:
            if hashlib.sha256(pa.read_bytes()).digest() == hashlib.sha256(pb.read_bytes()).digest():
                report["binary_equal"] += 1
            else:
                da = norm(pa.read_bytes().decode(errors="replace"), before)
                db = norm(pb.read_bytes().decode(errors="replace"), after)
                if da == db:
                    report["binary_equal"] += 1
                else:
                    report["differences"]["unexpected"].append({"file": rel, "path": [], "before": "bytes", "after": "bytes"})
    status = lambda root: {
        row.split("\t")[0]: row.split("\t")[6]
        for row in (root / "timings.tsv").read_text().splitlines()[1:]
    }
    sa, sb = status(before), status(after)
    report["exit_status"] = {"before": sa, "after": sb, "equal": sa == sb}
    for k in ("missing", "extra"):
        for rel in report[k]:
            report["differences"]["unexpected"].append({"file": rel, "path": [], "before": k, "after": k})
    if sa != sb:
        report["differences"]["unexpected"].append({"file": "timings.tsv", "path": ["status"], "before": str(sa), "after": str(sb)})
    counts = {k: len(v) for k, v in report["differences"].items()}
    report["counts"] = counts
    report["identical"] = counts["unexpected"] == 0
    # summarise which keys differed per class
    report["keys"] = {
        k: sorted({"/".join(str(x) for x in d["path"] if isinstance(x, str))[:100] + " @ " + d["file"].split("/")[0]
                   for d in v})
        for k, v in report["differences"].items() if k != "unexpected"
    }
    Path(out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"files": report["files"], "json_files": report["json_files"],
                      "binary_equal": report["binary_equal"], "counts": counts,
                      "exit_status_equal": sa == sb, "identical": report["identical"]}))
    for d in report["differences"]["unexpected"][:40]:
        print("UNEXPECTED", d)
    return 0 if report["identical"] else 1


if __name__ == "__main__":
    if "--calibration" in sys.argv:
        i = sys.argv.index("--calibration")
        cal = json.loads(Path(sys.argv[i + 1]).read_text())
        CALIBRATION = {
            (d["file"], tuple(k for k in d["path"] if isinstance(k, str)))
            for d in cal["differences"]["unexpected"]
            if d["path"] and not d["file"].startswith("bench-f")
        }
        del sys.argv[i : i + 2]
    sys.exit(main(*sys.argv[1:4]))
