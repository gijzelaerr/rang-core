//! The F4 flagger (task F4, `research/f4-flagger.md`, section 3): F3's
//! fifteen planes plus eight scan-scale spectral planes per
//! cross-correlation baseline, and F3's five-layer dilated 3×3 network with
//! 23 inputs, in f32.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The spectral planes compare each baseline's time-median spectrum `P` with
//! the median over the other baselines `B`, per correlation family (parallel
//! XX, YY; cross XY, YX): `e = max_c |P − B − q25_f(P − B)|`, its antenna
//! medians and the array excess `B − q25_f(B)`. Antenna-local, scan-long RFI
//! wider than F3's 33-channel running median shows across its whole band.
//! The NumPy reference is `rang.f4flag.features_numpy`; parity is in
//! `tests/test_f4_flag.py`. F3's numerics are reused unchanged.

pub use crate::f3flag::Inputs;
use crate::f3flag::{
    self, MIN_AGG, check, max_finite, median, medians_of_u, pair64, residuals, rows_by_baseline,
    u_planes,
};
use rayon::prelude::*;

/// Input planes per cell: F3's 14 feature planes, 8 spectral, the mask.
pub const INPUTS: usize = 23;
/// Plane of the first spectral feature.
pub const SPEC0: usize = 14;
const MIN_SPEC: usize = 16;
/// Correlation indices of the two families: parallel, cross.
const FAMILIES: [[usize; 2]; 2] = [[0, 3], [1, 2]];

/// Weights: 9·23·8 + 8 + 4·584 + 9.
pub fn weight_count() -> usize {
    f3flag::weight_count_for(INPUTS)
}

/// NumPy's default (linear) percentile `q` in [0, 1] of the finite values,
/// NaN if fewer than `min` are finite. Reorders `v`.
pub(crate) fn quantile(v: &mut Vec<f64>, q: f64, min: usize) -> f64 {
    v.retain(|x| x.is_finite());
    let n = v.len();
    if n < min.max(1) {
        return f64::NAN;
    }
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let h = q * (n - 1) as f64;
    let lo = h.floor() as usize;
    let t = h - lo as f64;
    if lo + 1 >= n {
        return v[n - 1];
    }
    let (a, b) = (v[lo], v[lo + 1]);
    // NumPy's `_lerp`: a + (b − a) t, from the upper end when t ≥ 0.5.
    if t >= 0.5 {
        b - (b - a) * (1.0 - t)
    } else {
        a + (b - a) * t
    }
}

/// The spectral features of one scan.
struct Spectra {
    nc: usize,
    /// Per baseline `[φ][f]`.
    e: Vec<Vec<f64>>,
    /// `[φ][k][f]`.
    ant: Vec<f64>,
    /// `[φ][f]`.
    x: Vec<f64>,
    alive: Vec<bool>,
}

