//! The cross-hand terms KCROSS (cross-hand delay) and Xf (cross-hand phase)
//! (task C6, `research/c6-polterms.md`; C1 terms T9 and T10,
//! `research/c1-calibration-chain.md` section 1.4).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Written from CASA's equations (`KcrossJones::solveOneSDB` and
//! `XJones::solveOne`, read in the 2023 mirror for this task); no code is
//! copied. Both terms are one value for the array and both are normalisable
//! in CASA, so the data are first divided by the model per cell and
//! correlation and the weight multiplied by `|M|^2`
//! (`VisEquation::divideCorrByModel`): a flagged cell gets data and weight
//! 0, a cell whose model is 0 is left undivided with its weight. Then, per
//! solution interval (rows grouped by `time_bin`), over rows that are not
//! flagged and not autocorrelations:
//!
//! - **KCROSS:** per channel `S = (sum w_XY V_XY + conj(sum w_YX V_YX)) /
//!   (sum w_XY + sum w_YX)`, each cross hand counted where it is unflagged
//!   (0 where the sum of weights is 0); `S` zero-padded to `8 nchan` points
//!   and Fourier transformed; the peak of `|FFT|` (the first maximum in
//!   centred order) refined by a parabola through it and its neighbours
//!   (not at the edges); `tau = (k - n/2) / n / dnu` in ns, with `dnu =
//!   freq[1] - freq[0]`, positive when the phase of `V_XY` rises with
//!   frequency. One delay per interval, the X parameter of every antenna.
//! - **Xf:** per channel, over cells where both cross hands are unflagged,
//!   `wt = (w_XY + w_YX) / 2`, `rl += wt V_XY`, `lr += wt V_YX` (each only
//!   where its normalised datum is not 0), `x = (rl + conj(lr)) / |rl +
//!   conj(lr)|`; a channel is solved when the interval's total weight
//!   (both hands, all channels) is positive and the amplitude is positive.
//!
//! The errors are rang's (CASA writes none it uses): for KCROSS the
//! weighted least-squares delay error of the channel phases of `S`
//! (`var(arg S_nu) = 1 / (W_nu |S_nu|^2)`, `W_nu` the channel's summed
//! weight; exact for weights `1/sigma^2`), for Xf the phase error
//! `sqrt(var / 2) / |rl + conj(lr)|` with `var = sum 2 wt^2 / w` per hand.
//! Accumulation is in float64, per interval in a fixed row order, so the
//! result does not depend on the thread count.

use rayon::prelude::*;
use rustfft::FftPlanner;
use rustfft::num_complex::Complex;

type C64 = Complex<f64>;

/// One solve's inputs: rows grouped by interval are not required.
pub struct Problem<'a> {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime: usize,
    /// Interleaved complex64 `(row, chan, 4)`: data with the lower terms
    /// corrected, and the model with the higher terms (and P) applied.
    pub data: &'a [f32],
    pub model: &'a [f32],
    /// `(row, chan, 4)`.
    pub weight: &'a [f32],
    /// `(row, chan, 4)`, 0 or 1.
    pub flag: &'a [u8],
    /// Per row, 0 or 1.
    pub flag_row: &'a [u8],
    pub antenna1: &'a [u32],
    pub antenna2: &'a [u32],
    /// Per row, the solution interval.
    pub time_bin: &'a [u32],
    /// Channel frequencies (Hz).
    pub freq: &'a [f64],
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
    if p.freq.len() != p.nchan {
        return Err("freq must have one value per channel".into());
    }
    if p.time_bin.iter().any(|&t| t as usize >= p.ntime) {
        return Err("time_bin out of range".into());
    }
    Ok(())
}

