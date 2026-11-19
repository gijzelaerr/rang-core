// SPDX-License-Identifier: MIT
//! Weights files of learned stages (task DL1, `research/dl1-contract.md`):
//! a small reader of ONNX `ModelProto` that needs neither protoc nor an ONNX
//! runtime, and the mapping of a `dilated-cnn/1` graph (F2-F5's network)
//! onto the flat weight order of the Rust kernels (`f3flag::network`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! Field numbers are `onnx.proto`'s (checked against onnx 1.23.2):
//! `ModelProto` 7 graph, 14 metadata_props; `StringStringEntryProto` 1 key,
//! 2 value; `GraphProto` 1 node, 5 initializer, 11 input, 12 output;
//! `ValueInfoProto` 1 name; `NodeProto` 1 input, 2 output, 3 name,
//! 4 op_type, 5 attribute; `AttributeProto` 1 name, 3 i, 8 ints;
//! `TensorProto` 1 dims, 2 data_type, 4 float_data, 8 name, 9 raw_data,
//! 14 data_location. Only FLOAT (1) tensors stored in the file are read.

use std::collections::HashMap;

/// One tensor of the graph (FLOAT only), row-major.
#[derive(Debug, Clone, PartialEq)]
pub struct Tensor {
    pub name: String,
    pub dims: Vec<i64>,
    pub data: Vec<f32>,
}

/// One attribute: an integer or a list of integers (all the
/// `dilated-cnn/1` mapping reads); other kinds are kept as absent.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Attribute {
    pub name: String,
    pub i: Option<i64>,
    pub ints: Vec<i64>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Node {
    pub name: String,
    pub op_type: String,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    pub attributes: Vec<Attribute>,
}

impl Node {
    pub fn attr(&self, name: &str) -> Option<&Attribute> {
        self.attributes.iter().find(|a| a.name == name)
    }
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Model {
    pub metadata: Vec<(String, String)>,
    pub nodes: Vec<Node>,
    pub initializers: Vec<Tensor>,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
}

/// Why a file was refused.
#[derive(Debug, Clone, PartialEq)]
pub struct Error(pub String);

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

fn err<T>(text: impl Into<String>) -> Result<T, Error> {
    Err(Error(text.into()))
}

/// A protobuf field: number and payload.
enum Value<'a> {
    Varint(u64),
    Fixed32(u32),
    Bytes(&'a [u8]),
}

struct Reader<'a> {
    buf: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn new(buf: &'a [u8]) -> Self {
        Reader { buf, at: 0 }
    }

    fn varint(&mut self) -> Result<u64, Error> {
        let mut v = 0u64;
        for shift in (0..64).step_by(7) {
            let Some(&b) = self.buf.get(self.at) else {
                return err("truncated varint");
            };
            self.at += 1;
            v |= ((b & 0x7f) as u64) << shift;
            if b & 0x80 == 0 {
                return Ok(v);
            }
        }
        err("varint longer than 10 bytes")
    }

    fn take(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let end = self.at.checked_add(n).filter(|&e| e <= self.buf.len());
        let Some(end) = end else {
            return err("truncated field");
        };
        let s = &self.buf[self.at..end];
        self.at = end;
        Ok(s)
    }

    fn next(&mut self) -> Result<Option<(u32, Value<'a>)>, Error> {
        if self.at >= self.buf.len() {
            return Ok(None);
        }
        let key = self.varint()?;
        let field = (key >> 3) as u32;
        let v = match key & 7 {
            0 => Value::Varint(self.varint()?),
            1 => {
                self.take(8)?;
                Value::Varint(0)
            }
            2 => {
                let n = self.varint()? as usize;
                Value::Bytes(self.take(n)?)
            }
            5 => {
                let b = self.take(4)?;
                Value::Fixed32(u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
            }
            w => return err(format!("wire type {w} not supported")),
        };
        Ok(Some((field, v)))
    }
}

fn string(v: &Value) -> Result<String, Error> {
    match v {
        Value::Bytes(b) => String::from_utf8(b.to_vec()).map_err(|_| Error("not UTF-8".into())),
        _ => err("expected a string"),
    }
}

fn bytes<'a>(v: &Value<'a>) -> Result<&'a [u8], Error> {
    match v {
        Value::Bytes(b) => Ok(b),
        _ => err("expected a message"),
    }
}

