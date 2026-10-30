//! Host side of one GPU inversion: bucketing (CPU code), per-layer cell
//! sort, batching under the memory budget, uploads, the dispatches of each
//! batch, the download and the CPU normalisation.

use super::context::{self, Context};
use super::{Precision, fft};
use crate::grid::{self, Inputs, Products, Sample, Settings};
use rayon::prelude::*;
use std::time::Instant;
use wgpu::util::DeviceExt;

/// Device-memory budget per inversion in MiB (default 256).
pub const MEMORY_ENV: &str = "RANG_GPU_MEMORY_MB";
/// Upper bound on the layers per batch (default: as many as the budget
/// allows); `1` forces one layer per batch.
pub const BATCH_ENV: &str = "RANG_GPU_LAYERS_PER_BATCH";

const DEFAULT_BUDGET_MIB: usize = 256;
/// Index words per sample (kernels, cell x) and values (re, im, weight).
const WORDS_PER_SAMPLE: usize = 2;
const VALUES_PER_SAMPLE: usize = 3;
const MAX_WORKGROUPS: u32 = 65535;

/// Where the time of one GPU inversion went (seconds) and what it used.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Timings {
    /// Adapter, device and queue creation (first call of the process only).
    pub context_s: f64,
    /// Shader compilation (first call per precision only).
    pub compile_s: f64,
    /// Host: counters, placement, sorts and packing.
    pub prepare_s: f64,
    /// The part of `prepare_s` in the CPU code's counters/placement pass
    /// and counting sort by layer (`grid::bucket`).
    pub bucket_s: f64,
    /// Host to device copies, waited for.
    pub upload_s: f64,
    /// Gridding, FFT and projection dispatches, waited for (with the
    /// per-batch setup of their parameters and bind groups).
    pub compute_s: f64,
    /// The three stages of `compute_s`, each submitted and waited for.
    pub grid_s: f64,
    pub fft_s: f64,
    pub project_s: f64,
    /// Device to host copy of the two sums.
    pub download_s: f64,
    /// Host: normalisation, kernel correction, trim, PSF normalisation.
    pub finish_s: f64,
    /// Bytes of device buffers allocated by this inversion.
    pub gpu_bytes: u64,
    pub batches: usize,
    pub layers_per_batch: usize,
}

impl Timings {
    pub fn as_array(&self) -> [f64; 14] {
        [
            self.context_s,
            self.compile_s,
            self.prepare_s,
            self.upload_s,
            self.compute_s,
            self.download_s,
            self.finish_s,
            self.gpu_bytes as f64,
            self.batches as f64,
            self.layers_per_batch as f64,
            self.grid_s,
            self.fft_s,
            self.project_s,
            self.bucket_s,
        ]
    }
}

pub(super) fn bytes_of<T: Copy>(values: &[T]) -> &[u8] {
    // SAFETY: only called with f32, f64 and u32 slices (plain data).
    unsafe {
        std::slice::from_raw_parts(values.as_ptr().cast::<u8>(), std::mem::size_of_val(values))
    }
}

pub(super) fn reals(values: &[f64], precision: Precision) -> Vec<u8> {
    match precision {
        Precision::F64 => bytes_of(values).to_vec(),
        Precision::F32 => {
            let narrow: Vec<f32> = values.iter().map(|&v| v as f32).collect();
            bytes_of(&narrow).to_vec()
        }
    }
}

fn env_usize(name: &str) -> Result<Option<usize>, String> {
    match std::env::var(name) {
        Ok(v) if !v.trim().is_empty() => v
            .trim()
            .parse::<usize>()
            .ok()
            .filter(|&n| n > 0)
            .map(Some)
            .ok_or_else(|| format!("{name} must be a positive integer, not {v:?}")),
        _ => Ok(None),
    }
}

/// One layer's samples sorted stably by cell (row-channel order within a
/// cell) for the gather kernel: per sample two index words (x kernel |
/// y kernel << 16, cell x) and three values (the f32 weighted sample re, im
/// and the PSF weight, widened exactly), and the offsets of every cell's
/// run, `cells + 1` of them, starting at zero.
struct Packed {
    words: Vec<u32>,
    values: Vec<f64>,
    start: Vec<u32>,
}

