"""E4 (research/e4-tutorial.md, section 3): the flagging strategies tried on
A1 small before the tutorial's was chosen, scored against A1's RFI mask.

    python research/results/e4-tutorial/flag_variants.py OUT_DIR [CARACAL_YAML]

Writes A1 small into OUT_DIR (examples/a1_simtruth.py), runs `rang-core flag`
with each strategy below on a fresh copy, and writes OUT_DIR/flag_variants.json:
the flagged fraction of all cells and, per truth mask (`any`, `above_5sigma`),
the recall (mask cells flagged) and the false-flag rate (clean cells flagged).
A cell counts as flagged when any correlation is. CARACAL_YAML, if given, is
CARACal's mk_rfi_flagging_calibrator_fields_firstpass.yaml (not shipped here;
the repository's copy lives in outputs/caracal-strategy-inputs-8f7bb363/).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HEAD = "strategies:\n  - name: nan_dropouts_flag\n    task: flag_nans_zeros\n"
TAIL = (
    "  - name: flag_autos\n    task: flag_autos\n"
    "  - name: combine_with_input_flags\n    task: combine_with_input_flags\n"
)


def mask(uvrange):
    return (
        "  - name: static_mask\n    task: apply_static_mask\n    kwargs:\n"
        f'      accumulation_mode: "or"\n      uvrange: "{uvrange}"\n'
    )


def st(nsigma, chunks):
    return (
        "  - name: background_flags\n    task: sum_threshold\n    kwargs:\n"
        f"      outlier_nsigma: {nsigma}\n      windows_time: [1, 2, 4, 8]\n"
        f"      windows_freq: [1, 2, 4, 8]\n      freq_chunks: {chunks}\n"
    )


UVC = (
    "  - name: background_fit\n    task: uvcontsub_flagger\n    kwargs:\n"
    "      major_cycles: 5\n      or_original_from_cycle: 0\n"
    "      taylor_degrees: 5\n      sigma: 5.0\n"
)
VARIANTS = {
    "mask-all-baselines-only": HEAD + mask("") + TAIL,
    "mask-all-baselines+st4.5-chunks4": HEAD + mask("") + st(4.5, 4) + TAIL,
    "st4.5-chunks4": HEAD + st(4.5, 4) + TAIL,
    "st4.5-chunks1": HEAD + st(4.5, 1) + TAIL,
    "st5-chunks1": HEAD + st(5, 1) + TAIL,
    "st6-chunks1": HEAD + st(6, 1) + TAIL,
    "uvcontsub5+st5-chunks1": HEAD + UVC + st(5, 1) + TAIL,
    "mask-0~3000+st5-chunks1": HEAD + mask("0~3000") + st(5, 1) + TAIL,
    "mask-0~1000+st5-chunks1 (the tutorial's)": HEAD + mask("0~1000") + st(5, 1) + TAIL,
}


def score(ms, truth_npz):
    from rang import core_ms

    with core_ms.open_table(str(ms)) as t:
        flagged = t.getcol("FLAG").any(-1)
    out = {"flagged": float(flagged.mean())}
    z = np.load(truth_npz)
    nchan = int(z["nchan"])
    for key in ("any", "above_5sigma"):
        m = np.unpackbits(z[key], axis=1, count=nchan).astype(bool)
        out[key] = {
            "mask_fraction": float(m.mean()),
            "recall": float(flagged[m].mean()),
            "false": float(flagged[~m].mean()),
        }
    return out


def main(argv):
    out = Path(argv[0]).resolve()
    variants = dict(VARIANTS)
    if len(argv) > 1:
        variants["caracal-calibrator-firstpass"] = Path(argv[1]).read_text(
            encoding="utf-8"
        )
    gen = [sys.executable, str(ROOT / "examples" / "a1_simtruth.py")]
    subprocess.run([*gen, "generate", "small", str(out / "a1")], check=True)
    pristine = out / "a1" / "a1-small.ms"
    results = {}
    for i, (name, text) in enumerate(variants.items()):
        work = out / f"v{i}"
        shutil.copytree(pristine, work / "x.ms")
        (work / "strategy.yaml").write_text(text, encoding="utf-8")
        (work / "c.yaml").write_text(
            "version: 1\nflag: {strategy: strategy.yaml}\n", encoding="utf-8"
        )
        subprocess.run(
            [sys.executable, "-m", "rang.core_cli", "--no-receipt", "flag"]
            + [str(work / "c.yaml"), str(work / "x.ms")],
            check=True,
            capture_output=True,
        )
        results[name] = score(work / "x.ms", out / "a1" / "a1-small.rfi_mask.npz")
        shutil.rmtree(work)
        print(name, json.dumps(results[name]))
    (out / "flag_variants.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