/// Repeated int64: packed or one per field.
fn push_ints(v: &Value, out: &mut Vec<i64>) -> Result<(), Error> {
    match v {
        Value::Varint(x) => out.push(*x as i64),
        Value::Bytes(b) => {
            let mut r = Reader::new(b);
            while r.at < b.len() {
                out.push(r.varint()? as i64);
            }
        }
        _ => return err("expected int64"),
    }
    Ok(())
}

fn entry(buf: &[u8]) -> Result<(String, String), Error> {
    let mut r = Reader::new(buf);
    let (mut k, mut v) = (String::new(), String::new());
    while let Some((f, val)) = r.next()? {
        match f {
            1 => k = string(&val)?,
            2 => v = string(&val)?,
            _ => {}
        }
    }
    Ok((k, v))
}

fn value_info_name(buf: &[u8]) -> Result<String, Error> {
    let mut r = Reader::new(buf);
    let mut name = String::new();
    while let Some((f, val)) = r.next()? {
        if f == 1 {
            name = string(&val)?;
        }
    }
    Ok(name)
}

fn attribute(buf: &[u8]) -> Result<Attribute, Error> {
    let mut r = Reader::new(buf);
    let mut a = Attribute::default();
    while let Some((f, val)) = r.next()? {
        match f {
            1 => a.name = string(&val)?,
            3 => {
                if let Value::Varint(x) = val {
                    a.i = Some(x as i64);
                }
            }
            8 => push_ints(&val, &mut a.ints)?,
            _ => {}
        }
    }
    Ok(a)
}

fn node(buf: &[u8]) -> Result<Node, Error> {
    let mut r = Reader::new(buf);
    let mut n = Node::default();
    while let Some((f, val)) = r.next()? {
        match f {
            1 => n.inputs.push(string(&val)?),
            2 => n.outputs.push(string(&val)?),
            3 => n.name = string(&val)?,
            4 => n.op_type = string(&val)?,
            5 => n.attributes.push(attribute(bytes(&val)?)?),
            _ => {}
        }
    }
    Ok(n)
}

fn tensor(buf: &[u8]) -> Result<Tensor, Error> {
    let mut r = Reader::new(buf);
    let mut dims = Vec::new();
    let mut name = String::new();
    let mut dtype = 0u64;
    let mut floats = Vec::new();
    let mut raw: Option<&[u8]> = None;
    let mut external = false;
    while let Some((f, val)) = r.next()? {
        match f {
            1 => push_ints(&val, &mut dims)?,
            2 => {
                if let Value::Varint(x) = val {
                    dtype = x;
                }
            }
            4 => match val {
                Value::Fixed32(x) => floats.push(f32::from_bits(x)),
                Value::Bytes(b) => {
                    if b.len() % 4 != 0 {
                        return err("float_data not a multiple of 4 bytes");
                    }
                    floats.extend(
                        b.chunks_exact(4)
                            .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]])),
                    );
                }
                _ => return err("bad float_data"),
            },
            8 => name = string(&val)?,
            9 => raw = Some(bytes(&val)?),
            14 => {
                if let Value::Varint(x) = val {
                    external = x == 1;
                }
            }
            _ => {}
        }
    }
    if external {
        return err(format!("tensor {name}: external data is not supported"));
    }
    if dtype != 1 {
        return err(format!(
            "tensor {name}: data type {dtype}, only FLOAT (1) is read"
        ));
    }
    let data = match raw {
        Some(b) => {
            if b.len() % 4 != 0 {
                return err(format!("tensor {name}: raw_data not a multiple of 4 bytes"));
            }
            b.chunks_exact(4)
                .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
                .collect()
        }
        None => floats,
    };
    let count = dims.iter().try_fold(
        1i64,
        |acc, &d| {
            if d < 0 { None } else { acc.checked_mul(d) }
        },
    );
    if count != Some(data.len() as i64) {
        return err(format!(
            "tensor {name}: dims {dims:?} hold {count:?} values, the file {}",
            data.len()
        ));
    }
    Ok(Tensor { name, dims, data })
}

fn graph(buf: &[u8], m: &mut Model) -> Result<(), Error> {
    let mut r = Reader::new(buf);
    while let Some((f, val)) = r.next()? {
        match f {
            1 => m.nodes.push(node(bytes(&val)?)?),
            5 => m.initializers.push(tensor(bytes(&val)?)?),
            11 => m.inputs.push(value_info_name(bytes(&val)?)?),
            12 => m.outputs.push(value_info_name(bytes(&val)?)?),
            _ => {}
        }
    }
    Ok(())
}