fn pack_layer(layer_samples: &[Sample], width: usize, cells: usize) -> Packed {
    let n = layer_samples.len();
    let mut words = vec![0u32; n * WORDS_PER_SAMPLE];
    let mut values = vec![0.0f64; n * VALUES_PER_SAMPLE];
    let mut start = vec![0u32; cells + 1];
    for s in layer_samples {
        start[s.y as usize * width + s.x as usize + 1] += 1;
    }
    for c in 0..cells {
        start[c + 1] += start[c];
    }
    let mut cursor = start[..cells].to_vec();
    for s in layer_samples {
        let cell = s.y as usize * width + s.x as usize;
        let at = cursor[cell] as usize;
        cursor[cell] += 1;
        words[at * WORDS_PER_SAMPLE] = u32::from(s.x_kernel) | (u32::from(s.y_kernel) << 16);
        words[at * WORDS_PER_SAMPLE + 1] = s.x as u32;
        values[at * VALUES_PER_SAMPLE] = f64::from(s.re);
        values[at * VALUES_PER_SAMPLE + 1] = f64::from(s.im);
        values[at * VALUES_PER_SAMPLE + 2] = f64::from(s.weight);
    }
    Packed {
        words,
        values,
        start,
    }
}

/// Layers packed at once on the host (in parallel), a multiple of the GPU
/// batch; bounds the host memory of the packed copies.
const HOST_PACK_LAYERS: usize = 16;

struct Buffers {
    kernels: wgpu::Buffer,
    sqrt_lm: wgpu::Buffer,
    tw_rows: wgpu::Buffer,
    tw_cols: wgpu::Buffer,
    samples: wgpu::Buffer,
    values: wgpu::Buffer,
    starts: wgpu::Buffer,
    bases: wgpu::Buffer,
    two_pi_w: wgpu::Buffer,
    grid_a: wgpu::Buffer,
    grid_b: wgpu::Buffer,
    sums: wgpu::Buffer,
    staging: wgpu::Buffer,
    bytes: u64,
}

pub(super) fn storage(
    ctx: &Context,
    label: &str,
    size: usize,
    extra: wgpu::BufferUsages,
) -> wgpu::Buffer {
    ctx.device.create_buffer(&wgpu::BufferDescriptor {
        label: Some(label),
        size: size.max(16).next_multiple_of(4) as u64,
        usage: wgpu::BufferUsages::STORAGE | extra,
        mapped_at_creation: false,
    })
}

pub(super) fn wait(ctx: &Context) -> Result<(), String> {
    ctx.device
        .poll(wgpu::PollType::wait_indefinitely())
        .map(|_| ())
        .map_err(|e| format!("waiting for the GPU: {e}"))
}

pub(super) fn uniform(ctx: &Context, words: &[u32]) -> wgpu::Buffer {
    ctx.device
        .create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("params"),
            contents: bytes_of(words),
            usage: wgpu::BufferUsages::UNIFORM,
        })
}

pub(super) fn bind(
    ctx: &Context,
    pipeline: &wgpu::ComputePipeline,
    buffers: &[&wgpu::Buffer],
) -> wgpu::BindGroup {
    let entries: Vec<wgpu::BindGroupEntry> = buffers
        .iter()
        .enumerate()
        .map(|(i, b)| wgpu::BindGroupEntry {
            binding: i as u32,
            resource: b.as_entire_binding(),
        })
        .collect();
    ctx.device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: None,
        layout: &pipeline.get_bind_group_layout(0),
        entries: &entries,
    })
}

/// Workgroup counts (x, y) for `threads` one-dimensional invocations of
/// 64, and the invocations per y row.
fn linear_dispatch(threads: usize) -> (u32, u32, u32) {
    let groups = threads.div_ceil(64) as u32;
    let x = groups.clamp(1, MAX_WORKGROUPS);
    let y = groups.div_ceil(x).max(1);
    (x, y, x * 64)
}

