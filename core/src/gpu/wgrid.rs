// SPDX-License-Identifier: GPL-3.0-or-later
//! The exact w-gridder's major-cycle calls on the GPU (issue #12,
//! `research/gpu-grid.md`): gridding and degridding of a [`Prepared`] plan
//! through wgpu, behind the cargo feature `gpu`.
//!
//! A child module of `wgridder` (included there with `#[path]`), so it reads
//! the CPU plan, layout and tables directly and leaves the CPU code as it is.
//! The host does what the CPU path does before and after its plane loop (the
//! stored values, the corrected image, the global corrections, the final
//! phase and weight of each visibility) with the CPU's own functions or a
//! copy of their loops; the GPU does the plane loop:
//!
//! - **gridding** by gather, without atomics: one workgroup per 16 × 16 tile
//!   of shifted grid cells, one invocation per cell. The visibilities whose
//!   first tap lies in a tile that can reach the cell, on a plane active
//!   there, are read in chunks into workgroup memory, each evaluating its
//!   taps once (the CPU's even/odd Horner polynomials, `fma` as `mul_add`);
//!   every invocation then adds the products for its cell in a fixed order,
//!   so the result does not depend on scheduling;
//! - the backward 2-D FFT (X2's Stockham passes, `gpu::fft`);
//! - the projection `Re(grid · screen)` added to the image, the w-screen
//!   formed per pixel from the CPU's screen table;
//! - **degridding**: the corrected image times the screen on the zeroed grid,
//!   the forward FFT (conjugate twiddles), then one invocation per
//!   visibility adding its taps, planes in ascending order.
//!
//! Visibilities go to the device in batches under a memory budget, in the
//! order (first plane, tile, CPU sorted order). A plane touched by several
//! batches is gridded, transformed and projected once per batch: the terms
//! add, as gridding, the transform and the projection are linear.
//!
//! The coordinates and the screen's phase are formed in f64 in both
//! precisions, as on the CPU (so `SHADER_F64` is required); the f32 screen
//! takes the f64 `sincos` of the f32-rounded angle, then rounds.

use super::*;
use crate::gpu::context::{self, Context};
use crate::gpu::invert::{bytes_of, fft_passes, storage, uniform, wait};
use crate::gpu::{Precision, fft};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Instant;

/// Default device-memory budget of this path, MiB (GeMClean's `-gpu-memory` sets it).
pub const DEFAULT_BUDGET_MIB: usize = 1024;

/// Side of the gather's output tiles (shifted grid cells).
const TILE: usize = 16;
/// Largest support the shaders hold (the private and workgroup tap arrays).
const SMAX: usize = 16;
/// Offset of the packed first taps (`iu0 + OFF` in 16 bits).
const OFF: i64 = 32;
/// Most source ranges of one output tile: three tile rows, three tile
/// columns, `SMAX` planes.
const MAX_RANGES: usize = 3 * 3 * SMAX;
const MAX_WORKGROUPS: u32 = 65535;

/// What the GPU path did in this process (for the log and the report).
#[derive(Clone, Copy, Debug, Default)]
pub struct Stats {
    pub grid_calls: usize,
    pub degrid_calls: usize,
    /// Host: values, permutations, corrections, packing (seconds).
    pub host_s: f64,
    pub upload_s: f64,
    /// Dispatches submitted and waited for.
    pub compute_s: f64,
    pub download_s: f64,
    /// Plane passes (gather or degrid, FFT, projection or placement).
    pub plane_passes: usize,
    pub batches: usize,
    /// Largest device allocation of one plan, bytes.
    pub device_bytes: u64,
    /// Host time making the GPU order of the plans.
    pub setup_s: f64,
}

static STATS: Mutex<Stats> = Mutex::new(Stats {
    grid_calls: 0,
    degrid_calls: 0,
    host_s: 0.0,
    upload_s: 0.0,
    compute_s: 0.0,
    download_s: 0.0,
    plane_passes: 0,
    batches: 0,
    device_bytes: 0,
    setup_s: 0.0,
});

/// The process's GPU statistics so far.
pub fn stats() -> Stats {
    *STATS.lock().unwrap_or_else(|e| e.into_inner())
}

fn add_stats(f: impl FnOnce(&mut Stats)) {
    f(&mut STATS.lock().unwrap_or_else(|e| e.into_inner()));
}

/// One line naming the adapter (for the log).
pub fn adapter() -> Result<String, String> {
    crate::gpu::adapter_description()
}

// ------------------------------------------------------------------ shaders

const WGSL: &str = r#"
alias real = REAL_TYPE;
alias cplx = vec2<real>;
const CH: u32 = CHUNK_SIZEu;
const SMAX: u32 = 16u;
const MAXR: u32 = MAX_RANGESu;

struct Params {
    nu: u32, nv: u32, nx: u32, ny: u32,
    supp: u32, ne: u32, ntu: u32, ntv: u32,
    nplanes: u32, plane: u32, bstart: u32, bend: u32,
    nchan: u32, lmshift: u32, dow: u32, tny: u32,
    fc_off: u32, rows_off: u32, table_off: u32, ntiles: u32,
    mlo: u32, mhi: u32, row_threads: u32, off: u32,
}

@group(0) @binding(0) var<uniform> p: Params;
// [0] pixsize_x, [1] pixsize_y, [2] wmin, [3] dw, [4] xdw; then 1/c per
// channel (fc_off), four per row (fixed u, v, w and the FixW sign, rows_off),
// the screen table (table_off).
@group(0) @binding(1) var<storage, read> geo: array<f64>;
@group(0) @binding(2) var<storage, read> coeff: array<real>;

fn taps_all(x: real, out: ptr<function, array<real, 16>>) {
    let s = p.supp;
    let ne = p.ne;
    let h = (s + 1u) / 2u;
    let x2 = x * x;
    for (var i = 0u; i < h; i++) {
        var e = coeff[i];
        var o = coeff[ne * s + i];
        for (var k = 1u; k < ne; k++) {
            e = fma(e, x2, coeff[k * s + i]);
            o = fma(o, x2, coeff[(ne + k) * s + i]);
        }
        (*out)[i] = fma(o, x, e);
        if (i < s - h) {
            (*out)[s - 1u - i] = fma(o, -x, e);
        }
    }
}

fn tap_one(i0: u32, x0: real) -> real {
    let s = p.supp;
    let ne = p.ne;
    let h = (s + 1u) / 2u;
    var i = i0;
    var x = x0;
    if (i0 >= h) {
        i = s - 1u - i0;
        x = -x0;
    }
    let x2 = x * x;
    var e = coeff[i];
    var o = coeff[ne * s + i];
    for (var k = 1u; k < ne; k++) {
        e = fma(e, x2, coeff[k * s + i]);
        o = fma(o, x2, coeff[(ne + k) * s + i]);
    }
    return fma(o, x, e);
}

struct Geo {
    x: real,
    y: real,
    w: f64,
    imflip: f64,
    iu0: i32,
    iv0: i32,
}

// The u and v kernel arguments of visibility `li` of the batch (getpix with
// the host's first taps) and its w and FixW sign.
fn vis_geo(idx: u32, pos: u32) -> Geo {
    let row = idx / p.nchan;
    let ch = idx - row * p.nchan;
    let f = geo[p.fc_off + ch];
    let r = p.rows_off + 4u * row;
    let u = geo[r] * f;
    let v = geo[r + 1u] * f;
    let w = geo[r + 2u] * f;
    var g: Geo;
    g.w = w;
    g.imflip = geo[r + 3u];
    g.iu0 = i32(pos & 0xffffu) - i32(p.off);
    g.iv0 = i32(pos >> 16u) - i32(p.off);
    var uu = u * geo[0];
    uu = (uu - floor(uu)) * f64(p.nu);
    let ufrac = uu - f64(g.iu0);
    var vv = v * geo[1];
    vv = (vv - floor(vv)) * f64(p.nv);
    let vfrac = vv - f64(g.iv0);
    let sm1 = f64(p.supp) - f64(1.0);
    g.x = real(-ufrac * f64(2.0) + sm1);
    g.y = real(-vfrac * f64(2.0) + sm1);
    return g;
}

