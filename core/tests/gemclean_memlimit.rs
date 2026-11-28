// SPDX-License-Identifier: MIT
//! GeMClean's `-memory-limit` (issue #34, `research/gemclean-memlimit.md`):
//! on the estimated path the estimate is at least the run's peak resident
//! memory and changes no image; a limit below it refuses before any image is
//! written, naming the figure; another path runs unchecked.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.

use rang_core::gemclean::input::{MsArrays, write_ms};
use rang_core::gemclean::sim::{antennas, baseline_uvw, enu};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const NANT: usize = 24;
const DUMPS: usize = 40;
const NCHAN: usize = 64;
const SIDE: &str = "256";

fn write_case(path: &Path, nant: usize, dumps: usize, nchan: usize) {
    let itrf: Vec<[f64; 3]> = antennas().into_iter().take(nant).collect();
    let (positions, lat) = enu(&itrf);
    let dec = (-30.0f64).to_radians();
    let freq: Vec<f64> = (0..nchan).map(|c| 1.3e9 + 2.0e6 * c as f64).collect();
    let (mut uvw, mut ant1, mut ant2, mut time) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for t in 0..dumps {
        let h = ((t as f64 + 0.5) / dumps as f64 - 0.5) * 4.0 * std::f64::consts::PI / 12.0;
        for p in 0..nant {
            for q in p + 1..nant {
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
    let mut data = vec![0.0f32; 2 * nrow * nchan * 4];
    let mut weight = vec![0.0f32; nrow * nchan * 4];
    for row in 0..nrow {
        for (c, f) in freq.iter().enumerate() {
            let cell = (row * nchan + c) * 4;
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

fn dir(tag: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("gemclean-memlimit-{}-{tag}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn gemclean(name: &Path, ms: &Path, extra: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_gemclean"))
        .args(["-name", name.to_str().unwrap()])
        .args(["-size", SIDE, SIDE, "-scale", "2asec"])
        .args([
            "-weight", "briggs", "0", "-niter", "100000", "-mgain", "0.9",
        ])
        .args(["-auto-threshold", "3", "-wgridder-accuracy", "1e-4"])
        .args([
            "-data-column",
            "DATA",
            "-no-update-model-required",
            "-j",
            "2",
        ])
        .args(extra)
        .arg(ms)
        .output()
        .unwrap()
}

fn text(out: &Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

fn number_after(report: &str, key: &str) -> u64 {
    let i = report
        .find(key)
        .unwrap_or_else(|| panic!("{key} in {report}"))
        + key.len();
    report[i..]
        .chars()
        .skip_while(|c| !c.is_ascii_digit())
        .take_while(|c| c.is_ascii_digit())
        .collect::<String>()
        .parse()
        .unwrap()
}

fn fits(prefix: &Path) -> Vec<(String, Vec<u8>)> {
    let parent = prefix.parent().unwrap();
    let mut out: Vec<(String, Vec<u8>)> = std::fs::read_dir(parent)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "fits"))
        .map(|p| {
            (
                p.file_name().unwrap().to_string_lossy().into_owned(),
                std::fs::read(&p).unwrap(),
            )
        })
        .collect();
    out.sort();
    out
}

#[test]
fn estimate_bounds_the_peak_and_changes_no_image() {
    let d = dir("bound");
    let ms = d.join("case.ms");
    write_case(&ms, NANT, DUMPS, NCHAN);
    let (a, b) = (d.join("a"), d.join("b"));
    std::fs::create_dir_all(&a).unwrap();
    std::fs::create_dir_all(&b).unwrap();
    let plain = gemclean(&a.join("g"), &ms, &[]);
    assert!(plain.status.success(), "{}", text(&plain));
    let limited = gemclean(&b.join("g"), &ms, &["-memory-limit", "1000"]);
    let log = text(&limited);
    assert!(limited.status.success(), "{log}");
    assert!(log.contains("memory estimate: "), "{log}");
    let report = std::fs::read_to_string(b.join("g-report.json")).unwrap();
    let estimate = number_after(
        &report,
        "\"memory_estimate\": {\"limit_gib\": 1000, \"bytes\":",
    );
    if let Some(i) = report.find("\"peak_memory_bytes\": ")
        && !report[i..].starts_with("\"peak_memory_bytes\": null")
    {
        let peak = number_after(&report, "\"peak_memory_bytes\":");
        println!("estimate {estimate} bytes, peak resident {peak} bytes");
        assert!(
            estimate >= peak,
            "estimate {estimate} below the peak {peak}
{log}"
        );
    }
    let (x, y) = (fits(&a.join("g")), fits(&b.join("g")));
    assert!(!x.is_empty());
    assert_eq!(x, y, "-memory-limit changed an image");
    std::fs::remove_dir_all(&d).unwrap();
}

#[test]
fn a_limit_below_the_estimate_refuses_before_any_image() {
    let d = dir("refuse");
    let ms = d.join("case.ms");
    write_case(&ms, NANT, DUMPS, NCHAN);
    let out = gemclean(&d.join("g"), &ms, &["-memory-limit", "0.001"]);
    let log = text(&out);
    assert!(!out.status.success(), "{log}");
    assert!(log.contains("the estimated peak memory, "), "{log}");
    assert!(log.contains("is above -memory-limit 0.001 GiB"), "{log}");
    assert!(log.contains("data.memory_limit_gb"), "{log}");
    assert!(fits(&d.join("g")).is_empty(), "an image was written");
    std::fs::remove_dir_all(&d).unwrap();
}

#[test]
fn another_path_runs_unchecked() {
    let d = dir("other");
    let ms = d.join("case.ms");
    write_case(&ms, NANT, DUMPS, NCHAN);
    let out = gemclean(
        &d.join("g"),
        &ms,
        &["-channels-out", "2", "-memory-limit", "0.001"],
    );
    let log = text(&out);
    assert!(out.status.success(), "{log}");
    assert!(
        log.contains("memory limit: no estimate for this path (-channels-out above 1)"),
        "{log}"
    );
    std::fs::remove_dir_all(&d).unwrap();
}
