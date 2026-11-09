//! gemclean: a reference CLEAN whose every minor step is a certified descent
//! step on the image-domain Gram model, with lazy exact corrections.
//! Research note: `research/gemclean.md`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The certified driver of [`crate::clean_certified`] bounds the error of a
//! truncated minor-cycle beam by the worst case `f Σ|c_j|` (Theorem 6 of
//! `research/clean-theory.md`) and therefore hands back to the major cycle
//! after one to four components. gemclean computes the error exactly at the
//! one pixel it is about to clean instead:
//!
//! 1. **Exact beam.** The PSF on the `2n × 2n` grid holds `b(Δ)` for every
//!    offset two image pixels can have, so subtracting it is the exact Gram
//!    matrix `B` of the gridded measurement without the w-term (the beam is
//!    the one at the phase centre). Its FFT is cached in a [`Convolver`].
//! 2. **Lazy exact Högbom minor cycle.** A working map `r̃` is updated with
//!    the beam within `±P` pixels only. The candidate is `p = argmax |r̃|`;
//!    its exact value is
//!    `r_p = r̃_p − Σ_{j: ‖x_p − x_j‖_∞ > P} c_j b(x_p − x_j)`
//!    over the components since the working map was last exact (one beam
//!    lookup per component, a gather). The component is `c = γ r_p / b(0)`,
//!    so the misfit falls by exactly `γ(2−γ)/2 · r_p² / b(0)` (Theorem 1,
//!    `Clean.misfit_step`). With `e = f b(0) Σ|c_j|` bounding the stale error
//!    anywhere in the map, the pick is `τ_k`-weak greedy with
//!    `τ_k = |r_p| / (max|r̃| + e)`. When the drift `|r_p − r̃_p|` exceeds a
//!    fraction of `|r̃_p|`, when `τ_k < τ_min`, or every `K` components, the
//!    working map is made exact again by one FFT pair on the `2n` grid,
//!    `r̃ = r_major − B (m − m_major)` (a *resync*; no visibilities are
//!    touched). The minor cycle ends on exact values only: when the exact
//!    `|r_p|` is below the threshold, it resyncs and goes on if a peak above
//!    the threshold reappears.
//! 3. **Major cycles** run the model through the measurement (degrid and
//!    grid) when the minor cycle has removed a fraction `φ` of the misfit, or
//!    at the end, and record the realised Gram gap (exact `ΔQ` minus the
//!    image-domain prediction): what the image-domain model cannot know, the
//!    w-term and the gridder's accuracy. [`CycleStop`] chooses when a minor
//!    cycle hands back; a long cycle against the phase-centre beam fits the
//!    beam's error at the source positions as false components (§5 of the
//!    note), so the default stops on the exact peak when it reaches the
//!    pointwise error the previous major cycle measured.
//!
//! "Exact" therefore means exact for the image-domain beam at the phase
//! centre; the per-step certificate is not a statement about the
//! visibility-space misfit, whose departure the major cycle measures.

pub mod fits;
pub mod host;
pub mod input;
pub mod joined;
pub mod kernels;
pub mod mask;
pub mod measure;
pub mod memory;
pub mod multiscale;
pub mod predict;
pub mod sim;
pub mod spectral;
pub mod stale_bound;
pub mod stokes;

use crate::clean::{CleanStep, argmax_abs};
use crate::clean_certified::Measurement;
use crate::wgridder::{Lease, Pool, SyncPtr};
use kernels::Level;
use rayon::prelude::*;
use rustfft::num_complex::Complex;
use rustfft::{Fft, FftPlanner};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

type C64 = Complex<f64>;

const ZERO: C64 = Complex { re: 0.0, im: 0.0 };

// ---------------------------------------------------------------------------
// The 2n FFT convolver.

/// `dst[c * dst_stride + r] = src[r * src_stride + c]` for `r < rows`,
/// `c < cols`; the rest of each `dst` row (`dst_stride > rows`) becomes zero.
/// Blocked over destination rows, so the source is read along its rows.
fn transpose_into(
    src: &[C64],
    src_stride: usize,
    rows: usize,
    cols: usize,
    dst: &mut [C64],
    dst_stride: usize,
) {
    const BLOCK: usize = 16;
    dst[..cols * dst_stride]
        .par_chunks_mut(BLOCK * dst_stride)
        .enumerate()
        .for_each(|(block, chunk)| {
            let c0 = block * BLOCK;
            let h = chunk.len() / dst_stride;
            for r in 0..rows {
                let s = &src[r * src_stride + c0..r * src_stride + c0 + h];
                for (dc, v) in s.iter().enumerate() {
                    chunk[dc * dst_stride + r] = *v;
                }
            }
            if dst_stride > rows {
                for row in chunk.chunks_exact_mut(dst_stride) {
                    row[rows..].fill(ZERO);
                }
            }
        });
}

/// The reusable work space of a [`Convolver`].
#[derive(Default)]
struct ConvolverBuffers {
    /// `rows × keep`: half spectra of the rows, as far as the kernel reaches.
    rows: Vec<C64>,
    /// Per row of the input: not all zero. A zero row's spectrum is not stored.
    nonzero: Vec<bool>,
}

/// Columns of the half spectrum transformed together: a task's work space then
/// stays in the second-level cache, and its rows are read and written whole.
const COLUMN_BLOCK: usize = 8;

/// Stride of a column in the work space: `m + COLUMN_PAD`, so that with `m` a
/// power of two the columns do not all fall in the same cache sets.
const COLUMN_PAD: usize = 16;

type ConvolverWork = (Vec<C64>, Vec<C64>);

/// Linear convolution of an `n × n` image with a kernel given on the
/// `2n × 2n` grid centred on pixel `(n, n)`, by one real FFT pair on the `2n`
/// grid: `out(y, x) = Σ in(y', x') k(y − y', x − x')` for every output pixel
/// of the `n × n` image (offsets up to `±(n − 1)` never wrap). Row-major,
/// rows are the slow index (`dy`).
///
/// Real input means half the spectrum: two real rows travel as one complex
/// row (`z = a + i b`) and only `m/2 + 1` columns are transformed. Input rows
/// `n..2n` are zero and output rows `n..2n` are dropped, and an all-zero pair
/// of rows skips its transform. Columns beyond the kernel's band need not be
/// transformed or stored: a PSF is band-limited by the longest baseline, so an
/// image with oversampled pixels can drop the outer columns
/// ([`Convolver::with_band`]). Work space is kept between calls.
pub struct Convolver {
    n: usize,
    /// The kernel's half spectrum, `[kx][ky]`, `keep × m`.
    spectrum: Vec<C64>,
    /// Half-spectrum columns kept, the lowest `kx`, at most `m/2 + 1`.
    keep: usize,
    /// The rms over the `2n` grid of the part of the kernel left out.
    dropped_rms: f64,
    forward: Arc<dyn Fft<f64>>,
    inverse: Arc<dyn Fft<f64>>,
    scratch: usize,
    buffers: std::sync::Mutex<ConvolverBuffers>,
    work: Pool<ConvolverWork>,
}

impl Convolver {
    /// `kernel` is `2n × 2n`, centred on `(n, n)`.
    pub fn new(n: usize, kernel: &[f64]) -> Result<Convolver, String> {
        Convolver::with_band(n, kernel, n + 1)
    }

    /// [`Convolver::new`] with only the lowest `columns` of the `n + 1` columns
    /// of the half spectrum. The result's error is the part of the kernel left
    /// out, whose rms is [`Convolver::dropped_rms`], convolved with the input.
    pub fn with_band(n: usize, kernel: &[f64], columns: usize) -> Result<Convolver, String> {
        let m = 2 * n;
        if n == 0 || kernel.len() != m * m {
            return Err("the kernel must be 2n × 2n".into());
        }
        let mut planner = FftPlanner::new();
        let forward = planner.plan_fft_forward(m);
        let inverse = planner.plan_fft_inverse(m);
        let scratch = forward
            .get_inplace_scratch_len()
            .max(inverse.get_inplace_scratch_len());
        let half = m / 2 + 1;
        let mut c = Convolver {
            n,
            spectrum: Vec::new(),
            keep: half,
            dropped_rms: 0.0,
            forward,
            inverse,
            scratch,
            buffers: std::sync::Mutex::new(ConvolverBuffers::default()),
            work: Pool::new(),
        };
        // Shift the centre to index 0: row r holds kernel[(r + n) % m][(· + n) % m].
        let mut rows = vec![ZERO; m * half];
        c.forward_rows(
            m,
            |r, x| kernel[((r + n) % m) * m + (x + n) % m],
            m,
            &mut rows,
            &mut vec![false; m],
        );
        let mut spectrum = vec![ZERO; half * m];
        transpose_into(&rows, half, m, half, &mut spectrum, m);
        drop(rows);
        let forward = &c.forward;
        spectrum.par_chunks_mut(m).for_each_init(
            || vec![ZERO; scratch],
            |s, col| forward.process_with_scratch(col, s),
        );
        c.keep = columns.clamp(1, half);
        c.dropped_rms = dropped_rms(&spectrum, m, c.keep);
        spectrum.truncate(c.keep * m);
        spectrum.shrink_to_fit();
        c.spectrum = spectrum;
        Ok(c)
    }

    /// Half-spectrum columns kept and their number without the band limit.
    pub fn columns(&self) -> (usize, usize) {
        (self.keep, self.n + 1)
    }

    /// The rms over the `2n` grid of the part of the kernel left out.
    pub fn dropped_rms(&self) -> f64 {
        self.dropped_rms
    }

    /// Half spectra of `rows` real rows of width `width` (padded to `m`):
    /// `out[y][kx]`, `kx < keep`. A pair of zero rows leaves `out` as it was and
    /// is marked in `nonzero`.
    fn forward_rows<F>(
        &self,
        rows: usize,
        value: F,
        width: usize,
        out: &mut [C64],
        nonzero: &mut [bool],
    ) where
        F: Fn(usize, usize) -> f64 + Sync,
    {
        let m = 2 * self.n;
        let keep = self.keep;
        out[..rows * keep]
            .par_chunks_mut(2 * keep)
            .zip(nonzero[..rows].par_chunks_mut(2))
            .enumerate()
            .for_each_init(
                || self.lease(),
                |work, (pair, (chunk, marks))| {
                    let (z, s) = &mut **work;
                    let z = &mut z[..m];
                    let (ya, yb) = (2 * pair, 2 * pair + 1);
                    let two = chunk.len() == 2 * keep;
                    let mut any = false;
                    for (x, cell) in z.iter_mut().enumerate().take(width) {
                        let a = value(ya, x);
                        let b = if two { value(yb, x) } else { 0.0 };
                        any |= a != 0.0 || b != 0.0;
                        *cell = Complex::new(a, b);
                    }
                    marks.fill(any);
                    if !any {
                        return;
                    }
                    z[width..].fill(ZERO);
                    self.forward.process_with_scratch(z, s);
                    let (first, second) = chunk.split_at_mut(keep);
                    for k in 0..keep {
                        let p = z[k];
                        let q = z[(m - k) % m].conj();
                        first[k] = (p + q) * 0.5;
                        if two {
                            // (p − q) / 2i
                            let d = (p - q) * 0.5;
                            second[k] = Complex::new(d.im, -d.re);
                        }
                    }
                },
            );
    }

