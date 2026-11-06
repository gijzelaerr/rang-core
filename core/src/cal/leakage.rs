//! The leakage term Df (task C6, `research/c6-polterms.md`; C1 term T11,
//! `research/c1-calibration-chain.md` section 1.4).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! CASA's `polcal(poltype='Df')` fits CASA's linearised D (`Jones::GenLinear`;
//! the parallel hands get weight 0 in `DJones::guessPar`) to the cross hands
//! by `VisCalSolver2`. The model is linear in the leakages:
//!
//! ```text
//! V_XY - M_XY = d_x,p M_YY + conj(d_y,q) M_XX
//! V_YX - M_YX = d_y,p M_XX + conj(d_x,q) M_YY
//! ```
//!
//! (`M` the model corrupted by the higher terms and P), so this module solves
//! the weighted least-squares problem directly, per solution interval and
//! channel: real normal equations over `(Re, Im)` of `d_x`, `d_y` of every
//! antenna, accumulated over unflagged, non-autocorrelation cross-hand cells
//! with positive weight, and solved by Cholesky. Written from the equations;
//! no CASA or QuartiCal code is copied.
//!
//! - **Gauge.** When `M_XX = M_YY` in every cell (an unpolarised calibrator,
//!   CARACal's strategy 1) the cost is unchanged by `d_x -> d_x + z`,
//!   `d_y -> d_y - conj(z)` for all antennas. CASA then references the
//!   solution subtractively (`SolvableVisJones::applyRefAnt`, case D:
//!   `d_x,p -= d_x,r`, `d_y,p += conj(d_x,r)`), which removes exactly that
//!   freedom; solving with `d_x,r = 0` held fixed gives the same referenced
//!   values. With `gauge` set, the first antenna of `refants` that keeps data
//!   in the channel has its `d_x` fixed at 0; the antenna used is returned.
//!   Without it every parameter is free and the caller references. More
//!   generally the cost is unchanged by `d_x -> d_x + z`, `d_y -> d_y -
//!   conj(z) rho` whenever `rho = M_YY / M_XX` is the same real number in
//!   every cell, so a polarised calibrator needs a rotating model
//!   (parallactic coverage); `rang.cal_pol.df` refuses a constant `rho != 1`.
//! - **`minblperant`** (`verifyConstraints`): per interval and channel, an
//!   antenna is used only if it has at least `minblperant` baselines with a
//!   usable cross-hand cell to other used antennas; eliminations repeat until
//!   none changes. Eliminated antennas are flagged.
//! - **Errors.** The covariance of the free parameters is `N^-1` (exact for
//!   weights `1/sigma^2`); returned per parameter as the variances of the
//!   real and imaginary parts, with the interval's `chi2` and its number of
//!   real equations, so that the caller can scale them.
//!
//! Channels are solved in parallel, each accumulating its rows in a fixed
//! order, so the result does not depend on the thread count.

use rayon::prelude::*;

/// One Df solve's inputs (see `crosshand::Problem` for the layouts).
pub struct Problem<'a> {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime: usize,
    pub nant: usize,
    pub data: &'a [f32],
    pub model: &'a [f32],
    pub weight: &'a [f32],
    pub flag: &'a [u8],
    pub flag_row: &'a [u8],
    pub antenna1: &'a [u32],
    pub antenna2: &'a [u32],
    pub time_bin: &'a [u32],
}

pub struct Settings<'a> {
    pub minblperant: usize,
    /// Fix the gauge (`d_x = 0`) on the first usable of `refants`.
    pub gauge: bool,
    pub refants: &'a [usize],
}

/// Per `(interval, chan, ant, 2)`: `d` (re, im interleaved), flags,
/// variances of the real and imaginary parts; per `(interval, chan)` the
/// chi-squared, the number of real equations and of free parameters, and
/// the gauge antenna (-1: none).
pub struct Solution {
    pub d: Vec<f64>,
    pub flag: Vec<bool>,
    pub var_re: Vec<f64>,
    pub var_im: Vec<f64>,
    pub chi2: Vec<f64>,
    pub neq: Vec<u64>,
    pub npar: Vec<u64>,
    pub gauge_antenna: Vec<i64>,
}

