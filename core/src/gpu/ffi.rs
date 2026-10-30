//! Entry points of the GPU gridder for the extension and the C ABI, with the
//! same buffers as `ffi_grid::rang_core_grid_invert` plus the precision and
//! a timing array (`Timings::as_array`, `N_TIMINGS` doubles).

use super::{Precision, Timings};
use crate::ffi_grid::{GridInputs, GridOutputs, N_STATS};
use crate::grid::{Inputs, Settings};

pub const N_TIMINGS: usize = 14;

/// Invert on the GPU into the caller's buffers; `Err` carries the reason
/// (invalid arguments, no adapter, no f64 support, device errors).
///
/// # Safety
/// Every pointer of `inputs` and `outputs` must reference live, aligned,
/// nonoverlapping buffers of the lengths documented on `GridInputs` and
/// `GridOutputs`, and `timings` must hold `N_TIMINGS` writable doubles.
pub unsafe fn grid_invert(
    inputs: &GridInputs,
    outputs: &mut GridOutputs,
    precision: Precision,
    timings: *mut f64,
) -> Result<(), String> {
    let i = inputs;
    let o = outputs;
    if i.uvw.is_null()
        || i.frequencies.is_null()
        || i.data.is_null()
        || i.weights.is_null()
        || i.imaging_weights.is_null()
        || o.dirty.is_null()
        || o.psf.is_null()
        || o.stats.is_null()
        || timings.is_null()
    {
        return Err("null buffer".into());
    }
    let cells = i
        .nrow
        .checked_mul(i.nchan)
        .ok_or("row and channel counts overflow")?;
    // SAFETY: lengths follow the documented contract.
    let (uvw, frequencies, data, weights, imaging_weights) = unsafe {
        (
            std::slice::from_raw_parts(i.uvw, i.nrow * 3),
            std::slice::from_raw_parts(i.frequencies, i.nchan),
            std::slice::from_raw_parts(i.data, cells * 2),
            std::slice::from_raw_parts(i.weights, cells),
            std::slice::from_raw_parts(i.imaging_weights, cells),
        )
    };
    let settings = Settings {
        width: i.width,
        height: i.height,
        pixel_size_x: i.pixel_size_x,
        pixel_size_y: i.pixel_size_y,
        kernel_size: i.kernel_size,
        oversampling: i.oversampling,
        n_w_layers: i.n_w_layers,
        padding: i.padding,
    };
    let grid_inputs = Inputs {
        uvw,
        frequencies,
        data,
        weights,
        imaging_weights,
    };
    let (products, t) = super::invert(&settings, &grid_inputs, precision)?;
    let pixels = i.width * i.height;
    // SAFETY: caller-owned output buffers of the documented sizes.
    let (dirty, psf, stats, times) = unsafe {
        (
            std::slice::from_raw_parts_mut(o.dirty, pixels),
            std::slice::from_raw_parts_mut(o.psf, pixels),
            std::slice::from_raw_parts_mut(o.stats, N_STATS),
            std::slice::from_raw_parts_mut(timings, N_TIMINGS),
        )
    };
    dirty.copy_from_slice(&products.dirty);
    psf.copy_from_slice(&products.psf);
    let s = products.stats;
    stats.copy_from_slice(&[
        s.image_weight,
        s.gridded_count as f64,
        s.visibility_weight_sum,
        s.max_gridded_weight,
        s.min_w,
        s.max_w,
        s.psf_normalization,
        i.n_w_layers as f64,
    ]);
    times.copy_from_slice(&Timings::as_array(&t));
    Ok(())
}

/// C ABI of `grid_invert`: `precision` 0 is f64, 1 is f32. Returns 0 on
/// success, 1 on invalid arguments, 2 on a panic, 3 when the GPU path fails
/// (no adapter, no f64 support, a device error).
///
/// # Safety
/// As `grid_invert`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_grid_invert_gpu(
    inputs: *const GridInputs,
    outputs: *mut GridOutputs,
    precision: i32,
    timings: *mut f64,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        let precision = match precision {
            0 => Precision::F64,
            1 => Precision::F32,
            _ => return 1,
        };
        // SAFETY: forwarded contract.
        match unsafe { grid_invert(i, o, precision, timings) } {
            Ok(()) => 0,
            Err(_) => 3,
        }
    })
    .unwrap_or(2)
}
