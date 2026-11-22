// SPDX-License-Identifier: MIT
//! The swap contract's reference runtime (task DL1-I, owner decision of
//! 2026-11-19, `research/dl1-contract.md` amendment 2): an interpreter of
//! ONNX graphs read by `learned::read`, pure Rust, NCHW float32.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! Ops: Conv (any kernel, dilations, pads and strides; group 1; bias
//! optional) and Relu, all of F3's and F4's networks. Every node is checked
//! when the graph is loaded; an op or attribute outside this set is refused
//! there, by name. The arithmetic is fixed: each output element is summed
//! from 0 over (ky, kx, ci) in that order, skipping padding, then its bias
//! is added. Threads split the output by (n, co, row) only, so no sum
//! depends on the thread count (gate I3).

use crate::learned::{Error, Model, Node, Tensor};
use rayon::prelude::*;
use std::collections::HashMap;

/// The ops the interpreter runs.
pub const OPS: [&str; 2] = ["Conv", "Relu"];

#[derive(Debug, Clone)]
enum Op {
    Conv {
        /// OIHW.
        w: Vec<f32>,
        cout: usize,
        cin: usize,
        kh: usize,
        kw: usize,
        b: Option<Vec<f32>>,
        dil: [usize; 2],
        /// top, left, bottom, right (ONNX's begin, begin, end, end).
        pads: [usize; 4],
        strides: [usize; 2],
    },
    Relu,
}

#[derive(Debug, Clone)]
struct Step {
    op: Op,
    input: String,
    output: String,
}

/// A loaded graph: one input and one output, NCHW float32.
#[derive(Debug, Clone)]
pub struct Interp {
    steps: Vec<Step>,
    input: String,
    output: String,
}

fn err<T>(text: impl Into<String>) -> Result<T, Error> {
    Err(Error(text.into()))
}

fn node_name(n: &Node, k: usize) -> String {
    if n.name.is_empty() {
        format!("node {k}")
    } else {
        format!("node {k} ({})", n.name)
    }
}

fn usizes(v: &[i64], what: &str, at: &str) -> Result<Vec<usize>, Error> {
    v.iter()
        .map(|&x| usize::try_from(x).map_err(|_| Error(format!("{at}: {what} {v:?} must be >= 0"))))
        .collect()
}

fn conv(n: &Node, at: &str, init: &HashMap<&str, &Tensor>) -> Result<Op, Error> {
    for a in &n.attributes {
        match a.name.as_str() {
            "kernel_shape" | "dilations" | "pads" | "strides" => {}
            "group" => {
                if a.i.unwrap_or(1) != 1 {
                    return err(format!("{at}: Conv group {:?} is not supported", a.i));
                }
            }
            "auto_pad" => {
                if a.s.as_deref().is_some_and(|v| v != "NOTSET") {
                    return err(format!("{at}: Conv auto_pad {:?} is not supported", a.s));
                }
            }
            other => return err(format!("{at}: Conv attribute {other} is not supported")),
        }
    }
    if n.inputs.len() < 2 || n.inputs.len() > 3 || n.outputs.len() != 1 {
        return err(format!(
            "{at}: Conv needs X, W and an optional B, one output"
        ));
    }
    let Some(w) = init.get(n.inputs[1].as_str()) else {
        return err(format!(
            "{at}: Conv weight {} is not an initializer",
            n.inputs[1]
        ));
    };
    if w.dims.len() != 4 {
        return err(format!(
            "{at}: Conv weight dims {:?}, only 2-D convolution",
            w.dims
        ));
    }
    let d = usizes(&w.dims, "weight dims", at)?;
    let (cout, cin, kh, kw) = (d[0], d[1], d[2], d[3]);
    let b = match n.inputs.get(2).filter(|s| !s.is_empty()) {
        None => None,
        Some(name) => {
            let Some(b) = init.get(name.as_str()) else {
                return err(format!("{at}: Conv bias {name} is not an initializer"));
            };
            if b.dims != [cout as i64] {
                return err(format!(
                    "{at}: Conv bias dims {:?}, expected [{cout}]",
                    b.dims
                ));
            }
            Some(b.data.clone())
        }
    };
    let ints = |name: &str| {
        n.attr(name)
            .map(|a| a.ints.clone())
            .filter(|v| !v.is_empty())
    };
    if let Some(k) = ints("kernel_shape")
        && k != [kh as i64, kw as i64]
    {
        return err(format!(
            "{at}: Conv kernel_shape {k:?} against weight {:?}",
            w.dims
        ));
    }
    let dil = usizes(&ints("dilations").unwrap_or(vec![1, 1]), "dilations", at)?;
    let pads = usizes(&ints("pads").unwrap_or(vec![0; 4]), "pads", at)?;
    let strides = usizes(&ints("strides").unwrap_or(vec![1, 1]), "strides", at)?;
    if dil.len() != 2 || pads.len() != 4 || strides.len() != 2 {
        return err(format!(
            "{at}: Conv dilations, pads or strides of the wrong length"
        ));
    }
    if dil.contains(&0) || strides.contains(&0) {
        return err(format!("{at}: Conv dilations and strides must be >= 1"));
    }
    Ok(Op::Conv {
        w: w.data.clone(),
        cout,
        cin,
        kh,
        kw,
        b,
        dil: [dil[0], dil[1]],
        pads: [pads[0], pads[1], pads[2], pads[3]],
        strides: [strides[0], strides[1]],
    })
}

