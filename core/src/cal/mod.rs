//! The calibration chain of rang-core (`research/c1-calibration-chain.md`
//! section 4): one module per concern. `apply` corrects and corrupts chunks
//! by calibration terms (task C4a, `research/c4a-apply.md`); `ffi_apply` is
//! its C ABI. `diag` solves the diagonal gain terms (`diag_complex`,
//! `phase`) and `reference` holds CASA's rules around a solve
//! (`minblperant`, `minsnr`, the reference antenna) (task C2a,
//! `research/c2a-gain.md`).

pub mod apply;
pub mod diag;
pub mod ffi_apply;
pub mod fluxscale;
pub mod reference;
