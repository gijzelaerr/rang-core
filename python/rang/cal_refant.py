"""CARACal's automatic reference antenna (`refant: auto`), task E0.

research/e0-refant-extend.md section 1.1. CARACal 8f7bb363's
`manage_antennas.get_refant` runs Stimela's `flagstats` cab (msutils 1.2.0's
`flag_stats.save_statistics` on the whole MS) and then keeps the antennas
within `maxdist` (1000 m) of the array centre whose distance to every other
ANTENNA row is at least `minbase` (150 m), sorts them by the tuple
`(name, flagged fraction, position, distance)` and returns the first three
names. The sort is by **name**: the flagged fraction only breaks ties
between equal names, so rang reads no FLAG and refuses equal names instead.
The array centre is casacore's observatory position for TELESCOPE_NAME
(row 0 of OBSERVATION) as `me.observatory` gives it, converted by msutils'
own `wgs84_to_ecef`, or antenna 0's POSITION when casacore does not know
the telescope. rang carries casacore-data 20250826's observatory table
(`data/casacore_observatories.json`). The arithmetic follows msutils and
CARACal in float64, operation by operation.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import core_ms

MAXDIST = 1000.0  # CARACal obsconf `maxdist` (its schema's example, the default)
MINBASE = 150.0  # CARACal obsconf `minbase`
OBSERVATORIES = Path(__file__).with_name("data") / "casacore_observatories.json"


class NoReferenceAntenna(ValueError):
    """No antenna meets CARACal's rule (CARACal passes an empty refant on)."""


@dataclass
class Choice:
    names: list
    centre: tuple
    centre_source: str
    telescope: str
    maxdist: float
    minbase: float
    antennas: list = field(default_factory=list)

    def record(self):
        return {
            "names": list(self.names),
            "caracal_string": ",".join(self.names),
            "telescope": self.telescope,
            "centre": [float(v) for v in self.centre],
            "centre_source": self.centre_source,
            "maxdist": self.maxdist,
            "minbase": self.minbase,
            "antennas": self.antennas,
        }


def observatories():
    """casacore's observatory table: {NAME upper-cased: entry}."""
    with open(OBSERVATORIES, encoding="utf-8") as f:
        table = json.load(f)["observatories"]
    return {o["name"].upper(): o for o in table}


def wgs84_to_ecef(lon, lat, alt):
    """msutils 1.2.0's `wgs84_to_ecef`, operation by operation (lon and lat
    in radians, as `me.observatory` returns them)."""
    a = 6378137.0
    f = 1 / 298.257223563
    b = a - a * f
    e = np.sqrt((2 * f) - (f**2))
    n = a / np.sqrt(1 - e**2 * np.sin(lat) ** 2)
    h = alt
    x = (n + h) * np.cos(lat) * np.cos(lon)
    y = (n + h) * np.cos(lat) * np.sin(lon)
    z = (((b**2 / a**2) * n) + h) * np.sin(lat)
    return x, y, z


def _distance(xyz1, xyz2):
    """msutils' and CARACal's `_distance`."""
    x = xyz2[0] - xyz1[0]
    y = xyz2[1] - xyz1[1]
    z = xyz2[2] - xyz1[2]
    return np.sqrt((x * x) + (y * y) + (z * z))


def array_centre(telescope, positions):
    """(centre, source): casacore's position for `telescope` through
    msutils' conversion, else antenna 0's POSITION (msutils' fallback)."""
    entry = observatories().get(str(telescope).upper()) if telescope else None
    if entry is None:
        return tuple(float(v) for v in positions[0]), "antenna 0 (telescope unknown)"
    centre = wgs84_to_ecef(entry["m0"], entry["m1"], entry["m2"])
    return tuple(
        float(v) for v in centre
    ), f"casacore {entry['name']} ({entry['refer']})"


