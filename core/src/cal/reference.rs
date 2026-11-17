// SPDX-License-Identifier: GPL-3.0-or-later
// Follows CASA's C++ source in part (Copyright (C) Associated
// Universities, Inc. Washington DC, USA; (L)GPL version 2 or later):
// notices in THIRD-PARTY-NOTICES.txt.
//! CASA's rules around a gain solve (task C2a, `research/c2a-gain.md`; C1
//! step 3): `minblperant` before the solve, `minsnr` after it, and the
//! reference antenna over the finished table. Written from CASA's rules as
//! read in `SolvableVisCal.cc` (C1 section 0, the 2023 mirror); CASA is not
//! copied.
//!
//! - `minblperant_ok` (`SolvableVisCal::verifyConstraints`): per solution
//!   interval, a baseline counts for both its antennas when it has positive
//!   unflagged weight; antennas with fewer than `minblperant` baselines are
//!   eliminated recursively (their baselines stop counting for the others,
//!   and the count restarts) and their data are flagged for the solve.
//! - `snr_ok` (`applySNRThreshold`): a solution parameter stays good when its
//!   SNR is strictly above `minsnr`.
//! - `apply_refant` (`SolvableVisJones::applyRefAnt`, types G, B, T):
//!   per window and in time order, the first good choice among the user's
//!   primary refant, the refant used last, the user's other refants and then
//!   every antenna by distance from the user's last refant; "good" means an
//!   unflagged solution in every checked polarisation (both, unless the
//!   second has none in the window) in the previous referenced interval and
//!   the current one. Its phasor (amplitudes below `FLT_EPSILON` flagged and
//!   reset to 1) divides every antenna's solution; after the first interval
//!   it is first divided by the same antenna's previous referenced phasor,
//!   which keeps an alternate refant's phase continuous (`flex`). `strict`
//!   tries the primary only. Where no choice is good, every solution of the
//!   interval is flagged and the previous interval stays the reference.

use crate::jones::C64;
use crate::solve::Problem;

/// `FLT_EPSILON`.
const FLT_EPSILON: f64 = f32::EPSILON as f64;

/// Per (time bin, frequency bin, antenna), whether the antenna passes
/// CASA's `minblperant` test in that interval. A cell counts when no
/// correlation is flagged and its row is not (QuartiCal's data flags, as
/// the solver uses them, `solve::data_flags`), its antennas differ, and the
/// sum of its XX and YY weights is positive.
pub fn minblperant_ok(problem: &Problem, minblperant: usize) -> Vec<bool> {
    let (nt, nf, na) = (problem.ntime_bins, problem.nfreq_bins, problem.nant);
    let flags = crate::solve::data_flags(problem);
    // blwt[(t, f)][p * na + q] > 0: a baseline with unflagged weight.
    let mut counted = vec![false; nt * nf * na * na];
    for row in 0..problem.nrow {
        let (p, q) = (
            problem.antenna1[row] as usize,
            problem.antenna2[row] as usize,
        );
        if p == q || problem.flag_row[row] != 0 {
            continue;
        }
        let t = problem.time_bin[row] as usize;
        for chan in 0..problem.nchan {
            let cell = row * problem.nchan + chan;
            if flags[cell] {
                continue;
            }
            let w = f64::from(problem.weights[4 * cell]) + f64::from(problem.weights[4 * cell + 3]);
            if w > 0. {
                let f = problem.freq_bin[chan] as usize;
                let base = (t * nf + f) * na * na;
                counted[base + p * na + q] = true;
                counted[base + q * na + p] = true;
            }
        }
    }
    let mut ok = vec![true; nt * nf * na];
    for interval in 0..nt * nf {
        let bl = &mut counted[interval * na * na..(interval + 1) * na * na];
        let good = &mut ok[interval * na..(interval + 1) * na];
        let mut a = 0;
        while a < na {
            if good[a] {
                let nbl = (0..na).filter(|&b| bl[b * na + a]).count();
                if nbl < minblperant {
                    good[a] = false;
                    for b in 0..na {
                        bl[a * na + b] = false;
                        bl[b * na + a] = false;
                    }
                    a = 0;
                    continue;
                }
            }
            a += 1;
        }
    }
    ok
}

/// `applySNRThreshold`: `snr > minsnr` for each parameter that is good.
pub fn snr_ok(snr: &[f32], ok: &mut [bool], minsnr: f32) {
    for (s, o) in snr.iter().zip(ok.iter_mut()) {
        if *o {
            *o = *s > minsnr;
        }
    }
}

/// The reference antenna modes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Flex,
    Strict,
}

#[derive(Debug, PartialEq)]
pub struct Error(pub String);

/// The outcome of `apply_refant`: the refant used per time (-1 where none
/// was good and the interval was flagged) and whether an alternate was used.
#[derive(Debug, PartialEq)]
pub struct Referenced {
    pub refant: Vec<i32>,
    pub used_alternate: bool,
}

