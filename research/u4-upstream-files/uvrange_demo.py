# ruff: noqa
"""Post-hoc RV1 demonstration (research/rv1-revalidate.md section 6): which
baselines `apply_static_mask(uvrange="0~550")` masks in Tricolour 0.2.1 and on
0.5.0-dev. Synthetic: three baselines of 300, 700 and 900 m along x, one time,
the shipped L-band static mask on MeerKAT L-band channels. Prints JSON."""

import json

import numpy as np
from tricolour import __version__ as version

lengths = np.array([300.0, 700.0, 900.0])
nbl, ntime, nchan = 3, 1, 4096
chan_freq = np.linspace(856e6, 1712e6, nchan, endpoint=False) + 856e6 / nchan / 2
chan_width = np.full(nchan, 856e6 / nchan)
flags = np.zeros((nbl, 1, ntime, nchan), bool)
try:  # 0.5.0-dev
    from tricolour.core.kernels.flagging import apply_static_mask
    from tricolour.core.kernels.mask import load_masks

    masks = list(load_masks(None).values())
    uvw = np.zeros((nbl, ntime, 3))
    uvw[:, :, 0] = lengths[:, None]
    out = apply_static_mask(flags, uvw, masks, chan_freq, chan_width, "or", "0~550")
    branch = "0.5.0-dev"
except ImportError:  # 0.2.1
    from tricolour.flagging import apply_static_mask
    from tricolour.mask import collect_masks, load_mask

    masks = [load_mask(f, dilate=None) for f in collect_masks()]
    pos = np.zeros((4, 3))
    pos[1:, 0] = lengths
    ubl = np.array([[0, 0, 1], [1, 0, 2], [2, 0, 3]])
    out = apply_static_mask(
        flags, ubl, pos, masks, chan_freq, chan_width, "or", "0~550"
    )
    branch = "0.2.1"
print(
    json.dumps(
        {
            "tricolour": version,
            "branch": branch,
            "baseline_m": lengths.tolist(),
            "masked_channels": [int(out[b].any(axis=(0, 1)).sum()) for b in range(nbl)],
        }
    )
)
