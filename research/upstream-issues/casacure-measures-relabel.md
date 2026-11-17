Target: https://github.com/tmolteno/casacure/issues
Status: ready to post
Reproduced on: casacure 3.8.41 (PyPI, Linux x86_64, CPython 3.12), python-casacore 3.8.1 as reference, 2026-11-12; source read at de45b5d
Duplicates checked: open and closed issues and PRs, searches "measures", "UT1", "TAI", "WGS84", "ITRF"; nearest #15 (AZEL parallactic angle, closed, different)
Title: measures: UTC to TAI/UT1 returns the input relabelled, and ITRF positions report metres as rad

---

The module header scopes `measures` to what DDFacet and killMS use, and `epoch('UTC', …)` is part of that. On casacure 3.8.41, `measure()` on an epoch converts between UTC, TAI, UT1 and UT2 by changing the label only. The value comes back unchanged, so UTC→TAI is 37 s off and UTC→UT1 0.13 s off at MJD 59444.5. python-casacore 3.8.1 converts.

```python
from casacure.measures import measures  # python-casacore: from casacore.measures import measures

dm = measures()
q = lambda v, u: {"value": v, "unit": u}
e = dm.epoch("UTC", q(59444.5, "d"))
for ref in ("TAI", "UT1", "TT", "TDB"):
    try:
        m = dm.measure(e, ref)
        print(ref, m["refer"], round((m["m0"]["value"] - 59444.5) * 86400, 4), "s")
    except Exception as err:
        print(ref, "raises", err)
m = dm.measure(dm.epoch("TAI", q(59444.5, "d")), "UTC")
print("TAI->UTC", round((m["m0"]["value"] - 59444.5) * 86400, 4), "s")
p = dm.position("ITRF", q(5109360.133, "m"), q(2006852.586, "m"), q(-3238948.127, "m"))
print("position", {k: (round(p[k]["value"], 6), p[k]["unit"]) for k in ("m0", "m1", "m2")})
try:
    print("WGS84 height", dm.measure(p, "WGS84")["m2"])
except Exception as err:
    print("WGS84 raises", err)
```

| | casacure 3.8.41 | python-casacore 3.8.1 |
| --- | --- | --- |
| UTC → TAI | `TAI`, +0.0 s | `TAI`, +37.0 s |
| UTC → UT1 | `UT1`, +0.0 s | `UT1`, −0.1301 s |
| UTC → TT | `bad reference type: TT` | +69.184 s (refer `TDT`) |
| UTC → TDB | `bad reference type: TDB` | +69.1829 s |
| TAI → UTC | +0.0 s | −37.0 s |
| `position('ITRF', x, y, z)` | `m0`, `m1` = 5109360.133, 2006852.586 with unit `rad`; `m2` = −3238948.127 `m` | longitude 0.374266 rad, latitude −0.533065 rad, radius 6373680.51 m |
| `measure(pos, 'WGS84')` | `bad reference type: WGS84` | height 1086.60 m |

- `crates/casacure/src/measures.rs:272-274` (de45b5d) maps any of UTC/TAI/UT1/UT2 to any other unchanged. The comment says the offsets are sub-millisecond and that there is no IERS data, but the leap-second offset is 37 s, and the crate does compile the IERS series in (it already uses UT1−UTC for GMST).
- `measures.rs:110` labels every position `rad, rad, m`. ITRF positions keep Cartesian metres in `values` (`:226-233`), so the dict says `rad` for metres. python-casacore returns longitude, latitude and radius for ITRF.
- `measures.rs:449` has `itrf_to_geodetic`, but `measure(pos, 'WGS84')` refuses.
- Minor: `dm.epoch("UTC", "59444.5d")` raises `TypeError: expected a Quantity, dict or number`. python-casacore accepts the string form.

Suggested fix: apply TAI−UTC (leap seconds) and UT1−UTC from the bundled data, or raise `bad reference type` for these pairs as is already done for TT. A silent relabel is the one result that is never right. For positions, report ITRF in casacore's (lon, lat, radius) form or label the units `m, m, m`, and route ITRF→WGS84 through `itrf_to_geodetic` (`:449`, which returns longitude and latitude; the height needs adding).
