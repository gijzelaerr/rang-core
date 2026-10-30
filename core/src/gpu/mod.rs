//! The w-stacking gridder on the GPU through `wgpu` (big-plan task X2,
//! `research/x2-wgpu.md`), behind the cargo feature `gpu`.
//!
//! The host runs the CPU gridder's counters/placement pass and the counting
//! sort by w-layer (`grid::bucket`, the same code as the CPU path) and sorts
//! each layer's samples by cell. The GPU grids every layer by gathering
//! (`shader::GRID`, no atomics), transforms each grid with a mixed-radix
//! Stockham FFT (`fft.rs`, `shader::FFT`), projects it with the w-phasor
//! and adds it to the running sums in ascending layer order
//! (`shader::PROJECT`). The sums come back to the host, which applies
//! `1 / image_weight`, the kernel correction, the trim and the PSF
//! normalisation through the CPU code. Layers go in batches bounded by a
//! device-memory budget; batching does not change the arithmetic.
//!
//! Precision: `F64` needs `Features::SHADER_F64` (Vulkan on NVIDIA and AMD
//! here; not DX12 in wgpu 30, not Metal) and is the path validated against
//! the archived comparators. `F32` is an experimental, separately
//! toleranced path. Differences from the CPU arithmetic, by design: the
//! order of the additions into one grid cell, the FFT algorithm, the
//! `sin`/`cos` of the phasor (WGSL has no f64 trigonometry; a Cody-Waite
//! reduction and fdlibm's polynomials) and any fused multiply-adds the
//! driver's compiler forms.

mod context;
pub mod ffi;
mod fft;
mod invert;
mod shader;

pub use context::{ADAPTER_ENV, adapter_description};
pub use invert::{BATCH_ENV, MEMORY_ENV, Options, Timings, invert, invert_with};

#[cfg(test)]
mod tests;

/// Arithmetic of the GPU path.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Precision {
    F64,
    F32,
}

impl Precision {
    pub fn parse(name: &str) -> Result<Precision, String> {
        match name.trim().to_ascii_lowercase().as_str() {
            "f64" | "" => Ok(Precision::F64),
            "f32" => Ok(Precision::F32),
            other => Err(format!("unknown GPU precision {other:?} (f64 or f32)")),
        }
    }

    pub(crate) fn bytes(self) -> usize {
        match self {
            Precision::F64 => 8,
            Precision::F32 => 4,
        }
    }
}
