# SPDX-License-Identifier: MIT
"""uhf-s-fetch metadata probe and frozen data rule (research/uhf-s-fetch.md
section 2; the rule is uhf-scope.md section 5, R1 and R4-R5).

    python uhfs_meta.py LINKFILE OUTDIR [--cbid CBID ...]

LINKFILE has one line per block, `cbid band url` (nash:
~/rang-data/uhf-s/sarao-links.txt, mode 600). The URL and its token are read
here only and never printed, logged or written: every message and JSON passes
through `scrub`. Per block it opens the RDB over the network (telstate and
sensors only: no visibility, flag or weight chunk is read) and writes
OUTDIR/<cbid>.json with the dump time, the spectral window, antennas,
correlation products, targets with tags, the scan table, the proposal fields
of obs_params, the volume katdal reports, and the rule check. OUTDIR/<cbid>.done
is written last; a rerun skips blocks that have one.

dl2_meta.py's probe (research/results/dl2-scripts/), with the link format of
this task and the rule check added.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

# Nominal receiver bands (uhf-scope.md section 1; S band: the SARAO S-band
# receiver, 1750-3500 MHz, digitised in sub-bands of 875 MHz).
BANDS = {"UHF": (544e6, 1088e6), "S": (1750e6, 3500e6)}
# Calibrators by every spelling seen in MeerKAT catalogues (name or alias,
# spaces removed, upper case). Amendment 2026-11-26: the first rule run matched
# J names only and so missed "PKS 0408-658" on 1690097605 (section 2.1).
FLUX_CALS = {
    "PKS 1934-638": {"J1939-6342", "1934-638", "PKS1934-638", "PKS1934-63"},
    "PKS 0408-65": {"J0408-6545", "0408-658", "0408-65", "PKS0408-658", "PKS0408-65"},
}
POL_CALS = {
    "3C 286": {"J1331+3030", "3C286", "1328+307"},
    "3C 138": {"J0521+1638", "3C138", "0518+165"},
}


def read_links(path):
    links = {}
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].startswith("http"):
            links[parts[0]] = (parts[1], parts[2])
    return links


def scrub(text, secrets):
    text = str(text)
    for url in secrets:
        text = text.replace(url, "<URL>")
        _, _, query = url.partition("?")
        if query:
            text = text.replace(query, "<TOKEN>")
    text = re.sub(r"token=[A-Za-z0-9._\-]+", "token=<TOKEN>", text)
    return re.sub(r"eyJ[A-Za-z0-9._\-]{20,}", "<TOKEN>", text)


OBS_KEYS = (
    "proposal_id",
    "sb_id_code",
    "description",
    "observer",
    "experiment_id",
    "pi",
    "contact_pi",
    "program_block_id",
    "issue_id",
    "proposal_description",
    "pb_id_code",
)


def which(names, table):
    """The calibrator any of `names` (a target's name and aliases) is, or None."""
    keys = {n.replace(" ", "").upper() for n in names}
    for cal, spellings in table.items():
        if keys & {x.upper() for x in spellings}:
            return cal
    return None


def probe(url):
    import katdal

    t0 = time.perf_counter()
    d = katdal.open(url)
    spw = d.spectral_windows[d.spw]
    info = {
        "katdal": katdal.__version__,
        "open_seconds": round(time.perf_counter() - t0, 1),
        "name": d.name,
        "experiment_id": d.experiment_id,
        "observer": d.observer,
        "description": d.description,
        "start_utc": str(d.start_time),
        "end_utc": str(d.end_time),
        "dump_period_s": float(d.dump_period),
        "dumps": int(d.shape[0]),
        "channels": int(d.shape[1]),
        "freq_first_hz": float(d.channel_freqs[0]),
        "freq_last_hz": float(d.channel_freqs[-1]),
        "channel_width_hz": float(d.channel_width),
        "spw": {
            "centre_freq_hz": float(spw.centre_freq),
            "bandwidth_hz": float(spw.bandwidth),
            "num_chans": int(spw.num_chans),
            "product": str(spw.product),
            "band": str(spw.band),
        },
        "antennas": [ant.name for ant in d.ants],
        "ref_ant": d.ref_ant,
        "targets": [
            {
                "name": t.name,
                "aliases": list(t.aliases),
                "tags": list(t.tags),
                "radec": str(t.radec()),
            }
            for t in d.catalogue.targets
        ],
    }
    ts = d.source.telstate
    try:
        params = ts.get("obs_params") or {}
        obs = {k: params[k] for k in OBS_KEYS if k in params}
        obs["keys"] = sorted(params)
    except Exception as exc:  # noqa: BLE001
        obs = {"error": f"{type(exc).__name__}"}
    info["obs_params"] = obs
    scans = []
    for scan_index, state, target in d.scans():
        t = d.timestamps
        scans.append(
            {
                "scan": int(scan_index),
                "state": state,
                "target": target.name,
                "tags": list(target.tags),
                "dumps": len(t),
                "start": float(t[0]) if len(t) else None,
                "seconds": float(len(t) * d.dump_period),
            }
        )
    info["scans"] = scans
    d.select()
    pols = sorted({(a[-1] + b[-1]).lower() for a, b in d.corr_products})
    info["corr_pols"] = pols
    info["products_all"] = int(d.shape[2])
    d.select(corrprods="cross")
    info["cross_products"] = int(d.shape[2])
    info["vis_bytes_cross_all"] = int(np.prod(d.shape)) * 8
    d.select()
    d.select(scans="track")
    info["track_dumps"] = int(d.shape[0])
    d.select()
    return info


def rule(band, info):
    """uhf-scope.md section 5 R1, R4, R5 and this task's scan-table check."""
    lo, hi = BANDS[band]
    f0, f1 = info["freq_first_hz"], info["freq_last_hz"]
    span = abs(f1 - f0) + info["channel_width_hz"]
    bw = info["spw"]["bandwidth_hz"]
    tracks = [s for s in info["scans"] if s["state"] == "track"]
    aliases = {t["name"]: [t["name"], *t["aliases"]] for t in info["targets"]}
    names = [aliases.get(s["target"], [s["target"]]) for s in tracks]
    fcal = sorted({c for n in names if (c := which(n, FLUX_CALS))})
    pcal = sorted({c for n in names if (c := which(n, POL_CALS))})
    checks = {
        "antennas_ge_40": len(info["antennas"]) >= 40,
        "four_correlations": info["corr_pols"] == ["hh", "hv", "vh", "vv"],
        "band_inside_receiver": lo - 1e3 <= min(f0, f1) and max(f0, f1) <= hi + 1e3,
        "channels_ge_1024": info["channels"] >= 1024,
        "full_band": span >= 0.99 * bw and info["channels"] == info["spw"]["num_chans"],
        "flux_calibrator_scan": bool(fcal),
        "scan_table": len(tracks) > 0 and all(s["dumps"] > 0 for s in tracks),
    }
    return {
        "band": band,
        "receiver_band_hz": [lo, hi],
        "channel_span_hz": span,
        "stream_bandwidth_hz": bw,
        "flux_calibrators": fcal,
        "polarisation_calibrators": pcal,
        "track_scans": len(tracks),
        "checks": checks,
        "passes": all(checks.values()),
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("linkfile")
    p.add_argument("outdir", type=Path)
    p.add_argument("--cbid", nargs="*", default=None)
    p.add_argument(
        "--rule-only",
        action="store_true",
        help="recompute the rule from OUTDIR/<cbid>.json; no network",
    )
    a = p.parse_args(argv)
    links = read_links(a.linkfile)
    if a.rule_only:
        for cbid in a.cbid or list(links):
            path = a.outdir / f"{cbid}.json"
            info = json.loads(path.read_text())
            info["rule"] = rule(links[cbid][0], info)
            path.write_text(json.dumps(info, indent=1, default=str) + "\n")
            r = info["rule"]
            print(
                cbid,
                r["flux_calibrators"],
                r["polarisation_calibrators"],
                "PASS" if r["passes"] else "FAIL",
                r["checks"],
            )
        return 0
    secrets = [u for _, u in links.values()]
    a.outdir.mkdir(parents=True, exist_ok=True)
    rc = 0
    for cbid in a.cbid or list(links):
        done = a.outdir / f"{cbid}.done"
        if done.exists():
            print(f"{cbid}: done, skipped")
            continue
        band, url = links[cbid]
        try:
            info = probe(url)
            info["rule"] = rule(band, info)
        except Exception as exc:  # noqa: BLE001  (the message may carry the URL)
            print(scrub(f"{cbid}: {type(exc).__name__}: {exc}", secrets))
            rc = 1
            continue
        info["cbid"] = cbid
        text = scrub(json.dumps(info, indent=1, default=str), secrets)
        (a.outdir / f"{cbid}.json").write_text(text + "\n")
        done.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ\n", time.gmtime()))
        r = info["rule"]
        print(
            scrub(
                f"{cbid} {band}: dump {info['dump_period_s']:.3f} s, {info['channels']} ch "
                f"{info['freq_first_hz'] / 1e6:.2f}-{info['freq_last_hz'] / 1e6:.2f} MHz, "
                f"{len(info['antennas'])} ant, pols {info['corr_pols']}, "
                f"{r['track_scans']} tracks, fcal {r['flux_calibrators']}, "
                f"pcal {r['polarisation_calibrators']}, rule {'PASS' if r['passes'] else 'FAIL'} "
                f"{r['checks']}, open {info['open_seconds']} s",
                secrets,
            )
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
