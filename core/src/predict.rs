// SPDX-License-Identifier: MIT AND BSD-3-Clause
//! WSClean-format component sky prediction, ported from codex-africanus 0.4.4.
//!
//! A Rust translation of `africanus/rime/wsclean_predict.py` and
//! `africanus/model/wsclean/spec_model.py` from codex-africanus 0.4.4,
//! distributed under this licence:
//!
//! > Copyright (c) 2019, National Research Foundation
//! > (South African Radio Astronomy Observatory)
//! > All rights reserved.
//! >
//! > Redistribution and use in source and binary forms, with or without
//! > modification, are permitted provided that the following conditions are
//! > met:
//! >
//! > 1. Redistributions of source code must retain the above copyright notice,
//! >    this list of conditions and the following disclaimer.
//! >
//! > 2. Redistributions in binary form must reproduce the above copyright
//! >    notice, this list of conditions and the following disclaimer in the
//! >    documentation and/or other materials provided with the distribution.
//! >
//! > 3. Neither the name of the copyright holder nor the names of its
//! >    contributors may be used to endorse or promote products derived from
//! >    this software without specific prior written permission.
//! >
//! > THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
//! > IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//! > THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//! > PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
//! > CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
//! > EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
//! > PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
//! > PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
//! > LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
//! > NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
//! > SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
//!
//! The translation and its integration are part of Rang (MIT).
//! Validation: `research/core-phase3c-a.md`. Positive Fourier phase, the
//! convention of the MS and of africanus.

use crate::jones::C64;

/// Speed of light in m/s, as `africanus.constants.c`.
pub const LIGHTSPEED: f64 = 299_792_458.0;
/// `africanus.constants.two_pi_over_c`.
pub const TWO_PI_OVER_C: f64 = 2.0 * std::f64::consts::PI / LIGHTSPEED;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Point,
    Gaussian,
}

/// Borrowed component list: `nsrc` components, `ncoeff` spectral terms each.
pub struct Components<'a> {
    pub lm: &'a [f64],
    pub kind: &'a [Kind],
    pub flux: &'a [f64],
    /// `nsrc * ncoeff`.
    pub coeffs: &'a [f64],
    pub ncoeff: usize,
    pub log_poly: &'a [bool],
    pub ref_freq: &'a [f64],
    /// `nsrc * 3`: major FWHM, minor FWHM (radians), position angle.
    pub gauss_shape: &'a [f64],
}

impl Components<'_> {
    pub fn len(&self) -> usize {
        self.flux.len()
    }
    pub fn is_empty(&self) -> bool {
        self.flux.is_empty()
    }
    fn check(&self) -> Result<(), &'static str> {
        let n = self.len();
        if self.lm.len() != 2 * n
            || self.kind.len() != n
            || self.coeffs.len() != n * self.ncoeff
            || self.log_poly.len() != n
            || self.ref_freq.len() != n
            || self.gauss_shape.len() != 3 * n
        {
            return Err("component buffer length mismatch");
        }
        Ok(())
    }
}

/// `spectra`: (nsrc, nchan) flux densities.
pub fn spectra(c: &Components, frequency: &[f64]) -> Result<Vec<f64>, &'static str> {
    c.check()?;
    let nchan = frequency.len();
    let mut out = vec![0.; c.len() * nchan];
    for s in 0..c.len() {
        let rf = c.ref_freq[s];
        let coeffs = &c.coeffs[s * c.ncoeff..(s + 1) * c.ncoeff];
        for (f, &nu) in frequency.iter().enumerate() {
            out[s * nchan + f] = if c.log_poly[s] {
                let mut value = 0.;
                for (k, &coeff) in coeffs.iter().enumerate() {
                    value += coeff * (nu / rf).ln().powi(k as i32 + 1);
                }
                c.flux[s] * value.exp()
            } else {
                let mut value = c.flux[s];
                for (k, &coeff) in coeffs.iter().enumerate() {
                    value += coeff * (nu / rf - 1.0).powi(k as i32 + 1);
                }
                value
            };
        }
    }
    Ok(out)
}