/// CASA's `applyRefAnt` for one window. `sol` and `flag` are
/// `(ntime, nant, npar, nchan)` row-major, times ascending, every antenna
/// present at every time; `positions` is `(nant, 3)` (ANTENNA POSITION);
/// `refants` the user's list, primary first. Modifies `sol` and `flag` in
/// place.
#[allow(clippy::too_many_arguments)]
pub fn apply_refant(
    sol: &mut [C64],
    flag: &mut [bool],
    ntime: usize,
    nant: usize,
    npar: usize,
    nchan: usize,
    positions: &[f64],
    refants: &[usize],
    mode: Mode,
) -> Result<Referenced, Error> {
    let per_time = nant * npar * nchan;
    if sol.len() != ntime * per_time || flag.len() != ntime * per_time {
        return Err(Error("solution and flag lengths".into()));
    }
    if positions.len() != 3 * nant {
        return Err(Error("positions must be (nant, 3)".into()));
    }
    if refants.is_empty() || refants.iter().any(|&r| r >= nant) {
        return Err(Error("refant list empty or out of range".into()));
    }
    if npar == 0 || npar > 2 || nchan == 0 {
        return Err(Error("npar must be 1 or 2 and nchan positive".into()));
    }
    // The choice list: primary, last used, user's others, then by distance.
    let last_user = refants[refants.len() - 1];
    let mut dist2: Vec<f64> = (0..nant)
        .map(|a| {
            (0..3)
                .map(|k| (positions[3 * a + k] - positions[3 * last_user + k]).powi(2))
                .sum()
        })
        .collect();
    for &r in refants {
        dist2[r] = f64::MAX;
    }
    let mut ord: Vec<usize> = (0..nant).collect();
    ord.sort_by(|&a, &b| dist2[a].total_cmp(&dist2[b]));
    let mut choices = vec![refants[0], refants[0]];
    choices.extend_from_slice(&refants[1..]);
    choices.extend(ord);
    if mode == Mode::Strict {
        choices.truncate(1);
    }
    // nPol: one when the second polarisation has no unflagged solution.
    let npol = if npar == 2 {
        let any =
            (0..ntime * nant).any(|ta| (0..nchan).any(|c| !flag[(ta * npar + 1) * nchan + c]));
        if any { 2 } else { 1 }
    } else {
        1
    };
    let at = |t: usize, a: usize, p: usize, c: usize| ((t * nant + a) * npar + p) * nchan + c;
    let good_in = |flag: &[bool], t: usize, a: usize| {
        (0..npol).all(|p| (0..nchan).any(|c| !flag[at(t, a, p, c)]))
    };
    // The unit phasor of antenna `a` at time `t` and its flags.
    let phasor = |sol: &[C64], flag: &[bool], t: usize, a: usize| {
        let mut r = vec![C64::ZERO; npar * nchan];
        let mut rf = vec![false; npar * nchan];
        for p in 0..npar {
            for c in 0..nchan {
                let (v, f) = (sol[at(t, a, p, c)], flag[at(t, a, p, c)]);
                let amp = v.re.hypot(v.im);
                let f = f || amp < FLT_EPSILON;
                let (v, amp) = if f { (C64::new(1., 0.), 1.) } else { (v, amp) };
                r[p * nchan + c] = C64::new(v.re / amp, v.im / amp);
                rf[p * nchan + c] = f;
            }
        }
        (r, rf)
    };
    let mut refant_used = vec![-1i32; ntime];
    let mut used_alternate = false;
    let mut previous: Option<usize> = None;
    for t in 0..ntime {
        let a_time = previous.unwrap_or(t);
        let found = choices
            .iter()
            .position(|&c| good_in(flag, a_time, c) && good_in(flag, t, c));
        match found {
            Some(ichoice) => {
                let current = choices[ichoice];
                used_alternate |= ichoice > 0;
                if choices.len() > 1 {
                    choices[1] = current;
                }
                let (mut rb, _) = phasor(sol, flag, t, current);
                if let Some(ta) = previous {
                    let (ra, _) = phasor(sol, flag, ta, current);
                    for (b, a) in rb.iter_mut().zip(&ra) {
                        *b = divide(*b, *a);
                    }
                }
                for a in 0..nant {
                    for p in 0..npar {
                        for c in 0..nchan {
                            let i = at(t, a, p, c);
                            sol[i] = divide(sol[i], rb[p * nchan + c]);
                        }
                    }
                }
                refant_used[t] = current as i32;
                previous = Some(t);
            }
            None => {
                for v in &mut flag[t * per_time..(t + 1) * per_time] {
                    *v = true;
                }
            }
        }
    }
    Ok(Referenced {
        refant: refant_used,
        used_alternate,
    })
}

