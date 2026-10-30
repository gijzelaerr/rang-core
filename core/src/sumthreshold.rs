//! RFI flagging ported from Tricolour 0.2.1 (research/core-d-tricolour.md).
//!
//! A Rust translation of `tricolour/flagging.py`, `tricolour/stokes.py`,
//! `tricolour/mask.py`, `tricolour/packing.py` and
//! `tricolour/apps/tricolour/strat_executor.py` from Tricolour 0.2.1, whose
//! SumThreshold kernel derives from katsdpsigproc (`rfi/twodflag.py`, also
//! BSD-3-Clause, National Research Foundation (SARAO)). Tricolour is
//! distributed under this licence:
//!
//! > Copyright (c) 2019, National Research Foundation
//! > (South African Radio Astronomy Observatory)
//! > All rights reserved.
//! >
//! > Redistribution and use in source and binary forms, with or without
//! > modification, are permitted provided that the following conditions are
//! > met:
//! >
//! > 1. Redistributions of source code must retain the above copyright notice,
//! >    this list of conditions and the following disclaimer.
//! >
//! > 2. Redistributions in binary form must reproduce the above copyright
//! >    notice, this list of conditions and the following disclaimer in the
//! >    documentation and/or other materials provided with the distribution.
//! >
//! > 3. Neither the name of the copyright holder nor the names of its
//! >    contributors may be used to endorse or promote products derived from
//! >    this software without specific prior written permission.
//! >
//! > THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
//! > IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//! > THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//! > PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
//! > CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
//! > EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
//! > PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
//! > PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
//! > LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
//! > NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
//! > SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
//!
//! The translation keeps Tricolour's arithmetic: single-precision data with
//! double-precision accumulators, Numba's promotion of a float32 value
//! combined with a float64 scalar to float64, medians of float32 values with
//! the midpoint sum rounded in float32, and the executor's accumulation
//! rules. The one known departure is the `uvcontsub_flagger` smooth fit,
//! which Tricolour obtains from a complex64 pocketfft round trip and this
//! module computes as the same truncated Fourier series in double precision
//! rounded to complex64. The whole of the archived MeerKAT controls is
//! reproduced through the protocol in `research/core-d-tricolour.md`.
//!
//! Layout: a *window* holds one correlation product per baseline as
//! `(baseline, time, channel)` row-major complex64 values stored as separate
//! real and imaginary float32 planes; flags are `bool` with the same shape.

use std::f64::consts::PI;

use rayon::prelude::*;

/// Ratio between the median absolute deviation and the standard deviation of
/// a Gaussian distribution (`tricolour.flagging.MAD_NORMAL`).
pub const MAD_NORMAL: f64 = 1.4826;

/// Boxcar passes of the approximate Gaussian filter.
const PASSES: usize = 4;

/// Parameters of `tricolour.flagging.sum_threshold_flagger`.
#[derive(Clone, Debug, PartialEq)]
pub struct SumThresholdParams {
    pub outlier_nsigma: f64,
    pub windows_time: Vec<i64>,
    pub windows_freq: Vec<i64>,
    pub background_reject: f64,
    pub background_iterations: i64,
    pub spike_width_time: f64,
    pub spike_width_freq: f64,
    pub time_extend: usize,
    pub freq_extend: usize,
    pub freq_chunks: usize,
    pub average_freq: usize,
    pub flag_all_time_frac: f64,
    pub flag_all_freq_frac: f64,
    pub rho: f64,
    pub num_major_iterations: usize,
}

/// One strategy step of `strat_executor.py`.
#[derive(Clone, Debug, PartialEq)]
pub enum Step {
    FlagNansZeros,
    /// `accumulation_mode` "or" (true) or "override" (false), and the
    /// `uvrange` bounds in metres (`casa_style_range`).
    StaticMask {
        or: bool,
        uv_low: f64,
        uv_high: f64,
    },
    SumThreshold(SumThresholdParams),
    UvContSub {
        major_cycles: usize,
        or_original_from_cycle: usize,
        taylor_degrees: usize,
        sigma: f64,
    },
    FlagAutos,
    CombineWithInputFlags,
    Unflag,
}

/// Geometry and masks shared by every step of one dataset.
pub struct Context<'a> {
    /// `(antenna1, antenna2)` per window baseline.
    pub baselines: &'a [(usize, usize)],
    /// ECEF antenna positions, `nant * 3` metres.
    pub antenna_position: &'a [f64],
    pub chan_freq: &'a [f64],
    pub chan_width: &'a [f64],
    /// One list of masked channel centre frequencies (Hz) per static mask.
    pub masks: &'a [&'a [f64]],
}

/// A window of one correlation product per baseline.
#[derive(Clone, Debug)]
pub struct Window {
    pub nbl: usize,
    pub ntime: usize,
    pub nchan: usize,
    pub re: Vec<f32>,
    pub im: Vec<f32>,
}