fn check(p: &Problem) -> Result<(), String> {
    let cells = p.nrow.checked_mul(p.nchan).ok_or("cell count overflows")?;
    if p.data.len() != 8 * cells || p.model.len() != 8 * cells {
        return Err("data and model must be (row, chan, 4) complex64".into());
    }
    if p.weight.len() != 4 * cells || p.flag.len() != 4 * cells {
        return Err("weight and flag must be (row, chan, 4)".into());
    }
    if p.flag_row.len() != p.nrow
        || p.antenna1.len() != p.nrow
        || p.antenna2.len() != p.nrow
        || p.time_bin.len() != p.nrow
    {
        return Err("flag_row, antenna1, antenna2 and time_bin need one value per row".into());
    }
    if p.time_bin.iter().any(|&t| t as usize >= p.ntime) {
        return Err("time_bin out of range".into());
    }
    if p.antenna1
        .iter()
        .chain(p.antenna2)
        .any(|&a| a as usize >= p.nant)
    {
        return Err("antenna index out of range".into());
    }
    Ok(())
}

fn c(v: &[f32], i: usize) -> (f64, f64) {
    (f64::from(v[2 * i]), f64::from(v[2 * i + 1]))
}

/// The real equation rows of one cross-hand cell: up to four
/// `(parameter index, coefficient)` pairs and the right-hand side, for the
/// real and the imaginary part. Parameters of antenna `a`: `4a` Re d_x,
/// `4a + 1` Im d_x, `4a + 2` Re d_y, `4a + 3` Im d_y.
type Row = ([(usize, f64); 4], f64);

fn equations(
    hand: usize,
    p: usize,
    q: usize,
    mxx: (f64, f64),
    myy: (f64, f64),
    y: (f64, f64),
) -> [Row; 2] {
    let (b_r, b_i) = mxx;
    let (a_r, a_i) = myy;
    if hand == 0 {
        // XY: d_x,p M_YY + conj(d_y,q) M_XX.
        [
            (
                [
                    (4 * p, a_r),
                    (4 * p + 1, -a_i),
                    (4 * q + 2, b_r),
                    (4 * q + 3, b_i),
                ],
                y.0,
            ),
            (
                [
                    (4 * p, a_i),
                    (4 * p + 1, a_r),
                    (4 * q + 2, b_i),
                    (4 * q + 3, -b_r),
                ],
                y.1,
            ),
        ]
    } else {
        // YX: d_y,p M_XX + conj(d_x,q) M_YY.
        [
            (
                [
                    (4 * p + 2, b_r),
                    (4 * p + 3, -b_i),
                    (4 * q, a_r),
                    (4 * q + 1, a_i),
                ],
                y.0,
            ),
            (
                [
                    (4 * p + 2, b_i),
                    (4 * p + 3, b_r),
                    (4 * q, a_i),
                    (4 * q + 1, -a_r),
                ],
                y.1,
            ),
        ]
    }
}

/// In-place Cholesky of the `n x n` row-major SPD matrix; false if not
/// positive definite.
fn cholesky(a: &mut [f64], n: usize) -> bool {
    for j in 0..n {
        let mut d = a[j * n + j];
        for k in 0..j {
            d -= a[j * n + k] * a[j * n + k];
        }
        if d <= 0.0 || !d.is_finite() {
            return false;
        }
        let d = d.sqrt();
        a[j * n + j] = d;
        for i in j + 1..n {
            let mut s = a[i * n + j];
            for k in 0..j {
                s -= a[i * n + k] * a[j * n + k];
            }
            a[i * n + j] = s / d;
        }
    }
    true
}

fn cholesky_solve(l: &[f64], n: usize, b: &mut [f64]) {
    for i in 0..n {
        let mut s = b[i];
        for k in 0..i {
            s -= l[i * n + k] * b[k];
        }
        b[i] = s / l[i * n + i];
    }
    for i in (0..n).rev() {
        let mut s = b[i];
        for k in i + 1..n {
            s -= l[k * n + i] * b[k];
        }
        b[i] = s / l[i * n + i];
    }
}

struct ChanOut {
    d: Vec<[f64; 4]>,
    ok: Vec<bool>,
    var: Vec<[f64; 4]>,
    chi2: f64,
    neq: u64,
    npar: u64,
    gauge: i64,
}