    fn lease(&self) -> Lease<'_, ConvolverWork> {
        let m = 2 * self.n;
        self.work.lease(|| {
            (
                vec![ZERO; (m + COLUMN_PAD) * COLUMN_BLOCK],
                vec![ZERO; self.scratch],
            )
        })
    }

    pub fn side(&self) -> usize {
        self.n
    }

    /// The kernel convolved with `input` (`n × n`), on the `n × n` image.
    pub fn apply(&self, input: &[f64]) -> Vec<f64> {
        let mut out = vec![0.0; self.n * self.n];
        self.apply_into(input, &mut out);
        out
    }

    /// [`Convolver::apply`] into `out`, without allocating after the first
    /// call (rayon's per-thread scratch aside).
    pub fn apply_into(&self, input: &[f64], out: &mut [f64]) {
        let n = self.n;
        let m = 2 * n;
        let half = m / 2 + 1;
        let keep = self.keep;
        assert_eq!(input.len(), n * n, "input must be n × n");
        assert_eq!(out.len(), n * n, "output must be n × n");
        let mut guard = self.buffers.lock().expect("no panic while convolving");
        let ConvolverBuffers { rows, nonzero } = &mut *guard;
        rows.resize(n * keep, ZERO);
        nonzero.resize(n, false);
        self.forward_rows(n, |y, x| input[y * n + x], n, rows, nonzero);
        let (forward, inverse) = (&self.forward, &self.inverse);
        let scale = 1.0 / (m * m) as f64;
        let stride = m + COLUMN_PAD;
        let nonzero: &[bool] = nonzero;
        let spectrum: &[C64] = &self.spectrum;
        let shared = SyncPtr(rows.as_mut_ptr());
        // Each task takes a block of columns out of the half spectra of the
        // rows, convolves them, and puts the first n rows of the result back.
        (0..keep.div_ceil(COLUMN_BLOCK))
            .into_par_iter()
            .for_each_init(
                || self.lease(),
                |work, block| {
                    let (columns, s) = &mut **work;
                    let c0 = block * COLUMN_BLOCK;
                    let h = COLUMN_BLOCK.min(keep - c0);
                    let at = |r: usize| shared.get().wrapping_add(r * keep + c0);
                    for (r, &hit) in nonzero.iter().enumerate() {
                        if !hit {
                            for c in 0..h {
                                columns[c * stride + r] = ZERO;
                            }
                            continue;
                        }
                        // SAFETY: inside `rows`; this task alone touches these
                        // columns.
                        let line = unsafe { std::slice::from_raw_parts(at(r), h) };
                        for (c, v) in line.iter().enumerate() {
                            columns[c * stride + r] = *v;
                        }
                    }
                    for c in 0..h {
                        let col = &mut columns[c * stride..c * stride + m];
                        col[n..].fill(ZERO);
                        forward.process_with_scratch(col, s);
                        let spec = &spectrum[(c0 + c) * m..(c0 + c + 1) * m];
                        for (v, k) in col.iter_mut().zip(spec) {
                            *v *= k * scale;
                        }
                        inverse.process_with_scratch(col, s);
                    }
                    for r in 0..n {
                        // SAFETY: as above.
                        let line = unsafe { std::slice::from_raw_parts_mut(at(r), h) };
                        for (c, v) in line.iter_mut().enumerate() {
                            *v = columns[c * stride + r];
                        }
                    }
                },
            );
        rows.par_chunks(2 * keep)
            .zip(out.par_chunks_mut(2 * n))
            .for_each_init(
                || self.lease(),
                |work, (chunk, o)| {
                    let (z, s) = &mut **work;
                    let z = &mut z[..m];
                    let two = chunk.len() == 2 * keep;
                    let (a, b) = chunk.split_at(keep);
                    for (k, cell) in z.iter_mut().enumerate() {
                        let (ka, conj) = if k < half { (k, false) } else { (m - k, true) };
                        if ka >= keep {
                            *cell = ZERO;
                            continue;
                        }
                        let mut p = a[ka];
                        let mut q = if two { b[ka] } else { ZERO };
                        if conj {
                            p = p.conj();
                            q = q.conj();
                        }
                        // z = p + i q
                        *cell = Complex::new(p.re - q.im, p.im + q.re);
                    }
                    inverse.process_with_scratch(z, s);
                    let (first, second) = o.split_at_mut(n);
                    for x in 0..n {
                        first[x] = z[x].re;
                    }
                    for (x, v) in second.iter_mut().enumerate() {
                        *v = z[x].im;
                    }
                },
            );
    }
}

/// The rms over the `m × m` grid of the columns from `keep` of a half spectrum
/// `[kx][ky]` (Parseval; each column but the self-conjugate last one stands for
/// its mirror too).
fn dropped_rms(spectrum: &[C64], m: usize, keep: usize) -> f64 {
    let power: f64 = spectrum
        .par_chunks(m)
        .enumerate()
        .skip(keep)
        .map(|(k, column)| {
            let weight = if k == m / 2 { 1.0 } else { 2.0 };
            weight * column.iter().map(|v| v.norm_sqr()).sum::<f64>()
        })
        .sum();
    power.sqrt() / (m * m) as f64
}

/// The first implementation of [`Convolver`] on complex transforms of the
/// whole grid: the reference in tests and in the optimisation benchmark.
pub struct ReferenceConvolver {
    n: usize,
    /// The kernel spectrum, transposed (`[kx][ky]`).
    spectrum: Vec<C64>,
    forward: Arc<dyn Fft<f64>>,
    inverse: Arc<dyn Fft<f64>>,
}

/// `out[i][j] = src[j][i]` for `i < rows`, `j < m`; `src` is `m × m`.
fn transpose(src: &[C64], m: usize, rows: usize) -> Vec<C64> {
    const BLOCK: usize = 16;
    let mut out = vec![ZERO; rows * m];
    out.par_chunks_mut(BLOCK * m)
        .enumerate()
        .for_each(|(block, chunk)| {
            let i0 = block * BLOCK;
            let h = chunk.len() / m;
            for j in 0..m {
                let s = &src[j * m + i0..j * m + i0 + h];
                for (di, v) in s.iter().enumerate() {
                    chunk[di * m + j] = *v;
                }
            }
        });
    out
}

fn rows_fft(data: &mut [C64], m: usize, rows: usize, fft: &Arc<dyn Fft<f64>>) {
    let scratch = fft.get_inplace_scratch_len();
    data.par_chunks_mut(m).take(rows).for_each_init(
        || vec![ZERO; scratch],
        |s, row| fft.process_with_scratch(row, s),
    );
}

impl ReferenceConvolver {
    /// `kernel` is `2n × 2n`, centred on `(n, n)`.
    pub fn new(n: usize, kernel: &[f64]) -> Result<ReferenceConvolver, String> {
        let m = 2 * n;
        if n == 0 || kernel.len() != m * m {
            return Err("the kernel must be 2n × 2n".into());
        }
        let mut planner = FftPlanner::new();
        let forward = planner.plan_fft_forward(m);
        let inverse = planner.plan_fft_inverse(m);
        // Shift the centre to index 0: a[r][c] = kernel[(r + n) % m][(c + n) % m].
        let mut a = vec![ZERO; m * m];
        a.par_chunks_mut(m).enumerate().for_each(|(r, row)| {
            let src = ((r + n) % m) * m;
            for (c, v) in row.iter_mut().enumerate() {
                *v = Complex::new(kernel[src + (c + n) % m], 0.0);
            }
        });
        rows_fft(&mut a, m, m, &forward);
        let mut t = transpose(&a, m, m);
        drop(a);
        rows_fft(&mut t, m, m, &forward);
        Ok(ReferenceConvolver {
            n,
            spectrum: t,
            forward,
            inverse,
        })
    }

    /// The kernel convolved with `input` (`n × n`), on the `n × n` image.
    pub fn apply(&self, input: &[f64]) -> Vec<f64> {
        let n = self.n;
        let m = 2 * n;
        assert_eq!(input.len(), n * n, "input must be n × n");
        let scratch = self
            .forward
            .get_inplace_scratch_len()
            .max(self.inverse.get_inplace_scratch_len());
        let mut a = vec![ZERO; m * m];
        // Rows n..2n of the padded input are zero and stay zero.
        a.par_chunks_mut(m).take(n).enumerate().for_each_init(
            || vec![ZERO; scratch],
            |s, (y, row)| {
                for (x, v) in row.iter_mut().take(n).enumerate() {
                    *v = Complex::new(input[y * n + x], 0.0);
                }
                self.forward.process_with_scratch(row, s);
            },
        );
        let mut t = transpose(&a, m, m);
        drop(a);
        let scale = 1.0 / (m * m) as f64;
        t.par_chunks_mut(m)
            .zip(self.spectrum.par_chunks(m))
            .for_each_init(
                || vec![ZERO; scratch],
                |s, (row, spec)| {
                    self.forward.process_with_scratch(row, s);
                    for (v, k) in row.iter_mut().zip(spec) {
                        *v *= k * scale;
                    }
                    self.inverse.process_with_scratch(row, s);
                },
            );
        // Only the first n rows of the result are needed.
        let mut b = transpose(&t, m, n);
        drop(t);
        let mut out = vec![0.0; n * n];
        b.par_chunks_mut(m)
            .zip(out.par_chunks_mut(n))
            .for_each_init(
                || vec![ZERO; scratch],
                |s, (row, o)| {
                    self.inverse.process_with_scratch(row, s);
                    for (x, v) in o.iter_mut().enumerate() {
                        *v = row[x].re;
                    }
                },
            );
        out
    }
}

// ---------------------------------------------------------------------------
// The beam.

/// The exact image-domain beam of gemclean: the patch `±P` subtracted every
/// step, the exterior (the beam outside the patch) for the exact
/// corrections, and the FFT of the whole beam for resyncs.
pub struct Beam {
    pub n: usize,
    /// `b(0)`.
    pub peak: f64,
    /// The patch half-width `P` (at most `n − 1`).
    pub patch: usize,
    patch_values: Vec<f64>,
    /// `ring[d]`: the largest `|b|` in the patch at `∞`-norm distance `≥ d`.
    ring: Vec<f64>,
    /// `(2n − 1)²` values, `[dy + n − 1][dx + n − 1]`, zero inside the patch.
    exterior: Vec<f64>,
    /// `max |b(Δ)| / b(0)` outside the patch (Theorem 6's `f`).
    pub f: f64,
    convolver: Convolver,
}

impl Beam {
    /// From a PSF image on the `2n × 2n` grid centred on `(n, n)` (row-major,
    /// rows the slow offset `dy`; [`crate::clean_certified::WgridMeasurement::psf_image`]
    /// with side `2n`).
    pub fn from_double(n: usize, psf2n: &[f64], patch: usize) -> Result<Beam, String> {
        Beam::from_double_band(n, psf2n, patch, n + 1)
    }

    /// [`Beam::from_double`] whose resyncs use only the lowest `columns` of
    /// the spectrum ([`Convolver::with_band`]). The steps keep the whole beam.
    pub fn from_double_band(
        n: usize,
        psf2n: &[f64],
        patch: usize,
        columns: usize,
    ) -> Result<Beam, String> {
        let m = 2 * n;
        if n < 2 || psf2n.len() != m * m {
            return Err("the PSF must be 2n × 2n with n ≥ 2".into());
        }
        let patch = patch.min(n - 1);
        let at = |dx: isize, dy: isize| {
            psf2n[(n as isize + dy) as usize * m + (n as isize + dx) as usize]
        };
        let peak = at(0, 0);
        if !(peak > 0.0 && peak.is_finite()) {
            return Err(format!("the PSF peak must be positive, not {peak}"));
        }
        let w = 2 * n - 1;
        let off = (n - 1) as isize;
        let h = patch as isize;
        let mut exterior = vec![0.0; w * w];
        exterior
            .par_chunks_mut(w)
            .enumerate()
            .for_each(|(row, out)| {
                let dy = row as isize - off;
                for (col, v) in out.iter_mut().enumerate() {
                    let dx = col as isize - off;
                    if dx.abs() > h || dy.abs() > h {
                        *v = at(dx, dy);
                    }
                }
            });
        let pw = 2 * patch + 1;
        let mut patch_values = vec![0.0; pw * pw];
        for dy in -h..=h {
            for dx in -h..=h {
                patch_values[(dy + h) as usize * pw + (dx + h) as usize] = at(dx, dy);
            }
        }
        // ring[d] = max |b| over offsets in the patch at ∞-norm distance ≥ d.
        let mut ring = vec![0.0_f64; patch + 1];
        for dy in -h..=h {
            for dx in -h..=h {
                let d = dx.abs().max(dy.abs()) as usize;
                ring[d] = ring[d].max(at(dx, dy).abs());
            }
        }
        for d in (0..patch).rev() {
            ring[d] = ring[d].max(ring[d + 1]);
        }
        let f = exterior.iter().fold(0.0_f64, |a, v| a.max(v.abs())) / peak;
        let convolver = Convolver::with_band(n, psf2n, columns)?;
        Ok(Beam {
            n,
            peak,
            patch,
            patch_values,
            ring,
            exterior,
            f,
            convolver,
        })
    }

    /// Spectrum columns the resyncs transform, and their number without the band limit.
    pub fn columns(&self) -> (usize, usize) {
        self.convolver.columns()
    }

    /// Bytes held, by buffer (for the memory report).
    pub fn memory(&self) -> Vec<(&'static str, usize)> {
        use memory::bytes_of;
        let buffers = self.convolver.buffers.lock().expect("no panic in a resync");
        vec![
            ("beam: exterior", bytes_of(&self.exterior)),
            (
                "beam: patch and rings",
                bytes_of(&self.patch_values) + bytes_of(&self.ring),
            ),
            ("beam: spectrum", bytes_of(&self.convolver.spectrum)),
            (
                "beam: row spectra (resync work space)",
                bytes_of(&buffers.rows) + bytes_of(&buffers.nonzero),
            ),
        ]
    }

    /// The rms of the part of the beam the resyncs leave out.
    pub fn dropped_rms(&self) -> f64 {
        self.convolver.dropped_rms()
    }

    /// The whole beam `b(dx, dy)`, `|dx|, |dy| ≤ n − 1`.
    pub fn at(&self, dx: isize, dy: isize) -> f64 {
        let h = self.patch as isize;
        if dx.abs() <= h && dy.abs() <= h {
            let pw = 2 * self.patch + 1;
            self.patch_values[(dy + h) as usize * pw + (dx + h) as usize]
        } else {
            let w = 2 * self.n - 1;
            let off = (self.n - 1) as isize;
            self.exterior[(dy + off) as usize * w + (dx + off) as usize]
        }
    }