fn spectra(inp: &Inputs, p: &[Vec<f64>], alive: Vec<bool>) -> Spectra {
    let nc = inp.nchan;
    let nbl = inp.nbl;
    let nant = inp.nant;
    // B_c(f): median over baselines, layout [f][c].
    let big_b: Vec<[f64; 4]> = (0..nc)
        .into_par_iter()
        .map(|f| {
            let mut out = [f64::NAN; 4];
            let mut buf = Vec::with_capacity(nbl);
            for (c, o) in out.iter_mut().enumerate() {
                buf.clear();
                buf.extend(p.iter().map(|pb| pb[f * 4 + c]).filter(|v| v.is_finite()));
                if buf.len() >= MIN_AGG {
                    *o = median(&mut buf);
                }
            }
            out
        })
        .collect();
    let e: Vec<Vec<f64>> = p
        .par_iter()
        .map(|pb| {
            let mut w = vec![f64::NAN; nc * 4];
            for f in 0..nc {
                for c in 0..4 {
                    w[f * 4 + c] = pb[f * 4 + c] - big_b[f][c];
                }
            }
            let mut off = [f64::NAN; 4];
            let mut buf = Vec::with_capacity(nc);
            for (c, o) in off.iter_mut().enumerate() {
                buf.clear();
                buf.extend((0..nc).map(|f| w[f * 4 + c]));
                *o = quantile(&mut buf, 0.25, MIN_SPEC);
            }
            let mut out = vec![f64::NAN; 2 * nc];
            for (phi, fam) in FAMILIES.iter().enumerate() {
                for f in 0..nc {
                    let d = [
                        (w[f * 4 + fam[0]] - off[fam[0]]).abs(),
                        (w[f * 4 + fam[1]] - off[fam[1]]).abs(),
                    ];
                    out[phi * nc + f] = max_finite(&d);
                }
            }
            out
        })
        .collect();
    let mut of_ant: Vec<Vec<usize>> = vec![Vec::new(); nant];
    for b in 0..nbl {
        of_ant[inp.ant1[b] as usize].push(b);
        if inp.ant2[b] != inp.ant1[b] {
            of_ant[inp.ant2[b] as usize].push(b);
        }
    }
    let ant: Vec<f64> = (0..2 * nant)
        .into_par_iter()
        .flat_map_iter(|pk| {
            let (phi, k) = (pk / nant, pk % nant);
            let mut buf = Vec::with_capacity(of_ant[k].len());
            (0..nc)
                .map(|f| {
                    buf.clear();
                    buf.extend(
                        of_ant[k]
                            .iter()
                            .map(|&b| e[b][phi * nc + f])
                            .filter(|v| v.is_finite()),
                    );
                    if buf.len() >= MIN_AGG {
                        median(&mut buf)
                    } else {
                        f64::NAN
                    }
                })
                .collect::<Vec<_>>()
        })
        .collect();
    let mut x = vec![f64::NAN; 2 * nc];
    let mut base = [f64::NAN; 4];
    let mut buf = Vec::with_capacity(nc);
    for (c, o) in base.iter_mut().enumerate() {
        buf.clear();
        buf.extend(big_b.iter().map(|bf| bf[c]));
        *o = quantile(&mut buf, 0.25, MIN_SPEC);
    }
    for (phi, fam) in FAMILIES.iter().enumerate() {
        for f in 0..nc {
            let d = [
                big_b[f][fam[0]] - base[fam[0]],
                big_b[f][fam[1]] - base[fam[1]],
            ];
            x[phi * nc + f] = max_finite(&d);
        }
    }
    Spectra {
        nc,
        e,
        ant,
        x,
        alive,
    }
}

/// Pass 1 (residuals per baseline, once), the antenna and array medians of
/// u (F3's), and the spectral features.
fn prepare(inp: &Inputs, start: &[usize], order: &[usize]) -> (Vec<f32>, Spectra) {
    let ncell = inp.ntime * inp.nchan;
    let per: Vec<(Vec<f32>, Vec<f64>, bool)> = (0..inp.nbl)
        .into_par_iter()
        .map(|b| {
            let res = residuals(inp, &order[start[b]..start[b + 1]]);
            let u = u_planes(&res, ncell);
            (u, res.p, res.alive)
        })
        .collect();
    let mut u = Vec::with_capacity(inp.nbl);
    let mut p = Vec::with_capacity(inp.nbl);
    let mut alive = Vec::with_capacity(inp.nbl);
    for (ub, pb, ab) in per {
        u.push(ub);
        p.push(pb);
        alive.push(ab);
    }
    let agg = medians_of_u(inp, &u);
    drop(u);
    (agg, spectra(inp, &p, alive))
}