/// The normalised cross hands of one cell: `(V_XY, w_XY, ok_XY)` and the
/// same for YX, as `divideCorrByModel` leaves them.
fn normalised(p: &Problem, cell: usize) -> [(C64, f64, bool); 2] {
    std::array::from_fn(|h| {
        let k = 1 + h;
        let flagged = p.flag[4 * cell + k] != 0;
        if flagged {
            return (C64::new(0.0, 0.0), 0.0, false);
        }
        let v = C64::new(
            f64::from(p.data[8 * cell + 2 * k]),
            f64::from(p.data[8 * cell + 2 * k + 1]),
        );
        let m = C64::new(
            f64::from(p.model[8 * cell + 2 * k]),
            f64::from(p.model[8 * cell + 2 * k + 1]),
        );
        let w = f64::from(p.weight[4 * cell + k]);
        let a = m.norm();
        if a > 0.0 {
            (v / m, w * a * a, true)
        } else {
            (v, w, true)
        }
    })
}

fn rows_by_interval(p: &Problem) -> Vec<Vec<usize>> {
    let mut rows = vec![Vec::new(); p.ntime];
    for r in 0..p.nrow {
        if p.flag_row[r] == 0 && p.antenna1[r] != p.antenna2[r] {
            rows[p.time_bin[r] as usize].push(r);
        }
    }
    rows
}

/// One KCROSS solution: the delay (ns), whether any data entered, rang's
/// error (ns, 0 when not defined), and the normalised summed spectrum.
#[derive(Clone, Debug)]
pub struct KcrossSolution {
    pub delay_ns: f64,
    pub ok: bool,
    pub err_ns: f64,
    pub spectrum: Vec<C64>,
    pub sumwt: Vec<f64>,
}

/// CASA's KCROSS estimator per interval.
pub fn kcross(p: &Problem) -> Result<Vec<KcrossSolution>, String> {
    check(p)?;
    if p.nchan < 2 {
        return Err("KCROSS needs at least two channels".into());
    }
    let rows = rows_by_interval(p);
    let nchan = p.nchan;
    let df = p.freq[1] - p.freq[0];
    Ok(rows
        .par_iter()
        .map(|rows| {
            let mut s = vec![C64::new(0.0, 0.0); nchan];
            let mut sw = vec![0f64; nchan];
            for &r in rows {
                for c in 0..nchan {
                    let [(v1, w1, ok1), (v2, w2, ok2)] = normalised(p, r * nchan + c);
                    if ok1 {
                        s[c] += v1 * w1;
                        sw[c] += w1;
                    }
                    if ok2 {
                        s[c] += (v2 * w2).conj();
                        sw[c] += w2;
                    }
                }
            }
            for (v, &w) in s.iter_mut().zip(&sw) {
                *v = if w > 0.0 { *v / w } else { C64::new(0.0, 0.0) };
            }
            let ok = sw.iter().any(|&w| w > 0.0);
            let (delay_ns, err_ns) = if ok {
                (fft_peak_delay(&s, df), delay_error(&s, &sw, p.freq))
            } else {
                (0.0, 0.0)
            };
            KcrossSolution {
                delay_ns,
                ok,
                err_ns,
                spectrum: s,
                sumwt: sw,
            }
        })
        .collect())
}

/// The delay (ns) of the peak of the 8x zero-padded FFT of `s` (channels
/// spaced `df` Hz), refined by a parabola, as `KcrossJones::solveOneSDB`.
pub fn fft_peak_delay(s: &[C64], df: f64) -> f64 {
    let nchan = s.len();
    let n = 8 * nchan;
    let mut buf = vec![C64::new(0.0, 0.0); n];
    buf[..nchan].copy_from_slice(s);
    let mut planner = FftPlanner::<f64>::new();
    planner.plan_fft_forward(n).process(&mut buf);
    // Centred order: index i holds frequency i - n/2.
    let amp: Vec<f64> = (0..n).map(|i| buf[(i + n - n / 2) % n].norm()).collect();
    let (mut ipk, mut amax) = (0usize, 0f64);
    for (i, &a) in amp.iter().enumerate() {
        if a > amax {
            ipk = i;
            amax = a;
        }
    }
    let mut fipk = ipk as f64;
    if ipk > 0 && ipk < n - 1 {
        let (a0, a1, a2) = (amp[ipk - 1], amp[ipk], amp[ipk + 1]);
        let den = a0 - 2.0 * a1 + a2;
        if den != 0.0 {
            fipk = ipk as f64 + 0.5 - (a2 - a1) / den;
        }
    }
    let cycles = (fipk - (n / 2) as f64) / n as f64;
    cycles / df / 1e-9
}

