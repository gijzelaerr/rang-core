// SPDX-License-Identifier: GPL-3.0-or-later
//! A SARA-style analysis prior: Dirac and the Daubechies db1 to db8 bases,
//! concatenated and scaled by `1/√9`, so that `Ψ Ψᵀ = I` (Carrillo, McEwen and
//! Wiaux 2012; uSARA, Terris et al. 2023).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The proximal operator of `τ ‖Ψᵀ x‖₁` with `x ≥ 0` has no closed form with a
//! redundant frame, so it runs dual forward-backward (as uSARA's sub-iteration),
//! warm-started from the previous call. See `research/gram-solver.md`.

use crate::prox_solver::Prior;
use rayon::prelude::*;

/// The minimum-phase scaling filters, from spectral factorisation of the
/// Daubechies polynomial; the test checks orthonormality and vanishing moments.
#[allow(clippy::excessive_precision, clippy::approx_constant)]
const FILTERS: [&[f64]; 8] = [
    &[7.07106781186547573e-01, 7.07106781186547573e-01],
    &[
        4.82962913144534156e-01,
        8.36516303737807942e-01,
        2.24143868042013389e-01,
        -1.29409522551260397e-01,
    ],
    &[
        3.32670552950082576e-01,
        8.06891509311092436e-01,
        4.59877502118491654e-01,
        -1.35011020010254584e-01,
        -8.54412738820266582e-02,
        3.52262918857095264e-02,
    ],
    &[
        2.30377813308896506e-01,
        7.14846570552915672e-01,
        6.30880767929859143e-01,
        -2.79837694168596982e-02,
        -1.87034811719093086e-01,
        3.08413818355606738e-02,
        3.28830116668851757e-02,
        -1.05974017850690248e-02,
    ],
    &[
        1.60102397974192928e-01,
        6.03829269797189649e-01,
        7.24308528437773047e-01,
        1.38428145901320715e-01,
        -2.42294887066382081e-01,
        -3.22448695846384650e-02,
        7.75714938400457049e-02,
        -6.24149021279827524e-03,
        -1.25807519990819953e-02,
        3.33572528547377125e-03,
    ],
    &[
        1.11540743350109370e-01,
        4.94623890398452781e-01,
        7.51133908021095253e-01,
        3.15250351709197962e-01,
        -2.26264693965439107e-01,
        -1.29766867567261995e-01,
        9.75016055873229592e-02,
        2.75228655303056506e-02,
        -3.15820393174859673e-02,
        5.53842201161496776e-04,
        4.77725751094550035e-03,
        -1.07730108530847764e-03,
    ],
    &[
        7.78520540850092257e-02,
        3.96539319481917507e-01,
        7.29132090846235537e-01,
        4.69782287405192900e-01,
        -1.43906003928565090e-01,
        -2.24036184993875231e-01,
        7.13092192668304398e-02,
        8.06126091510831894e-02,
        -3.80299369350145036e-02,
        -1.65745416306668919e-02,
        1.25509985560998648e-02,
        4.29577972921363371e-04,
        -1.80164070404749302e-03,
        3.53713799974520620e-04,
    ],
    &[
        5.44158422431039734e-02,
        3.12871590914299724e-01,
        6.75630736297289536e-01,
        5.85354683654206620e-01,
        -1.58291052563490180e-02,
        -2.84015542961545853e-01,
        4.72484573912326691e-04,
        1.28747426620479138e-01,
        -1.73693010018079602e-02,
        -4.40882539307945534e-02,
        1.39810279173982425e-02,
        8.74609404740575580e-03,
        -4.87035299345156287e-03,
        -3.91740373376947375e-04,
        6.75449406450568681e-04,
        -1.17476784124769386e-04,
    ],
];

/// The high-pass partner `g[k] = (−1)^k h[L−1−k]`.
fn highpass(h: &[f64]) -> Vec<f64> {
    h.iter()
        .rev()
        .enumerate()
        .map(|(k, v)| if k % 2 == 0 { *v } else { -*v })
        .collect()
}

/// One periodic analysis step of `src` (length `m`, even) into `dst`.
fn analyse(h: &[f64], g: &[f64], src: &[f64], dst: &mut [f64]) {
    let m = src.len();
    let half = m / 2;
    let (a, d) = dst.split_at_mut(half);
    for i in 0..half {
        let (mut sa, mut sd) = (0.0, 0.0);
        for (k, (hk, gk)) in h.iter().zip(g).enumerate() {
            let v = src[(2 * i + k) % m];
            sa += hk * v;
            sd += gk * v;
        }
        a[i] = sa;
        d[i] = sd;
    }
}