    /// `B x` for an `n × n` image (one FFT pair on the `2n` grid).
    pub fn convolve(&self, x: &[f64]) -> Vec<f64> {
        self.convolver.apply(x)
    }

    /// The gather key of pixel `q`: the exterior index of `b(x_p − x_q)` is
    /// `base(p) − key(q)`.
    fn key(&self, q: usize) -> i64 {
        let w = (2 * self.n - 1) as i64;
        (q % self.n) as i64 + w * (q / self.n) as i64
    }

    fn base(&self, p: usize) -> i64 {
        let w = (2 * self.n - 1) as i64;
        let off = (self.n - 1) as i64;
        (p % self.n) as i64 + off + w * ((p / self.n) as i64 + off)
    }
}

// ---------------------------------------------------------------------------
// The working map with cached tile maxima.

/// The working residual and, per tile, the first argmax of `|r̃|` or an upper
/// bound on it. With `lazy` a step only raises the bounds of the tiles its
/// patch touched, by `|c|` times the largest beam value that can reach them,
/// and a tile is rescanned only when its bound wins the argmax. The result is
/// the argmax of the eager rescan (the bound is rigorous, ties included), so
/// the picks do not change.
struct Working {
    n: usize,
    r: Vec<f64>,
    tile: usize,
    tiles: usize,
    /// Upper bound on `max |r̃|` per tile; exact where not `stale`.
    upper: Vec<f64>,
    /// The first pixel attaining the maximum, where not `stale`.
    pixel: Vec<usize>,
    stale: Vec<bool>,
    lazy: bool,
    level: Level,
    work: Work,
    /// The clean mask (task G4): the argmax only sees these pixels; a tile
    /// without any holds the bound 0 and the pixel `usize::MAX`.
    mask: Option<Vec<bool>>,
}

/// Deterministic work counts of a run (they do not depend on the host).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Work {
    /// Working-map pixels updated by patch subtractions.
    pub pixels_subtracted: u64,
    /// Working-map pixels read by tile rescans.
    pub pixels_rescanned: u64,
    /// Tile rescans (excluding full refreshes).
    pub tile_rescans: u64,
    /// Full scans of the working map.
    pub full_scans: u64,
}

impl Work {
    fn add(&mut self, o: &Work) {
        self.pixels_subtracted += o.pixels_subtracted;
        self.pixels_rescanned += o.pixels_rescanned;
        self.tile_rescans += o.tile_rescans;
        self.full_scans += o.full_scans;
    }
}

impl Working {
    fn new(r: Vec<f64>, n: usize, level: Level, tile: usize, lazy: bool) -> Working {
        let tile = tile.max(1);
        let tiles = n.div_ceil(tile);
        let mut w = Working {
            n,
            r,
            tile,
            tiles,
            upper: vec![0.0; tiles * tiles],
            pixel: vec![0; tiles * tiles],
            stale: vec![false; tiles * tiles],
            lazy,
            level,
            work: Work::default(),
            mask: None,
        };
        w.refresh_all();
        w
    }

    /// Restrict the argmax to `mask` (`None`: every pixel) and rescan.
    fn set_mask(&mut self, mask: Option<&[bool]>) {
        self.mask = mask.map(|m| m.to_vec());
        self.refresh_all();
    }

    /// `tile_best` inside the mask.
    fn tile_best_masked(
        r: &[f64],
        n: usize,
        tile: usize,
        tiles: usize,
        t: usize,
        mask: &[bool],
    ) -> (f64, usize) {
        let (ty, tx) = (t / tiles, t % tiles);
        let (y0, y1) = (ty * tile, ((ty + 1) * tile).min(n));
        let (x0, x1) = (tx * tile, ((tx + 1) * tile).min(n));
        let (mut best, mut pixel) = (0.0, usize::MAX);
        for y in y0..y1 {
            for k in y * n + x0..y * n + x1 {
                if mask[k] && (pixel == usize::MAX || r[k].abs() > best) {
                    best = r[k].abs();
                    pixel = k;
                }
            }
        }
        (best, pixel)
    }

    fn tile_best(
        r: &[f64],
        n: usize,
        tile: usize,
        tiles: usize,
        t: usize,
        level: Level,
    ) -> (f64, usize) {
        let (ty, tx) = (t / tiles, t % tiles);
        let (y0, y1) = (ty * tile, ((ty + 1) * tile).min(n));
        let (x0, x1) = (tx * tile, ((tx + 1) * tile).min(n));
        let (mut best, mut row) = (-1.0, y0);
        for y in y0..y1 {
            let v = kernels::max_abs_value(level, &r[y * n + x0..y * n + x1]);
            // Rows ascend, so a later equal value has a larger index.
            if v > best {
                best = v;
                row = y;
            }
        }
        // Locate the value once, in the first row that holds it.
        let segment = &r[row * n + x0..row * n + x1];
        let i = segment.iter().position(|v| v.abs() == best).unwrap_or(0);
        (best, row * n + x0 + i)
    }

    fn refresh_all(&mut self) {
        let (r, n, tile, tiles, level) = (&self.r, self.n, self.tile, self.tiles, self.level);
        let mask = self.mask.as_deref();
        self.upper
            .par_iter_mut()
            .zip(self.pixel.par_iter_mut())
            .enumerate()
            .for_each(|(t, (u, p))| {
                (*u, *p) = match mask {
                    None => Self::tile_best(r, n, tile, tiles, t, level),
                    Some(m) => Self::tile_best_masked(r, n, tile, tiles, t, m),
                };
            });
        self.stale.fill(false);
        self.work.full_scans += 1;
    }

    fn rescan(&mut self, t: usize) {
        (self.upper[t], self.pixel[t]) = match self.mask.as_deref() {
            None => Self::tile_best(&self.r, self.n, self.tile, self.tiles, t, self.level),
            Some(m) => Self::tile_best_masked(&self.r, self.n, self.tile, self.tiles, t, m),
        };
        self.stale[t] = false;
        self.work.tile_rescans += 1;
        self.work.pixels_rescanned += (self.tile * self.tile) as u64;
    }

    /// The first pixel of the largest `|r̃|` and its value.
    fn argmax(&mut self) -> (usize, f64) {
        loop {
            let top = kernels::max_abs_value(self.level, &self.upper);
            // Among the tiles at the top: any stale one first, then the
            // lowest pixel, as a raster scan would find it.
            let mut stale = None;
            let mut first = usize::MAX;
            for (t, &u) in self.upper.iter().enumerate() {
                if u == top {
                    if self.stale[t] {
                        stale = Some(t);
                        break;
                    }
                    first = first.min(self.pixel[t]);
                }
            }
            match stale {
                Some(t) => self.rescan(t),
                // An empty mask: no pixel, value zero.
                None if first == usize::MAX => return (first, 0.0),
                None => return (first, self.r[first]),
            }
        }
    }

    /// `r̃ −= c b(· − x_p)` within the patch.
    fn subtract_patch(&mut self, beam: &Beam, p: usize, c: f64) {
        let n = self.n;
        let h = beam.patch;
        let (px, py) = (p % n, p / n);
        let (y0, y1) = (py.saturating_sub(h), (py + h).min(n - 1));
        let (x0, x1) = (px.saturating_sub(h), (px + h).min(n - 1));
        let pw = 2 * h + 1;
        let len = x1 - x0 + 1;
        for y in y0..=y1 {
            let b0 = (y + h - py) * pw + (x0 + h - px);
            kernels::sub_scaled(
                self.level,
                &mut self.r[y * n + x0..y * n + x0 + len],
                &beam.patch_values[b0..b0 + len],
                c,
            );
        }
        self.work.pixels_subtracted += ((y1 - y0 + 1) * len) as u64;
        let tile = self.tile;
        for ty in y0 / tile..=y1 / tile {
            for tx in x0 / tile..=x1 / tile {
                let t = ty * self.tiles + tx;
                if self.lazy {
                    // The nearest pixel of the tile to p, in the ∞-norm.
                    let dy = (ty * tile)
                        .saturating_sub(py)
                        .max(py.saturating_sub((ty + 1) * tile - 1));
                    let dx = (tx * tile)
                        .saturating_sub(px)
                        .max(px.saturating_sub((tx + 1) * tile - 1));
                    let reach = c.abs() * beam.ring[dx.max(dy)];
                    // Inflated past rounding, so the bound stays rigorous.
                    self.upper[t] = (self.upper[t] + reach) * (1.0 + 1e-15);
                    self.stale[t] = true;
                } else {
                    self.rescan(t);
                }
            }
        }
    }
}

/// The components since the working map was last exact, aggregated per
/// pixel, as gather keys and fluxes.
#[derive(Default)]
struct Since {
    index: HashMap<usize, usize>,
    keys: Vec<i64>,
    flux: Vec<f64>,
    /// `Σ |c|` per pixel, beside `flux` (an upper bound on its magnitude).
    abs_flux: Vec<f64>,
    /// `Σ |c_j|` over the steps (an upper bound on the aggregated sum).
    abs_sum: f64,
    steps: usize,
}

impl Since {
    fn add(&mut self, p: usize, key: i64, c: f64) {
        match self.index.get(&p) {
            Some(&j) => {
                self.flux[j] += c;
                self.abs_flux[j] += c.abs();
            }
            None => {
                self.index.insert(p, self.keys.len());
                self.keys.push(key);
                self.flux.push(c);
                self.abs_flux.push(c.abs());
            }
        }
        self.abs_sum += c.abs();
        self.steps += 1;
    }

    fn clear(&mut self) {
        self.index.clear();
        self.keys.clear();
        self.flux.clear();
        self.abs_flux.clear();
        self.abs_sum = 0.0;
        self.steps = 0;
    }
}

// ---------------------------------------------------------------------------
// The driver.

/// When a minor cycle hands back to the major cycle. Every rule takes the
/// first step of a cycle, and the threshold ends a cycle under all of them.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum CycleStop {
    /// WSClean's `-mgain`: end the cycle once the exact peak falls below
    /// `(1 − g)` times the cycle's first peak.
    PeakFraction(f64),
    /// End the cycle once a fraction `φ` of the reducible misfit has been
    /// predicted removed, with the forcing rule on `φ`. Not WSClean's `-mgain`.
    MisfitFraction,
    /// The measured ℓ∞ rule. A major cycle measures the largest difference
    /// between the image-domain prediction and the exact residual per unit of
    /// flux cleaned, `δ = ‖r − r̃‖_∞ / Σ|c|`. Later cycles end once the exact
    /// peak falls to `ρ δ Σ|c|`, where the prediction can no longer be told
    /// from the peak. The first cycle, before any measurement, uses
    /// `PeakFraction(g)`. A later cycle also ends at `floor` times its first
    /// peak: a batch that cleaned only the phase centre measures `δ` near
    /// zero, and without a floor the next cycle has no stop.
    MeasuredStale { rho: f64, g: f64, floor: f64 },
    /// The certified rule of `research/stop-rule-theorem.md`: end the cycle once
    /// `κ |r_p|` falls to the bound on the beam error at the pick, from a
    /// [`stale_bound::StopBound`]. Needs [`run_with_bound`].
    Certified { kappa: f64 },
    /// No hand-back: the minor cycle runs to the threshold.
    Threshold,
}

/// Settings of a gemclean run.
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    /// The loop gain `γ` (`0 < γ < 2`).
    pub gain: f64,
    /// When a minor cycle hands back to the major cycle.
    pub cycle_stop: CycleStop,
    /// The initial fraction `φ` of [`CycleStop::MisfitFraction`].
    pub major_fraction: f64,
    /// Absolute threshold on the exact peak (Jy/beam).
    pub threshold: f64,
    /// Threshold in units of the residual's robust σ (`1.4826 MAD`),
    /// re-estimated every major cycle; the larger of the two applies.
    pub auto_threshold: Option<f64>,
    pub max_components: usize,
    pub max_major: usize,
    /// The forcing parameter `θ` (`0 ≤ θ < 1`): halve `φ` when the realised
    /// gap exceeds `(1 − θ)` of the predicted decrease, otherwise move `φ`
    /// towards one.
    pub theta: f64,
    /// Resync when `|r_p − r̃_p| > drift · |r̃_p|`.
    pub drift: f64,
    /// Resync when the weak-greedy certificate `τ_k` falls below this.
    pub tau_min: f64,
    /// Resync after this many components without one.
    pub resync_every: usize,
    /// Recompute every `r_p` by brute force (the full beam over the model
    /// change since the major cycle) and record the largest difference.
    pub audit: bool,
    /// The SIMD level (`None`: [`kernels::level`]).
    pub level: Option<Level>,
    /// Tile side of the argmax, pixels.
    pub tile: usize,
    /// Rescan a tile only when its upper bound wins the argmax. The picks are
    /// those of rescanning every touched tile.
    pub lazy_bounds: bool,
}