impl Interp {
    /// Check and load every node of `m`; Err names the first op, node or
    /// attribute the interpreter does not run (gate I1).
    pub fn load(m: &Model) -> Result<Self, Error> {
        if m.inputs.len() != 1 || m.outputs.len() != 1 {
            return err(format!(
                "the interpreter needs one graph input and one output, not {:?} and {:?}",
                m.inputs, m.outputs
            ));
        }
        let init: HashMap<&str, &Tensor> = m
            .initializers
            .iter()
            .map(|t| (t.name.as_str(), t))
            .collect();
        let mut known: std::collections::HashSet<String> = [m.inputs[0].clone()].into();
        let mut steps = Vec::new();
        for (k, n) in m.nodes.iter().enumerate() {
            let at = node_name(n, k);
            let op = match n.op_type.as_str() {
                "Conv" => conv(n, &at, &init)?,
                "Relu" => {
                    if n.inputs.len() != 1 || n.outputs.len() != 1 || !n.attributes.is_empty() {
                        return err(format!(
                            "{at}: Relu takes one input, one output, no attributes"
                        ));
                    }
                    Op::Relu
                }
                other => {
                    return err(format!(
                        "op {other} at {at} is not supported by the interpreter (supported: {})",
                        OPS.join(", ")
                    ));
                }
            };
            if !known.contains(&n.inputs[0]) {
                return err(format!(
                    "{at}: input {} is not computed before it",
                    n.inputs[0]
                ));
            }
            known.insert(n.outputs[0].clone());
            steps.push(Step {
                op,
                input: n.inputs[0].clone(),
                output: n.outputs[0].clone(),
            });
        }
        if !known.contains(&m.outputs[0]) {
            return err(format!("graph output {} is never computed", m.outputs[0]));
        }
        Ok(Interp {
            steps,
            input: m.inputs[0].clone(),
            output: m.outputs[0].clone(),
        })
    }

