# Tigger: ASCII.save writes np.float64(...) for NumPy scalars

Repository: ratt-ru/tigger-lsm. Status: **filed 2026-11-02 (U4), https://github.com/ratt-ru/tigger-lsm/issues/57**. Reproduced by U4 on 1.8.0
([../u4-upstream-files/tigger_numpy_scalars.py](../u4-upstream-files/tigger_numpy_scalars.py)).

<!-- issue-title: ASCII.save writes np.float64(...) into shape columns when values are NumPy scalars, and the loader skips the source -->
<!-- issue-body -->
A related case to #55. With astro-tigger-lsm 1.8.0 and NumPy 2.5.4, `ASCII.save` writes the NumPy 2 `repr` of a shape value when the model holds NumPy scalars, and `ASCII.load` then skips that source.

```python
import numpy
from Tigger.Models import ModelClasses, SkyModel
from Tigger.Models.Formats import ASCII

src = SkyModel.Source("A", ModelClasses.Position(0.1, -0.5), ModelClasses.Polarization(2.0, 0, 0, 0),
                      shape=ModelClasses.Gaussian(numpy.deg2rad(20 / 3600), numpy.deg2rad(10 / 3600), numpy.deg2rad(30)),
                      spectrum=ModelClasses.SpectralIndex(-0.7, 1.4e9))
ASCII.save(SkyModel.SkyModel(src), "np.txt")
print(ASCII.load("np.txt").sources)   # []
```

```
A 0 22 55.09870000000001 -28 38 52.40000000000873 2.0 0 0 0 -0.7 0 np.float64(20.000000000000004) np.float64(10.000000000000002) np.float64(29.999999999999996) 1400000000.0
```

With `verbose=True` the load stops on `could not convert string to float: 'np.float64(20.000000000000004)'`.

The cause is `repr(getattr(src.shape, sparm, 0) / scale)` in `ASCII.py`, the same on `master` (11131bec). Plain Python floats write correctly, and `repr(float(...))` would cover both. Other fields in `save` also use `repr`, but I only tested the shape values.
<!-- /issue-body -->