// The w factor of a visibility at `w` on plane `p.plane` (tap plane - m).
fn w_factor(m: u32, w: f64) -> real {
    let w0 = geo[2] + f64(p.plane) * geo[3];
    let z = real(geo[4] * (w0 - w));
    let nth = p.plane - m;
    let locz = (z - real(nth)) * real(2.0) + real(f64(p.supp) - f64(1.0));
    return tap_one(nth, locz);
}

// sin and cos of an f64 angle (X2's Cody-Waite reduction and fdlibm's
// polynomials), as (sin, cos).
fn sincos64(x: f64) -> vec2<f64> {
    let n = round(x * f64(6.36619772367581382433e-01));
    let r = (x - n * f64(1.57079632673412561417e+00)) - n * f64(6.07710050650619224932e-11);
    let z = r * r;
    let s = r + r * z * (f64(-1.66666666666666324348e-01) + z * (f64(8.33333333332248946124e-03)
        + z * (f64(-1.98412698298579493134e-04) + z * (f64(2.75573137070700676789e-06)
        + z * (f64(-2.50507602534068634195e-08) + z * f64(1.58969099521155010221e-10))))));
    let c = f64(1.0) - f64(0.5) * z + z * z * (f64(4.16666666666666019037e-02)
        + z * (f64(-1.38888888888741095749e-03) + z * (f64(2.48015872894767294178e-05)
        + z * (f64(-2.75573143513906633035e-07) + z * (f64(2.08757232129817482790e-09)
        + z * f64(-1.13596475577881948265e-11))))));
    let q = i32(n) & 3;
    if (q == 0) {
        return vec2<f64>(s, c);
    }
    if (q == 1) {
        return vec2<f64>(c, -s);
    }
    if (q == 2) {
        return vec2<f64>(-s, -c);
    }
    return vec2<f64>(-c, s);
}

PHASE_FN

fn table_index(i: u32, j: u32) -> u32 {
    if (p.lmshift == 1u) {
        return i * p.tny + j;
    }
    return min(i, p.nx - i) * p.tny + min(j, p.ny - j);
}

// The w-screen of pixel (i, j) on this plane (screen_par), (cos, sin).
fn screen(i: u32, j: u32, adjoint: bool) -> cplx {
    let w0 = geo[2] + f64(p.plane) * geo[3];
    var phs = w0 * geo[p.table_off + table_index(i, j)];
    if (adjoint) {
        phs = phs * f64(-1.0);
    }
    return phase(phs);
}
"#;

const PHASE_F64: &str = r#"
fn phase(phs: f64) -> cplx {
    let s = sincos64(f64(6.283185307179586) * phs);
    return cplx(s.y, s.x);
}
"#;

const PHASE_F32: &str = r#"
fn phase(phs: f64) -> cplx {
    let a = f32(f64(6.283185307179586) * (phs - floor(phs)));
    let s = sincos64(f64(a));
    return cplx(f32(s.y), f32(s.x));
}
"#;

const GRID: &str = r#"
@group(0) @binding(3) var<storage, read> offs: array<u32>;
// Two words per visibility of the batch: row * nchan + channel, and the
// first taps (iu0 + off) | (iv0 + off) << 16.
@group(0) @binding(4) var<storage, read> vis: array<u32>;
@group(0) @binding(5) var<storage, read> vval: array<cplx>;
@group(0) @binding(6) var<storage, read_write> grid: array<cplx>;

var<workgroup> wku: array<real, CHUNK_TAPS>;
var<workgroup> wkv: array<real, CHUNK_TAPS>;
var<workgroup> wval: array<cplx, CH>;
var<workgroup> wsu: array<u32, CH>;
var<workgroup> wsv: array<u32, CH>;
var<workgroup> rstart: array<u32, MAXR>;
var<workgroup> rm: array<u32, MAXR>;
var<workgroup> rpre: array<u32, MAXR_PLUS>;
var<workgroup> nranges: u32;
var<workgroup> total: u32;

@compute @workgroup_size(16, 16, 1)
fn grid_tile(
    @builtin(local_invocation_id) lid: vec3<u32>,
    @builtin(local_invocation_index) li: u32,
    @builtin(workgroup_id) wid: vec3<u32>,
) {
    let tu = wid.y;
    let tv = wid.x;
    let rs = tu * 16u + lid.y;
    let cs = tv * 16u + lid.x;
    let s = p.supp;
    if (li == 0u) {
        // The runs of (plane, tile) that can reach this tile on this plane,
        // clipped to the batch: source tile rows from the one holding
        // (tu * 16 - s + 1) mod nu up to tu, likewise for columns, planes
        // max(plane - s + 1, mlo) ..= min(plane, mhi).
        let su0 = ((tu * 16u + p.nu - (s - 1u)) % p.nu) / 16u;
        let sv0 = ((tv * 16u + p.nv - (s - 1u)) % p.nv) / 16u;
        var mlo = p.mlo;
        if (p.plane + 1u > s) {
            mlo = max(mlo, p.plane + 1u - s);
        }
        let mhi = min(p.mhi, p.plane);
        var n = 0u;
        var acc = 0u;
        var a = su0;
        loop {
            var b = sv0;
            loop {
                let t = a * p.ntv + b;
                for (var m = mlo; m <= mhi; m++) {
                    let lo = max(offs[m * p.ntiles + t], p.bstart);
                    let hi = min(offs[m * p.ntiles + t + 1u], p.bend);
                    if (hi > lo) {
                        rstart[n] = lo;
                        rm[n] = m;
                        rpre[n] = acc;
                        acc += hi - lo;
                        n++;
                    }
                }
                if (b == tv) {
                    break;
                }
                b = (b + 1u) % p.ntv;
            }
            if (a == tu) {
                break;
            }
            a = (a + 1u) % p.ntu;
        }
        rpre[n] = acc;
        nranges = n;
        total = acc;
    }
    let tot = workgroupUniformLoad(&total);
    let nr = workgroupUniformLoad(&nranges);
    var are = real(0.0);
    var aim = real(0.0);
    let inside = rs < p.nu && cs < p.nv;
    for (var base = 0u; base < tot; base += CH) {
        if (li < CH && base + li < tot) {
            let q = base + li;
            var lo = 0u;
            var hi = nr;
            while (hi - lo > 1u) {
                let mid = (lo + hi) / 2u;
                if (rpre[mid] <= q) {
                    lo = mid;
                } else {
                    hi = mid;
                }
            }
            let g = rstart[lo] + (q - rpre[lo]);
            let m = rm[lo];
            let k = g - p.bstart;
            let gg = vis_geo(vis[2u * k], vis[2u * k + 1u]);
            var ku: array<real, 16>;
            var kv: array<real, 16>;
            taps_all(gg.x, &ku);
            taps_all(gg.y, &kv);
            if (p.dow == 1u) {
                let kw = w_factor(m, gg.w);
                for (var i = 0u; i < s; i++) {
                    ku[i] = ku[i] * kw;
                }
            }
            for (var i = 0u; i < s; i++) {
                wku[li * SMAX + i] = ku[i];
                wkv[li * SMAX + i] = kv[i];
            }
            wval[li] = vval[k];
            wsu[li] = u32((gg.iu0 + i32(p.nu) + i32(p.nu / 2u)) % i32(p.nu));
            wsv[li] = u32((gg.iv0 + i32(p.nv) + i32(p.nv / 2u)) % i32(p.nv));
        }
        workgroupBarrier();
        let cnt = min(CH, tot - base);
        if (inside) {
            for (var j = 0u; j < cnt; j++) {
                var du = i32(rs) - i32(wsu[j]);
                if (du < 0) {
                    du += i32(p.nu);
                }
                var dv = i32(cs) - i32(wsv[j]);
                if (dv < 0) {
                    dv += i32(p.nv);
                }
                if (u32(du) < s && u32(dv) < s) {
                    let kuc = wku[j * SMAX + u32(du)];
                    let kvc = wkv[j * SMAX + u32(dv)];
                    let val = wval[j];
                    are = fma(val.x * kuc, kvc, are);
                    aim = fma(val.y * kuc, kvc, aim);
                }
            }
        }
        workgroupBarrier();
    }
    if (inside) {
        let gr = (rs + p.nu / 2u) % p.nu;
        let gc = (cs + p.nv / 2u) % p.nv;
        grid[gr * p.nv + gc] = cplx(are, aim);
    }
}
"#;

