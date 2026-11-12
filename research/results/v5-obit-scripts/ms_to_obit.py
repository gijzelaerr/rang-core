"""Write one field of a Measurement Set as an Obit UV FITS table file (task V5).

Obit reads only its own "uvtab" form (an "AIPS UV" binary table plus AIPS SU, FQ and
AN tables), not random-groups UVFITS. This follows Obit's own MeerKAT writer
(ObitSystem/Obit/python/MeerKATH5toAIPS.py: MakeTemplate, UpdateDescriptor,
WriteANTable, WriteFQTable, WriteSUTable, ConvertKATData), with the MS read by
python-casacore instead of katdal:

- rows of FIELD_ID = field and DATA_DESC_ID 0, autocorrelations dropped (WSClean and
  GeMClean drop them too), XX and YY only (Stokes I is all that is imaged);
- u, v, w in wavelengths at the reference frequency (channel 0), the MS's own UVW and
  visibilities unchanged (the sign is checked by imaging, not assumed);
- weight WEIGHT_SPECTRUM if present, else WEIGHT per correlation; FLAG (or FLAG_ROW)
  makes the weight negative, AIPS's flag convention, so nothing is lost or invented;
- TIME (MJD seconds) as days since 0h UTC of the first integration's date.

Run inside rang-obit (Obit's Python module and python-casacore):

    python3 ms_to_obit.py MS FIELD OUT.uvtab TEMPLATE.uvtab.gz [--column DATA]

and it prints a JSON summary (rows written, unflagged visibilities, weight sums) for
the conversion check in research/v5-obit.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
from astropy.io import fits as pyfits
from casacore.tables import table

import History
import OErr
import OSystem
import Table
import UV
import UVDesc

C = 2.997924562e8  # m/s, Obit's value in MeerKATH5toAIPS


def make_template(template: str, out: str, nchan: int, nstok: int) -> None:
    """Resize the template's VISIBILITIES column (Obit's MakeTemplate, FG table dropped)."""
    h = pyfits.open(template)
    cols = h[1].columns
    cols.del_col("VISIBILITIES")
    cols.add_col(pyfits.Column(
        name="VISIBILITIES", format="%dE" % (3 * nstok * nchan),
        dim="(3,%d,%d,1,1,1)" % (nstok, nchan),
        array=np.zeros((1, 1, 1, nchan, nstok, 3), dtype=np.float32)))
    vis = pyfits.BinTableHDU.from_columns(cols)
    for key in h[1].header.keys():
        if key not in vis.header and key != "HISTORY":
            vis.header[key] = h[1].header[key]
    keep = [h[0], vis] + [x for x in h[2:] if x.name in ("AIPS SU", "AIPS FQ", "AIPS AN", "History")]
    pyfits.HDUList(keep).writeto(out, overwrite=True)


def check(err: OErr.OErr, what: str) -> None:
    if err.isErr:
        OErr.printErrMsg(err, what)
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ms")
    ap.add_argument("field", type=int)
    ap.add_argument("out")
    ap.add_argument("template")
    ap.add_argument("--column", default="DATA")
    ap.add_argument("--block", type=int, default=4096, help="rows per MS read")
    ap.add_argument("--limit", type=int, default=0, help="write only the first N rows (tests)")
    a = ap.parse_args()
    t0 = time.time()

    spw = table(a.ms + "/SPECTRAL_WINDOW", ack=False)
    freqs = spw.getcol("CHAN_FREQ")[0]
    widths = spw.getcol("CHAN_WIDTH")[0]
    nchan = len(freqs)
    chinc = float(freqs[1] - freqs[0]) if nchan > 1 else float(widths[0])
    if nchan > 1 and np.max(np.abs(np.diff(freqs) - chinc)) > 1e-6 * abs(chinc):
        sys.exit("channels not evenly spaced")
    reffreq = float(freqs[0])
    lamb = C / reffreq
    pol = table(a.ms + "/POLARIZATION", ack=False).getcol("CORR_TYPE")[0].tolist()
    ixx, iyy = pol.index(9), pol.index(12)  # casacore Stokes enum: XX=9, YY=12
    ant = table(a.ms + "/ANTENNA", ack=False)
    names = ant.getcol("NAME")
    xyz = ant.getcol("POSITION")
    diam = ant.getcol("DISH_DIAMETER")
    fld = table(a.ms + "/FIELD", ack=False)
    ra, dec = fld.getcol("PHASE_DIR")[a.field][0]
    src = fld.getcol("NAME")[a.field]
    ra_deg = float(np.degrees(ra)) % 360.0
    dec_deg = float(np.degrees(dec))

    ms = table(a.ms, ack=False)
    sel = ms.query("FIELD_ID==%d && DATA_DESC_ID==0 && ANTENNA1!=ANTENNA2" % a.field,
                   sortlist="TIME,ANTENNA1,ANTENNA2")
    nrow = sel.nrows() if not a.limit else min(a.limit, sel.nrows())
    have_ws = "WEIGHT_SPECTRUM" in sel.colnames() and sel.iscelldefined("WEIGHT_SPECTRUM", 0)
    tfirst = float(sel.getcell("TIME", 0))
    day0 = np.floor(tfirst / 86400.0) * 86400.0  # 0h UTC of the first date
    obsdate = time.strftime("%Y-%m-%d", time.gmtime(day0 - 3506716800.0))  # MJD s -> Unix s

    nstok = 2
    make_template(a.template, a.out, nchan, nstok)

    err = OErr.OErr()
    outdir, fname = os.path.split(os.path.abspath(a.out))
    OSystem.OSystem("ms2obit", 1, 100, 0, [" "], 1, [outdir + "/"], True, False, err)
    check(err, "Obit init")
    uv = UV.newPFUV("out", fname, 1, True, err)
    check(err, "open template")

    d = uv.Desc.Dict
    d["obsdat"] = obsdate
    d["observer"] = "rang-v5"
    d["JDObs"] = UVDesc.PDate2JD(obsdate)
    d["naxis"] = 6
    d["inaxes"] = [3, nstok, nchan, 1, 1, 1, 0]
    d["cdelt"] = [1.0, -1.0, chinc, 1.0, 1.0, 1.0, 0.0]
    d["crval"] = [1.0, -5.0, reffreq, 1.0, ra_deg, dec_deg, 0.0]
    d["crota"] = [0.0] * 7
    uv.Desc.Dict = d
    uv.UpdateDesc(err)
    check(err, "descriptor")

    an = uv.NewTable(Table.READWRITE, "AIPS AN", 1, err)
    an.Open(Table.READWRITE, err)
    an.keys["RefDate"] = obsdate
    an.keys["Freq"] = reffreq
    jd = UVDesc.PDate2JD(obsdate)
    an.keys["GSTIA0"] = UVDesc.GST0(jd) * 15.0
    an.keys["DEGPDY"] = UVDesc.ERate(jd) * 360.0
    Table.PDirty(an)
    row = an.ReadRow(1, err)
    for i, name in enumerate(names):
        row["NOSTA"] = [i + 1]
        row["ANNAME"] = [(name + "        ")[:8]]
        row["STABXYZ"] = [float(v) for v in xyz[i]]
        row["DIAMETER"] = [float(diam[i])]
        row["POLAA"] = [90.0]
        an.WriteRow(i + 1, row, err)
    an.Close(err)
    check(err, "AN table")

    if uv.GetHighVer("AIPS FQ") > 0:
        uv.ZapTable("AIPS FQ", 1, err)
    fq = uv.NewTable(Table.READWRITE, "AIPS FQ", 1, err, numIF=1)
    fq.Open(Table.READWRITE, err)
    fq.keys["NO_IF"] = 1
    Table.PDirty(fq)
    fq.WriteRow(1, {"FRQSEL": [1], "IF FREQ": [0.0], "CH WIDTH": [float(widths[0])],
                    "TOTAL BANDWIDTH": [float(abs(widths).sum())], "RXCODE": ["L"],
                    "SIDEBAND": [1 if chinc > 0 else -1], "NumFields": 7,
                    "Table name": "AIPS FQ", "_status": [0]}, err)
    fq.Close(err)
    check(err, "FQ table")

    su = uv.NewTable(Table.READWRITE, "AIPS SU", 1, err)
    su.Open(Table.READWRITE, err)
    su.keys["RefDate"] = obsdate
    su.keys["Freq"] = reffreq
    Table.PDirty(su)
    row = su.ReadRow(1, err)
    row["ID. NO."] = [1]
    row["SOURCE"] = [(src + " " * 16)[:16]]
    for k in ("RAEPO", "RAOBS", "RAAPP"):
        row[k] = [ra_deg]
    for k in ("DECEPO", "DECOBS", "DECAPP"):
        row[k] = [dec_deg]
    row["EPOCH"] = [2000.0]
    row["BANDWIDTH"] = [float(abs(widths).sum())]
    su.WriteRow(1, row, err)
    su.Close(err)
    check(err, "SU table")

    uv.List.set("nVisPIO", 1)
    uv.Open(UV.READWRITE, err)
    check(err, "open for write")
    dd = uv.Desc.Dict
    nrparm = dd["nrparm"]
    lrec = nrparm + nstok * nchan * 3
    iu, iv, iw, it, ib, isu = (dd[k] for k in ("ilocu", "ilocv", "ilocw", "iloct", "ilocb", "ilocsu"))
    buf = np.frombuffer(uv.VisBuf, dtype=np.float32, count=len(uv.VisBuf) // 4)
    # Every write names its row. Python UV.Write stores firstVis-1 in the descriptor, but
    # ObitIOUVFITSWrite takes desc->firstVis as the 1-relative FITS row (and Open leaves
    # numVisBuff 0, so a write without numVis writes nothing): row r needs firstVis=r+1,
    # numVis=1. Measured on 1000 rows: firstVis once then sequential kept 1 row (the
    # template's); Obit's ConvertKATData pattern gave nvis 998; firstVis=r gave 999.
    if buf.size < lrec:
        sys.exit("visibility buffer smaller than one record")

    stats = {"rows": 0, "vis_unflagged": 0, "weight_sum_xx": 0.0, "weight_sum_yy": 0.0,
             "weight_spectrum": bool(have_ws), "nchan": nchan, "reffreq_hz": reffreq,
             "chinc_hz": chinc, "source": src, "ra_deg": ra_deg, "dec_deg": dec_deg,
             "obsdate": obsdate, "corr_order": pol}
    visno = 1
    for start in range(0, nrow, a.block):
        n = min(a.block, nrow - start)
        data = sel.getcol(a.column, start, n)            # (n, nchan, ncorr)
        flag = sel.getcol("FLAG", start, n)
        frow = sel.getcol("FLAG_ROW", start, n)
        if have_ws:
            wt = sel.getcol("WEIGHT_SPECTRUM", start, n)
        else:
            wt = np.repeat(sel.getcol("WEIGHT", start, n)[:, None, :], nchan, axis=1)
        uvw = sel.getcol("UVW", start, n)
        tim = sel.getcol("TIME", start, n)
        a1 = sel.getcol("ANTENNA1", start, n)
        a2 = sel.getcol("ANTENNA2", start, n)
        flag = flag | frow[:, None, None]
        for k in range(n):
            rec = buf[:lrec]
            for s, ic in enumerate((ixx, iyy)):
                v = data[k, :, ic]
                w = wt[k, :, ic].astype(np.float32)
                f = flag[k, :, ic]
                w = np.where(f | (w <= 0), -np.abs(w), w)
                rec[nrparm + 3 * s::3 * nstok][:nchan] = v.real
                rec[nrparm + 3 * s + 1::3 * nstok][:nchan] = v.imag
                rec[nrparm + 3 * s + 2::3 * nstok][:nchan] = w
                good = w > 0
                stats["vis_unflagged"] += int(good.sum())
                stats["weight_sum_" + ("xx" if s == 0 else "yy")] += float(w[good].sum(dtype=np.float64))
            rec[iu] = uvw[k, 0] / lamb
            rec[iv] = uvw[k, 1] / lamb
            rec[iw] = uvw[k, 2] / lamb
            rec[it] = (tim[k] - day0) / 86400.0
            rec[ib] = (a1[k] + 1) * 256.0 + (a2[k] + 1)
            rec[isu] = 1.0
            uv.Write(err, firstVis=visno + 1, numVis=1)  # FITS row visno (see above)
            visno += 1
        check(err, "write")
        stats["rows"] += n
    uv.Close(err)
    check(err, "close")
    UV.PUtilIndex(uv, err)
    check(err, "index")
    uv.Open(UV.READONLY, err)
    stats["nvis_written"] = uv.Desc.Dict["nvis"]
    uv.Close(err)
    hist = History.History("history", uv.List, err)
    hist.Open(History.READWRITE, err)
    hist.TimeStamp("ms_to_obit.py (rang V5)", err)
    hist.WriteRec(-1, "ms = " + os.path.basename(a.ms.rstrip("/")) + " field %d column %s" % (a.field, a.column), err)
    hist.Close(err)
    check(err, "history")
    stats["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
