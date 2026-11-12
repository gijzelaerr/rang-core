// SPDX-License-Identifier: GPL-3.0-or-later
//! The parallactic-angle term P (task C6, `research/c6-polterms.md`; C1 term
//! T6, `research/c1-calibration-chain.md` section 1.3).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! For linear feeds `P_p = [[cos a, sin a], [-sin a, cos a]]`, `a` the
//! parallactic angle of antenna `p` at the row's time plus the receptor angle
//! (C1 T6; `rang.simtruth`'s convention, which CASA's `applycal(parang=True)`
//! inverts, research/a1-simtruth.md 7.2). P is CASA's type 7: last when
//! correcting, first when corrupting. This module only rotates: the angles
//! are computed in Python (`rang.cal_pol.parallactic_angles`), and so are
//! P's flags (`rang.cal_pol.spread_flags`: CASA's general-Jones rule, any
//! flagged correlation of a cell flags all four; research/p-flag-spread.md). `corrupt` is `V = P_p M P_q^T`; `correct` its exact inverse
//! `M = P_p^T V P_q` (P is orthogonal), which is `corrupt` with both angles
//! negated. Rows are independent, so the output is bit-identical for every
//! thread count.

use rayon::prelude::*;

/// Rotate `data` (interleaved complex64 `(row, chan, 4)`, XX XY YX YY) by
/// `P_p M P_q^T` with angles `angle_p`, `angle_q` (rad, one per row), or by
/// the inverse when `inverse`. Every channel of a row has the same angles.
pub fn rotate(
    data: &[f32],
    nrow: usize,
    nchan: usize,
    angle_p: &[f64],
    angle_q: &[f64],
    inverse: bool,
    out: &mut [f32],
) -> Result<(), String> {
    let cells = nrow.checked_mul(nchan).ok_or("cell count overflows")?;
    if data.len() != 8 * cells || out.len() != data.len() {
        return Err("data and out must be (row, chan, 4) complex64".into());
    }
    if angle_p.len() != nrow || angle_q.len() != nrow {
        return Err("angle_p and angle_q must have one value per row".into());
    }
    let sign = if inverse { -1.0 } else { 1.0 };
    out.par_chunks_mut(8 * nchan.max(1))
        .zip(data.par_chunks(8 * nchan.max(1)))
        .enumerate()
        .for_each(|(r, (o, d))| {
            let (sp, cp) = (sign * angle_p[r]).sin_cos();
            let (sq, cq) = (sign * angle_q[r]).sin_cos();
            // P = [[c, s], [-s, c]]; V = P_p M P_q^T.
            let pp = [[cp, sp], [-sp, cp]];
            let pq = [[cq, sq], [-sq, cq]];
            for c in 0..nchan {
                let m: [[(f64, f64); 2]; 2] = std::array::from_fn(|i| {
                    std::array::from_fn(|j| {
                        let k = 8 * c + 2 * (2 * i + j);
                        (f64::from(d[k]), f64::from(d[k + 1]))
                    })
                });
                for (a, ppa) in pp.iter().enumerate() {
                    for (b, pqb) in pq.iter().enumerate() {
                        let (mut re, mut im) = (0.0, 0.0);
                        for (i, row) in m.iter().enumerate() {
                            for (j, v) in row.iter().enumerate() {
                                let w = ppa[i] * pqb[j];
                                re += w * v.0;
                                im += w * v.1;
                            }
                        }
                        let k = 8 * c + 2 * (2 * a + b);
                        o[k] = re as f32;
                        o[k + 1] = im as f32;
                    }
                }
            }
        });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unpolarised_with_equal_angles_is_unchanged_and_inverse_round_trips() {
        // I = 2: XX = YY = 2, XY = YX = 0; equal angles leave it unchanged.
        let data = [2.0f32, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 0.0];
        let mut out = [0f32; 8];
        rotate(&data, 1, 1, &[0.7], &[0.7], false, &mut out).unwrap();
        for (o, d) in out.iter().zip(&data) {
            assert!((o - d).abs() < 1e-6);
        }
        let v = [1.0f32, 0.2, 0.3, -0.1, 0.25, 0.4, 0.5, -0.3];
        let mut c = [0f32; 8];
        let mut back = [0f32; 8];
        rotate(&v, 1, 1, &[0.3], &[-1.1], false, &mut c).unwrap();
        rotate(&c, 1, 1, &[0.3], &[-1.1], true, &mut back).unwrap();
        for (b, x) in back.iter().zip(&v) {
            assert!((b - x).abs() < 1e-6);
        }
    }

    #[test]
    fn stokes_q_rotates_by_twice_the_angle() {
        // Q = 1 (XX = 1, YY = -1): P Q P^T gives Q cos 2a in XX - YY over 2
        // and -Q sin 2a in the real part of XY (U' = -Q sin 2a).
        let a = 0.4f64;
        let data = [1.0f32, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0];
        let mut out = [0f32; 8];
        rotate(&data, 1, 1, &[a], &[a], false, &mut out).unwrap();
        let q = (out[0] - out[6]) / 2.0;
        let u = (out[2] + out[4]) / 2.0;
        assert!((f64::from(q) - (2.0 * a).cos()).abs() < 1e-6);
        assert!((f64::from(u) + (2.0 * a).sin()).abs() < 1e-6);
    }
}
