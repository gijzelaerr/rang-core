//! Flux-density standards: per-channel evaluation of log-polynomial spectra.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Task FS1 (`research/fs1-flux-standards.md`). The standards' coefficient
//! tables, source names, validity ranges and refusals live in the canonical
//! Python module `rang.fluxstd`; this kernel evaluates one piece of a
//! standard, `log10 S = sum_k a_k (log10(nu / unit))^k`, over many
//! frequencies, and the piecewise form used by Stevens-Reynolds 2016. The
//! coefficients are published facts (Perley & Butler 2017; Reynolds 1994) or
//! values recovered from CASA `setjy` outputs; no CASA source is copied.

/// One polynomial piece, valid for `lo_hz <= nu < hi_hz`.
#[derive(Clone, Debug, PartialEq)]
pub struct Piece<'a> {
    pub lo_hz: f64,
    pub hi_hz: f64,
    /// Frequency unit of the logarithm, in Hz (1e9 for GHz, 1e6 for MHz, or
    /// a reference frequency for CASA's `manual` form).
    pub unit_hz: f64,
    /// `a_0, a_1, ...` of `log10 S = sum_k a_k x^k`, `x = log10(nu/unit)`.
    pub coeffs: &'a [f64],
}

/// `log10 S` at one frequency, Horner in `x = log10(nu / unit)`.
pub fn log10_flux(coeffs: &[f64], unit_hz: f64, nu_hz: f64) -> f64 {
    let x = (nu_hz / unit_hz).log10();
    coeffs.iter().rev().fold(0.0, |acc, &a| acc * x + a)
}

/// Stokes I in Jy at each frequency for one polynomial piece.
pub fn log10_poly(coeffs: &[f64], unit_hz: f64, freq_hz: &[f64]) -> Result<Vec<f64>, &'static str> {
    if coeffs.is_empty() {
        return Err("no coefficients");
    }
    if !(unit_hz > 0.0 && unit_hz.is_finite()) {
        return Err("frequency unit must be positive and finite");
    }
    if freq_hz.iter().any(|&f| !(f > 0.0 && f.is_finite())) {
        return Err("frequencies must be positive and finite");
    }
    Ok(freq_hz
        .iter()
        .map(|&nu| 10f64.powf(log10_flux(coeffs, unit_hz, nu)))
        .collect())
}

