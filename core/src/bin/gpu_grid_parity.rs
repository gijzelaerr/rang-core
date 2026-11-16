// SPDX-License-Identifier: GPL-3.0-or-later
//! Gate 1 of `research/gpu-grid.md`: the GPU gridder against the CPU path on
//! one Measurement Set, through one prepared plan each. Prints one JSON
//! object.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! ```text
//! gpu_grid_parity MS SIZE SCALE_ASEC EPS single|double MODEL_FITS BUDGET_MIB [cpu]
//! ```
//! The data are read and Briggs 0.5 weighted as GeMClean does, the rows of
//! zero weight dropped and the weights normalised; the model is a GeMClean
//! model FITS (`-` for none). Both plans compute the major cycle's residual
//! of the model and `dirty2vis` of it; the GPU's are compared with the CPU's
//! (largest difference over the CPU's largest value, and in µJy for the
//! image), with the GPU's bits hashed for the repeat check. With `cpu`
//! last, only the CPU plan runs (its time).

use rang_core::clean_certified::Complex;
use rang_core::gemclean::fits;
use rang_core::gemclean::input::{self, Selection};
use rang_core::weights::WeightClass;
use rang_core::wgridder::{KernelChoice, Options, Prepared, Real, VisData, Weights};
use std::time::Instant;

fn fnv(bytes: impl Iterator<Item = u64>) -> String {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in bytes {
        h ^= b;
        h = h.wrapping_mul(0x100000001b3);
    }
    format!("{h:016x}")
}

fn max_rel(a: &[f64], b: &[f64]) -> (f64, f64, f64) {
    let peak = b.iter().fold(0.0_f64, |m, x| m.max(x.abs()));
    let diff = a
        .iter()
        .zip(b)
        .fold(0.0_f64, |m, (x, y)| m.max((x - y).abs()));
    let rms =
        (a.iter().zip(b).map(|(x, y)| (x - y) * (x - y)).sum::<f64>() / a.len() as f64).sqrt();
    (diff / peak, diff, rms)
}

