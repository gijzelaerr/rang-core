# SPDX-License-Identifier: MIT
"""uhf-s-fetch: is each block's data on the archive's object store now?
(research/uhf-s-fetch.md section 3.1)

    python uhfs_stagecheck.py LINKFILE OUT.jsonl

Per block, with the token as a Bearer header: the RDB's size (ranged GET of
100 bytes), and an S3 listing (max-keys 5) of the visibility bucket
`<cbid>-sdp-l0` under `correlator_data/` and of `<cbid>-sdp-l1-flags` under
`flags/`. A link file with one URL per line (DL2's, already fetched blocks)
serves as the control for what a staged block lists. Appends one scrubbed JSON line per block with the status codes, the
object counts and names listed and the time. No chunk is downloaded.
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, urlunparse

import requests


def main(linkfile, out):
    rows = []
    for ln in Path(linkfile).read_text().splitlines():
        f = ln.split()
        if len(f) == 1 and f[0].startswith(
            "http"
        ):  # one URL per line (DL2's file): a control
            f = [urlparse(f[0]).path.split("/")[1], "control", f[0]]
        if len(f) == 3:
            rows.append(f)
    secrets = [r[2] for r in rows]
    tokens = [dict(parse_qsl(urlparse(u).query)).get("token", "") for u in secrets]

    def scrub(t):
        t = str(t)
        for s in secrets + tokens:
            if s:
                t = t.replace(s, "<SECRET>")
        return re.sub(r"token=[A-Za-z0-9._\-]+", "token=<TOKEN>", t)

    for (cbid, band, url), token in zip(rows, tokens):
        p = urlparse(url)
        ep = urlunparse((p.scheme, p.netloc, "", "", "", ""))
        h = {"Authorization": f"Bearer {token}"}
        rec = {
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cbid": cbid,
            "band": band,
        }
        r = requests.get(
            f"{ep}{p.path}", headers={**h, "Range": "bytes=0-99"}, timeout=60
        )
        rec["rdb_status"] = r.status_code
        rec["rdb_bytes"] = r.headers.get("Content-Range", "").rpartition("/")[2]
        for label, bucket, prefix in (
            ("vis", f"{cbid}-sdp-l0", "correlator_data/"),
            ("flags", f"{cbid}-sdp-l1-flags", "flags/"),
        ):
            r = requests.get(
                f"{ep}/{bucket}",
                headers=h,
                params={"prefix": prefix, "max-keys": 5},
                timeout=60,
            )
            keys = re.findall(r"<Key>([^<]+)</Key>", r.text)
            rec[label] = {
                "status": r.status_code,
                "keys_listed": len(keys),
                "first": keys[:2],
                "truncated": "<IsTruncated>true" in r.text,
                "error": re.findall(r"<Code>([^<]+)</Code>", r.text),
            }
        line = scrub(json.dumps(rec))
        print(line)
        with open(out, "a") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
