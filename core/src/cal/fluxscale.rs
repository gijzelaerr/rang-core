//! CASA's flux-density bootstrap `fluxscale` (task C2d,
//! `research/c2d-fluxscale.md`; C1 step 6): from the gain amplitudes of a
//! `G Jones` table, the scale of each transfer field relative to the
//! reference fields, its flux density per window and the fitted spectrum.
//! Written from `SolvableVisJones::fluxscale` of casa6 6.7.6.14
//! (`SolvableVisCal.cc`) and casacore's `median(MaskedArray)`,
//! `stddev(MaskedArray)` and `GenericL2Fit`/`LSQFit` (3.7.1), as read for
//! the protocol (section 0.1 there); CASA is not copied.
//!
//! - `scale`: per field and window the float32 median of every unflagged
//!   amplitude (for `gainthreshold`), the amplitudes inside the threshold
//!   averaged per (hand, antenna) without weights, several reference fields
//!   averaged where valid, the ratios transfer over reference, and per
//!   (transfer field, window) their median `mgratio`, `stddev`, the flux
//!   density `mgratio^2` and CASA's error `2 stddev / sqrt(n - 1)`.
//! - `spectral_fit`: CASA's weighted polynomial fit of `log10 fd` against
//!   `log10 f - mean(log10 f)`, with its order rules and its error scaling.
//! - `casa_median`: casacore's rule, which averages the two middle values of
//!   an even count only when the array, masked elements included, has at
//!   most 100 elements.

/// casacore's `median(MaskedArray)`: `values` are the valid elements,
/// `total` the array's element count including masked ones. Even counts
/// take the mean of the two middle values when `total <= 100`, else the
/// lower one. `None` for no valid element (casacore throws).
pub fn casa_median(values: &[f64], total: usize) -> Option<f64> {
    let n = values.len();
    if n == 0 {
        return None;
    }
    let mut v = values.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n2 = (n - 1) / 2;
    if n.is_multiple_of(2) && total <= 100 {
        Some(0.5 * (v[n2] + v[n2 + 1]))
    } else {
        Some(v[n2])
    }
}

/// `casa_median` in float32, as casacore evaluates it for `Float` arrays
/// (`T(0.5 * (a + b))`).
pub fn casa_median_f32(values: &[f32], total: usize) -> Option<f32> {
    let n = values.len();
    if n == 0 {
        return None;
    }
    let mut v = values.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n2 = (n - 1) / 2;
    if n.is_multiple_of(2) && total <= 100 {
        Some(0.5 * (v[n2] + v[n2 + 1]))
    } else {
        Some(v[n2])
    }
}

/// The rows of a gain table, as `fluxscale` reads them.
pub struct Rows<'a> {
    /// `|CPARAM|` in float32, `(row, par)`.
    pub amp: &'a [f32],
    /// FLAG, `(row, par)`.
    pub flag: &'a [bool],
    pub field: &'a [usize],
    pub spw: &'a [usize],
    pub antenna: &'a [usize],
    pub npar: usize,
    pub nant: usize,
    pub nspw: usize,
    /// One more than the largest field id present (CASA's `nFld`).
    pub nfield: usize,
}

/// What the user asked for, resolved to indices.
pub struct Settings {
    /// Reference fields (sorted, unique, each with rows).
    pub reference: Vec<usize>,
    /// Transfer fields (sorted, unique, without the reference fields).
    pub transfer: Vec<usize>,
    /// The reference window of each window.
    pub refspwmap: Vec<usize>,
    /// CASA's `gainthreshold` (negative: none).
    pub gainthreshold: f32,
}

/// Per (window, field): CASA's `fd`, `fderr`, `numSol` and the scale.
#[derive(Debug, Clone)]
pub struct Scale {
    pub nspw: usize,
    pub nfield: usize,
    /// `(spw, field)`, -1 where no scale was found (CASA's initial value).
    pub fd: Vec<f64>,
    pub fderr: Vec<f64>,
    pub fdrms: Vec<f64>,
    pub mgratio: Vec<f64>,
    pub mgrms: Vec<f64>,
    pub mgerr: Vec<f64>,
    pub numsol: Vec<i32>,
    pub ok: Vec<bool>,
    /// `(field, spw)`: the float32 median amplitude (0 where none).
    pub median_gain: Vec<f32>,
    /// `(field, ant, spw)`: amplitudes used and unflagged, summed over hands.
    pub used: Vec<u32>,
    pub unflagged: Vec<u32>,
}

/// Per-field accumulators over (par, ant, spw), as `MGOK`, `MG`, `MGN`.
struct Acc {
    ok: Vec<bool>,
    mg: Vec<f64>,
    n: Vec<u32>,
    nall: Vec<u32>,
}

