//! Closure quantities as a gauge-free flagging statistic (big plan task C1,
//! `research/c1-closure-arm.md`).
//!
//! Per (time, channel) cell, closures are formed only on cycles whose
//! baselines are all `usable` (the campaign passes its training cells):
//!
//! - `Family::Trace`: the closure trace of Broderick and Pesce (2020),
//!   `T = tr(V_ab V_sb^-1 V_sd V_ad^-1) / 2`, invariant under any invertible
//!   per-antenna 2x2 gains `V_ij -> G_i V_ij G_j^H`, on the cyclic
//!   quadrangle set: baseline (a, b) leads one quadrangle per station
//!   `s` not in {a, b}, with `d` the next station after `s` in the cycle
//!   (skipping a, b, s); if (s, d) or (a, d) is missing, `d` advances up to
//!   `reroute` more times; if (s, b) is missing the closure is skipped;
//! - `Family::Phase`: parallel-hand closure phases on all triangles (a, b, s);
//! - `Family::LogAmp`: parallel-hand log closure amplitudes on the cyclic
//!   quadrangles.
//!
//! Each closure's residual against the model's closure is normalised by its
//! first-order noise from WEIGHT_SPECTRUM (sigma^2 = 1/w per complex
//! correlation). Per sample of baseline (a, b) the kernel writes the median
//! normalised residual over the baseline's closures, the median closure TV
//! (mean normalised difference of the same closure to its time and frequency
//! neighbours) and the closure count. Baselines run in parallel; each keeps
//! a ring of three integrations of its closures, so no per-closure array of
//! the whole cube is stored. Results do not depend on the thread count.

use crate::jones::{self, C64, Jones};
use rayon::prelude::*;

/// Closure family codes of the C ABI.
pub const FAMILY_TRACE: u32 = 0;
pub const FAMILY_PHASE: u32 = 1;
pub const FAMILY_LOGAMP: u32 = 2;

/// Baselines processed per parallel chunk before their rows are scattered.
const CHUNK_BASELINES: usize = 64;
const NO_ROUTE: u16 = u16::MAX;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Family {
    Trace,
    Phase,
    LogAmp,
}

impl Family {
    pub fn from_code(code: u32) -> Option<Self> {
        match code {
            FAMILY_TRACE => Some(Self::Trace),
            FAMILY_PHASE => Some(Self::Phase),
            FAMILY_LOGAMP => Some(Self::LogAmp),
            _ => None,
        }
    }
}

/// Borrowed inputs of `closure_scores`.
pub struct ClosureInputs<'a> {
    pub nrow: usize,
    pub nchan: usize,
    pub nant: usize,
    pub ntime: usize,
    /// Interleaved complex64 DATA `(row, chan, 4)`: `8 * nrow * nchan` floats.
    pub data: &'a [f32],
    /// Interleaved complex64 MODEL_DATA, same layout.
    pub model: &'a [f32],
    /// WEIGHT_SPECTRUM `(row, chan, 4)`.
    pub weights: &'a [f32],
    /// `(row, chan)`, nonzero where the sample may enter a closure.
    pub usable: &'a [u8],
    pub antenna1: &'a [u32],
    pub antenna2: &'a [u32],
    /// Integration index of each row, `< ntime`.
    pub time_index: &'a [u32],
    /// The station cycle (every antenna with a cross-correlation row).
    pub stations: &'a [u32],
    pub family: Family,
    pub min_closures: usize,
    pub reroute: usize,
}

/// Caller buffers, `nrow * nchan` each: median normalised closure residual
/// (NaN without a score), median closure TV (NaN without a score) and the
/// closure count.
pub struct ClosureOutputs<'a> {
    pub residual: &'a mut [f32],
    pub tv: &'a mut [f32],
    pub count: &'a mut [u16],
}

#[derive(Debug, PartialEq, Eq)]
pub enum ClosureError {
    Shape(&'static str),
    DuplicateRow { time: usize, a: usize, b: usize },
    UnknownStation(usize),
}

impl std::fmt::Display for ClosureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Shape(what) => write!(f, "closure inputs: {what}"),
            Self::DuplicateRow { time, a, b } => {
                write!(
                    f,
                    "closure inputs: two rows for time {time}, baseline ({a}, {b})"
                )
            }
            Self::UnknownStation(s) => write!(f, "closure inputs: station {s} not in the cycle"),
        }
    }
}

