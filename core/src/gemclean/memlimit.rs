// SPDX-License-Identifier: MIT
//! GeMClean's estimate of its own peak resident memory, checked against
//! `-memory-limit` before the 2n PSF pass (issue #34,
//! `research/gemclean-memlimit.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! Only the single-image path of one polarisation is estimated (the path the
//! self-calibration images and rang's default `image` stage take; the cases
//! of the note's section 3). The estimate is a maximum over the phases of the
//! run. Each phase is the resident memory measured at the check (the process
//! itself, the read's leftovers) less the dense arrays it holds, plus what
//! the phase holds: exact buffer sizes from the type sizes, the weighted and
//! kept cells and the gridder's own plan, and a fixed part per pixel fitted
//! on the note's fit cases. Nothing here changes what the run computes.

/// GiB, as `-memory-limit` and the messages give it.
pub const GIB: f64 = (1u64 << 30) as f64;

/// The fixed parts, in bytes per pixel of the n × n image (`k_psf` per pixel
/// of the 2n × 2n PSF): the gridder's tables, the beam, the images and the
/// passes' transients. Fitted on F1-F4 (research/gemclean-memlimit.md,
/// section 6), per precision.
#[derive(Clone, Copy, Debug)]
pub struct Fixed {
    pub k_psf: f64,
    pub k_beam: f64,
    pub k_clean: f64,
}

/// Double precision (`-wgridder-accuracy` finer than 1e-5, or `-double`):
/// the larger of F1 (4096²) and F2 (2048²), glacier 2026-11-28, rounded up.
pub const FIXED_F64: Fixed = Fixed {
    k_psf: 10.6,
    k_beam: 74.2,
    k_clean: 186.0,
};
/// Single precision (rang's default accuracy 1e-4, or `-single`): the larger
/// of F3 and F4, rounded up.
pub const FIXED_F32: Fixed = Fixed {
    k_psf: 10.7,
    k_beam: 73.9,
    k_clean: 186.7,
};
/// The margin on the largest phase: allocator slack that grows with the
/// run's allocations and is not in the resident memory at the check.
pub const MARGIN: f64 = 1.03;

/// What the run knows at the check (after the read, the weights and the
/// row compaction).
#[derive(Clone, Copy, Debug)]
pub struct Inputs {
    /// Image side n.
    pub n: usize,
    /// Bytes of the gridder's real type (4 single, 8 double).
    pub real: usize,
    /// Cells of the rows kept (dense visibilities and weights).
    pub kept_cells: usize,
    /// Bytes of the kept rows' uvw.
    pub uvw_bytes: usize,
    /// Cells with a nonzero gridding weight.
    pub weighted: usize,
    /// Work grids of a residual pass on the n × n image.
    pub grid_n: usize,
    /// Work grids of the 2n × 2n PSF pass.
    pub grid_2n: usize,
    /// Resident bytes now and their peak so far.
    pub resident: u64,
    pub resident_peak: u64,
}

/// The estimate: each phase's bytes, and the largest with the margin.
#[derive(Clone, Debug)]
pub struct Estimate {
    pub inputs: Inputs,
    pub phases: Vec<(&'static str, f64)>,
    pub bytes: f64,
    pub phase: &'static str,
}

impl Estimate {
    pub fn gib(&self) -> f64 {
        self.bytes / GIB
    }

