"""Archive two O-CASA runs and check that they reproduce (research/o-casa.md).

Host python3, stdlib only.
  archive.py <run1> <run2> <build.json> <out.json> [post-hoc dir ...]
Gated hashes: per-column caltable hashes, CORRECTED_DATA, FLAG and MODEL_DATA
of every arm, flagdata FLAG, flux-standard models, WSClean pixel arrays, the
rebuilt MS columns and the split. Raw table-tree hashes are reported only.
"""

import json
import sys
from pathlib import Path


def load(run, name):
    path = Path(run) / name
    return json.loads(path.read_text()) if path.exists() else None


def gated(run):
    s = load(run, "summary.json")
    out = {}
    for arm, entry in s["arms"].items():
        for kind, table in entry["tables"].items():
            for column, digest in (table.get("column_sha256") or {}).items():
                out[f"arms.{arm}.{kind}.{column}"] = digest
        for key in ("corrected_sha256", "flag_sha256"):
            if key in entry:
                out[f"arms.{arm}.{key}"] = entry[key]
        out[f"arms.{arm}.model"] = entry["model"]["sha256"]
    for mode, entry in s["flagdata"].items():
        out[f"flagdata.{mode}"] = entry["flag_sha256"]
    for standard, entry in s["flux_standards"].items():
        out[f"flux_standards.{standard}"] = entry["sha256"]
    for name, image in s["images"].items():
        out[f"images.{name}.dirty"] = image["dirty_pixels_sha256"]
        out[f"images.{name}.psf"] = image["psf_pixels_sha256"]
    for column, digest in load(run, "ms-equality.json")["main_hashes"].items():
        out[f"work_ms.{column}"] = digest
    split = load(run, "split.json")
    out["split.validation"] = split["validation_sha256"]
    out["split.test"] = split["test_sha256"]
    return out


def trees(run):
    s = load(run, "summary.json")
    return {
        f"{arm}.{kind}": table["tree_sha256"]
        for arm, entry in s["arms"].items()
        for kind, table in entry["tables"].items()
        if table.get("exists")
    }


def strip_arm(entry):
    out = {k: v for k, v in entry.items() if k not in ("tables",)}
    out["model"] = {k: v for k, v in entry["model"].items() if k != "sha256"}
    out["tables"] = {}
    for kind, table in entry["tables"].items():
        out["tables"][kind] = {
            k: v for k, v in table.items() if k not in ("column_sha256", "tree_sha256")
        }
        if table.get("exists"):
            out["tables"][kind]["cparam_or_fparam_sha256"] = table["column_sha256"].get(
                table["par_column"]
            )
    return out


def solve_logs(run):
    out = {}
    for path in sorted((Path(run) / "casa").glob("*.json")):
        log = json.loads(path.read_text())
        tasks = {}
        for label, entry in log.get("tasks", {}).items():
            returned = entry.get("returned")
            if label.startswith(("gaincal", "bandpass")) and isinstance(returned, dict):
                returned = {
                    k: returned[k]
                    for k in ("solvestats", "expected", "attempted", "succeeded")
                    if k in returned
                }
            tasks[label] = {
                "ok": entry["ok"],
                "error": entry.get("error"),
                "seconds": round(entry["seconds"], 3),
                "params": entry["params"],
                "returned": returned,
            }
        keep = {
            k: log[k]
            for k in (
                "refant",
                "refant_auto",
                "minblperant",
                "uvrange",
                "manual_model",
                "baseline_lengths_m",
                "antennas",
                "field",
                "caracal_commit",
                "skipped",
            )
            if k in log
        }
        keep["tasks"] = tasks
        out[path.stem] = keep
    return out


def main(argv):
    run1, run2, build, out = argv[1:5]
    g1, g2 = gated(run1), gated(run2)
    differences = sorted(k for k in set(g1) | set(g2) if g1.get(k) != g2.get(k))
    t1, t2 = trees(run1), trees(run2)
    summary = load(run1, "summary.json")
    receipt1, receipt2 = load(run1, "receipt.json"), load(run2, "receipt.json")
    archive = {
        "protocol": "research/o-casa.md",
        "provisional": "LUNO licence: SARAO written confirmation pending; no visibilities",
        "image": json.loads(Path(build).read_text()) | {"receipt": receipt1["image"]},
        "runs": {
            Path(r).name: {
                "timings": rec["timings"],
                "code_sha256": rec["code_sha256"],
                "outputs": len(rec["outputs_sha256"]),
            }
            for r, rec in ((run1, receipt1), (run2, receipt2))
        },
        "inputs_check": receipt1["inputs_check"],
        "ms_equality": {
            k: v
            for k, v in load(run1, "ms-equality.json").items()
            if k != "main_hashes"
        },
        "split": load(run1, "split.json"),
        "prepare": load(run1, "prepare.json"),
        "reproducible": {
            "identical": not differences,
            "gated_hashes": len(g1),
            "differences": differences,
            "gated_sha256_run1": g1,
            "tree_sha256_identical": t1 == t2,
            "tree_differences": sorted(
                k for k in set(t1) | set(t2) if t1.get(k) != t2.get(k)
            ),
        },
        "stored_model": {
            k: v for k, v in summary["stored_model"].items() if k != "sha256"
        },
        "arms": {arm: strip_arm(entry) for arm, entry in summary["arms"].items()},
        "casa_calls": solve_logs(run1),
        "flagdata": summary["flagdata"],
        "flux_standards": summary["flux_standards"],
        "images": summary["images"],
        "comparison": load(run1, "compare.json"),
        "original_flag_fraction": summary["original_flag_fraction"],
        "frequency_mhz": summary["frequency_mhz"],
        "post_hoc": {},
    }
    # Labelled post-hoc directories: WSClean -j 1 images, extra CASA arms.
    for extra in argv[5:]:
        entry = {}
        if (Path(extra) / "metrics.json").exists():
            entry["wsclean_j1"] = load(extra, "metrics.json")
        if (Path(extra) / "casa").is_dir():
            entry["casa_calls"] = solve_logs(extra)
        timing = Path(extra) / "timing"
        entry["timings"] = {
            p.stem: p.read_text().split()[-3:] for p in sorted(timing.glob("*.txt"))
        }
        archive["post_hoc"][Path(extra).name] = entry
    Path(out).write_text(json.dumps(archive, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"identical": not differences, "differences": differences[:20]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