/// One closure at one cell: residual components, their variances and the
/// route (`d` for quadrangles, `s` for triangles; `NO_ROUTE` if absent).
#[derive(Clone, Copy)]
struct Rec {
    r: [f32; 2],
    i: f32,
    v: [f32; 2],
    d: u16,
}

const EMPTY: Rec = Rec {
    r: [0.0; 2],
    i: 0.0,
    v: [0.0; 2],
    d: NO_ROUTE,
};

/// A visibility of an unordered pair at one cell, oriented i -> j.
struct Edge {
    data: Jones,
    model: Jones,
    /// Parallel-hand weights (XX, YY).
    w: [f64; 2],
}

fn cdiv(a: C64, b: C64) -> C64 {
    let n = b.norm2();
    C64::new(
        (a.re * b.re + a.im * b.im) / n,
        (a.im * b.re - a.re * b.im) / n,
    )
}

fn abs(a: C64) -> f64 {
    a.norm2().sqrt()
}

fn arg(a: C64) -> f64 {
    a.im.atan2(a.re)
}

fn wrap(x: f64) -> f64 {
    let y = (x + std::f64::consts::PI).rem_euclid(2.0 * std::f64::consts::PI);
    y - std::f64::consts::PI
}

/// Inverse of a 2x2 complex matrix, `None` if singular or non-finite.
pub fn inverse(m: &Jones) -> Option<Jones> {
    let det = m[0] * m[3] - m[1] * m[2];
    if !det.is_finite() || det.norm2() == 0.0 {
        return None;
    }
    let one = C64::new(1.0, 0.0);
    let r = cdiv(one, det);
    let neg = |x: C64| C64::new(-x.re, -x.im);
    let out = [m[3] * r, neg(m[1]) * r, neg(m[2]) * r, m[0] * r];
    jones::is_finite(&out).then_some(out)
}

/// `tr(V_ab V_sb^-1 V_sd V_ad^-1) / 2`, `None` if a matrix is singular.
pub fn closure_trace(ab: &Jones, sb: &Jones, sd: &Jones, ad: &Jones) -> Option<C64> {
    let x = jones::mul(ab, &inverse(sb)?);
    let y = jones::mul(sd, &inverse(ad)?);
    let p = jones::mul(&x, &y);
    let t = (p[0] + p[3]).scale(0.5);
    t.is_finite().then_some(t)
}

struct Layout<'a> {
    inp: &'a ClosureInputs<'a>,
    /// `index[(t * nant + i) * nant + j]`: the row of (i, j) as stored, or -1.
    index: Vec<i64>,
    pos: Vec<usize>,
}

impl Layout<'_> {
    fn edge(&self, t: usize, i: usize, j: usize, c: usize) -> Option<Edge> {
        let nant = self.inp.nant;
        let (row, flip) = {
            let direct = self.index[(t * nant + i) * nant + j];
            if direct >= 0 {
                (direct as usize, false)
            } else {
                let back = self.index[(t * nant + j) * nant + i];
                if back < 0 {
                    return None;
                }
                (back as usize, true)
            }
        };
        let cell = row * self.inp.nchan + c;
        if self.inp.usable[cell] == 0 {
            return None;
        }
        let at = 8 * cell;
        let mut data = jones::from_f32(&self.inp.data[at..at + 8]);
        let mut model = jones::from_f32(&self.inp.model[at..at + 8]);
        if flip {
            data = jones::adjoint(&data);
            model = jones::adjoint(&model);
        }
        let w = &self.inp.weights[4 * cell..4 * cell + 4];
        Some(Edge {
            data,
            model,
            w: [f64::from(w[0]), f64::from(w[3])],
        })
    }

    fn next(&self, x: usize, excluded: &[usize]) -> usize {
        let cycle = self.inp.stations;
        let n = cycle.len();
        let mut k = self.pos[x];
        loop {
            k = (k + 1) % n;
            let s = cycle[k] as usize;
            if !excluded.contains(&s) {
                return s;
            }
        }
    }
}

