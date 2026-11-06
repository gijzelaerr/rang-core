//! The bandpass B's post-solve gap filling (task C2c,
//! `research/c2c-bandpass.md` part 2): CASA's `fillgaps`
//! (`BJones::fillChanGaps` and `BJones::fillChanGapArray`,
//! `StandardVisCal.cc`, read in the 2023 mirror; C1 section 0), written from
//! that rule; CASA is not copied. The solve itself is `diag.rs`'s
//! `diag_complex` per channel with `reference.rs`'s rules.
//!
//! Per (time, antenna, polarisation), over the channels: nothing changes
//! before the first unflagged channel or after the last; a run of flagged
//! channels between unflagged `ch1` and `ch2` is filled when `ch2 - ch1 <=
//! maxgap + 1`, by linear interpolation of the amplitude and of the phase
//! (the phase step wrapped into `[-pi, pi]` once), in float32 as CASA's
//! `Float` locals are, and its channels are unflagged.

pub use rustfft::num_complex::Complex32;

/// `fillChanGapArray` on one channel vector. `ok[c]` is true where the
/// solution is unflagged; filled channels become true.
pub fn fill_gap_array(sol: &mut [Complex32], ok: &mut [bool], maxgap: usize) {
    let n = sol.len();
    assert_eq!(n, ok.len());
    let pi = std::f64::consts::PI;
    let mut ich = 0usize;
    // Advance to the first unflagged channel.
    while ich < n && !ok[ich] {
        ich += 1;
    }
    let mut done = ich == n;
    while !done {
        // Advance to the next flagged channel.
        while ich < n && ok[ich] {
            ich += 1;
        }
        if ich < n {
            let ch1 = ich - 1;
            let mut ch2 = ich + 1;
            while ch2 < n && !ok[ch2] {
                ch2 += 1;
            }
            if ch2 < n {
                let dch = ch2 - ch1;
                if dch <= maxgap + 1 {
                    let a0: f32 = sol[ch1].norm();
                    let da: f32 = sol[ch2].norm() - a0;
                    let p0: f32 = sol[ch1].arg();
                    let mut dp: f32 = sol[ch2].arg() - p0;
                    // `if (dp > C::pi) dp -= 2 pi` in double, stored as Float.
                    if f64::from(dp) > pi {
                        dp = (f64::from(dp) - 2. * pi) as f32;
                    }
                    if f64::from(dp) < -pi {
                        dp = (f64::from(dp) + 2. * pi) as f32;
                    }
                    while ich < ch2 {
                        let fch = (ich - ch1) as f32 / dch as f32;
                        let a = a0 + da * fch;
                        let p = p0 + dp * fch;
                        sol[ich] = Complex32::new(p.cos(), p.sin()) * a;
                        ok[ich] = true;
                        ich += 1;
                    }
                    ich += 1;
                } else {
                    ich = ch2 + 1;
                }
            } else {
                done = true;
            }
        } else {
            done = true;
        }
        if ich >= n {
            done = true;
        }
    }
}

/// `fillChanGaps` over a whole table `(nrow, nchan, npar)` row-major, as the
/// `B Jones` CPARAM and FLAG columns hold it; rows with no unflagged
/// solution are left alone. `flag` true is flagged.
pub fn fill_gaps(
    sol: &mut [Complex32],
    flag: &mut [bool],
    nrow: usize,
    nchan: usize,
    npar: usize,
    maxgap: usize,
) {
    assert_eq!(sol.len(), nrow * nchan * npar);
    assert_eq!(flag.len(), sol.len());
    if maxgap == 0 {
        return;
    }
    let mut v = vec![Complex32::new(0., 0.); nchan];
    let mut ok = vec![false; nchan];
    for row in 0..nrow {
        let base = row * nchan * npar;
        if flag[base..base + nchan * npar].iter().all(|&f| f) {
            continue;
        }
        for p in 0..npar {
            for c in 0..nchan {
                v[c] = sol[base + c * npar + p];
                ok[c] = !flag[base + c * npar + p];
            }
            fill_gap_array(&mut v, &mut ok, maxgap);
            for c in 0..nchan {
                sol[base + c * npar + p] = v[c];
                flag[base + c * npar + p] = !ok[c];
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(a: f32, p: f32) -> Complex32 {
        Complex32::new(p.cos(), p.sin()) * a
    }

    #[test]
    fn short_gaps_are_filled_and_long_ones_kept() {
        let mut sol: Vec<Complex32> = (0..12).map(|i| c(1. + i as f32 * 0.1, 0.2)).collect();
        let mut ok = vec![true; 12];
        // A gap of 2 (channels 2, 3) and one of 4 (6..=9); leading 0 flagged.
        for i in [0usize, 2, 3, 6, 7, 8, 9] {
            ok[i] = false;
        }
        fill_gap_array(&mut sol, &mut ok, 3);
        assert!(!ok[0], "no extrapolation before the first channel");
        assert!(ok[2] && ok[3], "a gap of 2 <= 3 is filled");
        assert!(!ok[6] && !ok[9], "a gap of 4 > 3 is kept");
        assert!((sol[2].norm() - 1.2).abs() < 1e-6);
        assert!((sol[3].arg() - 0.2).abs() < 1e-6);
    }

    #[test]
    fn the_phase_step_is_wrapped() {
        let mut sol = vec![c(1., 3.0), c(9., 0.), c(1., -3.0)];
        let mut ok = vec![true, false, true];
        fill_gap_array(&mut sol, &mut ok, 1);
        assert!(ok[1]);
        // Halfway from 3.0 across pi to -3.0: near +-pi, not 0.
        assert!((sol[1].arg().abs() - std::f32::consts::PI).abs() < 1e-5);
    }

    #[test]
    fn trailing_and_whole_flags_are_left() {
        let mut sol = vec![c(1., 0.); 5];
        let mut ok = vec![true, true, false, false, false];
        fill_gap_array(&mut sol, &mut ok, 10);
        assert_eq!(ok, vec![true, true, false, false, false]);
        let mut ok = vec![false; 5];
        fill_gap_array(&mut sol, &mut ok, 10);
        assert_eq!(ok, vec![false; 5]);
    }
}