/// FFT passes of one batch of `grids` grids: rows (length `width`), then
/// columns (length `height`). Returns (uniform words, workgroups) per pass.
pub(super) fn fft_passes(
    width: usize,
    height: usize,
    grids: usize,
    rows: &[fft::Pass],
    cols: &[fft::Pass],
) -> Vec<([u32; 12], (u32, u32))> {
    let cells = width * height;
    let mut out = Vec::new();
    for (n, passes, lines_per_grid, line_stride, elem_stride, lines_fast) in [
        (width, rows, height, width, 1, 0u32),
        (height, cols, width, 1, width, 1u32),
    ] {
        for p in passes {
            let line_count = grids * lines_per_grid;
            let (x, y, row_threads) = linear_dispatch(line_count * (n / p.radix));
            out.push((
                [
                    n as u32,
                    p.radix as u32,
                    p.ns as u32,
                    (n / (p.ns * p.radix)) as u32,
                    elem_stride as u32,
                    line_count as u32,
                    lines_per_grid as u32,
                    line_stride as u32,
                    cells as u32,
                    lines_fast,
                    row_threads,
                    0,
                ],
                (x, y),
            ));
        }
    }
    out
}

/// Batching options; `invert` reads them from the environment.
#[derive(Clone, Copy, Debug, Default)]
pub struct Options {
    /// Device-memory budget in MiB (`RANG_GPU_MEMORY_MB`, default 256).
    pub budget_mib: Option<usize>,
    /// Upper bound on the layers per batch (`RANG_GPU_LAYERS_PER_BATCH`).
    pub layers_per_batch: Option<usize>,
}

impl Options {
    pub fn from_env() -> Result<Options, String> {
        Ok(Options {
            budget_mib: env_usize(MEMORY_ENV)?,
            layers_per_batch: env_usize(BATCH_ENV)?,
        })
    }
}

/// Invert on the GPU; the products are those of `grid::invert` within the
/// rounding differences documented in the module.
pub fn invert(
    settings: &Settings,
    inputs: &Inputs,
    precision: Precision,
) -> Result<(Products, Timings), String> {
    invert_with(settings, inputs, precision, Options::from_env()?)
}

