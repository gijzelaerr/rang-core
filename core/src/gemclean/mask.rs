//! Clean masks for gemclean (task G4, `research/g4-masks.md`): WSClean 3.7's
//! `-fits-mask` and radler's automatic mask (`-auto-mask`, `-abs-auto-mask`,
//! `-auto-mask-nmiter`, the default `dual` major-iteration mode).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Read in radler `76fe4474c31c` (`radler.cc`, `Radler::Perform`,
//! `SetAutoMaskMode`, `ReadMask`; `math/gain_calculations.h`,
//! `CalculateContinuedLoopGain`) and aocommon `aa4d6a47b864`
//! (`Image::MedianAndStdDevFromMAD`):
//!
//! - **The FITS mask**: a pixel is in the mask when its value is nonzero
//!   (NaN included, as `mask_data[i] != 0.0`). One plane only here.
//! - **Phase 1** (mask construction): every major iteration estimates the
//!   noise `σ` of the integrated residual (1.48260221850560 MAD, single
//!   precision, finite pixels, even counts averaged) and cleans to
//!   `max(σ · auto_mask, abs_auto_mask, abs_threshold)`, inside the FITS mask
//!   if there is one.
//! - **The switch**: a major iteration whose minor loop ends without wanting
//!   another (the threshold was reached, nothing was cleaned, the budget was
//!   spent) finishes the mask. In `dual` mode the same major iteration then
//!   continues with the mask at the final threshold and the continued gain
//!   `max(0, 1 − (1 − mgain) / (1 − achieved))`, `achieved = 1 − |end / start|`
//!   of its first minor loop; a phase-1 iteration that hands back normally
//!   also continues inside the mask so far, at `mgain`.
//! - **Phase 2**: the minor-loop gain doubles (`min(1, 2 · gain)`), the
//!   cleaning stays inside the mask, and at most `auto_mask_nmiter` more
//!   major iterations follow the one that finished the mask.
//! - **The Högbom mask** is the set of nonzero model pixels at the first
//!   moment the mask is used, and is not updated after that
//!   (`auto_mask_.empty()` guards its construction). Multiscale keeps one
//!   mask per scale instead, the component centres it cleaned while tracking.

use std::path::Path;

/// `-auto-mask`, `-abs-auto-mask` and `-auto-mask-nmiter`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AutoMask {
    /// `-auto-mask <sigma>`.
    pub sigma: Option<f64>,
    /// `-abs-auto-mask <Jy>`.
    pub absolute: Option<f64>,
    /// `-auto-mask-nmiter` (default 2).
    pub nmiter: usize,
}

/// The masks of a run.
#[derive(Clone, Debug, Default)]
pub struct Masking {
    /// `-fits-mask`, `n × n` in the gridder's order.
    pub fits: Option<Vec<bool>>,
    pub auto: Option<AutoMask>,
}

impl Masking {
    pub fn is_active(&self) -> bool {
        self.fits.is_some() || self.auto.is_some()
    }
}

/// radler's noise estimate: `1.48260221850560 · MAD` of the finite pixels,
/// in single precision, the two middle values averaged for an even count.
pub fn radler_stddev(x: &[f64]) -> f64 {
    let mut copy: Vec<f32> = x
        .iter()
        .map(|&v| v as f32)
        .filter(|v| v.is_finite())
        .collect();
    if copy.is_empty() {
        return 0.0;
    }
    let len = copy.len();
    let mid = (len - 1) / 2;
    let even = len.is_multiple_of(2);
    let middle = |v: &mut [f32]| -> f32 {
        v.select_nth_unstable_by(mid, |a, b| a.total_cmp(b));
        let lo = v[mid];
        if even {
            let hi = v[mid + 1..].iter().copied().fold(f32::INFINITY, f32::min);
            (lo + hi) * 0.5
        } else {
            lo
        }
    };
    let median = middle(&mut copy);
    for v in copy.iter_mut() {
        *v = (*v - median).abs();
    }
    let mad = middle(&mut copy);
    f64::from(1.482_602_2_f32 * mad)
}

/// `CalculateContinuedLoopGain` for the `dual` strategy: the achieved gain
/// of the first minor loop and the gain of the continued one.
pub fn continued_gain(base: f64, start: f64, end: f64, finishing: bool) -> (f64, f64) {
    let achieved = (end != 0.0 && start != 0.0)
        .then(|| (1.0 - (end as f32 / start as f32).abs()).max(0.0_f32) as f64);
    if finishing {
        match achieved {
            Some(a) => (a, (1.0 - (1.0 - base) / (1.0 - a)).max(0.0)),
            None => (0.0, 0.0),
        }
    } else {
        (achieved.unwrap_or(0.0), base)
    }
}

