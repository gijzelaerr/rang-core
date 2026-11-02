//! Simulated MeerKAT Measurement Sets for gmclean's experiments and profiles.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The array is the 64 antennas of `data/meerkat.itrf.txt`, the track
//! symmetric about transit. The visibilities are `dirty2vis` of a pixel model
//! with the flips the imager uses: an inverse crime by construction, kept
//! because these experiments measure a deconvolver's arithmetic and cost, not
//! its recovery of off-grid emission. The sky is defined by pixels, so the
//! UVW sign (antenna 1 minus antenna 2 here) has no physical meaning beyond
//! this consistency. The noise is Gaussian, `noise_sigma` Jy per real and
//! imaginary part of each correlation (XY and YX carry noise only).

use super::input::{self, MsArrays};
use crate::clean_certified::{Complex, WgridMeasurement};
use crate::wgridder::Options;
use std::f64::consts::PI;
use std::path::Path;

/// A fixed-seed xorshift generator.
pub struct Rng(pub u64);

impl Rng {
    pub fn uniform(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 11) as f64 / (1u64 << 53) as f64
    }

    pub fn normal(&mut self) -> f64 {
        let u = self.uniform().max(1e-300);
        let v = self.uniform();
        (-2.0 * u.ln()).sqrt() * (2.0 * PI * v).cos()
    }
}

/// MeerKAT antenna positions, ITRF metres.
pub fn antennas() -> Vec<[f64; 3]> {
    include_str!("../../../data/meerkat.itrf.txt")
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| {
            let f: Vec<f64> = line
                .split_whitespace()
                .take(3)
                .map(|v| v.parse().expect("ITRF coordinate"))
                .collect();
            [f[0], f[1], f[2]]
        })
        .collect()
}

/// ITRF to east-north-up about the array centroid, and its latitude.
pub fn enu(itrf: &[[f64; 3]]) -> (Vec<[f64; 3]>, f64) {
    let n = itrf.len() as f64;
    let c = itrf.iter().fold([0.0; 3], |acc, p| {
        [acc[0] + p[0] / n, acc[1] + p[1] / n, acc[2] + p[2] / n]
    });
    let lon = c[1].atan2(c[0]);
    let lat = c[2].atan2((c[0] * c[0] + c[1] * c[1]).sqrt());
    let (sl, cl) = lon.sin_cos();
    let (sp, cp) = lat.sin_cos();
    let positions = itrf
        .iter()
        .map(|p| {
            let d = [p[0] - c[0], p[1] - c[1], p[2] - c[2]];
            [
                -sl * d[0] + cl * d[1],
                -sp * cl * d[0] - sp * sl * d[1] + cp * d[2],
                cp * cl * d[0] + cp * sl * d[1] + sp * d[2],
            ]
        })
        .collect();
    (positions, lat)
}

/// Baseline east-north-up to `(u, v, w)` metres at hour angle `h`.
pub fn baseline_uvw(d: [f64; 3], lat: f64, h: f64, dec: f64) -> [f64; 3] {
    let x = -d[1] * lat.sin() + d[2] * lat.cos();
    let y = d[0];
    let z = d[1] * lat.cos() + d[2] * lat.sin();
    [
        h.sin() * x + h.cos() * y,
        -dec.sin() * h.cos() * x + dec.sin() * h.sin() * y + dec.cos() * z,
        dec.cos() * h.cos() * x - dec.cos() * h.sin() * y + dec.sin() * z,
    ]
}

/// The imager's gridder flips (WSClean's FITS orientation).
pub fn imaging_options() -> Options {
    Options {
        flip_v: true,
        flip_w: true,
        ..Options::default()
    }
}

/// The test skies of the optimisation phase.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Sky {
    /// `count` point sources, log-uniform over two decades up to 1 Jy.
    Point { count: usize },
    /// Eight uniform discs of 10-80 pixels radius, 1-10 Jy each, and 20
    /// points of 0.01-1 Jy.
    Disc,
    /// `count` point sources with `dN/dS ∝ S⁻²` over 0.2-200 mJy.
    Crowded { count: usize },
}

impl Sky {
    pub fn parse(name: &str) -> Result<Sky, String> {
        match name {
            "point" => Ok(Sky::Point { count: 50 }),
            "disc" => Ok(Sky::Disc),
            "crowded" => Ok(Sky::Crowded { count: 5000 }),
            other => Err(format!("unknown sky {other}")),
        }
    }

    pub fn name(&self) -> String {
        match self {
            Sky::Point { count } => format!("point-{count}"),
            Sky::Disc => "disc".into(),
            Sky::Crowded { count } => format!("crowded-{count}"),
        }
    }
}

/// The components of a point-source sky: `(i, j, flux)` in gridder pixels.
pub fn point_sources(side: usize, count: usize, seed: u64) -> Vec<(usize, usize, f64)> {
    let mut rng = Rng(seed);
    let margin = side / 20;
    let span = (side - 2 * margin) as f64;
    (0..count)
        .map(|_| {
            let i = margin + (rng.uniform() * span) as usize;
            let j = margin + (rng.uniform() * span) as usize;
            let flux = 0.01 * 100.0_f64.powf(rng.uniform());
            (i, j, flux)
        })
        .collect()
}

