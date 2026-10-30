//! C ABI for the WSClean weighting port (`weights.rs`), loaded through ctypes
//! by `rangtoy.core_weights`. Every pointer has an explicit length in the
//! structs, in the style of `ffi.rs`.

use crate::weights::{self, WeightClass, WeightGrid, WeightSettings};

/// Borrowed inputs for Stokes I formation: `ncell` cells of four
/// correlations (XX, XY, YX, YY).
#[repr(C)]
pub struct StokesIInputs {
    pub ncell: usize,
    /// `ncell * 4` interleaved complex floats.
    pub data: *const f32,
    /// `ncell * 4` floats.
    pub weights: *const f32,
    /// `ncell * 4` bytes, non-zero when flagged.
    pub flags: *const u8,
}

/// Caller-owned outputs: `ncell` interleaved complex floats and `ncell` weights.
#[repr(C)]
pub struct StokesIOutputs {
    pub vis: *mut f32,
    pub weight: *mut f32,
}

/// Borrowed inputs for one imaging-weight pass.
#[repr(C)]
pub struct ImagingWeightInputs {
    pub nrow: usize,
    pub nchan: usize,
    /// `nrow * 3` metres.
    pub uvw: *const f64,
    /// `nchan` wavelengths in metres.
    pub wavelength: *const f64,
    /// `nrow * nchan` Stokes I visibility weights (zero where flagged).
    pub weights: *const f32,
    /// `nrow` bytes, non-zero for rows WSClean selects.
    pub row_selected: *const u8,
    /// 0 natural, 1 uniform, 2 Briggs.
    pub class: u32,
    pub robust: f64,
    /// Padded image size.
    pub width: usize,
    pub height: usize,
    pub pixel_scale_x: f64,
    pub pixel_scale_y: f64,
    pub super_weight: f64,
    pub rank_filter_level: f64,
    pub rank_filter_size: usize,
}

/// Caller-owned outputs; null skips that product.
#[repr(C)]
pub struct ImagingWeightOutputs {
    /// `nrow * nchan` floats.
    pub weights: *mut f32,
    /// `grid_width * grid_height / 2` doubles (see
    /// `rang_core_weight_grid_shape`), or null.
    pub grid: *mut f64,
    /// Four doubles: visibility weight sum, total weight, max gridded weight,
    /// count; or null.
    pub sums: *mut f64,
}

unsafe fn slice<'a, T>(ptr: *const T, len: usize) -> Option<&'a [T]> {
    if ptr.is_null() {
        None
    } else {
        // SAFETY: the caller guarantees `len` live, aligned elements.
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

unsafe fn slice_mut<'a, T>(ptr: *mut T, len: usize) -> &'a mut [T] {
    if ptr.is_null() {
        &mut []
    } else {
        // SAFETY: the caller guarantees `len` live, aligned, unaliased elements.
        unsafe { std::slice::from_raw_parts_mut(ptr, len) }
    }
}

/// The weight grid shape after the super weight. Returns 0 on success, 1 on
/// invalid arguments, 2 on a panic.
///
/// # Safety
/// `shape` must reference two writable usize values.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_weight_grid_shape(
    width: usize,
    height: usize,
    super_weight: f64,
    shape: *mut usize,
) -> i32 {
    if shape.is_null() || super_weight.partial_cmp(&0.0) != Some(std::cmp::Ordering::Greater) {
        return 1;
    }
    std::panic::catch_unwind(|| {
        let (w, h) = WeightGrid::shape(width, height, super_weight);
        // SAFETY: the caller passes two writable values.
        let out = unsafe { slice_mut(shape, 2) };
        out[0] = w;
        out[1] = h;
        0
    })
    .unwrap_or(2)
}

/// WSClean's padded image size for `-size trimmed` and `-padding padding`;
/// 0 on a panic (never a valid size).
#[unsafe(no_mangle)]
pub extern "C" fn rang_core_padded_size(trimmed: usize, padding: f64) -> usize {
    std::panic::catch_unwind(|| weights::padded_size(trimmed, padding)).unwrap_or(0)
}

/// Form Stokes I visibilities and weights. Returns 0 on success, 1 on invalid
/// arguments, 2 on a panic.
///
/// # Safety
/// Every pointer must reference live, aligned, nonoverlapping buffers of the
/// lengths documented on the structs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_stokes_i(
    inputs: *const StokesIInputs,
    outputs: *mut StokesIOutputs,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        if o.vis.is_null() || o.weight.is_null() {
            return 1;
        }
        // SAFETY: lengths follow the documented contract.
        unsafe {
            let (Some(data), Some(weights), Some(flags)) = (
                slice(i.data, 8 * i.ncell),
                slice(i.weights, 4 * i.ncell),
                slice(i.flags, 4 * i.ncell),
            ) else {
                return 1;
            };
            let Ok((vis, weight)) = weights::stokes_i_from_linear(data, weights, flags, i.ncell)
            else {
                return 1;
            };
            slice_mut(o.vis, 2 * i.ncell).copy_from_slice(&vis);
            slice_mut(o.weight, i.ncell).copy_from_slice(&weight);
            0
        }
    });
    result.unwrap_or(2)
}

/// Compute WSClean imaging weights for every row and channel. Returns 0 on
/// success, 1 on invalid arguments, 2 on a panic.
///
/// # Safety
/// Every non-null pointer must reference live, aligned, nonoverlapping
/// buffers of the lengths documented on the structs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_imaging_weights(
    inputs: *const ImagingWeightInputs,
    outputs: *mut ImagingWeightOutputs,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        if o.weights.is_null() {
            return 1;
        }
        let class = match i.class {
            0 => WeightClass::Natural,
            1 => WeightClass::Uniform,
            2 => WeightClass::Briggs(i.robust),
            _ => return 1,
        };
        let settings = WeightSettings {
            class,
            width: i.width,
            height: i.height,
            scale_x: i.pixel_scale_x,
            scale_y: i.pixel_scale_y,
            super_weight: i.super_weight,
            rank_filter_level: i.rank_filter_level,
            rank_filter_size: i.rank_filter_size,
        };
        // SAFETY: lengths follow the documented contract.
        unsafe {
            let (Some(uvw), Some(wavelength), Some(vis_weights), Some(selected_raw)) = (
                slice(i.uvw, 3 * i.nrow),
                slice(i.wavelength, i.nchan),
                slice(i.weights, i.nrow * i.nchan),
                slice(i.row_selected, i.nrow),
            ) else {
                return 1;
            };
            let selected: Vec<bool> = selected_raw.iter().map(|&x| x != 0).collect();
            let Ok((out, grid)) =
                weights::imaging_weights(&settings, uvw, wavelength, vis_weights, &selected)
            else {
                return 1;
            };
            slice_mut(o.weights, i.nrow * i.nchan).copy_from_slice(&out);
            if !o.grid.is_null() {
                slice_mut(o.grid, grid.cells().len()).copy_from_slice(grid.cells());
            }
            if !o.sums.is_null() {
                let Ok(sums) = weights::weight_sums(vis_weights, &out) else {
                    return 1;
                };
                let s = slice_mut(o.sums, 4);
                s[0] = sums.visibility_weight_sum;
                s[1] = sums.total_weight;
                s[2] = sums.max_gridded_weight;
                s[3] = sums.count as f64;
            }
            0
        }
    });
    result.unwrap_or(2)
}
