// SPDX-License-Identifier: MIT
//! DL1's runtime bench (research/dl1-contract.md, section 7).
//!
//!     bench RUNTIME ONNX PLANES_A.bin TORCH_A.bin THREADS
//!
//! PLANES_A.bin: (1, 15, 64, 512) float32 little-endian (seed 20261119,
//! written by examples/dl1_export_f3.py); TORCH_A.bin: PyTorch's logits for
//! it. Prints one JSON line: wall of shape A (1 thread, outside the pool)
//! and of shape B (128 planes of 64 x 512, rayon over planes with THREADS
//! threads), each the median of 7 after 2 warm-ups; agreement with PyTorch;
//! G3 (a second shape on the same model); FNV-1a 64 hashes of the outputs
//! for identity across thread counts.

use rayon::prelude::*;
use std::time::Instant;

const NT: usize = 64;
const NC: usize = 512;
const NB: usize = 128;

fn read_f32(path: &str) -> Vec<f32> {
    let b = std::fs::read(path).unwrap_or_else(|e| panic!("{path}: {e}"));
    b.chunks_exact(4)
        .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

fn fnv(xs: &[f32]) -> u64 {
    let mut h = 0xcbf29ce484222325u64;
    for x in xs {
        for b in x.to_le_bytes() {
            h ^= b as u64;
            h = h.wrapping_mul(0x100000001b3);
        }
    }
    h
}

/// Seeded normal planes (xorshift64* and Box-Muller), the same on every
/// run and thread count.
fn planes(seed: u64, n: usize) -> Vec<f32> {
    let mut s = seed.max(1);
    let mut u = || {
        s ^= s >> 12;
        s ^= s << 25;
        s ^= s >> 27;
        ((s.wrapping_mul(0x2545F4914F6CDD1D) >> 11) as f64 + 0.5) / (1u64 << 53) as f64
    };
    (0..n)
        .map(|_| {
            let (a, b) = (u(), u());
            ((-2.0 * a.ln()).sqrt() * (2.0 * std::f64::consts::PI * b).cos()) as f32
        })
        .collect()
}

fn median(mut v: Vec<f64>) -> f64 {
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    v[v.len() / 2]
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() != 6 {
        eprintln!("usage: bench RUNTIME ONNX PLANES_A.bin TORCH_A.bin THREADS");
        std::process::exit(2);
    }
    let (name, onnx, threads) = (&a[1], &a[2], a[5].parse::<usize>().unwrap());
    let xa = read_f32(&a[3]);
    let ta = read_f32(&a[4]);
    assert_eq!(xa.len(), 15 * NT * NC);
    assert_eq!(ta.len(), NT * NC);
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build_global()
        .unwrap();
    #[cfg(feature = "tract-mt")]
    if std::env::var("DL1_TRACT_MT").is_ok() {
        tract_linalg::multithread::set_default_executor(
            tract_linalg::multithread::Executor::multithread(threads),
        );
    }
    let t0 = Instant::now();
    let rt = dl1_runtimes::load(name, onnx).unwrap_or_else(|e| panic!("load: {e}"));
    let load_s = t0.elapsed().as_secs_f64();

    // Shape A.
    let mut wall_a = Vec::new();
    let mut ya = Vec::new();
    for k in 0..9 {
        let t = Instant::now();
        ya = rt.run(&xa, NT, NC).unwrap();
        if k >= 2 {
            wall_a.push(t.elapsed().as_secs_f64());
        }
    }
    let mut d: Vec<f64> = ya
        .iter()
        .zip(&ta)
        .map(|(y, t)| (*y as f64 - *t as f64).abs())
        .collect();
    d.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let max_d = *d.last().unwrap();
    let p999 = d[(d.len() * 999) / 1000];

    // G3: a second shape on the same loaded model.
    let x3 = planes(7, 15 * 32 * 256);
    let g3 = match rt.run(&x3, 32, 256) {
        Ok(y) if y.len() == 32 * 256 => "pass".to_string(),
        Ok(y) => format!("fail: {} outputs", y.len()),
        Err(e) => format!("fail: {}", e.lines().next().unwrap_or("")),
    };

    // Shape B.
    let xb: Vec<Vec<f32>> = (0..NB)
        .map(|i| planes(1000 + i as u64, 15 * NT * NC))
        .collect();
    let mut wall_b = Vec::new();
    let mut yb: Vec<Vec<f32>> = Vec::new();
    for k in 0..9 {
        let t = Instant::now();
        yb = xb.par_iter().map(|x| rt.run(x, NT, NC).unwrap()).collect();
        if k >= 2 {
            wall_b.push(t.elapsed().as_secs_f64());
        }
    }
    let flat_b: Vec<f32> = yb.concat();
    println!(
        "{{\"runtime\":\"{}\",\"threads\":{},\"load_s\":{:.6},\"a_s\":{:.6},\"b_s\":{:.6},\
\"max_abs_vs_torch\":{:.3e},\"p999_abs_vs_torch\":{:.3e},\"g3\":\"{}\",\"hash_a\":\"{:016x}\",\"hash_b\":\"{:016x}\"}}",
        rt.name(),
        threads,
        load_s,
        median(wall_a),
        median(wall_b),
        max_d,
        p999,
        g3,
        fnv(&ya),
        fnv(&flat_b)
    );
}
