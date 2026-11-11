//! Apply (correct) and corrupt a chunk of visibilities by calibration terms
//! (task C4a, `research/c4a-apply.md`; C1 step 2,
//! `research/c1-calibration-chain.md` section 3.1).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The model is `rang.formats.caltable.correct`, frozen by DF-IO from CASA's
//! sources and measured against `applycal` (`research/dfio-formats.md`),
//! ported step for step:
//!
//! - terms are sorted by CASA's `VisCal::Type` key `B, K (KCROSS), G, J, D,
//!   X, C, P, E, T, F`; `correct` applies them in that order,
//!   `V <- J_p^-1 V J_q^-H`, and `corrupt` in the reverse order as the exact
//!   inverse;
//! - per (antenna, data time) the term's solutions are interpolated in time
//!   (`linear` or `nearest`, float32, times relative to `floor(t0 - 1)`,
//!   complex parameters as amplitude and float32-tracked phase), then
//!   resampled to the data channels (`linear`: flagged solution channels
//!   bridged, phase unwrapped, nearest beyond the end channels; `nearest`:
//!   the nearest unflagged solution channel);
//! - K is `exp(2 pi i tau[ns] (nu - nu_ref)[GHz])`, T one parameter on both
//!   receptors, B and G diagonal per receptor, Df CASA's linear
//!   approximation (`XY -= d_x,p YY + conj(d_y,q) XX`,
//!   `YX -= d_y,p XX + conj(d_x,q) YY`, parallel hands unchanged);
//! - flags as `applymode='calflag'`: a diagonal term flags the correlations
//!   of a flagged receptor; under that flag the bad receptor's element is 1
//!   and the other side is still applied (`JonesDiag::setMatByOk`; task C4b,
//!   `research/c4b-apply-ms.md`, found C4a skipped both sides). Df follows
//!   CASA's `JonesGenLin` (`Jones.cc`, read after run -01 of
//!   `research/c4a-apply.md` found the difference): XY is flagged when
//!   `d_x,p` or `d_y,q` is bad or XX or YY is flagged, YX likewise with
//!   `d_y,p`, `d_x,q`; the parallel hands are never flagged by Df; and when
//!   either leakage of an antenna is bad both are replaced by -1 in the
//!   formula above (`setMatByOk` sets both inverted elements to 1), so an
//!   unflagged cross hand of that antenna is corrected with that value, as
//!   CASA writes it. `caltable.correct` flags all four correlations instead.
//!   Flags are computed in correct order for both directions.
//!
//! KCROSS and Xf (task C6, `research/c6-polterms.md`): KCROSS is K's form
//! with the table's pivot (`KcrossJones : KJones`; CASA writes the delay in
//! the first parameter and 0 in the second, so Y is 1), flagged per
//! receptor; Xf is `diag(x, 1)` with one parameter per channel, and a flagged
//! parameter flags both receptors (`XJones::calcAllJones` sets both diagonal
//! elements' OK from the one parameter). P has its place in the order but is
//! not a table: it is refused here and applied by `cal::parang`.
//!
//! `apply_jones` (task C4b) applies a general 2x2 term on its own solution
//! bins, as QuartiCal's `complex` gains are solved: per row a time bin, per
//! channel a frequency bin, `G_p^-1 V G_q^-H` in float64, with CASA's
//! general-Jones flag rule (`Jones::flagRight` then `flagLeft`: a bad gain of
//! either antenna, or any flagged correlation of the cell, flags all four)
//! and `Jones::setMatByOk` (a bad side is the identity).
//!
//! Every output cell depends only on its own inputs: the per-(term,
//! antenna, time) tables are filled in parallel without reductions and rows
//! are corrected in parallel, so the output is bit-identical for every
//! thread count.

use rayon::prelude::*;

/// A calibration term type. The FFI codes are the discriminants.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    B = 0,
    K = 1,
    KCross = 2,
    G = 3,
    T = 4,
    Df = 5,
    Xf = 6,
    P = 7,
}

impl Kind {
    pub fn from_code(code: u32) -> Option<Kind> {
        Some(match code {
            0 => Kind::B,
            1 => Kind::K,
            2 => Kind::KCross,
            3 => Kind::G,
            4 => Kind::T,
            5 => Kind::Df,
            6 => Kind::Xf,
            7 => Kind::P,
            _ => return None,
        })
    }

    /// CASA's `VisCal::Type` (`VisCal.h`): B 0, K 1 (KCROSS too), G 2, J 3,
    /// D 4, X 5, C 6, P 7, E 8, T 9, F 10.
    pub fn type_key(self) -> u8 {
        match self {
            Kind::B => 0,
            Kind::K | Kind::KCross => 1,
            Kind::G => 2,
            Kind::Df => 4,
            Kind::Xf => 5,
            Kind::P => 7,
            Kind::T => 9,
        }
    }

    /// Parameters per solution channel in the table.
    pub fn npar(self) -> usize {
        match self {
            Kind::T | Kind::Xf | Kind::P => 1,
            _ => 2,
        }
    }

    /// FPARAM (float) rather than CPARAM (complex).
    pub fn float_param(self) -> bool {
        matches!(self, Kind::K | Kind::KCross)
    }

    fn not_yet(self) -> Option<&'static str> {
        match self {
            Kind::P => Some(
                "P (parallactic angle) is not a table: rotate with cal::parang \
                 (rang.cal_pol, task C6) after the tables",
            ),
            _ => None,
        }
    }
}

/// Time or frequency interpolation. FFI codes 0 and 1.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Interp {
    Linear = 0,
    Nearest = 1,
}

impl Interp {
    pub fn from_code(code: u32) -> Option<Interp> {
        match code {
            0 => Some(Interp::Linear),
            1 => Some(Interp::Nearest),
            _ => None,
        }
    }
}

/// Correct (`applycal`) or corrupt (the exact inverse). FFI codes 0 and 1.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    Correct = 0,
    Corrupt = 1,
}

/// One term: a table's rows for one field and window, grouped per antenna.
pub struct Term<'a> {
    pub kind: Kind,
    pub time_interp: Interp,
    pub freq_interp: Interp,
    /// `nant + 1` offsets: antenna `a`'s slots are
    /// `slot_start[a]..slot_start[a + 1]`, sorted by time.
    pub slot_start: &'a [usize],
    /// Solution time of each slot (s).
    pub slot_time: &'a [f64],
    pub nchan_sol: usize,
    pub npar: usize,
    /// `(slot, chan_sol, par)` floats (K), or the same interleaved re, im
    /// (complex terms).
    pub params: &'a [f32],
    /// `(slot, chan_sol, par)`, 0 or 1.
    pub flags: &'a [u8],
    /// The table window's CHAN_FREQ (Hz).
    pub sol_freq: &'a [f64],
    /// K's delay pivot (Hz): the window's `CHAN_FREQ[nchan // 2]`.
    pub k_ref_freq: f64,
}

/// One chunk of visibilities of one window.
pub struct Chunk<'a> {
    pub nrow: usize,
    pub nchan: usize,
    pub nant: usize,
    /// Interleaved complex64 `(row, chan, 4)`, XX, XY, YX, YY.
    pub data: &'a [f32],
    /// FLAG `(row, chan, 4)`, 0 or 1.
    pub flags: &'a [u8],
    pub time: &'a [f64],
    pub antenna1: &'a [u32],
    pub antenna2: &'a [u32],
    /// The window's CHAN_FREQ (Hz), at least `first_chan + nchan` values:
    /// the data hold its channels `first_chan..first_chan + nchan`. Each
    /// term's table is resampled to the whole window, as for a chunk of every
    /// channel, so a channel window is corrected exactly as the same channels
    /// of the whole band (research/sliced-read.md).
    pub freq: &'a [f64],
    /// The first channel of the window the data hold.
    pub first_chan: usize,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