/// CASA's flux scale (module docs). Errors carry CASA's messages.
pub fn scale(rows: &Rows<'_>, s: &Settings) -> Result<Scale, String> {
    let (npar, nant, nspw, nfield) = (rows.npar, rows.nant, rows.nspw, rows.nfield);
    let nrow = rows.field.len();
    for (name, len) in [
        ("spw", rows.spw.len()),
        ("antenna", rows.antenna.len()),
        ("amp", rows.amp.len() / npar.max(1)),
        ("flag", rows.flag.len() / npar.max(1)),
    ] {
        if len != nrow {
            return Err(format!("{name} has {len} rows, not {nrow}"));
        }
    }
    if rows.amp.len() != nrow * npar || rows.flag.len() != nrow * npar {
        return Err("amp and flag must be (row, par)".into());
    }
    if s.refspwmap.len() != nspw || s.refspwmap.iter().any(|&r| r >= nspw) {
        return Err("refspwmap must give a window for every window".into());
    }
    for r in 0..nrow {
        if rows.field[r] >= nfield || rows.spw[r] >= nspw || rows.antenna[r] >= nant {
            return Err(format!("row {r}: field, spw or antenna out of range"));
        }
    }
    if s.reference.is_empty() {
        return Err("Cannot find specified reference field(s)".into());
    }
    let cube = npar * nant * nspw;
    let at = |p: usize, a: usize, w: usize| p + npar * (a + nant * w);
    let present: Vec<bool> = (0..nfield).map(|f| rows.field.contains(&f)).collect();
    for &f in s.reference.iter() {
        if f >= nfield || !present[f] {
            return Err(format!("reference field {f} has no solutions"));
        }
    }

    // The float32 median amplitude per (field, spw), over every row of the
    // field and window: casacore counts the masked elements too.
    let mut median_gain = vec![0f32; nfield * nspw];
    for f in 0..nfield {
        let mut valid_any = false;
        for w in 0..nspw {
            let mut vals = Vec::new();
            let mut total = 0usize;
            for r in 0..nrow {
                if rows.field[r] != f || rows.spw[r] != w {
                    continue;
                }
                for p in 0..npar {
                    total += 1;
                    if !rows.flag[r * npar + p] {
                        vals.push(rows.amp[r * npar + p]);
                    }
                }
            }
            match casa_median_f32(&vals, total) {
                Some(m) => {
                    median_gain[f * nspw + w] = m;
                    valid_any = true;
                }
                None => {
                    // casacore throws; CASA marks the selection invalid for a
                    // transfer field only.
                }
            }
        }
        if s.transfer.contains(&f) && !valid_any {
            return Err(format!(
                "The input selections results in empy data selection for the transfer field={f}"
            ));
        }
    }

    // Accumulate the amplitudes inside the threshold, per field.
    let mut acc: Vec<Option<Acc>> = (0..nfield).map(|_| None).collect();
    let t = s.gainthreshold;
    let lowbound: f32 = if t > 0.0 && t < 1.0 {
        (1.0f64 - t as f64) as f32
    } else if t == 0.0 {
        1.0
    } else {
        0.0
    };
    let wanted: Vec<bool> = (0..nfield)
        .map(|f| s.reference.contains(&f) || s.transfer.contains(&f))
        .collect();
    for r in 0..nrow {
        let (f, w, a) = (rows.field[r], rows.spw[r], rows.antenna[r]);
        if !wanted[f] {
            continue;
        }
        let e = acc[f].get_or_insert_with(|| Acc {
            ok: vec![false; cube],
            mg: vec![0.0; cube],
            n: vec![0; cube],
            nall: vec![0; cube],
        });
        let med = median_gain[f * nspw + w];
        for p in 0..npar {
            if rows.flag[r * npar + p] {
                continue;
            }
            let gn = rows.amp[r * npar + p] as f64;
            let inside =
                t < 0.0 || (gn >= (lowbound * med) as f64 && gn <= (1.0 + t as f64) * med as f64);
            let i = at(p, a, w);
            if inside {
                e.ok[i] = true;
                e.mg[i] += gn;
                e.n[i] += 1;
            }
            e.nall[i] += 1;
        }
    }
    let mut used = vec![0u32; nfield * nant * nspw];
    let mut unflagged = vec![0u32; nfield * nant * nspw];
    for (f, e) in acc.iter_mut().enumerate() {
        let Some(e) = e else { continue };
        for w in 0..nspw {
            for a in 0..nant {
                for p in 0..npar {
                    let i = at(p, a, w);
                    used[(f * nant + a) * nspw + w] += e.n[i];
                    unflagged[(f * nant + a) * nspw + w] += e.nall[i];
                    if e.ok[i] && e.n[i] > 0 {
                        e.mg[i] /= e.n[i] as f64;
                    } else {
                        e.mg[i] = 0.0;
                        e.ok[i] = false;
                    }
                }
            }
        }
    }

    // The reference: the first reference field, or the mean over the valid
    // ones (CAS-4758).
    let r0 = s.reference[0];
    let (mut mgref, mut mgrefok) = {
        let e = acc[r0]
            .as_ref()
            .ok_or("reference field without solutions")?;
        (e.mg.clone(), e.ok.clone())
    };
    if s.reference.len() > 1 {
        let mut nok = vec![0f64; cube];
        let last = s.reference.len() - 1;
        for (iref, &fr) in s.reference.iter().enumerate().skip(1) {
            let e = acc[fr]
                .as_ref()
                .ok_or("reference field without solutions")?;
            for i in 0..cube {
                if iref == 1 {
                    if mgrefok[i] {
                        nok[i] += 1.0;
                    } else {
                        mgref[i] = 0.0;
                    }
                }
                if e.ok[i] {
                    mgref[i] += e.mg[i];
                    nok[i] += 1.0;
                }
                if iref == last {
                    if nok[i] == 0.0 {
                        mgrefok[i] = false;
                        mgref[i] = 0.0;
                    } else {
                        mgrefok[i] = true;
                    }
                }
            }
        }
        for i in 0..cube {
            mgref[i] /= nok[i];
        }
    }

    let n2 = nspw * nfield;
    let mut out = Scale {
        nspw,
        nfield,
        fd: vec![-1.0; n2],
        fderr: vec![-1.0; n2],
        fdrms: vec![-1.0; n2],
        mgratio: vec![-1.0; n2],
        mgrms: vec![-1.0; n2],
        mgerr: vec![-1.0; n2],
        numsol: vec![-1; n2],
        ok: vec![false; n2],
        median_gain,
        used,
        unflagged,
    };
    for &ft in s.transfer.iter() {
        let Some(e) = acc[ft].as_mut() else { continue };
        for w in 0..nspw {
            let rw = s.refspwmap[w];
            let any = (0..nant).any(|a| (0..npar).any(|p| e.ok[at(p, a, w)]));
            if any {
                for a in 0..nant {
                    for p in 0..npar {
                        let (i, j) = (at(p, a, w), at(p, a, rw));
                        if e.ok[i] && mgrefok[j] && mgref[j] > 0.0 {
                            e.mg[i] /= mgref[j];
                        } else {
                            e.mg[i] = 0.0;
                            e.ok[i] = false;
                        }
                    }
                }
            }
            // In casacore's storage order: hand fastest, then antenna.
            let vals: Vec<f64> = (0..nant)
                .flat_map(|a| (0..npar).map(move |p| (p, a)))
                .filter(|&(p, a)| e.ok[at(p, a, w)])
                .map(|(p, a)| e.mg[at(p, a, w)])
                .collect();
            let npa = vals.len();
            if npa == 0 {
                continue;
            }
            let k = w * nfield + ft;
            out.ok[k] = true;
            let ratio = casa_median(&vals, npar * nant).expect("npa > 0");
            out.mgratio[k] = ratio;
            if npa == 1 {
                out.mgrms[k] = 0.0;
                out.mgerr[k] = 0.0;
            } else {
                let mean = vals.iter().sum::<f64>() / npa as f64;
                let var =
                    vals.iter().map(|v| (v - mean).abs().powi(2)).sum::<f64>() / (npa - 1) as f64;
                out.mgrms[k] = var.sqrt();
                out.mgerr[k] = out.mgrms[k] / ((npa - 1) as f64).sqrt();
            }
            out.fd[k] = ratio * ratio;
            out.fdrms[k] = 2.0 * out.mgrms[k];
            out.fderr[k] = if npa == 1 {
                0.0
            } else {
                out.fdrms[k] / ((npa - 1) as f64).sqrt()
            };
            out.numsol[k] = npa as i32;
        }
    }
    if !out.ok.iter().any(|&o| o) {
        return Err("No scale factors determined!".into());
    }
    Ok(out)
}

