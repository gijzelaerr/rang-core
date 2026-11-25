//! Issue #57: a simulated MeerKAT L-band MS of the reported shape, for the
//! gemclean SIGSEGV reproduction (research/gemclean-57.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! ```text
//! cargo run --release --manifest-path core/Cargo.toml --example sim57 -- OUT.ms DUMPS NCHAN [HOURS] [flagged]
//! ```
//!
//! Without `flagged`: [`sim::simulate`] (64 antennas, 2016 baselines per
//! dump, five point sources, noise), a track of `HOURS` (default 10.6) about
//! transit at declination -24.5 deg, `NCHAN` channels over 856-1712 MHz. 870
//! dumps give 1 753 920 rows, the reported 1 754 910 to 0.06 %.
//!
//! With `flagged`: the same rows and channels, a 1 Jy point source at the
//! phase centre plus noise, and zero weights as real data has them: every
//! baseline of antennas 0-3 (whole rows), the channels of two RFI bands
//! (whole channels, 12 %), about 20 % of the remaining cells at random, and
//! NaN data under every zero weight.

use rang_core::gemclean::input::{self, MsArrays};
use rang_core::gemclean::sim::{self, Rng, SimSpec, Sky};
use std::f64::consts::PI;
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 4 {
        eprintln!("usage: sim57 OUT.ms DUMPS NCHAN [HOURS] [flagged]");
        std::process::exit(2);
    }
    let dumps: usize = a[2].parse().expect("DUMPS");
    let nchan: usize = a[3].parse().expect("NCHAN");
    let hours: f64 = a.get(4).map_or(10.6, |h| h.parse().expect("HOURS"));
    let flagged = a.get(5).is_some_and(|f| f == "flagged");
    let spec = SimSpec {
        sky: Sky::Point { count: 5 },
        side: 256,
        cell_arcsec: 20.0,
        dumps,
        dump_seconds: hours * 3600.0 / dumps as f64,
        nchan,
        hours,
        first_freq: 856e6 + 0.5 * 856e6 / nchan as f64,
        channel_width: 856e6 / nchan as f64,
        dec_deg: -24.5,
        ra_rad: 4.31,
        noise_sigma: 0.05,
        seed: 57,
    };
    let t = std::time::Instant::now();
    let rows = if flagged {
        write_flagged(Path::new(&a[1]), &spec)
    } else {
        sim::simulate(Path::new(&a[1]), &spec)
            .expect("simulate")
            .rows
    };
    println!(
        "{}: {} rows x {} channels{}, wall {:.1} s",
        a[1],
        rows,
        nchan,
        if flagged { ", flagged" } else { "" },
        t.elapsed().as_secs_f64()
    );
}

fn write_flagged(path: &Path, spec: &SimSpec) -> usize {
    let itrf = sim::antennas();
    let (positions, lat) = sim::enu(&itrf);
    let dec = spec.dec_deg.to_radians();
    let nchan = spec.nchan;
    let freq: Vec<f64> = (0..nchan)
        .map(|c| spec.first_freq + spec.channel_width * c as f64)
        .collect();
    let (mut uvw, mut ant1, mut ant2, mut time) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for t in 0..spec.dumps {
        let h = ((t as f64 + 0.5) / spec.dumps as f64 - 0.5) * spec.hours * PI / 12.0;
        for p in 0..positions.len() {
            for q in p + 1..positions.len() {
                let d = [
                    positions[p][0] - positions[q][0],
                    positions[p][1] - positions[q][1],
                    positions[p][2] - positions[q][2],
                ];
                uvw.extend_from_slice(&sim::baseline_uvw(d, lat, h, dec));
                ant1.push(p as i32);
                ant2.push(q as i32);
                time.push(5.0e9 + spec.dump_seconds * t as f64);
            }
        }
    }
    let nrow = ant1.len();
    let rfi = |c: usize| {
        let f = freq[c];
        (925e6..960e6).contains(&f) || (1525e6..1600e6).contains(&f)
    };
    let mut rng = Rng(spec.seed ^ 0x5757_5757_5757_5757);
    let mut data = vec![0.0f32; 2 * nrow * nchan * 4];
    let mut weight = vec![1.0f32; nrow * nchan * 4];
    for row in 0..nrow {
        let dead = ant1[row] < 4 || ant2[row] < 4;
        for c in 0..nchan {
            let zero = dead || rfi(c) || rng.uniform() < 0.2;
            let cell = (row * nchan + c) * 4;
            for corr in 0..4 {
                let k = cell + corr;
                if zero {
                    weight[k] = 0.0;
                    data[2 * k] = f32::NAN;
                    data[2 * k + 1] = f32::NAN;
                } else {
                    let parallel = corr == 0 || corr == 3;
                    let re = if parallel { 1.0 } else { 0.0 };
                    data[2 * k] = (re + spec.noise_sigma * rng.normal()) as f32;
                    data[2 * k + 1] = (spec.noise_sigma * rng.normal()) as f32;
                }
            }
        }
    }
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
    )
    .expect("write_ms");
    nrow
}
