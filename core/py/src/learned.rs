// SPDX-License-Identifier: MIT
//! `rang._core.learned_onnx_metadata` and `learned_dilated_cnn_weights`:
//! the ONNX weights-file reader of the swap contract (`rang_core::learned`,
//! task DL1, `research/dl1-contract.md`), for `rang.learned`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

use numpy::{IntoPyArray, PyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::learned;

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
