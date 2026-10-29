//! C ABI for the Tricolour port (`sumthreshold`), loaded through ctypes by
//! `python/rangtoy/core_flag.py`. Same conventions as `ffi.rs`: borrowed
//! buffers described by explicit lengths, 0 on success, 1 on invalid
//! arguments, 2 on a panic.

use crate::sumthreshold::{
    self, Context, Step, SumThresholdParams, Window, polarised_intensity, polarised_map,
};

/// Width of one encoded strategy step in doubles.
pub const STEP_WIDTH: usize = 32;

/// Borrowed inputs for `rang_core_flag_rows`.
#[repr(C)]
pub struct FlagInputs {
    pub nrow: usize,
    pub nchan: usize,
    pub ncorr: usize,
    pub nant: usize,
    pub nbl: usize,
    pub ntime: usize,
    pub nmasks: usize,
    pub nsteps: usize,
    /// Interleaved complex64, `nrow * nchan * ncorr * 2`.
    pub data: *const f32,
    /// Input flags, `nrow * nchan * ncorr`.
    pub flags: *const u8,
    /// Window baseline index per row, `nrow`.
    pub baseline_index: *const u32,
    /// Window time index per row, `nrow`.
    pub time_index: *const u32,
    /// `(antenna1, antenna2)` per window baseline, `nbl * 2`.
    pub baselines: *const u32,
    /// ECEF positions, `nant * 3`.
    pub antenna_position: *const f64,
    pub chan_freq: *const f64,
    pub chan_width: *const f64,
    /// Casacore correlation codes, `ncorr`.
    pub corr_type: *const i32,
    /// Masked channel frequencies of every mask, concatenated.
    pub mask_freqs: *const f64,
    /// `nmasks + 1` offsets into `mask_freqs`.
    pub mask_offsets: *const usize,
    /// `nsteps * STEP_WIDTH` doubles, see `decode_steps`.
    pub steps: *const f64,
}

/// Caller-owned outputs; null skips that product.
#[repr(C)]
pub struct FlagOutputs {
    /// `nrow * nchan * ncorr`, the window flag broadcast over correlations.
    pub flags: *mut u8,
    /// Polarised-intensity window as interleaved complex64,
    /// `nbl * ntime * nchan * 2`, or null.
    pub intensity: *mut f32,
    /// Window flags after every step, `nsteps * nbl * ntime * nchan`, or null.
    pub stages: *mut u8,
}

