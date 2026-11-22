"""DL2 metadata probe, per capture block (research/dl2-data.md sections 2-3).

    python dl2_meta.py LINKFILE OUTDIR [--cbid CBID ...]

LINKFILE holds one archive RDB URL with its token per line (nash:
~/rang-data/sarao-links-dl.txt, mode 600). URLs and tokens are read inside
this script only and never printed, logged or written: every message and
JSON passes through `scrub`. For each block it opens the RDB (telstate and
sensors only: no visibility, flag or weight chunk is read) and writes
OUTDIR/<cbid>.json with the dump time, channelisation, antennas, targets,
the scan list, and the proposal fields that telstate's obs_params carries.
OUTDIR/<cbid>.done is written last; a rerun skips blocks that have one.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import numpy as np


def read_urls(path):
    urls = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith("http"):
            cbid = PurePosixPath(urlparse(line).path).parts[1]
            urls[cbid] = line
    return urls


def scrub(text, urls):
    text = str(text)
    for url in urls:
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


def probe(url):
    import katdal

    t0 = time.perf_counter()
    d = katdal.open(url)
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
        "antennas": [ant.name for ant in d.ants],
        "ref_ant": d.ref_ant,
        "spectral_windows": [str(s) for s in d.spectral_windows],
        "targets": [
            {"name": t.name, "tags": list(t.tags), "radec": str(t.radec())}
            for t in d.catalogue.targets
        ],
    }
    ts = d.source.telstate
    obs = {}
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
    d.select(corrprods="cross")
    info["cross_products"] = int(d.shape[2])
    info["vis_bytes_cross_all"] = int(np.prod(d.shape)) * 8
    return info


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("linkfile")
    p.add_argument("outdir", type=Path)
    p.add_argument("--cbid", nargs="*", default=None)
    a = p.parse_args(argv)
    urls = read_urls(a.linkfile)
    secrets = list(urls.values())
    a.outdir.mkdir(parents=True, exist_ok=True)
    rc = 0
    for cbid in a.cbid or sorted(urls):
        done = a.outdir / f"{cbid}.done"
        if done.exists():
            print(f"{cbid}: done, skipped")
            continue
        try:
            info = probe(urls[cbid])
        except Exception as exc:  # noqa: BLE001  (the message may carry the URL)
            print(scrub(f"{cbid}: {type(exc).__name__}: {exc}", secrets))
            rc = 1
            continue
        text = scrub(json.dumps(info, indent=1, default=str), secrets)
        (a.outdir / f"{cbid}.json").write_text(text)
        done.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ\n", time.gmtime()))
        print(
            f"{cbid}: dump {info['dump_period_s']:.3f} s, {info['channels']} ch, "
            f"{len(info['antennas'])} ant, {len(info['scans'])} scans, "
            f"open {info['open_seconds']} s"
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
