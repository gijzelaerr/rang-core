"""C2e (research/c2e-calibrate.md): K, G, B, A and F in `rang-core calibrate`
and their CASA tables in `rang-core apply`. The command must equal
`rang.cal_chain.run` and `rang.applycal.applycal` called directly, bit for
bit; the library's default paths must not move; refusals name their real
owners."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import (
    applycal,
    cal_bandpass,
    cal_chain,
    cal_delay,
    cal_gain,
    core_config,
    core_flag,
    core_ms,
    core_ms_write,
)
from rang.formats import caltable
from test_w2_commands import DATA, STRATEGY, cli, make_ms

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

CONFIG = """\
version: 1
fields: {fcal: [CAL], gcal: [TGT]}
flag: {strategy: strategy.yaml}
calibrate:
  refant: m000
  minblperant: 3
  primary:
    terms:
      - {type: K, name: K}
      - {type: G, name: G, preapply: [K], interp: [linear]}
      - {type: B, name: B, combine: scan, fillgaps: 2, preapply: [K, G]}
      - {type: A, name: A}
  secondary:
    terms:
      - {type: F, name: F, preapply: [K, B], interp: [linear, linear]}
apply:
  targets:
    - {field: [CAL], tables: [K, G, B]}
    - {field: [TGT], tables: [K, F, B], gainfield: [CAL, nearest, CAL]}
run:
  stages: [calibrate, apply]
