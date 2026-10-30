//! Rang core: an in-memory visibility model and fused calibration passes.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Phase 1 of the port plan in `research/stack-consolidation-feasibility.md`:
//! one sweep over the visibility cells forms the prediction, the residual,
//! per-split weighted residual sums, per-baseline robust residual scores and
//! antenna-diagonal Gauss--Newton blocks. The validation protocol is frozen in
//! `research/core-phase1.md`. Phase 2 adds `solve`, a port of the full-Jones
//! `complex` solver of QuartiCal 0.2.7 (`research/core-phase2.md`). Nothing
//! here changes an archived result. `predict` ports the WSClean-format
//! component predictor of codex-africanus 0.4.4 (`research/core-phase3c-a.md`).
//! Wave 1 of `research/core-parallel-plan.md` adds `weights` (WSClean imaging
//! weights and Stokes I), `grid` (the w-stacking gridder), `sumthreshold`
//! (Tricolour strategies) and `ms` (a read-only Measurement Set reader), each
//! with its own `ffi_*` module and research report. Task P7
//! (`research/p7-architecture.md`) re-exports the root crate as `toy`, so the
//! extension links its kernels (gain TV, phase trend, anchored response with
//! the P4 eigensolver, projector, the pointing toy) and nothing builds the
//! root crate at run time.

pub mod aipsio;
pub mod blosc;
pub mod clean;
pub mod clean_certified;
pub mod closure;
pub mod correct;
pub mod ffi;
pub mod ffi_closure;
pub mod ffi_correct;
pub mod ffi_flag;
pub mod ffi_fluxstd;
pub mod ffi_grid;
pub mod ffi_ms;
pub mod ffi_ms_write;
pub mod ffi_weights;
pub mod ffi_wgridder;
pub mod fluxstd;
pub mod fused;
pub mod grid;
pub mod jones;
pub mod ms;
pub mod ms_desc;
pub mod ms_write;
pub mod predict;
pub mod robust;
pub mod solve;
pub mod sumthreshold;
pub mod weights;
pub mod wgridder;

pub use rang_toy as toy;