/// Rows per parallel block: the block's accumulator (16 bytes per row and
/// channel) stays in cache while the (nsrc, nchan) spectrum is streamed once
/// per block, not once per row.
pub const BLOCK_ROWS: usize = 8;

/// Per-component terms of the old loop, computed once per component with the
/// same expressions.
struct Source {
    l: f64,
    m: f64,
    n: f64,
    kind: Kind,
    el: f64,
    em: f64,
    er: f64,
}

fn sources(c: &Components) -> Vec<Source> {
    (0..c.len())
        .map(|s| {
            let (l, m) = (c.lm[2 * s], c.lm[2 * s + 1]);
            let n = (1.0 - l * l - m * m).sqrt() - 1.0;
            let (el, em, er) = match c.kind[s] {
                Kind::Point => (0., 0., 0.),
                Kind::Gaussian => {
                    let (emaj, emin, angle) = (
                        c.gauss_shape[3 * s],
                        c.gauss_shape[3 * s + 1],
                        c.gauss_shape[3 * s + 2],
                    );
                    let er = emin / if emaj == 0.0 { 1.0 } else { emaj };
                    (emaj * angle.sin(), emaj * angle.cos(), er)
                }
            };
            Source {
                l,
                m,
                n,
                kind: c.kind[s],
                el,
                em,
                er,
            }
        })
        .collect()
}

/// The single-threaded loop nest (component outer, row inner, channel
/// innermost) over one block of rows, into `out` as interleaved re, im.
fn predict_block(
    uvw: &[f64],
    frequency: &[f64],
    scaled_freq: &[f64],
    spectrum: &[f64],
    sources: &[Source],
    out: &mut [f64],
) {
    let nchan = frequency.len();
    out.fill(0.0);
    for (s, src) in sources.iter().enumerate() {
        let spec = &spectrum[s * nchan..(s + 1) * nchan];
        for (r, row) in out.chunks_exact_mut(2 * nchan).enumerate() {
            let (u, v, w) = (uvw[3 * r], uvw[3 * r + 1], uvw[3 * r + 2]);
            let real_phase = TWO_PI_OVER_C * (u * src.l + v * src.m + w * src.n);
            match src.kind {
                Kind::Point => {
                    for ((out, &nu), &sp) in row.chunks_exact_mut(2).zip(frequency).zip(spec) {
                        let p = real_phase * nu;
                        let re = p.cos() * sp;
                        let im = p.sin() * sp;
                        out[0] += re;
                        out[1] += im;
                    }
                }
                Kind::Gaussian => {
                    let u1 = (u * src.em - v * src.el) * src.er;
                    let v1 = u * src.el + v * src.em;
                    for (((out, &nu), &sp), &sf) in row
                        .chunks_exact_mut(2)
                        .zip(frequency)
                        .zip(spec)
                        .zip(scaled_freq)
                    {
                        let p = real_phase * nu;
                        let mut re = p.cos() * sp;
                        let mut im = p.sin() * sp;
                        let fu1 = u1 * sf;
                        let fv1 = v1 * sf;
                        let shape = (-(fu1 * fu1 + fv1 * fv1)).exp();
                        re *= shape;
                        im *= shape;
                        out[0] += re;
                        out[1] += im;
                    }
                }
            }
        }
    }
}

