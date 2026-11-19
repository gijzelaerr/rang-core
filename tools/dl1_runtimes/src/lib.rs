// SPDX-License-Identifier: MIT
//! The runtimes of DL1's comparison (research/dl1-contract.md, section 7)
//! behind one interface: load an ONNX file of F3's network, run one plane
//! (1, 15, nt, nc) float32 NCHW to logits (nt, nc).

pub trait Runtime: Sync {
    fn name(&self) -> &'static str;
    /// Logits (nt * nc) of planes `x` (15 * nt * nc, NCHW).
    fn run(&self, x: &[f32], nt: usize, nc: usize) -> Result<Vec<f32>, String>;
}

/// The hand-written kernel (rang_core::f3flag's arithmetic) with weights
/// from the ONNX initializers.
#[cfg(feature = "kernel")]
pub mod kernel {
    use rang_core::learned;

    pub struct Kernel {
        w: Vec<f32>,
    }

    impl Kernel {
        pub fn load(path: &str) -> Result<Self, String> {
            let buf = std::fs::read(path).map_err(|e| e.to_string())?;
            let m = learned::read(&buf).map_err(|e| e.0)?;
            let w = learned::dilated_cnn_weights(&m, 15, 8, &[1, 2, 4, 8, 16]).map_err(|e| e.0)?;
            Ok(Kernel { w })
        }
    }

    impl super::Runtime for Kernel {
        fn name(&self) -> &'static str {
            "kernel"
        }
        fn run(&self, x: &[f32], nt: usize, nc: usize) -> Result<Vec<f32>, String> {
            let cin = 15;
            let ncell = nt * nc;
            let mut h = vec![0f32; ncell * cin];
            for c in 0..cin {
                for i in 0..ncell {
                    h[i * cin + c] = x[c * ncell + i];
                }
            }
            Ok(learned::dilated_cnn_planes(h, nt, nc, cin, &self.w))
        }
    }
}

#[cfg(feature = "tract")]
pub mod tract {
    use tract_onnx::prelude::*;

    pub struct Tract {
        plan: std::sync::Arc<TypedRunnableModel>,
    }

    impl Tract {
        /// Loads with the file's symbolic N, T, F (G3: one model for every
        /// shape).
        pub fn load(path: &str) -> Result<Self, String> {
            let plan = tract_onnx::onnx()
                .model_for_path(path)
                .and_then(|m| m.into_optimized())
                .and_then(|m| m.into_runnable())
                .map_err(|e| format!("{e:?}"))?;
            Ok(Tract { plan })
        }
    }

    impl super::Runtime for Tract {
        fn name(&self) -> &'static str {
            "tract"
        }
        fn run(&self, x: &[f32], nt: usize, nc: usize) -> Result<Vec<f32>, String> {
            let t = Tensor::from_shape(&[1, 15, nt, nc], x).map_err(|e| format!("{e:?}"))?;
            let out = self
                .plan
                .run(tvec!(t.into()))
                .map_err(|e| format!("{e:?}"))?;
            let v = out[0]
                .to_plain_array_view::<f32>()
                .map_err(|e| format!("{e:?}"))?;
            Ok(v.iter().copied().collect())
        }
    }
}

#[cfg(feature = "candle")]
pub mod candle {
    use candle_core::{Device, Tensor};
    use std::collections::HashMap;

    pub struct Candle {
        model: candle_onnx::onnx::ModelProto,
    }

    impl Candle {
        pub fn load(path: &str) -> Result<Self, String> {
            let model = candle_onnx::read_file(path).map_err(|e| e.to_string())?;
            Ok(Candle { model })
        }
    }

    impl super::Runtime for Candle {
        fn name(&self) -> &'static str {
            "candle"
        }
        fn run(&self, x: &[f32], nt: usize, nc: usize) -> Result<Vec<f32>, String> {
            let t =
                Tensor::from_slice(x, (1, 15, nt, nc), &Device::Cpu).map_err(|e| e.to_string())?;
            let mut inputs = HashMap::new();
            inputs.insert("planes".to_string(), t);
            let out = candle_onnx::simple_eval(&self.model, inputs).map_err(|e| e.to_string())?;
            let y = out.get("logits").ok_or("no logits")?;
            y.flatten_all()
                .and_then(|y| y.to_vec1::<f32>())
                .map_err(|e| e.to_string())
        }
    }
}

#[cfg(feature = "burn")]
pub mod burn {
    pub struct Burn(dl1_burn::F3);

    impl Burn {
        /// burn has no run-time loading (G1): the network and its .bpk
        /// weights were generated from the ONNX file at build time; `path`
        /// is ignored.
        pub fn load(_path: &str) -> Result<Self, String> {
            Ok(Burn(dl1_burn::F3::new()))
        }
    }

    impl super::Runtime for Burn {
        fn name(&self) -> &'static str {
            "burn"
        }
        fn run(&self, x: &[f32], nt: usize, nc: usize) -> Result<Vec<f32>, String> {
            self.0.run(x, nt, nc)
        }
    }
}

/// Load the runtime this build has (one feature per build for G6's size).
pub fn load(name: &str, path: &str) -> Result<Box<dyn Runtime>, String> {
    match name {
        #[cfg(feature = "kernel")]
        "kernel" => Ok(Box::new(kernel::Kernel::load(path)?)),
        #[cfg(feature = "tract")]
        "tract" => Ok(Box::new(tract::Tract::load(path)?)),
        #[cfg(feature = "candle")]
        "candle" => Ok(Box::new(candle::Candle::load(path)?)),
        #[cfg(feature = "burn")]
        "burn" => Ok(Box::new(burn::Burn::load(path)?)),
        _ => Err(format!("runtime {name} not in this build")),
    }
}

/// The cdylib entry G6 measures: load `path` and run one plane into `out`.
///
/// # Safety
/// `path` points to `len` UTF-8 bytes, `x` to 15 * nt * nc floats and
/// `out` to nt * nc floats.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn dl1_run(
    name: *const u8,
    name_len: usize,
    path: *const u8,
    len: usize,
    x: *const f32,
    nt: usize,
    nc: usize,
    out: *mut f32,
) -> i32 {
    let (name, path, x, out) = unsafe {
        (
            std::slice::from_raw_parts(name, name_len),
            std::slice::from_raw_parts(path, len),
            std::slice::from_raw_parts(x, 15 * nt * nc),
            std::slice::from_raw_parts_mut(out, nt * nc),
        )
    };
    let (Ok(name), Ok(path)) = (std::str::from_utf8(name), std::str::from_utf8(path)) else {
        return 1;
    };
    match load(name, path).and_then(|r| r.run(x, nt, nc)) {
        Ok(y) if y.len() == out.len() => {
            out.copy_from_slice(&y);
            0
        }
        _ => 2,
    }
}