/// One baseline's input planes, HWC `(t, f, INPUTS)`.
fn planes(inp: &Inputs, b: usize, rows: &[usize], agg: &[f32], s: &Spectra) -> Vec<f32> {
    let nc = s.nc;
    let ncell = inp.ntime * nc;
    let nant = inp.nant;
    let h3 = f3flag::planes(inp, b, rows, agg);
    let n3 = f3flag::INPUTS;
    let mut h = vec![0f32; ncell * INPUTS];
    let (p, q) = (inp.ant1[b] as usize, inp.ant2[b] as usize);
    for cell in 0..ncell {
        let (o, o3) = (cell * INPUTS, cell * n3);
        h[o..o + n3 - 1].copy_from_slice(&h3[o3..o3 + n3 - 1]);
        h[o + INPUTS - 1] = h3[o3 + n3 - 1];
        if h3[o3 + n3 - 1] != 0.0 || !s.alive[b] {
            continue;
        }
        let f = cell % nc;
        for phi in 0..2 {
            let a = (phi * nant) * nc;
            let (mx, mn) = pair64(s.ant[a + p * nc + f], s.ant[a + q * nc + f]);
            let k = o + SPEC0 + 4 * phi;
            h[k] = f3flag::ash(s.e[b][phi * nc + f]);
            h[k + 1] = f3flag::ash(mx);
            h[k + 2] = f3flag::ash(mn);
            h[k + 3] = f3flag::ash(s.x[phi * nc + f]);
        }
    }
    h
}

/// Features `(nsel, ntime, nchan, INPUTS)` f32 of the baselines `select`
/// into `out`. Errors: 1 bad sizes, 2 an index out of range.
pub fn features(inp: &Inputs, select: &[u32], out: &mut [f32]) -> i32 {
    let code = check(inp);
    if code != 0 {
        return code;
    }
    let ncell = inp.ntime * inp.nchan;
    if out.len() != select.len() * ncell * INPUTS {
        return 1;
    }
    if select.iter().any(|&b| b as usize >= inp.nbl) {
        return 2;
    }
    let (start, order) = rows_by_baseline(inp);
    let (agg, s) = prepare(inp, &start, &order);
    out.par_chunks_mut(ncell * INPUTS)
        .zip(select.par_iter())
        .for_each(|(o, &b)| {
            let b = b as usize;
            o.copy_from_slice(&planes(inp, b, &order[start[b]..start[b + 1]], &agg, &s));
        });
    0
}

