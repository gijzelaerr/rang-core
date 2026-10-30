//! WGSL source of the GPU gridder: gridding (gather), one Stockham FFT pass
//! and the projection with the w-phasor and the ordered layer sum. One
//! source, instantiated for `f64` or `f32` by the `real` alias; the f64
//! instance needs `Features::SHADER_F64`.

use super::Precision;

const COMMON: &str = r#"
alias real = REAL_TYPE;
alias cplx = vec2<real>;

fn cmul(a: cplx, b: cplx) -> cplx {
    return cplx(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x);
}
"#;

/// WGSL has no f64 trigonometry: Cody-Waite reduction by pi/2 (the first
/// part of pi/2 has 33 significant bits, so `n * PIO2_1` is exact for
/// |n| < 2^20, |x| < 1.6e6) and fdlibm's `__kernel_sin` / `__kernel_cos`
/// polynomials on [-pi/4, pi/4].
const SINCOS_F64: &str = r#"
fn sincos(x: real) -> cplx {
    let n = round(x * real(6.36619772367581382433e-01));
    let r = (x - n * real(1.57079632673412561417e+00)) - n * real(6.07710050650619224932e-11);
    let z = r * r;
    let s = r + r * z * (real(-1.66666666666666324348e-01) + z * (real(8.33333333332248946124e-03)
        + z * (real(-1.98412698298579493134e-04) + z * (real(2.75573137070700676789e-06)
        + z * (real(-2.50507602534068634195e-08) + z * real(1.58969099521155010221e-10))))));
    let c = real(1.0) - real(0.5) * z + z * z * (real(4.16666666666666019037e-02)
        + z * (real(-1.38888888888741095749e-03) + z * (real(2.48015872894767294178e-05)
        + z * (real(-2.75573143513906633035e-07) + z * (real(2.08757232129817482790e-09)
        + z * real(-1.13596475577881948265e-11))))));
    let q = i32(n) & 3;
    if (q == 0) {
        return cplx(s, c);
    }
    if (q == 1) {
        return cplx(c, -s);
    }
    if (q == 2) {
        return cplx(-s, -c);
    }
    return cplx(-c, s);
}
"#;

const SINCOS_F32: &str = r#"
fn sincos(x: real) -> cplx {
    return cplx(sin(x), cos(x));
}
"#;

const GRID: &str = r#"
struct GridParams {
    width: u32,
    height: u32,
    ksize: u32,
    mid: u32,
    cells: u32,
    layers: u32,
    _pad0: u32,
    _pad1: u32,
}

@group(0) @binding(0) var<uniform> gp: GridParams;
@group(0) @binding(1) var<storage, read> kernels: array<real>;
// Two words per sample: x kernel | y kernel << 16, and the cell x.
@group(0) @binding(2) var<storage, read> samples: array<u32>;
// Per layer of the batch, `cells + 1` offsets of the cells' runs within the
// layer's samples (sorted by cell y * width + x, row-channel order within a
// cell).
@group(0) @binding(3) var<storage, read> cell_start: array<u32>;
// Per layer l of the batch, grid 2 l (dirty) and 2 l + 1 (PSF).
@group(0) @binding(4) var<storage, read_write> grids: array<cplx>;
// Per layer of the batch, the index of its first sample in `samples`.
@group(0) @binding(5) var<storage, read> sample_base: array<u32>;
// Three values per sample: the reader's f32 weighted sample (re, im) and
// PSF weight, widened exactly on the host.
@group(0) @binding(6) var<storage, read> values: array<real>;

// The sample at cell (x, y) adds kernel tap (i, j) to cell
// ((x + i - mid) mod W, (y + j - mid) mod H), as the CPU's AddDataSample.
// Gather: each cell of an 8 x 4 tile has seven invocations, one per kernel
// row j (rows j, j + 7, ... for kernels wider than 7); each sums, for its
// row, source cell x = cx + mid - i in ascending x (descending i), then the
// samples of that cell in row-channel order. The seven row sums are then
// added in row order 0..6 by the first invocation, so the result does not
// depend on scheduling.
var<workgroup> row_re: array<real, 224>;
var<workgroup> row_im: array<real, 224>;
var<workgroup> row_psf: array<real, 224>;

