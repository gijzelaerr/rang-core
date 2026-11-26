//! Issue #57: which phase of gemclean's channel set-up needs a stack that
//! grows with the thread count (research/gemclean-57.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! ```text
//! cargo run --release --manifest-path core/Cargo.toml --example stack57 -- THREADS STACK_BYTES SIDE DUMPS NCHAN [beam K]
//! ```
//!
//! One output channel of `DUMPS` x 2016 rows x `NCHAN` channels (64
//! antennas, 10.6 h, unit data and weights) through the steps of
//! `deconvolve_channels` in a rayon pool of `THREADS` threads of
//! `STACK_BYTES` each, printing each step as it ends; a stack overflow
//! aborts after the last step printed.

use rang_core::gemclean::measure::GridMeasurement;
use rang_core::gemclean::{self, Beam, multiscale, sim};
use rustfft::num_complex::Complex;
use std::f64::consts::PI;
use std::time::Instant;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let num = |i: usize| -> usize { a[i].parse().expect("a number") };
    let (threads, stack, n, dumps, nchan) = (num(1), num(2), num(3), num(4), num(5));
    let itrf = sim::antennas();
    let (pos, lat) = sim::enu(&itrf);
    let dec = (-24.5f64).to_radians();
    let mut uvw = Vec::new();
    for t in 0..dumps {
        let h = ((t as f64 + 0.5) / dumps as f64 - 0.5) * 10.6 * PI / 12.0;
        for p in 0..pos.len() {
            for q in p + 1..pos.len() {
                let d = [
                    pos[p][0] - pos[q][0],
                    pos[p][1] - pos[q][1],
                    pos[p][2] - pos[q][2],
                ];
                uvw.extend_from_slice(&sim::baseline_uvw(d, lat, h, dec));
            }
        }
    }
    let rows = uvw.len() / 3;
    let freq: Vec<f64> = (0..nchan)
        .map(|c| 856e6 + 428e6 / nchan as f64 * (c as f64 + 0.5))
        .collect();
    let cell = (1.1f64 * 10240.0 / n as f64 / 3600.0).to_radians();
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .stack_size(stack)
        .build()
        .expect("pool");
    let t = Instant::now();
    let step = |s: &str| eprintln!("{:8.1} s  {s}", t.elapsed().as_secs_f64());
    eprintln!("{rows} rows x {nchan} ch, n {n}, {threads} threads x {stack} B stack");
    if a.get(6).is_some_and(|m| m == "beam") {
        // `beam K`: theoretic_beam alone, K times.
        let k: usize = num(7);
        let wgt = vec![1.0f64; rows * nchan];
        pool.install(|| {
            for i in 0..k {
                std::hint::black_box(multiscale::theoretic_beam(&uvw, &freq, &wgt, n, cell));
                if (i + 1) % 50 == 0 {
                    step(&format!("theoretic_beam x {}", i + 1));
                }
            }
        });
        eprintln!("done");
        return;
    }
    pool.install(|| {
        let vis = vec![Complex::new(1.0f32, 0.0); rows * nchan];
        let wgt = vec![1.0f64; rows * nchan];
        let beam = multiscale::theoretic_beam(&uvw, &freq, &wgt, n, cell);
        step("theoretic_beam");
        let opts = rang_core::wgridder::Options {
            flip_v: true,
            flip_w: true,
            ..Default::default()
        };
        let m = GridMeasurement::<f64>::from_single_unprepared(
            uvw.clone(),
            freq.clone(),
            vis,
            wgt,
            n,
            cell,
            5e-5,
            opts,
        )
        .expect("measurement");
        step("from_single_unprepared");
        let psf2n = m.psf_image_with(2 * n, true).expect("psf");
        step("psf_image_with(2n)");
        let m = m.prepare().expect("prepare").releasing_grids();
        step("prepare");
        let b = Beam::from_double_band(n, &psf2n, 64, n + 1).expect("beam");
        step("Beam::from_double_band");
        let est = gemclean::beam_fit_estimate(beam, cell, 0.0);
        let _ = gemclean::fit_restoring_beam(n, &psf2n, est);
        step("fit_restoring_beam");
        let m = m.compacted().expect("compacted");
        step("compacted");
        let mut dirty = vec![0.0; n * n];
        let _ = b.convolve(&dirty);
        step("convolve");
        dirty.fill(0.0);
        let _ = m;
    });
    eprintln!("done");
}
