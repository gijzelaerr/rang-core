//! C ABI for the exact gridder (`wgridder.rs`), loaded through ctypes by
//! `python/rangtoy/core_wgridder.py`, in the style of `ffi_grid.rs`.
//! Status: 0 on success, 1 on invalid arguments (the message is kept for
//! `rang_core_wgridder_last_error`), 2 on a panic. DF2a added the `_ex`
//! entry points (borrowed inputs of either precision, the PSF in the same
//! pass); the DF1 entry points are unchanged.

use crate::wgridder::{self, KernelChoice, N_INFO, Options, Real, VisData, Weights};
use rustfft::num_complex::Complex;
use std::cell::RefCell;
use std::ffi::c_void;

thread_local! {
    static LAST_ERROR: RefCell<String> = const { RefCell::new(String::new()) };
}

fn set_error(message: &str) {
    LAST_ERROR.with(|e| *e.borrow_mut() = message.to_string());
}

/// Gridder options; `kernel_index < 0` lets the cost model choose.
#[repr(C)]
pub struct WgridderOptions {
    pub nx: usize,
    pub ny: usize,
    pub pixsize_x: f64,
    pub pixsize_y: f64,
    pub epsilon: f64,
    pub center_x: f64,
    pub center_y: f64,
    pub sigma_min: f64,
    pub sigma_max: f64,
    pub do_wgridding: i32,
    pub divide_by_n: i32,
    pub flip_u: i32,
    pub flip_v: i32,
    pub flip_w: i32,
    pub allow_nshift: i32,
    pub kernel_index: i64,
    pub nu: usize,
    pub nv: usize,
}

fn options(o: &WgridderOptions) -> Options {
    Options {
        nx: o.nx,
        ny: o.ny,
        pixsize_x: o.pixsize_x,
        pixsize_y: o.pixsize_y,
        epsilon: o.epsilon,
        do_wgridding: o.do_wgridding != 0,
        divide_by_n: o.divide_by_n != 0,
        flip_u: o.flip_u != 0,
        flip_v: o.flip_v != 0,
        flip_w: o.flip_w != 0,
        center_x: o.center_x,
        center_y: o.center_y,
        allow_nshift: o.allow_nshift != 0,
        sigma_min: o.sigma_min,
        sigma_max: o.sigma_max,
        kernel: (o.kernel_index >= 0).then_some(KernelChoice {
            index: o.kernel_index as usize,
            nu: o.nu,
            nv: o.nv,
        }),
    }
}

/// Shared body of the four entry points.
///
/// # Safety
/// As the entry points.
#[allow(clippy::too_many_arguments)]
unsafe fn run<T: Real>(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    vis: *mut T,
    wgt: *const T,
    mask: *const u8,
    dirty: *mut T,
    info: *mut f64,
    gridding: bool,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes a valid options pointer.
        let Some(o) = (unsafe { opts.as_ref() }) else {
            set_error("null options");
            return 1;
        };
        if uvw.is_null() || freq.is_null() || vis.is_null() || dirty.is_null() || info.is_null() {
            set_error("null array");
            return 1;
        }
        let opts = options(o);
        let n = nrow * nchan;
        // SAFETY: lengths follow the documented contract.
        let (uvw, freq, wgt, mask) = unsafe {
            (
                std::slice::from_raw_parts(uvw, nrow * 3),
                std::slice::from_raw_parts(freq, nchan),
                (!wgt.is_null()).then(|| std::slice::from_raw_parts(wgt, n)),
                (!mask.is_null()).then(|| std::slice::from_raw_parts(mask, n)),
            )
        };
        let result = if gridding {
            // SAFETY: as above; `vis` holds `2 n` values, `dirty` `nx ny`.
            let (vis, dirty) = unsafe {
                (
                    std::slice::from_raw_parts(vis as *const Complex<T>, n),
                    std::slice::from_raw_parts_mut(dirty, o.nx * o.ny),
                )
            };
            wgridder::vis2dirty(&opts, uvw, freq, vis, wgt, mask, dirty)
        } else {
            // SAFETY: as above.
            let (vis, dirty) = unsafe {
                (
                    std::slice::from_raw_parts_mut(vis as *mut Complex<T>, n),
                    std::slice::from_raw_parts(dirty as *const T, o.nx * o.ny),
                )
            };
            wgridder::dirty2vis(&opts, uvw, freq, dirty, wgt, mask, vis)
        };
        match result {
            Ok(plan) => {
                // SAFETY: `info` holds N_INFO doubles.
                let out = unsafe { std::slice::from_raw_parts_mut(info, N_INFO) };
                out.copy_from_slice(&plan.to_array());
                0
            }
            Err(message) => {
                set_error(&message);
                1
            }
        }
    });
    result.unwrap_or_else(|_| {
        set_error("panic in the gridder");
        2
    })
}

