//! GPU tests (protocol criterion 7). Each returns early, with a message on
//! stderr, when no usable adapter exists (Linux without a Vulkan loader, CI),
//! so they skip rather than fail there.

use super::context::{self, Context};
use super::invert::{bind, fft_passes, reals, storage, uniform, wait};
use super::{Options, Precision, fft, invert_with};
use crate::grid::{self, C_LIGHT, Inputs, Settings};
use rustfft::FftPlanner;
use rustfft::num_complex::Complex;
use std::f64::consts::PI;
use std::sync::Arc;

fn gpu(precision: Precision) -> Option<Arc<Context>> {
    match context::get() {
        Ok((ctx, _)) => {
            if precision == Precision::F64 && !ctx.f64 {
                eprintln!("skipped: the adapter has no SHADER_F64");
                return None;
            }
            Some(ctx)
        }
        Err(reason) => {
            eprintln!("skipped: {reason}");
            None
        }
    }
}

/// The 2-D backward transform of `grids` grids of `width * height` on the
/// GPU, through the same passes and kernel as the inversion.
fn fft_on_gpu(
    ctx: &Context,
    data: &[[f64; 2]],
    grids: usize,
    width: usize,
    height: usize,
    precision: Precision,
) -> Vec<[f64; 2]> {
    let (pipes, _) = ctx.pipelines(precision).unwrap();
    let _busy = ctx.busy.lock().unwrap_or_else(|e| e.into_inner());
    let rows = fft::plan(width).unwrap();
    let cols = fft::plan(height).unwrap();
    let flat: Vec<f64> = data.iter().flatten().copied().collect();
    let real = precision.bytes();
    let bytes = grids * width * height * 2 * real;
    let usage = wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::COPY_SRC;
    let a = storage(ctx, "a", bytes, usage);
    let b = storage(ctx, "b", bytes, usage);
    ctx.queue.write_buffer(&a, 0, &reals(&flat, precision));
    let tw = |n: usize| {
        let values: Vec<f64> = fft::twiddles(n).into_iter().flatten().collect();
        let buffer = storage(ctx, "tw", values.len() * real, wgpu::BufferUsages::COPY_DST);
        ctx.queue
            .write_buffer(&buffer, 0, &reals(&values, precision));
        buffer
    };
    let (tw_rows, tw_cols) = (tw(width), tw(height));
    let passes = fft_passes(width, height, grids, &rows, &cols);
    let params: Vec<wgpu::Buffer> = passes.iter().map(|(w, _)| uniform(ctx, w)).collect();
    let mut encoder = ctx.device.create_command_encoder(&Default::default());
    {
        let mut pass = encoder.begin_compute_pass(&Default::default());
        pass.set_pipeline(&pipes.fft);
        for (i, ((_, (x, y)), p)) in passes.iter().zip(&params).enumerate() {
            let t = if i < rows.len() { &tw_rows } else { &tw_cols };
            let (src, dst) = if i % 2 == 0 { (&a, &b) } else { (&b, &a) };
            let group = bind(ctx, &pipes.fft, &[p, t, src, dst]);
            pass.set_bind_group(0, &group, &[]);
            pass.dispatch_workgroups(*x, *y, 1);
        }
    }
    let result = if passes.len().is_multiple_of(2) {
        &a
    } else {
        &b
    };
    let staging = ctx.device.create_buffer(&wgpu::BufferDescriptor {
        label: None,
        size: bytes as u64,
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });
    encoder.copy_buffer_to_buffer(result, 0, &staging, 0, bytes as u64);
    ctx.queue.submit([encoder.finish()]);
    let slice = staging.slice(..);
    slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
    wait(ctx).unwrap();
    let view = slice.get_mapped_range().unwrap();
    let values: Vec<f64> = match precision {
        Precision::F64 => view
            .chunks_exact(8)
            .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
            .collect(),
        Precision::F32 => view
            .chunks_exact(4)
            .map(|c| f32::from_le_bytes(c.try_into().unwrap()) as f64)
            .collect(),
    };
    values.chunks_exact(2).map(|c| [c[0], c[1]]).collect()
}

/// rustfft's unnormalised inverse transform of rows then columns.
fn fft_reference(data: &[[f64; 2]], width: usize, height: usize) -> Vec<[f64; 2]> {
    let mut planner = FftPlanner::<f64>::new();
    let rows = planner.plan_fft_inverse(width);
    let cols = planner.plan_fft_inverse(height);
    let mut grid: Vec<Complex<f64>> = data.iter().map(|v| Complex::new(v[0], v[1])).collect();
    for row in grid.chunks_exact_mut(width) {
        rows.process(row);
    }
    let mut column = vec![Complex::new(0.0, 0.0); height];
    for x in 0..width {
        for y in 0..height {
            column[y] = grid[x + y * width];
        }
        cols.process(&mut column);
        for y in 0..height {
            grid[x + y * width] = column[y];
        }
    }
    grid.iter().map(|c| [c.re, c.im]).collect()
}

