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
//! The translation and its integration are part of Rang (GPL-3.0-or-later).
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

/// `wsclean_predict`: (nrow, nchan) Stokes I visibilities.
pub fn predict(uvw: &[f64], frequency: &[f64], c: &Components) -> Result<Vec<C64>, &'static str> {
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

#[cfg(test)]
mod tests {
    use super::*;

    fn single(l: f64, m: f64, shape: [f64; 3]) -> (Vec<f64>, Vec<f64>) {
        (vec![l, m], shape.to_vec())
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
