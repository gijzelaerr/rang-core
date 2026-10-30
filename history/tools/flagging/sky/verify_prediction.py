"""Independent tiny NumPy DFT check of the full pinned catalog prediction."""

import json
import re
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
from casacore.tables import table
from rangtoy.flagging_sky import model_provenance, point_catalog_predict


def read_catalog(path):
    sources = []
    for line in Path(path).read_text().splitlines()[1:]:
        # Preserve the spectral array as one field without borrowing the predictor's parser.
        fields = re.sub(
            r"\[([^\]]*)\]", lambda match: match[0].replace(",", ";"), line
        ).split(",")
        if fields[1] != "POINT" or fields[6] != "false":
            raise ValueError(
                "independent check only supports the pinned POINT/ordinary catalog"
            )
        hour, minute, second = map(float, fields[2].split(":"))
        ra = np.deg2rad(15 * (hour + minute / 60 + second / 3600))
        degree, minute, second = map(float, fields[3].split(".", 2))
        dec = np.deg2rad(np.sign(degree) * (abs(degree) + minute / 60 + second / 3600))
        coefficients = list(map(float, fields[5][1:-1].split(";")))
        sources.append((ra, dec, float(fields[4]), coefficients, float(fields[7])))
    return sources


def main():
    ms, catalog, column, output = sys.argv[1:5]
    model_provenance(catalog)
    sources = read_catalog(catalog)
    if sys.argv[5:] == ["primary"]:
        if not all(abs(source[2]) < abs(sources[0][2]) for source in sources[1:]):
            raise ValueError("first official source is not uniquely brightest")
        sources = sources[:1]
    radec = np.array([source[:2] for source in sources])
    flux = np.array([source[2] for source in sources])
    coefficients = np.array([source[3] for source in sources])
    reference = np.array([source[4] for source in sources])
    with table(ms, readonly=True, ack=False, lockoptions="autonoread") as data:
        cross = np.flatnonzero(data.getcol("ANTENNA1") != data.getcol("ANTENNA2"))
        rows = cross[[0, len(cross) // 2, -1]]
        channels = np.array([1024, 2048, 3071])
        uvw = data.getcol("UVW")[rows]
        actual = data.getcol(column)[rows][:, channels, 0]
    with table(
        ms + "/FIELD", readonly=True, ack=False, lockoptions="autonoread"
    ) as field:
        phase = field.getcol("PHASE_DIR")[0, 0]
        field_name = field.getcol("NAME")[0]
    with table(
        ms + "/SPECTRAL_WINDOW", readonly=True, ack=False, lockoptions="autonoread"
    ) as spw:
        frequencies = spw.getcol("CHAN_FREQ")[0, channels]
    predicted = point_catalog_predict(
        uvw, radec, phase, frequencies, flux, coefficients, reference
    )
    np.testing.assert_allclose(actual, predicted, rtol=2e-6, atol=2e-5)
    cosine = np.sin(phase[1]) * np.sin(radec[0, 1]) + np.cos(phase[1]) * np.cos(
        radec[0, 1]
    ) * np.cos(phase[0] - radec[0, 0])
    result = {
        "passed": True,
        "method": "independently parsed all components + NumPy DFT and ordinary Jy polynomial",
        "components": len(sources),
        "rows": rows.tolist(),
        "channels": channels.tolist(),
        "max_absolute_error_jy": float(np.max(np.abs(actual - predicted))),
        "field": str(field_name),
        "phase_centre_rad": phase.tolist(),
        "primary_component_phase_centre_offset_arcsec": float(
            np.rad2deg(np.arccos(np.clip(cosine, -1, 1))) * 3600
        ),
        "versions": {
            name: version(name)
            for name in (
                "crystalball",
                "codex-africanus",
                "numpy",
                "dask-ms",
                "numba",
                "python-casacore",
                "psutil",
                "regions",
            )
        },
    }
    with Path(output).open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print("Independent full-catalog DFT check passed", flush=True)


if __name__ == "__main__":
    main()