/// `1 / (w |V|^2)` of one parallel hand, infinite for a bad weight.
fn inv_snr2(e: &Edge, h: usize) -> f64 {
    let v = e.data[if h == 0 { 0 } else { 3 }];
    let x = 1.0 / (e.w[h] * v.norm2());
    if x.is_finite() && x > 0.0 {
        x
    } else {
        f64::INFINITY
    }
}

fn hand(j: &Jones, h: usize) -> C64 {
    j[if h == 0 { 0 } else { 3 }]
}

fn finite_rec(rec: Rec) -> Option<Rec> {
    let ok = rec.r.iter().chain(rec.v.iter()).all(|x| x.is_finite())
        && rec.i.is_finite()
        && rec.v.iter().all(|&v| v > 0.0);
    ok.then_some(rec)
}

#[allow(clippy::too_many_arguments)]
fn quadrangle(
    lay: &Layout,
    family: Family,
    t: usize,
    c: usize,
    ab: &Edge,
    a: usize,
    b: usize,
    s: usize,
) -> Option<Rec> {
    let sb = lay.edge(t, s, b, c)?;
    let excluded = [a, b, s];
    let tries = (1 + lay.inp.reroute).min(lay.inp.stations.len().saturating_sub(3));
    let mut d = s;
    for _ in 0..tries {
        d = lay.next(d, &excluded);
        let (Some(sd), Some(ad)) = (lay.edge(t, s, d, c), lay.edge(t, a, d, c)) else {
            continue;
        };
        let rec = match family {
            Family::Trace => {
                let td = closure_trace(&ab.data, &sb.data, &sd.data, &ad.data)?;
                let tm = closure_trace(&ab.model, &sb.model, &sd.model, &ad.model)?;
                let mut var = 0.0;
                for h in 0..2 {
                    let p = cdiv(
                        hand(&ab.data, h) * hand(&sd.data, h),
                        hand(&sb.data, h) * hand(&ad.data, h),
                    );
                    let sum: f64 = [ab, &sb, &sd, &ad].iter().map(|e| inv_snr2(e, h)).sum();
                    var += 0.25 * p.norm2() * sum;
                }
                let r = td - tm;
                Rec {
                    r: [r.re as f32, 0.0],
                    i: r.im as f32,
                    v: [var as f32, 1.0],
                    d: d as u16,
                }
            }
            Family::LogAmp => {
                let mut r = [0.0f32; 2];
                let mut v = [0.0f32; 2];
                for h in 0..2 {
                    let la = |e: &Edge, m: bool| {
                        let j = if m { &e.model } else { &e.data };
                        abs(hand(j, h)).ln()
                    };
                    let closure = |m: bool| la(ab, m) + la(&sd, m) - la(&sb, m) - la(&ad, m);
                    r[h] = (closure(false) - closure(true)) as f32;
                    let sum: f64 = [ab, &sb, &sd, &ad].iter().map(|e| inv_snr2(e, h)).sum();
                    v[h] = (0.5 * sum) as f32;
                }
                Rec {
                    r,
                    i: 0.0,
                    v,
                    d: d as u16,
                }
            }
            Family::Phase => unreachable!("triangles are not quadrangles"),
        };
        return finite_rec(rec);
    }
    None
}

fn triangle(
    lay: &Layout,
    t: usize,
    c: usize,
    ab: &Edge,
    b: usize,
    a: usize,
    s: usize,
) -> Option<Rec> {
    let bs = lay.edge(t, b, s, c)?;
    let sa = lay.edge(t, s, a, c)?;
    let mut r = [0.0f32; 2];
    let mut v = [0.0f32; 2];
    for h in 0..2 {
        let pd = hand(&ab.data, h) * hand(&bs.data, h) * hand(&sa.data, h);
        let pm = hand(&ab.model, h) * hand(&bs.model, h) * hand(&sa.model, h);
        if pd.norm2() == 0.0 || pm.norm2() == 0.0 {
            return None;
        }
        r[h] = wrap(arg(pd) - arg(pm)) as f32;
        let sum: f64 = [ab, &bs, &sa].iter().map(|e| inv_snr2(e, h)).sum();
        v[h] = (0.5 * sum) as f32;
    }
    finite_rec(Rec {
        r,
        i: 0.0,
        v,
        d: s as u16,
    })
}