    /// `memory_estimate` of the report.
    pub fn to_json(&self, limit_gib: f64) -> String {
        let phases: Vec<String> = self
            .phases
            .iter()
            .map(|(k, b)| format!("{{\"phase\": \"{k}\", \"bytes\": {b:.0}}}"))
            .collect();
        let i = &self.inputs;
        format!(
            "{{\"limit_gib\": {limit_gib}, \"bytes\": {:.0}, \"gib\": {:.4}, \"phase\": \"{}\", \"margin\": {MARGIN}, \"phases\": [{}], \"inputs\": {{\"n\": {}, \"real\": {}, \"kept_cells\": {}, \"uvw_bytes\": {}, \"weighted\": {}, \"grid_n\": {}, \"grid_2n\": {}, \"resident\": {}, \"resident_peak\": {}}}}}",
            self.bytes,
            self.gib(),
            self.phase,
            phases.join(", "),
            i.n,
            i.real,
            i.kept_cells,
            i.uvw_bytes,
            i.weighted,
            i.grid_n,
            i.grid_2n,
            i.resident,
            i.resident_peak
        )
    }
}

pub fn fixed(real: usize) -> Fixed {
    if real == 4 { FIXED_F32 } else { FIXED_F64 }
}

/// The estimate of `i` with the fixed parts `k`.
pub fn estimate(i: &Inputs, k: Fixed) -> Estimate {
    let t = i.real as f64;
    let c = i.kept_cells as f64;
    let a = i.weighted as f64;
    let n2 = (i.n * i.n) as f64;
    let psf2 = 4.0 * n2;
    // Dense arrays at the check: Stokes I visibilities (complex f32) and
    // gridding weights (f64) of the kept rows, and their uvw.
    let dense = 16.0 * c + i.uvw_bytes as f64;
    let rest = (i.resident as f64 - dense).max(0.0);
    // The measurement keeps the visibilities and holds the weights in the
    // gridder's type (a single-precision copy is made beside the f64 ones).
    let dense_m = (8.0 + t) * c + i.uvw_bytes as f64;
    let measurement = rest + dense + if i.real == 4 { 4.0 * c } else { 0.0 };
    // The 2n PSF pass: its work grid, its output in the gridder's type, and
    // per weighted cell the sorted index (8 B) and the stored sorted values
    // (complex, 2t).
    let psf = rest + dense_m + i.grid_2n as f64 + psf2 * t + (8.0 + 2.0 * t) * a + k.k_psf * psf2;
    // The plan and beam, then the compaction: the 2n PSF kept in f64, the
    // plan's sorted index, the compacted visibilities (complex f32) and
    // weights (the type) beside the dense ones.
    let beam = rest + dense_m + psf2 * 8.0 + 8.0 * a + (8.0 + t) * a + k.k_beam * n2;
    // The major and minor cycles: per weighted cell the visibilities (8),
    // weights (t), sorted index (8), stored sorted values (2t) and the
    // permutation (4); the residual pass's grids; images and beam per pixel.
    let clean = rest + i.uvw_bytes as f64 + (20.0 + 3.0 * t) * a + i.grid_n as f64 + k.k_clean * n2;
    let phases = vec![
        ("read and weights", i.resident_peak as f64),
        ("measurement", measurement),
        ("psf 2n", psf),
        ("plan, beam and compaction", beam),
        ("major and minor cycles", clean),
    ];
    let (phase, top) = phases
        .iter()
        .fold(("", 0.0_f64), |m, &(p, b)| if b > m.1 { (p, b) } else { m });
    Estimate {
        inputs: *i,
        phases,
        bytes: top * MARGIN,
        phase,
    }
}

/// The refusal: `None` when the estimate fits `limit_gib`.
pub fn refusal(e: &Estimate, limit_gib: f64) -> Option<String> {
    (e.gib() > limit_gib).then(|| {
        let need = (e.gib() * 10.0).ceil() / 10.0;
        format!(
            "the estimated peak memory, {:.2} GiB (in the {}), is above -memory-limit {limit_gib} GiB; \
             raise the limit to at least {need:.1} (rang-core: data.memory_limit_gb), or image fewer \
             pixels or cells (research/gemclean-memlimit.md)",
            e.gib(),
            e.phase
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inputs() -> Inputs {
        Inputs {
            n: 1024,
            real: 8,
            kept_cells: 10_000_000,
            uvw_bytes: 1_000_000,
            weighted: 4_000_000,
            grid_n: 50_000_000,
            grid_2n: 200_000_000,
            resident: 400_000_000,
            resident_peak: 500_000_000,
        }
    }

    #[test]
    fn largest_phase_with_margin() {
        let e = estimate(&inputs(), FIXED_F64);
        let top = e.phases.iter().map(|p| p.1).fold(0.0, f64::max);
        assert_eq!(e.bytes, top * MARGIN);
        assert!(e.phases.iter().any(|p| p.0 == e.phase && p.1 == top));
    }

    #[test]
    fn grows_with_weighted_cells() {
        let mut i = inputs();
        let a = estimate(&i, FIXED_F64).bytes;
        i.weighted *= 4;
        assert!(estimate(&i, FIXED_F64).bytes > a);
    }

    #[test]
    fn refusal_names_the_figure() {
        let e = estimate(&inputs(), FIXED_F64);
        assert!(refusal(&e, 1e3).is_none());
        let msg = refusal(&e, 1e-3).unwrap();
        assert!(msg.contains(&format!("{:.2} GiB", e.gib())), "{msg}");
        assert!(msg.contains("data.memory_limit_gb"), "{msg}");
    }
}
