//! Rang core: an in-memory visibility model and fused calibration passes.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Phase 1 of the port plan in `research/stack-consolidation-feasibility.md`:
//! one sweep over the visibility cells forms the prediction, the residual,
//! per-split weighted residual sums, per-baseline robust residual scores and
//! antenna-diagonal Gauss--Newton blocks. The validation protocol is frozen in
//! `research/core-phase1.md`. Nothing here changes an archived result.

pub mod ffi;
pub mod fused;
pub mod jones;
pub mod robust;