/// CASA's spectral fit of one transfer field (`fluxscale`, section 0.1
/// item 9 of the note).
#[derive(Debug, Clone, PartialEq)]
pub struct Fit {
    /// The polynomial order used (CASA's `myfitorder`).
    pub order: usize,
    /// Coefficients in `log10` units, constant first.
    pub coeffs: Vec<f64>,
    pub errors: Vec<f64>,
    /// `(order + 1)^2`, row-major, the unscaled inverse normal matrix.
    pub covar: Vec<f64>,
    pub flux: f64,
    pub flux_err: f64,
    pub ref_freq: f64,
}

/// Solve the symmetric positive system `n x = b` (Gauss-Jordan with
/// partial pivoting) and return `x` and `n^-1`.
fn solve_normal(n: &[f64], b: &[f64], m: usize) -> Result<(Vec<f64>, Vec<f64>), String> {
    let mut a = n.to_vec();
    let mut inv = vec![0.0; m * m];
    for i in 0..m {
        inv[i * m + i] = 1.0;
    }
    for c in 0..m {
        let piv = (c..m)
            .max_by(|&i, &j| a[i * m + c].abs().total_cmp(&a[j * m + c].abs()))
            .unwrap();
        if a[piv * m + c] == 0.0 || !a[piv * m + c].is_finite() {
            return Err("singular normal matrix in the spectral fit".into());
        }
        if piv != c {
            for k in 0..m {
                a.swap(c * m + k, piv * m + k);
                inv.swap(c * m + k, piv * m + k);
            }
        }
        let d = a[c * m + c];
        for k in 0..m {
            a[c * m + k] /= d;
            inv[c * m + k] /= d;
        }
        for i in 0..m {
            if i != c {
                let f = a[i * m + c];
                if f != 0.0 {
                    for k in 0..m {
                        a[i * m + k] -= f * a[c * m + k];
                        inv[i * m + k] -= f * inv[c * m + k];
                    }
                }
            }
        }
    }
    let x = (0..m)
        .map(|i| (0..m).map(|k| inv[i * m + k] * b[k]).sum())
        .collect();
    Ok((x, inv))
}