/// Visibilities (`nrow * nchan` interleaved complex doubles) to the dirty
/// image (`nx * ny` doubles, first axis l); `wgt` and `mask` may be null;
/// `info` receives `N_INFO` doubles (`Plan::to_array`).
///
/// # Safety
/// Every pointer must reference live, aligned buffers of those lengths.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_f64(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    vis: *const f64,
    wgt: *const f64,
    mask: *const u8,
    dirty: *mut f64,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract; `vis` is only read when gridding.
    unsafe {
        run::<f64>(
            opts,
            nrow,
            nchan,
            uvw,
            freq,
            vis as *mut f64,
            wgt,
            mask,
            dirty,
            info,
            true,
        )
    }
}

/// As `rang_core_wgridder_vis2dirty_f64` in single precision.
///
/// # Safety
/// As `rang_core_wgridder_vis2dirty_f64`.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_f32(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    vis: *const f32,
    wgt: *const f32,
    mask: *const u8,
    dirty: *mut f32,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract.
    unsafe {
        run::<f32>(
            opts,
            nrow,
            nchan,
            uvw,
            freq,
            vis as *mut f32,
            wgt,
            mask,
            dirty,
            info,
            true,
        )
    }
}

/// The image (`nx * ny` doubles) to visibilities (`nrow * nchan`
/// interleaved complex doubles, written).
///
/// # Safety
/// As `rang_core_wgridder_vis2dirty_f64`.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_dirty2vis_f64(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    dirty: *const f64,
    wgt: *const f64,
    mask: *const u8,
    vis: *mut f64,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract; `dirty` is only read when degridding.
    unsafe {
        run::<f64>(
            opts,
            nrow,
            nchan,
            uvw,
            freq,
            vis,
            wgt,
            mask,
            dirty as *mut f64,
            info,
            false,
        )
    }
}

/// As `rang_core_wgridder_dirty2vis_f64` in single precision.
///
/// # Safety
/// As `rang_core_wgridder_vis2dirty_f64`.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_dirty2vis_f32(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    dirty: *const f32,
    wgt: *const f32,
    mask: *const u8,
    vis: *mut f32,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract.
    unsafe {
        run::<f32>(
            opts,
            nrow,
            nchan,
            uvw,
            freq,
            vis,
            wgt,
            mask,
            dirty as *mut f32,
            info,
            false,
        )
    }
}

// ------------------------------------------- borrowed inputs and PSF (DF2a)

/// `vis_kind` of the `_ex` entry points: no data (unit visibilities).
pub const WGRIDDER_VIS_UNIT: i32 = 0;
/// `vis_kind`: interleaved complex floats.
pub const WGRIDDER_VIS_C64: i32 = 1;
/// `vis_kind`: interleaved complex doubles.
pub const WGRIDDER_VIS_C128: i32 = 2;
/// `wgt_kind` of the `_ex` entry points: no weights.
pub const WGRIDDER_WGT_NONE: i32 = 0;
/// `wgt_kind`: floats.
pub const WGRIDDER_WGT_F32: i32 = 1;
/// `wgt_kind`: doubles.
pub const WGRIDDER_WGT_F64: i32 = 2;

/// Borrow `n` visibilities of kind `kind` at `ptr`.
///
/// # Safety
/// `ptr` must hold `n` values of that kind (or be ignored for unit data).
unsafe fn vis_data<'a>(ptr: *const c_void, kind: i32, n: usize) -> Result<VisData<'a>, String> {
    // SAFETY: forwarded contract.
    unsafe {
        match kind {
            WGRIDDER_VIS_UNIT => Ok(VisData::Unit),
            WGRIDDER_VIS_C64 if !ptr.is_null() => Ok(VisData::C64(std::slice::from_raw_parts(
                ptr as *const Complex<f32>,
                n,
            ))),
            WGRIDDER_VIS_C128 if !ptr.is_null() => Ok(VisData::C128(std::slice::from_raw_parts(
                ptr as *const Complex<f64>,
                n,
            ))),
            _ => Err("invalid visibility array or kind".into()),
        }
    }
}