struct C {
    re: f64,
    im: f64,
}

impl C {
    const ONE: C = C { re: 1.0, im: 0.0 };
    fn new(re: f64, im: f64) -> C {
        C { re, im }
    }
    fn conj(self) -> C {
        C::new(self.re, -self.im)
    }
    fn mul(self, o: C) -> C {
        C::new(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
    fn add(self, o: C) -> C {
        C::new(self.re + o.re, self.im + o.im)
    }
    fn sub(self, o: C) -> C {
        C::new(self.re - o.re, self.im - o.im)
    }
    /// NumPy's complex128 division (Smith's method, `loops.c.src`).
    fn div(self, o: C) -> C {
        let (ar, ai, br, bi) = (self.re, self.im, o.re, o.im);
        if br.abs() >= bi.abs() {
            if br == 0.0 && bi == 0.0 {
                return C::new(ar / br.abs(), ai / br.abs());
            }
            let rat = bi / br;
            let scl = 1.0 / (br + bi * rat);
            C::new((ar + ai * rat) * scl, (ai - ar * rat) * scl)
        } else {
            let rat = br / bi;
            let scl = 1.0 / (bi + br * rat);
            C::new((ar * rat + ai) * scl, (ai * rat - ar) * scl)
        }
    }
}

/// The two receptors' values and flags of one term at one (antenna, time,
/// channel). For Df the values are the leakages `d_x, d_y`.
#[derive(Clone, Copy, Debug, Default)]
struct Rec {
    v: [C; 2],
    f: [bool; 2],
}

fn err<T>(message: impl Into<String>) -> Result<T, String> {
    Err(message.into())
}

/// Check every length and index; the first problem as a message.
pub fn check(chunk: &Chunk, terms: &[Term]) -> Result<(), String> {
    let cells = chunk
        .nrow
        .checked_mul(chunk.nchan)
        .ok_or("cell count overflows")?;
    if chunk.data.len() != 8 * cells || chunk.flags.len() != 4 * cells {
        return err("data must be (row, chan, 4) complex64 and flags (row, chan, 4)");
    }
    if chunk.time.len() != chunk.nrow
        || chunk.antenna1.len() != chunk.nrow
        || chunk.antenna2.len() != chunk.nrow
    {
        return err("time, antenna1 and antenna2 must have one value per row");
    }
    if chunk
        .first_chan
        .checked_add(chunk.nchan)
        .is_none_or(|end| end > chunk.freq.len())
    {
        return err("freq must have one value per channel of the window");
    }
    if chunk.freq.iter().any(|f| !f.is_finite()) || chunk.time.iter().any(|t| !t.is_finite()) {
        return err("freq and time must be finite");
    }
    for (&a, &b) in chunk.antenna1.iter().zip(chunk.antenna2) {
        if a as usize >= chunk.nant || b as usize >= chunk.nant {
            return err(format!(
                "antenna index {} or {} not below nant {}",
                a, b, chunk.nant
            ));
        }
    }
    for (i, t) in terms.iter().enumerate() {
        if let Some(message) = t.kind.not_yet() {
            return err(format!("term {i}: {message}"));
        }
        if t.npar != t.kind.npar() {
            return err(format!(
                "term {i}: {:?} has {} parameters per channel, not {}",
                t.kind,
                t.kind.npar(),
                t.npar
            ));
        }
        if t.slot_start.len() != chunk.nant + 1 || t.slot_start[0] != 0 {
            return err(format!(
                "term {i}: slot_start must hold nant + 1 offsets from 0"
            ));
        }
        if t.slot_start.windows(2).any(|w| w[1] < w[0]) {
            return err(format!("term {i}: slot_start must not decrease"));
        }
        let nslot = t.slot_start[chunk.nant];
        if t.slot_time.len() != nslot {
            return err(format!("term {i}: slot_time must hold {nslot} times"));
        }
        if t.slot_time.iter().any(|x| !x.is_finite()) {
            return err(format!("term {i}: slot times must be finite"));
        }
        for a in 0..chunk.nant {
            let s = &t.slot_time[t.slot_start[a]..t.slot_start[a + 1]];
            if s.windows(2).any(|w| w[1] < w[0]) {
                return err(format!(
                    "term {i}: antenna {a}'s slots are not sorted by time"
                ));
            }
        }
        if t.nchan_sol == 0 || t.sol_freq.len() != t.nchan_sol {
            return err(format!(
                "term {i}: sol_freq must hold nchan_sol > 0 frequencies"
            ));
        }
        if t.sol_freq.iter().any(|f| !f.is_finite()) || !t.k_ref_freq.is_finite() {
            return err(format!("term {i}: solution frequencies must be finite"));
        }
        let ncell = nslot * t.nchan_sol * t.npar;
        let nfloat = if t.kind.float_param() { 1 } else { 2 };
        if t.params.len() != ncell * nfloat || t.flags.len() != ncell {
            return err(format!(
                "term {i}: params must hold {} floats and flags {} values",
                ncell * nfloat,
                ncell
            ));
        }
    }
    Ok(())
}

/// One antenna's solutions as float32 series `(slot, chan_sol, par, nf)`:
/// complex parameters as amplitude and phase (`atan2`, not tracked), float
/// parameters as they are. CASA tracks phases only over the rows it reads
/// for one interpolation (`CTTimeInterp1::interpolate` reads the bracketing
/// pair, or one row for `nearest` and exact times, through
/// `fparamArray(rows)`), so tracking is done per pair in `interpolate_time`
/// (task C4b, research/c4b-apply-ms.md; C4a tracked along the whole series).
fn series(t: &Term, ant: usize) -> Vec<f32> {
    let (s0, s1) = (t.slot_start[ant], t.slot_start[ant + 1]);
    let per = t.nchan_sol * t.npar;
    if t.kind.float_param() {
        return t.params[s0 * per..s1 * per].to_vec();
    }
    let n = s1 - s0;
    let mut out = vec![0f32; n * per * 2];
    for s in 0..n {
        for k in 0..per {
            let base = 2 * ((s0 + s) * per + k);
            let (re, im) = (t.params[base], t.params[base + 1]);
            out[2 * (s * per + k)] = re.hypot(im);
            out[2 * (s * per + k) + 1] = im.atan2(re);
        }
    }
    out
}

/// `RIorAPArray::trackPhase` (`RIorAParray.cc`) of `cur` after `prev`:
/// float phases compared with the previous one's plus or minus pi in
/// double, each 2 pi step rounded back to float (run -03 of
/// research/c4a-apply.md found `caltable._track_phase`'s float32 whole
/// turns can differ by an ulp).
fn track(prev: f32, cur: f32) -> f32 {
    use std::f64::consts::{PI, TAU};
    let prev = f64::from(prev);
    let mut cur = cur;
    if f64::from(cur) > prev {
        while f64::from(cur) > prev + PI {
            cur = (f64::from(cur) - TAU) as f32;
        }
    }
    if f64::from(cur) < prev {
        while f64::from(cur) < prev - PI {
            cur = (f64::from(cur) + TAU) as f32;
        }
    }
    cur
}

/// `caltable._interpolate` at one time: the values `(chan_sol, par, nf)`
/// and flags `(chan_sol, par)` of an antenna's series.
fn interpolate_time(
    t: &Term,
    times: &[f64],
    vals: &[f32],
    flags: &[u8],
    at: f64,
    out: &mut [f32],
    oflag: &mut [bool],
) {
    let n = times.len();
    let per_f = oflag.len();
    let per_v = out.len();
    let reference = (times[0] - 1.0).floor();
    let rel = |x: f64| (x - reference) as f32;
    let x = rel(at);
    let take = |i: usize, out: &mut [f32], oflag: &mut [bool]| {
        out.copy_from_slice(&vals[i * per_v..(i + 1) * per_v]);
        for (o, &f) in oflag.iter_mut().zip(&flags[i * per_f..(i + 1) * per_f]) {
            *o = f != 0;
        }
    };
    if t.time_interp == Interp::Nearest {
        let mut best = 0;
        let mut best_d = (rel(times[0]) - x).abs();
        for (i, &ti) in times.iter().enumerate().skip(1) {
            let d = (rel(ti) - x).abs();
            if d < best_d {
                best = i;
                best_d = d;
            }
        }
        take(best, out, oflag);
        return;
    }
    let first = rel(times[0]);
    let last = rel(times[n - 1]);
    let (i, exact) = if n == 1 || x <= first {
        (0, true)
    } else if x >= last {
        (n - 1, true)
    } else {
        // searchsorted(side='right') - 1 over the float32 relative times.
        let i = times.partition_point(|&ti| rel(ti) <= x) - 1;
        (i, rel(times[i]) == x)
    };
    if exact {
        take(i, out, oflag);
        return;
    }
    let (x0, x1) = (rel(times[i]), rel(times[i + 1]));
    let dx = x - x0;
    let span = x1 - x0;
    let complex = !t.kind.float_param();
    // casacore 3.7.1 `Interpolate1D<Float, Array<Float>>` linear (read in
    // `rang-casacore-cpp:3.7.1`, `Interpolate1D.tcc`):
    // `y1 + ((x - x1) / (x2 - x1)) * (y2 - y1)` in float (task C4b; C4a used
    // `caltable.py`'s `y0 + (x - x0) (y1 - y0) / (x1 - x0)`).
    let frac = dx / span;
    for k in 0..per_v {
        let y0 = vals[i * per_v + k];
        let mut y1 = vals[(i + 1) * per_v + k];
        if complex && k % 2 == 1 {
            y1 = track(y0, y1); // the phase of the pair, tracked
        }
        out[k] = y0 + frac * (y1 - y0);
    }
    for k in 0..per_f {
        oflag[k] = flags[i * per_f + k] != 0 || flags[(i + 1) * per_f + k] != 0;
    }
}

/// `caltable._resample_freq` (`linear`) or the nearest unflagged channel
/// (`nearest`): per parameter, the values `(nchan, par, nf)` and flags
/// `(nchan, par)` at the data channels from the time-interpolated
/// `(chan_sol, par, nf)` values. GHz abscissae.
#[allow(clippy::too_many_arguments)]
fn resample_freq(
    t: &Term,
    fin: &[f64],
    fout: &[f64],
    vals: &[f32],
    flags: &[bool],
    nf: usize,
    good: &mut Vec<usize>,
    y: &mut Vec<f32>,
    out: &mut [f32],
    oflag: &mut [bool],
) {
    let npar = t.npar;
    let nout = fout.len();
    for p in 0..npar {
        good.clear();
        good.extend((0..t.nchan_sol).filter(|&c| !flags[c * npar + p]));
        if good.is_empty() {
            for c in 0..nout {
                oflag[c * npar + p] = true;
                for q in 0..nf {
                    out[(c * npar + p) * nf + q] = 0.0;
                }
            }
            continue;
        }
        for c in 0..nout {
            oflag[c * npar + p] = false;
        }
        let same = good.len() == nout
            && good
                .iter()
                .zip(fout)
                .all(|(&g, &f)| (f - fin[g]).abs() <= 1e-10);
        let m = good.len();
        let (lo, hi) = (fin[good[0]], fin[good[m - 1]]);
        for q in 0..nf {
            y.clear();
            y.extend(good.iter().map(|&g| vals[(g * npar + p) * nf + q]));
            if same {
                for c in 0..nout {
                    out[(c * npar + p) * nf + q] = y[c];
                }
                continue;
            }
            if !t.kind.float_param() && q == 1 {
                // Unwrap the phase in float32 as `CTPatchedInterp::
                // resampleInFreq` does, for both modes: the difference of two
                // floats compared with pi, each 2 pi step rounded back to
                // float. Large unwrapped phases lose precision there, and the
                // result must lose it the same way (runs -03 and -04 of
                // research/c4a-apply.md; `caltable.py` unwraps in float64 and
                // casts once, and only for `linear`).
                for i in 1..y.len() {
                    let prev = y[i - 1];
                    while f64::from(y[i] - prev) > std::f64::consts::PI {
                        y[i] = (f64::from(y[i]) - std::f64::consts::TAU) as f32;
                    }
                    while f64::from(y[i] - prev) < -std::f64::consts::PI {
                        y[i] = (f64::from(y[i]) + std::f64::consts::TAU) as f32;
                    }
                }
            }
            // Nearest beyond the end channels, then casacore's
            // `InterpolateArray1D<Double, Float>` inside (`InterpolateArray1D.tcc`
            // of casacore 3.7.1): `frac = (x - x1) / (x2 - x1)` in double,
            // `y1 + frac * (y2 - y1)` with the difference in float.
            let (lo_v, hi_v) = (y[0], y[m - 1]);
            for (c, &x) in fout.iter().enumerate() {
                let r = if x >= hi {
                    hi_v
                } else if x <= lo {
                    lo_v
                } else {
                    let i = good.partition_point(|&g| fin[g] <= x) - 1;
                    let i = i.min(m - 2);
                    let (x0, x1) = (fin[good[i]], fin[good[i + 1]]);
                    if t.freq_interp == Interp::Nearest {
                        // Ties to the lower channel, as casacore.
                        if (x1 - x).abs() < (x0 - x).abs() {
                            y[i + 1]
                        } else {
                            y[i]
                        }
                    } else {
                        let frac = (x - x0) / (x1 - x0);
                        (f64::from(y[i]) + frac * f64::from(y[i + 1] - y[i])) as f32
                    }
                };
                out[(c * npar + p) * nf + q] = r;
            }
        }
    }
}

/// The per-receptor values of one term at one (antenna, time) for every
/// data channel. An antenna without solutions is flagged (values 1), as
/// `caltable.jones_terms`.
#[allow(clippy::too_many_arguments)]
fn fill(
    t: &Term,
    ant: usize,
    series_vals: &[f32],
    at: f64,
    fin_ghz: &[f64],
    fout_ghz: &[f64],
    k_ref_ghz: f64,
    out: &mut [Rec],
) {
    let (s0, s1) = (t.slot_start[ant], t.slot_start[ant + 1]);
    if s0 == s1 {
        for r in out.iter_mut() {
            *r = Rec {
                v: [C::ONE; 2],
                f: [true; 2],
            };
        }
        return;
    }
    let nf = if t.kind.float_param() { 1 } else { 2 };
    let per_f = t.nchan_sol * t.npar;
    let mut tv = vec![0f32; per_f * nf];
    let mut tf = vec![false; per_f];
    interpolate_time(
        t,
        &t.slot_time[s0..s1],
        series_vals,
        &t.flags[s0 * per_f..s1 * per_f],
        at,
        &mut tv,
        &mut tf,
    );
    let nout = fout_ghz.len();
    let mut fv = vec![0f32; nout * t.npar * nf];
    let mut ff = vec![false; nout * t.npar];
    let (mut good, mut y) = (Vec::new(), Vec::new());
    resample_freq(
        t, fin_ghz, fout_ghz, &tv, &tf, nf, &mut good, &mut y, &mut fv, &mut ff,
    );
    let npar = t.npar;
    for (c, r) in out.iter_mut().enumerate() {
        let par = |p: usize| -> C {
            let base = (c * npar + p) * nf;
            if nf == 1 {
                C::new(f64::from(fv[base]), 0.0)
            } else {
                let (a, ph) = (fv[base], fv[base + 1]);
                C::new(f64::from(a * ph.cos()), f64::from(a * ph.sin()))
            }
        };
        let flag = |p: usize| ff[c * npar + p];
        *r = match t.kind {
            Kind::K | Kind::KCross => {
                let dnu = fout_ghz[c] - k_ref_ghz;
                let v: [C; 2] = std::array::from_fn(|p| {
                    let phase = std::f64::consts::TAU * par(p).re * dnu;
                    C::new(phase.cos(), phase.sin())
                });
                Rec {
                    v,
                    f: [flag(0), flag(1)],
                }
            }
            Kind::T => Rec {
                v: [par(0), par(0)],
                f: [flag(0), flag(0)],
            },
            Kind::Xf => Rec {
                v: [par(0), C::ONE],
                f: [flag(0), flag(0)],
            },
            _ => Rec {
                v: [par(0), par(1)],
                f: [flag(0), flag(1)],
            },
        };
    }
}

/// Correct or corrupt `chunk` by `terms` into `out_data` (interleaved
/// complex64, as `data`) and `out_flags` (input flags OR the terms' flags).
/// `threads` 0 uses the current rayon pool.
pub fn apply(
    chunk: &Chunk,
    terms: &[Term],
    direction: Direction,
    threads: usize,
    out_data: &mut [f32],
    out_flags: &mut [u8],
) -> Result<(), String> {
    check(chunk, terms)?;
    if out_data.len() != chunk.data.len() || out_flags.len() != chunk.flags.len() {
        return err("outputs must have the shapes of data and flags");
    }
    if threads == 0 {
        run(chunk, terms, direction, out_data, out_flags);
        return Ok(());
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .map_err(|e| e.to_string())?;
    pool.install(|| run(chunk, terms, direction, out_data, out_flags));
    Ok(())
}

fn run(
    chunk: &Chunk,
    terms: &[Term],
    direction: Direction,
    out_data: &mut [f32],
    out_flags: &mut [u8],
) {
    let (nrow, nchan, nant) = (chunk.nrow, chunk.nchan, chunk.nant);
    // Unique row times (exact), and the (antenna, time) pairs in use.
    let mut times: Vec<f64> = chunk.time.to_vec();
    times.sort_by(|a, b| a.total_cmp(b));
    times.dedup();
    let ntime = times.len();
    let tindex: Vec<usize> = chunk
        .time
        .iter()
        .map(|t| times.partition_point(|x| x < t))
        .collect();
    let mut used = vec![false; nant * ntime];
    for r in 0..nrow {
        used[chunk.antenna1[r] as usize * ntime + tindex[r]] = true;
        used[chunk.antenna2[r] as usize * ntime + tindex[r]] = true;
    }
    let mut pair = vec![usize::MAX; nant * ntime];
    let mut pairs = Vec::new();
    for (k, &u) in used.iter().enumerate() {
        if u {
            pair[k] = pairs.len();
            pairs.push((k / ntime, times[k % ntime]));
        }
    }
    // Terms in VisCal order (stable for equal keys).
    let mut order: Vec<usize> = (0..terms.len()).collect();
    order.sort_by_key(|&i| terms[i].kind.type_key());
    if direction == Direction::Corrupt {
        order.reverse();
    }
    let fout_ghz: Vec<f64> = chunk.freq.iter().map(|f| f / 1e9).collect();
    let (nband, first) = (chunk.freq.len(), chunk.first_chan);
    let tables: Vec<Vec<Rec>> = order
        .iter()
        .map(|&i| {
            let t = &terms[i];
            let fin_ghz: Vec<f64> = t.sol_freq.iter().map(|f| f / 1e9).collect();
            let k_ref_ghz = t.k_ref_freq / 1e9;
            let ser: Vec<Vec<f32>> = (0..nant).into_par_iter().map(|a| series(t, a)).collect();
            let mut table = vec![Rec::default(); pairs.len() * nband];
            table
                .par_chunks_mut(nband.max(1))
                .zip(pairs.par_iter())
                .for_each(|(out, &(a, at))| {
                    fill(t, a, &ser[a], at, &fin_ghz, &fout_ghz, k_ref_ghz, out)
                });
            table
        })
        .collect();
    let kinds: Vec<Kind> = order.iter().map(|&i| terms[i].kind).collect();
    const POLS: [(usize, usize); 4] = [(0, 0), (0, 1), (1, 0), (1, 1)];
    out_data
        .par_chunks_mut(8 * nchan.max(1))
        .zip(out_flags.par_chunks_mut(4 * nchan.max(1)))
        .enumerate()
        .for_each(|(r, (od, of))| {
            let p1 = pair[chunk.antenna1[r] as usize * ntime + tindex[r]];
            let p2 = pair[chunk.antenna2[r] as usize * ntime + tindex[r]];
            for c in 0..nchan {
                let cell = r * nchan + c;
                let mut v: [C; 4] = std::array::from_fn(|k| {
                    C::new(
                        f64::from(chunk.data[8 * cell + 2 * k]),
                        f64::from(chunk.data[8 * cell + 2 * k + 1]),
                    )
                });
                let mut f: [bool; 4] = std::array::from_fn(|k| chunk.flags[4 * cell + k] != 0);
                // Flags, in VisCal (correct) order for both directions, so
                // that corrupt and correct flag the same cells.
                let mut flag_term = |table: &[Rec], kind: Kind| {
                    let gp = table[p1 * nband + first + c];
                    let gq = table[p2 * nband + first + c];
                    if kind == Kind::Df {
                        // `JonesGenLin::flagRight` then `flagLeft`
                        // (`Jones.cc`): a cross hand is flagged by a bad
                        // leakage it uses or by a flagged parallel hand,
                        // input flags included; Df never flags XX or YY.
                        f[1] |= gp.f[0] || f[3] || gq.f[1] || f[0];
                        f[2] |= gp.f[1] || f[0] || gq.f[0] || f[3];
                    } else {
                        for (k, &(a, b)) in POLS.iter().enumerate() {
                            f[k] |= gp.f[a] || gq.f[b];
                        }
                    }
                };
                if direction == Direction::Correct {
                    for (table, &kind) in tables.iter().zip(&kinds) {
                        flag_term(table, kind);
                    }
                } else {
                    for (table, &kind) in tables.iter().zip(&kinds).rev() {
                        flag_term(table, kind);
                    }
                }
                for (table, &kind) in tables.iter().zip(&kinds) {
                    let gp = table[p1 * nband + first + c];
                    let gq = table[p2 * nband + first + c];
                    if kind == Kind::Df {
                        // `JonesGenLin::setMatByOk` after `invert`: when either
                        // leakage of an antenna is bad, both inverted elements
                        // become 1, which is d = -1 in this formula.
                        let leak = |r: &Rec| {
                            if r.f[0] || r.f[1] {
                                [C::new(-1.0, 0.0); 2]
                            } else {
                                r.v
                            }
                        };
                        let (dp, dq) = (leak(&gp), leak(&gq));
                        let (xx, yy) = (v[0], v[3]);
                        let dxy = dp[0].mul(yy).add(dq[1].conj().mul(xx));
                        let dyx = dp[1].mul(xx).add(dq[0].conj().mul(yy));
                        if direction == Direction::Correct {
                            v[1] = v[1].sub(dxy);
                            v[2] = v[2].sub(dyx);
                        } else {
                            v[1] = v[1].add(dxy);
                            v[2] = v[2].add(dyx);
                        }
                        continue;
                    }
                    for (k, &(a, b)) in POLS.iter().enumerate() {
                        // `JonesDiag::setMatByOk`: a bad receptor is 1 on its
                        // own side only; the other side is still applied, as
                        // CASA writes it (task C4b, research/c4b-apply-ms.md).
                        if gp.f[a] && gq.f[b] {
                            continue;
                        }
                        let ga = if gp.f[a] { C::ONE } else { gp.v[a] };
                        let gb = if gq.f[b] { C::ONE } else { gq.v[b] };
                        let g = ga.mul(gb.conj());
                        v[k] = match direction {
                            Direction::Correct => v[k].div(g),
                            Direction::Corrupt => v[k].mul(g),
                        };
                    }
                }
                for k in 0..4 {
                    od[8 * c + 2 * k] = v[k].re as f32;
                    od[8 * c + 2 * k + 1] = v[k].im as f32;
                    of[4 * c + k] = u8::from(f[k]);
                }
            }
        });
}

/// A general 2x2 term on its own solution bins (task C4b): the gains of
/// `rang.core.solve_complex`, `(time_bin, freq_bin, antenna, 2, 2)`.
pub struct BinnedJones<'a> {
    pub ntime_bins: usize,
    pub nfreq_bins: usize,
    /// Interleaved complex128 `(t, f, ant, 2, 2)`, row-major elements
    /// `[[XX, XY], [YX, YY]]`.
    pub gains: &'a [f64],
    /// `(t, f, ant)`: nonzero where the gain is valid.
    pub valid: &'a [u8],
    /// The time bin of each row and the frequency bin of each channel.
    pub time_bin: &'a [u32],
    pub freq_bin: &'a [u32],
}

type M2 = [C; 4];

/// The inverse of a 2x2 matrix, or None when it is singular or not finite.
fn inverse(m: &M2) -> Option<M2> {
    let det = m[0].mul(m[3]).sub(m[1].mul(m[2]));
    if !(det.re.is_finite() && det.im.is_finite()) || (det.re == 0.0 && det.im == 0.0) {
        return None;
    }
    let one = C::ONE;
    let r = one.div(det);
    let neg = |c: C| C::new(-c.re, -c.im);
    Some([m[3].mul(r), neg(m[1]).mul(r), neg(m[2]).mul(r), m[0].mul(r)])
}

fn mat_mul(a: &M2, b: &M2) -> M2 {
    [
        a[0].mul(b[0]).add(a[1].mul(b[2])),
        a[0].mul(b[1]).add(a[1].mul(b[3])),
        a[2].mul(b[0]).add(a[3].mul(b[2])),
        a[2].mul(b[1]).add(a[3].mul(b[3])),
    ]
}

fn adjoint(a: &M2) -> M2 {
    [a[0].conj(), a[2].conj(), a[1].conj(), a[3].conj()]
}

/// Correct (`V <- G_p^-1 V G_q^-H`) or corrupt (`V <- G_p V G_q^H`)
/// `chunk` by one binned general term into `out_data` and `out_flags`
/// (input flags OR the term's). A gain that is invalid, singular or not
/// finite is bad: its side is the identity and the cell is flagged. CASA's
/// `Jones::flagRight` then `flagLeft` flag a correlation when any
/// correlation of the cell is flagged or either side is bad, so a cell is
/// flagged in all four or none. `chunk.time` and `chunk.freq` are not used.
pub fn apply_jones(
    chunk: &Chunk,
    term: &BinnedJones,
    direction: Direction,
    threads: usize,
    out_data: &mut [f32],
    out_flags: &mut [u8],
) -> Result<(), String> {
    let (nrow, nchan, nant) = (chunk.nrow, chunk.nchan, chunk.nant);
    let cells = nrow * nchan;
    if chunk.data.len() != 8 * cells || chunk.flags.len() != 4 * cells {
        return err("data must be (row, chan, 4) complex64 and flags (row, chan, 4)");
    }
    if chunk.antenna1.len() != nrow || chunk.antenna2.len() != nrow {
        return err("antenna1 and antenna2 must have one value per row");
    }
    if term.time_bin.len() != nrow || term.freq_bin.len() != nchan {
        return err("time_bin must have one value per row and freq_bin one per channel");
    }
    let nsol = term.ntime_bins * term.nfreq_bins * nant;
    if term.gains.len() != 8 * nsol || term.valid.len() != nsol {
        return err(
            "gains must be (time_bin, freq_bin, antenna, 2, 2) and valid (time_bin, freq_bin, antenna)",
        );
    }
    if out_data.len() != chunk.data.len() || out_flags.len() != chunk.flags.len() {
        return err("outputs must have the shapes of data and flags");
    }
    if chunk
        .antenna1
        .iter()
        .chain(chunk.antenna2)
        .any(|&a| a as usize >= nant)
    {
        return err("an antenna index is not below nant");
    }
    if term.time_bin.iter().any(|&t| t as usize >= term.ntime_bins)
        || term.freq_bin.iter().any(|&f| f as usize >= term.nfreq_bins)
    {
        return err("a time or frequency bin is out of range");
    }
    // Per solution: the matrix applied on each side (inverse or gain) or
    // None when bad.
    let mats: Vec<Option<M2>> = (0..nsol)
        .into_par_iter()
        .map(|s| {
            if term.valid[s] == 0 {
                return None;
            }
            let g = &term.gains[8 * s..8 * s + 8];
            let m: M2 = std::array::from_fn(|k| C::new(g[2 * k], g[2 * k + 1]));
            let inv = inverse(&m)?;
            Some(match direction {
                Direction::Correct => inv,
                Direction::Corrupt => m,
            })
        })
        .collect();
    let body = |out_data: &mut [f32], out_flags: &mut [u8]| {
        out_data
            .par_chunks_mut(8 * nchan.max(1))
            .zip(out_flags.par_chunks_mut(4 * nchan.max(1)))
            .enumerate()
            .for_each(|(r, (od, of))| {
                let tb = term.time_bin[r] as usize;
                for c in 0..nchan {
                    let cell = r * nchan + c;
                    let base = (tb * term.nfreq_bins + term.freq_bin[c] as usize) * nant;
                    let mp = mats[base + chunk.antenna1[r] as usize];
                    let mq = mats[base + chunk.antenna2[r] as usize];
                    let mut v: M2 = std::array::from_fn(|k| {
                        C::new(
                            f64::from(chunk.data[8 * cell + 2 * k]),
                            f64::from(chunk.data[8 * cell + 2 * k + 1]),
                        )
                    });
                    let any = (0..4).any(|k| chunk.flags[4 * cell + k] != 0);
                    let flag = any || mp.is_none() || mq.is_none();
                    if let Some(p) = mp {
                        v = mat_mul(&p, &v);
                    }
                    if let Some(q) = mq {
                        v = mat_mul(&v, &adjoint(&q));
                    }
                    for k in 0..4 {
                        od[8 * c + 2 * k] = v[k].re as f32;
                        od[8 * c + 2 * k + 1] = v[k].im as f32;
                        of[4 * c + k] = u8::from(flag);
                    }
                }
            });
    };
    if threads == 0 {
        body(out_data, out_flags);
        return Ok(());
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .map_err(|e| e.to_string())?;
    pool.install(|| body(out_data, out_flags));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A seeded xorshift generator (no crate), values in [-1, 1).
    struct Rng(u64);
    impl Rng {
        fn next(&mut self) -> f64 {
            self.0 ^= self.0 << 13;
            self.0 ^= self.0 >> 7;
            self.0 ^= self.0 << 17;
            (self.0 >> 11) as f64 / (1u64 << 52) as f64 - 1.0
        }
    }

    struct Owned {
        kind: Kind,
        time_interp: Interp,
        freq_interp: Interp,
        slot_start: Vec<usize>,
        slot_time: Vec<f64>,
        nchan_sol: usize,
        params: Vec<f32>,
        flags: Vec<u8>,
        sol_freq: Vec<f64>,
    }

    impl Owned {
        fn term(&self) -> Term<'_> {
            Term {
                kind: self.kind,
                time_interp: self.time_interp,
                freq_interp: self.freq_interp,
                slot_start: &self.slot_start,
                slot_time: &self.slot_time,
                nchan_sol: self.nchan_sol,
                npar: self.kind.npar(),
                params: &self.params,
                flags: &self.flags,
                sol_freq: &self.sol_freq,
                k_ref_freq: self.sol_freq[self.nchan_sol / 2],
            }
        }
    }

    const NANT: usize = 6;
    const NTIME: usize = 20;
    const NCHAN: usize = 64;

    fn freqs(n: usize) -> Vec<f64> {
        (0..n)
            .map(|c| 1.0e9 + 1.0e9 * c as f64 / n as f64)
            .collect()
    }

    fn make_term(rng: &mut Rng, kind: Kind, nslot: usize, nchan_sol: usize) -> Owned {
        let npar = kind.npar();
        let mut params = Vec::new();
        let mut flags = Vec::new();
        let mut slot_time = Vec::new();
        for _a in 0..NANT {
            for s in 0..nslot {
                slot_time.push(100.0 + 8.0 * NTIME as f64 * (s as f64 + 0.5) / nslot as f64);
                for c in 0..nchan_sol {
                    for p in 0..npar {
                        match kind {
                            Kind::K => params.push((5.0 * rng.next()) as f32),
                            Kind::Df => {
                                params.push((0.05 * rng.next()) as f32);
                                params.push((0.05 * rng.next()) as f32);
                            }
                            _ => {
                                let amp = 1.0 + 0.2 * rng.next();
                                let ph = 3.0 * rng.next();
                                params.push((amp * ph.cos()) as f32);
                                params.push((amp * ph.sin()) as f32);
                            }
                        }
                        let flagged = (kind == Kind::G && s == 1 && p == 1)
                            || (kind == Kind::B && (4..7).contains(&c))
                            || (kind == Kind::Df && c == 9);
                        flags.push(u8::from(flagged));
                    }
                }
            }
        }
        Owned {
            kind,
            time_interp: Interp::Linear,
            freq_interp: Interp::Linear,
            slot_start: (0..=NANT).map(|a| a * nslot).collect(),
            slot_time,
            nchan_sol,
            params,
            flags,
            sol_freq: freqs(nchan_sol),
        }
    }

    struct Vis {
        data: Vec<f32>,
        flags: Vec<u8>,
        time: Vec<f64>,
        a1: Vec<u32>,
        a2: Vec<u32>,
        freq: Vec<f64>,
    }

    impl Vis {
        fn chunk(&self) -> Chunk<'_> {
            Chunk {
                nrow: self.time.len(),
                nchan: NCHAN,
                nant: NANT,
                data: &self.data,
                flags: &self.flags,
                time: &self.time,
                antenna1: &self.a1,
                antenna2: &self.a2,
                freq: &self.freq,
                first_chan: 0,
            }
        }
    }

    fn vis(rng: &mut Rng) -> Vis {
        let (mut time, mut a1, mut a2) = (Vec::new(), Vec::new(), Vec::new());
        for t in 0..NTIME {
            for p in 0..NANT {
                for q in p + 1..NANT {
                    time.push(100.0 + 8.0 * t as f64 + 4.0);
                    a1.push(p as u32);
                    a2.push(q as u32);
                }
            }
        }
        let n = time.len() * NCHAN;
        let data = (0..8 * n).map(|_| (10.0 * rng.next()) as f32).collect();
        let flags = (0..4 * n).map(|_| u8::from(rng.next() > 0.9)).collect();
        Vis {
            data,
            flags,
            time,
            a1,
            a2,
            freq: freqs(NCHAN),
        }
    }

    fn terms(rng: &mut Rng) -> Vec<Owned> {
        vec![
            make_term(rng, Kind::G, 5, 1),
            make_term(rng, Kind::Df, 1, NCHAN),
            make_term(rng, Kind::K, 1, 1),
            make_term(rng, Kind::B, 1, 16),
        ]
    }

    fn run_with(v: &Vis, t: &[Owned], dir: Direction, threads: usize) -> (Vec<f32>, Vec<u8>) {
        let terms: Vec<Term> = t.iter().map(Owned::term).collect();
        let mut od = vec![0f32; v.data.len()];
        let mut of = vec![0u8; v.flags.len()];
        apply(&v.chunk(), &terms, dir, threads, &mut od, &mut of).unwrap();
        (od, of)
    }

    #[test]
    fn bit_identical_across_thread_counts() {
        let mut rng = Rng(20261106);
        let v = vis(&mut rng);
        let mut t = terms(&mut rng);
        for (time_interp, freq_interp) in [
            (Interp::Linear, Interp::Linear),
            (Interp::Nearest, Interp::Nearest),
        ] {
            for o in t.iter_mut() {
                o.time_interp = time_interp;
                o.freq_interp = freq_interp;
            }
            for dir in [Direction::Correct, Direction::Corrupt] {
                let (d1, f1) = run_with(&v, &t, dir, 1);
                for threads in [2, 4, 16] {
                    let (d, f) = run_with(&v, &t, dir, threads);
                    assert!(d.iter().zip(&d1).all(|(a, b)| a.to_bits() == b.to_bits()));
                    assert_eq!(f, f1);
                }
            }
        }
    }

    #[test]
    fn round_trip_class_c() {
        let mut rng = Rng(20261106);
        let v = vis(&mut rng);
        let t = terms(&mut rng);
        let (cd, cf) = run_with(&v, &t, Direction::Corrupt, 0);
        let back = Vis {
            data: cd,
            flags: v.flags.clone(),
            time: v.time.clone(),
            a1: v.a1.clone(),
            a2: v.a2.clone(),
            freq: v.freq.clone(),
        };
        let (rd, rf) = run_with(&back, &t, Direction::Correct, 0);
        assert_eq!(cf, rf);
        assert!(rf.iter().zip(&v.flags).all(|(&o, &i)| o >= i));
        assert!(rf.contains(&1) && rf.contains(&0));
        let eps = f64::from(f32::EPSILON);
        let mut compared = 0;
        for cell in 0..v.time.len() * NCHAN {
            let orig: Vec<(f64, f64)> = (0..4)
                .map(|k| {
                    (
                        f64::from(v.data[8 * cell + 2 * k]),
                        f64::from(v.data[8 * cell + 2 * k + 1]),
                    )
                })
                .collect();
            let scale = orig.iter().map(|(a, b)| a.hypot(*b)).fold(0.0, f64::max);
            for k in 0..4 {
                if rf[4 * cell + k] != 0 {
                    continue;
                }
                let (gr, gi) = (
                    f64::from(rd[8 * cell + 2 * k]),
                    f64::from(rd[8 * cell + 2 * k + 1]),
                );
                let e = (gr - orig[k].0).hypot(gi - orig[k].1);
                let mag = orig[k].0.hypot(orig[k].1);
                assert!(
                    e <= 1e-6 * mag || e <= 11.0 * eps * scale,
                    "cell {cell} corr {k}: error {e}, scale {scale}"
                );
                compared += 1;
            }
        }
        assert!(compared > 1000);
    }

    #[test]
    fn diagonal_g_by_hand() {
        let freq = [1.4e9];
        let data = [2.0f32, 1.0, 0.5, 0.5, 0.25, -0.5, 3.0, 0.0];
        let flags = [0u8; 4];
        let chunk = Chunk {
            nrow: 1,
            nchan: 1,
            nant: 2,
            data: &data,
            flags: &flags,
            time: &[10.0],
            antenna1: &[0],
            antenna2: &[1],
            freq: &freq,
            first_chan: 0,
        };
        // g_0 = (2, 1j), g_1 = (1, 1 + 1j), one slot each.
        let params = [2.0f32, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0];
        let tflags = [0u8; 4];
        let term = Term {
            kind: Kind::G,
            time_interp: Interp::Linear,
            freq_interp: Interp::Linear,
            slot_start: &[0, 1, 2],
            slot_time: &[10.0, 10.0],
            nchan_sol: 1,
            npar: 2,
            params: &params,
            flags: &tflags,
            sol_freq: &freq,
            k_ref_freq: freq[0],
        };
        let mut od = [0f32; 8];
        let mut of = [0u8; 4];
        apply(&chunk, &[term], Direction::Correct, 0, &mut od, &mut of).unwrap();
        let g0 = [C::new(2.0, 0.0), C::new(0.0, 1.0)];
        let g1 = [C::new(1.0, 0.0), C::new(1.0, 1.0)];
        for (k, (a, b)) in [(0, 0), (0, 1), (1, 0), (1, 1)].into_iter().enumerate() {
            let v = C::new(f64::from(data[2 * k]), f64::from(data[2 * k + 1]));
            let want = v.div(g0[a].mul(g1[b].conj()));
            assert!((f64::from(od[2 * k]) - want.re).abs() < 1e-6);
            assert!((f64::from(od[2 * k + 1]) - want.im).abs() < 1e-6);
        }
        assert_eq!(of, [0; 4]);
    }

    #[test]
    fn p_is_refused_as_a_table() {
        let mut rng = Rng(1);
        let v = vis(&mut rng);
        let mut t = make_term(&mut rng, Kind::G, 1, 1);
        t.kind = Kind::P;
        let terms = [t.term()];
        let mut od = vec![0f32; v.data.len()];
        let mut of = vec![0u8; v.flags.len()];
        let e = apply(&v.chunk(), &terms, Direction::Correct, 0, &mut od, &mut of).unwrap_err();
        assert!(e.contains("parang"), "{e}");
    }

    /// One-row, one-time term of `kind` over `NANT` antennas (task C6).
    fn one_slot(kind: Kind, params: Vec<f32>, flags: Vec<u8>, sol_freq: Vec<f64>) -> Owned {
        Owned {
            kind,
            time_interp: Interp::Nearest,
            freq_interp: Interp::Linear,
            slot_start: (0..=NANT).collect(),
            slot_time: vec![150.0; NANT],
            nchan_sol: sol_freq.len(),
            params,
            flags,
            sol_freq,
        }
    }

    #[test]
    fn kcross_is_a_delay_on_x_only() {
        // CASA's Kcross table: the delay in the first parameter, 0 in the
        // second; every antenna holds the array value.
        let mut rng = Rng(5);
        let v = vis(&mut rng);
        let tau = 3.25f32;
        let mid = [1.5e9];
        let params = (0..NANT).flat_map(|_| [tau, 0.0]).collect();
        let t = one_slot(Kind::KCross, params, vec![0; 2 * NANT], mid.to_vec());
        let mut od = vec![0f32; v.data.len()];
        let mut of = vec![0u8; v.flags.len()];
        apply(
            &v.chunk(),
            &[t.term()],
            Direction::Correct,
            0,
            &mut od,
            &mut of,
        )
        .unwrap();
        for cell in 0..v.time.len() * NCHAN {
            let c = cell % NCHAN;
            let ph = std::f64::consts::TAU * f64::from(tau) * (v.freq[c] - mid[0]) / 1e9;
            let kx = C::new(ph.cos(), ph.sin());
            // XX: k conj(k) = 1; XY: k_x; YX: conj(k_x); YY: 1.
            let g = [C::ONE, kx, kx.conj(), C::ONE];
            for (k, gk) in g.iter().enumerate() {
                let d = C::new(
                    f64::from(v.data[8 * cell + 2 * k]),
                    f64::from(v.data[8 * cell + 2 * k + 1]),
                );
                let want = d.div(*gk);
                let got = C::new(
                    f64::from(od[8 * cell + 2 * k]),
                    f64::from(od[8 * cell + 2 * k + 1]),
                );
                assert!((got.re - want.re).abs() < 1e-4 && (got.im - want.im).abs() < 1e-4);
            }
            for k in 0..4 {
                assert_eq!(of[4 * cell + k], v.flags[4 * cell + k]);
            }
        }
    }

    #[test]
    fn xf_is_diag_x_one_and_its_flag_flags_both_receptors() {
        let mut rng = Rng(6);
        let v = vis(&mut rng);
        let x: Vec<C> = (0..NCHAN)
            .map(|c| {
                let a = 0.5 + 0.01 * c as f64;
                C::new(a.cos(), a.sin())
            })
            .collect();
        let mut params = Vec::new();
        let mut flags = Vec::new();
        // Channel 9 flagged everywhere (bridged in frequency, as CASA does);
        // antenna 2 flagged in every channel (both receptors flagged).
        for a in 0..NANT {
            for (c, xc) in x.iter().enumerate() {
                params.push(xc.re as f32);
                params.push(xc.im as f32);
                flags.push(u8::from(c == 9 || a == 2));
            }
        }
        let t = one_slot(Kind::Xf, params, flags, v.freq.clone());
        for dir in [Direction::Correct, Direction::Corrupt] {
            let mut od = vec![0f32; v.data.len()];
            let mut of = vec![0u8; v.flags.len()];
            apply(&v.chunk(), &[t.term()], dir, 0, &mut od, &mut of).unwrap();
            for cell in 0..v.time.len() * NCHAN {
                let (row, c) = (cell / NCHAN, cell % NCHAN);
                let bad = v.a1[row] == 2 || v.a2[row] == 2;
                let xc = C::new(f64::from(x[c].re as f32), f64::from(x[c].im as f32));
                let g = [C::ONE, xc, xc.conj(), C::ONE];
                for (k, gk) in g.iter().enumerate() {
                    let fl = v.flags[4 * cell + k] != 0 || bad;
                    assert_eq!(of[4 * cell + k] != 0, fl, "cell {cell} corr {k}");
                    if bad {
                        continue;
                    }
                    let d = C::new(
                        f64::from(v.data[8 * cell + 2 * k]),
                        f64::from(v.data[8 * cell + 2 * k + 1]),
                    );
                    let want = match dir {
                        Direction::Correct => d.div(*gk),
                        Direction::Corrupt => d.mul(*gk),
                    };
                    let got = C::new(
                        f64::from(od[8 * cell + 2 * k]),
                        f64::from(od[8 * cell + 2 * k + 1]),
                    );
                    assert!((got.re - want.re).abs() < 1e-4 && (got.im - want.im).abs() < 1e-4);
                }
            }
        }
    }

    #[test]
    fn one_sided_diagonal_flag_applies_the_other_side() {
        // `JonesDiag::setMatByOk` (task C4b): g_0's X receptor bad, so XX
        // and XY are flagged and divided by conj(g_1) only.
        let freq = [1.4e9];
        let data = [2.0f32, 1.0, 0.5, 0.5, 0.25, -0.5, 3.0, 0.0];
        let flags = [0u8; 4];
        let chunk = Chunk {
            nrow: 1,
            nchan: 1,
            nant: 2,
            data: &data,
            flags: &flags,
            time: &[10.0],
            antenna1: &[0],
            antenna2: &[1],
            freq: &freq,
            first_chan: 0,
        };
        let params = [2.0f32, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0];
        let tflags = [1u8, 0, 0, 0];
        let term = Term {
            kind: Kind::G,
            time_interp: Interp::Linear,
            freq_interp: Interp::Linear,
            slot_start: &[0, 1, 2],
            slot_time: &[10.0, 10.0],
            nchan_sol: 1,
            npar: 2,
            params: &params,
            flags: &tflags,
            sol_freq: &freq,
            k_ref_freq: freq[0],
        };
        for dir in [Direction::Correct, Direction::Corrupt] {
            let mut od = [0f32; 8];
            let mut of = [0u8; 4];
            let terms = [Term { ..term }];
            apply(&chunk, &terms, dir, 0, &mut od, &mut of).unwrap();
            let g0 = [C::ONE, C::new(0.0, 1.0)];
            let g1 = [C::new(1.0, 0.0), C::new(1.0, 1.0)];
            for (k, (a, b)) in [(0, 0), (0, 1), (1, 0), (1, 1)].into_iter().enumerate() {
                let v = C::new(f64::from(data[2 * k]), f64::from(data[2 * k + 1]));
                let g = g0[a].mul(g1[b].conj());
                let want = if dir == Direction::Correct {
                    v.div(g)
                } else {
                    v.mul(g)
                };
                assert!((f64::from(od[2 * k]) - want.re).abs() < 1e-6);
                assert!((f64::from(od[2 * k + 1]) - want.im).abs() < 1e-6);
            }
            assert_eq!(of, [1, 1, 0, 0]);
        }
    }

    fn jones_case(rng: &mut Rng, nt: usize, nf: usize) -> (Vec<f64>, Vec<u8>, Vec<u32>, Vec<u32>) {
        let nsol = nt * nf * NANT;
        let mut gains = Vec::with_capacity(8 * nsol);
        for _ in 0..nsol {
            for k in 0..4 {
                let diag = k == 0 || k == 3;
                gains.push(if diag {
                    1.0 + 0.3 * rng.next()
                } else {
                    0.1 * rng.next()
                });
                gains.push(0.3 * rng.next());
            }
        }
        let valid = (0..nsol).map(|_| u8::from(rng.next() > -0.8)).collect();
        let ntime = NTIME * NANT * (NANT - 1) / 2;
        let tb = (0..ntime).map(|r| ((r / 15) * nt / NTIME) as u32).collect();
        let fb = (0..NCHAN).map(|c| (c * nf / NCHAN) as u32).collect();
        (gains, valid, tb, fb)
    }

    #[test]
    fn jones_round_trip_threads_and_flags() {
        let mut rng = Rng(20261109);
        let v = vis(&mut rng);
        let (gains, valid, tb, fb) = jones_case(&mut rng, 5, 4);
        let term = BinnedJones {
            ntime_bins: 5,
            nfreq_bins: 4,
            gains: &gains,
            valid: &valid,
            time_bin: &tb,
            freq_bin: &fb,
        };
        let run = |dir, threads, chunk: &Chunk| {
            let mut od = vec![0f32; chunk.data.len()];
            let mut of = vec![0u8; chunk.flags.len()];
            apply_jones(chunk, &term, dir, threads, &mut od, &mut of).unwrap();
            (od, of)
        };
        let (c1, f1) = run(Direction::Correct, 1, &v.chunk());
        for threads in [2, 4, 16] {
            let (c, f) = run(Direction::Correct, threads, &v.chunk());
            assert_eq!(c, c1);
            assert_eq!(f, f1);
        }
        // Flags: all four or none per cell, and the input flags kept.
        for (cell, f) in f1.chunks(4).enumerate() {
            assert!(f.iter().all(|&x| x == f[0]));
            assert!(v.flags[4 * cell..4 * cell + 4].iter().all(|&x| x <= f[0]));
        }
        // Round trip on the cells whose gains are both valid.
        let corrupt = Vis {
            data: c1.clone(),
            flags: v.flags.clone(),
            time: v.time.clone(),
            a1: v.a1.clone(),
            a2: v.a2.clone(),
            freq: v.freq.clone(),
        };
        let (back, fb2) = run(Direction::Corrupt, 0, &corrupt.chunk());
        assert_eq!(fb2, f1);
        let mut compared = 0;
        for r in 0..v.time.len() {
            for (c, &f) in fb.iter().enumerate() {
                let base = (tb[r] as usize * 4 + f as usize) * NANT;
                if valid[base + v.a1[r] as usize] == 0 || valid[base + v.a2[r] as usize] == 0 {
                    continue;
                }
                let cell = r * NCHAN + c;
                let scale = (0..8)
                    .map(|k| v.data[8 * cell + k].abs())
                    .fold(0f32, f32::max);
                for k in 0..8 {
                    let d = (back[8 * cell + k] - v.data[8 * cell + k]).abs();
                    assert!(d <= 1e-5 * scale.max(1.0), "{d}");
                }
                compared += 1;
            }
        }
        assert!(compared > 1000);
    }

    #[test]
    fn jones_by_hand() {
        let data = [1.0f32, 0.0, 0.2, 0.1, 0.3, -0.1, 2.0, 0.0];
        let chunk = Chunk {
            nrow: 1,
            nchan: 1,
            nant: 2,
            data: &data,
            flags: &[0, 0, 0, 0],
            time: &[0.0],
            antenna1: &[0],
            antenna2: &[1],
            freq: &[1e9],
            first_chan: 0,
        };
        // G_0 = [[2, 0.5], [0, 1]], G_1 = [[1, 0], [1i, 1]].
        let gains = [
            2.0, 0.0, 0.5, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0,
        ];
        let term = BinnedJones {
            ntime_bins: 1,
            nfreq_bins: 1,
            gains: &gains,
            valid: &[1, 1],
            time_bin: &[0],
            freq_bin: &[0],
        };
        let mut od = [0f32; 8];
        let mut of = [0u8; 4];
        apply_jones(&chunk, &term, Direction::Correct, 0, &mut od, &mut of).unwrap();
        let g0: M2 = [C::new(2.0, 0.0), C::new(0.5, 0.0), C::new(0.0, 0.0), C::ONE];
        let g1: M2 = [C::ONE, C::new(0.0, 0.0), C::new(0.0, 1.0), C::ONE];
        let v: M2 =
            std::array::from_fn(|k| C::new(f64::from(data[2 * k]), f64::from(data[2 * k + 1])));
        let want = mat_mul(
            &mat_mul(&inverse(&g0).unwrap(), &v),
            &adjoint(&inverse(&g1).unwrap()),
        );
        // G_p (G_p^-1 V G_q^-H) G_q^H = V checks the inverse itself.
        let again = mat_mul(&mat_mul(&g0, &want), &adjoint(&g1));
        for k in 0..4 {
            assert!((f64::from(od[2 * k]) - want[k].re).abs() < 1e-6);
            assert!((f64::from(od[2 * k + 1]) - want[k].im).abs() < 1e-6);
            assert!((again[k].re - v[k].re).abs() < 1e-12 && (again[k].im - v[k].im).abs() < 1e-12);
        }
        assert_eq!(of, [0; 4]);
        // A bad side is the identity and flags all four.
        let term = BinnedJones {
            valid: &[1, 0],
            ..term
        };
        apply_jones(&chunk, &term, Direction::Correct, 0, &mut od, &mut of).unwrap();
        let want = mat_mul(&inverse(&g0).unwrap(), &v);
        for k in 0..4 {
            assert!((f64::from(od[2 * k]) - want[k].re).abs() < 1e-6);
        }
        assert_eq!(of, [1; 4]);
    }

    #[test]
    fn viscal_order_puts_t_after_p() {
        assert!(Kind::T.type_key() > Kind::P.type_key());
        assert!(Kind::Df.type_key() > Kind::G.type_key());
        assert!(Kind::B.type_key() < Kind::K.type_key());
        assert_eq!(Kind::K.type_key(), Kind::KCross.type_key());
    }
}