const PROJECT: &str = r#"
@group(0) @binding(3) var<storage, read> gridr: array<cplx>;
@group(0) @binding(4) var<storage, read_write> image: array<real>;

// grid_to_image: pixel (i, j) adds Re(grid(rows[i], cols[j]) * screen).
@compute @workgroup_size(16, 16, 1)
fn project(@builtin(global_invocation_id) id: vec3<u32>) {
    let j = id.x;
    let i = id.y;
    if (i >= p.nx || j >= p.ny) {
        return;
    }
    let gr = (p.nu - p.nx / 2u + i) % p.nu;
    let gc = (p.nv - p.ny / 2u + j) % p.nv;
    let g = gridr[gr * p.nv + gc];
    var term = g.x;
    if (p.dow == 1u) {
        let ph = screen(i, j, true);
        term = g.x * ph.x - g.y * ph.y;
    }
    let at = i * p.ny + j;
    image[at] = image[at] + term;
}
"#;

const PLACE: &str = r#"
@group(0) @binding(3) var<storage, read> imagein: array<real>;
@group(0) @binding(4) var<storage, read_write> gridw: array<cplx>;

// image_to_grid before its transforms: the corrected image times the screen
// at its cells, zero elsewhere.
@compute @workgroup_size(16, 16, 1)
fn place(@builtin(global_invocation_id) id: vec3<u32>) {
    let c = id.x;
    let r = id.y;
    if (r >= p.nu || c >= p.nv) {
        return;
    }
    let i = (r + p.nx / 2u) % p.nu;
    let j = (c + p.ny / 2u) % p.nv;
    var val = cplx(real(0.0), real(0.0));
    if (i < p.nx && j < p.ny) {
        let d = imagein[i * p.ny + j];
        if (p.dow == 1u) {
            let ph = screen(i, j, false);
            val = cplx(d * ph.x, d * ph.y);
        } else {
            val = cplx(d, real(0.0));
        }
    }
    gridw[r * p.nv + c] = val;
}
"#;

const DEGRID: &str = r#"
@group(0) @binding(3) var<storage, read> offs: array<u32>;
@group(0) @binding(4) var<storage, read> vis: array<u32>;
@group(0) @binding(5) var<storage, read_write> acc: array<cplx>;
@group(0) @binding(6) var<storage, read> gridr: array<cplx>;

// degrid_task_body for one visibility of the batch on this plane.
@compute @workgroup_size(64, 1, 1)
fn degrid(@builtin(global_invocation_id) id: vec3<u32>) {
    let k = id.x + id.y * p.row_threads;
    let g = p.bstart + k;
    if (g >= p.bend) {
        return;
    }
    // Its first plane: the last slice starting at or before g.
    var lo = p.mlo;
    var hi = p.mhi + 1u;
    while (hi - lo > 1u) {
        let mid = (lo + hi) / 2u;
        if (offs[mid * p.ntiles] <= g) {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    let m = lo;
    let s = p.supp;
    if (p.plane < m || p.plane >= m + s) {
        return;
    }
    let gg = vis_geo(vis[2u * k], vis[2u * k + 1u]);
    var ku: array<real, 16>;
    var kv: array<real, 16>;
    taps_all(gg.x, &ku);
    taps_all(gg.y, &kv);
    if (p.dow == 1u) {
        let kw = w_factor(m, gg.w);
        for (var i = 0u; i < s; i++) {
            ku[i] = ku[i] * kw;
        }
    }
    var rr = real(0.0);
    var ri = real(0.0);
    for (var cu = 0u; cu < s; cu++) {
        let row = u32((gg.iu0 + i32(cu) + i32(p.nu)) % i32(p.nu));
        var tr = real(0.0);
        var ti = real(0.0);
        for (var cv = 0u; cv < s; cv++) {
            let col = u32((gg.iv0 + i32(cv) + i32(p.nv)) % i32(p.nv));
            let v = gridr[row * p.nv + col];
            tr = fma(kv[cv], v.x, tr);
            ti = fma(kv[cv], v.y, ti);
        }
        rr = fma(ku[cu], tr, rr);
        ri = fma(ku[cu], ti, ri);
    }
    acc[k] = cplx(rr, ri * real(gg.imflip)) + acc[k];
}
"#;

/// Visibilities per gather chunk: as many as fit the workgroup memory, at
/// most one per invocation.
fn chunk_size(precision: Precision, limit: u32) -> usize {
    let real = precision.bytes();
    for ch in [256usize, 128, 64, 32] {
        let bytes = ch * (2 * SMAX * real + 2 * real + 8) + (3 * MAX_RANGES + 3) * 4;
        if bytes <= limit as usize {
            return ch;
        }
    }
    16
}

fn sources(precision: Precision, chunk: usize) -> [String; 4] {
    let (real, phase) = match precision {
        Precision::F64 => ("f64", PHASE_F64),
        Precision::F32 => ("f32", PHASE_F32),
    };
    let common = WGSL
        .replace("REAL_TYPE", real)
        .replace("CHUNK_SIZE", &chunk.to_string())
        .replace("MAX_RANGES", &MAX_RANGES.to_string())
        .replace("PHASE_FN", phase);
    let grid = GRID
        .replace("CHUNK_TAPS", &(chunk * SMAX).to_string())
        .replace("MAXR_PLUS", &(MAX_RANGES + 1).to_string());
    [
        format!("{common}{grid}"),
        format!("{common}{PROJECT}"),
        format!("{common}{PLACE}"),
        format!("{common}{DEGRID}"),
    ]
}

struct Pipes {
    grid: wgpu::ComputePipeline,
    project: wgpu::ComputePipeline,
    place: wgpu::ComputePipeline,
    degrid: wgpu::ComputePipeline,
    /// X2's pipelines, for its FFT pass.
    x2: Arc<context::Pipelines>,
}

/// The FFT passes' bind groups and workgroup counts.
type FftBinds = Vec<(wgpu::BindGroup, (u32, u32))>;

/// A bind group of explicit binding numbers (an entry point's automatic
/// layout holds only the bindings it uses).
fn bind(
    ctx: &Context,
    pipeline: &wgpu::ComputePipeline,
    buffers: &[(u32, &wgpu::Buffer)],
) -> wgpu::BindGroup {
    let entries: Vec<wgpu::BindGroupEntry> = buffers
        .iter()
        .map(|(i, b)| wgpu::BindGroupEntry {
            binding: *i,
            resource: b.as_entire_binding(),
        })
        .collect();
    ctx.device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: None,
        layout: &pipeline.get_bind_group_layout(0),
        entries: &entries,
    })
}

/// Bindings 0, 1, 2, ... in order.
fn seq<'a>(buffers: &[&'a wgpu::Buffer]) -> Vec<(u32, &'a wgpu::Buffer)> {
    buffers
        .iter()
        .enumerate()
        .map(|(i, b)| (i as u32, *b))
        .collect()
}