impl Default for Settings {
    fn default() -> Settings {
        Settings {
            gain: 0.1,
            cycle_stop: CycleStop::MeasuredStale {
                rho: 1.0,
                g: 0.95,
                floor: 0.01,
            },
            major_fraction: 0.8,
            threshold: 0.0,
            auto_threshold: None,
            max_components: 100_000,
            max_major: 20,
            theta: 0.5,
            drift: 0.1,
            tau_min: 0.5,
            resync_every: 2000,
            audit: false,
            level: None,
            tile: 64,
            lazy_bounds: true,
        }
    }
}

/// Why a minor cycle ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MinorStop {
    /// The exact image-domain peak is below the threshold.
    Threshold,
    /// The fraction `φ` of the reducible misfit was removed.
    MajorFraction,
    /// The peak fell to the peak fraction or the measured stale level.
    PeakRule,
    /// The component budget is spent.
    Budget,
}

/// Why the run ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopReason {
    /// The exact (measurement) residual peak is below the threshold.
    Threshold,
    Components,
    MajorCycles,
}

/// Resyncs by cause.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Resyncs {
    pub drift: usize,
    pub tau: usize,
    pub every: usize,
    /// Before deciding that the exact peak is below the threshold.
    pub threshold: usize,
}

impl Resyncs {
    pub fn total(&self) -> usize {
        self.drift + self.tau + self.every + self.threshold
    }
}

/// Wall time by phase, in seconds.
#[derive(Clone, Copy, Debug, Default)]
pub struct Timings {
    /// The first residual (the dirty image).
    pub initial: f64,
    /// Minor-cycle work: argmax, patch subtraction, corrections.
    pub minor: f64,
    /// The exact corrections alone (part of `minor`).
    pub correction: f64,
    pub resync: f64,
    pub major: f64,
    pub total: f64,
}

/// One major cycle's record.
#[derive(Clone, Debug)]
pub struct Cycle {
    pub index: usize,
    pub components: usize,
    pub resyncs: Resyncs,
    pub stop: MinorStop,
    /// Exact peak at the start of the cycle and the threshold used.
    pub peak_start: f64,
    pub threshold: f64,
    /// The fraction `φ` in force.
    pub fraction: f64,
    pub q_before: f64,
    pub q_after: f64,
    /// From the model visibilities.
    pub dq_exact: f64,
    /// `−Σ γ(2−γ)/2 · r_p² / b(0)`, exact for the image-domain beam.
    pub dq_predicted: f64,
    pub gap: f64,
    /// `gap / q_before`.
    pub gap_relative: f64,
    /// The exact misfit rose over the cycle.
    pub ascending: bool,
    /// `Σ |c_j|` of the cycle.
    pub abs_flux: f64,
    /// `‖r_exact − r̃‖_∞` at the end of the cycle: what the image-domain model
    /// got wrong anywhere in the map.
    pub stale_linf: f64,
    /// The level at which the cycle's stale rule would stop, when it has one.
    pub stale_per_flux_used: f64,
    /// The certified rule's bound on `‖r_exact − r̃‖_∞` at the end of the cycle
    /// (zero under the other rules).
    pub bound_linf: f64,
    /// Pixels where the measured `|r_exact − r̃|` exceeded the bound there
    /// (certified rule only; a sampled bound is checked here at every pixel).
    pub bound_violations: usize,
    pub tau_min: f64,
    pub timings: Timings,
}

/// The outcome of [`run`].
#[derive(Clone, Debug)]
pub struct Outcome {
    /// The residual of the empty model.
    pub dirty: Vec<f64>,
    pub model: Vec<f64>,
    /// The exact residual of the final model (from the measurement).
    pub residual: Vec<f64>,
    pub q0: f64,
    pub q_final: f64,
    /// Pixel and exact `r_p` of every component.
    pub steps: Vec<CleanStep>,
    /// The weak-greedy certificate of every component.
    pub taus: Vec<f64>,
    pub cycles: Vec<Cycle>,
    pub stop: StopReason,
    pub f: f64,
    pub patch: usize,
    pub resyncs: Resyncs,
    pub timings: Timings,
    /// Gathered beam terms over all corrections.
    pub correction_terms: u64,
    pub work: Work,
    /// Largest `|r_p(lazy) − r_p(brute force)|` (audit only).
    pub audit_max_error: Option<f64>,
    pub level: Level,
}

impl Outcome {
    /// `(min, 1 %, 10 %, median)` of the `τ_k`.
    pub fn tau_quantiles(&self) -> Option<(f64, f64, f64, f64)> {
        if self.taus.is_empty() {
            return None;
        }
        let mut t = self.taus.clone();
        t.sort_by(|a, b| a.total_cmp(b));
        let q = |f: f64| t[((t.len() - 1) as f64 * f).round() as usize];
        Some((t[0], q(0.01), q(0.1), q(0.5)))
    }
}

/// Minimal JSON helpers for the reports (hand-written, as the examples do).
pub mod json {
    pub fn num(x: f64) -> String {
        if x.is_finite() {
            format!("{x:e}")
        } else {
            "null".into()
        }
    }

    pub fn opt(x: Option<f64>) -> String {
        x.map_or("null".into(), num)
    }

    pub fn text(s: &str) -> String {
        let mut out = String::from("\"");
        for ch in s.chars() {
            match ch {
                '"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
                c => out.push(c),
            }
        }
        out.push('"');
        out
    }

    pub fn obj(fields: &[(&str, String)]) -> String {
        let inner: Vec<String> = fields
            .iter()
            .map(|(k, v)| format!("{}: {v}", text(k)))
            .collect();
        format!("{{{}}}", inner.join(", "))
    }

    pub fn arr(items: &[String]) -> String {
        format!("[{}]", items.join(", "))
    }
}

fn timings_json(t: &Timings) -> String {
    use json::*;
    obj(&[
        ("initial_dirty", num(t.initial)),
        ("minor", num(t.minor)),
        ("correction", num(t.correction)),
        ("resync", num(t.resync)),
        ("major", num(t.major)),
        ("total", num(t.total)),
    ])
}

fn resyncs_json(r: &Resyncs) -> String {
    use json::*;
    obj(&[
        ("drift", r.drift.to_string()),
        ("tau", r.tau.to_string()),
        ("every", r.every.to_string()),
        ("threshold", r.threshold.to_string()),
        ("total", r.total().to_string()),
    ])
}

impl Outcome {
    /// The run as a JSON object: summary, `τ` statistics, timings and one
    /// record per major cycle; `q_floor` adds `(Q − Q_∞)/(Q_0 − Q_∞)`.
    pub fn to_json(&self, q_floor: Option<f64>) -> String {
        use json::*;
        let reducible = |q: f64| q_floor.map(|f| (q - f) / (self.q0 - f));
        let cycles: Vec<String> = self
            .cycles
            .iter()
            .map(|c| {
                obj(&[
                    ("index", c.index.to_string()),
                    ("components", c.components.to_string()),
                    ("stop", text(&format!("{:?}", c.stop))),
                    ("resyncs", resyncs_json(&c.resyncs)),
                    ("peak_start", num(c.peak_start)),
                    ("threshold", num(c.threshold)),
                    ("fraction", num(c.fraction)),
                    ("q_before", num(c.q_before)),
                    ("q_after", num(c.q_after)),
                    ("dq_exact", num(c.dq_exact)),
                    ("dq_predicted", num(c.dq_predicted)),
                    ("gap", num(c.gap)),
                    ("gap_relative", num(c.gap_relative)),
                    ("ascending", c.ascending.to_string()),
                    ("abs_flux", num(c.abs_flux)),
                    ("stale_linf", num(c.stale_linf)),
                    ("stale_per_flux_used", num(c.stale_per_flux_used)),
                    ("bound_linf", num(c.bound_linf)),
                    ("bound_violations", c.bound_violations.to_string()),
                    ("tau_min", num(c.tau_min)),
                    ("reducible_after", opt(reducible(c.q_after))),
                    ("seconds", timings_json(&c.timings)),
                ])
            })
            .collect();
        let tau = self.tau_quantiles();
        let tau_mean = if self.taus.is_empty() {
            None
        } else {
            Some(self.taus.iter().sum::<f64>() / self.taus.len() as f64)
        };
        let corr_per_step = if self.steps.is_empty() {
            None
        } else {
            Some(self.timings.correction / self.steps.len() as f64)
        };
        obj(&[
            ("components", self.steps.len().to_string()),
            (
                "model_pixels",
                self.model.iter().filter(|&&c| c != 0.0).count().to_string(),
            ),
            ("model_flux", num(self.model.iter().sum())),
            ("major_cycles", self.cycles.len().to_string()),
            ("stop", text(&format!("{:?}", self.stop))),
            ("patch", self.patch.to_string()),
            ("f_outside_patch", num(self.f)),
            ("q0", num(self.q0)),
            ("q_final", num(self.q_final)),
            ("q_final_over_q0", num(self.q_final / self.q0)),
            ("q_floor", opt(q_floor)),
            ("reducible_final", opt(reducible(self.q_final))),
            (
                "residual_peak_abs",
                num(self.residual.iter().fold(0.0_f64, |a, r| a.max(r.abs()))),
            ),
            ("residual_mad_sigma", num(mad_sigma(&self.residual))),
            (
                "ascending_major_cycles",
                self.cycles
                    .iter()
                    .filter(|c| c.ascending)
                    .count()
                    .to_string(),
            ),
            (
                "max_abs_gap_relative",
                num(self
                    .cycles
                    .iter()
                    .fold(0.0_f64, |a, c| a.max(c.gap_relative.abs()))),
            ),
            ("resyncs", resyncs_json(&self.resyncs)),
            (
                "tau",
                obj(&[
                    ("min", opt(tau.map(|t| t.0))),
                    ("p01", opt(tau.map(|t| t.1))),
                    ("p10", opt(tau.map(|t| t.2))),
                    ("median", opt(tau.map(|t| t.3))),
                    ("mean", opt(tau_mean)),
                ]),
            ),
            ("correction_terms", self.correction_terms.to_string()),
            (
                "work",
                obj(&[
                    ("pixels_subtracted", self.work.pixels_subtracted.to_string()),
                    ("pixels_rescanned", self.work.pixels_rescanned.to_string()),
                    ("tile_rescans", self.work.tile_rescans.to_string()),
                    ("full_scans", self.work.full_scans.to_string()),
                ]),
            ),
            ("correction_seconds_per_step", opt(corr_per_step)),
            ("audit_max_error", opt(self.audit_max_error)),
            ("simd", text(self.level.name())),
            ("seconds", timings_json(&self.timings)),
            ("cycles", arr(&cycles)),
        ])
    }
}

/// `1.4826 · median |x − median x|`: a robust noise estimate.
pub fn mad_sigma(x: &[f64]) -> f64 {
    if x.is_empty() {
        return 0.0;
    }
    let median = |v: &mut Vec<f64>| {
        let mid = v.len() / 2;
        let (_, m, _) = v.select_nth_unstable_by(mid, |a, b| a.total_cmp(b));
        *m
    };
    let mut v = x.to_vec();
    let med = median(&mut v);
    let mut dev: Vec<f64> = x.iter().map(|a| (a - med).abs()).collect();
    1.4826 * median(&mut dev)
}

fn effective_threshold(residual: &[f64], s: &Settings) -> f64 {
    let mut t = s.threshold;
    if let Some(k) = s.auto_threshold {
        t = t.max(k * mad_sigma(residual));
    }
    t
}

/// Make the working map exact: `r̃ = r_major − B (m − m_major)`.
fn resync(
    work: &mut Working,
    since: &mut Since,
    beam: &Beam,
    model: &[f64],
    model_major: &[f64],
    r_major: &[f64],
    buffers: &mut [Vec<f64>; 2],
) {
    let [delta, conv] = buffers;
    delta.resize(model.len(), 0.0);
    conv.resize(model.len(), 0.0);
    delta
        .par_iter_mut()
        .zip(model)
        .zip(model_major)
        .for_each(|((d, a), b)| *d = a - b);
    beam.convolver.apply_into(delta, conv);
    work.r
        .par_iter_mut()
        .zip(r_major)
        .zip(conv.par_iter())
        .for_each(|((w, r), c)| *w = r - c);
    work.refresh_all();
    since.clear();
}

/// gemclean on `measurement` with `beam` (from the measurement's `2n` PSF);
/// `q_floor`, an estimate of `Q_∞`, makes `φ` a fraction of `Q − Q_∞`.
pub fn run<M: Measurement>(
    measurement: &M,
    beam: &Beam,
    settings: &Settings,
    q_floor: Option<f64>,
) -> Result<Outcome, String> {
    run_with_bound(measurement, beam, settings, q_floor, None)
}

/// [`run`] with the bound that [`CycleStop::Certified`] reads.
pub fn run_with_bound<M: Measurement>(
    measurement: &M,
    beam: &Beam,
    settings: &Settings,
    q_floor: Option<f64>,
    bound: Option<&stale_bound::StopBound>,
) -> Result<Outcome, String> {
    run_masked(measurement, beam, settings, q_floor, bound, None).map(|r| r.0)
}