unsafe fn slice<'a, T>(ptr: *const T, len: usize) -> Option<&'a [T]> {
    if ptr.is_null() {
        None
    } else {
        // SAFETY: the caller guarantees `len` live, aligned elements.
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

unsafe fn slice_mut<'a, T>(ptr: *mut T, len: usize) -> Option<&'a mut [T]> {
    if ptr.is_null() {
        None
    } else {
        // SAFETY: the caller guarantees `len` live, aligned, unaliased elements.
        Some(unsafe { std::slice::from_raw_parts_mut(ptr, len) })
    }
}

/// Decode the flat step table. Codes: 0 `flag_nans_zeros`;
/// 1 `apply_static_mask` [or, uv_low, uv_high]; 2 `sum_threshold`
/// [outlier_nsigma, n_time, 8 time windows, n_freq, 8 freq windows,
/// background_reject, background_iterations, spike_width_time,
/// spike_width_freq, time_extend, freq_extend, freq_chunks, average_freq,
/// flag_all_time_frac, flag_all_freq_frac, rho, num_major_iterations];
/// 3 `uvcontsub_flagger` [major_cycles, or_original_from_cycle,
/// taylor_degrees, sigma]; 4 `flag_autos`; 5 `combine_with_input_flags`;
/// 6 `unflag`.
pub fn decode_steps(table: &[f64]) -> Option<Vec<Step>> {
    let mut steps = Vec::new();
    for row in table.chunks_exact(STEP_WIDTH) {
        let step = match row[0] as i64 {
            0 => Step::FlagNansZeros,
            1 => Step::StaticMask {
                or: row[1] != 0.0,
                uv_low: row[2],
                uv_high: row[3],
            },
            2 => {
                let n_time = row[2] as usize;
                let n_freq = row[11] as usize;
                if n_time > 8 || n_freq > 8 {
                    return None;
                }
                Step::SumThreshold(SumThresholdParams {
                    outlier_nsigma: row[1],
                    windows_time: row[3..3 + n_time].iter().map(|&w| w as i64).collect(),
                    windows_freq: row[12..12 + n_freq].iter().map(|&w| w as i64).collect(),
                    background_reject: row[20],
                    background_iterations: row[21] as i64,
                    spike_width_time: row[22],
                    spike_width_freq: row[23],
                    time_extend: row[24] as usize,
                    freq_extend: row[25] as usize,
                    freq_chunks: row[26] as usize,
                    average_freq: row[27] as usize,
                    flag_all_time_frac: row[28],
                    flag_all_freq_frac: row[29],
                    rho: row[30],
                    num_major_iterations: row[31] as usize,
                })
            }
            3 => Step::UvContSub {
                major_cycles: row[1] as usize,
                or_original_from_cycle: row[2] as usize,
                taylor_degrees: row[3] as usize,
                sigma: row[4],
            },
            4 => Step::FlagAutos,
            5 => Step::CombineWithInputFlags,
            6 => Step::Unflag,
            _ => return None,
        };
        steps.push(step);
    }
    Some(steps)
}

/// Run Tricolour's `polarisation` flagging strategy on rows: polarised
/// intensity per visibility, input flags ORed over correlations, windows
/// packed by baseline and time, the strategy steps, and the window flag
/// written to every correlation of each row.
///
/// # Safety
/// Every non-null pointer must reference live, aligned, nonoverlapping
/// buffers of the lengths documented on `FlagInputs` and `FlagOutputs`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_flag_rows(
    inputs: *const FlagInputs,
    outputs: *mut FlagOutputs,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        let cells = i.nrow.saturating_mul(i.nchan).saturating_mul(i.ncorr);
        let plane = i.ntime.saturating_mul(i.nchan);
        let window_len = i.nbl.saturating_mul(plane);
        // SAFETY: lengths follow the documented contract.
        let (
            Some(data),
            Some(flags),
            Some(baseline_index),
            Some(time_index),
            Some(baselines),
            Some(antenna_position),
            Some(chan_freq),
            Some(chan_width),
            Some(corr_type),
            Some(mask_offsets),
            Some(steps),
            Some(out_flags),
        ) = (unsafe {
            (
                slice(i.data, 2 * cells),
                slice(i.flags, cells),
                slice(i.baseline_index, i.nrow),
                slice(i.time_index, i.nrow),
                slice(i.baselines, 2 * i.nbl),
                slice(i.antenna_position, 3 * i.nant),
                slice(i.chan_freq, i.nchan),
                slice(i.chan_width, i.nchan),
                slice(i.corr_type, i.ncorr),
                slice(i.mask_offsets, i.nmasks + 1),
                slice(i.steps, i.nsteps * STEP_WIDTH),
                slice_mut(o.flags, cells),
            )
        })
        else {
            return 1;
        };
        let total_mask = *mask_offsets.last().unwrap_or(&0);
        // SAFETY: as above.
        let mask_freqs = unsafe { slice(i.mask_freqs, total_mask) }.unwrap_or(&[]);
        if mask_offsets.windows(2).any(|w| w[0] > w[1]) || mask_freqs.len() < total_mask {
            return 1;
        }
        let masks: Vec<&[f64]> = (0..i.nmasks)
            .map(|m| &mask_freqs[mask_offsets[m]..mask_offsets[m + 1]])
            .collect();
        let Some(steps) = decode_steps(steps) else {
            return 1;
        };
        let pairs: Vec<(usize, usize)> = baselines
            .chunks_exact(2)
            .map(|b| (b[0] as usize, b[1] as usize))
            .collect();
        if pairs.iter().any(|&(a1, a2)| a1 >= i.nant || a2 >= i.nant)
            || baseline_index.iter().any(|&b| b as usize >= i.nbl)
            || time_index.iter().any(|&t| t as usize >= i.ntime)
        {
            return 1;
        }
        let stokes_pol = polarised_map(corr_type);
        if stokes_pol.is_empty() {
            return 1;
        }
        // Pack: defaults NaN and flagged, later rows overwrite earlier ones.
        let mut window = Window {
            nbl: i.nbl,
            ntime: i.ntime,
            nchan: i.nchan,
            re: vec![f32::NAN; window_len],
            im: vec![f32::NAN; window_len],
        };
        let mut input_flags = vec![true; window_len];
        let mut vis = vec![(0f32, 0f32); i.ncorr];
        for r in 0..i.nrow {
            let base = baseline_index[r] as usize * plane + time_index[r] as usize * i.nchan;
            for f in 0..i.nchan {
                let cell = (r * i.nchan + f) * i.ncorr;
                let mut any = false;
                for c in 0..i.ncorr {
                    vis[c] = (data[2 * (cell + c)], data[2 * (cell + c) + 1]);
                    any |= flags[cell + c] != 0;
                }
                window.re[base + f] = polarised_intensity(&vis, &stokes_pol);
                window.im[base + f] = 0.0;
                input_flags[base + f] = any;
            }
        }
        // SAFETY: as above.
        if let Some(out) = unsafe { slice_mut(o.intensity, 2 * window_len) } {
            for idx in 0..window_len {
                out[2 * idx] = window.re[idx];
                out[2 * idx + 1] = window.im[idx];
            }
        }
        // SAFETY: as above.
        let stages = unsafe { slice_mut(o.stages, i.nsteps * window_len) };
        let ctx = Context {
            baselines: &pairs,
            antenna_position,
            chan_freq,
            chan_width,
            masks: &masks,
        };
        let mut stage_sink = stages;
        let final_flags =
            sumthreshold::apply_strategies(&ctx, &window, &input_flags, &steps, |index, flags| {
                if let Some(stages) = stage_sink.as_deref_mut() {
                    for (dst, &src) in stages[index * window_len..(index + 1) * window_len]
                        .iter_mut()
                        .zip(flags)
                    {
                        *dst = src as u8;
                    }
                }
            });
        for r in 0..i.nrow {
            let base = baseline_index[r] as usize * plane + time_index[r] as usize * i.nchan;
            for f in 0..i.nchan {
                let value = final_flags[base + f] as u8;
                let cell = (r * i.nchan + f) * i.ncorr;
                out_flags[cell..cell + i.ncorr].fill(value);
            }
        }
        0
    });
    result.unwrap_or(2)
}