@compute @workgroup_size(8, 4, 7)
fn grid(
    @builtin(global_invocation_id) id: vec3<u32>,
    @builtin(local_invocation_id) lid: vec3<u32>,
    @builtin(workgroup_id) wid: vec3<u32>,
) {
    let cx = id.x;
    let cy = id.y;
    let l = wid.z;
    let w = gp.width;
    let h = gp.height;
    let in_grid = cx < w && cy < h && l < gp.layers;
    let ks = gp.ksize;
    let mid = gp.mid;
    let base = l * (gp.cells + 1u);
    let first = sample_base[min(l, gp.layers - 1u)];
    var dre = real(0.0);
    var dim = real(0.0);
    var pre = real(0.0);
    if (in_grid) {
        let interior = cx + mid >= ks - 1u && cx + mid < w;
        for (var j = lid.z; j < ks; j += 7u) {
            let row = ((cy + mid + h - j) % h) * w;
            if (interior) {
                let lo = first + cell_start[base + row + cx + mid + 1u - ks];
                let hi = first + cell_start[base + row + cx + mid + 1u];
                for (var s = lo; s < hi; s++) {
                    let kern = samples[2u * s];
                    let i = cx + mid - samples[2u * s + 1u];
                    let k = kernels[(kern >> 16u) * ks + j] * kernels[(kern & 0xffffu) * ks + i];
                    dre += values[3u * s] * k;
                    dim += values[3u * s + 1u] * k;
                    pre += values[3u * s + 2u] * k;
                }
            } else {
                for (var ii = 0u; ii < ks; ii++) {
                    let i = ks - 1u - ii;
                    let sx = (cx + mid + w - i) % w;
                    let lo = first + cell_start[base + row + sx];
                    let hi = first + cell_start[base + row + sx + 1u];
                    for (var s = lo; s < hi; s++) {
                        let kern = samples[2u * s];
                        let k = kernels[(kern >> 16u) * ks + j] * kernels[(kern & 0xffffu) * ks + i];
                        dre += values[3u * s] * k;
                        dim += values[3u * s + 1u] * k;
                        pre += values[3u * s + 2u] * k;
                    }
                }
            }
        }
    }
    let tile = lid.x + 8u * lid.y;
    let slot = tile + 32u * lid.z;
    row_re[slot] = dre;
    row_im[slot] = dim;
    row_psf[slot] = pre;
    workgroupBarrier();
    if (in_grid && lid.z == 0u) {
        var sre = row_re[tile];
        var sim = row_im[tile];
        var spr = row_psf[tile];
        for (var z = 1u; z < 7u; z++) {
            sre += row_re[tile + 32u * z];
            sim += row_im[tile + 32u * z];
            spr += row_psf[tile + 32u * z];
        }
        let cell = cy * w + cx;
        grids[(2u * l) * gp.cells + cell] = cplx(sre, sim);
        grids[(2u * l + 1u) * gp.cells + cell] = cplx(spr, real(0.0));
    }
}
"#;

const FFT: &str = r#"
struct FftParams {
    n: u32,
    radix: u32,
    ns: u32,
    tw_step: u32,
    elem_stride: u32,
    line_count: u32,
    lines_per_grid: u32,
    line_stride: u32,
    grid_stride: u32,
    lines_fast: u32,
    row_threads: u32,
    _pad0: u32,
}

@group(0) @binding(0) var<uniform> fp: FftParams;
@group(0) @binding(1) var<storage, read> tw: array<cplx>;
@group(0) @binding(2) var<storage, read> src: array<cplx>;
@group(0) @binding(3) var<storage, read_write> dst: array<cplx>;