static PIPES: OnceLock<Mutex<[Option<Arc<Pipes>>; 2]>> = OnceLock::new();

fn pipes(ctx: &Context, precision: Precision) -> Result<Arc<Pipes>, String> {
    if !ctx.f64 {
        return Err(format!(
            "the adapter {} ({:?}) has no SHADER_F64, which the GPU gridder needs",
            ctx.info.name, ctx.info.backend
        ));
    }
    let slot = usize::from(precision == Precision::F32);
    let cache = PIPES.get_or_init(|| Mutex::new([None, None]));
    let mut cache = cache.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(p) = &cache[slot] {
        return Ok(p.clone());
    }
    let (x2, _) = ctx.pipelines(precision)?;
    let chunk = chunk_size(precision, ctx.limits.max_compute_workgroup_storage_size);
    let [g, pr, pl, dg] = sources(precision, chunk);
    let make = |label: &str, source: &str, entry: &str| {
        let module = ctx
            .device
            .create_shader_module(wgpu::ShaderModuleDescriptor {
                label: Some(label),
                source: wgpu::ShaderSource::Wgsl(source.into()),
            });
        ctx.device
            .create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
                label: Some(label),
                layout: None,
                module: &module,
                entry_point: Some(entry),
                compilation_options: Default::default(),
                cache: None,
            })
    };
    let scope = ctx.device.push_error_scope(wgpu::ErrorFilter::Validation);
    let p = Pipes {
        grid: make("wgrid gather", &g, "grid_tile"),
        project: make("wgrid project", &pr, "project"),
        place: make("wgrid place", &pl, "place"),
        degrid: make("wgrid degrid", &dg, "degrid"),
        x2,
    };
    if let Some(error) = pollster::block_on(scope.pop()) {
        return Err(format!(
            "compiling the {precision:?} gridder shaders: {error}"
        ));
    }
    let p = Arc::new(p);
    cache[slot] = Some(p.clone());
    Ok(p)
}

// ------------------------------------------------------------- the GPU plan

/// The GPU order of a plan's active visibilities and the device buffers of
/// its calls.
pub(super) struct Gpu {
    precision: Precision,
    /// CPU sorted index of each visibility in the GPU order.
    perm: Vec<u32>,
    /// Start of every (first plane, tile) run in the GPU order, plane-major,
    /// and the total at the end.
    offs: Vec<u32>,
    nplanes: usize,
    ntu: usize,
    ntv: usize,
    fc_off: usize,
    rows_off: usize,
    table_off: usize,
    /// pixsize, w-plane constants, 1/c per channel, rows, the screen table.
    geo: Vec<f64>,
    coeff: Vec<f64>,
    /// Visibilities per batch.
    per_batch: usize,
    buffers: Mutex<Option<Buffers>>,
}

struct Buffers {
    geo: wgpu::Buffer,
    coeff: wgpu::Buffer,
    offs: wgpu::Buffer,
    tw_inv: [wgpu::Buffer; 2],
    tw_fwd: [wgpu::Buffer; 2],
    grid_a: wgpu::Buffer,
    grid_b: wgpu::Buffer,
    image: wgpu::Buffer,
    vis: wgpu::Buffer,
    vals: wgpu::Buffer,
    staging: wgpu::Buffer,
}

fn cbytes<T: Real>(v: &[Complex<T>]) -> &[u8] {
    // SAFETY: Complex<f32> and Complex<f64> are repr(C) pairs of plain floats.
    unsafe { std::slice::from_raw_parts(v.as_ptr().cast::<u8>(), std::mem::size_of_val(v)) }
}

fn tbytes<T: Real>(v: &[T]) -> &[u8] {
    // SAFETY: T is f32 or f64.
    unsafe { std::slice::from_raw_parts(v.as_ptr().cast::<u8>(), std::mem::size_of_val(v)) }
}

fn reals_of(values: &[f64], precision: Precision) -> Vec<u8> {
    crate::gpu::invert::reals(values, precision)
}

fn precision_of<T: Real>() -> Precision {
    if T::SINGLE {
        Precision::F32
    } else {
        Precision::F64
    }
}

impl Gpu {
    /// The GPU order of a prepared plan (host work, once per plan), checking
    /// that the device can run it within `budget_mib`.
    pub(super) fn new<T: Real>(
        setup: &Setup,
        bl: &Baselines,
        lay: &Layout,
        tables: &Tables<T>,
        budget_mib: usize,
    ) -> Result<Gpu, String> {
        let start = Instant::now();
        let precision = precision_of::<T>();
        let (ctx, _) = context::get()?;
        let _ = pipes(&ctx, precision)?;
        let (nu, nv) = (setup.nu, setup.nv);
        if setup.supp > SMAX {
            return Err(format!("kernel support {} above {SMAX}", setup.supp));
        }
        if nu as i64 + 2 * OFF >= 1 << 16 || nv as i64 + 2 * OFF >= 1 << 16 {
            return Err(format!("grid {nu} x {nv} too large for the GPU gridder"));
        }
        for n in [nu, nv] {
            if fft::plan(n).is_none() {
                return Err(format!(
                    "grid side {n} has a prime factor above {}",
                    fft::MAX_RADIX
                ));
            }
        }
        let nact = lay.refs.len();
        let nchan = bl.f_over_c.len();
        if nact >= u32::MAX as usize || bl.coord.len() * nchan >= u32::MAX as usize {
            return Err("too many visibilities for 32-bit GPU indices".into());
        }
        let ntu = nu.div_ceil(TILE);
        let ntv = nv.div_ceil(TILE);
        let ntiles = ntu * ntv;
        let nplanes = setup.nplanes.max(1);
        let nkeys = nplanes * ntiles;
        if nkeys >= u32::MAX as usize {
            return Err("too many planes and tiles for the GPU gridder".into());
        }
        // Key of each active visibility in the CPU sorted order: first plane,
        // then the tile of its shifted first tap (the CPU's getpix, minplane).
        let keys: Vec<u32> = lay
            .refs
            .par_iter()
            .map(|&r| {
                let ([u, v, w], _) = uvw_of(bl, r);
                let (_, _, iu0, iv0) = setup.getpix(u, v);
                let su = shifted(iu0, nu) / TILE;
                let sv = shifted(iv0, nv) / TILE;
                let m = setup.minplane(w).min(nplanes - 1);
                (m * ntiles + su * ntv + sv) as u32
            })
            .collect();
        let mut offs = vec![0u32; nkeys + 1];
        for &k in &keys {
            offs[k as usize + 1] += 1;
        }
        for i in 0..nkeys {
            offs[i + 1] += offs[i];
        }
        let mut next = offs.clone();
        let mut perm = vec![0u32; nact];
        for (k, &key) in keys.iter().enumerate() {
            let at = &mut next[key as usize];
            perm[*at as usize] = k as u32;
            *at += 1;
        }
        drop(next);
        drop(keys);
        // The geometry the shaders read in f64.
        let fc_off = 8;
        let rows_off = fc_off + nchan;
        let table_off = rows_off + 4 * bl.coord.len();
        let mut geo = vec![0.0; table_off + tables.table.len()];
        geo[0] = setup.pixsize_x;
        geo[1] = setup.pixsize_y;
        geo[2] = setup.wmin;
        geo[3] = setup.dw;
        geo[4] = setup.xdw;
        geo[fc_off..rows_off].copy_from_slice(&bl.f_over_c);
        for (row, c) in bl.coord.iter().enumerate() {
            let (f, imflip) = fix_w(*c);
            geo[rows_off + 4 * row..rows_off + 4 * row + 4]
                .copy_from_slice(&[f[0], f[1], f[2], imflip]);
        }
        geo[table_off..].copy_from_slice(&tables.table);
        let coeff: Vec<f64> = tables.coeff.iter().map(|c| c.to()).collect();
        // Batch size under the budget.
        let real = precision.bytes();
        let budget = budget_mib << 20;
        let grids = 2 * nu * nv * 2 * real;
        let fixed = grids
            + setup.nx * setup.ny * real
            + geo.len() * 8
            + offs.len() * 4
            + 4 * (nu + nv) * 2 * real
            + coeff.len() * real;
        let binding = ctx.limits.max_storage_buffer_binding_size as usize;
        if nu * nv * 2 * real > binding {
            return Err(format!(
                "a {nu} x {nv} grid exceeds the adapter's storage binding size"
            ));
        }
        if fixed + (1 << 20) > budget {
            return Err(format!(
                "the grids and tables need {} MiB, over the GPU budget of {budget_mib} MiB",
                fixed.div_ceil(1 << 20)
            ));
        }
        let per_vis = 8 + 2 * real + 2 * real; // words, values, staging
        let per_batch = ((budget - fixed) / per_vis)
            .min(binding / (2 * real))
            .min(nact.max(1))
            .max(1);
        add_stats(|s| s.setup_s += start.elapsed().as_secs_f64());
        Ok(Gpu {
            precision,
            perm,
            offs,
            nplanes,
            ntu,
            ntv,
            fc_off,
            rows_off,
            table_off,
            geo,
            coeff,
            per_batch,
            buffers: Mutex::new(None),
        })
    }

