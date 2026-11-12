# Static masks copied from Tricolour 0.2.1

`4k_lband_meerkat.staticmask` (SHA256 `96969417441917454186ddcf5fe2fbc4e9cc0aa464f8d072c917749164108c33`)
and `4k_uhfband_meerkat.staticmask` (SHA256 `2d862fbe61e7cf4b7799fb9cf7ceaff81860a26d70eb770816dfb2a3e8ddc1bb`)
are byte-for-byte copies of `tricolour/data/` in the Tricolour 0.2.1 wheel
(`tricolour-0.2.1-py3-none-any.whl`, SHA256
`7dd8dfcf8058bdc7351540d4d6248664169bab1debf8791234e9fa8846f1c63b`), the
version the archived CARACAL controls ran. They are NumPy `.npy` files with a
structured dtype `[("mask", bool), ("chans", float64)]` of shape `(2, 32768)`;
the mask is row 0 of `mask` and the channel centre frequencies in Hz are row 1
of `chans`, as `tricolour/mask.py` reads them. `TRICOLOUR-LICENSE` is the
licence file distributed with that wheel (BSD-3-Clause); see
`research/core-d-tricolour.md` section 1 for the licence decision.

# Observatory positions from casacore-data

`casacore_observatories.json` (SHA256
`975fac968a24199cbb32b4324590e278ff7c8ecfde3ea1a56be58a336437e450`) holds the
57 observatory positions of casacore-data 20250826-160001-5 as
`me.observatory()` returns them in the O-CASA image `rang-o-casa:6.7.6.14`
(name, reference frame and the three measure values with their units); its
`source` key records the same. `rang.cal_refant` takes the array centre
from it for `refant: auto` (`research/e0-refant-extend.md`). The entries are
positions of observatories, facts rather than code, recorded with their
source as the antenna tables in the repository's `data/` are (owner decision
E5-11); casacore-data's own licence was not checked.

# MeerKAT antenna positions

`meerkat.itrf.txt` (SHA256
`cbca5dbe41867fd29878302c3f79f2e8e90fa2278677a2bc7f72ce791fb9e638`) is a byte
copy of the repository's `data/meerkat.itrf.txt`: the 64 MeerKAT ITRF
positions from simms, with their provenance in `data/README.md`. Positions of
antennas are facts, not code (owner decision E5-11, `docs/licence.md`). It is
package data since task V3b (V3's owner decision 4,
`research/v3-intro-track.md`), so `rang.simtruth` and the A1 generator
`python -m rang.simtruth_ms` run from a wheel. GeMClean's simulator compiles
in the copy under `data/`; `tests/test_v3_intro.py` keeps the two identical.
