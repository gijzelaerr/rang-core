//! A measurement with reusable buffers, optionally gridding in single
//! precision, for gemclean's major cycles.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! [`GridMeasurement<f64>`] is the arithmetic of
//! [`crate::clean_certified::WgridMeasurement`] with the visibility buffer
//! kept between calls and the empty-model predict skipped.
//! [`GridMeasurement<f32>`] holds the data in `f32` and runs the same gridder
//! in single precision, as WSClean does: half the memory traffic, a coarser
//! floor. The misfit is still summed in `f64`, and the minor cycle's step is
//! still exact for the image-domain beam; the larger floor shows up in the
//! measured Gram gap, which the major cycle records. The default of the
//! binary stays `f64`.

use crate::clean_certified::{Complex, Measurement};
use crate::wgridder::{self, Options, Prepared, Real, VisData, Weights};
use rayon::prelude::*;
use std::sync::Mutex;

/// The measurement operator in precision `T`.
pub struct GridMeasurement<T: Real> {
    uvw: Vec<f64>,
    freq: Vec<f64>,
    vis: Vec<Complex<T>>,
    /// Weights normalised to sum to one.
    wgt: Vec<T>,
    opts: Options,
    /// The plan and layout of the image grid, reused by every major cycle.
    prepared: Option<Prepared<T>>,
    buffer: Mutex<Vec<Complex<T>>>,
}