/// How a major iteration's first minor loop ended, as radler sees it.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StageEnd {
    /// The loop handed back at the major-cycle level (`mgainReached`) after
    /// cleaning something, and not at the threshold.
    pub another: bool,
    pub start_peak: f64,
    pub end_peak: f64,
}

/// The continued minor loop of a major iteration.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Continuation {
    pub gain: f64,
    pub threshold: f64,
}

/// One major iteration of an auto-masked run, for the report.
#[derive(Clone, Debug, PartialEq)]
pub struct AutoCycle {
    pub index: usize,
    pub sigma: f64,
    pub threshold: f64,
    pub phase2: bool,
    pub continued: Option<Continuation>,
    pub achieved: f64,
}

/// radler's auto-mask state across major iterations.
#[derive(Clone, Debug)]
pub struct AutoState {
    pub cfg: AutoMask,
    /// `-auto-threshold` (radler's estimate) and `-abs-threshold`.
    pub auto_threshold: Option<f64>,
    pub abs_threshold: f64,
    /// `-mgain` (1 with `-minor-to-threshold`).
    pub mgain: f64,
    pub finished: bool,
    /// The 1-based major iteration that finished the mask.
    pub finishing: Option<usize>,
    /// The threshold radler's algorithm holds (`SetThreshold` persists).
    pub threshold: f64,
    final_threshold: f64,
    sigma: f64,
    pub cycles: Vec<AutoCycle>,
    /// Picks made while a mask was in force, and those outside it (a check
    /// of the drivers: zero by construction).
    pub masked_picks: usize,
    pub outside_picks: usize,
}

/// What a major iteration starts with.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CycleStart {
    pub threshold: f64,
    /// Clean inside the automatic mask (phase 2).
    pub use_auto: bool,
    /// The minor-loop gain factor (2 in phase 2, capped at gain 1).
    pub gain_doubled: bool,
}

impl AutoState {
    pub fn new(cfg: AutoMask, auto_threshold: Option<f64>, abs_threshold: f64, mgain: f64) -> Self {
        AutoState {
            cfg,
            auto_threshold,
            abs_threshold,
            mgain,
            finished: false,
            finishing: None,
            threshold: abs_threshold,
            final_threshold: abs_threshold,
            sigma: 0.0,
            cycles: Vec::new(),
            masked_picks: 0,
            outside_picks: 0,
        }
    }

    /// `Perform` up to `ExecuteMajorIteration`, for the 1-based iteration
    /// `index` on the integrated residual.
    pub fn begin(&mut self, index: usize, residual: &[f64]) -> CycleStart {
        let sigma = radler_stddev(residual);
        self.sigma = sigma;
        self.final_threshold = match self.auto_threshold {
            Some(k) => (sigma * k).max(self.abs_threshold),
            None => self.abs_threshold,
        };
        if !self.finished {
            let combined =
                (sigma * self.cfg.sigma.unwrap_or(0.0)).max(self.cfg.absolute.unwrap_or(0.0));
            self.threshold = combined.max(self.abs_threshold);
        } else if self.auto_threshold.is_some() {
            self.threshold = self.final_threshold;
        }
        self.cycles.push(AutoCycle {
            index,
            sigma,
            threshold: self.threshold,
            phase2: self.finished,
            continued: None,
            achieved: 0.0,
        });
        CycleStart {
            threshold: self.threshold,
            use_auto: self.finished,
            gain_doubled: self.finished,
        }
    }

    /// After the first minor loop of iteration `index`: whether another major
    /// iteration follows (`another`), and the continued minor loop if any.
    /// `more_majors` and `more_components` are the `-nmiter` and `-niter`
    /// budgets left after this iteration.
    pub fn end_stage(
        &mut self,
        index: usize,
        end: StageEnd,
        more_majors: bool,
        more_components: bool,
    ) -> (bool, Option<Continuation>) {
        let mut another = end.another;
        let mut finished_now = false;
        if !another && !self.finished {
            self.finished = true;
            another = true;
            self.finishing = Some(index);
            finished_now = true;
        }
        if another && !more_majors {
            another = false;
        }
        if another
            && self.finished
            && index - self.finishing.expect("set when finished") >= self.cfg.nmiter
        {
            another = false;
        }
        if another && !more_components {
            another = false;
        }
        let mut cont = None;
        if another && (!self.finished || finished_now) {
            let (achieved, gain) =
                continued_gain(self.mgain, end.start_peak, end.end_peak, finished_now);
            if let Some(c) = self.cycles.last_mut() {
                c.achieved = achieved;
            }
            if gain != 0.0 {
                if finished_now {
                    self.threshold = self.final_threshold;
                }
                cont = Some(Continuation {
                    gain,
                    threshold: self.threshold,
                });
            }
        }
        if let Some(c) = self.cycles.last_mut() {
            c.continued = cont;
        }
        (another, cont)
    }