/// `wsclean_predict` into `vis`, (nrow, nchan) interleaved re, im, in blocks
/// of `block_rows` rows on `threads` threads (0: rayon's global pool,
/// `RAYON_NUM_THREADS`). Every visibility gets its components' terms in
/// component order from the expressions of the single-threaded loop, so the
/// result is bit for bit the same at any thread count and block size.
/// Returns the (nsrc, nchan) spectra.
pub fn predict_into_blocks(
    uvw: &[f64],
    frequency: &[f64],
    c: &Components,
    threads: usize,
    block_rows: usize,
    vis: &mut [f64],
) -> Result<Vec<f64>, &'static str> {
    use rayon::prelude::*;
    if !uvw.len().is_multiple_of(3) {
        return Err("uvw must hold rows of three values");
    }
    if block_rows == 0 {
        return Err("block_rows must be positive");
    }
    let spectrum = spectra(c, frequency)?;
    let (nrow, nchan) = (uvw.len() / 3, frequency.len());
    if vis.len() != 2 * nrow * nchan {
        return Err("vis must hold 2 * nrow * nchan values");
    }
    if vis.is_empty() {
        return Ok(spectrum);
    }
    let fwhm = 2.0 * (2.0 * 2.0_f64.ln()).sqrt();
    let fwhminv = 1.0 / fwhm;
    let gauss_scale = fwhminv * 2.0_f64.sqrt() * std::f64::consts::PI / LIGHTSPEED;
    let scaled_freq: Vec<f64> = frequency.iter().map(|f| f * gauss_scale).collect();
    let sources = sources(c);
    let run = |vis: &mut [f64]| {
        vis.par_chunks_mut(2 * nchan * block_rows)
            .zip(uvw.par_chunks(3 * block_rows))
            .for_each(|(out, uvw)| {
                predict_block(uvw, frequency, &scaled_freq, &spectrum, &sources, out)
            })
    };
    if threads == 0 {
        run(vis);
    } else {
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .map_err(|_| "thread pool")?
            .install(|| run(vis));
    }
    Ok(spectrum)
}

/// `predict_into_blocks` with `BLOCK_ROWS`.
pub fn predict_into(
    uvw: &[f64],
    frequency: &[f64],
    c: &Components,
    threads: usize,
    vis: &mut [f64],
) -> Result<Vec<f64>, &'static str> {
    predict_into_blocks(uvw, frequency, c, threads, BLOCK_ROWS, vis)
}