def caracal_refant(ms, maxdist=MAXDIST, minbase=MINBASE):
    """CARACal's `refant: auto` on `ms`: a `Choice` with up to three names.
    Raises NoReferenceAntenna when no antenna qualifies, ValueError when
    qualifying antennas share a name (the flag fractions would decide)."""
    ms = Path(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
        positions = [[float(v) for v in p] for p in np.asarray(t.getcol("POSITION"))]
    telescope = ""
    with core_ms.open_table(ms / "OBSERVATION") as t:
        if t.nrows:
            telescope = str(t.getcol("TELESCOPE_NAME")[0])
    centre, source = array_centre(telescope, positions)
    maxdist, minbase = float(maxdist), float(minbase)
    antennas, core = [], []
    for i, (name, pos) in enumerate(zip(names, positions)):
        dist = float(_distance(centre, pos))
        others = [float(_distance(pos, q)) for j, q in enumerate(positions) if j != i]
        near = dist <= maxdist
        spaced = all(b >= minbase for b in others)
        antennas.append(
            {
                "id": i,
                "name": name,
                "array_centre_dist": dist,
                "shortest_baseline": min(others) if others else None,
                "within_maxdist": near,
                "all_baselines_ge_minbase": spaced,
            }
        )
        if near and spaced:
            core.append(name)
    if len(set(core)) != len(core):
        raise ValueError(
            f"refant auto: antennas that qualify share names {sorted(core)}; CARACal "
            "would order them by flagged fraction, which rang does not port"
        )
    picked = sorted(core)[:3]
    choice = Choice(picked, centre, source, telescope, maxdist, minbase, antennas)
    if not picked:
        raise NoReferenceAntenna(
            f"refant auto: no antenna of {ms.name} is within {maxdist:g} m of the "
            f"array centre ({source}) with every baseline at least {minbase:g} m "
            "(CARACal's maxdist and minbase); give calibrate.refant, or change "
            "calibrate.refant_maxdist or refant_minbase"
        )
    return choice


def is_auto(refant):
    """True when a parsed refant (a list) asks for CARACal's choice."""
    return refant is not None and any(str(r).lower() == "auto" for r in refant)


def _refant_slots(config):
    """(holder, key) of every refant in a validated configuration."""
    from .core_config import CALIBRATE_SECTIONS

    cal = config["calibrate"]
    slots = [(cal, "refant")]
    for section in CALIBRATE_SECTIONS:
        slots += [
            (term, "refant") for term in cal[section]["terms"] if "refant" in term
        ]
    return slots


def uses_auto(config):
    return any(is_auto(holder.get(key)) for holder, key in _refant_slots(config))


def _choose(config, ms):
    cal = config["calibrate"]
    return caracal_refant(ms, cal["refant_maxdist"], cal["refant_minbase"])


def problems(config, ms):
    """Preflight: why `refant: auto` cannot be resolved on `ms` ([] if it can
    or is not used)."""
    if not uses_auto(config):
        return []
    try:
        _choose(config, ms)
    except ValueError as exc:
        return [f"calibrate.refant: {exc}"]
    return []


def resolve_config(config, ms):
    """(config, record): a copy of `config` with every `auto` refant replaced
    by CARACal's names on `ms`, and the choice's record (None, and `config`
    itself, when no refant is auto). CARACal chooses at the start of its
    crosscal and polcal workers; the choice reads no flags, so both give
    these names."""
    if not uses_auto(config):
        return config, None
    import copy

    choice = _choose(config, ms)
    out = copy.deepcopy(config)
    for holder, key in _refant_slots(out):
        if is_auto(holder[key]):
            holder[key] = list(choice.names)
    return out, choice.record()


__all__ = [
    "MAXDIST",
    "MINBASE",
    "Choice",
    "NoReferenceAntenna",
    "array_centre",
    "caracal_refant",
    "is_auto",
    "observatories",
    "problems",
    "resolve_config",
    "uses_auto",
    "wgs84_to_ecef",
]
