"""FS1 oracle: CASA `setjy` flux-density standards on a simulated MS.

Runs inside the O-CASA image (research/fs1-flux-standards.md, "Oracle"):

    docker run --rm --network none --user $(id -u):$(id -g) --tmpfs /tmp \
        -e HOME=/tmp -v $PWD/examples:/code:ro -v $RUN:/run -w /run \
        rang-o-casa:6.7.6.14 /opt/casa/bin/python -I /code/oracle_setjy.py /run

With `--tables DIR` the process works in DIR, where CASA looks for the
`PerleyButler2017Coeffs`/`PerleyButler2013Coeffs` tables (mount them
read-only); the run directory is then given as an absolute path.

Writes into the (empty or new) run directory only: the template MSs, one MS
copy per standard, one CASA log per `setjy` call, `.npy` arrays and
`oracle.json` (SHA-256 of every array, versions, wall times).
"""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from casatasks import casalog, setjy
from casatools import ctsys, measures, simulator, table

FIELDS = {
    "3C48": ("01h37m41.3s", "33d09m35s"),
    "0137+331": ("01h37m41.3s", "33d09m35s"),
    "3C138": ("05h21m09.9s", "16d38m22s"),
    "0521+166": ("05h21m09.9s", "16d38m22s"),
    "3C147": ("05h42m36.1s", "49d51m07s"),
    "0542+498": ("05h42m36.1s", "49d51m07s"),
    "3C286": ("13h31m08.3s", "30d30m33s"),
    "1331+305": ("13h31m08.3s", "30d30m33s"),
    "J1331+3030": ("13h31m08.3s", "30d30m33s"),
    "3C295": ("14h11m20.5s", "52d12m10s"),
    "3C196": ("08h13m36.0s", "48d13m03s"),
    "3C123": ("04h37m04.4s", "29d40m14s"),
    "3C380": ("18h29m31.8s", "48d44m46s"),
    "3C444": ("22h14m25.8s", "-17d01m36s"),
    "1934-638": ("19h39m25.0s", "-63d42m46s"),
    "J1939-6342": ("19h39m25.0s", "-63d42m46s"),
    "PKS1934-638": ("19h39m25.0s", "-63d42m46s"),
    "J0408-6545": ("04h08m20.4s", "-65d45m09s"),
}
FRAME_FIELDS = ("3C286", "1934-638")
STANDARDS = ("Perley-Butler 2010", "Baars", "Stevens-Reynolds 2016")
PENDING = ("Perley-Butler 2017", "Perley-Butler 2013")
MANUAL = {  # CARACal's frozen 1934-638 model (research/o-casa.md)
    "fluxdensity": 14.907688923,
    "reffreq": "1.400000GHz",
    "spix": [-0.19473727, -1.38432520, 0.60533435, 1.43e-06],
}
LBAND = (0.8e9, 1e6, 1001)  # first channel, width, channels: 0.8-1.8 GHz


def sample_ghz():
    dense = [
        0.2, 0.4, 0.405, 0.408, 0.41, 0.5, 0.99, 1.0, 1.01, 2.0, 3.0, 4.0,
        10.9, 10.99, 11.0, 11.01, 11.1, 12.0, 14.9, 15.0, 15.1, 49.0,
    ]  # fmt: skip
    grid = np.geomspace(0.05, 50.0, 64)
    return np.unique(np.round(np.concatenate([grid, dense]), 9))


def dense_1934_ghz():
    """The 1934-638 piece breaks: 10 MHz steps over 9.6-12.1 GHz, and every
    0.1 GHz value with neighbours 1 kHz either side."""
    grid = np.arange(960, 1211) / 100
    tenths = np.arange(96, 122) / 10
    edges = np.concatenate([tenths - 1e-6, tenths, tenths + 1e-6])
    return np.unique(np.round(np.concatenate([grid, edges]), 9))


def build(ms, epoch, lband, freqs_ghz=None, fields=None):
    sm, me = simulator(), measures()
    sm.open(ms)
    pos = me.position("ITRF", "5109360.133m", "2006852.586m", "-3238948.127m")
    sm.setconfig(
        telescopename="MeerKAT",
        x=[5109360.133, 5109400.0],
        y=[2006852.586, 2006860.0],
        z=[-3238948.127, -3238940.0],
        dishdiameter=[13.5, 13.5],
        mount=["alt-az"] * 2,
        antname=["m000", "m001"],
        coordsystem="global",
        referencelocation=pos,
    )
    spws = []
    for k, f in enumerate(sample_ghz() if freqs_ghz is None else freqs_ghz):
        name = f"s{k:03d}"
        sm.setspwindow(
            spwname=name,
            freq=f"{f * 1e9:.3f}Hz",
            deltafreq="1MHz",
            freqresolution="1MHz",
            nchannels=1,
            stokes="XX XY YX YY",
        )
        spws.append(name)
    if lband:
        f0, df, n = LBAND
        sm.setspwindow(
            spwname="L",
            freq=f"{f0:.3f}Hz",
            deltafreq=f"{df:.3f}Hz",
            freqresolution=f"{df:.3f}Hz",
            nchannels=n,
            stokes="XX XY YX YY",
        )
        spws.append("L")
    sm.setfeed(mode="perfect X Y")
    fields = {k: FIELDS[k] for k in (fields or (FIELDS if lband else FRAME_FIELDS))}
    for name, (ra, dec) in fields.items():
        sm.setfield(sourcename=name, sourcedirection=me.direction("J2000", ra, dec))
    sm.setlimits(shadowlimit=0.0, elevationlimit="-90deg")
    sm.setauto(autocorrwt=0.0)
    sm.settimes(
        integrationtime="10s",
        usehourangle=False,
        referencetime=me.epoch("UTC", epoch),
    )
    t = 0
    for name in fields:
        for spw in spws:
            sm.observe(
                sourcename=name, spwname=spw, starttime=f"{t}s", stoptime=f"{t + 10}s"
            )
            t += 10
    sm.close()