impl<T: Real + Send + Sync> GridMeasurement<T> {
    /// `wgt` is normalised here; `vis` and `wgt` are `nrow × nchan`.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        uvw: Vec<f64>,
        freq: Vec<f64>,
        vis: Vec<Complex<f64>>,
        wgt: Vec<f64>,
        side: usize,
        cell: f64,
        epsilon: f64,
        opts: Options,
    ) -> Result<GridMeasurement<T>, String> {
        let nrow = uvw.len() / 3;
        if vis.len() != nrow * freq.len() || wgt.len() != vis.len() {
            return Err("vis and wgt must be nrow * nchan".into());
        }
        let sum: f64 = wgt.iter().sum();
        if sum <= 0.0 || sum.is_nan() {
            return Err("weights must have a positive sum".into());
        }
        let wgt: Vec<T> = wgt.iter().map(|w| T::of(w / sum)).collect();
        let opts = Options {
            nx: side,
            ny: side,
            pixsize_x: cell,
            pixsize_y: cell,
            epsilon,
            ..opts
        };
        let prepared = Some(Prepared::new(&opts, &uvw, &freq, T::weights(&wgt))?);
        Ok(GridMeasurement {
            uvw,
            freq,
            vis: vis
                .iter()
                .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
                .collect(),
            wgt,
            opts,
            prepared,
            buffer: Mutex::new(Vec::new()),
        })
    }

    /// Plan every gridder call afresh (for comparison; the images agree to
    /// the rounding of the tile order at most).
    pub fn without_plan_reuse(mut self) -> Self {
        self.prepared = None;
        self
    }

    /// Bytes held, by buffer (for the memory report).
    pub fn memory(&self) -> Vec<(&'static str, usize)> {
        use crate::gemclean::memory::bytes_of;
        let mut out = vec![
            ("measurement: visibilities", bytes_of(&self.vis)),
            ("measurement: weights", bytes_of(&self.wgt)),
            ("measurement: uvw", bytes_of(&self.uvw)),
            (
                "measurement: residual visibilities",
                bytes_of(&self.buffer.lock().expect("no panic while predicting")),
            ),
        ];
        if let Some(p) = &self.prepared {
            out.extend(p.memory());
        }
        out
    }

    /// Half-spectrum columns of a `side × side` image of this cell that the
    /// measurement can reach: the longest baseline at the highest frequency,
    /// plus the most the w-term moves it at the corner of the image, plus a
    /// few columns for the window's edge.
    pub fn band_columns(&self, side: usize) -> usize {
        const MARGIN: usize = 8;
        const SPEED_OF_LIGHT: f64 = 299_792_458.0;
        let cell = self.opts.pixsize_x.max(self.opts.pixsize_y);
        let fmax = self.freq.iter().fold(0.0_f64, |a, &f| a.max(f.abs()));
        let (mut reach, mut wmax) = (0.0_f64, 0.0_f64);
        for c in self.uvw.chunks_exact(3) {
            reach = reach.max(c[0].abs()).max(c[1].abs());
            wmax = wmax.max(c[2].abs());
        }
        if self.opts.do_wgridding {
            let l = std::f64::consts::SQRT_2 * 0.5 * side as f64 * cell;
            if l >= 1.0 {
                return side / 2 + 1;
            }
            reach += wmax * l / (1.0 - l * l).sqrt();
        }
        let columns = (reach * fmax / SPEED_OF_LIGHT * cell * side as f64).ceil() as usize;
        (columns + MARGIN).min(side / 2 + 1)
    }

    /// The PSF on a `side × side` grid of the same cell, centred on
    /// `(side/2, side/2)`, widened to `f64`.
    pub fn psf_image(&self, side: usize) -> Result<Vec<f64>, String> {
        self.psf_image_with(side, self.opts.do_wgridding)
    }

    /// [`GridMeasurement::psf_image`] with or without the w-term.
    pub fn psf_image_with(&self, side: usize, wgridding: bool) -> Result<Vec<f64>, String> {
        let mut out = vec![T::of(0.0); side * side];
        wgridder::vis2dirty_multi(
            &Options {
                nx: side,
                ny: side,
                do_wgridding: wgridding,
                ..self.opts
            },
            &self.uvw,
            &self.freq,
            VisData::Unit,
            T::weights(&self.wgt),
            None,
            None::<&mut [T]>,
            Some(&mut out),
        )?;
        Ok(widen(&out))
    }

    fn image(&self, vis: &[Complex<T>]) -> Result<Vec<f64>, String> {
        let mut out = vec![T::of(0.0); self.opts.nx * self.opts.ny];
        match &self.prepared {
            Some(p) => {
                p.vis2dirty(T::vis_data(vis), T::weights(&self.wgt), &mut out)?;
            }
            None => {
                wgridder::vis2dirty(
                    &self.opts,
                    &self.uvw,
                    &self.freq,
                    vis,
                    Some(&self.wgt),
                    None,
                    &mut out,
                )?;
            }
        }
        Ok(widen(&out))
    }

    fn predict_into(&self, model: &[f64], out: &mut [Complex<T>]) -> Result<(), String> {
        let m: Vec<T> = model.par_iter().map(|&c| T::of(c)).collect();
        match &self.prepared {
            // Visibilities of zero weight are not predicted: nothing reads them.
            Some(p) => p.dirty2vis(&m, Weights::None, out)?,
            None => wgridder::dirty2vis(&self.opts, &self.uvw, &self.freq, &m, None, None, out)?,
        };
        Ok(())
    }
}

fn widen<T: Real + Send + Sync>(x: &[T]) -> Vec<f64> {
    x.par_iter().map(|v| v.to()).collect()
}

