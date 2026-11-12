// SPDX-License-Identifier: GPL-3.0-or-later
//! The calibration chain of rang-core (`research/c1-calibration-chain.md`
//! section 4): one module per concern. `apply` corrects and corrupts chunks
//! by calibration terms (task C4a, `research/c4a-apply.md`); `ffi_apply` is
//! its C ABI. `diag` solves the diagonal gain terms (`diag_complex`,
//! `phase`) and `reference` holds CASA's rules around a solve
//! (`minblperant`, `minsnr`, the reference antenna) (task C2a,
//! `research/c2a-gain.md`). `delay` solves the delay term K (QuartiCal's
//! `delay` with its FFT initial estimate; task C2b, `research/c2b-delay.md`).
//! `delay_offset` solves K as QuartiCal's `delay_and_offset` and `bandpass`
//! holds CASA's `fillgaps` for B (task C2c, `research/c2c-bandpass.md`).
//! `parang` rotates by the parallactic angle P, `crosshand` solves KCROSS
//! and Xf, and `leakage` solves Df (task C6, `research/c6-polterms.md`).

pub mod apply;
pub mod bandpass;
pub mod crosshand;
pub mod delay;
pub mod delay_offset;
pub mod diag;
pub mod ffi_apply;
pub mod fluxscale;
pub mod leakage;
pub mod parang;
pub mod reference;
