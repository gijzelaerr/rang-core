//! The calibration chain of rang-core (`research/c1-calibration-chain.md`
//! section 4): one module per concern. `apply` corrects and corrupts chunks
//! by calibration terms (task C4a, `research/c4a-apply.md`); `ffi_apply` is
//! its C ABI.

pub mod apply;
pub mod ffi_apply;