/// `wsclean_predict`: (nrow, nchan) Stokes I visibilities, on rayon's global
/// pool.
pub fn predict(uvw: &[f64], frequency: &[f64], c: &Components) -> Result<Vec<C64>, &'static str> {
    if !uvw.len().is_multiple_of(3) {
        return Err("uvw must hold rows of three values");
    }
    let mut vis = vec![0.0; 2 * (uvw.len() / 3) * frequency.len()];
    predict_into(uvw, frequency, c, 0, &mut vis)?;
    Ok(vis.chunks_exact(2).map(|z| C64::new(z[0], z[1])).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The single-threaded loop before predict-par, kept verbatim as the
    /// bit-identity reference.
    fn reference(uvw: &[f64], frequency: &[f64], c: &Components) -> Result<Vec<C64>, &'static str> {
        if !uvw.len().is_multiple_of(3) {
            return Err("uvw must hold rows of three values");
        }
        let spectrum = spectra(c, frequency)?;
        let (nrow, nchan) = (uvw.len() / 3, frequency.len());
        let fwhm = 2.0 * (2.0 * 2.0_f64.ln()).sqrt();
        let fwhminv = 1.0 / fwhm;
        let gauss_scale = fwhminv * 2.0_f64.sqrt() * std::f64::consts::PI / LIGHTSPEED;
        let scaled_freq: Vec<f64> = frequency.iter().map(|f| f * gauss_scale).collect();
        let mut vis = vec![C64::ZERO; nrow * nchan];
        for s in 0..c.len() {
            let (l, m) = (c.lm[2 * s], c.lm[2 * s + 1]);
            let n = (1.0 - l * l - m * m).sqrt() - 1.0;
            let spec = &spectrum[s * nchan..(s + 1) * nchan];
            let (el, em, er) = match c.kind[s] {
                Kind::Point => (0., 0., 0.),
                Kind::Gaussian => {
                    let (emaj, emin, angle) = (
                        c.gauss_shape[3 * s],
                        c.gauss_shape[3 * s + 1],
                        c.gauss_shape[3 * s + 2],
                    );
                    let er = emin / if emaj == 0.0 { 1.0 } else { emaj };
                    (emaj * angle.sin(), emaj * angle.cos(), er)
                }
            };
            for r in 0..nrow {
                let (u, v, w) = (uvw[3 * r], uvw[3 * r + 1], uvw[3 * r + 2]);
                let real_phase = TWO_PI_OVER_C * (u * l + v * m + w * n);
                let row = &mut vis[r * nchan..(r + 1) * nchan];
                match c.kind[s] {
                    Kind::Point => {
                        for (f, out) in row.iter_mut().enumerate() {
                            let p = real_phase * frequency[f];
                            let re = p.cos() * spec[f];
                            let im = p.sin() * spec[f];
                            *out = *out + C64::new(re, im);
                        }
                    }
                    Kind::Gaussian => {
                        let u1 = (u * em - v * el) * er;
                        let v1 = u * el + v * em;
                        for (f, out) in row.iter_mut().enumerate() {
                            let p = real_phase * frequency[f];
                            let mut re = p.cos() * spec[f];
                            let mut im = p.sin() * spec[f];
                            let fu1 = u1 * scaled_freq[f];
                            let fv1 = v1 * scaled_freq[f];
                            let shape = (-(fu1 * fu1 + fv1 * fv1)).exp();
                            re *= shape;
                            im *= shape;
                            *out = *out + C64::new(re, im);
                        }
                    }
                }
            }
        }
        Ok(vis)
    }

    fn single(l: f64, m: f64, shape: [f64; 3]) -> (Vec<f64>, Vec<f64>) {
        (vec![l, m], shape.to_vec())
    }

    /// xorshift64*, deterministic test inputs.
    struct Rng(u64);
    impl Rng {
        fn next(&mut self) -> f64 {
            self.0 ^= self.0 >> 12;
            self.0 ^= self.0 << 25;
            self.0 ^= self.0 >> 27;
            (self.0.wrapping_mul(0x2545_F491_4F6C_DD1D) >> 11) as f64 / (1u64 << 53) as f64
        }
        fn range(&mut self, a: f64, b: f64) -> f64 {
            a + (b - a) * self.next()
        }
    }

    struct Case {
        uvw: Vec<f64>,
        freq: Vec<f64>,
        lm: Vec<f64>,
        kind: Vec<Kind>,
        flux: Vec<f64>,
        coeffs: Vec<f64>,
        ncoeff: usize,
        log_poly: Vec<bool>,
        ref_freq: Vec<f64>,
        gauss_shape: Vec<f64>,
    }

    impl Case {
        fn new(seed: u64, nrow: usize, nchan: usize, nsrc: usize, ncoeff: usize) -> Self {
            let mut g = Rng(seed);
            let uvw = (0..3 * nrow).map(|_| g.range(-8000., 8000.)).collect();
            let freq = (0..nchan)
                .map(|k| 544e6 + 544e6 * k as f64 / nchan.max(1) as f64)
                .collect();
            let lm = (0..2 * nsrc).map(|_| g.range(-0.02, 0.02)).collect();
            let kind = (0..nsrc)
                .map(|_| {
                    if g.next() < 0.5 {
                        Kind::Point
                    } else {
                        Kind::Gaussian
                    }
                })
                .collect();
            let flux = (0..nsrc).map(|_| g.range(-0.5, 2.0)).collect();
            let coeffs = (0..nsrc * ncoeff).map(|_| g.range(-1.0, 0.5)).collect();
            let log_poly = (0..nsrc).map(|_| g.next() < 0.5).collect();
            let ref_freq = (0..nsrc).map(|_| g.range(5e8, 1.5e9)).collect();
            let gauss_shape = (0..nsrc)
                .flat_map(|s| {
                    let emaj = if s % 7 == 0 { 0.0 } else { g.range(0., 1e-4) };
                    [emaj, g.range(0., 1e-4), g.range(0., 3.2)]
                })
                .collect();
            Self {
                uvw,
                freq,
                lm,
                kind,
                flux,
                coeffs,
                ncoeff,
                log_poly,
                ref_freq,
                gauss_shape,
            }
        }
        fn components(&self) -> Components<'_> {
            Components {
                lm: &self.lm,
                kind: &self.kind,
                flux: &self.flux,
                coeffs: &self.coeffs,
                ncoeff: self.ncoeff,
                log_poly: &self.log_poly,
                ref_freq: &self.ref_freq,
                gauss_shape: &self.gauss_shape,
            }
        }
    }

    fn bits(vis: &[C64]) -> Vec<u64> {
        vis.iter()
            .flat_map(|z| [z.re.to_bits(), z.im.to_bits()])
            .collect()
    }

    #[test]
    fn parallel_blocks_equal_the_single_threaded_loop_bit_for_bit() {
        // Shapes: rows below, at and not a multiple of the block, mixed kinds,
        // both spectrum kinds, ncoeff 1 to 3, and the empty cases.
        let shapes = [
            (1, 37, 19, 11, 2),
            (2, 5, 64, 9, 1),
            (3, 8, 7, 23, 3),
            (4, 101, 33, 6, 2),
            (5, 0, 16, 4, 1),
            (6, 12, 0, 4, 1),
            (7, 9, 16, 0, 1),
        ];
        for (seed, nrow, nchan, nsrc, ncoeff) in shapes {
            let case = Case::new(seed, nrow, nchan, nsrc, ncoeff);
            let c = case.components();
            let want = bits(&reference(&case.uvw, &case.freq, &c).unwrap());
            for threads in [1, 2, 8, 16] {
                for block in [1, 3, BLOCK_ROWS, 13, 256] {
                    let mut vis = vec![f64::NAN; 2 * nrow * nchan];
                    let spec =
                        predict_into_blocks(&case.uvw, &case.freq, &c, threads, block, &mut vis)
                            .unwrap();
                    let got: Vec<u64> = vis.iter().map(|x| x.to_bits()).collect();
                    assert_eq!(got, want, "seed {seed} threads {threads} block {block}");
                    assert_eq!(spec, spectra(&c, &case.freq).unwrap());
                }
            }
            assert_eq!(bits(&predict(&case.uvw, &case.freq, &c).unwrap()), want);
        }
    }

    #[test]
    fn predict_into_checks_lengths() {
        let case = Case::new(1, 4, 3, 2, 1);
        let c = case.components();
        let mut short = vec![0.0; 2 * 4 * 3 - 1];
        assert!(predict_into(&case.uvw, &case.freq, &c, 0, &mut short).is_err());
        let mut vis = vec![0.0; 2 * 4 * 3];
        assert!(predict_into_blocks(&case.uvw, &case.freq, &c, 0, 0, &mut vis).is_err());
        assert!(predict_into(&case.uvw[..11], &case.freq, &c, 0, &mut vis).is_err());
    }

    /// Timing at the UHF model's shape (point components, ordinary
    /// polynomials, 4,096 channels): `cargo test --release -p rang-core
    /// predict::tests::bench -- --ignored --nocapture`, with
    /// `RANG_PREDICT_BENCH=rows,nsrc,threads,...` to change the shape.
    #[test]
    #[ignore]
    fn bench() {
        let spec = std::env::var("RANG_PREDICT_BENCH").unwrap_or("64,7779,1,8,16".into());
        let v: Vec<usize> = spec.split(',').map(|x| x.trim().parse().unwrap()).collect();
        let (nrow, nsrc, nchan) = (v[0], v[1], 4096);
        let mut case = Case::new(42, nrow, nchan, nsrc, 2);
        case.kind.iter_mut().for_each(|k| *k = Kind::Point);
        case.log_poly.iter_mut().for_each(|x| *x = false);
        let c = case.components();
        let terms = (nrow * nchan * nsrc) as f64;
        // RANG_PREDICT_BENCH_OLD=0 skips the old loop and the bitwise check.
        let old = std::env::var("RANG_PREDICT_BENCH_OLD").map_or(true, |x| x != "0");
        let want = old.then(|| {
            let t = std::time::Instant::now();
            let want = reference(&case.uvw, &case.freq, &c).unwrap();
            let dt = t.elapsed().as_secs_f64();
            println!("old 1 thread: {dt:.2} s, {:.2} ns/term", dt * 1e9 / terms);
            bits(&want)
        });
        for &threads in &v[2..] {
            let mut vis = vec![0.0; 2 * nrow * nchan];
            let t = std::time::Instant::now();
            predict_into(&case.uvw, &case.freq, &c, threads, &mut vis).unwrap();
            let dt = t.elapsed().as_secs_f64();
            let same = want
                .as_ref()
                .map(|w| vis.iter().map(|x| x.to_bits()).collect::<Vec<_>>() == *w);
            println!(
                "new {threads} threads: {dt:.2} s, {:.2} ns/term, {:.2} ns/term x threads, bitwise {same:?}",
                dt * 1e9 / terms,
                dt * 1e9 * threads as f64 / terms
            );
            assert_ne!(same, Some(false));
        }
    }

    #[test]
    fn phase_centre_point_is_its_spectrum() {
        let (lm, shape) = single(0., 0., [0.; 3]);
        let c = Components {
            lm: &lm,
            kind: &[Kind::Point],
            flux: &[2.0],
            coeffs: &[-0.7],
            ncoeff: 1,
            log_poly: &[true],
            ref_freq: &[1e9],
            gauss_shape: &shape,
        };
        let freq = [1e9, 2e9];
        let vis = predict(&[100., -50., 3., 0., 0., 0.], &freq, &c).unwrap();
        let expected = 2.0 * 2.0_f64.powf(-0.7);
        assert!((vis[0].re - 2.0).abs() < 1e-15 && vis[0].im.abs() < 1e-15);
        assert!((vis[1].re - expected).abs() < 1e-14);
    }

    #[test]
    fn ordinary_polynomial_spectrum() {
        let (lm, shape) = single(0., 0., [0.; 3]);
        let c = Components {
            lm: &lm,
            kind: &[Kind::Point],
            flux: &[1.0],
            coeffs: &[0.5, 0.25],
            ncoeff: 2,
            log_poly: &[false],
            ref_freq: &[1e9],
            gauss_shape: &shape,
        };
        let s = spectra(&c, &[2e9]).unwrap();
        assert!((s[0] - (1.0 + 0.5 + 0.25)).abs() < 1e-15);
    }

    #[test]
    fn point_phase_and_gaussian_envelope() {
        let l = 1e-3;
        let uvw = [1000.0, 0.0, 0.0];
        let freq = [1e9];
        let lm = [l, 0.];
        let width = 2e-4;
        let shape = [width, width, 0.];
        let point = Components {
            lm: &lm,
            kind: &[Kind::Point],
            flux: &[1.0],
            coeffs: &[0.0],
            ncoeff: 1,
            log_poly: &[true],
            ref_freq: &[1e9],
            gauss_shape: &[0.; 3],
        };
        let gauss = Components {
            kind: &[Kind::Gaussian],
            gauss_shape: &shape,
            ..point
        };
        let p = predict(&uvw, &freq, &point).unwrap()[0];
        let g = predict(&uvw, &freq, &gauss).unwrap()[0];
        let phase = TWO_PI_OVER_C * 1000.0 * l * 1e9;
        assert!((p.re - phase.cos()).abs() < 1e-14 && (p.im - phase.sin()).abs() < 1e-14);
        // Circular Gaussian visibility: exp(-pi^2 w^2 (u/lambda)^2 / (4 ln 2)).
        let u_lambda = 1000.0 * 1e9 / LIGHTSPEED;
        let envelope = (-(std::f64::consts::PI.powi(2)) * width * width * u_lambda * u_lambda
            / (4.0 * 2.0_f64.ln()))
        .exp();
        assert!((g.re - envelope * phase.cos()).abs() < 1e-14);
    }
}
