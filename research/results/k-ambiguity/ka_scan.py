# SPDX-License-Identifier: MIT
"""research/k-ambiguity.md section 9: every antenna of an MS checked for the
pi channel step of section 7, read only. Per row (baseline, dump) and
parallel hand, the circular mean of angle(V[k+1] V[k]^*) over unflagged
channel pairs (at least 8); a row is flipped when |step| > pi/2. Per
(scan, antenna): usable rows and flipped rows; a hit is an antenna with more
than half its usable rows flipped in both hands (an antenna whose own
visibilities carry (-1)^channel flips every baseline except those to another
flipped antenna); and the coherent reading: the summed unit step of
the antenna's rows per hand, its angle and coherence (|sum| / pairs).

    python ka_scan.py MS OUT.json
"""

import json
import sys

import numpy as np
from rang import core_ms

ROWS = 1000
# Channels read (research/k-ambiguity.md section 9): a contiguous mid-band
# slice is enough for a per-channel sign step and reads an eighth of the
# 4,096-channel band; all channels when the band has fewer than 2,048.
CHANS = slice(1792, 2304)


def main(ms, out_path):
    with core_ms.open_table(f"{ms}/ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
    nant = len(names)
    with core_ms.open_table(f"{ms}/SPECTRAL_WINDOW") as t:
        nchan = len(t.getcol("CHAN_FREQ")[0])
    cut = CHANS if nchan >= 2048 else None
    with core_ms.open_table(ms) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        scan, field = t.getcol("SCAN_NUMBER"), t.getcol("FIELD_ID")
        nrow = len(a1)
        scans = sorted({int(s) for s in scan})
        si = {s: i for i, s in enumerate(scans)}
        srow = np.array([si[int(x)] for x in scan])
        used = np.zeros((len(scans), nant, 2), np.int64)
        flip = np.zeros((len(scans), nant, 2), np.int64)
        zsum = np.zeros((len(scans), nant, 2), complex)
        npair = np.zeros((len(scans), nant, 2), np.int64)
        for start in range(0, nrow, ROWS):
            n = min(ROWS, nrow - start)
            sl = slice(start, start + n)
            cross = a1[sl] != a2[sl]
            if not cross.any():
                continue
            d = t.getcol("DATA", start, n, chans=cut)
            f = t.getcol("FLAG", start, n, chans=cut).astype(bool)
            s = srow[sl]
            for h, c in ((0, 0), (1, 3)):
                v = d[..., c]
                ok = ~f[..., c] & (np.abs(v) > 0)
                pair = ok[:, 1:] & ok[:, :-1]
                z = np.where(pair, v[:, 1:] * np.conj(v[:, :-1]), 0)
                z = z / np.maximum(np.abs(z), 1e-30)
                zr = z.sum(1)
                m = np.angle(zr)
                good = cross & (pair.sum(1) >= 8)
                bad = good & (np.abs(m) > np.pi / 2)
                for ants in (a1[sl], a2[sl]):
                    np.add.at(used, (s[good], ants[good], h), 1)
                    np.add.at(flip, (s[bad], ants[bad], h), 1)
                    np.add.at(zsum, (s[good], ants[good], h), zr[good])
                    np.add.at(npair, (s[good], ants[good], h), pair.sum(1)[good])
    fields = {i: int(field[np.argmax(srow == i)]) for i in range(len(scans))}
    frac = flip / np.maximum(used, 1)
    # coherent: the summed unit step of the antenna's rows (both ends), its
    # angle (near pi: flipped) and coherence |sum| / pairs (noise: ~0)
    ang = np.angle(zsum)
    coh = np.abs(zsum) / np.maximum(npair, 1)
    hit = (used.min(-1) > 0) & (frac.min(-1) > 0.5) & (np.abs(ang) > np.pi / 2).all(-1)
    hits = [
        {"scan": scans[i], "field_id": fields[i], "antenna": int(a), "name": names[a],
         "rows": used[i, a].tolist(), "flipped": flip[i, a].tolist(),
         "step_angle": ang[i, a].round(4).tolist(), "coherence": coh[i, a].round(4).tolist()}
        for i, a in zip(*np.nonzero(hit))
    ]  # fmt: skip
    rest = frac.min(-1)[~hit & (used.min(-1) > 0)]
    out = {
        "ms": str(ms),
        "nant": nant,
        "channels_read": [cut.start, cut.stop] if cut else [0, nchan],
        "scans": scans,
        "hits": hits,
        "max_fraction_not_hit": float(rest.max()) if rest.size else 0.0,
        "rows_used_total": int(used.sum()),
        "fields_by_scan": {str(scans[i]): f for i, f in fields.items()},
        "max_coherence_not_hit": float(coh.min(-1)[~hit].max()) if (~hit).any() else 0.0,
    }
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({"ms": str(ms), "hits": len(hits), "antennas": sorted({h["name"] for h in hits}),
                      "max_fraction_not_hit": out["max_fraction_not_hit"]}))  # fmt: skip


if __name__ == "__main__":
    main(*sys.argv[1:3])
