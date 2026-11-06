"""W3b comparisons (research/w3b-chainchunks.md, sections 2 and 3).

    python compare.py config CASE ARM MS OUT.yaml      # the case's configuration for an arm
    python compare.py hashes MS OUT.json               # W3's casacure hashes per column
    python compare.py verdict RUN OUT.json             # every arm against U (W: against D)

The configurations are C2e's I-slice and I-a1 (`examples/check_c2e.py`),
C6w's CONFIG (`examples/check_c6w.py`) without its `data.chunk_rows`, and a
K, G, B chain on the whole-array set, frozen here. Arm M's limit follows the
rule of section 2: 1.25 x the largest GiB a chain term's smallest unit needs,
rounded up to 0.05 GiB.
"""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "w3_compare", HERE.parent / "w3" / "compare.py"
)
w3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w3)

STRATEGY = (
    Path.home()
    / "Github/rang/outputs/caracal-strategy-inputs-8f7bb363"
    / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)
SOURCES = {
    "O": Path.home() / "Github/rang/outputs/o-casa-20261030-01/work.ms",
    "C": Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms"),
    "P": Path("/mnt/d/rang/outputs/c6w-20261106-01/prepared.ms"),
    "W": Path("/mnt/d/rang/outputs/w3/data/w3.ms"),
    "H": Path("/mnt/d/rang/outputs/c6w-20261106-02/prepared.ms"),
}
TINY = 7

SLICE = """\
version: 1
fields: {fcal: [1]}
%(data)sflag: {strategy: %(strategy)s}
calibrate:
  model: {source: column}
  refant: m000
  minblperant: 3
  primary:
    terms:
      - {type: K, name: K0, solint: inf}
      - {type: G, name: G0, solint: inf, preapply: [K0], interp: [linear]}
      - {type: B, name: B0, solint: inf, combine: scan, fillgaps: 70, preapply: [K0, G0],
         interp: [linear, linear]}
      - {type: A, name: A0}
      - {type: K, name: K1, solint: int, preapply: [G0, B0], interp: [linear, linear]}
      - {type: G, name: G1, solint: int, preapply: [K1, B0], interp: [linear, linear]}
      - {type: B, name: B1, solint: inf, combine: scan, fillgaps: 70, preapply: [K1, G1],
         interp: [linear, linear]}
apply:
  targets:
    - {field: [1], tables: [K1, G1, B1]}
"""

A1 = """\
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], target: [SIM-TARGET]}
data: {weights: uniform, scans: %(scans)s%(data_inline)s}
flag: {strategy: %(strategy)s}
calibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: m000
  uvrange: ">150"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}
      - {type: A, name: A}
  secondary:
    terms:
      - {type: G, name: Gsec, solint: 60s, preapply: [K, B], interp: [linear, linear]}
      - {type: A, name: Asec}
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
apply:
  targets:
    - {field: [fcal], tables: [K, G, B]}
    - {field: [gcal, target], tables: [K, F, B],
       gainfield: [J1939-6342, nearest, J1939-6342]}
"""

POL = """\
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], xcal: [3C286-SIM],
         target: [SIM-TARGET]}
%(data)scalibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: m000
  uvrange: ">150"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}
  secondary:
    terms:
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
  polcal:
    model: {source: nrao, name: 3C286}
    feed_angle_rotation: -90.0
    terms:
      - {type: Gpol, name: Gpol, solint: 60s, preapply: [K, G, B]}
      - {type: KCROSS, name: Kcross, solint: inf, preapply: [K, G, B, Gpol]}
      - {type: Xf, name: Xf, solint: inf, combine: scan,
         preapply: [K, G, B, Gpol, Kcross]}
      - {type: Df, name: Df, field: [fcal], solint: inf, combine: scan,
         clip: [-0.6, 0.6], preapply: [K, G, B, Kcross, Xf]}
apply:
  parang: true
  targets:
    - {field: [xcal], tables: [K, G, B, Gpol, Kcross, Xf, Df],
       interp: [linear, linear, linear, linear, nearest, nearest, nearest]}
    - {field: [fcal], tables: [K, G, B, Kcross, Xf, Df],
       interp: [linear, linear, linear, nearest, nearest, nearest]}
    - {field: [gcal, target], tables: [K, F, B, Kcross, Xf, Df],
       gainfield: [J1939-6342, nearest, J1939-6342, "", "", ""],
       interp: [linear, linear, linear, nearest, nearest, nearest]}
"""