fn delay_error(s: &[C64], sw: &[f64], freq: &[f64]) -> f64 {
    // Weighted least squares of phase on frequency: weight 1/var(arg S).
    let mut w = Vec::with_capacity(s.len());
    for (v, &sumw) in s.iter().zip(sw) {
        w.push(sumw * v.norm_sqr());
    }
    let wsum: f64 = w.iter().sum();
    if wsum <= 0.0 {
        return 0.0;
    }
    let mean = w.iter().zip(freq).map(|(a, f)| a * f).sum::<f64>() / wsum;
    let s2: f64 = w
        .iter()
        .zip(freq)
        .map(|(a, f)| a * (f - mean) * (f - mean))
        .sum();
    if s2 <= 0.0 {
        return 0.0;
    }
    1.0 / (std::f64::consts::TAU * s2.sqrt()) / 1e-9
}

/// One Xf solution per interval: `x` per channel (1 where not solved),
/// whether each channel is solved, and rang's phase error (rad).
#[derive(Clone, Debug)]
pub struct XfSolution {
    pub x: Vec<C64>,
    pub ok: Vec<bool>,
    pub err: Vec<f64>,
}

/// CASA's Xf estimator per interval.
pub fn xf(p: &Problem) -> Result<Vec<XfSolution>, String> {
    check(p)?;
    let rows = rows_by_interval(p);
    let nchan = p.nchan;
    Ok(rows
        .par_iter()
        .map(|rows| {
            let mut rl = vec![C64::new(0.0, 0.0); nchan];
            let mut lr = vec![C64::new(0.0, 0.0); nchan];
            let mut var = vec![0f64; nchan];
            let mut sumwt = 0f64;
            for &r in rows {
                for c in 0..nchan {
                    let [(v1, w1, ok1), (v2, w2, ok2)] = normalised(p, r * nchan + c);
                    if !(ok1 && ok2) {
                        continue;
                    }
                    let wt = (w1 + w2) / 2.0;
                    if wt <= 0.0 {
                        continue;
                    }
                    if v1.norm() > 0.0 {
                        rl[c] += v1 * wt;
                        sumwt += wt;
                        if w1 > 0.0 {
                            var[c] += 2.0 * wt * wt / w1;
                        }
                    }
                    if v2.norm() > 0.0 {
                        lr[c] += v2 * wt;
                        sumwt += wt;
                        if w2 > 0.0 {
                            var[c] += 2.0 * wt * wt / w2;
                        }
                    }
                }
            }
            let mut x = vec![C64::new(1.0, 0.0); nchan];
            let mut ok = vec![false; nchan];
            let mut err = vec![0f64; nchan];
            for c in 0..nchan {
                let sum = rl[c] + lr[c].conj();
                let amp = sum.norm();
                if sumwt > 0.0 && amp > 0.0 {
                    x[c] = sum / amp;
                    ok[c] = true;
                    err[c] = (var[c] / 2.0).sqrt() / amp;
                }
            }
            XfSolution { x, ok, err }
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Sim {
        data: Vec<f32>,
        model: Vec<f32>,
        weight: Vec<f32>,
        flag: Vec<u8>,
        flag_row: Vec<u8>,
        a1: Vec<u32>,
        a2: Vec<u32>,
        tb: Vec<u32>,
        freq: Vec<f64>,
    }

    impl Sim {
        fn problem(&self, ntime: usize) -> Problem<'_> {
            Problem {
                nrow: self.a1.len(),
                nchan: self.freq.len(),
                ntime,
                data: &self.data,
                model: &self.model,
                weight: &self.weight,
                flag: &self.flag,
                flag_row: &self.flag_row,
                antenna1: &self.a1,
                antenna2: &self.a2,
                time_bin: &self.tb,
                freq: &self.freq,
            }
        }
    }

    /// Cross hands `V_XY = M_XY k(nu) x(nu)`, `V_YX = M_YX conj(k x)`, with
    /// a polarised model `M_XY = M_YX = u` per row.
    fn sim(nant: usize, nchan: usize, tau_ns: f64, xphase: f64) -> Sim {
        let freq: Vec<f64> = (0..nchan)
            .map(|c| 856e6 + 856e6 * (c as f64 + 0.5) / nchan as f64)
            .collect();
        let nu0 = freq.iter().sum::<f64>() / nchan as f64;
        let (mut a1, mut a2) = (Vec::new(), Vec::new());
        for p in 0..nant {
            for q in p..nant {
                a1.push(p as u32);
                a2.push(q as u32);
            }
        }
        let nrow = a1.len();
        let (mut data, mut model) = (Vec::new(), Vec::new());
        for r in 0..nrow {
            let u = 0.5 + 0.1 * (r % 7) as f64;
            for &f in &freq {
                let ph = std::f64::consts::TAU * tau_ns * 1e-9 * (f - nu0) + xphase;
                let g = C64::new(ph.cos(), ph.sin());
                let m = [
                    C64::new(1.0, 0.0),
                    C64::new(u, 0.0),
                    C64::new(u, 0.0),
                    C64::new(1.0, 0.0),
                ];
                let v = [m[0], m[1] * g, m[2] * g.conj(), m[3]];
                for k in 0..4 {
                    data.extend([v[k].re as f32, v[k].im as f32]);
                    model.extend([m[k].re as f32, m[k].im as f32]);
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
            freq,
        }
    }

    #[test]
    fn kcross_recovers_a_pure_delay_with_its_sign() {
        for tau in [3.0, -4.25, 0.4] {
            let s = sim(5, 256, tau, 0.0);
            let sol = kcross(&s.problem(1)).unwrap();
            assert!(sol[0].ok);
            // The parabolic refinement's bias stays far below one padded bin
            // (1 / (8 x 856 MHz) = 0.146 ns).
            assert!(
                (sol[0].delay_ns - tau).abs() < 0.01,
                "{tau} {}",
                sol[0].delay_ns
            );
        }
    }

    #[test]
    fn xf_recovers_the_phase_and_flags_empty_intervals() {
        let mut s = sim(4, 16, 0.0, 0.6);
        s.tb = (0..s.a1.len()).map(|r| u32::from(r % 2 == 1)).collect();
        // Interval 2 has no rows.
        let sol = xf(&s.problem(3)).unwrap();
        for s in sol.iter().take(2) {
            for (ok, x) in s.ok.iter().zip(&s.x) {
                assert!(*ok);
                assert!((x.arg() - 0.6).abs() < 1e-6);
            }
        }
        assert!(sol[2].ok.iter().all(|&o| !o));
        assert!(sol[2].x.iter().all(|&x| x == C64::new(1.0, 0.0)));
    }

    #[test]
    fn flagged_cells_do_not_enter() {
        let mut s = sim(4, 16, 0.0, 0.6);
        // Corrupt the XY of every row but flag it: the answer is unchanged.
        for r in 0..s.a1.len() {
            for c in 0..16 {
                let cell = r * 16 + c;
                s.data[8 * cell + 2] = 100.0;
                s.flag[4 * cell + 1] = 1;
            }
        }
        let k = kcross(&s.problem(1)).unwrap();
        assert!(k[0].delay_ns.abs() < 0.01);
        // Xf needs both hands: every channel unsolved.
        let x = xf(&s.problem(1)).unwrap();
        assert!(x[0].ok.iter().all(|&o| !o));
    }

    #[test]
    fn threads_are_bit_identical() {
        let s = sim(6, 64, 2.5, 0.3);
        let one = rayon::ThreadPoolBuilder::new()
            .num_threads(1)
            .build()
            .unwrap();
        let a = one.install(|| kcross(&s.problem(1)).unwrap());
        let b = kcross(&s.problem(1)).unwrap();
        assert_eq!(a[0].delay_ns.to_bits(), b[0].delay_ns.to_bits());
        let xa = one.install(|| xf(&s.problem(1)).unwrap());
        let xb = xf(&s.problem(1)).unwrap();
        assert_eq!(xa[0].x, xb[0].x);
    }
}