/// The model image of a sky, gridder layout.
pub fn sky_model(sky: Sky, side: usize, seed: u64) -> Vec<f64> {
    let mut model = vec![0.0; side * side];
    match sky {
        Sky::Point { count } => {
            for (i, j, f) in point_sources(side, count, seed) {
                model[i * side + j] += f;
            }
        }
        Sky::Crowded { count } => {
            let mut rng = Rng(seed);
            let margin = side / 20;
            let span = (side - 2 * margin) as f64;
            let (low, high) = (2e-4, 0.2);
            for _ in 0..count {
                let i = margin + (rng.uniform() * span) as usize;
                let j = margin + (rng.uniform() * span) as usize;
                // Inverse CDF of S⁻² between low and high.
                let u = rng.uniform();
                let flux = 1.0 / (1.0 / low - u * (1.0 / low - 1.0 / high));
                model[i * side + j] += flux;
            }
        }
        Sky::Disc => {
            let mut rng = Rng(seed);
            let margin = side as f64 / 10.0;
            let span = side as f64 - 2.0 * margin;
            for _ in 0..8 {
                let ci = margin + rng.uniform() * span;
                let cj = margin + rng.uniform() * span;
                let radius = 10.0 + 70.0 * rng.uniform();
                let flux = 1.0 + 9.0 * rng.uniform();
                let per_pixel = flux / (PI * radius * radius);
                let (i0, i1) = ((ci - radius) as usize, (ci + radius) as usize);
                let (j0, j1) = ((cj - radius) as usize, (cj + radius) as usize);
                for i in i0..=i1.min(side - 1) {
                    for j in j0..=j1.min(side - 1) {
                        let (di, dj) = (i as f64 - ci, j as f64 - cj);
                        if di * di + dj * dj <= radius * radius {
                            model[i * side + j] += per_pixel;
                        }
                    }
                }
            }
            for (i, j, f) in point_sources(side, 20, seed ^ 0x1234_5678) {
                model[i * side + j] += f;
            }
        }
    }
    model
}

/// A simulated observation.
#[derive(Clone, Copy, Debug)]
pub struct SimSpec {
    pub sky: Sky,
    pub side: usize,
    pub cell_arcsec: f64,
    pub dumps: usize,
    pub dump_seconds: f64,
    pub nchan: usize,
    /// Track length, hours (symmetric about transit).
    pub hours: f64,
    pub first_freq: f64,
    pub channel_width: f64,
    pub dec_deg: f64,
    pub ra_rad: f64,
    pub noise_sigma: f64,
    pub seed: u64,
}

impl SimSpec {
    pub fn cell(&self) -> f64 {
        (self.cell_arcsec / 3600.0).to_radians()
    }
}

/// What [`simulate`] wrote.
#[derive(Clone, Debug)]
pub struct Simulated {
    pub rows: usize,
    pub model: Vec<f64>,
    pub seconds_predict: f64,
    pub seconds_write: f64,
}

/// Write `path` (a new Measurement Set) from a spec.
pub fn simulate(path: &Path, spec: &SimSpec) -> Result<Simulated, String> {
    let itrf = antennas();
    let (positions, lat) = enu(&itrf);
    let dec = spec.dec_deg.to_radians();
    let freq: Vec<f64> = (0..spec.nchan)
        .map(|c| spec.first_freq + spec.channel_width * c as f64)
        .collect();
    let (mut uvw, mut ant1, mut ant2, mut time) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for t in 0..spec.dumps {
        let hours = ((t as f64 + 0.5) / spec.dumps as f64 - 0.5) * spec.hours;
        let h = hours * PI / 12.0;
        for p in 0..positions.len() {
            for q in p + 1..positions.len() {
                let d = [
                    positions[p][0] - positions[q][0],
                    positions[p][1] - positions[q][1],
                    positions[p][2] - positions[q][2],
                ];
                uvw.extend_from_slice(&baseline_uvw(d, lat, h, dec));
                ant1.push(p as i32);
                ant2.push(q as i32);
                time.push(5.0e9 + spec.dump_seconds * t as f64);
            }
        }
    }
    let nrow = ant1.len();
    let model = sky_model(spec.sky, spec.side, spec.seed);
    let predictor = WgridMeasurement::new(
        uvw.clone(),
        freq.clone(),
        vec![Complex::new(0.0, 0.0); nrow * spec.nchan],
        vec![1.0; nrow * spec.nchan],
        spec.side,
        spec.cell(),
        1e-9,
        imaging_options(),
    )?;
    let t = std::time::Instant::now();
    let predicted = predictor.predict(&model)?;
    let seconds_predict = t.elapsed().as_secs_f64();
    drop(predictor);
    let mut rng = Rng(spec.seed ^ 0x5555_aaaa_5555_aaaa);
    let mut data = vec![0.0f32; 2 * nrow * spec.nchan * 4];
    for (k, v) in predicted.iter().enumerate() {
        let cell = k * 4;
        for corr in 0..4 {
            let parallel = corr == 0 || corr == 3;
            let (re, im) = if parallel { (v.re, v.im) } else { (0.0, 0.0) };
            data[2 * (cell + corr)] = (re + spec.noise_sigma * rng.normal()) as f32;
            data[2 * (cell + corr) + 1] = (im + spec.noise_sigma * rng.normal()) as f32;
        }
    }
    drop(predicted);
    let weight = vec![1.0f32; nrow * spec.nchan * 4];
    let t = std::time::Instant::now();
    input::write_ms(
        path,
        &MsArrays {
            uvw: &uvw,
            antenna1: &ant1,
            antenna2: &ant2,
            time: &time,
            interval: spec.dump_seconds,
            freq: &freq,
            data: &data,
            weight_spectrum: &weight,
            antennas: &itrf,
            dish_diameter: 13.5,
            phase_dir: (spec.ra_rad, dec),
        },
    )?;
    Ok(Simulated {
        rows: nrow,
        model,
        seconds_predict,
        seconds_write: t.elapsed().as_secs_f64(),
    })
}