/// Stokes I for a piecewise standard: each frequency takes the piece whose
/// `[lo_hz, hi_hz)` contains it; a frequency outside every piece is an error
/// (the Python layer decides about extrapolation by widening the pieces).
pub fn piecewise(pieces: &[Piece], freq_hz: &[f64]) -> Result<Vec<f64>, &'static str> {
    if pieces.is_empty() {
        return Err("no pieces");
    }
    let mut out = Vec::with_capacity(freq_hz.len());
    for &nu in freq_hz {
        let piece = pieces
            .iter()
            .find(|p| p.lo_hz <= nu && nu < p.hi_hz)
            .ok_or("frequency outside every piece")?;
        out.push(log10_poly(piece.coeffs, piece.unit_hz, &[nu])?[0]);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Reynolds 1994 for PKS 1934-638 (ATNF memo AT/39.3/040, as carried by
    // CARACal's southern_calibrators.txt), log10 S against log10(nu/MHz).
    const REYNOLDS_1994: [f64; 4] = [-30.7667, 26.4908, -7.0977, 0.605334];
    // Perley & Butler 2017, Table 5, 3C286 (log10 nu/GHz).
    const PB2017_3C286: [f64; 4] = [1.2481, -0.4507, -0.1798, 0.0357];

    fn rel(a: f64, b: f64) -> f64 {
        ((a - b) / b).abs()
    }

    #[test]
    fn single_term_is_constant() {
        let s = log10_poly(&[1.0], 1e9, &[0.5e9, 1e9, 7e9]).unwrap();
        assert!(s.iter().all(|&v| rel(v, 10.0) < 1e-15));
    }

    #[test]
    fn a0_is_flux_at_unit() {
        let s = log10_poly(&PB2017_3C286, 1e9, &[1e9]).unwrap()[0];
        assert!(rel(s, 10f64.powf(1.2481)) < 1e-15);
    }

    #[test]
    fn horner_matches_direct_sum() {
        let freq: Vec<f64> = (0..50).map(|k| 0.05e9 * 1.15f64.powi(k)).collect();
        let s = log10_poly(&REYNOLDS_1994, 1e6, &freq).unwrap();
        for (nu, v) in freq.iter().zip(&s) {
            let y = (nu / 1e6).log10();
            let direct: f64 = REYNOLDS_1994
                .iter()
                .enumerate()
                .map(|(k, a)| a * y.powi(k as i32))
                .sum();
            assert!(rel(*v, 10f64.powf(direct)) < 1e-12, "{nu}");
        }
    }

    #[test]
    fn reynolds_1934_at_1400_mhz() {
        // CARACal's manual model is 14.907688923 Jy at 1.4 GHz, fitted to
        // this polynomial (research/o-casa.md).
        let s = log10_poly(&REYNOLDS_1994, 1e6, &[1.4e9]).unwrap()[0];
        assert!(rel(s, 14.907688923) < 1e-6, "{s}");
    }

    #[test]
    fn unit_change_is_exact_reexpression() {
        // log10(nu/MHz) = log10(nu/GHz) + 3: the GHz form of a MHz polynomial.
        let y0 = 3.0f64;
        let a = REYNOLDS_1994;
        let ghz = [
            a[0] + a[1] * y0 + a[2] * y0 * y0 + a[3] * y0.powi(3),
            a[1] + 2.0 * a[2] * y0 + 3.0 * a[3] * y0 * y0,
            a[2] + 3.0 * a[3] * y0,
            a[3],
        ];
        let freq = [0.9e9, 1.284e9, 1.7e9];
        let s1 = log10_poly(&a, 1e6, &freq).unwrap();
        let s2 = log10_poly(&ghz, 1e9, &freq).unwrap();
        for (x, y) in s1.iter().zip(&s2) {
            assert!(rel(*x, *y) < 1e-11);
        }
    }

    #[test]
    fn piecewise_selects_and_refuses() {
        let lo = [1.0];
        let hi = [2.0];
        let pieces = [
            Piece {
                lo_hz: 1e8,
                hi_hz: 11e9,
                unit_hz: 1e9,
                coeffs: &lo,
            },
            Piece {
                lo_hz: 11e9,
                hi_hz: 5e10,
                unit_hz: 1e9,
                coeffs: &hi,
            },
        ];
        let s = piecewise(&pieces, &[1e9, 10.999e9, 11e9, 4e10]).unwrap();
        assert_eq!(
            s.iter().map(|v| v.round()).collect::<Vec<_>>(),
            [10.0, 10.0, 100.0, 100.0]
        );
        assert!(piecewise(&pieces, &[5e10]).is_err());
        assert!(piecewise(&pieces, &[5e7]).is_err());
    }

    fn f32s(values: &[f32]) -> Vec<f64> {
        values.iter().map(|&v| v as f64).collect()
    }

    #[test]
    fn matches_casa_setjy_doubles() {
        // CASA 6.7.6 setjy `fluxd` (FS1 oracle run outputs/fs1-20261030-01);
        // CASA stores its compiled coefficients as float32.
        let pb2010_3c286 = f32s(&[1.2361, -0.4127, -0.1864, 0.0294]);
        let baars_3c286 = f32s(&[1.480, 0.292, -0.124]);
        let reynolds = f32s(&[1.170418, 0.248618, -1.649694, 0.605334]);
        let stevens_cubic = f32s(&[-2.5739, 10.0707, -10.0595, 2.9372]);
        let stevens_2016 = f32s(&[1.7581, -1.3763]);
        let piece = |lo_hz, hi_hz, coeffs| Piece {
            lo_hz,
            hi_hz,
            unit_hz: 1e9,
            coeffs,
        };
        let sr2016 = [
            piece(0.0, 11.1496e9, &reynolds[..]),
            piece(11.1496e9, f64::INFINITY, &stevens_2016[..]),
        ];
        let pb2010_1934 = [
            piece(0.0, 10.000_000_001e9, &reynolds[..]),
            piece(10.000_000_001e9, f64::INFINITY, &stevens_cubic[..]),
        ];
        let cases = [
            (
                log10_poly(&pb2010_3c286, 1e9, &[50e6]).unwrap()[0],
                24.704394517681834,
            ),
            (
                log10_poly(&pb2010_3c286, 1e9, &[1670242492.0]).unwrap()[0],
                13.653146466935462,
            ),
            (
                log10_poly(&baars_3c286, 1e6, &[1e9]).unwrap()[0],
                17.378009265360465,
            ),
            (piecewise(&sr2016, &[1e9]).unwrap()[0], 14.80532768603299),
            (
                piecewise(&sr2016, &[35984283650.0]).unwrap()[0],
                0.4134489914560951,
            ),
            (
                piecewise(&pb2010_1934, &[14967886474.0]).unwrap()[0],
                1.3657682064671135,
            ),
        ];
        for (port, casa) in cases {
            assert!(rel(port, casa) < 1e-13, "{port} {casa}");
        }
    }

    #[test]
    fn rejects_bad_input() {
        assert!(log10_poly(&[], 1e9, &[1e9]).is_err());
        assert!(log10_poly(&[1.0], 0.0, &[1e9]).is_err());
        assert!(log10_poly(&[1.0], 1e9, &[-1.0]).is_err());
        assert!(log10_poly(&[1.0], 1e9, &[f64::NAN]).is_err());
    }
}
