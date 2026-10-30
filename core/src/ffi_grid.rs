//! C ABI for the w-stacking gridder (`grid.rs`), loaded through ctypes by
//! `python/rang/core_grid.py`, in the style of `ffi.rs`.

use crate::grid::{self, Inputs, Settings};

/// Borrowed input buffers; lengths are explicit.
#[repr(C)]
pub struct GridInputs {
    pub nrow: usize,
    pub nchan: usize,
    pub width: usize,
    pub height: usize,
    pub kernel_size: usize,
    pub oversampling: usize,
    pub n_w_layers: usize,
    /// Pixel sizes in radians.
    pub pixel_size_x: f64,
    pub pixel_size_y: f64,
    /// Image padding factor (1.2 as WSClean's default).
    pub padding: f64,
    /// `nrow * 3` metres.
    pub uvw: *const f64,
    /// `nchan` Hz.
    pub frequencies: *const f64,
    /// `nrow * nchan * 2` interleaved complex singles.
    pub data: *const f32,
    /// `nrow * nchan` visibility weights.
    pub weights: *const f32,
    /// `nrow * nchan` imaging weights.
    pub imaging_weights: *const f32,
}

/// Caller-owned output buffers.
#[repr(C)]
pub struct GridOutputs {
    /// `width * height` doubles each, `[x + y * width]` order.
    pub dirty: *mut f64,
    pub psf: *mut f64,
    /// Eight doubles: image weight, gridded count, visibility weight sum,
    /// maximum gridded weight, min w, max w, PSF normalisation factor, and
    /// the number of w-layers used.
    pub stats: *mut f64,
}

pub const N_STATS: usize = 8;

/// Invert visibilities to a dirty image and PSF. Returns 0 on success, 1 on
/// invalid arguments, 2 on a panic.
///
/// # Safety
/// Every pointer must reference live, aligned, nonoverlapping buffers of the
/// lengths documented on `GridInputs` and `GridOutputs`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_grid_invert(
    inputs: *const GridInputs,
    outputs: *mut GridOutputs,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        if i.uvw.is_null()
            || i.frequencies.is_null()
            || i.data.is_null()
            || i.weights.is_null()
            || i.imaging_weights.is_null()
            || o.dirty.is_null()
            || o.psf.is_null()
            || o.stats.is_null()
        {
            return 1;
        }
        let cells = i.nrow * i.nchan;
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
        let inputs = Inputs {
            uvw,
            frequencies,
            data,
            weights,
            imaging_weights,
        };
        let products = match grid::invert(&settings, &inputs) {
            Ok(products) => products,
            Err(_) => return 1,
        };
        let pixels = i.width * i.height;
        // SAFETY: caller-owned output buffers of the documented sizes.
        let (dirty, psf, stats) = unsafe {
            (
                std::slice::from_raw_parts_mut(o.dirty, pixels),
                std::slice::from_raw_parts_mut(o.psf, pixels),
                std::slice::from_raw_parts_mut(o.stats, N_STATS),
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
        0
    });
    result.unwrap_or(2)
}

/// Fill `kernel` (`kernel_size * oversampling` doubles) with the oversampled
/// Kaiser–Bessel kernel. Returns 0 on success, 1 on invalid arguments, 2 on
/// a panic (for example `(7, 2)`, which aborted the process before task P7).
///
/// # Safety
/// `kernel` must hold `kernel_size * oversampling` writable doubles.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_grid_kernel(
    kernel_size: usize,
    oversampling: usize,
    kernel: *mut f64,
) -> i32 {
    let Some(len) = kernel_size.checked_mul(oversampling) else {
        return 1;
    };
    if kernel.is_null() || len == 0 {
        return 1;
    }
    std::panic::catch_unwind(|| {
        let values = grid::kaiser_bessel_kernel(kernel_size, oversampling);
        // SAFETY: the caller provides the documented length.
        let out = unsafe { std::slice::from_raw_parts_mut(kernel, len) };
        out.copy_from_slice(&values);
        0
    })
    .unwrap_or(2)
}
