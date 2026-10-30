//! Read every column of casacore tables through the `casacure` crate
//! (research/casacure-evaluation.md, criterion R3).
//!
//! Usage: eval-casacure-rs <out-dir> <label>=<table-dir> [...]
//!
//! For each table and column it writes `<out-dir>/<label>/<column>.bin`, the
//! cells' elements in native byte order and casacore cell order (NumPy `bool`
//! is one byte), or `<column>.strings` (one JSON string per line) for string
//! columns, and `<out-dir>/<label>/columns.tsv` with the status, the number
//! of rows, the per-cell shape of row 0 and the read time. Columns that fail
//! are listed with their error. Nothing is written to the tables. With
//! `EVAL_NO_WRITE` set (timing runs) the column files are not written.

use casacure::record::{ArrayData, RecordValue};
use std::fmt::Write as _;
use std::io::Write as _;
use std::path::Path;
use std::time::Instant;

fn push_value(out: &mut Vec<u8>, strings: &mut Vec<String>, v: &RecordValue) -> Result<(), String> {
    match v {
        RecordValue::Bool(b) => out.push(*b as u8),
        RecordValue::UChar(x) => out.push(*x),
        RecordValue::Short(x) => out.extend_from_slice(&x.to_ne_bytes()),
        RecordValue::UShort(x) => out.extend_from_slice(&x.to_ne_bytes()),
        RecordValue::Int(x) => out.extend_from_slice(&x.to_ne_bytes()),
        RecordValue::UInt(x) => out.extend_from_slice(&x.to_ne_bytes()),
        RecordValue::Int64(x) => out.extend_from_slice(&x.to_ne_bytes()),
        RecordValue::Float(x) => out.extend_from_slice(&x.to_ne_bytes()),
        RecordValue::Double(x) => out.extend_from_slice(&x.to_ne_bytes()),
        RecordValue::Complex(re, im) => {
            out.extend_from_slice(&re.to_ne_bytes());
            out.extend_from_slice(&im.to_ne_bytes());
        }
        RecordValue::DComplex(re, im) => {
            out.extend_from_slice(&re.to_ne_bytes());
            out.extend_from_slice(&im.to_ne_bytes());
        }
        RecordValue::String(s) => strings.push(s.clone()),
        RecordValue::Array(a) => match &a.data {
            ArrayData::Bool(v) => out.extend(v.iter().map(|b| *b as u8)),
            ArrayData::UChar(v) => out.extend_from_slice(v),
            ArrayData::Short(v) => v
                .iter()
                .for_each(|x| out.extend_from_slice(&x.to_ne_bytes())),
            ArrayData::UShort(v) => v
                .iter()
                .for_each(|x| out.extend_from_slice(&x.to_ne_bytes())),
            ArrayData::Int(v) => v
                .iter()
                .for_each(|x| out.extend_from_slice(&x.to_ne_bytes())),
            ArrayData::UInt(v) => v
                .iter()
                .for_each(|x| out.extend_from_slice(&x.to_ne_bytes())),
            ArrayData::Int64(v) => v
                .iter()
                .for_each(|x| out.extend_from_slice(&x.to_ne_bytes())),
            ArrayData::Float(v) => v
                .iter()
                .for_each(|x| out.extend_from_slice(&x.to_ne_bytes())),
            ArrayData::Double(v) => v
                .iter()
                .for_each(|x| out.extend_from_slice(&x.to_ne_bytes())),
            ArrayData::Complex(v) => v.iter().for_each(|(re, im)| {
                out.extend_from_slice(&re.to_ne_bytes());
                out.extend_from_slice(&im.to_ne_bytes());
            }),
            ArrayData::DComplex(v) => v.iter().for_each(|(re, im)| {
                out.extend_from_slice(&re.to_ne_bytes());
                out.extend_from_slice(&im.to_ne_bytes());
            }),
            ArrayData::String(v) => strings.extend(v.iter().cloned()),
        },
        other => return Err(format!("unsupported cell value {other:?}")),
    }
    Ok(())
}

fn json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn shape_of(v: &RecordValue) -> String {
    match v {
        RecordValue::Array(a) => format!("{:?}", a.shape),
        _ => "[]".to_string(),
    }
}

fn read_table(label: &str, dir: &Path, out: &Path) -> Result<f64, String> {
    let started = Instant::now();
    let table = casacure::Table::open(dir, true).map_err(|e| format!("open {dir:?}: {e}"))?;
    let target = out.join(label);
    std::fs::create_dir_all(&target).map_err(|e| e.to_string())?;
    let mut index = String::new();
    let nrows = table.nrows();
    for (i, name) in table.colnames().iter().enumerate() {
        let t0 = Instant::now();
        let values = match table.getcol(i, 0, nrows) {
            Ok(values) => values,
            Err(e) => {
                let _ = writeln!(index, "{name}\terror\t{e}");
                continue;
            }
        };
        let mut bytes = Vec::new();
        let mut strings = Vec::new();
        if let Some(e) = values
            .iter()
            .find_map(|v| push_value(&mut bytes, &mut strings, v).err())
        {
            let _ = writeln!(index, "{name}\terror\t{e}");
            continue;
        }
        let seconds = t0.elapsed().as_secs_f64();
        let shape = values.first().map(shape_of).unwrap_or_default();
        if std::env::var_os("EVAL_NO_WRITE").is_some() {
            // Timing runs: decode into the byte buffer, keep nothing.
        } else if strings.is_empty() {
            std::fs::write(target.join(format!("{name}.bin")), &bytes)
                .map_err(|e| e.to_string())?;
        } else {
            let mut f = std::fs::File::create(target.join(format!("{name}.strings")))
                .map_err(|e| e.to_string())?;
            for s in &strings {
                writeln!(f, "{}", json_string(s)).map_err(|e| e.to_string())?;
            }
        }
        let _ = writeln!(index, "{name}\tok\t{nrows}\t{shape}\t{seconds:.6}");
    }
    std::fs::write(target.join("columns.tsv"), index).map_err(|e| e.to_string())?;
    Ok(started.elapsed().as_secs_f64())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: eval-casacure-rs <out-dir> <label>=<table-dir> [...]");
        std::process::exit(2);
    }
    let out = Path::new(&args[1]);
    let started = Instant::now();
    let mut failed = false;
    for spec in &args[2..] {
        let Some((label, dir)) = spec.split_once('=') else {
            eprintln!("expected <label>=<table-dir>, got {spec}");
            std::process::exit(2);
        };
        match read_table(label, Path::new(dir), out) {
            Ok(seconds) => println!("{label}\t{seconds:.4} s"),
            Err(e) => {
                println!("{label}\tERROR {e}");
                failed = true;
            }
        }
    }
    println!("total\t{:.4} s", started.elapsed().as_secs_f64());
    if failed {
        std::process::exit(1);
    }
}