def spw_table(ms):
    tb = table()
    tb.open(f"{ms}/SPECTRAL_WINDOW")
    out = {
        "name": list(tb.getcol("NAME")),
        "ref": tb.getcol("REF_FREQUENCY").tolist(),
        "chan": [tb.getcell("CHAN_FREQ", i).tolist() for i in range(tb.nrows())],
        "meas_freq_ref": tb.getcol("MEAS_FREQ_REF").tolist(),
    }
    tb.close()
    return out


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(run, name, array, record):
    path = run / "arrays" / f"{name}.npy"
    np.save(path, array)
    record[name] = sha(path)


def log_lines(path):
    text = Path(path).read_text(errors="replace") if Path(path).exists() else ""
    keep = [
        line.split("\t", 3)[-1].strip()
        for line in text.splitlines()
        if "\tSEVERE\t" in line or "\tWARN\t" in line
    ]
    noise = ("measurespath", "casarundata", "casaconfig", "external-data", "TAI_UTC",
             "times and coordinates", "Until the table")  # fmt: skip
    return [line for line in keep if line and not any(n in line for n in noise)]


def call_setjy(run, ms, field, standard, tag, **extra):
    logfile = run / "logs" / f"{tag}.log"
    casalog.setlogfile(str(logfile))
    start = time.time()
    error = None
    try:
        result = setjy(
            vis=str(ms),
            field=field,
            standard=standard,
            scalebychan=True,
            usescratch=True,
            **extra,
        )
    except Exception as exc:  # noqa: BLE001 -- any CASA failure is recorded; the oracle continues
        result, error = None, repr(exc)
    wall = time.time() - start
    fluxd = {}
    if isinstance(result, dict):
        for fid, per in result.items():
            if fid == "format" or not isinstance(per, dict):
                continue
            for spw, value in per.items():
                if isinstance(value, dict) and "fluxd" in value:
                    fluxd[int(spw)] = [float(v) for v in np.asarray(value["fluxd"])]
    lines = log_lines(logfile)
    return {
        "field": field,
        "standard": standard,
        "wall_s": round(wall, 3),
        "error": error,
        "empty": not fluxd,
        "not_recognized": any("not recognized" in line for line in lines),
        "log": lines[:20],
        "fluxd": fluxd,
    }


def model_stokes(ms, field_id, ddid):
    tb = table()
    tb.open(str(ms))
    sub = tb.query(f"FIELD_ID=={field_id} AND DATA_DESC_ID=={ddid}")
    data = sub.getcol("MODEL_DATA")  # (4, nchan, nrow) complex64
    sub.close()
    tb.close()
    if data.shape[2] == 0:
        return None
    if not all(
        np.array_equal(data[..., 0], data[..., r]) for r in range(data.shape[2])
    ):
        raise RuntimeError("MODEL_DATA differs between rows of one field and SPW")
    return np.ascontiguousarray(data[..., 0].T)  # (nchan, 4) complex64


def field_ids(ms):
    tb = table()
    tb.open(f"{ms}/FIELD")
    names = list(tb.getcol("NAME"))
    tb.close()
    return {n: i for i, n in enumerate(names)}


def ddids(ms):
    tb = table()
    tb.open(f"{ms}/DATA_DESCRIPTION")
    spw = tb.getcol("SPECTRAL_WINDOW_ID").tolist()
    tb.close()
    return {s: d for d, s in enumerate(spw)}


