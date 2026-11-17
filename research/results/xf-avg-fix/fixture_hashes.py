"""Gate 2b of research/xf-avg-fix.md: SHA-256 of the Gpol, KCROSS, Xf and Df
tables on the public fixture (C2e's calibrator MS with C6w's FEED), with
`average_time` on and off, chunked and not.

    python fixture_hashes.py OUT.json
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))

from rang import cal_chain, cal_delay, cal_fluxscale, cal_pol, core_chunks
from test_c2e_calibrate import calibrator_ms
from test_c6w_polwire import _with_feed


def unit(ms, field, stokes=(1.0, 0.0, 0.0, 0.0)):
    nrow, nchan = cal_fluxscale._field_rows(ms, field, 0)
    return cal_fluxscale.smodel_view(nrow, nchan, stokes)


def budget(cells, nrows=480):
    return core_chunks.ChainBudget(
        chunk_bytes=core_chunks.CHAIN_ROW_BYTES * nrows
        + cells * core_chunks.CELL_BYTES["chain"]
    )


def main(out):
    d = Path(tempfile.mkdtemp())
    try:
        ms = _with_feed(calibrator_ms(d / "x.ms", seed=611))
        k = cal_delay.gaincal(ms, field_id=0, refant=0, model=unit(ms, 0),
                              weight_column="WEIGHT")  # fmt: skip
        pol = unit(ms, 1, (1.0, 0.05, 0.08, 0.0))
        c = {"gaintable": [k[0]], "weight_column": "WEIGHT"}
        got = {}
        for avg in (False, True):
            for bname, b, bg in (("one", None, None),
                                 ("chunked", budget(400 if avg else 2000), budget(1600 if avg else 8000))):  # fmt: skip
                tag = f"avg{int(avg)}-{bname}"
                got[f"Gpol-{tag}"] = cal_pol.gpol(
                    ms, field_id=1, model=pol, refant=0, minblperant=2, solint="inf",
                    average_time=avg, budget=bg, **c)[0]  # fmt: skip
                got[f"Kcross-{tag}"] = cal_pol.kcross(
                    ms, field_id=1, model=pol, average_time=avg, budget=bg, **c
                )[0]
                got[f"Xf-{tag}"] = cal_pol.xf(
                    ms, field_id=1, model=pol, combine="scan", average_time=avg,
                    budget=b, **c)[0]  # fmt: skip
                for f, m in ((0, unit(ms, 0)), (1, pol)):
                    got[f"Df{f}-{tag}"] = cal_pol.df(
                        ms, field_id=f, model=m, combine="scan", minblperant=2,
                        minsnr=0.0, average_time=avg, budget=b, **c)[0]  # fmt: skip
        hashes = {n: cal_chain._sha(t) for n, t in got.items()}
    finally:
        shutil.rmtree(d, ignore_errors=True)
    Path(out).write_text(json.dumps(hashes, indent=1) + "\n", encoding="utf-8")
    for n, h in hashes.items():
        print(n, h[:16])


if __name__ == "__main__":
    main(sys.argv[1])
