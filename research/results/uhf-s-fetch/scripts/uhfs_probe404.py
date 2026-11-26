# SPDX-License-Identifier: MIT
"""uhf-s-fetch: why a block's chunks answer 404 (research/uhf-s-fetch.md 3.1).

    python uhfs_probe404.py LINKFILE MVFDIR CBID

Reads the local RDB's chunk_info (bucket prefixes and the endpoint telstate
names), then asks the archive for the RDB and for the first chunk of
correlator_data and flags: HEAD and GET of the first bytes, with the token as a
Bearer header and as a query parameter. Prints status codes, the S3 error code
and selected headers; every string is scrubbed of the URL and token. No
visibility value is decoded.
"""

import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlparse, urlunparse

import requests


def main(linkfile, mvf, cbid):
    url = next(
        ln.split()[2]
        for ln in Path(linkfile).read_text().splitlines()
        if ln.split()[:1] == [cbid]
    )
    parts = urlparse(url)
    token = dict(parse_qsl(parts.query)).get("token")

    def scrub(t):
        t = str(t).replace(token, "<TOKEN>").replace(url, "<URL>")
        return re.sub(r"token=[A-Za-z0-9._\-]+", "token=<TOKEN>", t)

    endpoint = urlunparse((parts.scheme, parts.netloc, "", "", "", ""))
    print("link path parts:", scrub(list(PurePosixPath(parts.path).parts)))
    import katsdptelstate

    rdb = next((Path(mvf) / cbid).glob("*.rdb"))
    ts = katsdptelstate.TelescopeState()
    ts.load_from_file(str(rdb))
    stream = f"{cbid}_sdp_l0"
    view = ts.view(stream)
    info = view.get("chunk_info", None) or ts.get(f"{stream}_chunk_info", None)
    print(
        "chunk_info keys:",
        None if info is None else {k: v.get("prefix") for k, v in info.items()},
    )
    for key in ("s3_endpoint_url", "stream_type", "src_streams"):
        try:
            print(key, scrub(view[key]))
        except Exception as exc:  # noqa: BLE001
            print(key, "missing", type(exc).__name__)
    bucket = info["correlator_data"]["prefix"] if info else f"{cbid}-sdp-l0"
    names = sorted(p.name for p in (Path(mvf) / bucket / "correlator_data").glob("*"))[
        :1
    ]
    print("first local name:", names)
    targets = {
        "rdb": f"{endpoint}{parts.path}",
        "list": f"{endpoint}/{bucket}?prefix=correlator_data/&max-keys=3",
        "list-flags": f"{endpoint}/{cbid}-sdp-l1-flags?prefix=flags/&max-keys=3",
    }
    import importlib.util

    import katdal

    spec = importlib.util.spec_from_file_location(
        "mvf_download", Path(sys.executable).parent / "mvf_download.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from urllib.parse import urlencode

    q = urlencode({"s3_endpoint_url": endpoint, "token": token})
    d = katdal.open(urlunparse(("file", "", str(rdb.absolute()), "", q, "")))
    d.select(scans=[0])
    got = mod.chunk_names(d.source.data, d.vis.keep)
    for b, files in got.items():
        f = sorted(files)
        print("bucket", b, len(f), "first", f[:2])
        targets[f"chunk {b}"] = f"{endpoint}/{b}/{f[0]}"
    for label, u in targets.items():
        for mode in ("bearer", "query"):
            kw = (
                {"headers": {"Authorization": f"Bearer {token}"}}
                if mode == "bearer"
                else {"params": {"token": token}}
            )
            r = requests.get(
                u,
                stream=True,
                timeout=(30, 60),
                headers={**kw.get("headers", {}), "Range": "bytes=0-99"},
                params=kw.get("params"),
            )
            body = r.raw.read(1500, decode_content=True)
            hdr = {
                k: v
                for k, v in r.headers.items()
                if k.lower()
                in (
                    "content-length",
                    "content-range",
                    "x-amz-request-id",
                    "server",
                    "x-archive-status",
                    "retry-after",
                )
            }
            code = re.findall(rb"<Code>([^<]+)</Code>", body)
            print(
                label,
                mode,
                r.status_code,
                scrub(hdr),
                code,
                scrub(body[:160]) if r.status_code >= 400 else "",
            )
            r.close()


if __name__ == "__main__":
    main(*sys.argv[1:])
