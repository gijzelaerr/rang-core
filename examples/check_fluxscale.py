"""Host side of task C2d (research/c2d-fluxscale.md): the F term and
`fluxscale` against CASA 6.7.6.14 (classes P and B), A1's simulated truth
(class T) and CASA reading rang's F table (class C). Worktree venv; every
container step is one network-less run (`check_formats.docker`), timed.

    python examples/check_fluxscale.py frozen <run>     # sections 3 and 4
    python examples/check_fluxscale.py heldout <run> --a1h <dir>   # section 5
    python examples/check_fluxscale.py compare <run> [--heldout]   # again, current code

`<run>` is a fresh `/mnt/d/rang/outputs/c2d-<date>-NN`. Inputs are read in
place, read-only: O-CASA's slice and `c.K0` (under `~/Github/rang/outputs`,
or `--outputs <dir>`), A1's small and full twin versions (`--a1 <dir>`) and,
for `heldout`, the held-out version (`--a1h <dir>`). Phases: `prepare`
(copies, models, flags, the four-window copies), `casa` (CASA's chains and
the P cases), `rang` (rang's chains and the P cases on CASA's input
tables), `compare` (`compare.json`), `readback` (class C, frozen only).
Exit 0 only when every gated item passes.
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_formats as cf
from check_gain import a1_model, rfi_flags
from rang import _core, applycal, cal_fluxscale, cal_gain, core_ms
from rang.formats import caltable

CASA = "/opt/casa/bin/python"
EPS32 = 2.0**-23
P_TOL = {"fd": 1e-9, "fit": 1e-6, "abs": 1e-12, "cparam_eps": 2.0}
B_TOL = {
    "fd": 1e-3,
    "scale": 1e-3,
    "fit": 1e-3,
    "alpha": 5e-3,
    "median": 7e-4,
    "p95": 3e-3,
}
T_TOL = {"twin": {"fd": 2e-4, "fit": 2e-4, "alpha": 1e-3},
         "noisy": {"fd": 1e-3, "fit": 1e-3, "alpha": 5e-3}}  # fmt: skip
SOLVE = {
    "solint": "inf",
    "combine": "",
    "refant": "m000",
    "refantmode": "flex",
    "minsnr": 3.0,
}
PRIMARY = "J1939-6342"
GCAL = 2  # SIM-GCAL's field id in A1


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def paths(argv):
    outputs = Path(arg(argv, "--outputs", Path.home() / "Github/rang/outputs"))
    a1 = Path(arg(argv, "--a1", "/mnt/d/rang/outputs/fp-a1-20261106-simtruth"))
    out = {
        "slice": outputs / "o-casa-20261030-01/work.ms",
        "k0": outputs / "o-casa-20261030-01/c.K0",
        "a1": a1 / "small/a1-small.ms",
        "twin": a1 / "small/a1-small-twin.ms",
        "truth": a1 / "small/truth.npz",
        "rfi": a1 / "small/a1-small.rfi_mask.npz",
        "a1k": a1 / "casa-small/truth.K",
        "a1b": a1 / "casa-small/truth.B",
        "full": a1 / "full/a1-full-twin.ms",
        "full_truth": a1 / "full/truth.npz",
        "fullk": a1 / "casa-full/truth.K",
        "fullb": a1 / "casa-full/truth.B",
    }
    if "--a1h" in argv:
        h = Path(arg(argv, "--a1h"))
        out.update(
            h1=h / "small/a1-c2d-heldout.ms",
            h1twin=h / "small/a1-c2d-heldout-twin.ms",
            htruth=h / "small/truth.npz",
            hrfi=h / "small/a1-c2d-heldout.rfi_mask.npz",
            hk=h / "casa-small/truth.K",
            hb=h / "casa-small/truth.B",
        )
    return out


def write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=_default) + "\n")


def _default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


def columns(ms, names):
    with core_ms.open_table(ms) as t:
        return {n: t.getcol(n) for n in names}


def field_names(ms):
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        return [str(n) for n in t.getcol("NAME")]


# --- datasets -------------------------------------------------------------------
# name: source key, kind (slice2 | a1 | x4 | full), noisy, truth key, rfi key,
# pre-apply tables (container paths), secondaries, minblperant.


def datasets(heldout):
    if heldout:
        return {
            "h1": {"src": "h1", "kind": "a1", "noisy": True, "truth": "htruth", "rfi": "hrfi",
                       "pre": ["hk", "hb"], "sec": [1, 2], "mbl": 4},
            "h1-twin": {"src": "h1twin", "kind": "a1", "noisy": False, "truth": "htruth", "rfi": None,
                            "pre": ["hk", "hb"], "sec": [1, 2], "mbl": 4},
            "hx4": {"src": "h1", "kind": "x4", "noisy": True, "truth": "htruth", "rfi": "hrfi",
                        "pre": ["hk", "hb"], "sec": [1, 2], "mbl": 4, "base": "h1"},
            "hx4-twin": {"src": "h1twin", "kind": "x4", "noisy": False, "truth": "htruth", "rfi": None,
                             "pre": ["hk", "hb"], "sec": [1, 2], "mbl": 4, "base": "h1-twin"},
        }  # fmt: skip
    return {
        "slice2": {"src": "slice", "kind": "slice2", "noisy": True, "truth": None, "rfi": None,
                       "pre": ["k0"], "sec": [3], "mbl": 3, "prim": 1},
        "a1": {"src": "a1", "kind": "a1", "noisy": True, "truth": "truth", "rfi": "rfi",
                   "pre": ["a1k", "a1b"], "sec": [1, 2], "mbl": 4},
        "a1-twin": {"src": "twin", "kind": "a1", "noisy": False, "truth": "truth", "rfi": None,
                        "pre": ["a1k", "a1b"], "sec": [1, 2], "mbl": 4},
        "a1x4": {"src": "a1", "kind": "x4", "noisy": True, "truth": "truth", "rfi": "rfi",
                     "pre": ["a1k", "a1b"], "sec": [1, 2], "mbl": 4, "base": "a1"},
        "a1x4-twin": {"src": "twin", "kind": "x4", "noisy": False, "truth": "truth", "rfi": None,
                          "pre": ["a1k", "a1b"], "sec": [1, 2], "mbl": 4, "base": "a1-twin"},
        "full64": {"src": "full", "kind": "a1", "noisy": False, "truth": "full_truth", "rfi": None,
                       "pre": ["fullk", "fullb"], "sec": [2], "mbl": 4},
    }  # fmt: skip


def mounts(run, p, keys):
    out = [(run, "/run", "rw"), (HERE, "/ex", "ro")]
    for k in sorted(set(keys)):
        out.append((p[k], f"/src/{k}", "ro"))
    return out


# --- P cases (section 4 and 5): name, dataset, table edits, fluxscale settings --


def p_cases(heldout):
    if heldout:
        return [
            ("HP-1", "h1", [], {}),
            ("HP-4", "hx4", [], {}),
            ("HP-4-fit2", "hx4", [], {"fitorder": 2}),
            ("HP-threshold", "h1",
             [{"scale": {"field": [GCAL], "antenna": [9], "scan": [7, 9], "factor": 0.7}}],
             {"gainthreshold": 0.1}),
        ]  # fmt: skip
    return [
        ("P-slice2", "slice2", [], {}),
        ("P-a1", "a1", [], {}),
        ("P-a1-transfer", "a1", [], {"transfer": "SIM-GCAL"}),
        ("P-a1-reftran", "a1", [], {"transfer": "J1939-6342,SIM-GCAL"}),
        ("P-a1-tworef", "a1", [{"flag": {"field": [0], "antenna": [3]}}],
         {"reference": "J1939-6342,3C286-SIM", "transfer": "SIM-GCAL"}),
        ("P-a1-threshold", "a1",
         [{"scale": {"field": [GCAL], "antenna": [5], "scan": [3, 5], "factor": 1.2}}],
         {"gainthreshold": 0.05}),
        ("P-a1x4", "a1x4", [], {}),
        ("P-a1x4-fit2", "a1x4", [], {"fitorder": 2}),
        ("P-a1x4-2valid", "a1x4", [{"flag": {"field": [GCAL], "spw": [2, 3]}}], {"fitorder": 2}),
        ("P-a1x4-npa1", "a1x4",
         [{"flag_except": {"field": [GCAL], "spw": [3], "antenna": 1, "par": 0}}], {}),
        ("P-a1x4-refspw", "a1x4", [{"flag": {"field": [0], "spw": [1, 2, 3]}}],
         {"refspwmap": [0, 0, 0, 0]}),
        ("P-full64", "full64", [], {}),
    ]  # fmt: skip


# --- prepare ---------------------------------------------------------------------


def prepare(run, p, heldout):
    ds = datasets(heldout)
    work = run / "ms"
    edits = run / "edits"
    work.mkdir(parents=True)
    edits.mkdir()
    steps = []
    summary = {}
    for name, d in ds.items():
        if d["kind"] == "slice2":
            steps.append(
                f"{CASA} -I /ex/oracle_fluxscale.py slice2 /src/{d['src']} /run/ms/{name}.ms 16 0.6"
                f" > /run/edits/{name}.json"
            )
            continue
        if d["kind"] == "x4":
            continue
        src = p[d["src"]]
        truth = dict(np.load(p[d["truth"]]))
        rows, values = a1_model(src, truth, [0])
        np.savez(edits / f"{name}-model.npz", rows=rows, values=values)
        spec = {"model": f"/run/edits/{name}-model.npz"}
        if d["rfi"]:
            c = columns(src, ["FLAG"])
            nchan = c["FLAG"].shape[1]
            rfi = rfi_flags(src, p[d["rfi"]], nchan)
            np.savez(edits / f"{name}-rfi.npz", rows=np.arange(len(rfi)), flag=rfi)
            spec["flag"] = f"/run/edits/{name}-rfi.npz"
            summary[name] = {"rfi_flagged_fraction": float(rfi.mean())}
        write(edits / f"{name}.json", spec)
        steps += [
            f"{CASA} -I /ex/oracle_gain.py qc-copy /src/{d['src']} /run/ms/{name}.ms",
            f"{CASA} -I /ex/oracle_fluxscale.py edit /run/ms/{name}.ms /run/edits/{name}.json",
        ]
    for name, d in ds.items():
        if d["kind"] != "x4":
            continue
        write(edits / f"{name}-tables.json",
              {"gaintable": [f"/src/{k}" for k in d["pre"]], "interp": ["linear"] * len(d["pre"])})  # fmt: skip
        steps.append(
            f"{CASA} -I /ex/oracle_fluxscale.py multispw /run/ms/{d['base']}.ms /run/ms/{name}.ms 4 "
            f"/run/edits/{name}-tables.json /run/edits/{name}-check.json"
        )
    keys = [d["src"] for d in ds.values()] + [k for d in ds.values() for k in d["pre"]]
    cf.docker(cf.CASA_IMAGE, ["sh", "-c", " && ".join(steps)], mounts(run, p, keys),
              "prepare copies")  # fmt: skip
    for name, d in ds.items():
        if d["kind"] == "x4":
            chk = json.loads((edits / f"{name}-check.json").read_text())
            summary[name] = {"multispw_all_equal": chk["all_equal"]}
        if d["kind"] == "slice2":
            summary[name] = json.loads((edits / f"{name}.json").read_text())
    return summary


# --- CASA ------------------------------------------------------------------------


def casa_chain_steps(name, d, fields):
    ms = f"/run/ms/{name}.ms"
    pre = [f"/src/{k}" for k in d["pre"]] if d["kind"] != "x4" else []
    common = {"vis": ms, "gaintype": "G", "calmode": "ap", "solint": SOLVE["solint"], "combine": "",
                  "refant": SOLVE["refant"], "refantmode": "flex", "minsnr": 3.0, "minblperant": d["mbl"],
                  "uvrange": "", "solnorm": False, "parang": False, "gaintable": pre,
                  "interp": ["linear"] * len(pre)}  # fmt: skip
    g = f"/run/casa/{name}.G"
    gapp = f"/run/casa/{name}.Gapp"
    sec = ",".join(str(f) for f in d["sec"])
    return [
        {"label": f"{name} primary", "task": "gaincal", "args": {**common, "caltable": g, "field": str(d.get("prim", 0))}},
        {"label": f"{name} copy", "task": "copytree", "args": {"src": g, "dst": gapp}},
        {"label": f"{name} secondary", "task": "gaincal",
         "args": {**common, "caltable": gapp, "field": sec, "append": True,
                  "smodel": [1.0, 0.0, 0.0, 0.0]}},
        {"label": f"{name} fluxscale", "task": "fluxscale",
         "args": {"vis": ms, "caltable": gapp, "fluxtable": f"/run/casa/{name}.F",
                  "reference": fields[d.get("prim", 0)], "transfer": ""}},
    ]  # fmt: skip


def casa_p_steps(cases, ds, names):
    steps = []
    for case, dname, edits, settings in cases:
        gapp = f"/run/casa/{dname}.Gapp"
        tin = gapp
        if edits:
            tin = f"/run/casa/{case}.Gin"
            steps.append({"label": f"{case} edit", "task": "edit_caltable",
                          "args": {"src": gapp, "dst": tin, "ops": edits}})  # fmt: skip
        args = {"vis": f"/run/ms/{dname}.ms", "caltable": tin, "fluxtable": f"/run/casa/{case}.F",
                "reference": names[dname][ds[dname].get("prim", 0)], "transfer": ""}  # fmt: skip
        args.update(settings)
        steps.append({"label": f"{case} fluxscale", "task": "fluxscale", "args": args})
    return steps


def casa(run, p, heldout):
    ds = datasets(heldout)
    (run / "casa").mkdir()
    names = {n: field_names(run / "ms" / f"{n}.ms") for n in ds}
    steps = []
    for name, d in ds.items():
        steps += casa_chain_steps(name, d, names[name])
    steps += casa_p_steps(p_cases(heldout), ds, names)
    write(run / "casa" / "steps.json", steps)
    keys = [k for d in ds.values() if d["kind"] != "x4" for k in d["pre"]]
    cf.docker(cf.CASA_IMAGE,
              [CASA, "-I", "/ex/oracle_fluxscale.py", "steps", "/run/casa/steps.json",
               "/run/casa/result.json"], mounts(run, p, keys), "casa chains and fluxscale")  # fmt: skip
    return json.loads((run / "casa" / "result.json").read_text())


# --- rang ------------------------------------------------------------------------


def rang_chain(run, p, name, d):
    ms = run / "ms" / f"{name}.ms"
    pre = [caltable.read(p[k]) for k in d["pre"]] if d["kind"] != "x4" else []
    nspw = cal_fluxscale._windows(ms)
    kw = {"solint": SOLVE["solint"], "combine": "", "refant": SOLVE["refant"], "refantmode": "flex",
              "minsnr": 3.0, "minblperant": d["mbl"], "gaintable": pre}  # fmt: skip
    started = time.perf_counter()
    prim = [
        cal_gain.gaincal(
            ms, field_id=d.get("prim", 0), spw=w if nspw > 1 else None, **kw
        )[0]
        for w in range(nspw)
    ]
    primary = cal_fluxscale.append(prim[0], *prim[1:])
    ftab, record, merged = cal_fluxscale.bootstrap(
        ms, primary, d["sec"], reference=[d.get("prim", 0)], **kw
    )
    seconds = time.perf_counter() - started
    caltable.write(merged, run / "rang" / f"{name}.Gapp")
    caltable.write(ftab, run / "rang" / f"{name}.F")
    return ftab, record, merged, seconds


def rang_side(run, p, heldout):
    ds = datasets(heldout)
    (run / "rang").mkdir()
    out = {"chains": {}, "p": {}, "seconds": {}}
    tables = {}
    for name, d in ds.items():
        ftab, record, merged, seconds = rang_chain(run, p, name, d)
        out["chains"][name] = record
        out["seconds"][name] = seconds
        tables[name] = (ftab, merged)
    names = {n: field_names(run / "ms" / f"{n}.ms") for n in ds}
    for case, dname, edits, settings in p_cases(heldout):
        tin = run / "casa" / (f"{case}.Gin" if edits else f"{dname}.Gapp")
        kw = {"reference": names[dname][ds[dname].get("prim", 0)], "transfer": ""}
        kw.update(settings)
        started = time.perf_counter()
        try:
            ftab, record = cal_fluxscale.fluxscale(caltable.read(tin), **kw)
            caltable.write(ftab, run / "rang" / f"{case}.F")
            out["p"][case] = record
        except ValueError as exc:
            out["p"][case] = {"error": repr(exc)}
        out["seconds"][case] = time.perf_counter() - started
    # T with fitorder 2 on the held-out four-window chains (section 5).
    if heldout:
        for name in ("hx4-twin", "hx4"):
            g = caltable.read(run / "rang" / f"{name}.Gapp")
            _, rec = cal_fluxscale.fluxscale(g, reference=[0], fitorder=2)
            out["chains"][f"{name}-fit2"] = rec
    write(run / "rang" / "result.json", out)
    return out


# --- compare ---------------------------------------------------------------------


def rel(a, b):
    a, b = float(a), float(b)
    if abs(b) < P_TOL["abs"] and abs(a) < P_TOL["abs"]:
        return 0.0
    return abs(a - b) / max(abs(b), 1e-300)


def field_keys(rec):
    return sorted(k for k in rec if k.isdigit())


def compare_records(r, c, tol_fd, tol_fit, fit_keys=True):
    """Per transfer field and window: fluxd, fluxdErr, numSol; the fit."""
    out = {"fields": {}, "pass": True}
    if sorted(field_keys(r)) != sorted(field_keys(c)):
        out["pass"] = False
        out["field_sets"] = [field_keys(r), field_keys(c)]
        return out
    for f in field_keys(c):
        fr, fc = r[f], c[f]
        e = {"windows": {}}
        for w in (k for k in fc if k.isdigit()):
            a, b = fr[w], fc[w]
            fd_r, fd_c = (
                float(np.asarray(a["fluxd"])[0]),
                float(np.asarray(b["fluxd"])[0]),
            )
            item = {
                "fluxd": [fd_r, fd_c],
                "fluxd_rel": rel(fd_r, fd_c),
                "fluxdErr_rel": rel(
                    np.asarray(a["fluxdErr"])[0], np.asarray(b["fluxdErr"])[0]
                ),
                "numSol": [
                    int(np.asarray(a["numSol"])[0]),
                    int(np.asarray(b["numSol"])[0]),
                ],
            }
            item["pass"] = bool(
                item["numSol"][0] == item["numSol"][1]
                and ((fd_c < 0) == (fd_r < 0))
                and item["fluxd_rel"] <= tol_fd
            )
            e["windows"][w] = item
        e["fit"] = {
            k: [np.asarray(fr[k], float).tolist(), np.asarray(fc[k], float).tolist()]
            for k in ("fitFluxd", "fitFluxdErr", "fitRefFreq", "spidx", "spidxerr")
        }
        e["fit_rel"] = {}
        fit_ok = True
        for k, (vr, vc) in e["fit"].items():
            vr, vc = np.atleast_1d(vr), np.atleast_1d(vc)
            if vr.shape != vc.shape:
                e["fit_rel"][k] = "shape"
                fit_ok = False
                continue
            m = max((rel(x, y) for x, y in zip(vr, vc)), default=0.0)
            e["fit_rel"][k] = m
            if fit_keys and k in ("fitFluxd", "fitRefFreq") and m > tol_fit:
                fit_ok = False
        e["pass"] = bool(fit_ok and all(i["pass"] for i in e["windows"].values()))
        out["fields"][f] = e
        out["pass"] &= e["pass"]
    return out


def p_compare(r, c, ftab_r, ftab_c):
    """Class P: the records at P_TOL, then the tables."""
    res = compare_records(r, c, P_TOL["fd"], P_TOL["fit"])
    worst_err, worst_fit = 0.0, 0.0
    for f in res.get("fields", {}).values():
        for w in f["windows"].values():
            worst_err = max(worst_err, w["fluxdErr_rel"])
        for v in f["fit_rel"].values():
            if isinstance(v, str):
                worst_fit = np.inf
            else:
                worst_fit = max(worst_fit, v)
    res["worst_fluxdErr_rel"] = worst_err
    res["worst_fit_rel"] = worst_fit
    freq_eq = np.array_equal(np.asarray(r["freq"], float), np.asarray(c["freq"], float))
    res["freq_equal"] = bool(freq_eq)
    covar_ok = True
    for f in field_keys(c):
        a = np.asarray(r[f]["covarMat"], float)
        b = np.asarray(c[f]["covarMat"], float)
        if a.size or b.size:
            a, b = a.reshape(-1), b.reshape(-1)
            if a.shape != b.shape:
                covar_ok = False
            else:
                covar_ok &= all(rel(x, y) <= P_TOL["fit"] for x, y in zip(a, b))
    res["covar_ok"] = bool(covar_ok)
    tab = table_compare(ftab_r, ftab_c)
    res["table"] = tab
    res["pass"] = bool(res["pass"] and worst_err <= P_TOL["fd"] and worst_fit <= P_TOL["fit"]
                       and freq_eq and covar_ok and tab["pass"])  # fmt: skip
    return res


def keyed(table):
    k = list(zip(table.column("TIME").tolist(), table.column("FIELD_ID").tolist(),
                 table.column("SPECTRAL_WINDOW_ID").tolist(), table.column("ANTENNA1").tolist()))  # fmt: skip
    return {key: i for i, key in enumerate(k)}


def table_compare(tr, tc):
    kr, kc = keyed(tr), keyed(tc)
    out = {"rows": [len(kr), len(kc)], "same_keys": set(kr) == set(kc),
           "same_order": list(kr) == list(kc)}  # fmt: skip
    if not out["same_keys"]:
        out["pass"] = False
        return out
    pr, pc = tr.params, tc.params
    idx_r = np.array([kr[k] for k in kc])
    a, b = pr[idx_r], pc
    diff = np.abs(a - b)
    bound = P_TOL["cparam_eps"] * EPS32 * np.abs(b)
    out["cparam_max_eps"] = float(np.max(diff / np.maximum(np.abs(b), 1e-30)) / EPS32)
    out["cparam_bit_identical"] = float(np.mean(a == b))
    ok = bool(np.all(diff <= bound))
    for col in ("FLAG", "ANTENNA2", "SCAN_NUMBER", "INTERVAL", "PARAMERR", "SNR"):
        va = [np.asarray(tr.main[col][i]) for i in idx_r]
        vb = [np.asarray(tc.main[col][i]) for i in range(tc.nrows)]
        eq = all(np.array_equal(x, y) for x, y in zip(va, vb))
        out[f"{col}_equal"] = bool(eq)
        ok &= eq
    out["pass"] = ok
    return out


def products_rel(tr, tc, fields):
    """Parallel-hand products of two tables' rows of `fields`, matched per
    (field, spw, scan) and antenna: relative differences (C2a's class B)."""

    def per_interval(t):
        out = {}
        for i in range(t.nrows):
            f = int(t.main["FIELD_ID"][i])
            if f not in fields:
                continue
            key = (
                f,
                int(t.main["SPECTRAL_WINDOW_ID"][i]),
                int(t.main["SCAN_NUMBER"][i]),
            )
            out.setdefault(key, {})[int(t.main["ANTENNA1"][i])] = (
                np.asarray(t.main["CPARAM"][i])[0],
                np.asarray(t.main["FLAG"][i])[0],
            )
        return out

    ir, ic = per_interval(tr), per_interval(tc)
    rels = []
    missing = sorted(set(ic) ^ set(ir))
    for key in sorted(set(ir) & set(ic)):
        ants = sorted(set(ir[key]) & set(ic[key]))
        for x in range(len(ants)):
            for y in range(x + 1, len(ants)):
                p, q = ants[x], ants[y]
                for h in range(2):
                    gr = ir[key][p], ir[key][q]
                    gc = ic[key][p], ic[key][q]
                    if gr[0][1][h] or gr[1][1][h] or gc[0][1][h] or gc[1][1][h]:
                        continue
                    pr = gr[0][0][h] * np.conj(gr[1][0][h])
                    pc = gc[0][0][h] * np.conj(gc[1][0][h])
                    rels.append(abs(pr - pc) / abs(pc))
    rels = np.array(rels)
    return {
        "products": len(rels),
        "intervals_unmatched": [list(k) for k in missing],
        "median_rel": float(np.median(rels)) if len(rels) else None,
        "p95_rel": float(np.percentile(rels, 95)) if len(rels) else None,
        "max_rel": float(rels.max()) if len(rels) else None,
    }


def b_compare(r, c, ftab_r, ftab_c, merged_r):
    res = compare_records(r, c, B_TOL["fd"], B_TOL["fit"])
    for e in res.get("fields", {}).values():
        for item in e["windows"].values():
            fr, fc = item["fluxd"]
            item["scale_rel"] = (
                rel(np.sqrt(max(fr, 0)), np.sqrt(max(fc, 0))) if fc > 0 else 0.0
            )
            item["pass"] = bool(item["pass"] and item["scale_rel"] <= B_TOL["scale"])
        spr, spc = (np.atleast_1d(v) for v in e["fit"]["spidx"])
        nvalid = sum(1 for w in e["windows"].values() if w["fluxd"][1] > 0)
        if nvalid > 1 and len(spc) > 1:
            e["alpha"] = [float(spr[1]), float(spc[1])]
            e["alpha_abs"] = abs(float(spr[1]) - float(spc[1]))
            e["pass"] = bool(e["pass"] and e["alpha_abs"] <= B_TOL["alpha"])
        e["pass"] = bool(e["pass"] and all(i["pass"] for i in e["windows"].values()))
    tran = [int(f) for f in field_keys(c)]
    prod = products_rel(ftab_r, ftab_c, tran)
    res["products"] = prod
    ok = (
        prod["median_rel"] is not None
        and prod["median_rel"] <= B_TOL["median"]
        and prod["p95_rel"] <= B_TOL["p95"]
        and not prod["intervals_unmatched"]
    )
    # Reference rows of rang's F equal rang's input G.
    ref = [
        k for k in range(ftab_r.nrows) if int(ftab_r.main["FIELD_ID"][k]) not in tran
    ]
    ref_eq = all(np.array_equal(np.asarray(ftab_r.main["CPARAM"][k]),
                                np.asarray(merged_r.main["CPARAM"][k])) for k in ref)  # fmt: skip
    res["reference_rows_unchanged"] = bool(ref_eq)
    res["pass"] = bool(all(e["pass"] for e in res.get("fields", {}).values())
                       and res.get("field_sets") is None and ok and ref_eq)  # fmt: skip
    return res


def expected_flux(ms1, truth, field, nspw, chan_slices):
    """E_k (section 2, class T): the weighted mean of Re(P_p M P_q^T) over the
    field's unflagged parallel-hand cells of each window, on the one-window
    copy `ms1` (its flags are those of the four-window copy: checked)."""
    rows, values = a1_model(ms1, truth, [field], parang=True)
    c = columns(ms1, ["FLAG", "WEIGHT_SPECTRUM"])
    flag = c["FLAG"][rows]
    w = c["WEIGHT_SPECTRUM"][rows].astype(float)
    out = []
    for sl in chan_slices:
        num = den = 0.0
        for h in (0, 3):
            ok = ~flag[:, sl, h]
            num += float(np.sum((w[:, sl, h] * values[:, sl, h].real)[ok]))
            den += float(np.sum(w[:, sl, h][ok]))
        out.append(num / den)
    return np.array(out)


def t_compare(rec, ms1, truth, nspw, noisy, fitorder, expected=None):
    tol = T_TOL["noisy" if noisy else "twin"]
    nchan = len(truth["freq_hz"])
    per = nchan // nspw
    slices = [slice(k * per, (k + 1) * per) for k in range(nspw)]
    e = expected_flux(ms1, truth, GCAL, nspw, slices) if expected is None else expected
    entry = rec[str(GCAL)]
    fd = np.array([float(np.asarray(entry[str(k)]["fluxd"])[0]) for k in range(nspw)])
    err = np.array(
        [float(np.asarray(entry[str(k)]["fluxdErr"])[0]) for k in range(nspw)]
    )
    freq = np.asarray(rec["freq"], float)
    out = {"E": e, "fd": fd, "fderr": err, "fd_rel": np.abs(fd / e - 1),
           "z": (fd - e) / np.where(err > 0, err, np.nan)}  # fmt: skip
    ok = bool(np.all(out["fd_rel"] <= tol["fd"]))
    nominal = truth["calibrator_stokes"][GCAL, :, 0]
    out["nominal_at_centre_rel"] = [
        float(fd[k] / np.interp(freq[k], truth["freq_hz"], nominal) - 1)
        for k in range(nspw)
    ]
    if nspw > 1:
        fe = _core.cal_fluxscale_fit(list(freq), list(e), list(err), int(fitorder))
        out["fit_expected"] = fe
        out["fit"] = {
            "flux": float(entry["fitFluxd"]),
            "spidx": np.asarray(entry["spidx"]).tolist(),
        }
        out["fit_flux_rel"] = abs(float(entry["fitFluxd"]) / fe["flux"] - 1)
        out["alpha_abs"] = abs(float(np.asarray(entry["spidx"])[1]) - fe["coeffs"][1])
        ok &= out["fit_flux_rel"] <= tol["fit"] and out["alpha_abs"] <= tol["alpha"]
    else:
        out["fit_flux_rel"] = abs(float(entry["fitFluxd"]) / e[0] - 1)
        ok &= out["fit_flux_rel"] <= tol["fit"]
    out["pass"] = bool(ok)
    return out


def compare(run, p, heldout):
    ds = datasets(heldout)
    cres = json.loads((run / "casa" / "result.json").read_text())
    by_label = {s["label"]: s for s in cres}
    rres = json.loads((run / "rang" / "result.json").read_text())
    out = {"P": {}, "B": {}, "T": {}, "T_Emed": {}}
    for case, dname, _, _ in p_cases(heldout):
        c = by_label[f"{case} fluxscale"]
        r = rres["p"][case]
        if c["error"] or "error" in r:
            out["P"][case] = {
                "pass": False,
                "casa_error": c["error"],
                "rang_error": r.get("error"),
            }
            continue
        ctab = caltable.read(run / "casa" / f"{case}.F")
        rtab = caltable.read(run / "rang" / f"{case}.F")
        out["P"][case] = p_compare(r, c["return"], rtab, ctab)
    for name, d in ds.items():
        c = by_label[f"{name} fluxscale"]
        r = rres["chains"][name]
        ctab = caltable.read(run / "casa" / f"{name}.F")
        rtab = caltable.read(run / "rang" / f"{name}.F")
        merged = caltable.read(run / "rang" / f"{name}.Gapp")
        case = ("HB-" if heldout else "B-") + name
        if name in ("a1-twin", "a1x4-twin", "h1-twin", "hx4-twin"):
            case = None
        if case:
            out["B"][case.replace("HB-h1", "HB-1").replace("HB-hx4", "HB-4")] = (
                b_compare(r, c["return"], rtab, ctab, merged)
            )
        if d["truth"] and name not in ("full64", "h1-twin"):
            truth = dict(np.load(p[d["truth"]]))
            ms1 = run / "ms" / f"{d.get('base', name)}.ms"
            nspw = 4 if d["kind"] == "x4" else 1
            label = {"a1": "T-a1", "a1-twin": "T-a1-twin", "a1x4": "T-a1x4",
                     "a1x4-twin": "T-a1x4-twin", "h1": "HT-1", "hx4": "HT-4",
                     "hx4-twin": "HT-twin-4"}[name]  # fmt: skip
            out["T"][label] = t_compare(r, ms1, truth, nspw, d["noisy"], 1)
            # Post hoc (section 8): the per-antenna median expectation E_med.
            from probe_fluxscale_truth import per_antenna

            e_med = np.array([x["E_med"] for x in per_antenna(ms1, truth, nspw)])
            out["T_Emed"][label] = t_compare(r, ms1, truth, nspw, d["noisy"], 1, e_med)
            if f"{name}-fit2" in rres["chains"]:
                out["T"][label + "-fit2"] = t_compare(rres["chains"][f"{name}-fit2"], ms1,
                                                      truth, nspw, d["noisy"], 2)  # fmt: skip
                out["T_Emed"][label + "-fit2"] = t_compare(
                    rres["chains"][f"{name}-fit2"],
                    ms1,
                    truth,
                    nspw,
                    d["noisy"],
                    2,
                    e_med,
                )
    out["pass"] = {k: all(v["pass"] for v in out[k].values()) for k in ("P", "B", "T")}
    out["pass_post_hoc"] = {"T_Emed": all(v["pass"] for v in out["T_Emed"].values())}
    return out


# --- class C ---------------------------------------------------------------------


def readback(run, p):
    src = run / "ms" / "a1.ms"
    if (run / "readback").exists():  # a failed earlier attempt (run -02)
        shutil.rmtree(run / "readback")
    (run / "readback").mkdir()
    rang_ms = run / "readback" / "rang.ms"
    shutil.copytree(src, rang_ms)  # with its table.lock, which the writer opens
    ftab = run / "rang" / "a1.F"
    gt = [p["a1k"], p["a1b"], ftab]
    started = time.perf_counter()
    applycal.applycal(rang_ms, [caltable.read(t) for t in gt], interp=["linear"] * 3,
                      gainfield=["", "", "nearest"], field=[2, 3])  # fmt: skip
    rang_s = time.perf_counter() - started
    steps = [
        {"label": "readback copy", "task": "copytree", "args": {"src": "/run/ms/a1.ms",
                                                                 "dst": "/run/readback/casa.ms"}},
        {"label": "readback applycal", "task": "applycal",
         "args": {"vis": "/run/readback/casa.ms", "field": "2,3",
                  "gaintable": ["/src/a1k", "/src/a1b", "/run/rang/a1.F"],
                  "gainfield": ["", "", "nearest"], "interp": ["linear"] * 3,
                  "calwt": [False], "parang": False, "applymode": "calflag", "flagbackup": False}},
    ]  # fmt: skip
    write(run / "readback" / "steps.json", steps)
    cf.docker(cf.CASA_IMAGE, [CASA, "-I", "/ex/oracle_fluxscale.py", "steps",
                              "/run/readback/steps.json", "/run/readback/result.json"],
              mounts(run, p, ["a1k", "a1b"]), "readback applycal")  # fmt: skip
    a = columns(rang_ms, ["CORRECTED_DATA", "FLAG", "FIELD_ID"])
    b = columns(run / "readback" / "casa.ms", ["CORRECTED_DATA", "FLAG"])
    sel = np.isin(a["FIELD_ID"], [2, 3])
    r, c = a["CORRECTED_DATA"][sel], b["CORRECTED_DATA"][sel]
    cellmax = np.max(np.abs(c), axis=-1, keepdims=True)
    bound = np.maximum(1e-6 * np.abs(c), 11 * EPS32 * cellmax)
    diff = np.abs(r - c)
    over = diff > bound
    return {
        "cells": int(diff.size),
        "over": int(over.sum()),
        "worst_eps_of_cell": float(np.max(diff / np.maximum(cellmax, 1e-30)) / EPS32),
        "flag_exact": bool(np.array_equal(a["FLAG"], b["FLAG"])),
        "rang_seconds": rang_s,
        "pass": bool(not over.any() and np.array_equal(a["FLAG"], b["FLAG"])),
    }


# --- entry -----------------------------------------------------------------------


def run_all(run, argv, heldout):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    timings = {}
    cf.TIMINGS.clear()
    summary = {"prepare": prepare(run, p, heldout)}
    timings["prepare"] = time.perf_counter() - t0
    t = time.perf_counter()
    casa(run, p, heldout)
    timings["casa"] = time.perf_counter() - t
    t = time.perf_counter()
    rres = rang_side(run, p, heldout)
    timings["rang"] = time.perf_counter() - t
    timings["rang_parts"] = rres["seconds"]
    t = time.perf_counter()
    summary["compare"] = compare(run, p, heldout)
    timings["compare"] = time.perf_counter() - t
    write(run / "compare.json", summary)
    if not heldout:
        t = time.perf_counter()
        summary["C"] = {"C-a1": readback(run, p)}
        timings["readback"] = time.perf_counter() - t
        summary["compare"]["pass"]["C"] = summary["C"]["C-a1"]["pass"]
    timings["total"] = time.perf_counter() - t0
    summary["timings"] = timings
    summary["containers"] = list(cf.TIMINGS)
    write(run / "compare.json", summary)
    print(json.dumps(summary["compare"]["pass"]))
    return 0 if all(summary["compare"]["pass"].values()) else 1


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd in ("frozen", "heldout") and len(argv) >= 3:
        return run_all(argv[2], argv, cmd == "heldout")
    if cmd == "compare" and len(argv) >= 3:
        heldout = "--heldout" in argv
        res = compare(Path(argv[2]), paths(argv), heldout)
        write(Path(argv[2]) / "compare-again.json", res)
        print(json.dumps(res["pass"]))
        return 0 if all(res["pass"].values()) else 1
    if cmd == "recheck" and len(argv) >= 3:
        # Post hoc: rang's side again with the current code on the run's CASA
        # outputs and copies; the run's own rang outputs move to rang-<tag>.
        run, p = Path(argv[2]), paths(argv)
        heldout = "--heldout" in argv
        tag = arg(argv, "--tag", "before")
        shutil.move(run / "rang", run / f"rang-{tag}")
        t = time.perf_counter()
        rang_side(run, p, heldout)
        res = compare(run, p, heldout)
        res["seconds"] = time.perf_counter() - t
        write(run / f"compare-recheck-{tag}.json", res)
        print(json.dumps(res["pass"]))
        return 0 if all(res["pass"].values()) else 1
    if cmd == "readback" and len(argv) >= 3:
        cf.TIMINGS.clear()
        res = {"C-a1": readback(Path(argv[2]), paths(argv)), "containers": cf.TIMINGS}
        write(Path(argv[2]) / "readback.json", res)
        print(json.dumps(res["C-a1"]))
        return 0 if res["C-a1"]["pass"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
