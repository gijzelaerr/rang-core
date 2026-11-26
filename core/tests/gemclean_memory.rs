// SPDX-License-Identifier: MIT
//! The memory regression test of GeMClean's joined polarisations
//! (`research/gemclean-memory.md`, issue #32): a small `-pol IQUV
//! -join-polarizations -channels-out 4 -join-channels -auto-mask 5` run of
//! the `gemclean` binary, whose allocator counts the heap bytes asked for on
//! every platform, must stay under a frozen bound on its peak heap. The
//! count is that of the allocations, not of resident pages, so it does not
//! depend on the host's load; `-j 2` fixes the per-thread buffers.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.

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
    write_case(&ms, NANT, DUMPS, NCHAN);
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
        // The in-memory path, as measured in phase 1 (-reorder is the default with
        // joined polarisations since research/gemclean-memory3.md).
        .args([
            "-memory-report",
            "-j",
            "2",
            "-no-reorder",
            ms.to_str().unwrap(),
        ])
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

/// The `-reorder` case (research/gemclean-memory2.md): visibilities
/// dominate (24 antennas, 120 dumps, 128 channels, 30 % of the cells
/// weighted, against 128² images), so the band read and the in-memory
/// visibilities that `-reorder` moves to temporary files set the peak.
const REORDER_DUMPS: usize = 120;
const REORDER_NCHAN: usize = 128;
const REORDER_SIDE: usize = 128;

/// The frozen bound on `-reorder`'s peak heap, bytes: 1.2 × the value
/// measured on each platform on 2026-11-16 (research/gemclean-memory2.md,
/// section 6). Windows (`CountingAlloc`, `42ad6c6`): 232,370,794 with
/// `-reorder`, 351,758,344 without. Linux (`HugePageAlloc`, the `tests`
/// workflow's run 43966049067): 282,702,156 with, 402,089,822 without; the
/// Linux bound was added after that run (post hoc). The run without
/// `-reorder` must exceed the bound.
const REORDER_BOUND_BYTES: u64 = if cfg!(target_os = "linux") {
    339_000_000
} else {
    279_000_000
};

/// The peak heap of the clean (the phases from the first minor cycle on),
/// from the report's phase list.
fn peak_of_clean(report: &str) -> u64 {
    let from = report
        .find("\"label\": \"cycle 1: minor\"")
        .expect("a first minor cycle");
    peaks(&report[from..]).0
}

/// Run the `-reorder` case: the FITS files' bytes by name, the peak heap and
/// the peak heap of the clean.
fn run_reorder_case(
    dir: &Path,
    ms: &Path,
    tag: &str,
    extra: &[&str],
) -> (Vec<(String, Vec<u8>)>, u64, u64) {
    let out_dir = dir.join(tag);
    std::fs::create_dir_all(&out_dir).unwrap();
    let side = REORDER_SIDE.to_string();
    let out = Command::new(env!("CARGO_BIN_EXE_gemclean"))
        .args(["-name", out_dir.join("g").to_str().unwrap()])
        .args(["-size", &side, &side, "-scale", "4asec"])
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
        .args(["-memory-report", "-j", "2"])
        .args(extra)
        .arg(ms)
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "{stdout}{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let report = std::fs::read_to_string(out_dir.join("g-report.json")).unwrap();
    let (heap, _) = peaks(&report);
    let mut files: Vec<(String, Vec<u8>)> = std::fs::read_dir(&out_dir)
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
    files.sort();
    (files, heap, peak_of_clean(&report))
}

