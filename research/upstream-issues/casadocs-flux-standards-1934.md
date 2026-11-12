Target: https://github.com/casangi/casadocs/issues
Status: ready to post
Reproduced on: casatasks/casatools 6.7.6.14 (PyPI), run 2026-11-12: setjy 'Stevens-Reynolds 2016' on 1934-638 at 11.0 and 11.1 GHz. Docs read at casangi/casadocs master 4073e552e2bc (docs/notebooks/memo-series.ipynb, "Flux Calibrator Models"). Code read in source at casa6 master 90e9d3dae955.
Duplicates checked: casangi/casadocs issues and PRs, open and closed, searched for "Stevens", "Reynolds", "1934", "Baars", "frequecy" and "setjy"; the only hit is PR #45 "Update task_setjy.rst" (unrelated).

Title: Flux calibrator models: Stevens-Reynolds 2016 break is 11.1496 GHz, not 11 GHz; Baars entry omits its 1934-638 polynomial

---

Three small corrections to the "Flux Calibrator Models" section of `docs/notebooks/memo-series.ipynb` (at 4073e55).

1. **Stevens-Reynolds 2016.** The page says "Low frequency (<11GHz) polynomial from Reynolds and updated high frequecy polynomial from Stevens." The code switches at 11.1496 GHz (casa6 `casatools/src/code/components/ComponentModels/FluxStdsQS2.cc:202-204`, `fill_lohi_coeffs(..., MFrequency(Quantity(11.1496, "GHz")), ...)`). That is where the two polynomials cross: 2.07375 Jy for both. Between 11 and 11.1496 GHz CASA uses the Reynolds piece. For example, `setjy(standard='Stevens-Reynolds 2016')` on 1934-638 at 11.0 GHz gives 2.10811 Jy, while the Stevens piece gives 2.11267 Jy (+0.22 %). Suggested text: "Reynolds polynomial below 11.1496 GHz (where the two fits cross), Stevens above." Also "frequecy" -> "frequency".

2. **Baars.** The section says the models are second-order polynomials from Baars et al. (1977), valid 408 MHz to 15 GHz. But `setjy(standard='Baars')` also answers for 1934-638, which is not in Baars et al. (1977). It uses the cubic `-23.839, 19.569, -4.8168, 0.35836` (MHz; `FluxStdsQS2.cc:65-66`, comment "No error specified"). The Perley 90 / Perley-Taylor entries say "plus Reynolds (1934-638; 7/94)". The Baars entry should say the same, or say where that polynomial comes from.

3. Optional, for the same section: the compiled coefficients are stored as `RigidVector<Float, N>` (float32) and evaluated in double. So the results differ from the printed decimals by up to about 3e-7 relative. This is harmless, but worth one sentence for anyone checking setjy against the papers.