/// One periodic synthesis step, the adjoint and inverse of [`analyse`].
fn synthesise(h: &[f64], g: &[f64], src: &[f64], dst: &mut [f64]) {
    let m = src.len();
    let half = m / 2;
    dst.fill(0.0);
    let (a, d) = src.split_at(half);
    for i in 0..half {
        for (k, (hk, gk)) in h.iter().zip(g).enumerate() {
            dst[(2 * i + k) % m] += hk * a[i] + gk * d[i];
        }
    }
}

/// `dst[c * m + r] = src[r * stride + c]` over the leading `m × m` block.
fn transpose_block(src: &[f64], stride: usize, m: usize, dst: &mut [f64]) {
    dst.par_chunks_mut(m).enumerate().for_each(|(c, col)| {
        for (r, o) in col.iter_mut().enumerate() {
            *o = src[r * stride + c];
        }
    });
}

/// Multilevel forward transform of an `n × n` image in place.
fn dwt2(h: &[f64], g: &[f64], data: &mut [f64], n: usize, levels: usize, tmp: &mut [f64]) {
    let mut m = n;
    for _ in 0..levels {
        // Rows: every row of the leading block, through `tmp`.
        data.par_chunks_mut(n)
            .take(m)
            .zip(tmp.par_chunks_mut(m))
            .for_each(|(row, out)| {
                analyse(h, g, &row[..m], out);
                row[..m].copy_from_slice(out);
            });
        // Columns: transpose into `tmp`, transform, write back.
        transpose_block(data, n, m, &mut tmp[..m * m]);
        let tmp_ref: &[f64] = &tmp[..m * m];
        let mut cols = vec![0.0; m * m];
        cols.par_chunks_mut(m)
            .zip(tmp_ref.par_chunks(m))
            .for_each(|(out, col)| analyse(h, g, col, out));
        data.par_chunks_mut(n)
            .take(m)
            .enumerate()
            .for_each(|(r, row)| {
                for (c, o) in row[..m].iter_mut().enumerate() {
                    *o = cols[c * m + r];
                }
            });
        m /= 2;
    }
}

/// Multilevel inverse (and adjoint) in place.
fn idwt2(h: &[f64], g: &[f64], data: &mut [f64], n: usize, levels: usize, tmp: &mut [f64]) {
    let mut m = n >> (levels - 1);
    for _ in 0..levels {
        transpose_block(data, n, m, &mut tmp[..m * m]);
        let tmp_ref: &[f64] = &tmp[..m * m];
        let mut cols = vec![0.0; m * m];
        cols.par_chunks_mut(m)
            .zip(tmp_ref.par_chunks(m))
            .for_each(|(out, col)| synthesise(h, g, col, out));
        data.par_chunks_mut(n)
            .take(m)
            .enumerate()
            .for_each(|(r, row)| {
                for (c, o) in row[..m].iter_mut().enumerate() {
                    *o = cols[c * m + r];
                }
            });
        data.par_chunks_mut(n)
            .take(m)
            .zip(tmp.par_chunks_mut(m))
            .for_each(|(row, out)| {
                synthesise(h, g, &row[..m], out);
                row[..m].copy_from_slice(out);
            });
        m *= 2;
    }
}

/// The frame and the dual state of its proximal operator.
pub struct Sara {
    n: usize,
    levels: usize,
    bases: Vec<(&'static [f64], Vec<f64>)>,
    scale: f64,
    /// `λ`, in coefficient units of the scaled frame.
    pub lambda: f64,
    /// Dual variables: Dirac first, then one image per wavelet basis.
    dual: Vec<Vec<f64>>,
    /// Reweighting factors per coefficient, one image per basis; empty is 1.
    weights: Vec<Vec<f64>>,
    /// Dual iterations per proximal call.
    pub dual_iterations: usize,
    /// Stop the dual loop when the relative change of `x` falls below this.
    pub dual_tolerance: f64,
    /// Dual iterations run so far, one forward and one adjoint transform each.
    pub dual_iterations_run: u64,
    /// `δ` of the reweighting `δ / (δ + |c|)`.
    pub delta: f64,
    work: Vec<f64>,
    synth: Vec<f64>,
}

impl Sara {
    pub fn new(
        n: usize,
        levels: usize,
        nbases: usize,
        lambda: f64,
        dual_iterations: usize,
        delta: f64,
    ) -> Result<Sara, String> {
        if !n.is_power_of_two() || n >> levels < 8 {
            return Err("the image side must be a power of two, with room for the levels".into());
        }
        if nbases == 0 || nbases > FILTERS.len() {
            return Err("between 1 and 8 wavelet bases".into());
        }
        let bases: Vec<_> = FILTERS[..nbases]
            .iter()
            .map(|h| (*h, highpass(h)))
            .collect();
        Ok(Sara {
            n,
            levels,
            scale: 1.0 / ((nbases + 1) as f64).sqrt(),
            bases,
            lambda,
            dual: vec![vec![0.0; n * n]; nbases + 1],
            weights: Vec::new(),
            dual_iterations,
            dual_tolerance: 1e-4,
            dual_iterations_run: 0,
            delta,
            work: vec![0.0; n * n],
            synth: vec![0.0; n * n],
        })
    }