#[test]
fn reorder_keeps_the_bytes_and_lowers_the_peak_heap() {
    let dir = std::env::temp_dir().join(format!("gemclean-reorder-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let ms = dir.join("case.ms");
    write_case(&ms, NANT, REORDER_DUMPS, REORDER_NCHAN);
    let tmp = dir.join("tmp");
    std::fs::create_dir_all(&tmp).unwrap();
    let (plain, heap_plain, clean_plain) = run_reorder_case(&dir, &ms, "plain", &["-no-reorder"]);
    let (reorder, heap_reorder, clean_reorder) = run_reorder_case(
        &dir,
        &ms,
        "reorder",
        &["-reorder", "-temp-dir", tmp.to_str().unwrap()],
    );
    println!(
        "peak heap {heap_plain} bytes without -reorder, {heap_reorder} with;          in the clean {clean_plain} and {clean_reorder}"
    );
    assert!(!plain.is_empty());
    assert!(
        plain == reorder,
        "-reorder changed the FITS files (research/gemclean-memory2.md)"
    );
    let left: Vec<_> = std::fs::read_dir(&tmp).unwrap().collect();
    assert!(left.is_empty(), "-reorder left temporary files: {left:?}");
    assert!(heap_reorder > 0, "the binary's allocator does not count");
    assert!(
        heap_reorder <= REORDER_BOUND_BYTES,
        "-reorder peak heap {heap_reorder} bytes over the frozen bound {REORDER_BOUND_BYTES}"
    );
    assert!(
        heap_plain > REORDER_BOUND_BYTES,
        "the case no longer separates: {heap_plain} bytes without -reorder"
    );
    // With -reorder the whole peak sits in the read's chunk buffers, so the
    // clean (from the first minor cycle on) is checked on its own (post hoc,
    // 2026-11-17): at most 0.75 of the run without -reorder, which in-memory
    // visibilities coming back would exceed.
    assert!(
        clean_reorder * 4 <= clean_plain * 3,
        "-reorder's clean peaks at {clean_reorder} bytes, over 0.75 × {clean_plain}"
    );
    // GEMCLEAN_MEMORY_KEEP keeps the case's MS for the identity sweeps
    // (research/gemclean-memory3.md).
    if std::env::var_os("GEMCLEAN_MEMORY_KEEP").is_some() {
        println!("kept {}", ms.display());
    } else {
        std::fs::remove_dir_all(&dir).unwrap();
    }
}

/// The image-dominated case (research/gemclean-memory3.md): phase 1's
/// visibilities at 512², so the clean's image-sized buffers (models,
/// residuals, working maps, beams and the convolver's row spectra) set its
/// peak. Arms A (one row-spectra buffer for every beam) and B (sparse
/// models) lower it.
const IMAGE_SIDE: usize = 512;

/// The frozen bound on the clean's peak heap (the phases from the first
/// minor cycle on), in n² `f64` images of this case's side, so that it does
/// not depend on the platform's allocator: set between the value with main's
/// joined loop (`7be8c95`'s binary) and the value with arms A and B
/// (research/gemclean-memory3.md, section 6). Measured on Windows
/// (`CountingAlloc`) on 2026-11-17: 105.86 images before (222,012,486 bytes),
/// 84.35 after (176,898,150); a return of the per-beam row spectra alone (3 × 2 images) or
/// of the dense models (16 images) exceeds it. With `-reorder`, so the dirty
/// images do not come back beside the beams at the end.
const IMAGE_BOUND_IMAGES: f64 = 89.0;

/// The gemclean binary under test: this build's, or `GEMCLEAN_MEMORY_BIN`
/// (to measure another build on the same case).
fn gemclean_binary() -> String {
    std::env::var("GEMCLEAN_MEMORY_BIN").unwrap_or_else(|_| env!("CARGO_BIN_EXE_gemclean").into())
}

#[test]
fn joined_clean_images_stay_under_the_frozen_bound() {
    let dir = std::env::temp_dir().join(format!("gemclean-images-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let ms = dir.join("case.ms");
    write_case(&ms, NANT, DUMPS, NCHAN);
    let side = IMAGE_SIDE.to_string();
    let out = Command::new(gemclean_binary())
        .args(["-name", dir.join("g").to_str().unwrap()])
        .args(["-size", &side, &side, "-scale", "2asec"])
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
        .args([
            "-memory-report",
            "-j",
            "2",
            "-reorder",
            ms.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "{stdout}{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let report = std::fs::read_to_string(dir.join("g-report.json")).unwrap();
    let clean = peak_of_clean(&report);
    let images = clean as f64 / (IMAGE_SIDE * IMAGE_SIDE * 8) as f64;
    println!("clean peak heap {clean} bytes, {images:.2} images of {IMAGE_SIDE}²");
    assert!(clean > 0, "the binary's allocator does not count");
    assert!(
        images <= IMAGE_BOUND_IMAGES,
        "the clean's peak heap is {images:.2} images, over the frozen bound \
         {IMAGE_BOUND_IMAGES} (research/gemclean-memory3.md)\n{stdout}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

/// The bytes of the report buffer `label`.
fn buffer_bytes(report: &str, label: &str) -> u64 {
    let key = format!("\"label\": \"{label}\", \"bytes\": ");
    let i = report
        .find(&key)
        .unwrap_or_else(|| panic!("no buffer {label}"))
        + key.len();
    report[i..]
        .chars()
        .take_while(|c| c.is_ascii_digit())
        .collect::<String>()
        .parse()
        .unwrap()
}

/// A single-image Stokes I run (the self-calibration images, issue #34,
/// research/selfcal-mem-34.md) keeps only the active visibilities and
/// weights through its clean: on the `-reorder` case (30 % of the cells
/// weighted) the measurement's visibilities are at most 0.4 of the read's
/// dense Stokes I visibilities, and its weights at most 0.4 of the dense
/// gridding weights (both 1.0 before, whatever the weights' precision).
#[test]
fn single_image_keeps_only_the_active_visibilities() {
    let dir = std::env::temp_dir().join(format!("gemclean-single-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let ms = dir.join("case.ms");
    write_case(&ms, NANT, REORDER_DUMPS, REORDER_NCHAN);
    let side = REORDER_SIDE.to_string();
    let out = Command::new(gemclean_binary())
        .args(["-name", dir.join("g").to_str().unwrap()])
        .args(["-size", &side, &side, "-scale", "4asec"])
        .args([
            "-weight",
            "briggs",
            "0",
            "-niter",
            "100000",
            "-mgain",
            "0.9",
            "-auto-threshold",
            "3",
        ])
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
    assert!(
        report.contains("\"buffers\""),
        "the binary's allocator does not count"
    );
    let vis = buffer_bytes(&report, "measurement: visibilities");
    let dense_vis = buffer_bytes(&report, "read: Stokes I visibilities");
    let wgt = buffer_bytes(&report, "measurement: weights");
    let dense_wgt = buffer_bytes(&report, "weights: gridding weights");
    println!("visibilities {vis} of {dense_vis} bytes, weights {wgt} of {dense_wgt}");
    assert!(
        vis * 5 <= dense_vis * 2,
        "the single-image measurement holds {vis} bytes of visibilities, over 0.4 × {dense_vis}"
    );
    assert!(
        wgt * 5 <= dense_wgt * 2,
        "the single-image measurement holds {wgt} bytes of weights, over 0.4 × {dense_wgt}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}