    /// Run on `x` of shape (n, c, h, w); returns the output and its shape.
    /// Uses the current rayon pool.
    pub fn run(&self, x: &[f32], shape: [usize; 4]) -> Result<(Vec<f32>, [usize; 4]), Error> {
        if x.len() != shape.iter().product::<usize>() {
            return err(format!("input of {} values, shape {shape:?}", x.len()));
        }
        let mut env: HashMap<&str, (std::borrow::Cow<'_, [f32]>, [usize; 4])> = HashMap::new();
        env.insert(self.input.as_str(), (std::borrow::Cow::Borrowed(x), shape));
        for s in &self.steps {
            let (v, sh) = env
                .get(s.input.as_str())
                .ok_or_else(|| Error(format!("{} not computed", s.input)))?;
            let out = match &s.op {
                Op::Relu => (v.iter().map(|&a| a.max(0.0)).collect::<Vec<f32>>(), *sh),
                Op::Conv { .. } => conv_run(&s.op, v, *sh)?,
            };
            env.insert(s.output.as_str(), (std::borrow::Cow::Owned(out.0), out.1));
        }
        let (v, sh) = env
            .remove(self.output.as_str())
            .ok_or_else(|| Error("output not computed".into()))?;
        Ok((v.into_owned(), sh))
    }
}

fn conv_run(op: &Op, x: &[f32], shape: [usize; 4]) -> Result<(Vec<f32>, [usize; 4]), Error> {
    let Op::Conv {
        w,
        cout,
        cin,
        kh,
        kw,
        b,
        dil,
        pads,
        strides,
    } = op
    else {
        unreachable!()
    };
    let (cout, cin, kh, kw) = (*cout, *cin, *kh, *kw);
    let [n, c, h, wd] = shape;
    if c != cin {
        return err(format!("Conv: input has {c} channels, the weight {cin}"));
    }
    let span = |len: usize, k: usize, d: usize, p0: usize, p1: usize, s: usize| {
        let full = len + p0 + p1;
        let reach = d * (k - 1) + 1;
        if full < reach {
            0
        } else {
            (full - reach) / s + 1
        }
    };
    let ho = span(h, kh, dil[0], pads[0], pads[2], strides[0]);
    let wo = span(wd, kw, dil[1], pads[1], pads[3], strides[1]);
    let mut out = vec![0f32; n * cout * ho * wo];
    if wo == 0 || ho == 0 {
        return Ok((out, [n, cout, ho, wo]));
    }
    let plane = h * wd;
    out.par_chunks_mut(wo).enumerate().for_each(|(row, acc)| {
        let y = row % ho;
        let co = (row / ho) % cout;
        let ni = row / (ho * cout);
        for ky in 0..kh {
            let iy = (y * strides[0] + ky * dil[0]) as isize - pads[0] as isize;
            if iy < 0 || iy >= h as isize {
                continue;
            }
            let iy = iy as usize;
            for kx in 0..kw {
                let off = (kx * dil[1]) as isize - pads[1] as isize;
                // x with 0 <= x * s + off < wd
                let s = strides[1] as isize;
                let lo = if off >= 0 { 0 } else { ((-off) + s - 1) / s } as usize;
                let hi = if (wd as isize) <= off {
                    0
                } else {
                    (((wd as isize - off - 1) / s) as usize + 1).min(wo)
                };
                if lo >= hi {
                    continue;
                }
                for ci in 0..cin {
                    let wv = w[((co * cin + ci) * kh + ky) * kw + kx];
                    let src = &x[(ni * c + ci) * plane + iy * wd..][..wd];
                    if strides[1] == 1 {
                        let base = (lo as isize + off) as usize;
                        for (a, &v) in acc[lo..hi].iter_mut().zip(&src[base..base + (hi - lo)]) {
                            *a += wv * v;
                        }
                    } else {
                        for (xo, a) in acc.iter_mut().enumerate().take(hi).skip(lo) {
                            *a += wv * src[(xo as isize * s + off) as usize];
                        }
                    }
                }
            }
        }
        if let Some(b) = b {
            for a in acc.iter_mut() {
                *a += b[co];
            }
        }
    });
    Ok((out, [n, cout, ho, wo]))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::learned;

    fn fixture(name: &str) -> Option<Vec<u8>> {
        let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../tests/data/learned")
            .join(name);
        std::fs::read(p).ok()
    }

    fn planes(seed: u64, n: usize) -> Vec<f32> {
        let mut s = seed.max(1);
        (0..n)
            .map(|_| {
                s ^= s << 13;
                s ^= s >> 7;
                s ^= s << 17;
                ((s >> 40) as f32 / (1u64 << 24) as f32) * 4.0 - 2.0
            })
            .collect()
    }

    /// A direct convolution in the documented order, for one output value.
    #[test]
    fn conv_matches_direct_sum_with_stride_and_pads() {
        let (cin, cout, kh, kw, h, wd) = (2, 3, 3, 2, 7, 9);
        let w = planes(5, cout * cin * kh * kw);
        let b = vec![0.5, -0.25, 1.0];
        let op = Op::Conv {
            w: w.clone(),
            cout,
            cin,
            kh,
            kw,
            b: Some(b.clone()),
            dil: [2, 1],
            pads: [2, 1, 1, 0],
            strides: [1, 2],
        };
        let x = planes(9, cin * h * wd);
        let (y, sh) = conv_run(&op, &x, [1, cin, h, wd]).unwrap();
        // torch.nn.functional.conv2d semantics, by hand
        // pads (2, 1, 1, 0), dilation (2, 1), stride (1, 2)
        let ho = h + 3 - (2 * (kh - 1) + 1) + 1;
        let wo = (wd + 1 - kw) / 2 + 1;
        assert_eq!(sh, [1, cout, ho, wo]);
        for co in 0..cout {
            for yo in 0..ho {
                for xo in 0..wo {
                    let mut acc = 0f32;
                    for ky in 0..kh {
                        for kx in 0..kw {
                            for ci in 0..cin {
                                let iy = yo as isize + 2 * ky as isize - 2;
                                let ix = 2 * xo as isize + kx as isize - 1;
                                if iy < 0 || ix < 0 || iy >= h as isize || ix >= wd as isize {
                                    continue;
                                }
                                acc += w[((co * cin + ci) * kh + ky) * kw + kx]
                                    * x[(ci * h + iy as usize) * wd + ix as usize];
                            }
                        }
                    }
                    acc += b[co];
                    assert_eq!(y[(co * ho + yo) * wo + xo].to_bits(), acc.to_bits());
                }
            }
        }
    }

    #[test]
    fn refuses_unknown_op_by_name() {
        let mut m = learned::Model {
            inputs: vec!["x".into()],
            outputs: vec!["y".into()],
            ..Default::default()
        };
        m.nodes.push(learned::Node {
            name: "act".into(),
            op_type: "Sigmoid".into(),
            inputs: vec!["x".into()],
            outputs: vec!["y".into()],
            attributes: vec![],
        });
        let e = Interp::load(&m).unwrap_err().0;
        assert!(e.contains("op Sigmoid") && e.contains("act"), "{e}");
    }

    fn check_network(name: &str, inputs: usize) {
        let Some(buf) = fixture(name) else {
            panic!("{name} missing from tests/data/learned");
        };
        let m = learned::read(&buf).unwrap();
        let it = Interp::load(&m).unwrap();
        let (nt, nc) = (64, 512);
        let x = planes(20261119, inputs * nt * nc);
        let run = |threads: usize, x: &[f32]| {
            rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap()
                .install(|| it.run(x, [1, inputs, nt, nc]).unwrap())
        };
        let (y1, sh) = run(1, &x);
        assert_eq!(sh, [1, 1, nt, nc]);
        // I3 on shape A and on 16 planes run one after another.
        let xb: Vec<Vec<f32>> = (0..16)
            .map(|i| planes(1000 + i, inputs * nt * nc))
            .collect();
        let yb1: Vec<Vec<f32>> = xb.iter().map(|x| run(1, x).0).collect();
        for t in [2, 4, 8, 16] {
            assert!(
                run(t, &x)
                    .0
                    .iter()
                    .zip(&y1)
                    .all(|(a, b)| a.to_bits() == b.to_bits())
            );
            for (x, y) in xb.iter().zip(&yb1) {
                assert!(
                    run(t, x)
                        .0
                        .iter()
                        .zip(y)
                        .all(|(a, b)| a.to_bits() == b.to_bits())
                );
            }
        }
        // I5: the hand-written kernel against the interpreter.
        let flat = learned::dilated_cnn_weights(&m, inputs, 8, &[1, 2, 4, 8, 16]).unwrap();
        let cells = nt * nc;
        let mut h = vec![0f32; cells * inputs];
        for ci in 0..inputs {
            for i in 0..cells {
                h[i * inputs + ci] = x[ci * cells + i];
            }
        }
        let k = learned::dilated_cnn_planes(h, nt, nc, inputs, &flat);
        let d = k
            .iter()
            .zip(&y1)
            .map(|(a, b)| (a - b).abs())
            .fold(0f32, f32::max);
        assert!(d <= 1e-4, "{name}: kernel against interpreter {d}");
    }

    /// F5's N5 (research/f5-flagger.md section 2e on dl3-f5): a 1×1 stem
    /// 33 → 8 with no activation, F3's five dilated 3×3 layers with Relu
    /// and pads equal to the dilation, a 1×1 head; built here, not exported.
    #[test]
    fn f5_shaped_graph_loads_and_is_thread_identical() {
        let attr = |name: &str, v: Vec<i64>| learned::Attribute {
            name: name.into(),
            ints: v,
            ..Default::default()
        };
        let mut m = learned::Model {
            inputs: vec!["x".into()],
            outputs: vec!["y".into()],
            ..Default::default()
        };
        let mut seed = 77;
        let mut conv_node = |m: &mut learned::Model,
                             k: usize,
                             cin: usize,
                             cout: usize,
                             ks: usize,
                             d: i64,
                             src: &str,
                             dst: &str| {
            seed += 1;
            let (wn, bn) = (format!("w{k}"), format!("b{k}"));
            m.initializers.push(learned::Tensor {
                name: wn.clone(),
                dims: vec![cout as i64, cin as i64, ks as i64, ks as i64],
                data: planes(seed, cout * cin * ks * ks)
                    .iter()
                    .map(|v| v * 0.2)
                    .collect(),
            });
            m.initializers.push(learned::Tensor {
                name: bn.clone(),
                dims: vec![cout as i64],
                data: planes(seed + 100, cout),
            });
            let p = if ks == 1 { 0 } else { d };
            m.nodes.push(learned::Node {
                name: format!("conv{k}"),
                op_type: "Conv".into(),
                inputs: vec![src.into(), wn, bn],
                outputs: vec![dst.into()],
                attributes: vec![
                    attr("dilations", vec![d, d]),
                    attr("kernel_shape", vec![ks as i64, ks as i64]),
                    attr("pads", vec![p; 4]),
                    attr("strides", vec![1, 1]),
                ],
            });
        };
        conv_node(&mut m, 0, 33, 8, 1, 1, "x", "s");
        let mut prev = "s".to_string();
        for (k, d) in [1i64, 2, 4, 8, 16].iter().enumerate() {
            let c = format!("c{k}");
            conv_node(&mut m, k + 1, 8, 8, 3, *d, &prev, &c);
            let r = format!("r{k}");
            m.nodes.push(learned::Node {
                name: format!("relu{k}"),
                op_type: "Relu".into(),
                inputs: vec![c],
                outputs: vec![r.clone()],
                attributes: vec![],
            });
            prev = r;
        }
        conv_node(&mut m, 6, 8, 1, 1, 1, &prev, "y");
        let it = Interp::load(&m).unwrap();
        let (nt, nc) = (40, 300);
        let x = planes(5, 33 * nt * nc);
        let run = |t: usize| {
            rayon::ThreadPoolBuilder::new()
                .num_threads(t)
                .build()
                .unwrap()
                .install(|| it.run(&x, [1, 33, nt, nc]).unwrap())
        };
        let (y1, sh) = run(1);
        assert_eq!(sh, [1, 1, nt, nc]);
        assert!(y1.iter().all(|v| v.is_finite()));
        for t in [2, 4, 8, 16] {
            assert!(
                run(t)
                    .0
                    .iter()
                    .zip(&y1)
                    .all(|(a, b)| a.to_bits() == b.to_bits())
            );
        }
    }

    #[test]
    fn f3_threads_and_kernel() {
        check_network("f3-calibrator-seed3.onnx", 15);
    }

    #[test]
    fn f4_threads_and_kernel() {
        check_network("f4-calibrator-seed2.onnx", 23);
    }
}