impl Window {
    pub fn len(&self) -> usize {
        self.nbl * self.ntime * self.nchan
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// Complex128 product as Numba lowers it (no fused multiply-add).
fn cmul(a: (f64, f64), b: (f64, f64)) -> (f64, f64) {
    (a.0 * b.0 - a.1 * b.1, a.0 * b.1 + a.1 * b.0)
}

/// One Stokes dependency: `(corr1, corr2, alpha, sign1, sign2)` with
/// casacore correlation codes, so that `stokes = alpha * (sign1 * corr1 +
/// sign2 * corr2)`.
type StokesDep = (i32, i32, (f64, f64), f64, f64);

/// The same with correlation indices into the data instead of codes.
pub type StokesTerm = (usize, usize, (f64, f64), f64, f64);

/// Stokes dependency table of `tricolour.stokes.stokes_deps`.
const STOKES_DEPS: [(&str, [StokesDep; 2]); 4] = [
    (
        "I",
        [(9, 12, (0.5, 0.0), 1.0, 1.0), (5, 8, (0.5, 0.0), 1.0, 1.0)],
    ),
    (
        "Q",
        [(9, 12, (0.5, 0.0), 1.0, -1.0), (6, 7, (0.5, 0.0), 1.0, 1.0)],
    ),
    (
        "U",
        [
            (10, 11, (0.5, 0.0), 1.0, 1.0),
            (6, 7, (0.0, -0.5), 1.0, -1.0),
        ],
    ),
    (
        "V",
        [
            (10, 11, (0.0, -0.5), 1.0, -1.0),
            (5, 8, (0.5, 0.0), 1.0, -1.0),
        ],
    ),
];

/// `stokes_corr_map` restricted to the polarised parameters Q, U, V, in that
/// order: `(c1, c2, alpha, s1, s2)` with correlation indices.
pub fn polarised_map(corr_type: &[i32]) -> Vec<StokesTerm> {
    let mut map = Vec::new();
    for (stokes, deps) in STOKES_DEPS.iter() {
        if *stokes == "I" {
            continue;
        }
        let mut found = None;
        for (c1, c2, alpha, s1, s2) in deps.iter() {
            let i1 = corr_type.iter().position(|c| c == c1);
            let i2 = corr_type.iter().position(|c| c == c2);
            if let (Some(i1), Some(i2)) = (i1, i2) {
                // Later dependencies overwrite earlier ones, as the dict does.
                found = Some((i1, i2, *alpha, *s1, *s2));
            }
        }
        if let Some(entry) = found {
            map.push(entry);
        }
    }
    map
}

/// `tricolour.stokes.polarised_intensity` for one visibility: the float64
/// sum of squared magnitudes, square-rooted and rounded to float32.
pub fn polarised_intensity(vis: &[(f32, f32)], stokes_pol: &[StokesTerm]) -> f32 {
    let mut pol = 0.0f64;
    for &(c1, c2, alpha, s1, s2) in stokes_pol {
        let v1 = (vis[c1].0 as f64, vis[c1].1 as f64);
        let v2 = (vis[c2].0 as f64, vis[c2].1 as f64);
        let t1 = cmul((s1, 0.0), v1);
        let t2 = cmul((s2, 0.0), v2);
        let value = cmul(alpha, (t1.0 + t2.0, t1.1 + t2.1));
        let magnitude = value.0.hypot(value.1);
        pol += magnitude * magnitude;
    }
    pol.sqrt() as f32
}

/// Median of float32 values as Numba's `np.median` and NumPy's `median`
/// return it: the middle element, or the float32 sum of the two middle
/// elements halved. `values` is reordered.
pub fn median_f32(values: &mut [f32]) -> f32 {
    let n = values.len();
    assert!(n > 0, "median of nothing");
    let (lower, &mut upper, _) = values.select_nth_unstable_by(n / 2, |a, b| a.total_cmp(b));
    if n % 2 == 1 {
        upper
    } else {
        let low = lower
            .iter()
            .copied()
            .max_by(|a, b| a.total_cmp(b))
            .expect("even length has a lower half");
        (low + upper) / 2.0
    }
}

/// `_time_median`: per channel, the median over unflagged times; zero and
/// flagged where nothing is unflagged.
fn time_median(data: &[f32], flags: &[bool], ntime: usize, nchan: usize) -> (Vec<f32>, Vec<bool>) {
    let mut out = vec![0f32; nchan];
    let mut out_flags = vec![false; nchan];
    let mut values = Vec::with_capacity(ntime);
    for f in 0..nchan {
        values.clear();
        for t in 0..ntime {
            if !flags[t * nchan + f] {
                values.push(data[t * nchan + f]);
            }
        }
        if values.is_empty() {
            out_flags[f] = true;
        } else {
            out[f] = median_f32(&mut values);
        }
    }
    (out, out_flags)
}

/// `_median_abs`: median of the absolute unflagged values, NaN if none.
fn median_abs(data: &[f32], flags: &[bool]) -> f64 {
    let mut values: Vec<f32> = data
        .iter()
        .zip(flags)
        .filter(|&(_, &flag)| !flag)
        .map(|(&v, _)| v.abs())
        .collect();
    if values.is_empty() {
        f64::NAN
    } else {
        median_f32(&mut values) as f64
    }
}

/// `_median_abs_axis0` on a `(rows, cols)` block: per column, the median of
/// the absolute unflagged values stored as float32, NaN if none.
fn median_abs_axis0(data: &[f32], flags: &[bool], rows: usize, cols: usize) -> Vec<f32> {
    let mut out = vec![f32::NAN; cols];
    let mut values = Vec::with_capacity(rows);
    for j in 0..cols {
        values.clear();
        for i in 0..rows {
            if !flags[i * cols + j] {
                values.push(data[i * cols + j].abs());
            }
        }
        if !values.is_empty() {
            out[j] = median_f32(&mut values);
        }
    }
    out
}

/// `_linearly_interpolate_nans1d`, in place.
fn interpolate_nans_1d(data: &mut [f32]) {
    let n = data.len();
    let mut p = 0;
    while p < n && data[p].is_nan() {
        p += 1;
    }
    if p == n {
        data.fill(0.0);
        return;
    }
    let first = data[p];
    data[..p].fill(first);
    p += 1;
    while p < n {
        if data[p].is_nan() {
            let mut q = p + 1;
            while q < n && data[q].is_nan() {
                q += 1;
            }
            if q == n {
                let last = data[p - 1];
                data[p..].fill(last);
            } else {
                let start = data[p - 1];
                // float32 difference, float64 gradient and interpolation.
                let grad = (data[q] - start) as f64 / (q - (p - 1)) as f64;
                for (i, value) in data.iter_mut().enumerate().take(q).skip(p) {
                    *value = (start as f64 + (i - (p - 1)) as f64 * grad) as f32;
                }
            }
            p = q;
        } else {
            p += 1;
        }
    }
}

/// Reusable buffers of the box filters, one set per worker (task P3,
/// `research/p3-sumthreshold.md`). Contents never carry over between calls:
/// every user clears and resizes what it takes.
#[derive(Default)]
struct Scratch {
    padded: Vec<f32>,
    acc: Vec<f64>,
    lanes: Vec<f32>,
    weight: Vec<f32>,
}

/// Rows of a block filtered together along its second axis: the rows become
/// the lanes of the column-wise kernels (`box_gaussian_filter`,
/// `sum_threshold`).
const LANE_GROUP: usize = 64;

/// `_box_gaussian_filter1d` along the first axis of a `(rows, cols)` block,
/// in place: `passes` boxcar sums of radius `r` in a double accumulator with
/// float32 storage between passes, then division by `(2r+1)^passes` in
/// float32 (Numba evaluates `float32 ** int` in float32).
#[cfg(test)]
fn box_filter_axis0(buf: &mut [f32], rows: usize, cols: usize, r: usize, passes: usize) {
    let (mut padded, mut acc) = (Vec::new(), Vec::new());
    box_filter_axis0_with(buf, rows, cols, r, passes, &mut padded, &mut acc);
}

/// `box_filter_axis0` with caller-owned buffers. Every column is an
/// independent lane with the same sequence of float operations as a
/// one-column call, so grouping columns (or transposed rows) into lanes does
/// not change any value; the lane loops are what the compiler vectorises.
fn box_filter_axis0_with(
    buf: &mut [f32],
    rows: usize,
    cols: usize,
    r: usize,
    passes: usize,
    padded: &mut Vec<f32>,
    s: &mut Vec<f64>,
) {
    if rows == 0 || passes == 0 {
        return;
    }
    let d = 2 * r + 1;
    let padding = r * passes;
    let prow = rows + padding;
    padded.clear();
    padded.resize(prow * cols, 0.0);
    padded[padding * cols..].copy_from_slice(&buf[..rows * cols]);
    let mut prev_start = padding as isize;
    s.clear();
    s.resize(cols, 0.0);
    for p in 1..=passes {
        s.fill(0.0);
        let mut start = padding as isize - 2 * (r * p) as isize;
        let mut stop = start + (rows + 2 * padding) as isize;
        start = start.max(0);
        stop = stop.min(prow as isize);
        let tail = stop.min(prow as isize - 2 * r as isize);
        let pre_end = (start + 2 * r as isize).min(prow as isize);
        for i in prev_start..pre_end {
            let row = &padded[i as usize * cols..(i as usize + 1) * cols];
            lanes_add(s, row);
        }
        for i in start..tail {
            let i = i as usize;
            let (head, right) = padded.split_at_mut((i + 2 * r) * cols);
            lanes_slide(s, &mut head[i * cols..(i + 1) * cols], &right[..cols]);
        }
        for i in tail.max(start)..stop {
            let i = i as usize;
            lanes_drain(s, &mut padded[i * cols..(i + 1) * cols]);
        }
        prev_start = start;
    }
    let scale = powi_f32(d as f32, passes);
    for (out, &v) in buf[..rows * cols].iter_mut().zip(&padded[..rows * cols]) {
        *out = v / scale;
    }
}

// The lane loops of the box filter. Blocks of `LANES` lanes are loaded into
// registers, updated and stored back, so the compiler emits vector
// instructions without having to prove that the reused buffers do not
// overlap; every lane performs the scalar loop's operations in its order.

/// Lanes per register block (two AVX2 registers of doubles).
const LANES: usize = 8;

/// `acc += row` in double precision.
#[inline(always)]
fn lanes_add(acc: &mut [f64], row: &[f32]) {
    let n = acc.len().min(row.len());
    let (acc, row) = (&mut acc[..n], &row[..n]);
    let mut a_blocks = acc.chunks_exact_mut(LANES);
    let mut r_blocks = row.chunks_exact(LANES);
    for (a, r) in (&mut a_blocks).zip(&mut r_blocks) {
        let mut av: [f64; LANES] = a.try_into().expect("block");
        let rv: [f32; LANES] = r.try_into().expect("block");
        for k in 0..LANES {
            av[k] += rv[k] as f64;
        }
        a.copy_from_slice(&av);
    }
    for (a, &v) in a_blocks
        .into_remainder()
        .iter_mut()
        .zip(r_blocks.remainder())
    {
        *a += v as f64;
    }
}

/// One step of the running boxcar: take in `incoming`, store the sum in
/// `current` as float32, drop the value `current` held.
#[inline(always)]
fn lanes_slide(acc: &mut [f64], current: &mut [f32], incoming: &[f32]) {
    let n = acc.len().min(current.len()).min(incoming.len());
    let (acc, current, incoming) = (&mut acc[..n], &mut current[..n], &incoming[..n]);
    let mut a_blocks = acc.chunks_exact_mut(LANES);
    let mut c_blocks = current.chunks_exact_mut(LANES);
    let mut x_blocks = incoming.chunks_exact(LANES);
    for ((a, c), x) in (&mut a_blocks).zip(&mut c_blocks).zip(&mut x_blocks) {
        let mut av: [f64; LANES] = (&*a).try_into().expect("block");
        let mut cv: [f32; LANES] = (&*c).try_into().expect("block");
        let xv: [f32; LANES] = x.try_into().expect("block");
        for k in 0..LANES {
            av[k] += xv[k] as f64;
            let prev = cv[k];
            cv[k] = av[k] as f32;
            av[k] -= prev as f64;
        }
        a.copy_from_slice(&av);
        c.copy_from_slice(&cv);
    }
    for ((a, value), &x) in a_blocks
        .into_remainder()
        .iter_mut()
        .zip(c_blocks.into_remainder())
        .zip(x_blocks.remainder())
    {
        *a += x as f64;
        let prev = *value;
        *value = *a as f32;
        *a -= prev as f64;
    }
}

/// The boxcar's tail: store the sum, drop the value `current` held.
#[inline(always)]
fn lanes_drain(acc: &mut [f64], current: &mut [f32]) {
    let n = acc.len().min(current.len());
    let (acc, current) = (&mut acc[..n], &mut current[..n]);
    let mut a_blocks = acc.chunks_exact_mut(LANES);
    let mut c_blocks = current.chunks_exact_mut(LANES);
    for (a, c) in (&mut a_blocks).zip(&mut c_blocks) {
        let mut av: [f64; LANES] = (&*a).try_into().expect("block");
        let mut cv: [f32; LANES] = (&*c).try_into().expect("block");
        for k in 0..LANES {
            let prev = cv[k];
            cv[k] = av[k] as f32;
            av[k] -= prev as f64;
        }
        a.copy_from_slice(&av);
        c.copy_from_slice(&cv);
    }
    for (a, value) in a_blocks
        .into_remainder()
        .iter_mut()
        .zip(c_blocks.into_remainder())
    {
        let prev = *value;
        *value = *a as f32;
        *a -= prev as f64;
    }
}

/// `float32 ** int` by squaring, as Numba's `int_power_impl` does.
fn powi_f32(base: f32, mut exponent: usize) -> f32 {
    let mut result = 1.0f32;
    let mut a = base;
    while exponent > 0 {
        if exponent & 1 == 1 {
            result *= a;
        }
        a *= a;
        exponent >>= 1;
    }
    result
}

/// Boxcar radius of `_box_gaussian_filter` for one axis.
fn box_radius(sigma: f64, passes: usize) -> usize {
    (0.5 * (12.0 * (sigma * sigma) / passes as f64 + 1.0).sqrt()) as i64 as usize
}

/// `out[j * rows + i] = src[i * cols + j]` for a `(rows, cols)` block.
fn transpose<T: Copy>(src: &[T], rows: usize, cols: usize, out: &mut [T]) {
    for (i, row) in src[..rows * cols].chunks_exact(cols).enumerate() {
        for (j, &v) in row.iter().enumerate() {
            out[j * rows + i] = v;
        }
    }
}

/// `_box_gaussian_filter` on a `(rows, cols)` block, in place.
fn box_gaussian_filter(
    buf: &mut [f32],
    rows: usize,
    cols: usize,
    sigma: [f64; 2],
    scratch: &mut Scratch,
) {
    let r0 = box_radius(sigma[0], PASSES);
    let r1 = box_radius(sigma[1], PASSES);
    let Scratch {
        padded, acc, lanes, ..
    } = scratch;
    if r0 > 0 {
        // Column chunks keep the padded working set in cache, as Tricolour's
        // `step = 256` does; columns are independent, so the result is the
        // same.
        const STEP: usize = 256;
        lanes.clear();
        lanes.resize(rows * STEP.min(cols), 0.0);
        for c0 in (0..cols).step_by(STEP) {
            let width = (cols - c0).min(STEP);
            for i in 0..rows {
                lanes[i * width..(i + 1) * width]
                    .copy_from_slice(&buf[i * cols + c0..i * cols + c0 + width]);
            }
            box_filter_axis0_with(
                &mut lanes[..rows * width],
                rows,
                width,
                r0,
                PASSES,
                padded,
                acc,
            );
            for i in 0..rows {
                buf[i * cols + c0..i * cols + c0 + width]
                    .copy_from_slice(&lanes[i * width..(i + 1) * width]);
            }
        }
    }
    if r1 > 0 {
        // Along the second axis: groups of rows transposed into lanes, so
        // that each row is filtered with the same operations as a
        // one-column call but the rows advance together (task P3).
        lanes.clear();
        lanes.resize(cols * LANE_GROUP.min(rows), 0.0);
        for i0 in (0..rows).step_by(LANE_GROUP) {
            let group = (rows - i0).min(LANE_GROUP);
            let block = &mut buf[i0 * cols..(i0 + group) * cols];
            transpose(block, group, cols, lanes);
            box_filter_axis0_with(
                &mut lanes[..cols * group],
                cols,
                group,
                r1,
                PASSES,
                padded,
                acc,
            );
            transpose(&lanes[..cols * group], cols, group, block);
        }
    }
}

/// `masked_gaussian_filter`: Gaussian-filtered data divided by the filtered
/// weights, NaN where no weight survives.
fn masked_gaussian_filter(
    data: &[f32],
    flags: &[bool],
    rows: usize,
    cols: usize,
    sigma: [f64; 2],
    out: &mut [f32],
    scratch: &mut Scratch,
) {
    let mut weight = std::mem::take(&mut scratch.weight);
    weight.clear();
    weight.resize(rows * cols, 0.0);
    for idx in 0..rows * cols {
        weight[idx] = if flags[idx] { 0.0 } else { 1.0 };
        out[idx] = if flags[idx] { 0.0 } else { data[idx] };
    }
    box_gaussian_filter(&mut weight, rows, cols, sigma, scratch);
    box_gaussian_filter(out, rows, cols, sigma, scratch);
    for idx in 0..rows * cols {
        if weight[idx] == 0.0 {
            out[idx] = f32::NAN;
        } else {
            out[idx] /= weight[idx];
        }
    }
    scratch.weight = weight;
}

/// `_get_background2d` on a `(rows, cols)` block.
#[allow(clippy::too_many_arguments)]
fn background_2d(
    data: &[f32],
    flags: &[bool],
    rows: usize,
    cols: usize,
    iterations: i64,
    spike_width: [f64; 2],
    reject_threshold: f64,
    chunk_ends: &[usize],
    scratch: &mut Scratch,
) -> Vec<f32> {
    let mut flags = flags.to_vec();
    let mut background = vec![0f32; rows * cols];
    let mut residual_values = Vec::new();
    let mut residual_flags = Vec::new();
    let mut extend_factor = iterations;
    while extend_factor > 0 {
        let sigma = [
            extend_factor as f64 * spike_width[0],
            extend_factor as f64 * spike_width[1],
        ];
        masked_gaussian_filter(data, &flags, rows, cols, sigma, &mut background, scratch);
        for c in 0..chunk_ends.len() - 1 {
            let (lo, hi) = (chunk_ends[c], chunk_ends[c + 1]);
            residual_values.clear();
            residual_flags.clear();
            for t in 0..rows {
                for f in lo..hi {
                    let idx = t * cols + f;
                    background[idx] = (data[idx] - background[idx]).abs();
                    residual_values.push(background[idx]);
                    residual_flags.push(flags[idx]);
                }
            }
            let mut threshold = median_abs(&residual_values, &residual_flags);
            threshold *= MAD_NORMAL * reject_threshold;
            for t in 0..rows {
                for f in lo..hi {
                    let idx = t * cols + f;
                    if background[idx] as f64 > threshold {
                        flags[idx] = true;
                    }
                }
            }
        }
        extend_factor -= 1;
    }
    masked_gaussian_filter(
        data,
        &flags,
        rows,
        cols,
        spike_width,
        &mut background,
        scratch,
    );
    for i in 0..rows {
        interpolate_nans_1d(&mut background[i * cols..(i + 1) * cols]);
    }
    background
}

/// `_convolve_flags`: threshold scaled values, smear by a box of `window`
/// and OR into `out_flags`; `in_values` is `(n_in, cols)`, `out_flags`
/// `(n_out, cols)` with `n_in = n_out - window + 1`.
#[allow(clippy::too_many_arguments)]
fn convolve_flags(
    in_values: &[f64],
    n_in: usize,
    cols: usize,
    scale: f32,
    threshold: &[f64],
    out_flags: &mut [bool],
    n_out: usize,
    window: usize,
) {
    let cum_size = n_in + 2 * window - 1;
    let mut cum = vec![0u32; cum_size * cols];
    for i in 0..n_in {
        for j in 0..cols {
            let flag = in_values[i * cols + j] * scale as f64 > threshold[j];
            cum[(window + i) * cols + j] = cum[(window + i - 1) * cols + j] + flag as u32;
        }
    }
    let last = (cum_size - window) * cols;
    for i in cum_size - (window - 1)..cum_size {
        let (head, tail) = cum.split_at_mut(i * cols);
        tail[..cols].copy_from_slice(&head[last..last + cols]);
    }
    for i in 0..n_out {
        for j in 0..cols {
            out_flags[i * cols + j] |= cum[(i + window) * cols + j] != cum[i * cols + j];
        }
    }
}

/// `_sum_threshold1d` along the first axis of a `(n, cols)` block.
#[allow(clippy::too_many_arguments)]
fn sum_threshold_axis0(
    data: &[f32],
    flags: &[bool],
    out: &mut [bool],
    n: usize,
    cols: usize,
    windows: &[i64],
    outlier_nsigma: f64,
    rho: f64,
    chunks: &[usize],
) {
    let max_window = windows.iter().copied().max().unwrap_or(1).max(1) as usize;
    for ci in 0..chunks.len() - 1 {
        let (c0, c1) = (chunks[ci], chunks[ci + 1]);
        let rows = c1 - c0;
        let mut threshold = median_abs_axis0(
            &data[c0 * cols..c1 * cols],
            &flags[c0 * cols..c1 * cols],
            rows,
            cols,
        );
        let threshold_scale = outlier_nsigma * MAD_NORMAL;
        for value in threshold.iter_mut() {
            if value.is_nan() {
                *value = f32::INFINITY;
            } else {
                *value = (*value as f64 * threshold_scale) as f32;
            }
        }
        let p0 = c0.saturating_sub(max_window - 1);
        let p1 = (c1 + max_window - 1).min(n);
        let plen = p1 - p0;
        let padded = &data[p0 * cols..p1 * cols];
        let mut pos = vec![false; plen * cols];
        let mut neg = vec![false; plen * cols];
        let mut cum = vec![0f64; (plen + 1) * cols];
        let mut avg = Vec::new();
        for &window in windows {
            let w = window as usize;
            let tf = rho.powf((window as f64).log2());
            let this_threshold: Vec<f64> = threshold.iter().map(|&t| t as f64 / tf).collect();
            cum[..cols].fill(0.0);
            for i in 0..plen {
                for (j, &limit) in this_threshold.iter().enumerate() {
                    let idx = i * cols + j;
                    let mut clamped = padded[idx] as f64;
                    if pos[idx] && clamped > limit {
                        clamped = limit;
                    } else if neg[idx] && clamped < -limit {
                        clamped = -limit;
                    }
                    cum[idx + cols] = cum[idx] + clamped;
                }
            }
            let n_avg = plen + 1 - w;
            avg.clear();
            avg.resize(n_avg * cols, 0.0);
            for i in 0..n_avg {
                for j in 0..cols {
                    avg[i * cols + j] = cum[(i + w) * cols + j] - cum[i * cols + j];
                }
            }
            let rolling_scale = (1.0 / window as f64) as f32;
            convolve_flags(
                &avg,
                n_avg,
                cols,
                rolling_scale,
                &this_threshold,
                &mut pos,
                plen,
                w,
            );
            convolve_flags(
                &avg,
                n_avg,
                cols,
                -rolling_scale,
                &this_threshold,
                &mut neg,
                plen,
                w,
            );
        }
        let rel = c0 - p0;
        for i in 0..rows {
            for j in 0..cols {
                out[(c0 + i) * cols + j] = pos[(rel + i) * cols + j] | neg[(rel + i) * cols + j];
            }
        }
    }
}

/// `_sum_threshold` on a `(n0, n1)` block along `axis` 0 or 1.
#[allow(clippy::too_many_arguments)]
fn sum_threshold(
    data: &[f32],
    flags: &[bool],
    n0: usize,
    n1: usize,
    axis: usize,
    windows: &[i64],
    outlier_nsigma: f64,
    rho: f64,
    chunks: Option<&[usize]>,
) -> Vec<bool> {
    let mut out = vec![false; n0 * n1];
    match axis {
        1 => {
            let default = [0, n1];
            let chunks = chunks.unwrap_or(&default);
            // Each row is an independent one-column problem; groups of rows
            // are transposed into the lanes of one axis-0 call, which keeps
            // every lane's operations as in a one-column call (task P3).
            let group_max = LANE_GROUP.min(n0);
            let mut lane_data = vec![0f32; n1 * group_max];
            let mut lane_flags = vec![false; n1 * group_max];
            let mut lane_out = vec![false; n1 * group_max];
            for i0 in (0..n0).step_by(LANE_GROUP) {
                let group = (n0 - i0).min(LANE_GROUP);
                let len = n1 * group;
                let rows = i0 * n1..(i0 + group) * n1;
                transpose(&data[rows.clone()], group, n1, &mut lane_data);
                transpose(&flags[rows.clone()], group, n1, &mut lane_flags);
                sum_threshold_axis0(
                    &lane_data[..len],
                    &lane_flags[..len],
                    &mut lane_out[..len],
                    n1,
                    group,
                    windows,
                    outlier_nsigma,
                    rho,
                    chunks,
                );
                transpose(&lane_out[..len], n1, group, &mut out[rows]);
            }
        }
        0 => {
            let default = [0, n0];
            let chunks = chunks.unwrap_or(&default);
            sum_threshold_axis0(
                data,
                flags,
                &mut out,
                n0,
                n1,
                windows,
                outlier_nsigma,
                rho,
                chunks,
            );
        }
        _ => panic!("axis must be 0 or 1"),
    }
    out
}

/// `_combine_flags`: OR the spectral, time and frequency flags and smear in
/// time with a box of `time_extend`.
fn combine_flags(
    spec_flags: &[bool],
    time_flags: &[bool],
    freq_flags: &[bool],
    ntime: usize,
    nchan: usize,
    time_extend: usize,
    out: &mut [bool],
) {
    let mut flag_sum = vec![0u32; (ntime + 1) * nchan];
    for t in 0..ntime {
        for f in 0..nchan {
            let flag = spec_flags[f] || time_flags[t * nchan + f] || freq_flags[t * nchan + f];
            flag_sum[(t + 1) * nchan + f] = flag_sum[t * nchan + f] + flag as u32;
        }
    }
    let lo = -((time_extend / 2) as isize);
    let hi = lo + time_extend as isize;
    for t in 0..ntime {
        let t0 = (t as isize + lo).max(0) as usize;
        let t1 = (t as isize + hi).min(ntime as isize) as usize;
        for f in 0..nchan {
            out[t * nchan + f] = flag_sum[t0 * nchan + f] != flag_sum[t1 * nchan + f];
        }
    }
}

/// `_average_freq` for one correlation product: magnitudes averaged over
/// `factor` channels, flagged where nothing valid contributes.
fn average_freq(
    re: &[f32],
    im: &[f32],
    flags: &[bool],
    ntime: usize,
    nchan: usize,
    factor: usize,
) -> (Vec<f32>, Vec<bool>) {
    let a_freq = nchan.div_ceil(factor);
    let mut avg = vec![0f32; ntime * a_freq];
    let mut weight = vec![0u32; ntime * a_freq];
    for t in 0..ntime {
        for f in 0..nchan {
            let idx = t * nchan + f;
            let value = re[idx].hypot(im[idx]);
            if !flags[idx] && !value.is_nan() {
                avg[t * a_freq + f / factor] += value;
                weight[t * a_freq + f / factor] += 1;
            }
        }
    }
    let mut out_flags = vec![false; ntime * a_freq];
    for idx in 0..ntime * a_freq {
        if weight[idx] == 0 {
            avg[idx] = 0.0;
            out_flags[idx] = true;
        } else {
            avg[idx] /= weight[idx] as f32;
        }
    }
    (avg, out_flags)
}

/// `_unaverage_freq`: replicate averaged flags, smear in frequency and apply
/// the row and column fraction cuts.
#[allow(clippy::too_many_arguments)]
fn unaverage_freq(
    flags: &[bool],
    ntime: usize,
    a_freq: usize,
    freq_extend: usize,
    average_freq: usize,
    flag_all_time_frac: f64,
    flag_all_freq_frac: f64,
    out: &mut [bool],
    nchan: usize,
) {
    let mut flag_sum = vec![0i32; nchan + 1];
    let mut flag_sum_time = vec![0i32; nchan];
    let lo = -((freq_extend / 2) as isize);
    let hi = lo + freq_extend as isize;
    for t in 0..ntime {
        flag_sum[0] = 0;
        for f in 0..nchan {
            flag_sum[f + 1] = flag_sum[f] + flags[t * a_freq + f / average_freq] as i32;
        }
        let mut tot = 0i64;
        for f in 0..nchan {
            let f0 = (f as isize + lo).max(0) as usize;
            let f1 = (f as isize + hi).min(nchan as isize) as usize;
            let flag = flag_sum[f1] != flag_sum[f0];
            out[t * nchan + f] = flag;
            tot += flag as i64;
            flag_sum_time[f] += flag as i32;
        }
        if tot as f64 > flag_all_freq_frac * nchan as f64 {
            out[t * nchan..(t + 1) * nchan].fill(true);
        }
    }
    for f in 0..nchan {
        if flag_sum_time[f] as f64 > ntime as f64 * flag_all_time_frac {
            for t in 0..ntime {
                out[t * nchan + f] = true;
            }
        }
    }
}

/// `_get_baseline_flags` for one correlation product after averaging.
#[allow(clippy::too_many_arguments)]
fn baseline_flags(
    data: &mut [f32],
    flags: &mut [bool],
    ntime: usize,
    a_freq: usize,
    out: &mut [bool],
    nchan: usize,
    p: &SumThresholdParams,
    windows_time: &[i64],
    windows_freq: &[i64],
    chunk_ends: &[usize],
    scratch: &mut Scratch,
) {
    let (mut spec_data, spec_flags) = time_median(data, flags, ntime, a_freq);
    let spec_background = background_2d(
        &spec_data,
        &spec_flags,
        1,
        a_freq,
        p.background_iterations,
        [0.0, p.spike_width_freq],
        p.background_reject,
        chunk_ends,
        scratch,
    );
    for (v, b) in spec_data.iter_mut().zip(&spec_background) {
        *v -= *b;
    }
    let spec_flags = sum_threshold(
        &spec_data,
        &spec_flags,
        1,
        a_freq,
        1,
        windows_freq,
        p.outlier_nsigma,
        p.rho,
        Some(chunk_ends),
    );
    for t in 0..ntime {
        for f in 0..a_freq {
            flags[t * a_freq + f] |= spec_flags[f];
        }
    }
    let background = background_2d(
        data,
        flags,
        ntime,
        a_freq,
        p.background_iterations,
        [p.spike_width_time, p.spike_width_freq],
        p.background_reject,
        chunk_ends,
        scratch,
    );
    for (v, b) in data.iter_mut().zip(&background) {
        *v -= *b;
    }
    let time_flags = sum_threshold(
        data,
        flags,
        ntime,
        a_freq,
        0,
        windows_time,
        p.outlier_nsigma,
        p.rho,
        None,
    );
    for (f, t) in flags.iter_mut().zip(&time_flags) {
        *f |= *t;
    }
    let freq_flags = sum_threshold(
        data,
        flags,
        ntime,
        a_freq,
        1,
        windows_freq,
        p.outlier_nsigma,
        p.rho,
        Some(chunk_ends),
    );
    combine_flags(
        &spec_flags,
        &time_flags,
        &freq_flags,
        ntime,
        a_freq,
        p.time_extend,
        flags,
    );
    unaverage_freq(
        flags,
        ntime,
        a_freq,
        p.freq_extend,
        p.average_freq,
        p.flag_all_time_frac,
        p.flag_all_freq_frac,
        out,
        nchan,
    );
}

/// `np.linspace(0, stop, num + 1).astype(int)`.
fn linspace_int(stop: usize, num: usize) -> Vec<usize> {
    let step = stop as f64 / num as f64;
    let mut ends: Vec<usize> = (0..=num)
        .map(|i| (i as f64 * step) as i64 as usize)
        .collect();
    ends[num] = stop;
    ends
}

/// `sum_threshold_flagger`: returns the flags of the last major iteration
/// only, as Tricolour does; the executor ORs them with the running flags.
pub fn sum_threshold_flagger(window: &Window, flags: &[bool], p: &SumThresholdParams) -> Vec<bool> {
    let (nbl, ntime, nchan) = (window.nbl, window.ntime, window.nchan);
    let factor = p.average_freq.max(1);
    let mut windows_freq: Vec<i64> = p
        .windows_freq
        .iter()
        .map(|&w| ((w as f32).ceil() / factor as f32) as i64)
        .collect();
    windows_freq.sort_unstable();
    windows_freq.dedup();
    let a_freq = nchan.div_ceil(factor);
    let chunk_ends = linspace_int(a_freq, p.freq_chunks);
    let windows_time: Vec<i64> = p
        .windows_time
        .iter()
        .copied()
        .filter(|&w| w <= ntime as i64)
        .collect();
    let windows_freq: Vec<i64> = windows_freq
        .into_iter()
        .filter(|&w| w <= a_freq as i64)
        .collect();
    let plane = ntime * nchan;
    let mut out = vec![false; nbl * plane];
    if plane == 0 {
        return out;
    }
    // Baselines are independent: a major iteration reads and writes only the
    // baseline's own plane, so each baseline runs all its major iterations
    // on one worker, with the operations of the serial loop (task P3).
    let mut iter_flags = flags[..nbl * plane].to_vec();
    out.par_chunks_mut(plane)
        .zip(iter_flags.par_chunks_mut(plane))
        .enumerate()
        .for_each_init(Scratch::default, |scratch, (b, (out_b, iter_b))| {
            let re = &window.re[b * plane..(b + 1) * plane];
            let im = &window.im[b * plane..(b + 1) * plane];
            for _ in 0..p.num_major_iterations {
                let (mut data, mut a_flags) = average_freq(re, im, iter_b, ntime, nchan, factor);
                baseline_flags(
                    &mut data,
                    &mut a_flags,
                    ntime,
                    a_freq,
                    out_b,
                    nchan,
                    p,
                    &windows_time,
                    &windows_freq,
                    &chunk_ends,
                    scratch,
                );
                for idx in 0..plane {
                    out_b[idx] = out_b[idx] || re[idx].is_nan() || im[idx].is_nan();
                }
                for (i, o) in iter_b.iter_mut().zip(out_b.iter()) {
                    *i |= *o;
                }
            }
        });
    out
}

/// The truncated Fourier series of `uvcontsub_flagger`: the first `keep`
/// bins of the forward transform, inverse-transformed, in double precision.
fn lowpass_fit(re: &[f32], im: &[f32], keep: usize) -> (Vec<f32>, Vec<f32>) {
    let n = re.len();
    let keep = keep.min(n);
    let twiddle: Vec<(f64, f64)> = (0..n)
        .map(|m| {
            let angle = 2.0 * PI * m as f64 / n as f64;
            (angle.cos(), angle.sin())
        })
        .collect();
    let mut spectrum = Vec::with_capacity(keep);
    for k in 0..keep {
        let (mut sr, mut si) = (0.0f64, 0.0f64);
        let mut index = 0usize;
        for (&xr, &xi) in re.iter().zip(im) {
            let (c, s) = twiddle[index];
            // x * exp(-i angle)
            sr += xr as f64 * c + xi as f64 * s;
            si += xi as f64 * c - xr as f64 * s;
            index += k;
            if index >= n {
                index -= n;
            }
        }
        spectrum.push((sr, si));
    }
    let mut out_re = vec![0f32; n];
    let mut out_im = vec![0f32; n];
    for j in 0..n {
        let (mut sr, mut si) = (0.0f64, 0.0f64);
        let mut index = 0usize;
        for &(xr, xi) in &spectrum {
            let (c, s) = twiddle[index];
            // X * exp(+i angle)
            sr += xr * c - xi * s;
            si += xi * c + xr * s;
            index += j;
            if index >= n {
                index -= n;
            }
        }
        out_re[j] = (sr / n as f64) as f32;
        out_im[j] = (si / n as f64) as f32;
    }
    (out_re, out_im)
}

/// NumPy `nanmedian` of float32 values, NaN when nothing remains.
fn nanmedian_f32(values: &[f32]) -> f32 {
    let mut kept: Vec<f32> = values.iter().copied().filter(|v| !v.is_nan()).collect();
    if kept.is_empty() {
        f32::NAN
    } else {
        median_f32(&mut kept)
    }
}

/// `uvcontsub_flagger`: returns the new running flags (the executor replaces
/// the running flags with them).
pub fn uvcontsub_flagger(
    window: &Window,
    flags: &[bool],
    major_cycles: usize,
    or_original_from_cycle: usize,
    taylor_degrees: usize,
    sigma: f64,
) -> Vec<bool> {
    let (nbl, ntime, nchan) = (window.nbl, window.ntime, window.nchan);
    let plane = ntime * nchan;
    let mut result = flags[..nbl * plane].to_vec();
    if plane == 0 {
        return result;
    }
    let sigma32 = sigma as f32;
    // No coupling between baselines in this flagger: a cycle reads and
    // writes only the baseline's own plane, so each baseline runs all its
    // cycles on one worker, in the serial loop's order (task P3).
    let buffers = || {
        (
            vec![0f32; nchan],
            vec![0f32; nchan],
            vec![0f32; plane],
            vec![0f32; plane],
        )
    };
    result.par_chunks_mut(plane).enumerate().for_each_init(
        buffers,
        |(avg_re, avg_im, residual, scratch), (b, current)| {
            let re = &window.re[b * plane..(b + 1) * plane];
            let im = &window.im[b * plane..(b + 1) * plane];
            for cycle in 0..major_cycles {
                uvcontsub_cycle(
                    re,
                    im,
                    current,
                    ntime,
                    nchan,
                    cycle >= or_original_from_cycle,
                    taylor_degrees,
                    sigma32,
                    (
                        &mut avg_re[..],
                        &mut avg_im[..],
                        &mut residual[..],
                        &mut scratch[..],
                    ),
                );
            }
        },
    );
    result
}

/// One cycle of `uvcontsub_flagger` on one baseline's plane, in place.
#[allow(clippy::too_many_arguments)]
fn uvcontsub_cycle(
    re: &[f32],
    im: &[f32],
    current: &mut [bool],
    ntime: usize,
    nchan: usize,
    or_original: bool,
    taylor_degrees: usize,
    sigma32: f32,
    (avg_re, avg_im, residual, scratch): (&mut [f32], &mut [f32], &mut [f32], &mut [f32]),
) {
    let plane = ntime * nchan;
    if current.iter().all(|&f| f) {
        return;
    }
    // nanmean over time of the complex64 values with flagged samples
    // set to NaN: a sequential float32 sum of the non-NaN samples,
    // divided in double precision as NumPy's complex128 loop does
    // (multiplication by the reciprocal), rounded to complex64.
    for f in 0..nchan {
        let (mut tr, mut ti, mut count) = (0.0f32, 0.0f32, 0usize);
        for t in 0..ntime {
            let idx = t * nchan + f;
            let nan = current[idx] || re[idx].is_nan() || im[idx].is_nan();
            if !nan {
                tr += re[idx];
                ti += im[idx];
                count += 1;
            }
        }
        if count == 0 {
            avg_re[f] = 0.0;
            avg_im[f] = 0.0;
        } else {
            let scl = 1.0 / count as f64;
            avg_re[f] = (tr as f64 * scl) as f32;
            avg_im[f] = (ti as f64 * scl) as f32;
        }
    }
    let (fit_re, fit_im) = lowpass_fit(avg_re, avg_im, taylor_degrees);
    for t in 0..ntime {
        for f in 0..nchan {
            let idx = t * nchan + f;
            residual[idx] = (re[idx] - fit_re[f]).hypot(im[idx] - fit_im[f]);
        }
    }
    for idx in 0..plane {
        scratch[idx] = if current[idx] {
            f32::NAN
        } else {
            residual[idx]
        };
    }
    let median = nanmedian_f32(scratch);
    for value in scratch.iter_mut() {
        *value = (value.abs() - median).abs();
    }
    let mad = nanmedian_f32(scratch);
    let threshold = sigma32 * mad;
    for idx in 0..plane {
        let new = residual[idx] > threshold;
        if or_original {
            current[idx] |= new;
        } else {
            current[idx] = new;
        }
    }
}

/// `flag_nans_and_zeros`: "value is zero or NaN", which the executor ORs
/// into the running flags (the kernel itself ORs its input flags in).
pub fn flag_nans_zeros(window: &Window) -> Vec<bool> {
    window
        .re
        .par_iter()
        .zip(&window.im)
        .map(|(&r, &i)| (r == 0.0 && i == 0.0) || r.is_nan() || i.is_nan())
        .collect()
}

/// `apply_static_mask`: channels within half a width of a masked frequency,
/// on baselines selected by `uvrange`.
pub fn static_mask(ctx: &Context, window: &Window, uv_low: f64, uv_high: f64) -> Vec<bool> {
    let nchan = window.nchan;
    let mut channel_mask = vec![false; nchan];
    for mask in ctx.masks {
        let mut sorted: Vec<f64> = mask.iter().copied().filter(|v| !v.is_nan()).collect();
        sorted.sort_by(|a, b| a.total_cmp(b));
        for (f, masked) in channel_mask.iter_mut().enumerate() {
            let lb = ctx.chan_freq[f] - ctx.chan_width[f] * 0.5;
            let ub = ctx.chan_freq[f] + ctx.chan_width[f] * 0.5;
            // A masked frequency in [lb, ub): the first value >= lb is < ub.
            let first = sorted.partition_point(|&v| v < lb);
            if first < sorted.len() && sorted[first] < ub {
                *masked = true;
            }
        }
    }
    let plane = window.ntime * nchan;
    let mut out = vec![false; window.nbl * plane];
    if plane == 0 {
        return out;
    }
    out.par_chunks_mut(plane)
        .zip(ctx.baselines.par_iter())
        .for_each(|(out_b, &(a1, a2))| {
            let mut d2 = 0.0f64;
            for k in 0..3 {
                let delta = ctx.antenna_position[a1 * 3 + k] - ctx.antenna_position[a2 * 3 + k];
                d2 += delta * delta;
            }
            d2 *= 0.5;
            let low = uv_low.min(uv_high);
            let high = uv_low.max(uv_high);
            if d2 >= low * low && d2 <= high * high {
                for row in out_b.chunks_exact_mut(nchan) {
                    row.copy_from_slice(&channel_mask);
                }
            }
        });
    out
}

/// `strat_executor.StrategyExecutor.apply_strategies`.
pub fn apply_strategies(
    ctx: &Context,
    window: &Window,
    input_flags: &[bool],
    steps: &[Step],
    mut stage: impl FnMut(usize, &[bool]),
) -> Vec<bool> {
    let plane = window.ntime * window.nchan;
    let mut flags = input_flags.to_vec();
    for (index, step) in steps.iter().enumerate() {
        match step {
            Step::FlagNansZeros => {
                for (f, n) in flags.iter_mut().zip(flag_nans_zeros(window)) {
                    *f |= n;
                }
            }
            Step::StaticMask {
                or,
                uv_low,
                uv_high,
            } => {
                let new = static_mask(ctx, window, *uv_low, *uv_high);
                if *or {
                    for (f, n) in flags.iter_mut().zip(&new) {
                        *f |= *n;
                    }
                } else {
                    flags = new;
                }
            }
            Step::SumThreshold(p) => {
                let new = sum_threshold_flagger(window, &flags, p);
                for (f, n) in flags.iter_mut().zip(&new) {
                    *f |= *n;
                }
            }
            Step::UvContSub {
                major_cycles,
                or_original_from_cycle,
                taylor_degrees,
                sigma,
            } => {
                flags = uvcontsub_flagger(
                    window,
                    &flags,
                    *major_cycles,
                    *or_original_from_cycle,
                    *taylor_degrees,
                    *sigma,
                );
            }
            Step::FlagAutos => {
                for (b, &(a1, a2)) in ctx.baselines.iter().enumerate() {
                    if a1 == a2 {
                        flags[b * plane..(b + 1) * plane].fill(true);
                    }
                }
            }
            Step::CombineWithInputFlags => {
                for (f, o) in flags.iter_mut().zip(input_flags) {
                    *f |= *o;
                }
            }
            Step::Unflag => flags.fill(false),
        }
        stage(index, &flags);
    }
    flags
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn median_rounds_the_midpoint_sum_in_float32() {
        let mut odd = [3.0f32, 1.0, 2.0];
        assert_eq!(median_f32(&mut odd), 2.0);
        let a = 16777216.0f32;
        let b = 16777219.0f32;
        let mut even = [b, a];
        // (a + b) rounds to 16777236 in float32 before halving.
        assert_eq!(median_f32(&mut even), (a + b) / 2.0);
    }

    #[test]
    fn box_filter_matches_a_direct_boxcar_for_one_pass() {
        let data = [1.0f32, 2.0, 3.0, 4.0, 5.0];
        let mut buf = data;
        box_filter_axis0(&mut buf, 5, 1, 1, 1);
        let expected = [3.0 / 3.0, 6.0 / 3.0, 9.0 / 3.0, 12.0 / 3.0, 9.0 / 3.0];
        assert_eq!(buf, expected);
    }

    #[test]
    fn box_radius_truncates() {
        assert_eq!(box_radius(10.0, 4), 8);
        assert_eq!(box_radius(12.5, 4), 10);
        assert_eq!(box_radius(64.0, 4), 55);
        assert_eq!(box_radius(0.0, 4), 0);
    }

    #[test]
    fn linspace_matches_numpy_truncation() {
        assert_eq!(
            linspace_int(4096, 10),
            [0, 409, 819, 1228, 1638, 2048, 2457, 2867, 3276, 3686, 4096]
        );
    }

    #[test]
    fn convolve_flags_smears_by_the_window() {
        let values = [0.0f64, 0.0, 10.0, 0.0, 0.0];
        let threshold = [1.0];
        let mut out = vec![false; 6];
        convolve_flags(&values, 5, 1, 1.0, &threshold, &mut out, 6, 2);
        assert_eq!(out, [false, false, true, true, false, false]);
    }

    #[test]
    fn lowpass_keeping_everything_is_the_identity() {
        let re = [1.0f32, -2.0, 0.5, 3.0, 0.25, -1.0, 2.0, 0.0];
        let im = [0.0f32; 8];
        let (fr, fi) = lowpass_fit(&re, &im, 8);
        for i in 0..8 {
            assert!((fr[i] - re[i]).abs() < 1e-6, "{i}");
            assert!(fi[i].abs() < 1e-6, "{i}");
        }
    }

    #[test]
    fn polarised_intensity_of_pure_stokes_i_is_zero() {
        let map = polarised_map(&[9, 10, 11, 12]);
        assert_eq!(map.len(), 3);
        let vis = [(2.0f32, 0.0), (0.0, 0.0), (0.0, 0.0), (2.0, 0.0)];
        assert_eq!(polarised_intensity(&vis, &map), 0.0);
        let vis = [(2.0f32, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)];
        assert_eq!(polarised_intensity(&vis, &map), 1.0);
    }

    /// Deterministic xorshift noise with sparse bright spikes and flags.
    fn noise(n: usize, seed: u64) -> (Vec<f32>, Vec<bool>) {
        let mut state = seed | 1;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64
        };
        let mut data = Vec::with_capacity(n);
        let mut flags = Vec::with_capacity(n);
        for _ in 0..n {
            let mut v = (0..4).map(|_| next()).sum::<f64>() - 2.0;
            if next() < 0.01 {
                v += 40.0 * next();
            }
            data.push(v as f32);
            flags.push(next() < 0.05);
        }
        (data, flags)
    }

    /// `_box_gaussian_filter` in Tricolour's per-row form: the time axis in
    /// one call over all columns, the frequency axis one row at a time with
    /// one column per call (task D's arrangement before task P3).
    fn box_gaussian_filter_reference(buf: &mut [f32], rows: usize, cols: usize, sigma: [f64; 2]) {
        let r0 = box_radius(sigma[0], PASSES);
        let r1 = box_radius(sigma[1], PASSES);
        if r0 > 0 {
            box_filter_axis0(buf, rows, cols, r0, PASSES);
        }
        if r1 > 0 {
            for i in 0..rows {
                box_filter_axis0(&mut buf[i * cols..(i + 1) * cols], cols, 1, r1, PASSES);
            }
        }
    }

    fn bits(values: &[f32]) -> Vec<u32> {
        values.iter().map(|v| v.to_bits()).collect()
    }

    #[test]
    fn lane_grouped_box_filter_equals_per_row_calls() {
        let mut scratch = Scratch::default();
        for &(rows, cols, sigma) in &[
            (1usize, 4096usize, [0.0, 10.0]),
            (14, 4096, [12.5, 10.0]),
            (70, 301, [2.0, 3.7]),
            (129, 37, [0.0, 1.5]),
            (5, 3, [6.0, 9.0]),
        ] {
            let (data, _) = noise(rows * cols, (rows * 31 + cols) as u64);
            let mut expected = data.clone();
            box_gaussian_filter_reference(&mut expected, rows, cols, sigma);
            let mut got = data.clone();
            box_gaussian_filter(&mut got, rows, cols, sigma, &mut scratch);
            assert_eq!(bits(&got), bits(&expected), "{rows}x{cols} {sigma:?}");
        }
    }

    #[test]
    fn lane_grouped_sum_threshold_equals_per_row_calls() {
        let windows = [1i64, 2, 4, 8, 16];
        for &(n0, n1, nchunks) in &[(1usize, 4096usize, 10usize), (70, 257, 3), (14, 409, 1)] {
            let (data, flags) = noise(n0 * n1, (n0 * 7 + n1) as u64);
            let chunks = linspace_int(n1, nchunks);
            let mut expected = vec![false; n0 * n1];
            for i in 0..n0 {
                sum_threshold_axis0(
                    &data[i * n1..(i + 1) * n1],
                    &flags[i * n1..(i + 1) * n1],
                    &mut expected[i * n1..(i + 1) * n1],
                    n1,
                    1,
                    &windows,
                    4.5,
                    1.3,
                    &chunks,
                );
            }
            let got = sum_threshold(&data, &flags, n0, n1, 1, &windows, 4.5, 1.3, Some(&chunks));
            assert!(
                expected.iter().any(|&f| f),
                "the test data must flag something"
            );
            assert_eq!(got, expected, "{n0}x{n1}");
        }
    }

    fn default_params() -> SumThresholdParams {
        SumThresholdParams {
            outlier_nsigma: 4.5,
            windows_time: vec![1, 2, 4, 8],
            windows_freq: vec![1, 2, 4, 8],
            background_reject: 2.0,
            background_iterations: 1,
            spike_width_time: 12.5,
            spike_width_freq: 10.0,
            time_extend: 3,
            freq_extend: 3,
            freq_chunks: 10,
            average_freq: 1,
            flag_all_time_frac: 0.6,
            flag_all_freq_frac: 0.8,
            rho: 1.3,
            num_major_iterations: 5,
        }
    }

    #[test]
    fn flaggers_are_identical_across_thread_counts() {
        let (nbl, ntime, nchan) = (7, 20, 300);
        let (re, flags) = noise(nbl * ntime * nchan, 11);
        let (im, _) = noise(nbl * ntime * nchan, 12);
        let mut flags = flags;
        // One fully flagged baseline exercises the uvcontsub early exit.
        flags[2 * ntime * nchan..3 * ntime * nchan].fill(true);
        let window = Window {
            nbl,
            ntime,
            nchan,
            re,
            im,
        };
        let p = default_params();
        let mut reference = None;
        for threads in [1, 3, 8] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .expect("thread pool");
            let result = pool.install(|| {
                (
                    sum_threshold_flagger(&window, &flags, &p),
                    uvcontsub_flagger(&window, &flags, 5, 1, 20, 5.0),
                    flag_nans_zeros(&window),
                )
            });
            match &reference {
                None => {
                    assert!(result.0.iter().any(|&f| f) && !result.0.iter().all(|&f| f));
                    reference = Some(result);
                }
                Some(expected) => assert_eq!(&result, expected, "{threads} threads"),
            }
        }
    }

    #[test]
    fn executor_combines_input_flags_and_autos() {
        let window = Window {
            nbl: 2,
            ntime: 1,
            nchan: 2,
            re: vec![1.0, 0.0, 1.0, 1.0],
            im: vec![0.0; 4],
        };
        let positions = [0.0, 0.0, 0.0, 10.0, 0.0, 0.0];
        let ctx = Context {
            baselines: &[(0, 0), (0, 1)],
            antenna_position: &positions,
            chan_freq: &[1.0e9, 1.1e9],
            chan_width: &[1.0e8, 1.0e8],
            masks: &[],
        };
        let input = [false, false, false, true];
        let steps = [
            Step::FlagNansZeros,
            Step::FlagAutos,
            Step::CombineWithInputFlags,
        ];
        let mut seen = 0;
        let out = apply_strategies(&ctx, &window, &input, &steps, |index, flags| {
            seen += 1;
            if index == 0 {
                // The zero at (0, 1) and the input flag at (1, 1) are both kept.
                assert_eq!(flags, [false, true, false, true]);
            }
        });
        assert_eq!(seen, 3);
        assert_eq!(out, [true, true, false, true]);
    }
}
