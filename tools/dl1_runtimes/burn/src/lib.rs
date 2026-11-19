// SPDX-License-Identifier: MIT
//! F3's network as burn-onnx generated it at build time, on burn's portable
//! CPU backend (flex).

pub mod model {
    include!(concat!(env!("OUT_DIR"), "/model/f3.rs"));
}

use burn::tensor::{Tensor, TensorData};

pub struct F3 {
    model: model::Model,
    device: burn::tensor::Device,
}

// The bench shares one loaded model across rayon threads.
unsafe impl Sync for F3 {}
unsafe impl Send for F3 {}

impl F3 {
    pub fn new() -> Self {
        let device = burn::tensor::Device::default();
        F3 {
            model: model::Model::default(),
            device,
        }
    }

    pub fn run(&self, x: &[f32], nt: usize, nc: usize) -> Result<Vec<f32>, String> {
        let data = TensorData::new(x.to_vec(), [1, 15, nt, nc]);
        let t = Tensor::<4>::from_data(data, &self.device);
        let y = self.model.forward(t);
        y.into_data().to_vec::<f32>().map_err(|e| format!("{e:?}"))
    }
}

impl Default for F3 {
    fn default() -> Self {
        Self::new()
    }
}
