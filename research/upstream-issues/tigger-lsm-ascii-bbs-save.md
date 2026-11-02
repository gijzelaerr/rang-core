# Tigger: ASCII.save and BBS.save write files their own loaders cannot read back

Repository: ratt-ru/tigger-lsm. Status: **filed 2026-11-02 (U4), https://github.com/ratt-ru/tigger-lsm/issues/55**. Found by DF-IO
([../dfio-formats.md](../dfio-formats.md)), reproduced by U4 on 1.8.0 with
[../u4-upstream-files/tigger_repro.py](../u4-upstream-files/tigger_repro.py); `master`
11131bec has the same lines. Environment detail for the record: on a fresh venv 1.8.0 does
not import because PyPI `kittens` (through purr) overwrites `astro-kittens`; the run removed
`kittens` and reinstalled `astro-kittens`. That is a separate candidate, not in this issue
(see [../u4-upstream.md](../u4-upstream.md)).

<!-- issue-title: ASCII.save and BBS.save: a multi-term spectral index is written as a list repr their loaders skip, and BBS shapes are written in radians -->
<!-- issue-body -->
With astro-tigger-lsm 1.8.0 (astro-kittens 1.4.6, NumPy 2.5.4, Python 3.12), a model with a three-term spectrum does not survive a save and load through either text format. `master` (11131bec) has the same code.

```python
import numpy
from Tigger.Models import ModelClasses, SkyModel
from Tigger.Models.Formats import ASCII, BBS

a = SkyModel.Source("A", ModelClasses.Position(0.1, -0.5), ModelClasses.Polarization(2.0, 0, 0, 0),
                    shape=ModelClasses.Gaussian(float(numpy.deg2rad(20 / 3600)), float(numpy.deg2rad(10 / 3600)), float(numpy.deg2rad(30))),
                    spectrum=ModelClasses.SpectralIndex([-0.7, -0.1, 0.02], 1.4e9))
b = SkyModel.Source("B", ModelClasses.Position(0.1, -0.5001), ModelClasses.Polarization(1.0, 0, 0, 0),
                    spectrum=ModelClasses.SpectralIndex(-0.7, 1.4e9))
ASCII.save(SkyModel.SkyModel(a, b), "m.txt")
BBS.save(SkyModel.SkyModel(a, b), "m.catalog")
print([s.name for s in ASCII.load("m.txt").sources])    # ['B']
print([s.name for s in BBS.load("m.catalog").sources])  # ['B']
```

**ASCII.** `ASCII.py` line 495 writes `repr(spi)` into the single `spi` column, so the list spreads over three whitespace-separated fields, while the loader reads `spi`, `spi2`, `spi3`, ... (lines 211 and 292). With `verbose=True` the load stops on `could not convert string to float: '-0.1,'`; by default the line is skipped:

```
A 0 22 55.09870000000001 -28 38 52.40000000000873 2.0 0 0 0 [-0.7, -0.1, 0.02] 0 20.000000000000004 ...
```

Writing the terms to `spi`, `spi2`, ... would match the loader.

**BBS, spectrum.** `BBS.py` line 384 writes `str(spi)` into `SpectralIndex:0` with `SpectralIndexDegree` 0, and `BBS.load` calls `float()` on it (line 274), so the source is skipped.

**BBS, shape.** Lines 389-391 write the `Gaussian` values as they are, in radians. The 20 x 10 arcsec source at PA 30 deg becomes:

```
A, GAUSSIAN, , 5.43.46.4806, -28.38.52.4031, 2.0, 0, 0, 0, 1400000000.0, 0, [-0.7, -0.1, 0.02], 9.696273622190721e-05, 4.8481368110953604e-05, 0.5235987755982988
```

makesourcedb and LSMTool read `MajorAxis` and `MinorAxis` in arcsec and `Orientation` in degrees. `BBS.load` (lines 279-281) reads them unconverted too, so Tigger's own round trip looks consistent while other BBS readers see a much smaller source. Converting in both `save` and `load` would fix it, though existing Tigger-written catalogues would then be read differently.

Thanks for maintaining this.
<!-- /issue-body -->
