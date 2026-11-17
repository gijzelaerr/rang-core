# ruff: noqa
from casacure.measures import (
    measures,
)  # python-casacore: from casacore.measures import measures

dm = measures()
q = lambda v, u: {"value": v, "unit": u}  # noqa: E731
e = dm.epoch("UTC", q(59444.5, "d"))
for ref in ("TAI", "UT1", "TT"):
    try:
        m = dm.measure(e, ref)
        print(ref, m["refer"], round((m["m0"]["value"] - 59444.5) * 86400, 4), "s")
    except Exception as err:
        print(ref, "raises", err)
p = dm.position("ITRF", q(5109360.133, "m"), q(2006852.586, "m"), q(-3238948.127, "m"))
print(
    "position", {k: (round(p[k]["value"], 6), p[k]["unit"]) for k in ("m0", "m1", "m2")}
)
try:
    print("WGS84 height", dm.measure(p, "WGS84")["m2"])
except Exception as err:
    print("WGS84 raises", err)
try:
    dm.epoch("UTC", "59444.5d")
    print("string quantity ok")
except Exception as err:
    print("string quantity raises", type(err).__name__, err)