fn normalised(family: Family, x: &Rec) -> f64 {
    match family {
        Family::Trace => (f64::from(x.r[0]).powi(2) + f64::from(x.i).powi(2)) / f64::from(x.v[0]),
        _ => {
            0.5 * (f64::from(x.r[0]).powi(2) / f64::from(x.v[0])
                + f64::from(x.r[1]).powi(2) / f64::from(x.v[1]))
        }
    }
    .sqrt()
}

fn difference(family: Family, x: &Rec, y: &Rec) -> f64 {
    match family {
        Family::Trace => {
            let dr = f64::from(x.r[0]) - f64::from(y.r[0]);
            let di = f64::from(x.i) - f64::from(y.i);
            ((dr * dr + di * di) / (f64::from(x.v[0]) + f64::from(y.v[0]))).sqrt()
        }
        _ => {
            let mut sum = 0.0;
            for h in 0..2 {
                let mut d = f64::from(x.r[h]) - f64::from(y.r[h]);
                if family == Family::Phase {
                    d = wrap(d);
                }
                sum += d * d / (f64::from(x.v[h]) + f64::from(y.v[h]));
            }
            (0.5 * sum).sqrt()
        }
    }
}

/// Median with NumPy's convention (mean of the two middle values); `values`
/// is reordered.
pub fn median(values: &mut [f64]) -> Option<f64> {
    let n = values.len();
    if n == 0 {
        return None;
    }
    values.sort_unstable_by(|a, b| a.total_cmp(b));
    Some(if n % 2 == 1 {
        values[n / 2]
    } else {
        0.5 * (values[n / 2 - 1] + values[n / 2])
    })
}

/// One baseline's per-row outputs: (row, residual, tv, count) per integration.
type BaselineRows = Vec<(usize, Vec<f32>, Vec<f32>, Vec<u16>)>;

fn baseline(lay: &Layout, a: usize, b: usize) -> BaselineRows {
    let inp = lay.inp;
    let (nchan, ntime, nant) = (inp.nchan, inp.ntime, inp.nant);
    let partners: Vec<usize> = inp
        .stations
        .iter()
        .map(|&s| s as usize)
        .filter(|&s| s != a && s != b)
        .collect();
    let k = partners.len();
    let slice = nchan * k;
    let mut ring = vec![EMPTY; 3 * slice];
    let row_of = |t: usize| lay.index[(t * nant + a) * nant + b];
    let fill = |ring: &mut [Rec], t: usize| {
        let out = &mut ring[(t % 3) * slice..(t % 3 + 1) * slice];
        out.fill(EMPTY);
        if row_of(t) < 0 {
            return;
        }
        for c in 0..nchan {
            let Some(ab) = lay.edge(t, a, b, c) else {
                continue;
            };
            for (j, &s) in partners.iter().enumerate() {
                let rec = match inp.family {
                    Family::Phase => triangle(lay, t, c, &ab, b, a, s),
                    family => quadrangle(lay, family, t, c, &ab, a, b, s),
                };
                if let Some(rec) = rec {
                    out[c * k + j] = rec;
                }
            }
        }
    };
    let mut rows = Vec::new();
    let mut zs = Vec::with_capacity(k);
    let mut es = Vec::with_capacity(k);
    if ntime > 0 {
        fill(&mut ring, 0);
    }
    for t in 0..ntime {
        if t + 1 < ntime {
            fill(&mut ring, t + 1);
        }
        let row = row_of(t);
        if row < 0 {
            continue;
        }
        let at = |tt: usize, c: usize, j: usize| ring[(tt % 3) * slice + c * k + j];
        let mut residual = vec![f32::NAN; nchan];
        let mut tv = vec![f32::NAN; nchan];
        let mut count = vec![0u16; nchan];
        for c in 0..nchan {
            zs.clear();
            es.clear();
            for j in 0..k {
                let x = at(t, c, j);
                if x.d == NO_ROUTE {
                    continue;
                }
                zs.push(normalised(inp.family, &x));
                let mut sum = 0.0;
                let mut n = 0usize;
                let mut neighbours = [None; 4];
                if t > 0 {
                    neighbours[0] = Some(at(t - 1, c, j));
                }
                if t + 1 < ntime {
                    neighbours[1] = Some(at(t + 1, c, j));
                }
                if c > 0 {
                    neighbours[2] = Some(at(t, c - 1, j));
                }
                if c + 1 < nchan {
                    neighbours[3] = Some(at(t, c + 1, j));
                }
                for y in neighbours.into_iter().flatten() {
                    if y.d == x.d {
                        sum += difference(inp.family, &x, &y);
                        n += 1;
                    }
                }
                if n > 0 {
                    es.push(sum / n as f64);
                }
            }
            count[c] = zs.len().min(usize::from(u16::MAX)) as u16;
            if zs.len() >= inp.min_closures {
                residual[c] = median(&mut zs).map_or(f32::NAN, |m| m as f32);
            }
            if es.len() >= inp.min_closures {
                tv[c] = median(&mut es).map_or(f32::NAN, |m| m as f32);
            }
        }
        rows.push((row as usize, residual, tv, count));
    }
    rows
}