fn solve_channel(p: &Problem, s: &Settings, rows: &[usize], chan: usize) -> ChanOut {
    let na = p.nant;
    let nchan = p.nchan;
    // Usable cross-hand cells per row (XY, YX).
    let usable = |r: usize, h: usize| -> bool {
        let cell = r * nchan + chan;
        let k = 1 + h;
        p.flag[4 * cell + k] == 0 && p.weight[4 * cell + k] > 0.0
    };
    // minblperant, iterated.
    let mut used = vec![true; na];
    loop {
        let mut count = vec![0usize; na];
        for &r in rows {
            let (a, b) = (p.antenna1[r] as usize, p.antenna2[r] as usize);
            if used[a] && used[b] && (usable(r, 0) || usable(r, 1)) {
                count[a] += 1;
                count[b] += 1;
            }
        }
        let mut changed = false;
        for a in 0..na {
            if used[a] && count[a] < s.minblperant.max(1) {
                used[a] = false;
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }
    let gauge: i64 = if s.gauge {
        s.refants
            .iter()
            .copied()
            .find(|&r| r < na && used[r])
            .map_or(-1, |r| r as i64)
    } else {
        -1
    };
    // Free parameters: those of used antennas, minus the gauge antenna's d_x.
    let mut index = vec![usize::MAX; 4 * na];
    let mut n = 0;
    for a in 0..na {
        if !used[a] {
            continue;
        }
        for k in 0..4 {
            if gauge == a as i64 && k < 2 {
                continue;
            }
            index[4 * a + k] = n;
            n += 1;
        }
    }
    let mut out = ChanOut {
        d: vec![[0.0; 4]; na],
        ok: vec![false; na],
        var: vec![[0.0; 4]; na],
        chi2: 0.0,
        neq: 0,
        npar: n as u64,
        gauge,
    };
    if n == 0 || (s.gauge && gauge < 0) {
        return out;
    }
    let mut nm = vec![0f64; n * n];
    let mut rhs = vec![0f64; n];
    let mut yy = 0f64;
    for &r in rows {
        let (a, b) = (p.antenna1[r] as usize, p.antenna2[r] as usize);
        if !(used[a] && used[b]) {
            continue;
        }
        let cell = r * nchan + chan;
        let mxx = c(p.model, 4 * cell);
        let myy = c(p.model, 4 * cell + 3);
        for h in 0..2 {
            if !usable(r, h) {
                continue;
            }
            let k = 1 + h;
            let v = c(p.data, 4 * cell + k);
            let m = c(p.model, 4 * cell + k);
            let y = (v.0 - m.0, v.1 - m.1);
            let w = f64::from(p.weight[4 * cell + k]);
            for (coef, rhs_v) in equations(h, a, b, mxx, myy, y) {
                out.neq += 1;
                yy += w * rhs_v * rhs_v;
                for &(i, ci) in &coef {
                    let ii = index[i];
                    if ii == usize::MAX {
                        continue;
                    }
                    rhs[ii] += w * ci * rhs_v;
                    for &(j, cj) in &coef {
                        let jj = index[j];
                        if jj != usize::MAX {
                            nm[ii * n + jj] += w * ci * cj;
                        }
                    }
                }
            }
        }
    }
    let rhs0 = rhs.clone();
    if !cholesky(&mut nm, n) {
        return out;
    }
    let mut x = rhs;
    cholesky_solve(&nm, n, &mut x);
    // chi2 = y'Wy - x'b at the least-squares solution.
    let xb: f64 = x.iter().zip(&rhs0).map(|(a, b)| a * b).sum();
    out.chi2 = (yy - xb).max(0.0);
    // Diagonal of N^-1.
    let mut diag = vec![0f64; n];
    let mut e = vec![0f64; n];
    for (i, d) in diag.iter_mut().enumerate() {
        e.iter_mut().for_each(|v| *v = 0.0);
        e[i] = 1.0;
        cholesky_solve(&nm, n, &mut e);
        *d = e[i];
    }
    for a in 0..na {
        if !used[a] {
            continue;
        }
        out.ok[a] = true;
        for k in 0..4 {
            let i = index[4 * a + k];
            if i != usize::MAX {
                out.d[a][k] = x[i];
                out.var[a][k] = diag[i];
            }
        }
    }
    out
}

/// Solve Df per interval and channel.
pub fn solve(p: &Problem, s: &Settings) -> Result<Solution, String> {
    check(p)?;
    let (nt, nc, na) = (p.ntime, p.nchan, p.nant);
    let mut rows = vec![Vec::new(); nt];
    for r in 0..p.nrow {
        if p.flag_row[r] == 0 && p.antenna1[r] != p.antenna2[r] {
            rows[p.time_bin[r] as usize].push(r);
        }
    }
    let jobs: Vec<(usize, usize)> = (0..nt).flat_map(|t| (0..nc).map(move |c| (t, c))).collect();
    let outs: Vec<ChanOut> = jobs
        .par_iter()
        .map(|&(t, c)| solve_channel(p, s, &rows[t], c))
        .collect();
    let mut sol = Solution {
        d: vec![0.0; nt * nc * na * 4],
        flag: vec![true; nt * nc * na * 2],
        var_re: vec![0.0; nt * nc * na * 2],
        var_im: vec![0.0; nt * nc * na * 2],
        chi2: vec![0.0; nt * nc],
        neq: vec![0; nt * nc],
        npar: vec![0; nt * nc],
        gauge_antenna: vec![-1; nt * nc],
    };
    for (j, o) in outs.iter().enumerate() {
        sol.chi2[j] = o.chi2;
        sol.neq[j] = o.neq;
        sol.npar[j] = o.npar;
        sol.gauge_antenna[j] = o.gauge;
        for a in 0..na {
            let base = j * na + a;
            for h in 0..2 {
                sol.d[4 * base + 2 * h] = o.d[a][2 * h];
                sol.d[4 * base + 2 * h + 1] = o.d[a][2 * h + 1];
                sol.flag[2 * base + h] = !o.ok[a];
                sol.var_re[2 * base + h] = o.var[a][2 * h];
                sol.var_im[2 * base + h] = o.var[a][2 * h + 1];
            }
        }
    }
    Ok(sol)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Lcg(u64);
    impl Lcg {
        fn next(&mut self) -> f64 {
            self.0 = self
                .0
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((self.0 >> 11) as f64) / ((1u64 << 53) as f64) - 0.5
        }
    }

    struct Sim {
        data: Vec<f32>,
        model: Vec<f32>,
        weight: Vec<f32>,
        flag: Vec<u8>,
        flag_row: Vec<u8>,
        a1: Vec<u32>,
        a2: Vec<u32>,
        tb: Vec<u32>,
        d: Vec<[(f64, f64); 2]>,
    }

    fn cmul(a: (f64, f64), b: (f64, f64)) -> (f64, f64) {
        (a.0 * b.0 - a.1 * b.1, a.0 * b.1 + a.1 * b.0)
    }
    fn conj(a: (f64, f64)) -> (f64, f64) {
        (a.0, -a.1)
    }

    /// `nant` antennas, `nchan` channels, `ntime` integrations; model I = 2
    /// and Stokes Q = q cos(0.7 r) per row r (0: unpolarised; a rotating
    /// Q breaks the gauge), U = 0.3 in the cross hands.
    fn sim(nant: usize, nchan: usize, ntime: usize, q: f64, seed: u64) -> Sim {
        let mut rng = Lcg(seed);
        let d: Vec<[(f64, f64); 2]> = (0..nant)
            .map(|_| {
                [
                    (0.04 * rng.next(), 0.04 * rng.next()),
                    (0.04 * rng.next(), 0.04 * rng.next()),
                ]
            })
            .collect();
        let (mut a1, mut a2) = (Vec::new(), Vec::new());
        for _ in 0..ntime {
            for p in 0..nant {
                for qq in p + 1..nant {
                    a1.push(p as u32);
                    a2.push(qq as u32);
                }
            }
        }
        let nrow = a1.len();
        let (mut data, mut model) = (Vec::new(), Vec::new());
        for r in 0..nrow {
            let (p, qa) = (a1[r] as usize, a2[r] as usize);
            for _ in 0..nchan {
                let qr = q * (0.7 * r as f64).cos();
                let m = [(2.0 + qr, 0.0), (0.3, 0.0), (0.3, 0.0), (2.0 - qr, 0.0)];
                let mut v = m;
                let xy = cmul(d[p][0], m[3]);
                let xy2 = cmul(conj(d[qa][1]), m[0]);
                v[1] = (m[1].0 + xy.0 + xy2.0, m[1].1 + xy.1 + xy2.1);
                let yx = cmul(d[p][1], m[0]);
                let yx2 = cmul(conj(d[qa][0]), m[3]);
                v[2] = (m[2].0 + yx.0 + yx2.0, m[2].1 + yx.1 + yx2.1);
                for k in 0..4 {
                    data.extend([v[k].0 as f32, v[k].1 as f32]);
                    model.extend([m[k].0 as f32, m[k].1 as f32]);
                }
            }
        }
        Sim {
            weight: vec![1.0; 4 * nrow * nchan],
            flag: vec![0; 4 * nrow * nchan],
            flag_row: vec![0; nrow],
            tb: vec![0; nrow],
            data,
            model,
            a1,
            a2,
            d,
        }
    }

    fn problem(s: &Sim, nant: usize, nchan: usize) -> Problem<'_> {
        Problem {
            nrow: s.a1.len(),
            nchan,
            ntime: 1,
            nant,
            data: &s.data,
            model: &s.model,
            weight: &s.weight,
            flag: &s.flag,
            flag_row: &s.flag_row,
            antenna1: &s.a1,
            antenna2: &s.a2,
            time_bin: &s.tb,
        }
    }

    #[test]
    fn unpolarised_recovers_casa_referenced_leakages() {
        let (na, nc) = (7, 3);
        let s = sim(na, nc, 2, 0.0, 11);
        let sol = solve(
            &problem(&s, na, nc),
            &Settings {
                minblperant: 4,
                gauge: true,
                refants: &[2],
            },
        )
        .unwrap();
        let r = 2;
        for c in 0..nc {
            assert_eq!(sol.gauge_antenna[c], 2);
            for a in 0..na {
                let base = c * na + a;
                // CASA's referenced truth: d_x - d_x,r and d_y + conj(d_x,r).
                let want_x = (s.d[a][0].0 - s.d[r][0].0, s.d[a][0].1 - s.d[r][0].1);
                let want_y = (s.d[a][1].0 + s.d[r][0].0, s.d[a][1].1 - s.d[r][0].1);
                let got_x = (sol.d[4 * base], sol.d[4 * base + 1]);
                let got_y = (sol.d[4 * base + 2], sol.d[4 * base + 3]);
                for (g, w) in [(got_x, want_x), (got_y, want_y)] {
                    assert!(
                        (g.0 - w.0).abs() < 1e-6 && (g.1 - w.1).abs() < 1e-6,
                        "{a} {g:?} {w:?}"
                    );
                }
                assert!(!sol.flag[2 * base]);
            }
        }
    }

    #[test]
    fn polarised_recovers_the_raw_leakages_without_a_gauge() {
        let (na, nc) = (6, 2);
        let s = sim(na, nc, 1, 0.4, 3);
        let sol = solve(
            &problem(&s, na, nc),
            &Settings {
                minblperant: 4,
                gauge: false,
                refants: &[0],
            },
        )
        .unwrap();
        for a in 0..na {
            for h in 0..2 {
                let got = (sol.d[4 * a + 2 * h], sol.d[4 * a + 2 * h + 1]);
                let want = s.d[a][h];
                assert!((got.0 - want.0).abs() < 1e-5 && (got.1 - want.1).abs() < 1e-5);
            }
        }
    }

    #[test]
    fn minblperant_flags_an_antenna_with_too_few_baselines() {
        let (na, nc) = (6, 1);
        let mut s = sim(na, nc, 1, 0.0, 5);
        // Antenna 5 keeps only its baselines to 0, 1, 2 (three).
        for r in 0..s.a1.len() {
            let (p, q) = (s.a1[r], s.a2[r]);
            if (p == 5 || q == 5) && ![0, 1, 2].contains(&(if p == 5 { q } else { p })) {
                s.flag_row[r] = 1;
            }
        }
        let sol = solve(
            &problem(&s, na, nc),
            &Settings {
                minblperant: 4,
                gauge: true,
                refants: &[0],
            },
        )
        .unwrap();
        assert!(sol.flag[2 * 5] && sol.flag[2 * 5 + 1]);
        assert!(!sol.flag[0]);
    }

    #[test]
    fn threads_are_bit_identical() {
        let (na, nc) = (8, 4);
        let s = sim(na, nc, 2, 0.0, 9);
        let st = Settings {
            minblperant: 4,
            gauge: true,
            refants: &[0],
        };
        let one = rayon::ThreadPoolBuilder::new()
            .num_threads(1)
            .build()
            .unwrap();
        let a = one.install(|| solve(&problem(&s, na, nc), &st).unwrap());
        let b = solve(&problem(&s, na, nc), &st).unwrap();
        assert_eq!(a.d, b.d);
        assert_eq!(a.var_re, b.var_re);
    }
}