/// Read an ONNX `ModelProto`: metadata, nodes, FLOAT initializers, graph
/// inputs and outputs (initializers listed as inputs by old exporters are
/// left out of `inputs`).
pub fn read(buf: &[u8]) -> Result<Model, Error> {
    let mut m = Model::default();
    let mut r = Reader::new(buf);
    let mut seen_graph = false;
    while let Some((f, val)) = r.next()? {
        match f {
            7 => {
                graph(bytes(&val)?, &mut m)?;
                seen_graph = true;
            }
            14 => m.metadata.push(entry(bytes(&val)?)?),
            _ => {}
        }
    }
    if !seen_graph {
        return err("no graph: not an ONNX model");
    }
    let names: std::collections::HashSet<&str> =
        m.initializers.iter().map(|t| t.name.as_str()).collect();
    let inputs = m
        .inputs
        .iter()
        .filter(|n| !names.contains(n.as_str()))
        .cloned()
        .collect();
    m.inputs = inputs;
    Ok(m)
}

/// The flat weights of a `dilated-cnn/1` graph in the Rust kernels' order
/// (`f3flag::weight_count_for`): per layer W (ky, kx, cin, cout) row-major
/// then b; the head W (hidden, 1) then b. The graph must be exactly
/// `len(dilations)` 3×3 Conv nodes with the given dilations and padding
/// equal to the dilation, each followed by Relu, then one 1×1 Conv head
/// with one output channel; anything else is refused. The values are
/// copied, never computed, so the kernel sees the trained float32 values.
pub fn dilated_cnn_weights(
    m: &Model,
    inputs: usize,
    hidden: usize,
    dilations: &[usize],
) -> Result<Vec<f32>, Error> {
    let init: HashMap<&str, &Tensor> = m
        .initializers
        .iter()
        .map(|t| (t.name.as_str(), t))
        .collect();
    let ops: Vec<&str> = m.nodes.iter().map(|n| n.op_type.as_str()).collect();
    let mut want = Vec::new();
    for _ in dilations {
        want.push("Conv");
        want.push("Relu");
    }
    want.push("Conv");
    if ops != want {
        return err(format!("dilated-cnn/1: nodes {ops:?}, expected {want:?}"));
    }
    let mut out = Vec::new();
    let mut cin = inputs;
    let convs: Vec<&Node> = m.nodes.iter().filter(|n| n.op_type == "Conv").collect();
    for (k, n) in convs.iter().enumerate() {
        let head = k == dilations.len();
        let (cout, ksize, d) = if head {
            (1usize, 1usize, 1usize)
        } else {
            (hidden, 3, dilations[k])
        };
        if n.inputs.len() != 3 {
            return err(format!("Conv {k}: needs weight and bias inputs"));
        }
        let (Some(w), Some(b)) = (
            init.get(n.inputs[1].as_str()),
            init.get(n.inputs[2].as_str()),
        ) else {
            return err(format!("Conv {k}: weight or bias is not an initializer"));
        };
        let shape = [cout as i64, cin as i64, ksize as i64, ksize as i64];
        if w.dims != shape || b.dims != [cout as i64] {
            return err(format!(
                "Conv {k}: weight {:?} bias {:?}, expected {shape:?} [{cout}]",
                w.dims, b.dims
            ));
        }
        let ints = |name: &str, default: Vec<i64>| {
            n.attr(name)
                .map(|a| a.ints.clone())
                .filter(|v| !v.is_empty())
                .unwrap_or(default)
        };
        let di = d as i64;
        let p = if head { 0 } else { di };
        let checks = [
            ("dilations", ints("dilations", vec![1, 1]), vec![di, di]),
            ("strides", ints("strides", vec![1, 1]), vec![1, 1]),
            ("pads", ints("pads", vec![0, 0, 0, 0]), vec![p, p, p, p]),
            (
                "kernel_shape",
                ints("kernel_shape", vec![ksize as i64; 2]),
                vec![ksize as i64; 2],
            ),
        ];
        for (name, got, expect) in checks {
            if got != expect {
                return err(format!("Conv {k}: {name} {got:?}, expected {expect:?}"));
            }
        }
        if n.attr("group").and_then(|a| a.i).unwrap_or(1) != 1 {
            return err(format!("Conv {k}: group must be 1"));
        }
        if let Some(a) = n.attr("auto_pad")
            && a.i.is_some()
        {
            return err(format!("Conv {k}: auto_pad not supported"));
        }
        // OIHW -> (ky, kx, cin, cout)
        for ky in 0..ksize {
            for kx in 0..ksize {
                for ci in 0..cin {
                    for co in 0..cout {
                        out.push(w.data[((co * cin + ci) * ksize + ky) * ksize + kx]);
                    }
                }
            }
        }
        out.extend_from_slice(&b.data);
        cin = hidden;
    }
    // Wiring: each node reads the previous node's output; the first reads
    // the graph input; the last writes the graph output.
    for (k, n) in m.nodes.iter().enumerate() {
        let src = if k == 0 {
            m.inputs.first().cloned()
        } else {
            m.nodes[k - 1].outputs.first().cloned()
        };
        if n.inputs.first().cloned() != src || n.outputs.len() != 1 {
            return err(format!("node {k} ({}): not a chain", n.op_type));
        }
    }
    if m.inputs.len() != 1
        || m.outputs.len() != 1
        || m.nodes.last().map(|n| &n.outputs[0]) != m.outputs.first()
    {
        return err("dilated-cnn/1: needs one graph input and one output");
    }
    Ok(out)
}

