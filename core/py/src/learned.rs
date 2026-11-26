// SPDX-License-Identifier: MIT
//! `rang._core.learned_onnx_metadata` and `learned_dilated_cnn_weights`:
//! the ONNX weights-file reader of the swap contract (`rang_core::learned`,
//! task DL1, `research/dl1-contract.md`), for `rang.learned`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.

use crate::{Ro, c_slice, detach};
use numpy::{IntoPyArray, PyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::learned;
use rang_core::learned_interp::Interp;

fn model(payload: &[u8]) -> PyResult<learned::Model> {
    learned::read(payload).map_err(|e| PyValueError::new_err(format!("ONNX: {e}")))
}

/// The metadata_props of an ONNX file's bytes as [(key, value)], the graph
/// inputs, outputs and node op types; ValueError if it is not a readable
/// ONNX model.
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn learned_onnx_metadata(
    payload: &[u8],
) -> PyResult<(Vec<(String, String)>, Vec<String>, Vec<String>, Vec<String>)> {
    let m = model(payload)?;
    let ops = m.nodes.iter().map(|n| n.op_type.clone()).collect();
    Ok((m.metadata, m.inputs, m.outputs, ops))
}

/// The flat float32 weights of a `dilated-cnn/1` ONNX graph in the Rust
/// kernels' order (`f3flag`, `f4flag`); ValueError naming the mismatch if
/// the graph is not that architecture with these hyperparameters.
#[pyfunction]
pub fn learned_dilated_cnn_weights<'py>(
    py: Python<'py>,
    payload: &[u8],
    inputs: usize,
    hidden: usize,
    dilations: Vec<usize>,
) -> PyResult<Bound<'py, PyArray1<f32>>> {
    let m = model(payload)?;
    let w = learned::dilated_cnn_weights(&m, inputs, hidden, &dilations)
        .map_err(|e| PyValueError::new_err(format!("ONNX: {e}")))?;
    Ok(w.into_pyarray(py))
}

fn interp(payload: &[u8]) -> PyResult<Interp> {
    Interp::load(&model(payload)?).map_err(|e| PyValueError::new_err(format!("ONNX: {e}")))
}

/// Check that the interpreter runs every node of an ONNX file (the swap
/// contract's reference runtime, task DL1-I); ValueError names the first
/// op, node or attribute it does not.
#[pyfunction]
pub fn learned_interp_check(payload: &[u8]) -> PyResult<()> {
    interp(payload).map(|_| ())
}

/// Run an ONNX file's graph on `x` float32 of `shape` (n, c, h, w) with the
/// interpreter; returns the flat output and its shape.
#[pyfunction]
pub fn learned_interp_run<'py>(
    py: Python<'py>,
    payload: &[u8],
    x: Ro<'_, f32>,
    shape: [usize; 4],
) -> PyResult<(Bound<'py, PyArray1<f32>>, [usize; 4])> {
    let it = interp(payload)?;
    let x = c_slice(&x, "x")?;
    let (y, sh) = detach(py, || it.run(x, shape))
        .map_err(|e| PyValueError::new_err(format!("interpreter: {e}")))?;
    Ok((y.into_pyarray(py), sh))
}