/// Borrow `n` weights of kind `kind` at `ptr`.
///
/// # Safety
/// `ptr` must hold `n` values of that kind (or be ignored without weights).
unsafe fn weights<'a>(ptr: *const c_void, kind: i32, n: usize) -> Result<Weights<'a>, String> {
    // SAFETY: forwarded contract.
    unsafe {
        match kind {
            WGRIDDER_WGT_NONE => Ok(Weights::None),
            WGRIDDER_WGT_F32 if !ptr.is_null() => Ok(Weights::F32(std::slice::from_raw_parts(
                ptr as *const f32,
                n,
            ))),
            WGRIDDER_WGT_F64 if !ptr.is_null() => Ok(Weights::F64(std::slice::from_raw_parts(
                ptr as *const f64,
                n,
            ))),
            _ => Err("invalid weight array or kind".into()),
        }
    }
}

/// Shared body of the `vis2dirty_ex` entry points.
///
/// # Safety
/// As the entry points.
#[allow(clippy::too_many_arguments)]
unsafe fn run_ex<T: Real>(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    vis: *const c_void,
    vis_kind: i32,
    wgt: *const c_void,
    wgt_kind: i32,
    mask: *const u8,
    dirty: *mut T,
    psf: *mut T,
    info: *mut f64,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes a valid options pointer.
        let Some(o) = (unsafe { opts.as_ref() }) else {
            set_error("null options");
            return 1;
        };
        if uvw.is_null() || freq.is_null() || info.is_null() || (dirty.is_null() && psf.is_null()) {
            set_error("null array");
            return 1;
        }
        let opts = options(o);
        let n = nrow * nchan;
        let npix = o.nx * o.ny;
        // SAFETY: lengths follow the documented contract.
        let inputs = unsafe {
            (
                std::slice::from_raw_parts(uvw, nrow * 3),
                std::slice::from_raw_parts(freq, nchan),
                vis_data(vis, vis_kind, n),
                weights(wgt, wgt_kind, n),
                (!mask.is_null()).then(|| std::slice::from_raw_parts(mask, n)),
                (!dirty.is_null()).then(|| std::slice::from_raw_parts_mut(dirty, npix)),
                (!psf.is_null()).then(|| std::slice::from_raw_parts_mut(psf, npix)),
            )
        };
        let (uvw, freq, data, wgt, mask, dirty, psf) = inputs;
        let result = match (data, wgt) {
            (Ok(data), Ok(wgt)) => {
                wgridder::vis2dirty_multi(&opts, uvw, freq, data, wgt, mask, dirty, psf)
            }
            (Err(e), _) | (_, Err(e)) => Err(e),
        };
        match result {
            Ok(plan) => {
                // SAFETY: `info` holds N_INFO doubles.
                let out = unsafe { std::slice::from_raw_parts_mut(info, N_INFO) };
                out.copy_from_slice(&plan.to_array());
                0
            }
            Err(message) => {
                set_error(&message);
                1
            }
        }
    });
    result.unwrap_or_else(|_| {
        set_error("panic in the gridder");
        2
    })
}

/// Visibilities to a dirty image and/or a PSF in one pass, working in
/// double precision, reading the data and weights in the caller's
/// precision without copies. `vis` holds `nrow * nchan` values of kind
/// `vis_kind` (`WGRIDDER_VIS_*`; ignored for unit data); `wgt` likewise
/// with `wgt_kind` (`WGRIDDER_WGT_*`); `mask` may be null; `dirty` and
/// `psf` (`nx * ny` doubles each) may each be null but not both. With a
/// PSF both images use the plan of `wgt * mask != 0`; `info` receives
/// `N_INFO` doubles.
///
/// # Safety
/// Every pointer must reference live, aligned buffers of those lengths.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_ex_f64(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    vis: *const c_void,
    vis_kind: i32,
    wgt: *const c_void,
    wgt_kind: i32,
    mask: *const u8,
    dirty: *mut f64,
    psf: *mut f64,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract.
    unsafe {
        run_ex::<f64>(
            opts, nrow, nchan, uvw, freq, vis, vis_kind, wgt, wgt_kind, mask, dirty, psf, info,
        )
    }
}

/// As `rang_core_wgridder_vis2dirty_ex_f64`, working in single precision.
///
/// # Safety
/// As `rang_core_wgridder_vis2dirty_ex_f64`.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_vis2dirty_ex_f32(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    vis: *const c_void,
    vis_kind: i32,
    wgt: *const c_void,
    wgt_kind: i32,
    mask: *const u8,
    dirty: *mut f32,
    psf: *mut f32,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract.
    unsafe {
        run_ex::<f32>(
            opts, nrow, nchan, uvw, freq, vis, vis_kind, wgt, wgt_kind, mask, dirty, psf, info,
        )
    }
}