/// `a / b` as `std::complex` divides (the straightforward formula; the
/// phasors have unit modulus).
fn divide(a: C64, b: C64) -> C64 {
    let d = b.re * b.re + b.im * b.im;
    C64::new(
        (a.re * b.re + a.im * b.im) / d,
        (a.im * b.re - a.re * b.im) / d,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn phase(v: C64) -> f64 {
        v.im.atan2(v.re)
    }

    /// 3 times, 4 antennas, 2 pars, 1 chan; antenna `a` has phase
    /// `0.1 * (a + 1) * (t + 1)` in both pars.
    fn table() -> (Vec<C64>, Vec<bool>) {
        let mut sol = Vec::new();
        for t in 0..3 {
            for a in 0..4 {
                for _p in 0..2 {
                    let ph = 0.1 * (a + 1) as f64 * (t + 1) as f64;
                    sol.push(C64::new(2. * ph.cos(), 2. * ph.sin()));
                }
            }
        }
        let flag = vec![false; sol.len()];
        (sol, flag)
    }

    const POS: [f64; 12] = [0., 0., 0., 10., 0., 0., 20., 0., 0., 5., 0., 0.];

    #[test]
    fn primary_refant_has_zero_phase_and_amplitudes_stay() {
        let (mut sol, mut flag) = table();
        let out = apply_refant(&mut sol, &mut flag, 3, 4, 2, 1, &POS, &[1], Mode::Flex).unwrap();
        assert_eq!(out.refant, vec![1, 1, 1]);
        assert!(!out.used_alternate);
        for t in 0..3 {
            assert!(phase(sol[(t * 4 + 1) * 2]).abs() < 1e-12);
            for a in 0..4 {
                let v = sol[(t * 4 + a) * 2];
                assert!((v.re.hypot(v.im) - 2.).abs() < 1e-12);
                let want = 0.1 * (a as f64 - 1.) * (t + 1) as f64;
                assert!((phase(v) - want).abs() < 1e-12);
            }
        }
    }

    #[test]
    fn flex_holds_the_alternate_and_strict_flags() {
        for mode in [Mode::Flex, Mode::Strict] {
            let (mut sol, mut flag) = table();
            // The primary (0) is flagged at time 1.
            flag[2] = false;
            flag[(4) * 2] = true;
            flag[(4) * 2 + 1] = true;
            let out = apply_refant(&mut sol, &mut flag, 3, 4, 2, 1, &POS, &[0], mode).unwrap();
            match mode {
                Mode::Flex => {
                    // Nearest to antenna 0 is antenna 3 (5 m).
                    assert_eq!(out.refant, vec![0, 3, 3]);
                    assert!(out.used_alternate);
                    // Antenna 3 keeps its time-0 referenced phase (0.3).
                    let v = sol[(4 + 3) * 2];
                    assert!((phase(v) - 0.3).abs() < 1e-12, "{}", phase(v));
                }
                Mode::Strict => {
                    // Time 1 is flagged; time 2 cannot use time 1 as its
                    // previous interval, so it connects to time 0 again.
                    assert_eq!(out.refant, vec![0, -1, 0]);
                    assert!(flag[4 * 2..8 * 2].iter().all(|&f| f));
                    assert!(phase(sol[8 * 2]).abs() < 1e-12);
                }
            }
        }
    }

    #[test]
    fn minblperant_eliminates_recursively() {
        // 4 antennas, one time, one channel: baselines 0-1, 0-2, 1-2, 2-3.
        let (a1, a2) = (vec![0u32, 0, 1, 2], vec![1u32, 2, 2, 3]);
        let nrow = a1.len();
        let data = vec![1f32; nrow * 8];
        let weights = vec![1f32; nrow * 4];
        let flag = vec![0u8; nrow * 4];
        let flag_row = vec![0u8; nrow];
        let tb = vec![0u32; nrow];
        let fb = vec![0u32];
        let model = vec![1f32; nrow * 8];
        let problem = Problem {
            nrow,
            nchan: 1,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 4,
            data: &data,
            weights: &weights,
            model: crate::fused::Model::Stored(&model),
            flag: &flag,
            flag_row: &flag_row,
            antenna1: &a1,
            antenna2: &a2,
            time_bin: &tb,
            freq_bin: &fb,
        };
        assert_eq!(minblperant_ok(&problem, 1), vec![true; 4]);
        assert_eq!(minblperant_ok(&problem, 2), vec![true, true, true, false]);
        // With 3, antenna 3 goes, then 2 has two baselines left and goes,
        // then 0 and 1 have one each.
        assert_eq!(minblperant_ok(&problem, 3), vec![false; 4]);
    }

    #[test]
    fn snr_threshold_is_strict() {
        let mut ok = vec![true, true, false];
        snr_ok(&[3., 3.5, 10.], &mut ok, 3.);
        assert_eq!(ok, vec![false, true, false]);
    }
}