fn run<T: Real + Send + Sync>(
    opts: &Options,
    uvw: &[f64],
    freq: &[f64],
    vis: &[Complex<f32>],
    wgt64: &[f64],
    model: &[f64],
    budget: usize,
    cpu_only: bool,
) -> Result<String, String> {
    let n = opts.nx * opts.ny;
    let wgt: Vec<T> = wgt64.iter().map(|&w| T::of(w)).collect();
    let model: Vec<T> = model.iter().map(|&m| T::of(m)).collect();
    let has_model = model.iter().any(|m| m.to() != 0.0);
    let t = Instant::now();
    let cpu = Prepared::<T>::new(opts, uvw, freq, T::weights(&wgt))?;
    let t_cpu_plan = t.elapsed().as_secs_f64();
    let mut d_cpu = vec![T::zero(); n];
    let t = Instant::now();
    let q_cpu = cpu.residual(
        VisData::C64(vis),
        &wgt,
        has_model.then_some(&model[..]),
        &mut d_cpu,
    )?;
    let t_cpu_res = t.elapsed().as_secs_f64();
    let mut v_cpu = vec![Complex::new(T::zero(), T::zero()); vis.len()];
    let t = Instant::now();
    cpu.dirty2vis(&model, Weights::None, &mut v_cpu)?;
    let t_cpu_d2v = t.elapsed().as_secs_f64();
    let plan = cpu.plan();
    drop(cpu);
    if cpu_only {
        return Ok(format!(
            "{{\"cpu_plan_s\": {t_cpu_plan}, \"cpu_residual_s\": {t_cpu_res}, \"cpu_dirty2vis_s\": {t_cpu_d2v}, \"q_cpu\": {q_cpu:e}}}"
        ));
    }
    let t = Instant::now();
    let mut gpu = Prepared::<T>::new(opts, uvw, freq, T::weights(&wgt))?;
    gpu.use_gpu(budget)?;
    let t_gpu_plan = t.elapsed().as_secs_f64();
    let mut d_gpu = vec![T::zero(); n];
    let t = Instant::now();
    let q_gpu = gpu.residual(
        VisData::C64(vis),
        &wgt,
        has_model.then_some(&model[..]),
        &mut d_gpu,
    )?;
    let t_gpu_res = t.elapsed().as_secs_f64();
    // Again, warm (the device buffers are allocated now).
    let mut d_gpu2 = vec![T::zero(); n];
    let t = Instant::now();
    let q_gpu2 = gpu.residual(
        VisData::C64(vis),
        &wgt,
        has_model.then_some(&model[..]),
        &mut d_gpu2,
    )?;
    let t_gpu_res2 = t.elapsed().as_secs_f64();
    let mut v_gpu = vec![Complex::new(T::zero(), T::zero()); vis.len()];
    let t = Instant::now();
    gpu.dirty2vis(&model, Weights::None, &mut v_gpu)?;
    let t_gpu_d2v = t.elapsed().as_secs_f64();
    let wide = |x: &[T]| x.iter().map(|v| v.to()).collect::<Vec<f64>>();
    let (dc, dg) = (wide(&d_cpu), wide(&d_gpu));
    let (img_rel, img_abs, img_rms) = max_rel(&dg, &dc);
    let flat = |v: &[Complex<T>]| {
        v.iter()
            .flat_map(|c| [c.re.to(), c.im.to()])
            .collect::<Vec<f64>>()
    };
    let (vc, vg) = (flat(&v_cpu), flat(&v_gpu));
    let (vis_rel, _, _) = max_rel(&vg, &vc);
    let repeat_same = d_gpu
        .iter()
        .zip(&d_gpu2)
        .all(|(a, b)| a.to().to_bits() == b.to().to_bits())
        && q_gpu.to_bits() == q_gpu2.to_bits();
    // In single precision: the CPU path in double precision with the same
    // kernel and grid, the reference both single-precision paths round from.
    let reference = if T::SINGLE {
        let o64 = Options {
            kernel: Some(KernelChoice {
                index: plan.kernel_index,
                nu: plan.nu,
                nv: plan.nv,
            }),
            ..*opts
        };
        let w64: Vec<f64> = wgt.iter().map(|w| w.to()).collect();
        let m64: Vec<f64> = model.iter().map(|m| m.to()).collect();
        let p64 = Prepared::<f64>::new(&o64, uvw, freq, Weights::F64(&w64))?;
        let mut d64 = vec![0.0; n];
        p64.residual(
            VisData::C64(vis),
            &w64,
            has_model.then_some(&m64[..]),
            &mut d64,
        )?;
        let (c_rel, c_abs, _) = max_rel(&dc, &d64);
        let (g_rel, g_abs, _) = max_rel(&dg, &d64);
        format!(
            "{{\"cpu_rel\": {c_rel:e}, \"cpu_abs_ujy\": {:e}, \"gpu_rel\": {g_rel:e}, \"gpu_abs_ujy\": {:e}}}",
            c_abs * 1e6,
            g_abs * 1e6
        )
    } else {
        "null".to_string()
    };
    let s = rang_core::wgridder::gpu::stats();
    Ok(format!(
        concat!(
            "{{\"plan\": {{\"supp\": {}, \"nu\": {}, \"nv\": {}, \"nplanes\": {}, \"nvis\": {}}}, ",
            "\"residual_rel\": {:e}, \"residual_abs_ujy\": {:e}, \"residual_rms_ujy\": {:e}, \"residual_peak_ujy\": {:e}, ",
            "\"misfit_rel\": {:e}, \"dirty2vis_rel\": {:e}, \"q_cpu\": {:e}, \"q_gpu\": {:e}, ",
            "\"gpu_repeat_identical\": {}, \"gpu_residual_hash\": \"{}\", \"gpu_vis_hash\": \"{}\", ",
            "\"cpu_plan_s\": {}, \"cpu_residual_s\": {}, \"cpu_dirty2vis_s\": {}, ",
            "\"gpu_plan_s\": {}, \"gpu_residual_s\": {}, \"gpu_residual_warm_s\": {}, \"gpu_dirty2vis_s\": {}, ",
            "\"gpu_batches\": {}, \"gpu_plane_passes\": {}, \"gpu_device_bytes\": {}, ",
            "\"gpu_host_s\": {}, \"gpu_upload_s\": {}, \"gpu_compute_s\": {}, \"gpu_download_s\": {}, \"double_reference\": {}}}"
        ),
        plan.supp,
        plan.nu,
        plan.nv,
        plan.nplanes,
        plan.nvis,
        img_rel,
        img_abs * 1e6,
        img_rms * 1e6,
        dc.iter().fold(0.0_f64, |m, x| m.max(x.abs())) * 1e6,
        ((q_gpu - q_cpu) / q_cpu).abs(),
        vis_rel,
        q_cpu,
        q_gpu,
        repeat_same,
        fnv(dg.iter().map(|x| x.to_bits())),
        fnv(vg.iter().map(|x| x.to_bits())),
        t_cpu_plan,
        t_cpu_res,
        t_cpu_d2v,
        t_gpu_plan,
        t_gpu_res,
        t_gpu_res2,
        t_gpu_d2v,
        s.batches,
        s.plane_passes,
        s.device_bytes,
        s.host_s,
        s.upload_s,
        s.compute_s,
        s.download_s,
        reference,
    ))
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 8 {
        eprintln!(
            "usage: gpu_grid_parity MS SIZE SCALE_ASEC EPS single|double MODEL_FITS BUDGET_MIB [cpu]"
        );
        std::process::exit(2);
    }
    let result = (|| -> Result<String, String> {
        let n: usize = a[2].parse().map_err(|_| "SIZE")?;
        let cell =
            a[3].parse::<f64>().map_err(|_| "SCALE")? / 3600.0 * std::f64::consts::PI / 180.0;
        let eps: f64 = a[4].parse().map_err(|_| "EPS")?;
        let single = a[5] == "single";
        let budget: usize = a[7].parse().map_err(|_| "BUDGET")?;
        let cpu_only = a.get(8).is_some_and(|x| x == "cpu");
        let t = Instant::now();
        let selection = Selection {
            data_column: "DATA".into(),
            ..Selection::default()
        };
        let data = input::read_ms(std::path::Path::new(&a[1]), &selection)?;
        let weights = input::gridding_weights(&data, WeightClass::Briggs(0.5), n, cell)?;
        let nchan = data.freq.len();
        let (mut uvw, mut vis, mut wgt) = (Vec::new(), Vec::new(), Vec::new());
        for row in 0..data.rows() {
            let w = &weights.weights[row * nchan..(row + 1) * nchan];
            if w.iter().any(|&x| x != 0.0) {
                uvw.extend_from_slice(&data.uvw[3 * row..3 * row + 3]);
                vis.extend_from_slice(&data.vis[row * nchan..(row + 1) * nchan]);
                wgt.extend_from_slice(w);
            }
        }
        let sum: f64 = wgt.iter().sum();
        for w in &mut wgt {
            *w /= sum;
        }
        let t_read = t.elapsed().as_secs_f64();
        let model = if a[6] == "-" {
            vec![0.0; n * n]
        } else {
            let (_, px) = fits::read(std::path::Path::new(&a[6]))?;
            if px.len() != n * n {
                return Err("model size".into());
            }
            // FITS order to the gridder's: grid[x * n + y] = fits[y * n + x].
            let mut g = vec![0.0; n * n];
            for y in 0..n {
                for x in 0..n {
                    g[x * n + y] = px[y * n + x];
                }
            }
            g
        };
        let opts = Options {
            nx: n,
            ny: n,
            pixsize_x: cell,
            pixsize_y: cell,
            epsilon: eps,
            flip_v: true,
            flip_w: true,
            ..Options::default()
        };
        let body = if single {
            run::<f32>(
                &opts, &uvw, &data.freq, &vis, &wgt, &model, budget, cpu_only,
            )?
        } else {
            run::<f64>(
                &opts, &uvw, &data.freq, &vis, &wgt, &model, budget, cpu_only,
            )?
        };
        let adapter = rang_core::wgridder::gpu::adapter().unwrap_or_else(|e| e);
        Ok(format!(
            "{{\"ms\": {:?}, \"size\": {n}, \"eps\": {eps:e}, \"precision\": {:?}, \"budget_mib\": {budget}, \"read_s\": {t_read}, \"threads\": {}, \"adapter\": {:?}, \"result\": {body}}}",
            a[1],
            a[5],
            rayon::current_num_threads(),
            adapter
        ))
    })();
    match result {
        Ok(s) => println!("{s}"),
        Err(e) => {
            eprintln!("gpu_grid_parity: {e}");
            std::process::exit(1);
        }
    }
}