/// Per-sample closure scores of one family; see the module documentation.
pub fn closure_scores(inp: &ClosureInputs, out: &mut ClosureOutputs) -> Result<(), ClosureError> {
    let (nrow, nchan, nant, ntime) = (inp.nrow, inp.nchan, inp.nant, inp.ntime);
    let cells = nrow.checked_mul(nchan).ok_or(ClosureError::Shape("size"))?;
    if inp.data.len() != 8 * cells || inp.model.len() != 8 * cells {
        return Err(ClosureError::Shape("data or model length"));
    }
    if inp.weights.len() != 4 * cells || inp.usable.len() != cells {
        return Err(ClosureError::Shape("weights or usable length"));
    }
    if inp.antenna1.len() != nrow || inp.antenna2.len() != nrow || inp.time_index.len() != nrow {
        return Err(ClosureError::Shape("row columns"));
    }
    if out.residual.len() != cells || out.tv.len() != cells || out.count.len() != cells {
        return Err(ClosureError::Shape("output length"));
    }
    if nant >= usize::from(NO_ROUTE) || inp.stations.len() > nant {
        return Err(ClosureError::Shape("station count"));
    }
    let mut pos = vec![usize::MAX; nant];
    for (k, &s) in inp.stations.iter().enumerate() {
        let s = s as usize;
        if s >= nant || pos[s] != usize::MAX {
            return Err(ClosureError::Shape("station cycle"));
        }
        pos[s] = k;
    }
    let mut index = vec![-1i64; ntime * nant * nant];
    let mut pairs = Vec::new();
    for row in 0..nrow {
        let (a, b, t) = (
            inp.antenna1[row] as usize,
            inp.antenna2[row] as usize,
            inp.time_index[row] as usize,
        );
        if a >= nant || b >= nant || t >= ntime {
            return Err(ClosureError::Shape("antenna or time index out of range"));
        }
        if a == b {
            continue;
        }
        for s in [a, b] {
            if pos[s] == usize::MAX {
                return Err(ClosureError::UnknownStation(s));
            }
        }
        let here = (t * nant + a) * nant + b;
        let back = (t * nant + b) * nant + a;
        if index[here] >= 0 || index[back] >= 0 {
            return Err(ClosureError::DuplicateRow { time: t, a, b });
        }
        index[here] = row as i64;
        pairs.push((a, b));
    }
    pairs.sort_unstable();
    pairs.dedup();
    out.residual.fill(f32::NAN);
    out.tv.fill(f32::NAN);
    out.count.fill(0);
    let lay = Layout { inp, index, pos };
    for chunk in pairs.chunks(CHUNK_BASELINES) {
        let results: Vec<BaselineRows> = chunk
            .par_iter()
            .map(|&(a, b)| baseline(&lay, a, b))
            .collect();
        for rows in results {
            for (row, residual, tv, count) in rows {
                let s = row * nchan..(row + 1) * nchan;
                out.residual[s.clone()].copy_from_slice(&residual);
                out.tv[s.clone()].copy_from_slice(&tv);
                out.count[s].copy_from_slice(&count);
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A small deterministic generator (no extra dependency).
    struct Lcg(u64);
    impl Lcg {
        fn next(&mut self) -> f64 {
            self.0 = self
                .0
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((self.0 >> 11) as f64) / ((1u64 << 53) as f64) - 0.5
        }
        fn jones(&mut self, diag: f64) -> Jones {
            let mut j: Jones = std::array::from_fn(|_| C64::new(self.next(), self.next()));
            j[0] = j[0] + C64::new(diag, 0.0);
            j[3] = j[3] + C64::new(diag, 0.0);
            j
        }
    }

    fn corrupt(g: &[Jones], i: usize, j: usize, v: &Jones) -> Jones {
        jones::mul(&jones::mul(&g[i], v), &jones::adjoint(&g[j]))
    }

    #[test]
    fn trace_is_gauge_invariant() {
        let mut rng = Lcg(7);
        let n = 5;
        let mut v = vec![[C64::ZERO; 4]; n * n];
        for i in 0..n {
            for j in i + 1..n {
                v[i * n + j] = rng.jones(3.0);
                v[j * n + i] = jones::adjoint(&v[i * n + j]);
            }
        }
        let g: Vec<Jones> = (0..n).map(|_| rng.jones(1.5)).collect();
        let mut w = v.clone();
        for i in 0..n {
            for j in 0..n {
                if i != j {
                    w[i * n + j] = corrupt(&g, i, j, &v[i * n + j]);
                }
            }
        }
        let at = |m: &[Jones], i: usize, j: usize| m[i * n + j];
        for (a, b, s, d) in [(0, 1, 2, 3), (1, 0, 3, 4), (4, 2, 0, 1), (3, 1, 4, 0)] {
            let t0 =
                closure_trace(&at(&v, a, b), &at(&v, s, b), &at(&v, s, d), &at(&v, a, d)).unwrap();
            let t1 =
                closure_trace(&at(&w, a, b), &at(&w, s, b), &at(&w, s, d), &at(&w, a, d)).unwrap();
            let rel = abs(t0 - t1) / abs(t0);
            assert!(rel < 1e-10, "{rel}");
        }
    }

    #[test]
    fn inverse_and_median() {
        let m = [
            C64::new(2.0, 1.0),
            C64::new(0.5, 0.0),
            C64::new(0.0, -0.5),
            C64::new(1.0, 1.0),
        ];
        let p = jones::mul(&m, &inverse(&m).unwrap());
        assert!(abs(p[0] - C64::new(1.0, 0.0)) < 1e-12 && abs(p[1]) < 1e-12);
        assert!(inverse(&[C64::ZERO; 4]).is_none());
        assert_eq!(median(&mut [3.0, 1.0, 2.0]), Some(2.0));
        assert_eq!(median(&mut [4.0, 1.0, 2.0, 3.0]), Some(2.5));
        assert_eq!(median(&mut []), None);
        assert!((wrap(0.5 + 4.0 * std::f64::consts::PI) - 0.5).abs() < 1e-12);
        assert!((wrap(-0.5 - 2.0 * std::f64::consts::PI) + 0.5).abs() < 1e-12);
    }

    /// `nant` stations, `ntime` integrations, one channel; model = identity
    /// times 10, data = gains applied to the model, one baseline corrupted.
    fn kernel_case(
        family: Family,
        planted: Option<(usize, usize)>,
    ) -> (Vec<f32>, Vec<u32>, Vec<u32>) {
        let (nant, ntime, nchan) = (9usize, 3usize, 2usize);
        let mut rng = Lcg(11);
        let g: Vec<Jones> = (0..nant).map(|_| rng.jones(1.0)).collect();
        let mut a1 = Vec::new();
        let mut a2 = Vec::new();
        let mut ti = Vec::new();
        for t in 0..ntime {
            for i in 0..nant {
                for j in i + 1..nant {
                    a1.push(i as u32);
                    a2.push(j as u32);
                    ti.push(t as u32);
                }
            }
        }
        let nrow = a1.len();
        let mut data = vec![0f32; 8 * nrow * nchan];
        let mut model = vec![0f32; 8 * nrow * nchan];
        for r in 0..nrow {
            for c in 0..nchan {
                let m = jones::scalar(10.0);
                let mut d = corrupt(&g, a1[r] as usize, a2[r] as usize, &m);
                if planted == Some((a1[r] as usize, a2[r] as usize)) {
                    d[0] = d[0] * C64::new(0.0, 1.0);
                }
                let at = 8 * (r * nchan + c);
                for e in 0..4 {
                    data[at + 2 * e] = d[e].re as f32;
                    data[at + 2 * e + 1] = d[e].im as f32;
                    model[at + 2 * e] = m[e].re as f32;
                    model[at + 2 * e + 1] = m[e].im as f32;
                }
            }
        }
        let weights = vec![1f32; 4 * nrow * nchan];
        let usable = vec![1u8; nrow * nchan];
        let stations: Vec<u32> = (0..nant as u32).collect();
        let inp = ClosureInputs {
            nrow,
            nchan,
            nant,
            ntime,
            data: &data,
            model: &model,
            weights: &weights,
            usable: &usable,
            antenna1: &a1,
            antenna2: &a2,
            time_index: &ti,
            stations: &stations,
            family,
            min_closures: 3,
            reroute: 3,
        };
        let mut residual = vec![0f32; nrow * nchan];
        let mut tv = vec![0f32; nrow * nchan];
        let mut count = vec![0u16; nrow * nchan];
        closure_scores(
            &inp,
            &mut ClosureOutputs {
                residual: &mut residual,
                tv: &mut tv,
                count: &mut count,
            },
        )
        .unwrap();
        assert!(count.iter().all(|&n| n == (nant - 2) as u16));
        assert!(tv.iter().all(|x| x.is_finite()));
        (residual, a1, a2)
    }

    #[test]
    fn trace_residual_vanishes_under_gains() {
        let (residual, _, _) = kernel_case(Family::Trace, None);
        let worst = residual.iter().fold(0f32, |m, &x| m.max(x.abs()));
        assert!(worst < 1e-3, "{worst}");
    }

    #[test]
    fn planted_baseline_is_the_maximum() {
        for family in [Family::Trace, Family::Phase] {
            let (residual, a1, a2) = kernel_case(family, Some((2, 5)));
            let nchan = residual.len() / a1.len();
            let best = (0..residual.len())
                .max_by(|&i, &j| residual[i].total_cmp(&residual[j]))
                .unwrap();
            let row = best / nchan;
            assert_eq!((a1[row], a2[row]), (2, 5), "{family:?}");
        }
    }

    #[test]
    fn duplicate_rows_are_refused() {
        let data = vec![0f32; 16];
        let weights = vec![1f32; 8];
        let usable = vec![1u8; 2];
        let inp = ClosureInputs {
            nrow: 2,
            nchan: 1,
            nant: 2,
            ntime: 1,
            data: &data,
            model: &data,
            weights: &weights,
            usable: &usable,
            antenna1: &[0, 1],
            antenna2: &[1, 0],
            time_index: &[0, 0],
            stations: &[0, 1],
            family: Family::Trace,
            min_closures: 1,
            reroute: 0,
        };
        let (mut r, mut t, mut c) = (vec![0f32; 2], vec![0f32; 2], vec![0u16; 2]);
        let err = closure_scores(
            &inp,
            &mut ClosureOutputs {
                residual: &mut r,
                tv: &mut t,
                count: &mut c,
            },
        );
        assert_eq!(
            err,
            Err(ClosureError::DuplicateRow {
                time: 0,
                a: 1,
                b: 0
            })
        );
    }
}