WHOLE = """\
version: 1
fields: {fcal: [J1939-6342]}
%(data)sflag: {strategy: %(strategy)s}
calibrate:
  model: {source: setjy}
  refant: m000
  primary:
    terms:
      - {type: K, name: K, solint: %(ksolint)s}
      - {type: G, name: G, solint: int, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, preapply: [K, G],
         interp: [linear, linear]}
"""


def _text(case, data_lines, ksolint="int"):
    data = "".join(f"  {d}\n" for d in data_lines)
    block = f"data:\n{data}" if data_lines else ""
    if case == "O":
        return SLICE % {"data": block, "strategy": STRATEGY}
    if case == "C":
        from rang import core_ms

        with core_ms.open_table(SOURCES["C"]) as t:
            scans = sorted({int(s) for s in t.getcol("SCAN_NUMBER")})[:-1]
        inline = "".join(f", {d}" for d in data_lines)
        return A1 % {"scans": json.dumps(scans), "data_inline": inline,
                     "strategy": STRATEGY}  # fmt: skip
    if case in ("P", "H"):
        return POL % {"data": block}
    if case == "W":
        return WHOLE % {"data": block, "strategy": STRATEGY, "ksolint": ksolint}
    raise SystemExit(f"unknown case {case}")


def m_limit(case, ms):
    """Arm M's limit (section 2): 1.25 x the largest GiB of any chain term's
    smallest unit above the fixed bytes, plus those (amendment 2)."""
    from rang import cal_gain, core_chunks, core_config
    from rang import core_pipeline as pipe

    path = Path(ms).with_name("m-limit-probe.yaml")
    path.write_text(_text(case, []), encoding="utf-8")
    config = core_config.validate_file(path, ["calibrate"])
    path.unlink()
    info = pipe.inspect_ms(ms)
    plan = core_chunks.budget(config, info)
    chain = plan.chain()
    rows = info["rows"]
    nchan, ncorr = info["cell"]
    need = 0.0
    for section in core_config.CALIBRATE_SECTIONS:
        block = config["calibrate"][section]
        for term in block["terms"]:
            fields = pipe.resolve_fields(
                term["field"] or block["field"], config, info, ""
            )
            if term["type"] == "A":
                sel = pipe._selected_rows(rows, fields, config["data"]["scans"])
                for idx in pipe._groups(rows, sel).values():
                    ntime = len(np.unique(rows["TIME"][idx]))
                    need = max(need, plan.need_gb("flag", ntime * nchan * ncorr))
                continue
            per_channel = term["type"] in pipe.PER_CHANNEL_TERMS
            for f in fields:
                idx = pipe._selected_rows(rows, [f], config["data"]["scans"])
                if not len(idx):
                    continue
                tb, _ = cal_gain.solint_bins(
                    rows["TIME"][idx], rows["SCAN_NUMBER"][idx], rows["FIELD_ID"][idx],
                    term["solint"] or "inf", term["combine"] or "",
                )  # fmt: skip
                largest = int(np.bincount(tb).max())
                unit = largest * (1 if per_channel else nchan) * ncorr
                unit = max(unit, nchan * ncorr) if per_channel else unit
                need = max(need, chain.need_gb(len(idx), unit, per_channel))
    # Amendment 2 (research/w3b-chainchunks.md 2): 1.25 x the unit's part
    # above the process's fixed bytes, rounded up to 0.001 GiB.
    fixed = plan.fixed_bytes / core_chunks.GIB
    return math.ceil((fixed + 1.25 * (need - fixed)) / 0.001) * 0.001


def config(case, arm, ms, out):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        nrows = t.nrows
    lines = []
    if arm == "U":
        lines = ["memory_limit_gb: 28", f"chunk_rows: {int(nrows)}"]
    elif arm == "T":
        lines = [f"chunk_rows: {TINY}"]
    elif arm == "M":
        lines = [f"memory_limit_gb: {m_limit(case, ms):.3f}"]
    elif arm == "R":  # criterion 4: K solint inf at the default limit
        Path(out).write_text(_text(case, [], ksolint="inf"), encoding="utf-8")
        return
    Path(out).write_text(_text(case, lines), encoding="utf-8")


def verdict(run, out):
    """W3's verdict (`tools/oracles/w3/compare.py`) over the W3b cases: every
    arm against U, or against D where there is no U (W)."""
    w3.CASES = {c: {} for c in ("O", "C", "P", "W", "H")}
    return w3.verdict(run, out)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "config":
        config(*args)
    elif cmd == "hashes":
        w3.hashes(*args)
    elif cmd == "verdict":
        verdict(*args)
    elif cmd == "mlimit":
        print(f"{m_limit(*args):.3f}")
    else:
        raise SystemExit(__doc__)