impl<T: Real + Send + Sync> Measurement for GridMeasurement<T> {
    fn side(&self) -> usize {
        self.opts.nx
    }

    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        let mut guard = self.buffer.lock().expect("no panic while predicting");
        guard.resize(self.vis.len(), Complex::new(T::of(0.0), T::of(0.0)));
        let e = guard.as_mut_slice();
        if model.par_iter().any(|&c| c != 0.0) {
            self.predict_into(model, e)?;
            e.par_iter_mut()
                .zip(self.vis.par_iter())
                .for_each(|(p, v)| *p = *v - *p);
        } else {
            e.par_iter_mut()
                .zip(self.vis.par_iter())
                .for_each(|(p, v)| *p = *v);
        }
        // In f64, so the misfit keeps its digits in either precision; serial,
        // so it does not depend on the thread count.
        let mut q = 0.0;
        for (d, w) in e.iter().zip(&self.wgt) {
            let (re, im) = (d.re.to(), d.im.to());
            q += w.to() * (re * re + im * im);
        }
        crate::gemclean::memory::mark("residual: predict");
        let image = self.image(e)?;
        crate::gemclean::memory::mark("residual: grid");
        Ok((image, 0.5 * q))
    }

    fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
        let mut guard = self.buffer.lock().expect("no panic while predicting");
        guard.resize(self.vis.len(), Complex::new(T::of(0.0), T::of(0.0)));
        self.predict_into(x, guard.as_mut_slice())?;
        self.image(guard.as_slice())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clean_certified::WgridMeasurement;

    /// `-beam-band`: on oversampled pixels the columns from the geometry hold
    /// the PSF's spectrum. What the band drops is the slow tail that the edge
    /// of the 2n box spreads over every column, which more columns barely
    /// reduce, while ten fewer cut the beam itself. On coarse pixels the band
    /// is the whole half spectrum.
    #[test]
    fn band_columns_hold_the_psf_spectrum() {
        use crate::gemclean::Convolver;
        let mut state = 99u64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        };
        let nrow = 1200;
        let uvw: Vec<f64> = (0..3 * nrow)
            .map(|i| next() * if i % 3 == 2 { 50.0 } else { 3000.0 })
            .collect();
        let freq = vec![299_792_458.0];
        let opts = crate::gemclean::sim::imaging_options();
        let n = 48usize;
        let vis = vec![Complex::new(0.0, 0.0); nrow];
        let wgt = vec![1.0; nrow];
        let fine: GridMeasurement<f64> = GridMeasurement::new(
            uvw.clone(),
            freq.clone(),
            vis.clone(),
            wgt.clone(),
            n,
            5e-5,
            1e-7,
            opts,
        )
        .unwrap();
        let band = fine.band_columns(2 * n);
        // Longest baseline 1500 wavelengths: ceil(1500 × 5e-5 × 96) = 8, plus the margin.
        assert!((16..=17).contains(&band), "band {band}");
        let psf = fine.psf_image(2 * n).unwrap();
        let peak = psf.iter().fold(0.0_f64, |a, &v| a.max(v.abs()));
        let kept = Convolver::with_band(n, &psf, band).unwrap();
        assert_eq!(kept.columns(), (band, n + 1));
        let dropped = |k| Convolver::with_band(n, &psf, k).unwrap().dropped_rms();
        let (inside, wider) = (dropped(band - 10), dropped(band + 16));
        assert!(kept.dropped_rms() < 5e-3 * peak, "{}", kept.dropped_rms());
        assert!(inside > 10.0 * kept.dropped_rms(), "{inside}");
        assert!(kept.dropped_rms() < 2.0 * wider, "{wider}");
        let coarse: GridMeasurement<f64> =
            GridMeasurement::new(uvw, freq, vis, wgt, n, 4e-4, 1e-7, opts).unwrap();
        assert_eq!(coarse.band_columns(2 * n), n + 1);
    }

    /// The regression test of the reduced-precision path: with the gridder in
    /// `f32` every component's amplitude still comes from the exact value on
    /// the image-domain beam (lazy against brute force to rounding, in f64),
    /// so the one-step identity holds for that beam, each step predicts its
    /// exact decrease, and only the measured gap sees the coarser operator.
    /// The components and the misfit stay close to the f64 reference run.
    #[test]
    fn single_precision_keeps_the_amplitudes_exact() {
        use crate::gemclean::{Beam, Settings, run};
        let mut state = 321u64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        };
        let nrow = 1500;
        let uvw: Vec<f64> = (0..3 * nrow)
            .map(|i| next() * if i % 3 == 2 { 50.0 } else { 3000.0 })
            .collect();
        let freq = vec![299_792_458.0];
        let (n, cell, eps) = (48usize, 1.5e-4, 1e-5);
        let opts = crate::gemclean::sim::imaging_options();
        let wgt = vec![1.0; nrow];
        let mut truth = vec![0.0; n * n];
        truth[9 * n + 33] = 1.0;
        truth[31 * n + 7] = -0.4;
        truth[20 * n + 20] = 0.15;
        let vis = WgridMeasurement::new(
            uvw.clone(),
            freq.clone(),
            vec![Complex::new(0.0, 0.0); nrow],
            wgt.clone(),
            n,
            cell,
            1e-9,
            opts,
        )
        .unwrap()
        .predict(&truth)
        .unwrap();
        let settings = Settings {
            threshold: 2e-3,
            max_components: 2000,
            audit: true,
            ..Settings::default()
        };
        let double: GridMeasurement<f64> = GridMeasurement::new(
            uvw.clone(),
            freq.clone(),
            vis.clone(),
            wgt.clone(),
            n,
            cell,
            eps,
            opts,
        )
        .unwrap();
        let beam = Beam::from_double(n, &double.psf_image(2 * n).unwrap(), 6).unwrap();
        let reference = run(&double, &beam, &settings, None).unwrap();
        let single: GridMeasurement<f32> =
            GridMeasurement::new(uvw, freq, vis, wgt, n, cell, eps, opts).unwrap();
        let beam = Beam::from_double(n, &single.psf_image(2 * n).unwrap(), 6).unwrap();
        let reduced = run(&single, &beam, &settings, None).unwrap();
        assert!(reference.steps.len() > 30);
        for out in [&reference, &reduced] {
            assert!(out.audit_max_error.unwrap() < 1e-11);
            let decrease = 0.1 * 1.9 / 2.0;
            let predicted: f64 = out.steps.iter().map(|s| decrease * s.peak * s.peak).sum();
            let total: f64 = out.cycles.iter().map(|c| -c.dq_predicted).sum();
            assert!((predicted - total).abs() < 1e-3 * total);
            for c in &out.cycles {
                assert!(c.gap.abs() < 1e-3 * c.q_before.max(1e-3), "gap {}", c.gap);
            }
        }
        // The science, within the stated tolerance.
        assert!((reduced.q_final - reference.q_final).abs() < 1e-5 * reference.q0);
        let flux = |o: &crate::gemclean::Outcome| o.model.iter().sum::<f64>();
        assert!((flux(&reduced) - flux(&reference)).abs() < 2e-2);
    }

    #[test]
    fn f64_path_equals_the_certified_measurement_and_f32_is_close() {
        let mut state = 123u64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        };
        let nrow = 800;
        let uvw: Vec<f64> = (0..3 * nrow).map(|_| next() * 3000.0).collect();
        let freq = vec![299_792_458.0];
        let vis: Vec<Complex<f64>> = (0..nrow).map(|_| Complex::new(next(), next())).collect();
        let wgt: Vec<f64> = (0..nrow).map(|_| 0.5 + next().abs()).collect();
        let (n, cell, eps) = (48usize, 1.5e-4, 1e-5);
        let opts = crate::gemclean::sim::imaging_options();
        let reference = WgridMeasurement::new(
            uvw.clone(),
            freq.clone(),
            vis.clone(),
            wgt.clone(),
            n,
            cell,
            eps,
            opts,
        )
        .unwrap();
        let double: GridMeasurement<f64> = GridMeasurement::new(
            uvw.clone(),
            freq.clone(),
            vis.clone(),
            wgt.clone(),
            n,
            cell,
            eps,
            opts,
        )
        .unwrap();
        let single: GridMeasurement<f32> =
            GridMeasurement::new(uvw, freq, vis, wgt, n, cell, eps, opts).unwrap();
        let mut model = vec![0.0; n * n];
        model[5 * n + 30] = 1.25;
        model[40 * n + 2] = -0.5;
        for m in [vec![0.0; n * n], model] {
            let (a, qa) = reference.residual(&m).unwrap();
            let (b, qb) = double.residual(&m).unwrap();
            let (c, qc) = single.residual(&m).unwrap();
            assert_eq!(a, b);
            assert_eq!(qa.to_bits(), qb.to_bits());
            assert!((qa - qc).abs() <= 1e-5 * qa, "{qa} against {qc}");
            let peak = a.iter().fold(0.0_f64, |x, v| x.max(v.abs()));
            for (x, y) in a.iter().zip(&c) {
                assert!((x - y).abs() <= 2e-3 * peak, "{x} against {y}");
            }
        }
        assert_eq!(
            reference.psf_image(2 * n).unwrap(),
            double.psf_image(2 * n).unwrap()
        );
    }
}