/// The `-mgain` of a cycle rule under the automatic mask (task G4): `-mgain`
/// itself, or 1 for `-minor-to-threshold`; other rules are refused.
pub fn auto_mask_mgain(rule: CycleStop) -> Result<f64, String> {
    match rule {
        CycleStop::PeakFraction(g) => Ok(g),
        CycleStop::Threshold => Ok(1.0),
        _ => Err(
            "-auto-mask and -abs-auto-mask take -mgain or -minor-to-threshold: radler's \
             mask stages are defined on the peak fraction (research/g4-masks.md)"
                .into(),
        ),
    }
}

/// [`run_with_bound`] with clean masks (task G4, `research/g4-masks.md`):
/// the FITS mask confines every pick and the threshold checks; the automatic
/// mask follows radler's stages ([`mask::AutoState`]), whose record is
/// returned beside the outcome.
pub fn run_masked<M: Measurement>(
    measurement: &M,
    beam: &Beam,
    settings: &Settings,
    q_floor: Option<f64>,
    bound: Option<&stale_bound::StopBound>,
    masking: Option<&mask::Masking>,
) -> Result<(Outcome, Option<mask::AutoState>), String> {
    let start = Instant::now();
    let s = settings;
    let n = measurement.side();
    if beam.n != n {
        return Err("the beam must match the image side".into());
    }
    if !(s.gain > 0.0 && s.gain < 2.0) {
        return Err("the gain must be in (0, 2)".into());
    }
    if matches!(s.cycle_stop, CycleStop::Certified { .. }) && bound.is_none() {
        return Err("the certified rule needs a bound".into());
    }
    let level = s.level.unwrap_or_else(kernels::level);
    let mut timings = Timings::default();
    let mut model = vec![0.0; n * n];
    let t = Instant::now();
    let (mut residual, q0) = measurement.residual(&model)?;
    timings.initial = t.elapsed().as_secs_f64();
    let dirty = residual.clone();
    let mut q = q0;
    let mut fraction = s.major_fraction;
    let mut stale_per_flux = 0.0_f64;
    let mut steps: Vec<CleanStep> = Vec::new();
    let mut taus = Vec::new();
    let mut cycles: Vec<Cycle> = Vec::new();
    let mut resyncs_all = Resyncs::default();
    let mut correction_terms = 0u64;
    let mut work_all = Work::default();
    let mut resync_buffers = [Vec::new(), Vec::new()];
    let mut audit_max: Option<f64> = s.audit.then_some(0.0);
    let fits_mask = masking.and_then(|m| m.fits.clone());
    let mut auto = match masking.and_then(|m| m.auto) {
        Some(a) => Some(mask::AutoState::new(
            a,
            s.auto_threshold,
            s.threshold,
            auto_mask_mgain(s.cycle_stop)?,
        )),
        None => None,
    };
    // radler's Högbom mask: the model's nonzero pixels when first used.
    let mut auto_pixels: Option<Vec<bool>> = None;
    let mut another_prev = true;
    let stop = loop {
        let index = cycles.len() + 1;
        let mut gain = s.gain;
        let (mut threshold, stage_mask) = match auto.as_mut() {
            None => (effective_threshold(&residual, s), fits_mask.clone()),
            Some(a) => {
                if !another_prev {
                    break StopReason::Threshold;
                }
                let c = a.begin(index, &residual);
                if c.gain_doubled {
                    gain = (2.0 * s.gain).min(1.0);
                }
                if c.use_auto {
                    if auto_pixels.is_none() {
                        auto_pixels = Some(mask::from_models(&[&model]));
                    }
                    (c.threshold, auto_pixels.clone())
                } else {
                    (c.threshold, fits_mask.clone())
                }
            }
        };
        let decrease = gain * (2.0 - gain) / 2.0;
        let peak = match &stage_mask {
            None => argmax_abs(&residual).1,
            Some(m) => mask::masked_peak(&residual, Some(m)).map_or(0.0, |p| p.1),
        };
        if auto.is_none() && peak.abs() < threshold {
            break StopReason::Threshold;
        }
        if steps.len() >= s.max_components {
            break StopReason::Components;
        }
        if cycles.len() >= s.max_major {
            break StopReason::MajorCycles;
        }
        let mut ct = Timings::default();
        let model_major = model.clone();
        let mut work = Working::new(residual.clone(), n, level, s.tile, s.lazy_bounds);
        if stage_mask.is_some() {
            work.set_mask(stage_mask.as_deref());
        }
        let mut since = Since::default();
        let mut delta: HashMap<usize, f64> = HashMap::new();
        let mut predicted = 0.0;
        let mut resyncs = Resyncs::default();
        let mut tau_min = f64::INFINITY;
        let mut abs_flux = 0.0_f64;
        let goal = fraction * (q - q_floor.unwrap_or(0.0)).max(0.0);
        let mut first_peak = peak.abs();
        let stale_used = stale_per_flux;
        let mut taken_before = steps.len();
        let cycle_taken = taken_before;
        let mut stop_rule = s.cycle_stop;
        let mut stage = 0;
        let mut last_r: f64;
        // The bound's map as of the last resync, and the steps it holds.
        let mut bound_map: Vec<f64> = Vec::new();
        let mut bound_steps = 0_usize;
        let minor_start = Instant::now();
        let minor_stop = 'stages: loop {
            let stage_stop = loop {
                let (p, rt) = work.argmax();
                if p == usize::MAX {
                    // An empty mask: nothing to clean.
                    last_r = 0.0;
                    break MinorStop::Threshold;
                }
                let tc = Instant::now();
                // A patch covering every offset leaves no exterior to correct.
                let corr = if since.keys.is_empty() || beam.f == 0.0 {
                    0.0
                } else {
                    correction_terms += since.keys.len() as u64;
                    kernels::gather_sum(
                        level,
                        &beam.exterior,
                        beam.base(p),
                        &since.keys,
                        &since.flux,
                    )
                };
                ct.correction += tc.elapsed().as_secs_f64();
                let r = rt - corr;
                last_r = r;
                if let Some(worst) = audit_max.as_mut() {
                    let (px, py) = ((p % n) as isize, (p / n) as isize);
                    let mut brute = residual[p];
                    for (&j, &c) in &delta {
                        let (jx, jy) = ((j % n) as isize, (j / n) as isize);
                        brute -= c * beam.at(px - jx, py - jy);
                    }
                    *worst = worst.max((r - brute).abs());
                }
                if r.abs() < threshold || r == 0.0 {
                    if since.steps == 0 {
                        break MinorStop::Threshold;
                    }
                    let tr = Instant::now();
                    resync(
                        &mut work,
                        &mut since,
                        beam,
                        &model,
                        &model_major,
                        &residual,
                        &mut resync_buffers,
                    );
                    ct.resync += tr.elapsed().as_secs_f64();
                    resyncs.threshold += 1;
                    continue;
                }
                let e = beam.f * beam.peak * since.abs_sum;
                let tau = r.abs() / (rt.abs() + e);
                if tau < s.tau_min {
                    let tr = Instant::now();
                    resync(
                        &mut work,
                        &mut since,
                        beam,
                        &model,
                        &model_major,
                        &residual,
                        &mut resync_buffers,
                    );
                    ct.resync += tr.elapsed().as_secs_f64();
                    resyncs.tau += 1;
                    continue;
                }
                if steps.len() >= s.max_components {
                    break MinorStop::Budget;
                }
                // The ℓ∞ rules read the exact value, and take a cycle's first step.
                if steps.len() > taken_before {
                    let stop_here = match stop_rule {
                        CycleStop::PeakFraction(g) => r.abs() < (1.0 - g) * first_peak,
                        CycleStop::MeasuredStale { rho, g, floor } => {
                            if cycles.is_empty() {
                                r.abs() < (1.0 - g) * first_peak
                            } else {
                                r.abs() <= (rho * stale_used * abs_flux).max(floor * first_peak)
                            }
                        }
                        CycleStop::Certified { kappa } => {
                            let b = bound.expect("checked on entry");
                            if since.steps == 0 && bound_steps != steps.len() - taken_before {
                                bound_map = b.map_of(&model, &model_major);
                                bound_steps = steps.len() - taken_before;
                            }
                            kappa * r.abs() <= b.at_pick(level, beam, p, &bound_map, &since)
                        }
                        CycleStop::MisfitFraction | CycleStop::Threshold => false,
                    };
                    if stop_here {
                        break MinorStop::PeakRule;
                    }
                }
                let c = gain * r / beam.peak;
                abs_flux += c.abs();
                model[p] += c;
                predicted -= decrease * r * r / beam.peak;
                work.subtract_patch(beam, p, c);
                since.add(p, beam.key(p), c);
                if s.audit {
                    *delta.entry(p).or_insert(0.0) += c;
                }
                steps.push(CleanStep { pixel: p, peak: r });
                if let Some(a) = auto.as_mut() {
                    a.record_pick(work.mask.as_deref(), p);
                }
                taus.push(tau);
                tau_min = tau_min.min(tau);
                if s.cycle_stop == CycleStop::MisfitFraction && goal > 0.0 && -predicted >= goal {
                    break MinorStop::MajorFraction;
                }
                let drifted = (r - rt).abs() > s.drift * rt.abs();
                if drifted || since.steps >= s.resync_every {
                    let tr = Instant::now();
                    resync(
                        &mut work,
                        &mut since,
                        beam,
                        &model,
                        &model_major,
                        &residual,
                        &mut resync_buffers,
                    );
                    ct.resync += tr.elapsed().as_secs_f64();
                    if drifted {
                        resyncs.drift += 1;
                    } else {
                        resyncs.every += 1;
                    }
                }
            };
            // The automatic mask (task G4): radler's decision after the first
            // minor loop, and the continued, masked one of the `dual` mode.
            if let Some(a) = auto.as_mut().filter(|_| stage == 0) {
                stage = 1;
                let did_work = steps.len() > taken_before;
                let end = mask::StageEnd {
                    another: stage_stop == MinorStop::PeakRule && did_work,
                    start_peak: first_peak,
                    end_peak: last_r.abs(),
                };
                let (another, cont) = a.end_stage(
                    index,
                    end,
                    index < s.max_major,
                    steps.len() < s.max_components,
                );
                another_prev = another;
                if let Some(k) = cont {
                    if since.steps > 0 {
                        let tr = Instant::now();
                        resync(
                            &mut work,
                            &mut since,
                            beam,
                            &model,
                            &model_major,
                            &residual,
                            &mut resync_buffers,
                        );
                        ct.resync += tr.elapsed().as_secs_f64();
                    }
                    if auto_pixels.is_none() {
                        auto_pixels = Some(mask::from_models(&[&model]));
                    }
                    work.set_mask(auto_pixels.as_deref());
                    let (p, rt) = work.argmax();
                    first_peak = if p == usize::MAX { 0.0 } else { rt.abs() };
                    threshold = k.threshold;
                    stop_rule = CycleStop::PeakFraction(k.gain);
                    taken_before = steps.len();
                    continue 'stages;
                }
            }
            break stage_stop;
        };
        // The prediction at the end of the cycle, exact for the image-domain
        // beam, to measure what the major cycle corrects.
        if since.steps > 0 {
            let tr = Instant::now();
            resync(
                &mut work,
                &mut since,
                beam,
                &model,
                &model_major,
                &residual,
                &mut resync_buffers,
            );
            ct.resync += tr.elapsed().as_secs_f64();
        }
        ct.minor = minor_start.elapsed().as_secs_f64() - ct.resync;
        work_all.add(&work.work);
        memory::mark(&format!("cycle {}: minor", cycles.len() + 1));
        let tm = Instant::now();
        let (next, q_next) = measurement.residual(&model)?;
        ct.major = tm.elapsed().as_secs_f64();
        let stale_linf = next
            .par_iter()
            .zip(work.r.par_iter())
            .map(|(a, b)| (a - b).abs())
            .reduce(|| 0.0, f64::max);
        if abs_flux > 0.0 {
            stale_per_flux = stale_linf / abs_flux;
        }
        let (bound_linf, bound_violations) = match (s.cycle_stop, bound) {
            (CycleStop::Certified { .. }, Some(b)) => {
                let map = b.map_of(&model, &model_major);
                let worst = map.par_iter().copied().reduce(|| 0.0, f64::max);
                let over = next
                    .par_iter()
                    .zip(work.r.par_iter())
                    .zip(map.par_iter())
                    .filter(|&((a, w), e)| (a - w).abs() > *e)
                    .count();
                (worst, over)
            }
            _ => (0.0, 0),
        };
        let dq_exact = q_next - q;
        let gap = dq_exact - predicted;
        cycles.push(Cycle {
            index: cycles.len(),
            components: steps.len() - cycle_taken,
            resyncs,
            stop: minor_stop,
            peak_start: peak.abs(),
            threshold,
            fraction,
            q_before: q,
            q_after: q_next,
            dq_exact,
            dq_predicted: predicted,
            gap,
            gap_relative: gap / q,
            ascending: dq_exact > 0.0,
            abs_flux,
            stale_linf,
            stale_per_flux_used: stale_used,
            bound_linf,
            bound_violations,
            tau_min,
            timings: ct,
        });
        timings.minor += ct.minor;
        timings.correction += ct.correction;
        timings.resync += ct.resync;
        timings.major += ct.major;
        resyncs_all.drift += resyncs.drift;
        resyncs_all.tau += resyncs.tau;
        resyncs_all.every += resyncs.every;
        resyncs_all.threshold += resyncs.threshold;
        if predicted < 0.0 {
            // The forcing rule: halve φ when the realised gap exceeds the
            // allowance `(1 − θ) |predicted|`, otherwise return towards the
            // initial value. The gap is a misfit: it does not see a small
            // pointwise error, so φ must not grow past its initial value
            // (research/gemclean.md, §5).
            if gap.abs() > (1.0 - s.theta) * predicted.abs() {
                fraction *= 0.5;
            } else {
                fraction = (fraction * 2.0).min(s.major_fraction);
            }
        }
        residual = next;
        q = q_next;
    };
    timings.total = start.elapsed().as_secs_f64();
    let outcome = Outcome {
        dirty,
        model,
        residual,
        q0,
        q_final: q,
        steps,
        taus,
        cycles,
        stop,
        f: beam.f,
        patch: beam.patch,
        resyncs: resyncs_all,
        timings,
        correction_terms,
        work: work_all,
        audit_max_error: audit_max,
        level,
    };
    Ok((outcome, auto))
}