    /// Count one pick at `pixel` against the mask in force.
    pub fn record_pick(&mut self, mask: Option<&[bool]>, pixel: usize) {
        if let Some(m) = mask {
            self.masked_picks += 1;
            if !m[pixel] {
                self.outside_picks += 1;
            }
        }
    }

    pub fn to_json(&self) -> String {
        use super::json::{arr, num, obj, opt};
        let cycles: Vec<String> = self
            .cycles
            .iter()
            .map(|c| {
                obj(&[
                    ("index", c.index.to_string()),
                    ("sigma", num(c.sigma)),
                    ("threshold", num(c.threshold)),
                    ("phase2", c.phase2.to_string()),
                    ("achieved", num(c.achieved)),
                    ("continued_gain", opt(c.continued.map(|k| k.gain))),
                    ("continued_threshold", opt(c.continued.map(|k| k.threshold))),
                ])
            })
            .collect();
        obj(&[
            ("auto_mask_sigma", opt(self.cfg.sigma)),
            ("abs_auto_mask", opt(self.cfg.absolute)),
            ("auto_mask_nmiter", self.cfg.nmiter.to_string()),
            ("finishing_iteration", opt(self.finishing.map(|i| i as f64))),
            ("masked_picks", self.masked_picks.to_string()),
            ("outside_picks", self.outside_picks.to_string()),
            ("cycles", arr(&cycles)),
        ])
    }
}

/// The mask of `Masking`: the nonzero pixels of every model, union.
pub fn from_models(models: &[&[f64]]) -> Vec<bool> {
    let n2 = models.first().map_or(0, |m| m.len());
    let mut mask = vec![false; n2];
    for m in models {
        for (k, &v) in m.iter().enumerate() {
            if v.is_finite() && v != 0.0 {
                mask[k] = true;
            }
        }
    }
    mask
}

/// The signed value of the largest `|x|` inside `mask` (everywhere without
/// one), first in raster order; `None` when the mask is empty.
pub fn masked_peak(x: &[f64], mask: Option<&[bool]>) -> Option<(usize, f64)> {
    let mut best: Option<(usize, f64)> = None;
    for (k, &v) in x.iter().enumerate() {
        if mask.is_some_and(|m| !m[k]) {
            continue;
        }
        if best.is_none_or(|(_, b)| v.abs() > b.abs()) {
            best = Some((k, v));
        }
    }
    best
}