/// Logits (nt × nc) of one (time, channel) plane through a `dilated-cnn/1`
/// with hidden 8 and dilations [1, 2, 4, 8, 16]: `h` (time, channel,
/// inputs) cell-major, `w` in the flat order. The arithmetic of
/// `f3flag::network` (the same convolutions in the same order), without
/// the rows of a scan: the reference fast path of section 7 of
/// `research/dl1-contract.md`.
pub fn dilated_cnn_planes(
    mut h: Vec<f32>,
    nt: usize,
    nc: usize,
    inputs: usize,
    w: &[f32],
) -> Vec<f32> {
    use crate::f3flag::{DILATIONS, HIDDEN, conv, weight_count_for};
    assert_eq!(w.len(), weight_count_for(inputs));
    assert_eq!(h.len(), nt * nc * inputs);
    let ncell = nt * nc;
    let mut at = 0;
    let mut cin = inputs;
    let mut next = vec![0f32; ncell * HIDDEN];
    for &d in DILATIONS.iter() {
        let wl = &w[at..at + 9 * cin * HIDDEN];
        let bl = &w[at + 9 * cin * HIDDEN..at + 9 * cin * HIDDEN + HIDDEN];
        at += 9 * cin * HIDDEN + HIDDEN;
        conv(&h, &mut next, nt, nc, cin, d, wl, bl);
        std::mem::swap(&mut h, &mut next);
        if next.len() != ncell * HIDDEN {
            next = vec![0f32; ncell * HIDDEN];
        }
        cin = HIDDEN;
    }
    let wh = &w[at..at + HIDDEN];
    let bh = w[at + HIDDEN];
    (0..ncell)
        .map(|c| {
            let o = c * HIDDEN;
            let mut acc = 0f32;
            for k in 0..HIDDEN {
                acc += wh[k] * h[o + k];
            }
            acc + bh
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn varint(mut v: u64, out: &mut Vec<u8>) {
        loop {
            let b = (v & 0x7f) as u8;
            v >>= 7;
            if v == 0 {
                out.push(b);
                return;
            }
            out.push(b | 0x80);
        }
    }

    fn field_bytes(f: u32, b: &[u8], out: &mut Vec<u8>) {
        varint(((f as u64) << 3) | 2, out);
        varint(b.len() as u64, out);
        out.extend_from_slice(b);
    }

    fn field_varint(f: u32, v: u64, out: &mut Vec<u8>) {
        varint((f as u64) << 3, out);
        varint(v, out);
    }

    fn tensor_bytes(name: &str, dims: &[i64], data: &[f32]) -> Vec<u8> {
        let mut t = Vec::new();
        for &d in dims {
            field_varint(1, d as u64, &mut t);
        }
        field_varint(2, 1, &mut t);
        field_bytes(8, name.as_bytes(), &mut t);
        let raw: Vec<u8> = data.iter().flat_map(|x| x.to_le_bytes()).collect();
        field_bytes(9, &raw, &mut t);
        t
    }

    fn ints_attr(name: &str, v: &[i64]) -> Vec<u8> {
        let mut a = Vec::new();
        field_bytes(1, name.as_bytes(), &mut a);
        for &x in v {
            field_varint(8, x as u64, &mut a);
        }
        a
    }

    fn node_bytes(op: &str, ins: &[&str], out: &str, attrs: &[Vec<u8>]) -> Vec<u8> {
        let mut n = Vec::new();
        for i in ins {
            field_bytes(1, i.as_bytes(), &mut n);
        }
        field_bytes(2, out.as_bytes(), &mut n);
        field_bytes(4, op.as_bytes(), &mut n);
        for a in attrs {
            field_bytes(5, a, &mut n);
        }
        n
    }

    fn vi(name: &str) -> Vec<u8> {
        let mut v = Vec::new();
        field_bytes(1, name.as_bytes(), &mut v);
        v
    }

    /// A two-layer dilated-cnn/1 (inputs 2, hidden 3, dilations [1, 2]).
    fn model(dil2: i64) -> (Vec<u8>, Vec<f32>) {
        let (inputs, hidden) = (2usize, 3usize);
        let mut g = Vec::new();
        let mut expect = Vec::new();
        let mut prev = "x".to_string();
        let mut cin = inputs;
        let mut v = 0f32;
        for (k, d) in [1i64, dil2].iter().enumerate() {
            let n = hidden * cin * 9;
            let w: Vec<f32> = (0..n)
                .map(|_| {
                    v += 1.0;
                    v
                })
                .collect();
            let b: Vec<f32> = (0..hidden).map(|i| -(i as f32) - 0.5).collect();
            for ky in 0..3 {
                for kx in 0..3 {
                    for ci in 0..cin {
                        for co in 0..hidden {
                            expect.push(w[((co * cin + ci) * 3 + ky) * 3 + kx]);
                        }
                    }
                }
            }
            expect.extend_from_slice(&b);
            let (wn, bn) = (format!("w{k}"), format!("b{k}"));
            field_bytes(5, &tensor_bytes(&wn, &[3, cin as i64, 3, 3], &w), &mut g);
            field_bytes(5, &tensor_bytes(&bn, &[3], &b), &mut g);
            let c = format!("c{k}");
            let attrs = vec![
                ints_attr("dilations", &[*d, *d]),
                ints_attr("pads", &[*d; 4]),
                ints_attr("kernel_shape", &[3, 3]),
            ];
            field_bytes(
                1,
                &node_bytes("Conv", &[&prev, &wn, &bn], &c, &attrs),
                &mut g,
            );
            let r = format!("r{k}");
            field_bytes(1, &node_bytes("Relu", &[&c], &r, &[]), &mut g);
            prev = r;
            cin = hidden;
        }
        let hw = [0.25f32, -0.5, 0.75];
        field_bytes(5, &tensor_bytes("hw", &[1, 3, 1, 1], &hw), &mut g);
        field_bytes(5, &tensor_bytes("hb", &[1], &[0.125]), &mut g);
        expect.extend_from_slice(&hw);
        expect.push(0.125);
        field_bytes(
            1,
            &node_bytes("Conv", &[&prev, "hw", "hb"], "y", &[]),
            &mut g,
        );
        field_bytes(11, &vi("x"), &mut g);
        field_bytes(12, &vi("y"), &mut g);
        let mut m = Vec::new();
        field_varint(1, 8, &mut m);
        field_bytes(7, &g, &mut m);
        let mut e = Vec::new();
        field_bytes(1, b"rang.learned", &mut e);
        field_bytes(2, b"{\"format\":\"rang.learned/1\"}", &mut e);
        field_bytes(14, &e, &mut m);
        (m, expect)
    }

    #[test]
    fn reads_and_maps_dilated_cnn() {
        let (buf, expect) = model(2);
        let m = read(&buf).unwrap();
        assert_eq!(m.metadata[0].0, "rang.learned");
        assert_eq!(m.inputs, vec!["x"]);
        assert_eq!(m.outputs, vec!["y"]);
        let w = dilated_cnn_weights(&m, 2, 3, &[1, 2]).unwrap();
        assert_eq!(w, expect);
    }

    #[test]
    fn refuses_wrong_dilation_and_shape() {
        let (buf, _) = model(4);
        let m = read(&buf).unwrap();
        assert!(dilated_cnn_weights(&m, 2, 3, &[1, 2]).is_err());
        let (buf, _) = model(2);
        let m = read(&buf).unwrap();
        assert!(dilated_cnn_weights(&m, 3, 3, &[1, 2]).is_err());
        assert!(dilated_cnn_weights(&m, 2, 3, &[1, 2, 4]).is_err());
    }

    #[test]
    fn refuses_garbage() {
        assert!(read(&[0xff, 0xff]).is_err());
        assert!(read(&[]).is_err());
    }
}
