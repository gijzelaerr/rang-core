# Crystalball: import_from_wsclean fails on SpectralIndex lists of different lengths

Repository: caracal-pipeline/crystalball. Status: **filed 2026-11-02 (U4), https://github.com/caracal-pipeline/crystalball/issues/83**. Found by DF-IO, reproduced
by U4 on 0.4.3 ([../u4-upstream-files/crystalball_repro.py](../u4-upstream-files/crystalball_repro.py));
`master` 21213bcc has the same lines. No duplicate (#3, #31 and #42 are other parsing problems,
all closed).

<!-- issue-title: import_from_wsclean fails with "inhomogeneous shape" when components have SpectralIndex lists of different lengths -->
<!-- issue-body -->
With crystalball 0.4.3 (codex-africanus 0.4.5, NumPy 2.5.4, Python 3.12), a WSClean component list whose components have different spectral orders cannot be loaded:

```python
from crystalball.wsclean import import_from_wsclean

open("m.txt", "w").write(
    "Format = Name, Type, Ra, Dec, I, SpectralIndex, LogarithmicSI, ReferenceFrequency='1400000000.0', MajorAxis, MinorAxis, Orientation\n"
    "s0c0,POINT,00:00:00.0,-30.00.00.0,1.0,[-0.7,-0.1],false,1400000000.0,,,\n"
    "s0c1,POINT,00:00:10.0,-30.00.00.0,0.5,[-0.7],false,1400000000.0,,,\n"
)
import_from_wsclean("m.txt")
```

```
ValueError: setting an array element with a sequence. The requested array has an inhomogeneous shape after 1 dimensions. The detected shape was (2,) + inhomogeneous part.
```

The cause is `np.asarray(values)` over every column in `wsclean.py` (line 59, the same on `master`, 21213bcc). The same list with `[-0.7,0.0]` in the second component loads, with `spi` of shape `(2, 2)`.

Padding `SpectralIndex` with zeros to the longest list before stacking should keep the values the same, since an extra zero term adds nothing to the polynomial. I have not tested that change.
<!-- /issue-body -->
