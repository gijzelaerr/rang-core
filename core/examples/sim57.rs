//! Issue #57: a simulated MeerKAT L-band MS of the reported shape, for the
//! gemclean SIGSEGV reproduction (research/gemclean-57.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! ```text
//! cargo run --release --manifest-path core/Cargo.toml --example sim57 -- OUT.ms DUMPS NCHAN [HOURS]
//! ```
//!
//! 64 antennas (2016 baselines per dump), a track of `HOURS` (default 10.6)
//! about transit at declination -24.5 deg, `NCHAN` channels over 856-1712
//! MHz, five point sources and noise. 870 dumps give 1 753 920 rows, the
//! reported 1 754 910 to 0.06 %.

use rang_core::gemclean::sim::{self, SimSpec, Sky};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 4 {
        eprintln!("usage: sim57 OUT.ms DUMPS NCHAN [HOURS]");
        std::process::exit(2);
    }
    let dumps: usize = a[2].parse().expect("DUMPS");
    let nchan: usize = a[3].parse().expect("NCHAN");
    let hours: f64 = a.get(4).map_or(10.6, |h| h.parse().expect("HOURS"));
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
    let s = sim::simulate(Path::new(&a[1]), &spec).expect("simulate");
    println!(
        "{}: {} rows x {} channels, predict {:.1} s, write {:.1} s, wall {:.1} s",
        a[1],
        s.rows,
        nchan,
        s.seconds_predict,
        s.seconds_write,
        t.elapsed().as_secs_f64()
    );
}
