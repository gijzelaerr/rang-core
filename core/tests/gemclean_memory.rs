// SPDX-License-Identifier: GPL-3.0-or-later
//! The memory regression test of GeMClean's joined polarisations
//! (`research/gemclean-memory.md`, issue #32): a small `-pol IQUV
//! -join-polarizations -channels-out 4 -join-channels -auto-mask 5` run of
//! the `gemclean` binary, whose allocator counts the heap bytes asked for on
//! every platform, must stay under a frozen bound on its peak heap. The
//! count is that of the allocations, not of resident pages, so it does not
//! depend on the host's load; `-j 2` fixes the per-thread buffers.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

use rang_core::gemclean::input::{MsArrays, write_ms};
use rang_core::gemclean::sim::{antennas, baseline_uvw, enu};
use std::path::Path;
use std::process::Command;

/// The case: 24 MeerKAT antennas, 40 dumps over 4 h, 64 channels, four
/// linear correlations; 70 % of the cells at zero weight in all four
/// correlations (as after E2-B's P flag spread, 76 % on J1833−2103); a 1 Jy
/// source in XX and YY 20 pixels from the centre, plus noise.
const NANT: usize = 24;
const DUMPS: usize = 40;
const NCHAN: usize = 64;
const SIDE: usize = 256;

/// The frozen bound on the peak heap, bytes: 1.2 × the 101,622,308 bytes
/// measured after the fix on 2026-11-15 (research/gemclean-memory.md,
/// section 5). Before the fix this case peaked at 149,499,552 bytes.
const BOUND_BYTES: u64 = 122_000_000;

fn write_case(path: &Path) {
    let itrf: Vec<[f64; 3]> = antennas().into_iter().take(NANT).collect();
    let (positions, lat) = enu(&itrf);
    let dec = (-30.0f64).to_radians();
    let freq: Vec<f64> = (0..NCHAN).map(|c| 1.3e9 + 2.0e6 * c as f64).collect();
    let (mut uvw, mut ant1, mut ant2, mut time) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for t in 0..DUMPS {
        let h = ((t as f64 + 0.5) / DUMPS as f64 - 0.5) * 4.0 * std::f64::consts::PI / 12.0;
        for p in 0..NANT {
            for q in p + 1..NANT {
                let d = [
                    positions[p][0] - positions[q][0],
                    positions[p][1] - positions[q][1],
                    positions[p][2] - positions[q][2],
                ];
                uvw.extend_from_slice(&baseline_uvw(d, lat, h, dec));
                ant1.push(p as i32);
                ant2.push(q as i32);
                time.push(5.0e9 + 360.0 * t as f64);
            }
        }
    }
    let nrow = ant1.len();
    let mut state = 0x2026_1115_0032_0001u64;
    let mut next = || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        (state >> 11) as f64 / (1u64 << 53) as f64
    };
    // The source at (l, m) = 20 pixels of 2″ east: phase 2π (u l) / λ.
    let l = (20.0 * 2.0 / 3600.0f64).to_radians();
    let mut data = vec![0.0f32; 2 * nrow * NCHAN * 4];
    let mut weight = vec![0.0f32; nrow * NCHAN * 4];
    for row in 0..nrow {
        for (c, f) in freq.iter().enumerate() {
            let cell = (row * NCHAN + c) * 4;
            let phase = 2.0 * std::f64::consts::PI * uvw[3 * row] * f / 299_792_458.0 * l;
            let on = next() >= 0.7;
            for corr in 0..4 {
                let (mut re, mut im) = (0.05 * (next() - 0.5), 0.05 * (next() - 0.5));
                if corr == 0 || corr == 3 {
                    re += phase.cos();
                    im += phase.sin();
                }
                data[2 * (cell + corr)] = re as f32;
                data[2 * (cell + corr) + 1] = im as f32;
                weight[cell + corr] = if on { 1.0 } else { 0.0 };
            }
        }
    }
    write_ms(
        path,
        &MsArrays {
            uvw: &uvw,
            antenna1: &ant1,
            antenna2: &ant2,
            time: &time,
            interval: 360.0,
            freq: &freq,
            data: &data,
            weight_spectrum: &weight,
            antennas: &itrf,
            dish_diameter: 13.5,
            phase_dir: (0.0, dec),
        },
    )
    .unwrap();
}

/// The peak heap of the report's phases, and the report's peak RSS.
fn peaks(report: &str) -> (u64, Option<u64>) {
    let number = |key: &str, from: usize| -> Option<(u64, usize)> {
        let i = report[from..].find(key)? + from + key.len();
        let digits: String = report[i..]
            .chars()
            .skip_while(|c| !c.is_ascii_digit() && *c != 'n')
            .take_while(|c| c.is_ascii_digit())
            .collect();
        Some((digits.parse().ok()?, i))
    };
    let mut peak = 0;
    let mut from = 0;
    while let Some((v, i)) = number("\"heap_peak_bytes\":", from) {
        peak = peak.max(v);
        from = i;
    }
    (peak, number("\"peak_memory_bytes\":", 0).map(|x| x.0))
}

#[test]
fn joined_iquv_peak_heap_stays_under_the_frozen_bound() {
    let dir = std::env::temp_dir().join(format!("gemclean-memory-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let ms = dir.join("case.ms");
    write_case(&ms);
    let name = dir.join("g");
    let out = Command::new(env!("CARGO_BIN_EXE_gemclean"))
        .args(["-name", name.to_str().unwrap()])
        .args([
            "-size",
            &SIDE.to_string(),
            &SIDE.to_string(),
            "-scale",
            "2asec",
        ])
        .args([
            "-weight", "briggs", "0", "-niter", "100000", "-mgain", "0.9",
        ])
        .args([
            "-auto-threshold",
            "3",
            "-auto-mask",
            "5",
            "-wgridder-accuracy",
            "1e-4",
        ])
        .args(["-pol", "IQUV", "-join-polarizations"])
        .args(["-channels-out", "4", "-join-channels"])
        .args(["-data-column", "DATA", "-no-update-model-required"])
        .args(["-memory-report", "-j", "2", ms.to_str().unwrap()])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "{stdout}{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let report = std::fs::read_to_string(dir.join("g-report.json")).unwrap();
    let (heap, rss) = peaks(&report);
    println!("peak heap {heap} bytes, peak resident {rss:?} bytes");
    assert!(heap > 0, "the binary's allocator does not count");
    assert!(
        heap <= BOUND_BYTES,
        "peak heap {heap} bytes over the frozen bound {BOUND_BYTES} \
         (research/gemclean-memory.md)\n{stdout}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}