// One radix pass over every line of every grid (fft.rs documents the
// scheme; its host transcription is the unit-tested reference).
@compute @workgroup_size(64, 1, 1)
fn fft_pass(@builtin(global_invocation_id) id: vec3<u32>) {
    let t = id.x + id.y * fp.row_threads;
    let r = fp.radix;
    let m = fp.n / r;
    if (t >= fp.line_count * m) {
        return;
    }
    var line: u32;
    var j: u32;
    if (fp.lines_fast == 1u) {
        line = t % fp.line_count;
        j = t / fp.line_count;
    } else {
        j = t % m;
        line = t / m;
    }
    let base = (line / fp.lines_per_grid) * fp.grid_stride + (line % fp.lines_per_grid) * fp.line_stride;
    let es = fp.elem_stride;
    let k = j % fp.ns;
    var v: array<cplx, 16>;
    for (var q = 0u; q < r; q++) {
        v[q] = cmul(src[base + (j + q * m) * es], tw[q * k * fp.tw_step]);
    }
    let first = (j / fp.ns) * fp.ns * r + k;
    for (var s = 0u; s < r; s++) {
        var acc = cplx(real(0.0), real(0.0));
        // (q s) mod r, advanced by s per term instead of a modulo per term.
        var e = 0u;
        for (var q = 0u; q < r; q++) {
            acc += cmul(v[q], tw[e * m]);
            e += s;
            if (e >= r) {
                e -= r;
            }
        }
        dst[base + (first + s * fp.ns) * es] = acc;
    }
}
"#;

const PROJECT: &str = r#"
struct ProjectParams {
    width: u32,
    height: u32,
    cells: u32,
    layers: u32,
}

@group(0) @binding(0) var<uniform> pp: ProjectParams;
@group(0) @binding(1) var<storage, read> sqrt_lm: array<real>;
// -2 pi w of each layer of the batch.
@group(0) @binding(2) var<storage, read> two_pi_w: array<real>;
@group(0) @binding(3) var<storage, read> grids: array<cplx>;
// Dirty sum (cells) then PSF sum (cells), in the CPU's `target` order.
@group(0) @binding(4) var<storage, read_write> acc: array<real>;

// projectOnImageAndCorrect<false> of every layer of the batch, added to the
// running sums in ascending layer order (the CPU's order).
@compute @workgroup_size(16, 16, 1)
fn project(@builtin(global_invocation_id) id: vec3<u32>) {
    let x = id.x;
    let y = id.y;
    let w = pp.width;
    let h = pp.height;
    if (x >= w || y >= h) {
        return;
    }
    let index = y * w + x;
    var y_src = (h - y) + h / 2u;
    if (y_src >= h) {
        y_src -= h;
    }
    var x_src = x + w / 2u;
    if (x_src >= w) {
        x_src -= w;
    }
    let target_index = x_src + y_src * w;
    var dirty = acc[target_index];
    var psf = acc[pp.cells + target_index];
    let lm = sqrt_lm[index];
    for (var l = 0u; l < pp.layers; l++) {
        let phasor = sincos(two_pi_w[l] * lm);
        let d = grids[(2u * l) * pp.cells + index];
        let p = grids[(2u * l + 1u) * pp.cells + index];
        dirty = dirty + (d.x * phasor.y - d.y * phasor.x);
        psf = psf + (p.x * phasor.y - p.y * phasor.x);
    }
    acc[target_index] = dirty;
    acc[pp.cells + target_index] = psf;
}
"#;

/// The three entry points' sources for one precision.
pub(crate) struct Sources {
    pub(crate) grid: String,
    pub(crate) fft: String,
    pub(crate) project: String,
}

pub(crate) fn sources(precision: Precision) -> Sources {
    let (real, sincos) = match precision {
        Precision::F64 => ("f64", SINCOS_F64),
        Precision::F32 => ("f32", SINCOS_F32),
    };
    let common = COMMON.replace("REAL_TYPE", real);
    Sources {
        grid: format!("{common}{GRID}"),
        fft: format!("{common}{FFT}"),
        project: format!("{common}{sincos}{PROJECT}"),
    }
}