def run_standard(run, template, standard, fields, record, hashes, manual=None):
    tag = "manual" if manual else standard.replace(" ", "_")
    ms = run / f"std-{tag}.ms"
    shutil.copytree(template, ms)
    fid, dd = field_ids(ms), ddids(ms)
    spws = spw_table(ms)
    lband = spws["name"].index("L") if "L" in spws["name"] else None
    calls = []
    for field in fields:
        entry = call_setjy(run, ms, field, "manual" if manual else standard,
                           f"{tag}-{field}", **(manual or {}))  # fmt: skip
        single = [i for i, n in enumerate(spws["name"]) if n != "L"]
        if entry["fluxd"]:
            doubles = np.array(
                [
                    [spws["chan"][i][0]] + entry["fluxd"].get(i, [np.nan] * 4)
                    for i in single
                ]
            )
            save(run, f"{tag}--{field}--doubles", doubles, hashes)
        if lband is not None and not entry["empty"]:
            stokes = model_stokes(ms, fid[field], dd[lband])
            if stokes is not None:
                save(run, f"{tag}--{field}--lband-model", stokes, hashes)
        calls.append(entry)
    record[tag] = {"ms": ms.name, "calls": calls}
    shutil.rmtree(ms)  # the arrays and logs are the evidence; MS copies are large


def main(argv):
    run = Path(argv[1]).resolve()
    tables = None
    if "--tables" in argv:
        tables = Path(argv[argv.index("--tables") + 1]).resolve()
    (run / "logs").mkdir(parents=True, exist_ok=True)
    (run / "arrays").mkdir(exist_ok=True)
    if tables:
        os.chdir(tables)
    import casatools

    record = {
        "casatools": casatools.version_string(),
        "measurespath": str(
            ctsys.getmeasurespath() if hasattr(ctsys, "getmeasurespath") else ""
        ),
        "cwd": os.getcwd(),
        "samples_ghz": sample_ghz().tolist(),
        "lband": {"first_hz": LBAND[0], "width_hz": LBAND[1], "nchan": LBAND[2]},
        "timing": {},
        "standards": {},
        "frame_check": {},
    }
    hashes = {}
    start = time.time()
    template = run / "template.ms"
    if "--dense-1934" in argv:  # pin the 1934-638 piece breaks (second run)
        record["samples_ghz"] = dense_1934_ghz().tolist()
        build(
            str(template), "2020/01/01/00:00:00", False, dense_1934_ghz(), ["1934-638"]
        )
        record["spw"] = spw_table(template)
        for standard in ("Stevens-Reynolds 2016", "Perley-Butler 2010"):
            t0 = time.time()
            run_standard(
                run, template, standard, ["1934-638"], record["standards"], hashes
            )
            record["timing"][standard] = round(time.time() - t0, 3)
        shutil.rmtree(template)
        record["timing"]["total_s"] = round(time.time() - start, 3)
        record["array_sha256"] = hashes
        (run / "oracle.json").write_text(json.dumps(record, indent=1, default=float))
        print(
            json.dumps({"arrays": len(hashes), "total_s": record["timing"]["total_s"]})
        )
        return
    build(str(template), "2020/01/01/00:00:00", lband=True)
    record["timing"]["build_s"] = round(time.time() - start, 3)
    record["spw"] = spw_table(template)
    fields = list(FIELDS)
    for standard in STANDARDS + PENDING:
        t0 = time.time()
        run_standard(run, template, standard, fields, record["standards"], hashes)
        record["timing"][standard] = round(time.time() - t0, 3)
    t0 = time.time()
    run_standard(
        run, template, "manual", ["1934-638"], record["standards"], hashes, MANUAL
    )
    record["timing"]["manual"] = round(time.time() - t0, 3)

    # Frame/epoch check: PB2010 on single-channel SPWs, TOPO 2020 vs LSRK 2020 vs TOPO 2010.
    t0 = time.time()
    for label, epoch, lsrk in (
        ("topo-2020", "2020/01/01/00:00:00", False),
        ("lsrk-2020", "2020/01/01/00:00:00", True),
        ("topo-2010", "2010/01/01/00:00:00", False),
    ):
        ms = run / f"frame-{label}.ms"
        build(str(ms), epoch, lband=False)
        if lsrk:
            tb = table()
            tb.open(f"{ms}/SPECTRAL_WINDOW", nomodify=False)
            tb.putcol("MEAS_FREQ_REF", np.ones(tb.nrows(), dtype=np.int32))
            tb.close()
        spws = spw_table(ms)
        out = {"meas_freq_ref": sorted(set(spws["meas_freq_ref"]))}
        for field in FRAME_FIELDS:
            entry = call_setjy(
                run, ms, field, "Perley-Butler 2010", f"frame-{label}-{field}"
            )
            out[field] = [
                [spws["chan"][i][0], entry["fluxd"].get(i, [np.nan])[0]]
                for i in range(len(spws["name"]))
            ]
        record["frame_check"][label] = out
        shutil.rmtree(ms)
    record["timing"]["frame_check_s"] = round(time.time() - t0, 3)
    shutil.rmtree(template)
    record["timing"]["total_s"] = round(time.time() - start, 3)
    record["array_sha256"] = hashes
    (run / "oracle.json").write_text(json.dumps(record, indent=1, default=float))
    print(json.dumps({"arrays": len(hashes), "total_s": record["timing"]["total_s"]}))


if __name__ == "__main__":
    main(sys.argv)