/// CASA's fit over the valid windows of one field: `freq` (Hz), `fd` and
/// `fderr` per window, `fitorder` the user's (must be >= 0).
pub fn spectral_fit(
    freq: &[f64],
    fd: &[f64],
    fderr: &[f64],
    fitorder: usize,
) -> Result<Fit, String> {
    let nv = freq.len();
    if nv == 0 || fd.len() != nv || fderr.len() != nv {
        return Err("spectral_fit needs equal, non-empty freq, fd and fderr".into());
    }
    if nv == 1 {
        return Ok(Fit {
            order: 0,
            coeffs: vec![],
            errors: vec![],
            covar: vec![],
            flux: fd[0],
            flux_err: 0.0,
            ref_freq: freq[0],
        });
    }
    let order = if nv == 2 && fitorder > 1 { 0 } else { fitorder };
    let m = order + 1;
    let logf: Vec<f64> = freq.iter().map(|f| f.log10()).collect();
    let mean = logf.iter().sum::<f64>() / nv as f64;
    let mut n = vec![0.0; m * m];
    let mut b = vec![0.0; m];
    let mut sumll = 0.0;
    let mut nc = 0usize;
    for i in 0..nv {
        let sigma = fderr[i] / fd[i];
        if sigma == 0.0 || sigma == -1.0 {
            continue;
        }
        let w = (1.0 / sigma).abs().powi(2);
        let x = logf[i] - mean;
        let y = fd[i].log10();
        let row: Vec<f64> = (0..m).map(|k| x.powi(k as i32)).collect();
        for j in 0..m {
            for k in 0..m {
                n[j * m + k] += w * row[j] * row[k];
            }
            b[j] += w * row[j] * y;
        }
        sumll += w * y * y;
        nc += 1;
    }
    let (sol, inv) = solve_normal(&n, &b, m)?;
    let chi2 = sumll - sol.iter().zip(b.iter()).map(|(s, k)| s * k).sum::<f64>();
    let mu = (chi2 / (1.0f64).max(nc as f64 - m as f64)).max(0.0).sqrt();
    let errors: Vec<f64> = (0..m).map(|i| inv[i * m + i].abs().sqrt() * mu).collect();
    let flux = 10f64.powf(sol[0]);
    let flux_err = if errors[0] > 0.0 {
        std::f64::consts::LN_10 * flux * errors[0]
    } else {
        0.0
    };
    Ok(Fit {
        order,
        coeffs: sol,
        errors,
        covar: inv,
        flux,
        flux_err,
        ref_freq: 10f64.powf(mean),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn median_follows_casacore() {
        // Odd: the middle value; even with a small array: the mean.
        assert_eq!(casa_median(&[3.0, 1.0, 2.0], 3), Some(2.0));
        assert_eq!(casa_median(&[4.0, 1.0, 3.0, 2.0], 32), Some(2.5));
        // Even with more than 100 elements (masked ones count): the lower.
        assert_eq!(casa_median(&[4.0, 1.0, 3.0, 2.0], 128), Some(2.0));
        assert_eq!(casa_median(&[], 5), None);
        assert_eq!(casa_median_f32(&[1.0, 2.0], 2), Some(1.5));
    }

    type Table = (Vec<f32>, Vec<bool>, Vec<usize>, Vec<usize>, Vec<usize>);

    fn table(amp: Vec<f32>, field: Vec<usize>, ant: Vec<usize>) -> Table {
        let n = field.len();
        let flag = vec![false; amp.len()];
        (amp, flag, field, vec![0; n], ant)
    }

    #[test]
    fn ratio_squared_is_the_flux() {
        // Two antennas, two hands; the transfer gains are 2x the reference's.
        let (amp, flag, field, spw, ant) = table(
            vec![1.0, 1.2, 0.8, 0.9, 2.0, 2.4, 1.6, 1.8],
            vec![0, 0, 1, 1],
            vec![0, 1, 0, 1],
        );
        let rows = Rows {
            amp: &amp,
            flag: &flag,
            field: &field,
            spw: &spw,
            antenna: &ant,
            npar: 2,
            nant: 2,
            nspw: 1,
            nfield: 2,
        };
        let s = Settings {
            reference: vec![0],
            transfer: vec![1],
            refspwmap: vec![0],
            gainthreshold: -1.0,
        };
        let out = scale(&rows, &s).unwrap();
        let k = 1; // spw 0, field 1
        assert!(out.ok[k]);
        assert!((out.mgratio[k] - 2.0).abs() < 1e-6);
        assert!((out.fd[k] - 4.0).abs() < 1e-5);
        assert_eq!(out.numsol[k], 4);
        assert!(!out.ok[0]);
        assert_eq!(out.fd[0], -1.0);
    }

    #[test]
    fn threshold_excludes_an_outlier() {
        // Antenna 1 of the transfer field is 3x high in one of two rows.
        let amp = vec![
            1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 6.0, 6.0,
        ];
        let field = vec![0, 0, 0, 0, 1, 1, 1, 1];
        let ant = vec![0, 1, 0, 1, 0, 1, 0, 1];
        let (amp, flag, field, spw, ant) = table(amp, field, ant);
        let rows = Rows {
            amp: &amp,
            flag: &flag,
            field: &field,
            spw: &spw,
            antenna: &ant,
            npar: 2,
            nant: 2,
            nspw: 1,
            nfield: 2,
        };
        let mut s = Settings {
            reference: vec![0],
            transfer: vec![1],
            refspwmap: vec![0],
            gainthreshold: -1.0,
        };
        let all = scale(&rows, &s).unwrap();
        s.gainthreshold = 0.5;
        let cut = scale(&rows, &s).unwrap();
        assert!((cut.mgratio[1] - 2.0).abs() < 1e-12);
        assert!(all.mgratio[1] > 2.0);
        assert_eq!(cut.used[3], 2);
        assert_eq!(cut.unflagged[3], 4);
    }

    #[test]
    fn fit_recovers_a_power_law() {
        let freq = [0.9e9, 1.1e9, 1.3e9, 1.6e9];
        let fd: Vec<f64> = freq
            .iter()
            .map(|f| 4.0 * (f / 1.4e9f64).powf(-0.6))
            .collect();
        let err = vec![0.01; 4];
        let fit = spectral_fit(&freq, &fd, &err, 1).unwrap();
        assert_eq!(fit.order, 1);
        assert!((fit.coeffs[1] + 0.6).abs() < 1e-12);
        let s0 = 4.0 * (fit.ref_freq / 1.4e9).powf(-0.6);
        assert!((fit.flux - s0).abs() < 1e-12);
        assert!(fit.errors.iter().all(|e| *e < 1e-6));
        // Two windows and fitorder 2: CASA's unset branch gives order 0.
        let two = spectral_fit(&freq[..2], &fd[..2], &err[..2], 2).unwrap();
        assert_eq!(two.order, 0);
        assert_eq!(two.coeffs.len(), 1);
        // One window: no fit.
        let one = spectral_fit(&freq[..1], &fd[..1], &err[..1], 1).unwrap();
        assert_eq!((one.flux, one.ref_freq), (fd[0], freq[0]));
        // Zero errors are skipped, so three points remain.
        let mut e0 = err.clone();
        e0[3] = 0.0;
        let skip = spectral_fit(&freq, &fd, &e0, 1).unwrap();
        assert!((skip.coeffs[1] + 0.6).abs() < 1e-12);
    }
}