    /// Bytes of the dual variables, the reweighting factors and the work space.
    pub fn state_bytes(&self) -> u64 {
        ((self.dual.len() + self.weights.len() + 2) * self.n * self.n * 8) as u64
    }

    /// `Ψᵀ x`, basis `b` (0 is Dirac).
    fn analysis(&mut self, b: usize, x: &[f64], out: &mut [f64]) {
        out.copy_from_slice(x);
        if b > 0 {
            let (h, g) = &self.bases[b - 1];
            dwt2(h, g, out, self.n, self.levels, &mut self.work);
        }
        let s = self.scale;
        out.par_iter_mut().for_each(|v| *v *= s);
    }

    /// `Σ_b Ψ_b v_b` of the dual variables into `self.synth`.
    fn synthesis_of_dual(&mut self) {
        let mut sum = std::mem::take(&mut self.synth);
        sum.fill(0.0);
        let mut buf = vec![0.0; self.n * self.n];
        for b in 0..self.dual.len() {
            buf.copy_from_slice(&self.dual[b]);
            if b > 0 {
                let (h, g) = &self.bases[b - 1];
                idwt2(h, g, &mut buf, self.n, self.levels, &mut self.work);
            }
            sum.par_iter_mut()
                .zip(buf.par_iter())
                .for_each(|(s, v)| *s += *v);
        }
        let s = self.scale;
        sum.par_iter_mut().for_each(|v| *v *= s);
        self.synth = sum;
    }

    fn weight_of(&self, b: usize) -> Option<&[f64]> {
        self.weights.get(b).map(|w| w.as_slice())
    }
}

impl Prior for Sara {
    fn prox(&mut self, z: &[f64], step: f64, out: &mut [f64]) {
        let tau = step * self.lambda;
        let mut coef = vec![0.0; z.len()];
        self.synthesis_of_dual();
        out.par_iter_mut()
            .zip(z.par_iter())
            .zip(self.synth.par_iter())
            .for_each(|((o, a), s)| *o = (a - s).max(0.0));
        let mut previous = out.to_vec();
        for _ in 0..self.dual_iterations {
            for b in 0..self.dual.len() {
                self.analysis(b, out, &mut coef);
                let w = self.weight_of(b).map(<[f64]>::to_vec);
                let v = &mut self.dual[b];
                v.par_iter_mut()
                    .zip(coef.par_iter())
                    .enumerate()
                    .for_each(|(i, (d, c))| {
                        let limit = tau * w.as_ref().map_or(1.0, |w| w[i]);
                        *d = (*d + *c).clamp(-limit, limit);
                    });
            }
            self.dual_iterations_run += 1;
            self.synthesis_of_dual();
            out.par_iter_mut()
                .zip(z.par_iter())
                .zip(self.synth.par_iter())
                .for_each(|((o, a), s)| *o = (a - s).max(0.0));
            let (mut change, mut norm) = (0.0, 0.0);
            for (a, b) in out.iter().zip(&previous) {
                change += (a - b) * (a - b);
                norm += a * a;
            }
            previous.copy_from_slice(out);
            if change <= self.dual_tolerance * self.dual_tolerance * norm.max(1e-300) {
                break;
            }
        }
    }

    fn value(&mut self, x: &[f64]) -> f64 {
        let mut coef = vec![0.0; x.len()];
        let mut total = 0.0;
        for b in 0..self.dual.len() {
            self.analysis(b, x, &mut coef);
            total += match self.weight_of(b) {
                Some(w) => coef
                    .par_iter()
                    .zip(w.par_iter())
                    .map(|(c, w)| c.abs() * w)
                    .sum::<f64>(),
                None => coef.par_iter().map(|c| c.abs()).sum::<f64>(),
            };
        }
        self.lambda * total
    }