/// `invert` with explicit batching options.
pub fn invert_with(
    settings: &Settings,
    inputs: &Inputs,
    precision: Precision,
    options: Options,
) -> Result<(Products, Timings), String> {
    let mut t = Timings::default();
    let (ctx, context_s) = context::get()?;
    t.context_s = context_s;
    let (pipes, compile_s) = ctx.pipelines(precision)?;
    t.compile_s = compile_s;
    let _busy = ctx.busy.lock().unwrap_or_else(|e| e.into_inner());

    let start = Instant::now();
    let bucketed = grid::bucket(settings, inputs)?;
    t.bucket_s = start.elapsed().as_secs_f64();
    let padded = bucketed.padded;
    let (width, height) = (padded.width, padded.height);
    let cells = width * height;
    let rows = fft::plan(width).ok_or(format!(
        "padded width {width} has a prime factor above {}",
        fft::MAX_RADIX
    ))?;
    let cols = fft::plan(height).ok_or(format!(
        "padded height {height} has a prime factor above {}",
        fft::MAX_RADIX
    ))?;
    let offsets = &bucketed.offsets;
    let layers: Vec<usize> = (0..padded.n_w_layers)
        .filter(|&l| offsets[l + 1] > offsets[l])
        .collect();
    t.prepare_s += start.elapsed().as_secs_f64();

    // Batch size under the memory budget and the binding limits.
    let real = precision.bytes();
    let grid_layer = 2 * 2 * cells * real; // dirty + PSF, complex
    let per_layer = 2 * grid_layer + (cells + 1) * 4; // ping-pong + offsets
    let total_samples = bucketed.samples.len();
    let sample_bytes = WORDS_PER_SAMPLE * 4 + VALUES_PER_SAMPLE * real;
    let sample_layer = total_samples * sample_bytes / layers.len().max(1);
    let kernel_count = padded.kernel_size * padded.oversampling;
    let fixed =
        kernel_count * real + cells * real + 2 * (width + height) * real + 2 * 2 * cells * real;
    let budget = options.budget_mib.unwrap_or(DEFAULT_BUDGET_MIB) << 20;
    let binding = ctx.limits.max_storage_buffer_binding_size as usize;
    let mut per_batch = (budget.saturating_sub(fixed) / (per_layer + sample_layer)).max(1);
    per_batch = per_batch.min((binding / grid_layer).max(1));
    if let Some(cap) = options.layers_per_batch {
        per_batch = per_batch.min(cap);
    }
    let per_batch = per_batch.min(layers.len().max(1));
    let batches: Vec<&[usize]> = layers.chunks(per_batch).collect();
    let max_batch_samples = batches
        .iter()
        .map(|b| {
            b.iter()
                .map(|&l| offsets[l + 1] - offsets[l])
                .sum::<usize>()
        })
        .max()
        .unwrap_or(0);
    if max_batch_samples * VALUES_PER_SAMPLE * real > binding || per_batch * grid_layer > binding {
        return Err("a layer batch exceeds the adapter's storage binding size".into());
    }
    if 2 * per_batch * cells >= u32::MAX as usize
        || max_batch_samples * WORDS_PER_SAMPLE >= u32::MAX as usize
    {
        return Err("image or layer too large for 32-bit GPU indices".into());
    }
    t.batches = batches.len();
    t.layers_per_batch = per_batch;

    // Device buffers, reused by every batch.
    let up = Instant::now();
    let gridder = &bucketed.gridder;
    let copy_dst = wgpu::BufferUsages::COPY_DST;
    let buffers = {
        let tw_rows: Vec<f64> = fft::twiddles(width).into_iter().flatten().collect();
        let tw_cols: Vec<f64> = fft::twiddles(height).into_iter().flatten().collect();
        let make_init = |label: &str, contents: &[u8]| {
            ctx.device
                .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                    label: Some(label),
                    contents,
                    usage: wgpu::BufferUsages::STORAGE,
                })
        };
        let kernels = make_init("kernels", &reals(&gridder.kernels, precision));
        let sqrt_lm = make_init("sqrt_lm", &reals(&gridder.sqrt_lm, precision));
        let tw_rows = make_init("tw_rows", &reals(&tw_rows, precision));
        let tw_cols = make_init("tw_cols", &reals(&tw_cols, precision));
        let samples = storage(
            &ctx,
            "samples",
            max_batch_samples * WORDS_PER_SAMPLE * 4,
            copy_dst,
        );
        let values = storage(
            &ctx,
            "values",
            max_batch_samples * VALUES_PER_SAMPLE * real,
            copy_dst,
        );
        let starts = storage(&ctx, "cell_start", per_batch * (cells + 1) * 4, copy_dst);
        let bases = storage(&ctx, "sample_base", per_batch * 4, copy_dst);
        let two_pi_w = storage(&ctx, "two_pi_w", per_batch * real, copy_dst);
        let grid_a = storage(
            &ctx,
            "grid_a",
            per_batch * grid_layer,
            wgpu::BufferUsages::empty(),
        );
        let grid_b = storage(
            &ctx,
            "grid_b",
            per_batch * grid_layer,
            wgpu::BufferUsages::empty(),
        );
        let sums = storage(&ctx, "sums", 2 * cells * real, wgpu::BufferUsages::COPY_SRC);
        let staging = ctx.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("staging"),
            size: (2 * cells * real) as u64,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let bytes = [
            &kernels, &sqrt_lm, &tw_rows, &tw_cols, &samples, &values, &starts, &bases, &two_pi_w,
            &grid_a, &grid_b, &sums, &staging,
        ]
        .iter()
        .map(|b| b.size())
        .sum();
        Buffers {
            kernels,
            sqrt_lm,
            tw_rows,
            tw_cols,
            samples,
            values,
            starts,
            bases,
            two_pi_w,
            grid_a,
            grid_b,
            sums,
            staging,
            bytes,
        }
    };
    t.gpu_bytes = buffers.bytes;
    ctx.queue.submit([]);
    wait(&ctx)?;
    t.upload_s += up.elapsed().as_secs_f64();

    let n_passes = rows.len() + cols.len();
    let host_chunk = per_batch * HOST_PACK_LAYERS.div_ceil(per_batch);
    let mut packed_layers: Vec<Packed> = Vec::new();
    for (index, batch) in batches.iter().enumerate() {
        let prep = Instant::now();
        let first = index * per_batch;
        if first.is_multiple_of(host_chunk) {
            let chunk = &layers[first..(first + host_chunk).min(layers.len())];
            let samples = &bucketed.samples;
            packed_layers = chunk
                .par_iter()
                .map(|&l| pack_layer(&samples[offsets[l]..offsets[l + 1]], width, cells))
                .collect();
        }
        let in_chunk = first % host_chunk;
        let ws: Vec<f64> = batch
            .iter()
            .map(|&l| -2.0 * std::f64::consts::PI * gridder.layer_to_w(l))
            .collect();
        t.prepare_s += prep.elapsed().as_secs_f64();

        let up = Instant::now();
        let mut base = 0usize;
        let mut sample_base = Vec::with_capacity(batch.len());
        let these = &packed_layers[in_chunk..in_chunk + batch.len()];
        for (slot, packed) in these.iter().enumerate() {
            sample_base.push(base as u32);
            let at = (base * WORDS_PER_SAMPLE * 4) as u64;
            ctx.queue
                .write_buffer(&buffers.samples, at, bytes_of(&packed.words));
            let at = (base * VALUES_PER_SAMPLE * real) as u64;
            ctx.queue
                .write_buffer(&buffers.values, at, &reals(&packed.values, precision));
            let at = (slot * (cells + 1) * 4) as u64;
            ctx.queue
                .write_buffer(&buffers.starts, at, bytes_of(&packed.start));
            base += packed.words.len() / WORDS_PER_SAMPLE;
        }
        ctx.queue
            .write_buffer(&buffers.bases, 0, bytes_of(&sample_base));
        ctx.queue
            .write_buffer(&buffers.two_pi_w, 0, &reals(&ws, precision));
        ctx.queue.submit([]);
        wait(&ctx)?;
        t.upload_s += up.elapsed().as_secs_f64();

        let compute = Instant::now();
        let bl = batch.len();
        let grid_params = uniform(
            &ctx,
            &[
                width as u32,
                height as u32,
                padded.kernel_size as u32,
                (padded.kernel_size / 2) as u32,
                cells as u32,
                bl as u32,
                0,
                0,
            ],
        );
        let grid_bind = bind(
            &ctx,
            &pipes.grid,
            &[
                &grid_params,
                &buffers.kernels,
                &buffers.samples,
                &buffers.starts,
                &buffers.grid_a,
                &buffers.bases,
                &buffers.values,
            ],
        );
        let passes = fft_passes(width, height, 2 * bl, &rows, &cols);
        let pass_params: Vec<wgpu::Buffer> = passes.iter().map(|(w, _)| uniform(&ctx, w)).collect();
        let pass_binds: Vec<wgpu::BindGroup> = pass_params
            .iter()
            .enumerate()
            .map(|(i, params)| {
                let tw = if i < rows.len() {
                    &buffers.tw_rows
                } else {
                    &buffers.tw_cols
                };
                let (src, dst) = if i % 2 == 0 {
                    (&buffers.grid_a, &buffers.grid_b)
                } else {
                    (&buffers.grid_b, &buffers.grid_a)
                };
                bind(&ctx, &pipes.fft, &[params, tw, src, dst])
            })
            .collect();
        let transformed = if n_passes.is_multiple_of(2) {
            &buffers.grid_a
        } else {
            &buffers.grid_b
        };
        let project_params = uniform(
            &ctx,
            &[width as u32, height as u32, cells as u32, bl as u32],
        );
        let project_bind = bind(
            &ctx,
            &pipes.project,
            &[
                &project_params,
                &buffers.sqrt_lm,
                &buffers.two_pi_w,
                transformed,
                &buffers.sums,
            ],
        );
        let tiles = ((width as u32).div_ceil(16), (height as u32).div_ceil(16));
        t.compute_s += compute.elapsed().as_secs_f64();
        // Three submissions, each waited for, so the stages are timed apart.
        let stage = |record: &dyn Fn(&mut wgpu::ComputePass)| -> Result<f64, String> {
            let start = Instant::now();
            let mut encoder = ctx.device.create_command_encoder(&Default::default());
            {
                let mut pass = encoder.begin_compute_pass(&Default::default());
                record(&mut pass);
            }
            ctx.queue.submit([encoder.finish()]);
            wait(&ctx)?;
            Ok(start.elapsed().as_secs_f64())
        };
        let compute = Instant::now();
        t.grid_s += stage(&|pass| {
            pass.set_pipeline(&pipes.grid);
            pass.set_bind_group(0, &grid_bind, &[]);
            pass.dispatch_workgroups(
                (width as u32).div_ceil(8),
                (height as u32).div_ceil(4),
                bl as u32,
            );
        })?;
        t.fft_s += stage(&|pass| {
            pass.set_pipeline(&pipes.fft);
            for (bind_group, (_, (x, y))) in pass_binds.iter().zip(&passes) {
                pass.set_bind_group(0, bind_group, &[]);
                pass.dispatch_workgroups(*x, *y, 1);
            }
        })?;
        t.project_s += stage(&|pass| {
            pass.set_pipeline(&pipes.project);
            pass.set_bind_group(0, &project_bind, &[]);
            pass.dispatch_workgroups(tiles.0, tiles.1, 1);
        })?;
        t.compute_s += compute.elapsed().as_secs_f64();
    }

    let down = Instant::now();
    let mut encoder = ctx.device.create_command_encoder(&Default::default());
    encoder.copy_buffer_to_buffer(
        &buffers.sums,
        0,
        &buffers.staging,
        0,
        (2 * cells * real) as u64,
    );
    ctx.queue.submit([encoder.finish()]);
    let slice = buffers.staging.slice(..);
    let mapped = std::sync::Arc::new(std::sync::Mutex::new(None));
    let sink = mapped.clone();
    slice.map_async(wgpu::MapMode::Read, move |r| {
        *sink.lock().unwrap_or_else(|e| e.into_inner()) = Some(r);
    });
    wait(&ctx)?;
    match mapped.lock().unwrap_or_else(|e| e.into_inner()).take() {
        Some(Ok(())) => {}
        Some(Err(e)) => return Err(format!("mapping the result: {e}")),
        None => return Err("the result was not mapped".into()),
    }
    let (mut dirty, mut psf) = {
        let view = slice
            .get_mapped_range()
            .map_err(|e| format!("reading the result: {e}"))?;
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
        let psf = values[cells..].to_vec();
        let mut dirty = values;
        dirty.truncate(cells);
        (dirty, psf)
    };
    buffers.staging.unmap();
    t.download_s = down.elapsed().as_secs_f64();

    let fin = Instant::now();
    let grid::Bucketed {
        gridder,
        stats,
        samples,
        ..
    } = bucketed;
    drop(samples);
    gridder.normalise(&mut dirty, &mut psf, stats.image_weight);
    let products = grid::finish(settings, &padded, dirty, psf, stats);
    t.finish_s = fin.elapsed().as_secs_f64();
    Ok((products, t))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pack_layer_sorts_stably_by_cell() {
        let sample = |x: i32, y: i32, re: f32| Sample {
            x,
            y,
            x_kernel: 1,
            y_kernel: 2,
            re,
            im: 0.0,
            weight: 1.0,
        };
        // Two samples in cell (1, 0) and one in (0, 1) of a 3 x 2 grid.
        let samples = vec![sample(1, 0, 1.0), sample(0, 1, 2.0), sample(1, 0, 3.0)];
        let packed = pack_layer(&samples, 3, 6);
        let res: Vec<f64> = packed.values.chunks(3).map(|v| v[0]).collect();
        assert_eq!(res, vec![1.0, 3.0, 2.0]);
        assert_eq!(packed.start, vec![0, 0, 2, 2, 3, 3, 3]);
        assert_eq!(packed.words[0], 1 | (2 << 16));
        assert_eq!(packed.words[1], 1);
    }
}
