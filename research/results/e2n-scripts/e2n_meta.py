"""E2-N metadata probe: scans, targets, antennas, sizes, sparse flag fractions.

    python e2n_meta.py LINKFILE OUT.json [--flag-every N]

LINKFILE holds the archive RDB URL with its token. The URL is read from the
file and never printed, logged or written: every message and the JSON pass
through `scrub`, which replaces the query string. Reads metadata (telstate,
sensors) and, for the flag fractions, katdal's flag cube at one dump in every
N (no visibilities). Run before research/e2n-native.md's freeze.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np


def read_url(path):
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith("http"):
            return line
    raise SystemExit("no URL in the link file")


def scrub(text, url):
    text = str(text)
    if url:
        text = text.replace(url, "<URL>")
        _, _, query = url.partition("?")
        if query:
            text = text.replace(query, "<TOKEN>")
    return re.sub(r"token=[A-Za-z0-9._\-]+", "token=<TOKEN>", text)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("linkfile")
    p.add_argument("out", type=Path)
    p.add_argument("--flag-every", type=int, default=0)
    a = p.parse_args(argv)
    url = read_url(a.linkfile)
    try:
        import katdal

        t0 = time.perf_counter()
        d = katdal.open(url)
        opened = time.perf_counter() - t0
        info = {
            "katdal": katdal.__version__,
            "open_seconds": opened,
            "name": d.name,
            "experiment_id": d.experiment_id,
            "observer": d.observer,
            "description": d.description,
            "start_utc": str(d.start_time),
            "end_utc": str(d.end_time),
            "dump_period_s": float(d.dump_period),
            "dumps": int(d.shape[0]),
            "channels": int(d.shape[1]),
            "corr_products_total": int(d.shape[2]),
            "freq_first_hz": float(d.channel_freqs[0]),
            "freq_last_hz": float(d.channel_freqs[-1]),
            "channel_width_hz": float(d.channel_width),
            "antennas": [ant.name for ant in d.ants],
            "ref_ant": d.ref_ant,
            "spectral_windows": [str(s) for s in d.spectral_windows],
            "vis_bytes_all_products": int(np.prod(d.shape)) * 8,
            "targets": [
                {"name": t.name, "tags": list(t.tags), "radec": str(t.radec())}
                for t in d.catalogue.targets
            ],
        }
        scans = []
        for scan_index, state, target in d.scans():
            ts = d.timestamps
            scans.append(
                {
                    "scan": int(scan_index),
                    "state": state,
                    "target": target.name,
                    "tags": list(target.tags),
                    "dumps": len(ts),
                    "start": float(ts[0]) if len(ts) else None,
                    "seconds": float(len(ts) * d.dump_period),
                }
            )
        info["scans"] = scans
        d.select()
        d.select(corrprods="cross")
        info["cross_products"] = int(d.shape[2])
        if a.flag_every:
            fractions = []
            for scan_index, state, target in d.scans():
                if state != "track":
                    continue
                n = d.shape[0]
                idx = np.arange(0, n, a.flag_every)
                if len(idx) == 0:
                    continue
                f = np.asarray(
                    d.flags[idx[:: max(1, len(idx) // 4)] if len(idx) > 4 else idx]
                )
                fractions.append(
                    {
                        "scan": int(scan_index),
                        "target": target.name,
                        "dumps_read": int(f.shape[0]),
                        "flagged_fraction": float(f.mean()),
                    }
                )
            info["flag_fractions_sampled"] = fractions
    except Exception as exc:  # noqa: BLE001  (the message may carry the URL)
        raise SystemExit(scrub(f"{type(exc).__name__}: {exc}", url)) from None
    text = scrub(json.dumps(info, indent=1, default=str), url)
    a.out.write_text(text)
    summary = {
        k: v for k, v in info.items() if k not in ("scans", "targets", "antennas")
    }
    print(scrub(json.dumps(summary, indent=1, default=str), url))


if __name__ == "__main__":
    sys.exit(main())