/// Logits `(row, chan)` f32 into `out`. Errors: 1 bad sizes, 2 an index out
/// of range.
pub fn logits(inp: &Inputs, weights: &[f32], out: &mut [f32]) -> i32 {
    let code = check(inp);
    if code != 0 {
        return code;
    }
    let nc = inp.nchan;
    if out.len() != inp.baseline.len() * nc || weights.len() != weight_count() {
        return 1;
    }
    let (start, order) = rows_by_baseline(inp);
    let (agg, s) = prepare(inp, &start, &order);
    let results: Vec<Vec<(usize, Vec<f32>)>> = (0..inp.nbl)
        .into_par_iter()
        .map(|b| {
            let rows = &order[start[b]..start[b + 1]];
            if rows.is_empty() {
                return Vec::new();
            }
            let h = planes(inp, b, rows, &agg, &s);
            f3flag::network(inp, rows, h, weights, INPUTS)
        })
        .collect();
    for rows in results {
        for (r, values) in rows {
            out[r * nc..(r + 1) * nc].copy_from_slice(&values);
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn weight_count_is_the_protocols() {
        assert_eq!(weight_count(), 4009);
    }

    #[test]
    fn quantile_follows_numpy() {
        // numpy.percentile([1, 2, 3, 4, 10], 25) = 2.0; [1, 2, 3, 4] -> 1.75.
        assert_eq!(quantile(&mut vec![10.0, 2.0, 1.0, 4.0, 3.0], 0.25, 1), 2.0);
        assert!((quantile(&mut vec![4.0, 3.0, 2.0, 1.0], 0.25, 1) - 1.75).abs() < 1e-15);
        assert!(quantile(&mut vec![1.0, f64::NAN], 0.25, 2).is_nan());
    }

    /// Unit noise on every baseline; on antenna 0's baselines a scan-long
    /// band of 30 channels (wider than F3's 33-channel running median can
    /// separate, half the channels) at 10 σ in all correlations. The cross
    /// spectral plane is high in the band on antenna 0's baselines only; F3's
    /// residual planes are not.
    #[test]
    fn wide_scan_long_antenna_band_shows_in_the_spectral_planes() {
        let (nc, nt, nant) = (64usize, 8usize, 6usize);
        let mut ubl = Vec::new();
        for a in 0..nant as u32 {
            for b in a + 1..nant as u32 {
                ubl.push((a, b));
            }
        }
        let nbl = ubl.len();
        let nrow = nt * nbl;
        let mut state = 12345u64;
        let mut gauss = move || {
            // Box-Muller on a 64-bit LCG.
            let mut u = || {
                state = state
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add(1442695040888963407);
                ((state >> 11) as f64 + 0.5) / (1u64 << 53) as f64
            };
            let (a, b) = (u(), u());
            (-2.0 * a.ln()).sqrt() * (2.0 * std::f64::consts::PI * b).cos()
        };
        let mut data = vec![0f32; nrow * nc * 8];
        let baseline: Vec<u32> = (0..nrow as u32).map(|r| r % nbl as u32).collect();
        let time: Vec<u32> = (0..nrow as u32).map(|r| r / nbl as u32).collect();
        for r in 0..nrow {
            let on = ubl[baseline[r] as usize].0 == 0;
            for f in 0..nc {
                for i in 0..8 {
                    let mut v = gauss();
                    if on && (20..50).contains(&f) && i % 2 == 0 {
                        v += 10.0;
                    }
                    data[(r * nc + f) * 8 + i] = v as f32;
                }
            }
        }
        let flags = vec![0u8; nrow * nc];
        let ant1: Vec<u32> = ubl.iter().map(|x| x.0).collect();
        let ant2: Vec<u32> = ubl.iter().map(|x| x.1).collect();
        let inp = Inputs {
            nchan: nc,
            nbl,
            ntime: nt,
            nant,
            data: &data,
            flags: &flags,
            baseline: &baseline,
            time: &time,
            ant1: &ant1,
            ant2: &ant2,
        };
        let select: Vec<u32> = (0..nbl as u32).collect();
        let ncell = nt * nc;
        let mut feat = vec![0f32; nbl * ncell * INPUTS];
        assert_eq!(features(&inp, &select, &mut feat), 0);
        let at =
            |b: usize, t: usize, f: usize, k: usize| feat[(b * ncell + t * nc + f) * INPUTS + k];
        // Baseline 0 is (0, 1), baseline nbl-1 is (4, 5).
        let cross_on = at(0, 3, 35, SPEC0 + 4);
        let cross_off = at(nbl - 1, 3, 35, SPEC0 + 4);
        assert!(cross_on.sinh() > 5.0, "{cross_on}");
        assert!(cross_off.sinh() < 2.0, "{cross_off}");
        // max(E_p, E_q) high, min low on (0, 1).
        assert!(at(0, 3, 35, SPEC0 + 5).sinh() > 5.0);
        assert!(at(0, 3, 35, SPEC0 + 6).sinh() < 2.0);
        // F3's channel-local residual inside the band is small.
        let rf = (4..8)
            .map(|k| at(0, 3, 35, k).sinh())
            .fold(f32::MIN, f32::max);
        assert!(rf < 4.0, "{rf}");
        let weights = vec![0.01f32; weight_count()];
        let mut out = vec![0f32; nrow * nc];
        assert_eq!(logits(&inp, &weights, &mut out), 0);
        assert!(out.iter().all(|v| v.is_finite()));
        assert_eq!(logits(&inp, &weights[1..], &mut out), 1);
    }
}
