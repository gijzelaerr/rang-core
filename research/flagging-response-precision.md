# Response evaluation precision failure and fix-forward

2026-09-24. The frozen10-solve response pilot completed actual QuartiCal
calibration but failed its strict inverse-Jones decomposition closure check.
Failed run `outputs/tv-response-20260924-recovered-01` is preserved unchanged;
there is no result.json/final success audit and no science improvement claim.
All ten native calibration command/log/gain/metrics outputs remain retained.

## Independent read-only diagnosis

Native DATA is complex64. The original implementation allocated `actual_delta`
as complex64 and subtracted the two stored native DATA arrays in that dtype.
Although the DATA values themselves were correct, some small components of
their difference rounded again. Casting the narrow difference afterwards cannot
recover those components. The corrected visibility operation uses complex128
gain coefficients, so that extra narrow rounding breaks its linear identity.

Both signs and all eight injected-sky/grid arms were replayed read-only using
the exact retained gains/native DATA, on one commonTEST9169/9169 support,
zero unsupported samples. Saved differences have108 positive/104 negative
TEST correlation components with precision loss; each sign's maximum difference
from cast-before-subtraction DATA is3.725290298461914e-9Jy.

| Sign | Sky | Grid | Saved complex64 delta closure, Jy | Wide DATA difference closure, Jy |
| --- | --- | --- | ---: | ---: |
| + | omitted | 2,32 | 3.1804940996957817e-9 | 6.988730482830058e-15 |
| + | omitted | 14,128 | 3.5116627059873515e-9 | 7.467075239607940e-15 |
| + | complete diagnostic | 2,32 | 3.1831128286105646e-9 | 6.884505334999802e-15 |
| + | complete diagnostic | 14,128 | 3.5135691699255386e-9 | 7.879712106676592e-15 |
| − | omitted | 2,32 | 3.3963557326775340e-9 | 8.252985906614684e-15 |
| − | omitted | 14,128 | 3.5144860680407760e-9 | 7.577272143066693e-15 |
| − | complete diagnostic | 2,32 | 3.3966198879673533e-9 | 7.548754398627655e-15 |
| − | complete diagnostic | 14,128 | 3.5126051770486874e-9 | 7.984650069228706e-15 |

The unchanged threshold is1e-10Jy. All narrow differences fail; all wide
differences pass by more than four orders of magnitude. This is a software
precision diagnosis, not independent calibration/science evidence.

19 read-only diagnosis checks pass. Original/source DATA, Observatory flags,
the base calibration model and all four native weight/SIGMA columns remain
protected. Failed working copies still contain the temporary training/holdout
flags: evaluation failed before final flag restoration, so they are NOT
advertised as exported/restored/deployable MSs. No old file was repaired in place.

Failed-run tree digest (excluding only casacore transient table.lock files),
identical before/after diagnosis:
`f16c341384e9d8baf397640a2c0fa245235cbc1b34aedc621d5bff123534af8f`.
Frozen runtime module SHA256:
`4b3771c36c26a041d1a0bcf35058ab9dabeeceb3cf1dba581a251788780779ab`.
`response-config.json` SHA256:
`3ee5b6f969247562a9652cc5aded25c853b78146f9a52e3c55e2495fb197d259`.
Prepared source digest remains
`8d21dd5ab4ff0d689ee06379fdc5bc00890fcb7c6221beec5d30007e34afba4c`;
raw/original source digest remains
`84e244f9e8256731b0d20a0e853a107dd80e3c2be36a532efe707b3d8766c519`.

## Narrow implementation fix; new run required

Allocate the evaluation delta as complex128 and cast EACH stored native DATA
value before subtraction. Native injected DATA, calibration sky/model columns,
native weights, flags, gain grids, source settings, solver commands and closure
tolerance are unchanged. Record delta dtype/precision explicitly. This is not
a wider tolerance, changed injection or retrospective reinterpretation of the
old bounded spectral fits.

A new regression exercises `_inject` with a mocked native-complex64 table,
bright real diagonal visibilities, tiny imaginary components and signed faint
perturbations, then non-diagonal full-Jones inverse correction. It requires
exact wide differences, protected outside-mask DATA/model/flags, unchanged
complex64 storage, successful1e-10 closure and failure of subtraction-then-cast.
No dataset or QuartiCal solver is invoked by that regression.

All 27 targeted response tests pass, including both signed precision
regressions; Ruff lint/format checks and `git diff --check` pass. Root's full
local verification preceded the fix-forward checkpoint `1f53a17`. A fresh
`outputs/tv-response-20260924-precision-01` completed all ten solves and strict
evaluation on2026-09-24 08:51:35UTC; [measured response](flagging-response.md)
and [full compact results](results/gain-tv-response.json) are new artifacts.
The failed run remains unchanged and has no final success audit. Twenty actual
QC invocations represent ten frozen controls repeated after the precision fix,
not twenty independent replicates. Independent source/gain/input replay is
recorded separately; no old trial DATA, gains or config was repaired in place.