"""


def calibrator_ms(path, seed=7):
    """`make_ms` with DATA = g_p g_q^* (K, G and a bandpass per antenna and
    hand), times 0.6 on TGT, plus noise of 1e-3."""
    ms = make_ms(path)
    rng = np.random.default_rng(seed)
    with core_ms.open_table(ms) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        field = t.getcol("FIELD_ID")
        shape = t.getcol("DATA").shape
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = t.getcol("CHAN_FREQ")[0]
    nant, nchan = 4, shape[1]
    tau = rng.uniform(-2e-9, 2e-9, (nant, 2))
    tau[0] = 0
    phase = rng.uniform(-np.pi, np.pi, (nant, 2))
    amp = rng.uniform(0.8, 1.2, (nant, 2))
    bp = 1 + 0.05 * rng.standard_normal((nant, nchan, 2))
    nu = freq - freq[nchan // 2]
    g = (amp * np.exp(1j * phase))[:, None, :] * bp
    g = g * np.exp(2j * np.pi * tau[:, None, :] * nu[None, :, None])
    data = np.zeros(shape, np.complex64)
    scale = np.where(field == 1, 0.6, 1.0)[:, None]
    data[..., 0] = scale * g[a1, :, 0] * np.conj(g[a2, :, 0])
    data[..., 3] = scale * g[a1, :, 1] * np.conj(g[a2, :, 1])
    data += 1e-3 * (rng.standard_normal(shape) + 1j * rng.standard_normal(shape))
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("DATA", data)
    return ms


def sha(ms, name):
    import hashlib

    with core_ms.open_table(ms) as t:
        return hashlib.sha256(
            np.ascontiguousarray(t.getcol(name)).tobytes()
        ).hexdigest()


def same_table(a, b):
    ta, tb = caltable.read(a), caltable.read(b)
    assert ta.vis_cal == tb.vis_cal and ta.keywords == tb.keywords
    assert set(ta.main) == set(tb.main)
    for name in ta.main:
        for x, y in zip(ta.main[name], tb.main[name], strict=True):
            if x is None or y is None:
                assert x is None and y is None, name
            else:
                assert np.array_equal(np.asarray(x), np.asarray(y)), name
    assert ta.subtables.keys() == tb.subtables.keys()


def reference_terms():
    common = {
        "solint": "inf",
        "combine": "",
        "refant": ["m000"],
        "refantmode": "flex",
        "minsnr": 3.0,
        "minblperant": 3,
        "uvrange": "",
        "max_iterations": 50,
        "stop_criterion": 1e-7,
        "stop_fraction": 0.99,
        "model": "unit",
    }
    strategies = core_flag.parse_strategy(STRATEGY)
    return [
        {"type": "K", "name": "K", "fields": [0], **common, "preapply": [], "interp": []},
        {"type": "G", "name": "G", "fields": [0], **common, "calmode": "ap",
         "preapply": ["K"], "interp": ["linear"]},
        {"type": "B", "name": "B", "fields": [0], **common, "combine": "scan",
         "fillgaps": 2, "preapply": ["K", "G"], "interp": []},
        {"type": "A", "name": "A", "fields": [0], "tables": ["K", "G", "B"],
         "gainfield": ["0", "0", "0"], "strategies": strategies},
        {"type": "F", "name": "F", "fields": [1], **common, "calmode": "ap",
         "preapply": ["K", "B"], "interp": ["linear", "linear"], "base": "G",
         "smodel": [1.0, 0.0, 0.0, 0.0]},
    ]  # fmt: skip


def test_the_command_equals_the_library_chain_bit_for_bit(tmp_path):
    src = calibrator_ms(tmp_path / "src" / "x.ms")
    (tmp_path / "cmd").mkdir()
    (tmp_path / "lib").mkdir()
    ms = Path(shutil.copytree(src, tmp_path / "cmd" / "x.ms"))
    ref = Path(shutil.copytree(src, tmp_path / "lib" / "x.ms"))
    (tmp_path / "strategy.yaml").write_text(STRATEGY, encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    state = cli("run", config, ms)
    assert state["stages"]["calibrate"]["status"] == "done"
    assert state["stages"]["apply"]["status"] == "done"
    run = ms.with_name("x.ms.rang-run")

    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    out = tmp_path / "lib-tables"
    result = cal_chain.run(
        ref, reference_terms(), out_dir=out, weight_column="WEIGHT", masks=masks
    )
    for name in ("K", "G", "B", "F", "F.append"):
        same_table(run / "calibrate" / name, out / name)
    assert result["steps"][3]["tables"] == ["K", "G", "B"]
    applycal.applycal(
        ref, [out / n for n in ("K", "G", "B")], interp=["linear"], gainfield=[""],
        calwt=[False], field=[0],
    )  # fmt: skip
    applycal.applycal(
        ref, [out / n for n in ("K", "F", "B")], interp=["linear"],
        gainfield=["CAL", "nearest", "CAL"], calwt=[False], field=[1],
    )  # fmt: skip
    for name in ("DATA", "CORRECTED_DATA", "FLAG", "FLAG_ROW", "WEIGHT", "SIGMA"):
        assert sha(ms, name) == sha(ref, name), name
    # The A step flagged something and wrote CORRECTED_DATA on CAL.
    a_step = result["steps"][3]
    assert a_step["flagged"]["rows"] == 120
    # F's flux density: TGT's visibilities are 0.6 of CAL's.
    fd = result["steps"][4]["fluxscale"]["TGT"]["fitted_flux_jy"]
    assert abs(fd - 0.6) < 2e-3


def test_a_forced_calibrate_restores_its_input_flags_first(tmp_path):
    ms = calibrator_ms(tmp_path / "x.ms")
    (tmp_path / "strategy.yaml").write_text(STRATEGY, encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG.replace("[calibrate, apply]", "[calibrate]"), "utf-8")
    before = sha(ms, "FLAG")
    cli("calibrate", config, ms)
    after = sha(ms, "FLAG")
    assert after != before  # the A step and its applycal flagged cells
    state = cli("calibrate", config, ms, "--force")
    assert state["stages"]["calibrate"]["attempts"] == 2
    assert sha(ms, "FLAG") == after  # restored to the input, then the same flags


def test_k_alone_is_reported():
    assert cal_chain.k_alone(["K", "B"])
    assert not cal_chain.k_alone(["K", "G", "B"])
    assert not cal_chain.k_alone(["K", "F", "B"])
    assert cal_chain.a_tables(
        [("K0", "K"), ("G0", "G"), ("B0", "B"), ("K1", "K"), ("G1", "G")]
    ) == ["B0", "K1", "G1"]
    assert cal_chain.a_tables([("K", "K"), ("B", "B"), ("G", "G"), ("F", "F")]) == [
        "K",
        "B",
        "F",
    ]


def test_library_defaults_are_unchanged_by_the_new_arguments(tmp_path):
    """`scan=None` and `weight_column` as before give the same tables as an
    explicit selection of every scan; WEIGHT repeated per channel equals a
    WEIGHT_SPECTRUM column holding the same values."""
    ms = calibrator_ms(tmp_path / "x.ms")
    unit = cal_chain.cal_fluxscale.smodel_array(120, 16)
    kw = {"field_id": 0, "refant": 0, "minblperant": 3, "model": unit}
    k0 = cal_delay.gaincal(ms, weight_column="WEIGHT", **kw)[0]
    k1 = cal_delay.gaincal(ms, weight_column="WEIGHT", scan=[1, 2], **kw)[0]
    g0 = cal_gain.gaincal(ms, weight_column="WEIGHT", gaintable=[k0], **kw)[0]
    g1 = cal_gain.gaincal(ms, weight_column="WEIGHT", gaintable=[k1], scan=[1], **kw)[0]
    b0 = cal_bandpass.bandpass(ms, weight_column=None, gaintable=[k0, g0], **kw)[0]
    b1 = cal_bandpass.bandpass(
        ms, weight_column=None, gaintable=[k1, g1], scan=[1, 2], **kw
    )[0]
    for a, b in ((k0, k1), (g0, g1), (b0, b1)):
        for name in a.main:
            for x, y in zip(a.main[name], b.main[name], strict=True):
                assert (x is None and y is None) or np.array_equal(x, y), name
    # WEIGHT_SPECTRUM holding WEIGHT per channel gives the WEIGHT solve.
    with core_ms.open_table(ms) as t:
        w = t.getcol("WEIGHT")
    spectrum = np.repeat(w[:, None, :], 16, axis=1).astype(np.float32)
    from rang import core_writeback as wb

    with wb.WriteBack(ms) as session:
        session.ensure_column("WEIGHT_SPECTRUM")
        session.write("WEIGHT_SPECTRUM", 0, spectrum)
    ka = cal_delay.gaincal(ms, weight_column="WEIGHT_SPECTRUM", **kw)[0]
    for name in ka.main:
        for x, y in zip(ka.main[name], k0.main[name], strict=True):
            assert (x is None and y is None) or np.array_equal(x, y), name


def test_e2_calibrate_is_no_longer_refused_for_c2_tasks():
    raw = core_config.load(DATA / "e2a.yaml")
    core_config.validate(raw, ["calibrate"])  # no error, no refusal
    raw = core_config.load(DATA / "e2b.yaml")
    with pytest.raises(core_config.ConfigError) as exc:
        core_config.validate(raw, ["calibrate"])
    # Since task C6w (research/c6w-polwire.md) nothing is refused for a task:
    # refant auto (research/c2e-calibrate.md, section 9) and extendflags
    # (research/c6w-polwire.md) have no owner task yet.
    assert exc.value.refusals == []
    assert [p for p, _ in exc.value.errors] == [
        "calibrate.primary.terms[0].refant",
        "calibrate.primary.terms[1].refant",
        "calibrate.primary.terms[2].refant",
        "calibrate.secondary.terms[0].refant",
        "calibrate.secondary.terms[2].refant",
        "calibrate.polcal.terms[0].refant",
        "calibrate.polcal.terms[1].refant",
        "calibrate.polcal.terms[2].refant",
        "calibrate.polcal.terms[3].refant",
        "calibrate.polcal.extendflags",
    ]


def test_chain_errors_are_explained():
    def errors(terms, **cal):
        raw = {"version": 1, "calibrate": {"refant": 0, **cal, **terms}}
        config, problems = core_config.resolve(raw)
        assert problems == []
        return {(r.path, r.task) for r in core_config.refusals(config, ["calibrate"])}

    got = errors({"primary": {"terms": [{"type": "A"}, {"type": "F"}]}})
    assert ("calibrate.primary.terms[0].type", "") in got  # A before any table
    assert ("calibrate.primary.terms[0].strategy", "") in got
    assert ("calibrate.primary.terms[1].type", "") in got  # F not on secondary
    got = errors(
        {"primary": {"terms": [{"type": "G", "solint": 4, "preapply": ["B"]},
                               {"type": "B", "solnorm": True}]}}
    )  # fmt: skip
    assert {
        ("calibrate.primary.terms[0].solint", ""),
        ("calibrate.primary.terms[0].preapply[0]", ""),
        ("calibrate.primary.terms[1].solnorm", ""),
    } <= got
    got = errors({"primary": {"terms": [{"type": "G"}, {"type": "complex"}]}})
    assert ("calibrate", "") in got
    # Since task C6w a Gpol term runs, in the polcal section only.
    got = errors({"primary": {"terms": [{"type": "Gpol"}]}})
    assert ("calibrate.primary.terms[0].type", "") in got