// ---------------------------------------------------------------------------
// Restoring.

/// An elliptical Gaussian `exp(−(a X² + b X Y + c Y²))` in pixels of the FITS
/// frame (`X` along FITS axis 1, the gridder's slow index; `Y` along axis 2,
/// the fast index), with its FWHM axes and position angle.
#[derive(Clone, Copy, Debug)]
pub struct RestoringBeam {
    pub a: f64,
    pub b: f64,
    pub c: f64,
    /// FWHM in pixels.
    pub major: f64,
    pub minor: f64,
    /// Position angle of the major axis, radians from +Y (north) towards −X
    /// (east, as `CDELT1 < 0`), in `(−π/2, π/2]`.
    pub pa: f64,
    /// Main-lobe pixels used in the fit.
    pub pixels: usize,
}

impl RestoringBeam {
    fn from_quadratic(a: f64, b: f64, c: f64, pixels: usize) -> RestoringBeam {
        let mean = 0.5 * (a + c);
        let radius = (0.25 * (a - c) * (a - c) + 0.25 * b * b).sqrt();
        let (lmin, lmax) = (mean - radius, mean + radius);
        let fwhm = |l: f64| 2.0 * (std::f64::consts::LN_2 / l).sqrt();
        // The quadratic form is largest along ½ atan2(b, a − c): the minor axis.
        let minor_dir = 0.5 * b.atan2(a - c);
        let major_dir = minor_dir + std::f64::consts::FRAC_PI_2;
        let (x, y) = (major_dir.cos(), major_dir.sin());
        let mut pa = (-x).atan2(y);
        while pa > std::f64::consts::FRAC_PI_2 {
            pa -= std::f64::consts::PI;
        }
        while pa <= -std::f64::consts::FRAC_PI_2 {
            pa += std::f64::consts::PI;
        }
        RestoringBeam {
            a,
            b,
            c,
            major: fwhm(lmin),
            minor: fwhm(lmax),
            pa,
            pixels,
        }
    }

    /// A circular beam of the given FWHM in pixels.
    pub fn circular(fwhm: f64) -> RestoringBeam {
        let a = 4.0 * std::f64::consts::LN_2 / (fwhm * fwhm);
        RestoringBeam::from_quadratic(a, 0.0, a, 0)
    }

    pub fn value(&self, x: f64, y: f64) -> f64 {
        (-(self.a * x * x + self.b * x * y + self.c * y * y)).exp()
    }

    /// The Gaussian on the `2n × 2n` grid centred on `(n, n)`, gridder layout
    /// (row = `X`, column = `Y`), for a [`Convolver`].
    pub fn kernel_double(&self, n: usize) -> Vec<f64> {
        let m = 2 * n;
        let mut k = vec![0.0; m * m];
        k.par_chunks_mut(m).enumerate().for_each(|(r, row)| {
            let x = r as f64 - n as f64;
            for (col, v) in row.iter_mut().enumerate() {
                *v = self.value(x, col as f64 - n as f64);
            }
        });
        k
    }
}

/// Fit an elliptical Gaussian to the PSF main lobe: linear least squares of
/// `−ln(b/b(0))` on the pixels connected to the centre with `b ≥ b(0)/2`.
/// `psf2n` is the `2n × 2n` PSF in gridder layout, centred on `(n, n)`. A
/// main lobe of fewer than six pixels gives a circular one-pixel beam.
pub fn fit_restoring_beam(n: usize, psf2n: &[f64]) -> RestoringBeam {
    let m = 2 * n;
    let centre = n * m + n;
    let peak = psf2n[centre];
    let mut seen = vec![false; m * m];
    let mut queue = vec![centre];
    seen[centre] = true;
    let mut normal = [[0.0; 3]; 3];
    let mut rhs = [0.0; 3];
    let mut count = 0;
    while let Some(p) = queue.pop() {
        let (r, c) = (p / m, p % m);
        let v = psf2n[p] / peak;
        let x = r as f64 - n as f64;
        let y = c as f64 - n as f64;
        let row = [x * x, x * y, y * y];
        for i in 0..3 {
            for j in 0..3 {
                normal[i][j] += row[i] * row[j];
            }
            rhs[i] += row[i] * (-v.ln());
        }
        count += 1;
        for (dr, dc) in [(-1isize, 0isize), (1, 0), (0, -1), (0, 1)] {
            let (rr, cc) = (r as isize + dr, c as isize + dc);
            if rr < 0 || cc < 0 || rr >= m as isize || cc >= m as isize {
                continue;
            }
            let q = rr as usize * m + cc as usize;
            if !seen[q] && psf2n[q] >= 0.5 * peak {
                seen[q] = true;
                queue.push(q);
            }
        }
    }
    let flat: Vec<f64> = normal.iter().flatten().copied().collect();
    match (count >= 6)
        .then(|| crate::clean::solve_dense(&flat, &rhs))
        .flatten()
    {
        Some(s) if s[0] > 0.0 && s[2] > 0.0 && 4.0 * s[0] * s[2] > s[1] * s[1] => {
            RestoringBeam::from_quadratic(s[0], s[1], s[2], count)
        }
        _ => RestoringBeam {
            pixels: count,
            ..RestoringBeam::circular(1.0)
        },
    }
}

/// The restored image `residual + model ⊛ G` with the Gaussian at unit peak.
pub fn restore(n: usize, model: &[f64], residual: &[f64], beam: &RestoringBeam) -> Vec<f64> {
    let conv = Convolver::new(n, &beam.kernel_double(n)).expect("valid kernel size");
    let smooth = conv.apply(model);
    smooth.iter().zip(residual).map(|(s, r)| s + r).collect()
}

/// The peak resident set size (Linux `VmHWM`), when the platform reports it.
pub fn peak_memory_bytes() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|l| l.starts_with("VmHWM:"))?;
    let kb: u64 = line.split_whitespace().nth(1)?.parse().ok()?;
    Some(kb * 1024)
}

// ---------------------------------------------------------------------------
// Kernel micro-benchmark.

/// Nanoseconds per pixel (patch subtraction, argmax) and per term (gather)
/// of one SIMD level.
#[derive(Clone, Copy, Debug)]
pub struct KernelTiming {
    pub level: Level,
    pub patch_ns_per_pixel: f64,
    /// The same patch loop on an `f32` map, compiled for the build's baseline
    /// (the evidence for or against an `f32` working map).
    pub patch_f32_ns_per_pixel: f64,
    pub argmax_ns_per_pixel: f64,
    pub gather_ns_per_term: f64,
}