    /// Host bytes held (for the memory report).
    pub(super) fn memory(&self) -> usize {
        self.perm.capacity() * 4 + self.offs.capacity() * 4 + self.geo.capacity() * 8
    }

    /// Free the device buffers (the next call allocates them again).
    pub(super) fn release(&self) {
        *self.buffers.lock().unwrap_or_else(|e| e.into_inner()) = None;
    }

    fn buffers<'a>(
        &self,
        ctx: &Context,
        setup: &Setup,
        guard: &'a mut Option<Buffers>,
    ) -> &'a Buffers {
        if guard.is_none() {
            let up = Instant::now();
            let p = self.precision;
            let real = p.bytes();
            let init = |label: &str, contents: &[u8]| {
                use wgpu::util::DeviceExt;
                ctx.device
                    .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                        label: Some(label),
                        contents,
                        usage: wgpu::BufferUsages::STORAGE,
                    })
            };
            let tw = |n: usize, conj: bool| {
                let t: Vec<f64> = fft::twiddles(n)
                    .into_iter()
                    .flat_map(|[re, im]| [re, if conj { -im } else { im }])
                    .collect();
                init("twiddles", &reals_of(&t, p))
            };
            let (nu, nv) = (setup.nu, setup.nv);
            let grid_bytes = nu * nv * 2 * real;
            let copy = wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::COPY_SRC;
            let b = self.per_batch;
            let staging = (setup.nx * setup.ny * real).max(b * 2 * real);
            let bufs = Buffers {
                geo: init("geo", bytes_of(&self.geo)),
                coeff: init("coeff", &reals_of(&self.coeff, p)),
                offs: init("offs", bytes_of(&self.offs)),
                // Rows have length nv (the contiguous axis), columns nu.
                tw_inv: [tw(nv, false), tw(nu, false)],
                tw_fwd: [tw(nv, true), tw(nu, true)],
                grid_a: storage(ctx, "grid a", grid_bytes, wgpu::BufferUsages::empty()),
                grid_b: storage(ctx, "grid b", grid_bytes, wgpu::BufferUsages::empty()),
                image: storage(ctx, "image", setup.nx * setup.ny * real, copy),
                vis: storage(ctx, "vis", b * 8, wgpu::BufferUsages::COPY_DST),
                vals: storage(ctx, "vals", b * 2 * real, copy),
                staging: ctx.device.create_buffer(&wgpu::BufferDescriptor {
                    label: Some("staging"),
                    size: staging.next_multiple_of(8) as u64,
                    usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
                    mapped_at_creation: false,
                }),
            };
            let bytes = [
                &bufs.geo,
                &bufs.coeff,
                &bufs.offs,
                &bufs.tw_inv[0],
                &bufs.tw_inv[1],
                &bufs.tw_fwd[0],
                &bufs.tw_fwd[1],
                &bufs.grid_a,
                &bufs.grid_b,
                &bufs.image,
                &bufs.vis,
                &bufs.vals,
                &bufs.staging,
            ]
            .iter()
            .map(|b| b.size())
            .sum();
            *guard = Some(bufs);
            add_stats(|s| {
                s.upload_s += up.elapsed().as_secs_f64();
                s.device_bytes = s.device_bytes.max(bytes);
            });
        }
        guard.as_ref().expect("allocated above")
    }

    /// Uniform words of one plane pass of batch `[b0, b1)`.
    #[allow(clippy::too_many_arguments)]
    fn params(
        &self,
        setup: &Setup,
        plane: usize,
        b0: usize,
        b1: usize,
        mlo: usize,
        mhi: usize,
        row_threads: u32,
    ) -> [u32; 24] {
        let (_, tny) = setup.table_dims();
        [
            setup.nu as u32,
            setup.nv as u32,
            setup.nx as u32,
            setup.ny as u32,
            setup.supp as u32,
            (self.coeff.len() / (2 * setup.supp)) as u32,
            self.ntu as u32,
            self.ntv as u32,
            self.nplanes as u32,
            plane as u32,
            b0 as u32,
            b1 as u32,
            (self.fc_off..self.rows_off).len() as u32,
            u32::from(setup.lmshift),
            u32::from(setup.do_wgridding),
            tny as u32,
            self.fc_off as u32,
            self.rows_off as u32,
            self.table_off as u32,
            (self.ntu * self.ntv) as u32,
            mlo as u32,
            mhi as u32,
            row_threads,
            OFF as u32,
        ]
    }

    /// First plane of GPU-order visibility `g`.
    fn plane_of(&self, g: usize) -> usize {
        let ntiles = self.ntu * self.ntv;
        // The last slice whose start is at or before g.
        let (mut lo, mut hi) = (0usize, self.nplanes);
        while hi - lo > 1 {
            let mid = (lo + hi) / 2;
            if self.offs[mid * ntiles] as usize <= g {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        lo
    }

    /// The batches: GPU-order ranges and their first-plane ranges.
    fn batches(&self) -> Vec<(usize, usize, usize, usize)> {
        let n = self.perm.len();
        (0..n.div_ceil(self.per_batch))
            .map(|i| {
                let b0 = i * self.per_batch;
                let b1 = (b0 + self.per_batch).min(n);
                (b0, b1, self.plane_of(b0), self.plane_of(b1 - 1))
            })
            .collect()
    }

    /// The two words of each visibility of a batch.
    fn words(&self, setup: &Setup, bl: &Baselines, lay: &Layout, b0: usize, b1: usize) -> Vec<u32> {
        let nchan = bl.f_over_c.len();
        let mut out = vec![0u32; 2 * (b1 - b0)];
        out.par_chunks_mut(2)
            .zip(self.perm[b0..b1].par_iter())
            .for_each(|(o, &k)| {
                let r = lay.refs[k as usize];
                let ([u, v, _], _) = uvw_of(bl, r);
                let (_, _, iu0, iv0) = setup.getpix(u, v);
                o[0] = (r.row as usize * nchan + r.ch as usize) as u32;
                o[1] = ((iu0 + OFF) as u32) | (((iv0 + OFF) as u32) << 16);
            });
        out
    }

    fn download<T: Real>(
        &self,
        ctx: &Context,
        src: &wgpu::Buffer,
        staging: &wgpu::Buffer,
        count: usize,
    ) -> Result<Vec<T>, String> {
        let bytes = (count * std::mem::size_of::<T>()) as u64;
        let mut encoder = ctx.device.create_command_encoder(&Default::default());
        encoder.copy_buffer_to_buffer(src, 0, staging, 0, bytes);
        ctx.queue.submit([encoder.finish()]);
        let slice = staging.slice(..bytes);
        let mapped = Arc::new(Mutex::new(None));
        let sink = mapped.clone();
        slice.map_async(wgpu::MapMode::Read, move |r| {
            *sink.lock().unwrap_or_else(|e| e.into_inner()) = Some(r);
        });
        wait(ctx)?;
        match mapped.lock().unwrap_or_else(|e| e.into_inner()).take() {
            Some(Ok(())) => {}
            Some(Err(e)) => return Err(format!("mapping a GPU result: {e}")),
            None => return Err("a GPU result was not mapped".into()),
        }
        let out = {
            let view = slice
                .get_mapped_range()
                .map_err(|e| format!("reading a GPU result: {e}"))?;
            let mut out = vec![T::zero(); count];
            // SAFETY: `out` has exactly `bytes` bytes of plain floats.
            unsafe {
                std::ptr::copy_nonoverlapping(
                    view.as_ptr(),
                    out.as_mut_ptr().cast::<u8>(),
                    bytes as usize,
                );
            }
            out
        };
        staging.unmap();
        Ok(out)
    }

    /// Record and run one submission, waited for.
    fn run(ctx: &Context, record: impl FnOnce(&mut wgpu::ComputePass)) -> Result<(), String> {
        let mut encoder = ctx.device.create_command_encoder(&Default::default());
        {
            let mut pass = encoder.begin_compute_pass(&Default::default());
            record(&mut pass);
        }
        ctx.queue.submit([encoder.finish()]);
        wait(ctx)
    }

    /// The FFT passes of one grid (in `grid_a`), returning the buffer that
    /// holds the result.
    fn fft_binds<'a>(
        &self,
        ctx: &Context,
        pipes: &Pipes,
        setup: &Setup,
        bufs: &'a Buffers,
        forward: bool,
    ) -> (FftBinds, &'a wgpu::Buffer) {
        let (nu, nv) = (setup.nu, setup.nv);
        let rows = fft::plan(nv).expect("checked at setup");
        let cols = fft::plan(nu).expect("checked at setup");
        let passes = fft_passes(nv, nu, 1, &rows, &cols);
        let tw = if forward { &bufs.tw_fwd } else { &bufs.tw_inv };
        let binds = passes
            .iter()
            .enumerate()
            .map(|(i, (words, dispatch))| {
                let params = uniform(ctx, words);
                let t = if i < rows.len() { &tw[0] } else { &tw[1] };
                let (src, dst) = if i % 2 == 0 {
                    (&bufs.grid_a, &bufs.grid_b)
                } else {
                    (&bufs.grid_b, &bufs.grid_a)
                };
                (
                    bind(ctx, &pipes.x2.fft, &seq(&[&params, t, src, dst])),
                    *dispatch,
                )
            })
            .collect();
        let out = if passes.len().is_multiple_of(2) {
            &bufs.grid_a
        } else {
            &bufs.grid_b
        };
        (binds, out)
    }

    /// The gridding half of `grid_images_from` for a dirty image alone, from
    /// the stored values (CPU sorted order): the plane loop on the GPU, then
    /// the CPU's global corrections. `dirty` is zero on entry.
    pub(super) fn grid<T: Real>(
        &self,
        setup: &Setup,
        bl: &Baselines,
        lay: &Layout,
        tables: &Tables<T>,
        stored: &[Complex<T>],
        dirty: &mut [T],
    ) -> Result<(), String> {
        let (ctx, _) = context::get()?;
        let pipes = pipes(&ctx, self.precision)?;
        let _busy = ctx.busy.lock().unwrap_or_else(|e| e.into_inner());
        let mut guard = self.buffers.lock().unwrap_or_else(|e| e.into_inner());
        let bufs = self.buffers(&ctx, setup, &mut guard);
        let (mut host, mut up, mut comp, mut passes) = (0.0, 0.0, 0.0, 0usize);
        let t = Instant::now();
        {
            let mut enc = ctx.device.create_command_encoder(&Default::default());
            enc.clear_buffer(&bufs.image, 0, None);
            ctx.queue.submit([enc.finish()]);
        }
        let (fft_binds, transformed) = self.fft_binds(&ctx, &pipes, setup, bufs, false);
        comp += t.elapsed().as_secs_f64();
        let batches = self.batches();
        for &(b0, b1, mlo, mhi) in &batches {
            let t = Instant::now();
            let words = self.words(setup, bl, lay, b0, b1);
            let vals: Vec<Complex<T>> = self.perm[b0..b1]
                .par_iter()
                .map(|&k| stored[k as usize])
                .collect();
            host += t.elapsed().as_secs_f64();
            let t = Instant::now();
            ctx.queue.write_buffer(&bufs.vis, 0, bytes_of(&words));
            ctx.queue.write_buffer(&bufs.vals, 0, cbytes(&vals));
            ctx.queue.submit([]);
            wait(&ctx)?;
            drop((words, vals));
            up += t.elapsed().as_secs_f64();
            let pmax = (mhi + setup.supp - 1).min(self.nplanes - 1);
            let pmax = if setup.do_wgridding { pmax } else { 0 };
            for plane in mlo..=pmax {
                let t = Instant::now();
                let params = uniform(&ctx, &self.params(setup, plane, b0, b1, mlo, mhi, 0));
                let gb = bind(
                    &ctx,
                    &pipes.grid,
                    &seq(&[
                        &params,
                        &bufs.geo,
                        &bufs.coeff,
                        &bufs.offs,
                        &bufs.vis,
                        &bufs.vals,
                        &bufs.grid_a,
                    ]),
                );
                let pb = bind(
                    &ctx,
                    &pipes.project,
                    &[
                        (0, &params),
                        (1, &bufs.geo),
                        (3, transformed),
                        (4, &bufs.image),
                    ],
                );
                Self::run(&ctx, |pass| {
                    pass.set_pipeline(&pipes.grid);
                    pass.set_bind_group(0, &gb, &[]);
                    pass.dispatch_workgroups(self.ntv as u32, self.ntu as u32, 1);
                    pass.set_pipeline(&pipes.x2.fft);
                    for (b, (x, y)) in &fft_binds {
                        pass.set_bind_group(0, b, &[]);
                        pass.dispatch_workgroups(*x, *y, 1);
                    }
                    pass.set_pipeline(&pipes.project);
                    pass.set_bind_group(0, &pb, &[]);
                    pass.dispatch_workgroups(
                        (setup.ny as u32).div_ceil(16),
                        (setup.nx as u32).div_ceil(16),
                        1,
                    );
                })?;
                comp += t.elapsed().as_secs_f64();
                passes += 1;
            }
        }
        let t = Instant::now();
        let image: Vec<T> = self.download(&ctx, &bufs.image, &bufs.staging, setup.nx * setup.ny)?;
        let down = t.elapsed().as_secs_f64();
        drop(guard);
        let t = Instant::now();
        dirty.copy_from_slice(&image);
        correct_image(setup, dirty, &tables.corr, &tables.cfuv);
        host += t.elapsed().as_secs_f64();
        add_stats(|s| {
            s.grid_calls += 1;
            s.host_s += host;
            s.upload_s += up;
            s.compute_s += comp;
            s.download_s += down;
            s.plane_passes += passes;
            s.batches += batches.len();
        });
        Ok(())
    }

    /// `degrid_images` with the plane loop on the GPU: the CPU's corrected
    /// image, then per batch and plane the screen, the forward FFT and the
    /// degridding, then the CPU's phase and weight loop. `vis` is zero on
    /// entry (`sorted`: in the layout's order, else in visibility order).
    #[allow(clippy::too_many_arguments)]
    pub(super) fn degrid<T: Real>(
        &self,
        setup: &Setup,
        bl: &Baselines,
        lay: &Layout,
        tables: &Tables<T>,
        dirty: &[T],
        wgt: Weights,
        vis: &mut [Complex<T>],
        sorted: bool,
    ) -> Result<(), String> {
        let t = Instant::now();
        let (nx, ny) = (setup.nx, setup.ny);
        // The corrected copy of the image, as degrid_images forms it.
        let mut image: Vec<T> = dirty.to_vec();
        let (_, tny) = setup.table_dims();
        let (corr, cfuv) = (&tables.corr, &tables.cfuv);
        image
            .par_chunks_exact_mut(ny)
            .enumerate()
            .for_each(|(i, row)| {
                if setup.do_wgridding {
                    for (j, d) in row.iter_mut().enumerate() {
                        *d = *d * T::of(corr[setup.table_index(i, j, tny)]);
                    }
                } else {
                    let iu = nx / 2 - i.min(nx - i);
                    for (j, d) in row.iter_mut().enumerate() {
                        let iv = ny / 2 - j.min(ny - j);
                        *d = *d * T::of(cfuv.0[iu] * cfuv.1[iv]);
                    }
                }
            });
        let mut host = t.elapsed().as_secs_f64();
        let (ctx, _) = context::get()?;
        let pipes = pipes(&ctx, self.precision)?;
        let _busy = ctx.busy.lock().unwrap_or_else(|e| e.into_inner());
        let mut guard = self.buffers.lock().unwrap_or_else(|e| e.into_inner());
        let bufs = self.buffers(&ctx, setup, &mut guard);
        let t = Instant::now();
        ctx.queue.write_buffer(&bufs.image, 0, tbytes(&image));
        ctx.queue.submit([]);
        wait(&ctx)?;
        let mut up = t.elapsed().as_secs_f64();
        let (mut comp, mut down, mut passes) = (0.0, 0.0, 0usize);
        let t = Instant::now();
        let (fft_binds, transformed) = self.fft_binds(&ctx, &pipes, setup, bufs, true);
        comp += t.elapsed().as_secs_f64();
        let nchan = bl.f_over_c.len();
        let out = SyncPtr(vis.as_mut_ptr());
        let batches = self.batches();
        for &(b0, b1, mlo, mhi) in &batches {
            let t = Instant::now();
            let words = self.words(setup, bl, lay, b0, b1);
            host += t.elapsed().as_secs_f64();
            let t = Instant::now();
            ctx.queue.write_buffer(&bufs.vis, 0, bytes_of(&words));
            {
                let mut enc = ctx.device.create_command_encoder(&Default::default());
                enc.clear_buffer(
                    &bufs.vals,
                    0,
                    Some(((b1 - b0) * 2 * self.precision.bytes()) as u64),
                );
                ctx.queue.submit([enc.finish()]);
            }
            wait(&ctx)?;
            drop(words);
            up += t.elapsed().as_secs_f64();
            let n = b1 - b0;
            let groups = n.div_ceil(64) as u32;
            let gx = groups.clamp(1, MAX_WORKGROUPS);
            let gy = groups.div_ceil(gx).max(1);
            let pmax = (mhi + setup.supp - 1).min(self.nplanes - 1);
            let pmax = if setup.do_wgridding { pmax } else { 0 };
            for plane in mlo..=pmax {
                let t = Instant::now();
                let params = uniform(&ctx, &self.params(setup, plane, b0, b1, mlo, mhi, gx * 64));
                let plb = bind(
                    &ctx,
                    &pipes.place,
                    &[
                        (0, &params),
                        (1, &bufs.geo),
                        (3, &bufs.image),
                        (4, &bufs.grid_a),
                    ],
                );
                let db = bind(
                    &ctx,
                    &pipes.degrid,
                    &seq(&[
                        &params,
                        &bufs.geo,
                        &bufs.coeff,
                        &bufs.offs,
                        &bufs.vis,
                        &bufs.vals,
                        transformed,
                    ]),
                );
                Self::run(&ctx, |pass| {
                    pass.set_pipeline(&pipes.place);
                    pass.set_bind_group(0, &plb, &[]);
                    pass.dispatch_workgroups(
                        (setup.nv as u32).div_ceil(16),
                        (setup.nu as u32).div_ceil(16),
                        1,
                    );
                    pass.set_pipeline(&pipes.x2.fft);
                    for (b, (x, y)) in &fft_binds {
                        pass.set_bind_group(0, b, &[]);
                        pass.dispatch_workgroups(*x, *y, 1);
                    }
                    pass.set_pipeline(&pipes.degrid);
                    pass.set_bind_group(0, &db, &[]);
                    pass.dispatch_workgroups(gx, gy, 1);
                })?;
                comp += t.elapsed().as_secs_f64();
                passes += 1;
            }
            let t = Instant::now();
            let flat: Vec<T> = self.download(&ctx, &bufs.vals, &bufs.staging, 2 * n)?;
            down += t.elapsed().as_secs_f64();
            let t = Instant::now();
            flat.par_chunks_exact(2)
                .zip(self.perm[b0..b1].par_iter())
                .for_each(|(c, &k)| {
                    let r = lay.refs[k as usize];
                    let at = if sorted {
                        k as usize
                    } else {
                        r.row as usize * nchan + r.ch as usize
                    };
                    // SAFETY: each visibility index appears once in `perm`.
                    unsafe { *out.get().add(at) = Complex::new(c[0], c[1]) };
                });
            host += t.elapsed().as_secs_f64();
        }
        drop(guard);
        // The final loop of degrid_images.
        let t = Instant::now();
        lay.refs.par_iter().enumerate().for_each(|(k, &r)| {
            let idx = r.row as usize * nchan + r.ch as usize;
            let twgt = wgt.get::<T>(idx).unwrap_or(T::one());
            // SAFETY: each visibility index appears once in `refs`.
            unsafe {
                let o = out.get().add(if sorted { k } else { idx });
                *o = if setup.shifting {
                    let ph = shift_phase::<T>(setup, bl, r, -1.0);
                    *o * Complex::new(ph.re * twgt, ph.im * twgt)
                } else {
                    *o * twgt
                };
            }
        });
        host += t.elapsed().as_secs_f64();
        add_stats(|s| {
            s.degrid_calls += 1;
            s.host_s += host;
            s.upload_s += up;
            s.compute_s += comp;
            s.download_s += down;
            s.plane_passes += passes;
            s.batches += batches.len();
        });
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(seed: &mut u64) -> f64 {
        *seed = seed
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*seed >> 11) as f64) / ((1u64 << 53) as f64)
    }

    struct Case {
        uvw: Vec<f64>,
        freq: Vec<f64>,
        vis: Vec<Complex<f64>>,
        wgt: Vec<f64>,
        opts: Options,
    }

    fn case(
        n: usize,
        field: f64,
        wmax: f64,
        nrow: usize,
        eps: f64,
        wgrid: bool,
        seed: u64,
    ) -> Case {
        let mut s = seed;
        let freq = vec![1.0e9, 1.2e9, 1.4e9];
        let dx = field / n as f64;
        let lam = 1.4e9 / C_LIGHT;
        let mut uvw = Vec::new();
        for _ in 0..nrow {
            uvw.push((lcg(&mut s) - 0.5) * 0.9 / dx / lam);
            uvw.push((lcg(&mut s) - 0.5) * 0.9 / dx / lam);
            uvw.push((lcg(&mut s) - 0.5) * 2.0 * wmax / lam);
        }
        let nv = nrow * freq.len();
        let vis = (0..nv)
            .map(|_| Complex::new(lcg(&mut s) - 0.5, lcg(&mut s) - 0.5))
            .collect();
        // A few zero weights: inactive visibilities.
        let wgt = (0..nv)
            .map(|i| if i % 17 == 3 { 0.0 } else { 0.5 + lcg(&mut s) })
            .collect();
        let opts = Options {
            nx: n,
            ny: n,
            pixsize_x: dx,
            pixsize_y: dx,
            epsilon: eps,
            do_wgridding: wgrid,
            ..Options::default()
        };
        Case {
            uvw,
            freq,
            vis,
            wgt,
            opts,
        }
    }

    /// The GPU, or `None` (and a note) where no adapter can run the path.
    fn have_gpu() -> bool {
        match context::get().and_then(|(c, _)| pipes(&c, Precision::F64).map(|_| ())) {
            Ok(()) => true,
            Err(e) => {
                eprintln!("skipped: no usable GPU adapter for the gridder ({e})");
                false
            }
        }
    }

    fn rel<T: Real>(a: &[T], b: &[T]) -> f64 {
        let peak = b.iter().map(|x| x.to().abs()).fold(0.0, f64::max);
        let diff = a
            .iter()
            .zip(b)
            .map(|(x, y)| (x.to() - y.to()).abs())
            .fold(0.0, f64::max);
        diff / peak
    }

    fn crel<T: Real>(a: &[Complex<T>], b: &[Complex<T>]) -> f64 {
        let peak = b
            .iter()
            .map(|x| x.re.to().abs().max(x.im.to().abs()))
            .fold(0.0, f64::max);
        let diff = a
            .iter()
            .zip(b)
            .map(|(x, y)| {
                (x.re.to() - y.re.to())
                    .abs()
                    .max((x.im.to() - y.im.to()).abs())
            })
            .fold(0.0, f64::max);
        diff / peak
    }

    fn compare<T: Real + Send + Sync>(c: &Case, tol: f64, batch: Option<usize>) {
        let wgt: Vec<T> = c.wgt.iter().map(|&w| T::of(w)).collect();
        let vis: Vec<Complex<T>> = c
            .vis
            .iter()
            .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
            .collect();
        let n = c.opts.nx * c.opts.ny;
        let mut s = 5u64;
        let model: Vec<T> = (0..n)
            .map(|i| T::of(if i % 7 == 0 { lcg(&mut s) - 0.3 } else { 0.0 }))
            .collect();
        let cpu = Prepared::<T>::new(&c.opts, &c.uvw, &c.freq, T::weights(&wgt)).unwrap();
        let mut gpu = Prepared::<T>::new(&c.opts, &c.uvw, &c.freq, T::weights(&wgt)).unwrap();
        gpu.use_gpu(DEFAULT_BUDGET_MIB).unwrap();
        if let Some(b) = batch {
            gpu.gpu.as_mut().unwrap().per_batch = b;
        }
        // vis2dirty
        let (mut d0, mut d1) = (vec![T::zero(); n], vec![T::zero(); n]);
        cpu.vis2dirty(T::vis_data(&vis), T::weights(&wgt), &mut d0)
            .unwrap();
        gpu.vis2dirty(T::vis_data(&vis), T::weights(&wgt), &mut d1)
            .unwrap();
        let r = rel(&d1, &d0);
        assert!(r <= tol, "vis2dirty {r:e} > {tol:e}");
        // dirty2vis
        let (mut v0, mut v1) = (vec![czero::<T>(); vis.len()], vec![czero::<T>(); vis.len()]);
        cpu.dirty2vis(&model, T::weights(&wgt), &mut v0).unwrap();
        gpu.dirty2vis(&model, T::weights(&wgt), &mut v1).unwrap();
        let r = crel(&v1, &v0);
        assert!(r <= tol, "dirty2vis {r:e} > {tol:e}");
        // The major cycle's residual.
        let q0 = cpu
            .residual(T::vis_data(&vis), &wgt, Some(&model), &mut d0)
            .unwrap();
        let q1 = gpu
            .residual(T::vis_data(&vis), &wgt, Some(&model), &mut d1)
            .unwrap();
        let r = rel(&d1, &d0);
        assert!(r <= tol, "residual {r:e} > {tol:e}");
        assert!(((q1 - q0) / q0).abs() <= tol, "misfit {q0} {q1}");
        // Repeats are bit-identical.
        let mut d2 = vec![T::zero(); n];
        let q2 = gpu
            .residual(T::vis_data(&vis), &wgt, Some(&model), &mut d2)
            .unwrap();
        assert_eq!(q1.to_bits(), q2.to_bits());
        assert!(
            d1.iter()
                .zip(&d2)
                .all(|(a, b)| a.to().to_bits() == b.to().to_bits())
        );
    }

    #[test]
    fn gpu_gridder_matches_the_cpu_f64() {
        if !have_gpu() {
            return;
        }
        compare::<f64>(&case(64, 0.25, 800.0, 400, 1e-9, true, 7), 1e-11, None);
        compare::<f64>(&case(96, 0.05, 2000.0, 300, 1e-6, true, 8), 1e-11, None);
        compare::<f64>(&case(64, 0.1, 0.0, 300, 1e-7, false, 9), 1e-11, None);
    }

    #[test]
    fn gpu_gridder_matches_the_cpu_f32() {
        if !have_gpu() {
            return;
        }
        compare::<f32>(&case(64, 0.25, 800.0, 400, 1e-4, true, 7), 1e-5, None);
        compare::<f32>(&case(128, 0.1, 1500.0, 500, 1e-5, true, 10), 1e-5, None);
    }

    #[test]
    fn gpu_batches_agree() {
        if !have_gpu() {
            return;
        }
        let c = case(64, 0.25, 800.0, 400, 1e-9, true, 7);
        compare::<f64>(&c, 1e-11, Some(97));
        compare::<f64>(&c, 1e-11, Some(1));
        // Degridding does not depend on the batches, bit for bit.
        let n = c.opts.nx * c.opts.ny;
        let model: Vec<f64> = (0..n).map(|i| (i % 13) as f64 - 6.0).collect();
        let run = |b: Option<usize>| {
            let mut p =
                Prepared::<f64>::new(&c.opts, &c.uvw, &c.freq, Weights::F64(&c.wgt)).unwrap();
            p.use_gpu(DEFAULT_BUDGET_MIB).unwrap();
            if let Some(b) = b {
                p.gpu.as_mut().unwrap().per_batch = b;
            }
            let mut v = vec![Complex::new(0.0, 0.0); c.vis.len()];
            p.dirty2vis(&model, Weights::None, &mut v).unwrap();
            v
        };
        let (a, b) = (run(None), run(Some(53)));
        assert!(
            a.iter()
                .zip(&b)
                .all(|(x, y)| x.re.to_bits() == y.re.to_bits() && x.im.to_bits() == y.im.to_bits())
        );
    }

    #[test]
    fn plane_of_finds_the_slice() {
        // Host scheme only: no adapter needed.
        let g = Gpu {
            precision: Precision::F64,
            perm: vec![0; 10],
            offs: vec![0, 0, 3, 3, 3, 7, 10],
            nplanes: 3,
            ntu: 1,
            ntv: 2,
            fc_off: 0,
            rows_off: 0,
            table_off: 0,
            geo: Vec::new(),
            coeff: Vec::new(),
            per_batch: 4,
            buffers: Mutex::new(None),
        };
        let planes: Vec<usize> = (0..10).map(|i| g.plane_of(i)).collect();
        assert_eq!(planes, vec![0, 0, 0, 2, 2, 2, 2, 2, 2, 2]);
        assert_eq!(g.batches(), vec![(0, 4, 0, 2), (4, 8, 2, 2), (8, 10, 2, 2)]);
    }
}