/// Shared body of the `dirty2vis_ex` entry points.
///
/// # Safety
/// As the entry points.
#[allow(clippy::too_many_arguments)]
unsafe fn run_d2v_ex<T: Real>(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    dirty: *const T,
    wgt: *const c_void,
    wgt_kind: i32,
    mask: *const u8,
    vis: *mut T,
    info: *mut f64,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes a valid options pointer.
        let Some(o) = (unsafe { opts.as_ref() }) else {
            set_error("null options");
            return 1;
        };
        if uvw.is_null() || freq.is_null() || vis.is_null() || dirty.is_null() || info.is_null() {
            set_error("null array");
            return 1;
        }
        let opts = options(o);
        let n = nrow * nchan;
        // SAFETY: lengths follow the documented contract.
        let (uvw, freq, dirty, wgt, mask, vis) = unsafe {
            (
                std::slice::from_raw_parts(uvw, nrow * 3),
                std::slice::from_raw_parts(freq, nchan),
                std::slice::from_raw_parts(dirty, o.nx * o.ny),
                weights(wgt, wgt_kind, n),
                (!mask.is_null()).then(|| std::slice::from_raw_parts(mask, n)),
                std::slice::from_raw_parts_mut(vis as *mut Complex<T>, n),
            )
        };
        let result =
            wgt.and_then(|wgt| wgridder::dirty2vis_multi(&opts, uvw, freq, dirty, wgt, mask, vis));
        match result {
            Ok(plan) => {
                // SAFETY: `info` holds N_INFO doubles.
                let out = unsafe { std::slice::from_raw_parts_mut(info, N_INFO) };
                out.copy_from_slice(&plan.to_array());
                0
            }
            Err(message) => {
                set_error(&message);
                1
            }
        }
    });
    result.unwrap_or_else(|_| {
        set_error("panic in the gridder");
        2
    })
}

/// The image (`nx * ny` doubles) to visibilities (`nrow * nchan`
/// interleaved complex doubles, written), with weights of kind `wgt_kind`
/// read without copies.
///
/// # Safety
/// As `rang_core_wgridder_vis2dirty_ex_f64`.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_dirty2vis_ex_f64(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    dirty: *const f64,
    wgt: *const c_void,
    wgt_kind: i32,
    mask: *const u8,
    vis: *mut f64,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract.
    unsafe {
        run_d2v_ex::<f64>(
            opts, nrow, nchan, uvw, freq, dirty, wgt, wgt_kind, mask, vis, info,
        )
    }
}

/// As `rang_core_wgridder_dirty2vis_ex_f64` in single precision.
///
/// # Safety
/// As `rang_core_wgridder_vis2dirty_ex_f64`.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_wgridder_dirty2vis_ex_f32(
    opts: *const WgridderOptions,
    nrow: usize,
    nchan: usize,
    uvw: *const f64,
    freq: *const f64,
    dirty: *const f32,
    wgt: *const c_void,
    wgt_kind: i32,
    mask: *const u8,
    vis: *mut f32,
    info: *mut f64,
) -> i32 {
    // SAFETY: forwarded contract.
    unsafe {
        run_d2v_ex::<f32>(
            opts, nrow, nchan, uvw, freq, dirty, wgt, wgt_kind, mask, vis, info,
        )
    }
}

/// Row `index` of the kernel table into `out` (seven doubles: W, ofactor,
/// epsilon, beta, e0, ndim, singleprec); 1 past the end.
///
/// # Safety
/// `out` must hold seven doubles.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_wgridder_kernel_row(index: usize, out: *mut f64) -> i32 {
    let Some(row) = wgridder::kernel_row(index) else {
        return 1;
    };
    if out.is_null() {
        return 1;
    }
    // SAFETY: the caller passes seven doubles.
    let out = unsafe { std::slice::from_raw_parts_mut(out, 7) };
    out.copy_from_slice(&[
        row.w as f64,
        row.ofactor,
        row.epsilon,
        row.beta,
        row.e0,
        row.ndim as f64,
        f64::from(u8::from(row.singleprec)),
    ]);
    0
}

/// The message of this thread's last status-1 failure into `buf` (at most
/// `len` bytes, not terminated); returns its full length.
///
/// # Safety
/// `buf` must hold `len` bytes or be null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_wgridder_last_error(buf: *mut u8, len: usize) -> usize {
    LAST_ERROR.with(|e| {
        let e = e.borrow();
        if !buf.is_null() {
            let n = e.len().min(len);
            // SAFETY: `buf` holds `len` bytes.
            unsafe { std::ptr::copy_nonoverlapping(e.as_ptr(), buf, n) };
        }
        e.len()
    })
}