    fn reweight(&mut self, x: &[f64]) {
        let delta = self.delta;
        let mut coef = vec![0.0; x.len()];
        let mut weights = Vec::with_capacity(self.dual.len());
        for b in 0..self.dual.len() {
            self.analysis(b, x, &mut coef);
            weights.push(coef.par_iter().map(|c| delta / (delta + c.abs())).collect());
        }
        self.weights = weights;
    }

    fn set_lambda(&mut self, lambda: f64) {
        self.lambda = lambda;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn noise(n: usize, seed: u64) -> Vec<f64> {
        let mut state = seed;
        (0..n)
            .map(|_| {
                state ^= state << 13;
                state ^= state >> 7;
                state ^= state << 17;
                (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
            })
            .collect()
    }

    #[test]
    fn filters_are_orthonormal_with_the_vanishing_moments() {
        for (i, h) in FILTERS.iter().enumerate() {
            assert_eq!(h.len(), 2 * (i + 1));
            for shift in 0..=i {
                let dot: f64 = h[..h.len() - 2 * shift]
                    .iter()
                    .zip(&h[2 * shift..])
                    .map(|(a, b)| a * b)
                    .sum();
                let want = if shift == 0 { 1.0 } else { 0.0 };
                assert!((dot - want).abs() < 1e-14, "db{} shift {shift}", i + 1);
            }
            let g = highpass(h);
            for p in 0..=i {
                let moment: f64 = g
                    .iter()
                    .enumerate()
                    .map(|(k, v)| v * (k as f64 / h.len() as f64).powi(p as i32))
                    .sum();
                assert!(moment.abs() < 1e-11, "db{} moment {p}: {moment}", i + 1);
            }
        }
    }

    #[test]
    fn transforms_are_orthonormal() {
        let n = 64;
        let x = noise(n * n, 5);
        let y = noise(n * n, 7);
        let mut tmp = vec![0.0; n * n];
        for h in &FILTERS {
            let g = highpass(h);
            let (mut a, mut b) = (x.clone(), y.clone());
            dwt2(h, &g, &mut a, n, 3, &mut tmp);
            dwt2(h, &g, &mut b, n, 3, &mut tmp);
            let inner: f64 = a.iter().zip(&b).map(|(p, q)| p * q).sum();
            let want: f64 = x.iter().zip(&y).map(|(p, q)| p * q).sum();
            assert!((inner - want).abs() < 1e-11, "{inner} {want}");
            idwt2(h, &g, &mut a, n, 3, &mut tmp);
            let err = a
                .iter()
                .zip(&x)
                .map(|(p, q)| (p - q).abs())
                .fold(0.0, f64::max);
            assert!(err < 1e-12, "{err}");
        }
    }

    #[test]
    fn the_proximal_point_beats_its_neighbours() {
        let n = 32;
        let z = noise(n * n, 11);
        let mut prior = Sara::new(n, 2, 8, 0.2, 400, 1.0).unwrap();
        prior.dual_tolerance = 1e-10;
        let mut x = vec![0.0; n * n];
        prior.prox(&z, 1.0, &mut x);
        assert!(x.iter().all(|&v| v >= 0.0));
        let distance =
            |a: &[f64]| -> f64 { a.iter().zip(&z).map(|(p, q)| (p - q) * (p - q)).sum() };
        let f0 = 0.5 * distance(&x) + prior.value(&x);
        let bump = noise(n * n, 13);
        for scale in [1e-3, 1e-2, 1e-1] {
            let y: Vec<f64> = x
                .iter()
                .zip(&bump)
                .map(|(v, b)| (v + scale * b).max(0.0))
                .collect();
            let f = 0.5 * distance(&y) + prior.value(&y);
            assert!(f >= f0 - 1e-7, "scale {scale}: {f} below {f0}");
        }
    }

    #[test]
    fn a_large_threshold_gives_the_mean_free_limit_and_reweighting_lowers_the_penalty() {
        let n = 32;
        let mut prior = Sara::new(n, 2, 2, 1e3, 200, 0.1).unwrap();
        let mut x = vec![0.0; n * n];
        let z = noise(n * n, 3);
        prior.prox(&z, 1.0, &mut x);
        let peak = x.iter().cloned().fold(0.0, f64::max);
        assert!(peak < 1e-2, "{peak}");
        let m: Vec<f64> = noise(n * n, 9).iter().map(|v| v + 0.5).collect();
        let before = prior.value(&m);
        prior.reweight(&m);
        assert!(prior.value(&m) < before);
    }
}
