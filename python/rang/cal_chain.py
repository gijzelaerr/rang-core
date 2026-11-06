"""The primary calibrator's chain K, G, B in CARACal's order (task C2c,
research/c2c-bandpass.md part 3; C1 section 1.3, solve steps 1-3,
research/c1-calibration-chain.md).

`primary(ms, ...)` solves, on one field:

1. K by `rang.cal_delay.gaincal` (`delay_and_offset` by default), nothing
   pre-applied and no `uvrange` (CARACal passes `uvrange` to G, B and
   polcal only);
2. G (`calmode='ap'`) by `rang.cal_gain.gaincal` with K pre-applied;
3. B by `rang.cal_bandpass.bandpass` with K and G pre-applied;

each with `interp='linear'`, and returns the three tables with their
solutions. The K table holds the delays only; G absorbs K's phase offsets.
This is CASA-style sequential calibration: no joint solve of the chain.
"""

from . import cal_bandpass, cal_delay, cal_gain


def primary(
    ms,
    *,
    field_id=0,
    refant=0,
    k_solint="inf",
    g_solint="inf",
    b_solint="inf",
    k_combine="",
    g_combine="",
    b_combine="scan",
    uvrange="",
    minsnr=3.0,
    minblperant=4,
    fillgaps=0,
    refantmode="flex",
    k_kind="delay_and_offset",
    model_column="MODEL_DATA",
    model=None,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
):
    """K, G, B on one field of `ms`: returns `{"K": (table, sol, info),
    "G": ..., "B": ...}`. `uvrange` reaches G and B only."""
    common = {
        "field_id": field_id,
        "refant": refant,
        "model_column": model_column,
        "model": model,
        "max_iterations": max_iterations,
        "stop_criterion": stop_criterion,
        "stop_fraction": stop_fraction,
    }
    k = cal_delay.gaincal(ms, solint=k_solint, combine=k_combine, kind=k_kind, **common)
    g = cal_gain.gaincal(
        ms, solint=g_solint, combine=g_combine, calmode="ap", refantmode=refantmode,
        minsnr=minsnr, minblperant=minblperant, uvrange=uvrange, gaintable=[k[0]],
        interp="linear", **common,
    )  # fmt: skip
    b = cal_bandpass.bandpass(
        ms, solint=b_solint, combine=b_combine, refantmode=refantmode, minsnr=minsnr,
        minblperant=minblperant, fillgaps=fillgaps, uvrange=uvrange,
        gaintable=[k[0], g[0]], interp="linear", **common,
    )  # fmt: skip
    return {"K": k, "G": g, "B": b}


__all__ = ["primary"]