/// Time the three kernels at every level the CPU has, on a synthetic
/// `n × n` map, `±patch` beam patches and `terms` gathered components; the
/// fastest of `rounds` passes per kernel.
pub fn kernel_benchmark(
    n: usize,
    patch: usize,
    terms: usize,
    reps: usize,
    rounds: usize,
) -> Vec<KernelTiming> {
    let mut state = 0x9e37_79b9_7f4a_7c15u64;
    let mut next = || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
    };
    let map: Vec<f64> = (0..n * n).map(|_| next()).collect();
    let pw = 2 * patch + 1;
    let beam: Vec<f64> = (0..pw).map(|_| next()).collect();
    let w = 2 * n - 1;
    let table: Vec<f64> = (0..w * w).map(|_| next()).collect();
    let base = (w * w - 1) as i64;
    let keys: Vec<i64> = (0..terms)
        .map(|_| ((next() + 0.5) * (w * w - 1) as f64) as i64)
        .collect();
    let flux: Vec<f64> = (0..terms).map(|_| next()).collect();
    let mut out = Vec::new();
    for level in [Level::Scalar, Level::Avx2, Level::Avx512] {
        if level > kernels::detected() {
            continue;
        }
        let mut work = map.clone();
        let tiles = n.div_ceil(32);
        let (mut patch_ns, mut patch_f32_ns, mut argmax_ns, mut gather_ns) =
            (f64::INFINITY, f64::INFINITY, f64::INFINITY, f64::INFINITY);
        let mut work32: Vec<f32> = map.iter().map(|&v| v as f32).collect();
        let beam32: Vec<f32> = beam.iter().map(|&v| v as f32).collect();
        for _ in 0..rounds.max(1) {
            let t = Instant::now();
            for rep in 0..reps {
                for row in 0..pw.min(n) {
                    let r = &mut work[row * n..row * n + pw.min(n)];
                    kernels::sub_scaled(level, r, &beam, 1e-3 * rep as f64);
                }
            }
            let per = t.elapsed().as_secs_f64() * 1e9 / (reps * pw.min(n) * pw.min(n)) as f64;
            patch_ns = patch_ns.min(per);
            let t = Instant::now();
            for rep in 0..reps {
                let c = 1e-3 * rep as f32;
                for row in 0..pw.min(n) {
                    let r = &mut work32[row * n..row * n + pw.min(n)];
                    for (v, b) in r.iter_mut().zip(&beam32) {
                        *v -= c * b;
                    }
                }
            }
            let per = t.elapsed().as_secs_f64() * 1e9 / (reps * pw.min(n) * pw.min(n)) as f64;
            patch_f32_ns = patch_f32_ns.min(per);
            let t = Instant::now();
            let mut sink = 0usize;
            for _ in 0..reps.div_ceil(20) {
                for tile in 0..tiles * tiles {
                    sink =
                        sink.wrapping_add(Working::tile_best(&work, n, 32, tiles, tile, level).1);
                }
            }
            let per = t.elapsed().as_secs_f64() * 1e9 / (reps.div_ceil(20) * n * n) as f64;
            argmax_ns = argmax_ns.min(per);
            let t = Instant::now();
            let mut total = 0.0;
            for _ in 0..reps {
                total += kernels::gather_sum(level, &table, base, &keys, &flux);
            }
            let per = t.elapsed().as_secs_f64() * 1e9 / (reps * terms.max(1)) as f64;
            gather_ns = gather_ns.min(per);
            std::hint::black_box((sink, total));
        }
        out.push(KernelTiming {
            level,
            patch_ns_per_pixel: patch_ns,
            patch_f32_ns_per_pixel: patch_f32_ns,
            argmax_ns_per_pixel: argmax_ns,
            gather_ns_per_term: gather_ns,
        });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clean::{self, Grid, Psf, Sampling, Vis};
    use crate::clean_certified::DftMeasurement;

    struct Rng(u64);

    impl Rng {
        fn next(&mut self) -> f64 {
            self.0 ^= self.0 << 13;
            self.0 ^= self.0 >> 7;
            self.0 ^= self.0 << 17;
            (self.0 >> 11) as f64 / (1u64 << 53) as f64
        }
    }

    fn sampling(count: usize, seed: u64) -> Sampling {
        let mut rng = Rng(seed);
        let mut s = Sampling::default();
        for _ in 0..count {
            s.u.push((rng.next() - 0.5) * 10000.0);
            s.v.push((rng.next() - 0.5) * 10000.0);
            s.w.push(0.5 + rng.next());
        }
        s.normalise();
        s
    }

    const GRID: Grid = Grid {
        n: 16,
        cell: 1.0e-4,
    };

    #[test]
    fn a_band_limited_kernel_drops_its_empty_columns() {
        // Harmonics of the 2n grid up to |kx| = 8: nothing beyond column 8.
        let (n, m) = (32_usize, 64_usize);
        let mut kernel = vec![0.0; m * m];
        for (y, row) in kernel.chunks_mut(m).enumerate() {
            for (x, v) in row.iter_mut().enumerate() {
                let (dx, dy) = (x as f64 - n as f64, y as f64 - n as f64);
                for (kx, ky, a) in [(0.0, 0.0, 0.5), (8.0, 3.0, 0.3), (5.0, -7.0, 0.2)] {
                    *v += a * (2.0 * std::f64::consts::PI * (kx * dx + ky * dy) / m as f64).cos();
                }
            }
        }
        let mut rng = Rng(7);
        let input: Vec<f64> = (0..n * n).map(|_| rng.next() - 0.5).collect();
        let whole = Convolver::new(n, &kernel).unwrap();
        let band = Convolver::with_band(n, &kernel, 9).unwrap();
        assert_eq!(whole.columns(), (n + 1, n + 1));
        assert_eq!(whole.dropped_rms(), 0.0);
        assert_eq!(band.columns(), (9, n + 1));
        assert!(band.dropped_rms() < 1e-12);
        let (a, b) = (whole.apply(&input), band.apply(&input));
        for (x, y) in a.iter().zip(&b) {
            assert!((x - y).abs() < 1e-9, "{x} {y}");
        }
        // Too few columns drop a real part of the kernel, and it says so: the
        // two harmonics of amplitude 0.3 and 0.2 have rms 0.3 / √2 and 0.2 / √2.
        let cut = Convolver::with_band(n, &kernel, 5).unwrap();
        let expected = (0.3_f64.powi(2) / 2.0 + 0.2_f64.powi(2) / 2.0).sqrt();
        assert!(
            (cut.dropped_rms() - expected).abs() < 1e-9,
            "{}",
            cut.dropped_rms()
        );
    }

    fn data(s: &Sampling, seed: u64) -> Vec<Vis> {
        let mut rng = Rng(seed ^ 0x9e37_79b9_7f4a_7c15);
        let mut truth = vec![0.0; GRID.pixels()];
        truth[GRID.index(4, 5)] = 1.0;
        truth[GRID.index(11, 9)] = -0.6;
        truth[GRID.index(1 + (seed as usize % 13), 13)] = 0.4;
        truth[GRID.index(15, 0)] = 0.3;
        let mut vis = clean::predict(s, &GRID, &truth);
        for v in &mut vis {
            v.0 += 0.05 * (rng.next() - 0.5);
            v.1 += 0.05 * (rng.next() - 0.5);
        }
        vis
    }

    /// The `2n × 2n` PSF image of a direct-sum beam (row and column 0, the
    /// offset −n, are never used and stay zero).
    fn double(psf: &Psf) -> Vec<f64> {
        let n = psf.n;
        let m = 2 * n;
        let mut out = vec![0.0; m * m];
        for r in 1..m {
            for c in 1..m {
                out[r * m + c] = psf.at(c as isize - n as isize, r as isize - n as isize);
            }
        }
        out
    }

    #[test]
    fn convolver_equals_direct_subtraction() {
        let s = sampling(150, 4);
        let psf = clean::psf(&s, &GRID);
        let conv = Convolver::new(GRID.n, &double(&psf)).unwrap();
        let mut rng = Rng(8);
        let mut model = vec![0.0; GRID.pixels()];
        for p in [
            GRID.index(0, 0),
            GRID.index(15, 2),
            GRID.index(3, 15),
            77,
            200,
        ] {
            model[p] = rng.next() - 0.3;
        }
        let fast = conv.apply(&model);
        let direct = clean::convolve(&psf, &model);
        for (a, b) in fast.iter().zip(&direct) {
            assert!((a - b).abs() < 1e-12, "{a} against {b}");
        }
        // A second call reuses the buffers; the reference agrees.
        let again = conv.apply(&model);
        assert_eq!(fast, again);
        // A dense input in between leaves nothing behind for a sparse one's
        // zero rows, which are not stored.
        let dense: Vec<f64> = (0..GRID.pixels()).map(|_| rng.next() - 0.5).collect();
        let _ = conv.apply(&dense);
        assert_eq!(fast, conv.apply(&model));
        let reference = ReferenceConvolver::new(GRID.n, &double(&psf)).unwrap();
        for (a, b) in fast.iter().zip(&reference.apply(&model)) {
            assert!((a - b).abs() < 1e-12, "{a} against {b}");
        }
    }

    #[test]
    fn convolver_handles_odd_sides_and_empty_rows() {
        for n in [7usize, 9, 16] {
            let g = Grid { n, cell: 1.0e-4 };
            let s = sampling(90, 40 + n as u64);
            let psf = clean::psf(&s, &g);
            let conv = Convolver::new(n, &double(&psf)).unwrap();
            let mut model = vec![0.0; n * n];
            model[n - 1] = 0.7; // first row only, then an empty stretch
            model[n * n - 1] = -0.4; // last row of an odd side has no partner
            let direct = clean::convolve(&psf, &model);
            for (a, b) in conv.apply(&model).iter().zip(&direct) {
                assert!((a - b).abs() < 1e-12, "side {n}: {a} against {b}");
            }
        }
    }

    #[test]
    fn tiled_argmax_follows_the_raster_argmax() {
        let mut rng = Rng(21);
        for n in [5, 32, 33, 70] {
            let r: Vec<f64> = (0..n * n).map(|_| rng.next() - 0.5).collect();
            let mut w = Working::new(r.clone(), n, kernels::level(), 32, false);
            assert_eq!(w.argmax().0, clean::argmax_abs(&r).0);
            // A tie across tiles resolves to the lower index.
            let v = 2.0;
            w.r[n * n - 1] = -v;
            w.r[n + 1] = v;
            w.refresh_all();
            assert_eq!(w.argmax().0, n + 1);
        }
    }

    #[test]
    fn exact_steps_audit_and_gap_on_the_direct_measurement() {
        for (seed, patch) in [(3u64, 2usize), (5, 4), (9, 1), (12, 15)] {
            let s = sampling(160, seed);
            let vis = data(&s, seed);
            let m = DftMeasurement {
                sampling: &s,
                grid: GRID,
                vis: &vis,
            };
            let psf = clean::psf(&s, &GRID);
            let beam = Beam::from_double(GRID.n, &double(&psf), patch).unwrap();
            let settings = Settings {
                gain: 0.2,
                threshold: 1e-3,
                max_components: 600,
                max_major: 6,
                audit: true,
                resync_every: 50,
                ..Settings::default()
            };
            let out = run(&m, &beam, &settings, None).unwrap();
            assert!(out.steps.len() > 20, "seed {seed}: {}", out.steps.len());
            let audit = out.audit_max_error.unwrap();
            assert!(audit < 1e-12, "seed {seed}, patch {patch}: audit {audit}");
            for c in &out.cycles {
                assert!(
                    c.gap.abs() <= 1e-11 * c.q_before,
                    "seed {seed}, cycle {}: gap {}",
                    c.index,
                    c.gap
                );
                assert!(c.dq_exact < 0.0 && !c.ascending);
            }
            for t in &out.taus {
                assert!(*t >= settings.tau_min && *t <= 1.0 + 1e-12);
            }
            if patch == GRID.n - 1 {
                assert_eq!(out.f, 0.0);
                assert_eq!(out.correction_terms, 0);
            } else {
                assert!(out.f > 0.0 && out.correction_terms > 0);
            }
        }
    }

    /// The fixture of `long_minor_cycles_do_not_fit_the_beam_error`.
    fn strong_w_field(
        sources: &[(usize, usize, f64)],
    ) -> (
        crate::clean_certified::WgridMeasurement,
        Vec<f64>,
        Vec<f64>,
        Vec<f64>,
    ) {
        use crate::clean_certified::WgridMeasurement;
        use crate::wgridder::Options;
        let mut rng = Rng(2026);
        let (n, cell) = (128usize, 3.0e-4);
        let nvis = 8000;
        let mut uvw = Vec::with_capacity(3 * nvis);
        for _ in 0..nvis {
            uvw.push((rng.next() - 0.5) * 6000.0);
            uvw.push((rng.next() - 0.5) * 6000.0);
            uvw.push((rng.next() - 0.5) * 6000.0);
        }
        let opts = Options {
            flip_v: true,
            flip_w: true,
            ..Options::default()
        };
        let freq = vec![299_792_458.0];
        let wgt = vec![1.0; nvis];
        let empty = vec![Complex::new(0.0, 0.0); nvis];
        let mut truth = vec![0.0; n * n];
        for &(i, j, f) in sources {
            truth[i * n + j] = f;
        }
        let mut m = WgridMeasurement::new(
            uvw.clone(),
            freq.clone(),
            empty,
            wgt.clone(),
            n,
            cell,
            1e-9,
            opts,
        )
        .unwrap();
        m.vis = m.predict(&truth).unwrap();
        for v in &mut m.vis {
            v.re += 0.02 * (rng.next() - 0.5);
            v.im += 0.02 * (rng.next() - 0.5);
        }
        let normalised = vec![1.0 / nvis as f64; nvis];
        (m, uvw, freq, normalised)
    }

    fn strong_w_bound(
        m: &crate::clean_certified::WgridMeasurement,
        uvw: &[f64],
        freq: &[f64],
        wgt: &[f64],
    ) -> (Beam, Vec<f64>, stale_bound::StaleBound) {
        use crate::wgridder::Options;
        let (n, cell) = (128usize, 3.0e-4);
        let psf2n = m.psf_image(2 * n).unwrap();
        let beam = Beam::from_double(n, &psf2n, 16).unwrap();
        let opts = Options {
            flip_v: true,
            flip_w: true,
            do_wgridding: true,
            ..Options::default()
        };
        let table =
            stale_bound::StaleBound::compute(n, cell, &opts, uvw, freq, wgt, &psf2n, 1e-9, 0)
                .unwrap();
        (beam, psf2n, table)
    }

    /// The table is an upper bound on the true Gram matrix: exact columns from
    /// the gridder, minus the shifted PSF, on a strong w-term. The centre
    /// column vanishes, the diagonal vanishes.
    #[test]
    fn stale_bound_holds_for_exact_columns() {
        let n = 128usize;
        let (m, uvw, freq, wgt) = strong_w_field(&[(14, 20, 1.0)]);
        let (beam, _, table) = strong_w_bound(&m, &uvw, &freq, &wgt);
        assert!(table.delta() > 1e-3, "delta {}", table.delta());
        let w = 2 * n;
        for &(px, py) in &[
            (64, 64),
            (70, 64),
            (10, 12),
            (120, 8),
            (3, 125),
            (127, 127),
            (30, 100),
        ] {
            let j = py * n + px;
            let mut unit = vec![0.0; n * n];
            unit[j] = 1.0;
            let g = m.gram_apply(&unit).unwrap();
            let mut worst = 0.0_f64;
            for qy in 0..n {
                for qx in 0..n {
                    let (dx, dy) = (qx as isize - px as isize, qy as isize - py as isize);
                    let e = (g[qy * n + qx] - beam.at(dx, dy)).abs();
                    worst = worst.max(e);
                    let env =
                        table.envelope[(n as isize + dy) as usize * w + (n as isize + dx) as usize];
                    if dx != 0 || dy != 0 {
                        assert!(e <= env + 1e-7, "({px},{py}) -> ({qx},{qy}): {e} > {env}");
                    } else {
                        assert!(e < 1e-7, "diagonal {e}");
                    }
                }
            }
            if (px, py) == (64, 64) {
                assert!(worst < 1e-7, "centre column {worst}");
            }
            assert!(
                worst <= table.at_pixel(j) + 1e-7,
                "({px},{py}): {worst} > {}",
                table.at_pixel(j)
            );
        }
    }

    /// The certified rule on a strong w-term: the bound holds at every pixel at
    /// the end of every cycle, each cycle descends, and the sky stays within
    /// five thresholds of the default's false flux.
    #[test]
    fn certified_rule_holds_on_a_strong_w_term() {
        let n = 128usize;
        let sources = [
            (14usize, 20usize, 1.0),
            (110, 30, 0.7),
            (25, 105, 0.5),
            (100, 100, 0.3),
            (64, 20, 0.2),
        ];
        let (m, uvw, freq, wgt) = strong_w_field(&sources);
        let (beam, _, table) = strong_w_bound(&m, &uvw, &freq, &wgt);
        let settings = Settings {
            threshold: 2e-3,
            max_components: 40_000,
            max_major: 400,
            ..Settings::default()
        };
        let false_flux = |o: &Outcome| {
            let mut total = 0.0;
            for (p, &c) in o.model.iter().enumerate() {
                let (i, j) = ((p / n) as i64, (p % n) as i64);
                let near = sources
                    .iter()
                    .any(|&(a, b, _)| (i - a as i64).abs() <= 2 && (j - b as i64).abs() <= 2);
                if !near {
                    total += c.abs();
                }
            }
            total
        };
        let base = run(&m, &beam, &settings, None).unwrap();
        for kind in [
            stale_bound::BoundKind::Envelope,
            stale_bound::BoundKind::Radial,
        ] {
            let bound = stale_bound::StopBound::new(&table, kind).unwrap();
            let out = run_with_bound(
                &m,
                &beam,
                &Settings {
                    cycle_stop: CycleStop::Certified { kappa: 0.5 },
                    ..settings
                },
                None,
                Some(&bound),
            )
            .unwrap();
            assert_eq!(out.stop, StopReason::Threshold, "{kind:?}");
            for c in &out.cycles {
                assert_eq!(c.bound_violations, 0, "{kind:?}, cycle {}", c.index);
                assert!(
                    c.stale_linf <= c.bound_linf + 1e-9,
                    "{kind:?}, cycle {}",
                    c.index
                );
                assert!(c.dq_exact < 0.0, "{kind:?}, cycle {}", c.index);
            }
            assert!(
                false_flux(&out) <= false_flux(&base) + 5.0 * settings.threshold,
                "{kind:?}: {} against {}",
                false_flux(&out),
                false_flux(&base)
            );
        }
    }

    /// The counterexample to the measured rule: a batch at the phase centre
    /// measures a stale error of about nothing, because the centre column of
    /// the error is zero, so the next cycle has no stop and runs to the
    /// threshold, where the off-centre sources make the error real. The default's
    /// floor stops it, and the certified rule does not depend on what the last
    /// batch happened to measure.
    #[test]
    fn a_centre_batch_measures_nothing_about_the_next_cycle() {
        let sources = [
            (64usize, 64usize, 100.0),
            (14, 20, 1.0),
            (110, 30, 0.7),
            (25, 105, 0.5),
        ];
        let (m, uvw, freq, wgt) = strong_w_field(&sources);
        let (beam, _, table) = strong_w_bound(&m, &uvw, &freq, &wgt);
        let settings = Settings {
            threshold: 2e-3,
            max_components: 40_000,
            max_major: 400,
            ..Settings::default()
        };
        let no_floor = Settings {
            cycle_stop: CycleStop::MeasuredStale {
                rho: 1.0,
                g: 0.95,
                floor: 0.0,
            },
            ..settings
        };
        let out = run(&m, &beam, &no_floor, None).unwrap();
        let first = &out.cycles[0];
        let second = &out.cycles[1];
        let measured = first.stale_linf / first.abs_flux;
        assert!(measured < 1e-7, "first batch measures {measured}");
        let next = second.stale_linf / second.abs_flux;
        assert!(next > 100.0 * measured, "{next} against {measured}");
        assert_ne!(second.stop, MinorStop::PeakRule);
        // The default's floor gives that cycle a stop.
        let floored = run(&m, &beam, &settings, None).unwrap();
        assert_eq!(floored.cycles[1].stop, MinorStop::PeakRule);
        // The rule that uses the bound stops long before the threshold.
        let bound = stale_bound::StopBound::new(&table, stale_bound::BoundKind::Envelope).unwrap();
        let certified = run_with_bound(
            &m,
            &beam,
            &Settings {
                cycle_stop: CycleStop::Certified { kappa: 0.5 },
                ..settings
            },
            None,
            Some(&bound),
        )
        .unwrap();
        for c in &certified.cycles {
            assert_eq!(c.bound_violations, 0, "cycle {}", c.index);
        }
        assert!(
            certified.cycles[1].stop == MinorStop::PeakRule
                || certified.cycles[0].stop == MinorStop::PeakRule
        );
    }

    /// The regression test of the long minor cycle (found on the benchmark's
    /// S1 at `0d804e4`): the phase-centre beam is not the Gram matrix off
    /// centre when the w-term matters, a cycle run down to the threshold fits
    /// that error with false components, and the misfit gap does not show it.
    /// The default hands back on the exact peak, stays close to the many-cycle
    /// reference and spends no cycle's budget.
    #[test]
    fn long_minor_cycles_do_not_fit_the_beam_error() {
        use crate::clean_certified::WgridMeasurement;
        use crate::wgridder::Options;
        let mut rng = Rng(2026);
        let (n, cell) = (128usize, 3.0e-4);
        let nvis = 8000;
        let mut uvw = Vec::with_capacity(3 * nvis);
        for _ in 0..nvis {
            uvw.push((rng.next() - 0.5) * 6000.0);
            uvw.push((rng.next() - 0.5) * 6000.0);
            uvw.push((rng.next() - 0.5) * 6000.0);
        }
        let opts = Options {
            flip_v: true,
            flip_w: true,
            ..Options::default()
        };
        let freq = vec![299_792_458.0];
        let wgt = vec![1.0; nvis];
        let empty = vec![Complex::new(0.0, 0.0); nvis];
        let mut truth = vec![0.0; n * n];
        let sources = [
            (14usize, 20usize, 1.0),
            (110, 30, 0.7),
            (25, 105, 0.5),
            (100, 100, 0.3),
            (64, 20, 0.2),
        ];
        for &(i, j, f) in &sources {
            truth[i * n + j] = f;
        }
        let mut m = WgridMeasurement::new(uvw, freq, empty, wgt, n, cell, 1e-9, opts).unwrap();
        m.vis = m.predict(&truth).unwrap();
        for v in &mut m.vis {
            v.re += 0.02 * (rng.next() - 0.5);
            v.im += 0.02 * (rng.next() - 0.5);
        }
        let beam = Beam::from_double(n, &m.psf_image(2 * n).unwrap(), 16).unwrap();
        let false_flux = |o: &Outcome| {
            let mut total = 0.0;
            for (p, &c) in o.model.iter().enumerate() {
                let (i, j) = ((p / n) as i64, (p % n) as i64);
                let near = sources
                    .iter()
                    .any(|&(a, b, _)| (i - a as i64).abs() <= 2 && (j - b as i64).abs() <= 2);
                if !near {
                    total += c.abs();
                }
            }
            total
        };
        let settings = Settings {
            threshold: 2e-3,
            max_components: 40_000,
            max_major: 400,
            ..Settings::default()
        };
        let run_with = |cycle_stop: CycleStop| {
            run(
                &m,
                &beam,
                &Settings {
                    cycle_stop,
                    ..settings
                },
                None,
            )
            .unwrap()
        };
        let reference = run_with(CycleStop::PeakFraction(0.3));
        let default = run(&m, &beam, &settings, None).unwrap();
        let long = run_with(CycleStop::Threshold);
        let (r, d, l) = (
            false_flux(&reference),
            false_flux(&default),
            false_flux(&long),
        );
        assert_eq!(default.stop, StopReason::Threshold);
        // Within five thresholds of the many-cycle reference, whose few pixels
        // of false flux here round to nothing.
        assert!(
            d <= 2.0 * r + 5.0 * settings.threshold,
            "default {d} against the reference {r}"
        );
        assert!(
            l > 2.0 * d,
            "the long cycle {l} against the default {d}: not vacuous"
        );
        assert!(default.cycles.len() >= 3);
        // A floor that binds ends later cycles early, so it takes more of them.
        let floored = run_with(CycleStop::MeasuredStale {
            rho: 1.0,
            g: 0.95,
            floor: 0.5,
        });
        assert_eq!(floored.stop, StopReason::Threshold);
        assert!(floored.cycles.len() > default.cycles.len());
    }

    /// The bounds only postpone rescans: the picks and values of the lazy
    /// tile maxima are those of the eager rescans, whatever the tile size.
    #[test]
    fn lazy_bounds_keep_the_picks_bit_identical() {
        let s = sampling(160, 17);
        let vis = data(&s, 17);
        let m = DftMeasurement {
            sampling: &s,
            grid: GRID,
            vis: &vis,
        };
        let psf = clean::psf(&s, &GRID);
        let beam = Beam::from_double(GRID.n, &double(&psf), 5).unwrap();
        let base = Settings {
            threshold: 1e-3,
            max_components: 500,
            cycle_stop: CycleStop::Threshold,
            ..Settings::default()
        };
        let reference = run(
            &m,
            &beam,
            &Settings {
                lazy_bounds: false,
                tile: 4,
                ..base
            },
            None,
        )
        .unwrap();
        assert!(reference.steps.len() > 50);
        for (lazy_bounds, tile) in [(true, 2), (true, 4), (true, 16), (false, 8)] {
            let out = run(
                &m,
                &beam,
                &Settings {
                    lazy_bounds,
                    tile,
                    ..base
                },
                None,
            )
            .unwrap();
            assert_eq!(out.steps.len(), reference.steps.len());
            for (a, b) in out.steps.iter().zip(&reference.steps) {
                assert_eq!(a.pixel, b.pixel);
                assert_eq!(a.peak.to_bits(), b.peak.to_bits());
            }
            assert_eq!(out.model, reference.model);
        }
    }

    #[test]
    fn simd_and_scalar_runs_agree() {
        let s = sampling(160, 31);
        let vis = data(&s, 31);
        let m = DftMeasurement {
            sampling: &s,
            grid: GRID,
            vis: &vis,
        };
        let psf = clean::psf(&s, &GRID);
        let beam = Beam::from_double(GRID.n, &double(&psf), 3).unwrap();
        let mut settings = Settings {
            threshold: 1e-3,
            max_components: 300,
            ..Settings::default()
        };
        settings.level = Some(Level::Scalar);
        let a = run(&m, &beam, &settings, None).unwrap();
        settings.level = Some(kernels::detected());
        let b = run(&m, &beam, &settings, None).unwrap();
        assert_eq!(a.steps.len(), b.steps.len());
        for (x, y) in a.steps.iter().zip(&b.steps) {
            assert_eq!(x.pixel, y.pixel);
            assert!((x.peak - y.peak).abs() <= 1e-12 * x.peak.abs().max(1e-3));
        }
    }

    #[test]
    fn gaussian_fit_recovers_a_rotated_beam() {
        let n = 40;
        let truth = RestoringBeam::from_quadratic(0.05, 0.03, 0.012, 0);
        let psf = truth.kernel_double(n);
        let fit = fit_restoring_beam(n, &psf);
        assert!((fit.a - truth.a).abs() < 1e-10);
        assert!((fit.b - truth.b).abs() < 1e-10);
        assert!((fit.c - truth.c).abs() < 1e-10);
        assert!((fit.major - truth.major).abs() < 1e-8 && fit.major > fit.minor);
        assert!((fit.pa - truth.pa).abs() < 1e-8);
        // A beam elongated along +Y (north) has PA 0; along X, ±90°.
        let north = RestoringBeam::from_quadratic(0.1, 0.0, 0.01, 0);
        assert!(north.pa.abs() < 1e-12);
        let east = RestoringBeam::from_quadratic(0.01, 0.0, 0.1, 0);
        assert!((east.pa.abs() - std::f64::consts::FRAC_PI_2).abs() < 1e-12);
        // Elongated towards −X when going +Y (north-east): positive PA.
        let ne = RestoringBeam::from_quadratic(0.05, 0.08, 0.05, 0);
        assert!(
            (ne.pa - std::f64::consts::FRAC_PI_4).abs() < 1e-12,
            "{}",
            ne.pa
        );
        // Restoring a point gives the flux at its pixel.
        let mut model = vec![0.0; n * n];
        model[7 * n + 30] = 2.5;
        let restored = restore(n, &model, &vec![0.0; n * n], &fit);
        assert!((restored[7 * n + 30] - 2.5).abs() < 1e-10);
    }

    /// A source east and north of the phase centre, with visibilities of the
    /// MS's positive Fourier phase `exp(+2πi (u l + v m + w (n − 1)))` (as
    /// `predict.rs` states), lands where the FITS WCS puts it: `CDELT1 < 0`
    /// means east is towards smaller FITS `x`.
    #[test]
    fn flips_put_a_source_where_the_wcs_says() {
        use crate::clean_certified::WgridMeasurement;
        use crate::wgridder::Options;
        let mut rng = Rng(99);
        let (n, cell) = (64usize, 1.0e-4);
        let (dx, dy) = (10.0, 5.0);
        let (l, m) = (dx * cell, dy * cell);
        let nn = (1.0f64 - l * l - m * m).sqrt();
        let mut uvw = Vec::new();
        let mut vis = Vec::new();
        for _ in 0..4000 {
            let (u, v, w) = (
                (rng.next() - 0.5) * 8000.0,
                (rng.next() - 0.5) * 8000.0,
                (rng.next() - 0.5) * 2000.0,
            );
            uvw.extend_from_slice(&[u, v, w]);
            let phase = 2.0 * std::f64::consts::PI * (u * l + v * m + w * (nn - 1.0));
            vis.push(Complex::new(phase.cos(), phase.sin()));
        }
        let opts = Options {
            flip_v: true,
            flip_w: true,
            ..Options::default()
        };
        let wgt = vec![1.0; 4000];
        let meas =
            WgridMeasurement::new(uvw, vec![299_792_458.0], vis, wgt, n, cell, 1e-9, opts).unwrap();
        let (dirty, _) = meas.residual(&vec![0.0; n * n]).unwrap();
        let fits_image = fits::gridder_to_fits(n, &dirty);
        let (p, value) = clean::argmax_abs(&fits_image);
        let (x, y) = (p % n, p / n);
        assert!(value > 0.9, "peak {value}");
        assert_eq!((x, y), (n / 2 - 10, n / 2 + 5));
    }

    #[test]
    fn mad_sigma_of_a_known_sample() {
        let x: Vec<f64> = (0..101).map(|i| i as f64).collect();
        // median 50, deviations 0..50 with median 25.
        assert!((mad_sigma(&x) - 1.4826 * 25.0).abs() < 1e-12);
    }
}