#[test]
fn gpu_fft_matches_rustfft() {
    for precision in [Precision::F64, Precision::F32] {
        let Some(ctx) = gpu(precision) else {
            continue;
        };
        let tolerance = match precision {
            Precision::F64 => 1e-12,
            Precision::F32 => 1e-5,
        };
        // Factors 2, 3, 4, 5, 7, 11, 13, a length of 1, non-square, and
        // the comparator size 616 = 4 2 7 11 (three grids at once).
        for (width, height, grids) in [
            (12, 30, 2),
            (77, 13, 1),
            (1, 8, 1),
            (16, 5, 3),
            (616, 616, 3),
        ] {
            let n = width * height;
            let data: Vec<[f64; 2]> = (0..grids * n)
                .map(|i| [(i as f64 * 0.37).sin(), (i as f64 * 0.11).cos()])
                .collect();
            let fast = fft_on_gpu(&ctx, &data, grids, width, height, precision);
            for g in 0..grids {
                let slow = fft_reference(&data[g * n..(g + 1) * n], width, height);
                let scale = slow
                    .iter()
                    .map(|v| v[0].abs().max(v[1].abs()))
                    .fold(0.0_f64, f64::max);
                let worst = fast[g * n..(g + 1) * n]
                    .iter()
                    .zip(&slow)
                    .map(|(a, b)| (a[0] - b[0]).abs().max((a[1] - b[1]).abs()))
                    .fold(0.0_f64, f64::max);
                assert!(
                    worst <= tolerance * scale,
                    "{precision:?} {width} x {height} grid {g}: {worst:e} of {scale:e}"
                );
            }
        }
    }
}

/// Settings, uvw, frequencies, data, weights and imaging weights.
type Case = (Settings, Vec<f64>, Vec<f64>, Vec<f32>, Vec<f32>, Vec<f32>);

fn point_source(n_w_layers: usize) -> Case {
    let settings = Settings {
        width: 40,
        height: 36,
        pixel_size_x: 1e-3,
        pixel_size_y: 1e-3,
        kernel_size: 7,
        oversampling: 1023,
        n_w_layers,
        padding: 1.2,
    };
    let (l, m) = (5.0e-3_f64, -3.0e-3_f64);
    let n = (1.0 - l * l - m * m).sqrt();
    let frequencies = vec![1.0e9, 1.2e9, 1.4e9];
    let (mut uvw, mut data, mut weights, mut imaging) = (vec![], vec![], vec![], vec![]);
    for i in 0..120 {
        let angle = i as f64 * 0.37;
        let r = 10.0 + (i % 11) as f64 * 9.0;
        let (u, v, w) = (r * angle.cos(), r * angle.sin(), 8.0 * (angle * 1.7).sin());
        uvw.extend_from_slice(&[u, v, w]);
        for (c, &freq) in frequencies.iter().enumerate() {
            let lambda = C_LIGHT / freq;
            let phase = 2.0 * PI * (u * l + v * m + w * (n - 1.0)) / lambda;
            data.push(phase.cos() as f32);
            data.push(phase.sin() as f32);
            weights.push(if i % 7 == 0 && c == 1 { 0.0 } else { 1.0 });
            imaging.push(0.5 + ((i + c) % 3) as f32);
        }
    }
    (settings, uvw, frequencies, data, weights, imaging)
}

#[test]
fn gpu_inversion_matches_the_cpu_and_ignores_batching() {
    for precision in [Precision::F64, Precision::F32] {
        if gpu(precision).is_none() {
            continue;
        }
        let (settings, uvw, frequencies, data, weights, imaging) = point_source(9);
        let inputs = Inputs {
            uvw: &uvw,
            frequencies: &frequencies,
            data: &data,
            weights: &weights,
            imaging_weights: &imaging,
        };
        let cpu = grid::invert(&settings, &inputs).unwrap();
        let (one, t1) = invert_with(
            &settings,
            &inputs,
            precision,
            Options {
                layers_per_batch: Some(1),
                ..Options::default()
            },
        )
        .unwrap();
        let (all, t_all) = invert_with(&settings, &inputs, precision, Options::default()).unwrap();
        assert!(t1.batches > 1 && t_all.batches == 1, "{t1:?} {t_all:?}");
        let tolerance = match precision {
            Precision::F64 => 1e-12,
            Precision::F32 => 1e-4,
        };
        // The counters are the CPU code's; the PSF normalisation is derived
        // from the PSF image and agrees to the image tolerance.
        for gpu_stats in [one.stats, all.stats] {
            let mut same = gpu_stats;
            same.psf_normalization = cpu.stats.psf_normalization;
            assert_eq!(cpu.stats, same);
            let relative = (gpu_stats.psf_normalization / cpu.stats.psf_normalization - 1.0).abs();
            assert!(relative <= tolerance, "{precision:?}: {relative:e}");
        }
        for (gpu_image, cpu_image) in [(&all.dirty, &cpu.dirty), (&all.psf, &cpu.psf)] {
            let peak = cpu_image.iter().fold(0.0_f64, |a, v| a.max(v.abs()));
            let worst = gpu_image
                .iter()
                .zip(cpu_image)
                .fold(0.0_f64, |a, (x, y)| a.max((x - y).abs()));
            assert!(
                worst <= tolerance * peak,
                "{precision:?}: {worst:e} of {peak:e}"
            );
        }
        // Batching changes no bit.
        for (a, b) in one
            .dirty
            .iter()
            .zip(&all.dirty)
            .chain(one.psf.iter().zip(&all.psf))
        {
            assert_eq!(a.to_bits(), b.to_bits(), "{precision:?}");
        }
    }
}

#[test]
fn unsupported_sizes_are_refused() {
    if gpu(Precision::F32).is_none() {
        return;
    }
    let (mut settings, uvw, frequencies, data, weights, imaging) = point_source(4);
    // 1.2 * 57 = 68.4 -> 72 = 8 * 9 is fine; force a prime 17 * 4 = 68.
    settings.width = 68;
    settings.padding = 1.0;
    let inputs = Inputs {
        uvw: &uvw,
        frequencies: &frequencies,
        data: &data,
        weights: &weights,
        imaging_weights: &imaging,
    };
    let error = match invert_with(&settings, &inputs, Precision::F32, Options::default()) {
        Ok(_) => panic!("a 68-pixel grid (4 x 17) must be refused"),
        Err(error) => error,
    };
    assert!(error.contains("prime factor"), "{error}");
}