/// Read a FITS mask of `n × n` pixels, one frequency and one Stokes plane
/// (BITPIX 8, 16, 32, 64, −32 or −64, with BSCALE and BZERO), into the
/// gridder's order: true where the value is nonzero (NaN included).
pub fn read_fits_mask(path: &Path, n: usize) -> Result<Vec<bool>, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut cards: Vec<(String, String)> = Vec::new();
    let mut pos = 0;
    loop {
        if pos + 80 > bytes.len() {
            return Err(format!("{}: no END card", path.display()));
        }
        let text = String::from_utf8_lossy(&bytes[pos..pos + 80]).to_string();
        pos += 80;
        let key = text.get(..8).unwrap_or("").trim().to_string();
        if key == "END" {
            break;
        }
        if text.len() > 10 && &text[8..10] == "= " {
            let rest = &text[10..];
            let value = if rest.trim_start().starts_with('\'') {
                let start = rest.find('\'').unwrap() + 1;
                let end = rest[start..].find('\'').map_or(rest.len(), |e| start + e);
                rest[start..end].trim_end().to_string()
            } else {
                rest.split('/').next().unwrap_or("").trim().to_string()
            };
            cards.push((key, value));
        }
    }
    let get = |k: &str| cards.iter().find(|(key, _)| key == k).map(|c| c.1.clone());
    let num = |k: &str, default: f64| -> Result<f64, String> {
        match get(k) {
            None => Ok(default),
            Some(v) => v
                .replace('D', "E")
                .parse()
                .map_err(|_| format!("{}: {k} = {v:?} is not a number", path.display())),
        }
    };
    let naxis = num("NAXIS", 0.0)? as usize;
    let (w, h) = (num("NAXIS1", 0.0)? as usize, num("NAXIS2", 0.0)? as usize);
    if naxis < 2 || w != n || h != n {
        return Err(format!(
            "{}: the mask is {w} × {h}, the image {n} × {n}: Specified Fits file mask did \
             not have same dimensions as output image",
            path.display()
        ));
    }
    for k in 3..=naxis {
        if num(&format!("NAXIS{k}"), 1.0)? != 1.0 {
            return Err(format!(
                "{}: NAXIS{k} is not 1: masks with several planes (one per output channel) are \
                 not implemented (research/g4-masks.md)",
                path.display()
            ));
        }
    }
    let bitpix = num("BITPIX", 0.0)? as i64;
    let (bscale, bzero) = (num("BSCALE", 1.0)?, num("BZERO", 0.0)?);
    let size = (bitpix.unsigned_abs() / 8) as usize;
    let start = pos.div_ceil(2880) * 2880;
    let raw = bytes
        .get(start..start + n * n * size)
        .ok_or_else(|| format!("{}: truncated data", path.display()))?;
    let value = |c: &[u8]| -> f64 {
        let v = match bitpix {
            8 => f64::from(c[0]),
            16 => f64::from(i16::from_be_bytes([c[0], c[1]])),
            32 => f64::from(i32::from_be_bytes(c.try_into().unwrap())),
            64 => i64::from_be_bytes(c.try_into().unwrap()) as f64,
            -32 => f64::from(f32::from_be_bytes(c.try_into().unwrap())),
            _ => f64::from_be_bytes(c.try_into().unwrap()),
        };
        v * bscale + bzero
    };
    if ![8, 16, 32, 64, -32, -64].contains(&bitpix) {
        return Err(format!(
            "{}: BITPIX {bitpix} is not supported",
            path.display()
        ));
    }
    // FITS order (x fast) to the gridder's order: grid[x * n + y] = fits[y * n + x].
    let mut mask = vec![false; n * n];
    for (k, c) in raw.chunks_exact(size).enumerate() {
        let (y, x) = (k / n, k % n);
        mask[x * n + y] = value(c) != 0.0;
    }
    if !mask.iter().any(|&m| m) {
        return Err(format!("{}: the mask holds no pixel", path.display()));
    }
    Ok(mask)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stddev_is_radlers_mad() {
        // Median 2.5 (even count averaged), deviations 1.5, 0.5, 0.5, 1.5:
        // MAD 1.0.
        let s = radler_stddev(&[1.0, 2.0, 3.0, 4.0, f64::NAN]);
        assert!((s - 1.482_602_2).abs() < 1e-6);
        assert_eq!(radler_stddev(&[]), 0.0);
    }

    #[test]
    fn continued_gain_follows_radler() {
        // A phase-1 iteration continues at mgain.
        assert_eq!(continued_gain(0.8, 1.0, 0.2, false).1, 0.8);
        // The finishing iteration took the peak from 1 to 0.5 (achieved 0.5):
        // 1 - 0.2 / 0.5 = 0.6.
        let (a, g) = continued_gain(0.8, 1.0, 0.5, true);
        assert!((a - 0.5).abs() < 1e-7 && (g - 0.6).abs() < 1e-6);
        // Deeper than mgain already: no continuation.
        assert_eq!(continued_gain(0.8, 1.0, 0.1, true).1, 0.0);
    }

    #[test]
    fn state_machine_switches_and_counts() {
        let cfg = AutoMask {
            sigma: Some(5.0),
            absolute: None,
            nmiter: 2,
        };
        let mut st = AutoState::new(cfg, Some(1.0), 0.0, 0.8);
        let noise: Vec<f64> = (0..101).map(|i| (i as f64 - 50.0) * 1e-3).collect();
        let c = st.begin(1, &noise);
        assert!(!c.use_auto && c.threshold > 0.0);
        let hand_back = StageEnd {
            another: true,
            start_peak: 1.0,
            end_peak: 0.2,
        };
        let (more, cont) = st.end_stage(1, hand_back, true, true);
        assert!(more && cont.is_some_and(|k| k.gain == 0.8));
        st.begin(2, &noise);
        let reached = StageEnd {
            another: false,
            start_peak: 1.0,
            end_peak: 0.5,
        };
        let (more, cont) = st.end_stage(2, reached, true, true);
        assert!(more && st.finishing == Some(2));
        assert!(cont.is_some_and(|k| (k.gain - 0.6).abs() < 1e-6));
        let c3 = st.begin(3, &noise);
        assert!(c3.use_auto && c3.threshold < c.threshold);
        assert!(st.end_stage(3, hand_back, true, true).0);
        st.begin(4, &noise);
        // Two iterations after the finishing one: the run ends.
        assert!(!st.end_stage(4, hand_back, true, true).0);
    }

    #[test]
    fn masked_peak_respects_the_mask() {
        let x = [5.0, -7.0, 1.0, 3.0];
        assert_eq!(masked_peak(&x, None), Some((1, -7.0)));
        assert_eq!(
            masked_peak(&x, Some(&[true, false, false, true])),
            Some((0, 5.0))
        );
        assert_eq!(masked_peak(&x, Some(&[false; 4])), None);
    }
}
