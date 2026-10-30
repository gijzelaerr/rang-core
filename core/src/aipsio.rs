//! AipsIO serialisation and casacore records for the table writer
//! (research/e3-table-writer.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The format was read in the casacore 3.8.1 sources (`casa/IO/AipsIO.cc`,
//! `casa/IO/TypeIO.cc`, `casa/IO/IPositionIO.cc`, `casa/IO/ArrayIO.tcc`,
//! `casa/Containers/RecordDesc.cc`, `casa/Containers/RecordRep.cc`,
//! `casa/BasicSL/STLIO.tcc`, `tables/Tables/TableRecordRep.cc`); nothing is
//! copied from casacore (LGPL-2.1-or-later). Reading uses the task E cursor
//! (`ms::Cursor`); this module adds the writer and a record model that keeps
//! every field so that `serialise(parse(x)) == x`.

use crate::ms::{Cursor, MAGIC, MsError, Result};

/// casacore `DataType` codes of record fields (casa/Utilities/DataType.h).
pub mod tp {
    pub const BOOL: i32 = 0;
    pub const CHAR: i32 = 1;
    pub const UCHAR: i32 = 2;
    pub const SHORT: i32 = 3;
    pub const USHORT: i32 = 4;
    pub const INT: i32 = 5;
    pub const UINT: i32 = 6;
    pub const FLOAT: i32 = 7;
    pub const DOUBLE: i32 = 8;
    pub const COMPLEX: i32 = 9;
    pub const DCOMPLEX: i32 = 10;
    pub const STRING: i32 = 11;
    pub const TABLE: i32 = 12;
    pub const ARRAY_BOOL: i32 = 13;
    pub const ARRAY_STRING: i32 = 24;
    pub const RECORD: i32 = 25;
    pub const INT64: i32 = 29;
    pub const ARRAY_INT64: i32 = 30;

    /// The array type code of a scalar type code.
    pub fn array_of(code: i32) -> Option<i32> {
        match code {
            0..=11 => Some(code + 13),
            29 => Some(30),
            _ => None,
        }
    }

    /// True for the array type codes.
    pub fn is_array(code: i32) -> bool {
        (13..=24).contains(&code) || code == 30
    }

    /// Bytes of one canonical value of a scalar type (0: variable or none).
    pub fn scalar_size(code: i32) -> usize {
        match code {
            0..=2 => 1,
            3 | 4 => 2,
            5..=7 => 4,
            8 | 9 | 29 => 8,
            10 => 16,
            _ => 0,
        }
    }

    /// The object name `RecordRep::putDataField` gives an array of this type.
    pub fn array_object_name(code: i32) -> &'static str {
        match code {
            15 => "Array<uChar>",
            16 => "Array<short>",
            18 => "Array<Int>",
            19 => "Array<uInt>",
            30 => "Array<Int64>",
            20 => "Array<float>",
            21 => "Array<double>",
            24 => "Array<String>",
            _ => "Array<void>",
        }
    }
}

// ---------------------------------------------------------------------------
// The writer.

/// An AipsIO output stream into memory, canonical big-endian or the
/// little-endian canonical format of `LECanonicalIO`.
pub struct Writer {
    pub buf: Vec<u8>,
    big: bool,
    starts: Vec<usize>,
}

impl Writer {
    pub fn new(big: bool) -> Self {
        Writer {
            buf: Vec::new(),
            big,
            starts: Vec::new(),
        }
    }

    /// Start an object; a top-level object is preceded by the magic value.
    /// The length is back-patched by `putend`.
    pub fn putstart(&mut self, kind: &str, version: u32) {
        if self.starts.is_empty() {
            self.u32(MAGIC);
        }
        self.starts.push(self.buf.len());
        self.u32(MAGIC);
        self.string(kind);
        self.u32(version);
    }

    pub fn putend(&mut self) {
        let start = self.starts.pop().expect("putend without putstart");
        let length = (self.buf.len() - start) as u32;
        let bytes = if self.big {
            length.to_be_bytes()
        } else {
            length.to_le_bytes()
        };
        self.buf[start..start + 4].copy_from_slice(&bytes);
    }

    pub fn bytes(&mut self, b: &[u8]) {
        self.buf.extend_from_slice(b);
    }

    pub fn u8(&mut self, v: u8) {
        self.buf.push(v);
    }

    pub fn bool(&mut self, v: bool) {
        self.buf.push(u8::from(v));
    }

    pub fn u16(&mut self, v: u16) {
        let b = if self.big {
            v.to_be_bytes()
        } else {
            v.to_le_bytes()
        };
        self.buf.extend(b);
    }

    pub fn u32(&mut self, v: u32) {
        let b = if self.big {
            v.to_be_bytes()
        } else {
            v.to_le_bytes()
        };
        self.buf.extend(b);
    }

    pub fn i32(&mut self, v: i32) {
        self.u32(v as u32);
    }

    pub fn u64(&mut self, v: u64) {
        let b = if self.big {
            v.to_be_bytes()
        } else {
            v.to_le_bytes()
        };
        self.buf.extend(b);
    }

    pub fn i64(&mut self, v: i64) {
        self.u64(v as u64);
    }

    pub fn f32(&mut self, v: f32) {
        self.u32(v.to_bits());
    }

    pub fn f64(&mut self, v: f64) {
        self.u64(v.to_bits());
    }

    pub fn string(&mut self, s: &str) {
        self.u32(s.len() as u32);
        self.buf.extend_from_slice(s.as_bytes());
    }

    /// `IPosition`: version 1 (Int values) unless a value exceeds Int.
    pub fn iposition(&mut self, shape: &[i64]) {
        let wide = shape.iter().any(|&v| v > i64::from(i32::MAX));
        self.putstart("IPosition", if wide { 2 } else { 1 });
        self.u32(shape.len() as u32);
        for &v in shape {
            if wide {
                self.i64(v);
            } else {
                self.i32(v as i32);
            }
        }
        self.putend();
    }

    /// `putBlock` of `uInt` values.
    pub fn block_u32(&mut self, values: &[u32]) {
        self.putstart("Block", 1);
        self.u32(values.len() as u32);
        for &v in values {
            self.u32(v);
        }
        self.putend();
    }

    /// `putBlock` of `uInt64` values.
    pub fn block_u64(&mut self, values: &[u64]) {
        self.putstart("Block", 1);
        self.u32(values.len() as u32);
        for &v in values {
            self.u64(v);
        }
        self.putend();
    }

    /// `AipsIO::put(uInt n, const uChar*)`: the count, then the bytes.
    pub fn uchar_block(&mut self, b: &[u8]) {
        self.u32(b.len() as u32);
        self.buf.extend_from_slice(b);
    }

    /// A `std::map<Int,Int>` as `SimpleOrderedMap` (STLIO.tcc).
    pub fn int_map(&mut self, map: &[(i32, i32)]) {
        self.putstart("SimpleOrderedMap", 1);
        self.i32(0);
        self.u32(map.len() as u32);
        self.u32(1);
        for &(k, v) in map {
            self.i32(k);
            self.i32(v);
        }
        self.putend();
    }
}

/// Read a `SimpleOrderedMap` of Int keys and values.
pub fn read_int_map(c: &mut Cursor<'_>) -> Result<Vec<(i32, i32)>> {
    let object = c.start_expect("SimpleOrderedMap")?;
    let _default = c.i32()?;
    let n = c.u32()? as usize;
    let _incr = c.u32()?;
    let mut out = Vec::with_capacity(n);
    for _ in 0..n {
        out.push((c.i32()?, c.i32()?));
    }
    c.end(&object);
    Ok(out)
}

/// The raw bytes of the next nested object (its length field onwards).
pub fn raw_object(c: &mut Cursor<'_>) -> Result<Vec<u8>> {
    let at = c.pos;
    let object = c.start()?;
    c.end(&object);
    Ok(c.bytes[at..c.pos].to_vec())
}

// ---------------------------------------------------------------------------
// Records.

/// One field of a `RecordDesc`.
#[derive(Clone, Debug, PartialEq)]
pub struct FieldDesc {
    pub name: String,
    pub dtype: i32,
    /// The description of a sub-record field.
    pub sub: Option<RecordDesc>,
    /// The shape of an array field.
    pub shape: Option<Vec<i64>>,
    /// The table description name of a table field.
    pub table_desc: Option<String>,
    pub comment: String,
}

/// A `RecordDesc` (version 2).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct RecordDesc {
    pub fields: Vec<FieldDesc>,
}

/// A field value: the canonical bytes of a scalar, string, table name or
/// array object, or a sub-record.
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Raw(Vec<u8>),
    Record(Box<Record>),
}

/// A `TableRecord`: its description, record type (0 fixed, 1 variable) and
/// one value per field.
#[derive(Clone, Debug, PartialEq)]
pub struct Record {
    pub desc: RecordDesc,
    pub record_type: i32,
    pub values: Vec<Value>,
}

impl Default for Record {
    fn default() -> Self {
        Record {
            desc: RecordDesc::default(),
            record_type: 1,
            values: Vec::new(),
        }
    }
}

impl RecordDesc {
    pub fn read(c: &mut Cursor<'_>) -> Result<Self> {
        let object = c.start_expect("RecordDesc")?;
        if object.version != 2 && object.version != 1 {
            return Err(MsError(format!(
                "RecordDesc version {} is not supported",
                object.version
            )));
        }
        let n = c.i32()?.max(0) as usize;
        let mut fields = Vec::with_capacity(n);
        for _ in 0..n {
            let name = c.string()?;
            let dtype = c.i32()?;
            let (mut sub, mut shape, mut table_desc) = (None, None, None);
            if dtype == tp::RECORD {
                sub = Some(RecordDesc::read(c)?);
            } else if tp::is_array(dtype) {
                shape = Some(c.iposition()?);
            } else if dtype == tp::TABLE {
                table_desc = Some(c.string()?);
            }
            let comment = if object.version >= 2 {
                c.string()?
            } else {
                String::new()
            };
            fields.push(FieldDesc {
                name,
                dtype,
                sub,
                shape,
                table_desc,
                comment,
            });
        }
        c.end(&object);
        Ok(RecordDesc { fields })
    }

    pub fn write(&self, w: &mut Writer) {
        w.putstart("RecordDesc", 2);
        w.i32(self.fields.len() as i32);
        for f in &self.fields {
            w.string(&f.name);
            w.i32(f.dtype);
            if let Some(sub) = &f.sub {
                sub.write(w);
            } else if let Some(shape) = &f.shape {
                w.iposition(shape);
            } else if let Some(name) = &f.table_desc {
                w.string(name);
            }
            w.string(&f.comment);
        }
        w.putend();
    }
}

impl Record {
    /// Read a `TableRecord` object (the only keyword-set form written by
    /// casacore 3.x).
    pub fn read(c: &mut Cursor<'_>) -> Result<Self> {
        let object = c.start()?;
        if object.kind != "TableRecord" && object.kind != "Record" {
            return Err(MsError(format!(
                "keyword set {} is not supported",
                object.kind
            )));
        }
        let desc = RecordDesc::read(c)?;
        let record_type = c.i32()?;
        let values = Self::read_data(c, &desc)?;
        c.end(&object);
        Ok(Record {
            desc,
            record_type,
            values,
        })
    }

    fn read_data(c: &mut Cursor<'_>, desc: &RecordDesc) -> Result<Vec<Value>> {
        let mut values = Vec::with_capacity(desc.fields.len());
        for f in &desc.fields {
            values.push(match f.dtype {
                tp::RECORD => {
                    let sub = f.sub.as_ref().unwrap();
                    if sub.fields.is_empty() {
                        Value::Record(Box::new(Record::read(c)?))
                    } else {
                        Value::Record(Box::new(Record {
                            desc: sub.clone(),
                            record_type: 0,
                            values: Self::read_data(c, sub)?,
                        }))
                    }
                }
                tp::STRING | tp::TABLE => {
                    let at = c.pos;
                    c.string()?;
                    Value::Raw(c.bytes[at..c.pos].to_vec())
                }
                code if tp::is_array(code) => Value::Raw(raw_object(c)?),
                code => {
                    let size = tp::scalar_size(code);
                    if size == 0 {
                        return Err(MsError(format!(
                            "record field {} has unsupported type {code}",
                            f.name
                        )));
                    }
                    Value::Raw(c.take(size)?.to_vec())
                }
            });
        }
        Ok(values)
    }

    /// Write as a `TableRecord` object.
    pub fn write(&self, w: &mut Writer) {
        w.putstart("TableRecord", 1);
        self.desc.write(w);
        w.i32(self.record_type);
        self.write_data(w);
        w.putend();
    }

    fn write_data(&self, w: &mut Writer) {
        for (f, v) in self.desc.fields.iter().zip(&self.values) {
            match v {
                Value::Raw(b) => w.bytes(b),
                Value::Record(r) => {
                    if f.sub.as_ref().is_none_or(|s| s.fields.is_empty()) {
                        r.write(w);
                    } else {
                        r.write_data(w);
                    }
                }
            }
        }
    }

    pub fn field(&self, name: &str) -> Option<usize> {
        self.desc.fields.iter().position(|f| f.name == name)
    }

    /// Define or replace a field as `Record::define` does: a field of the
    /// same type keeps its place and description and gets the new value; a
    /// field of another type is removed and the new one appended. New array
    /// fields are described with shape [-1] (variable) and sub-records with
    /// an empty (variable) description.
    pub fn define(&mut self, name: &str, value: KeywordValue) -> Result<()> {
        let (dtype, shape, encoded) = value.encode()?;
        if let Some(i) = self.field(name) {
            if self.desc.fields[i].dtype == dtype {
                self.values[i] = encoded;
                return Ok(());
            }
            self.desc.fields.remove(i);
            self.values.remove(i);
        }
        self.desc.fields.push(FieldDesc {
            name: name.to_string(),
            dtype,
            sub: (dtype == tp::RECORD).then(RecordDesc::default),
            shape,
            table_desc: None,
            comment: String::new(),
        });
        self.values.push(encoded);
        Ok(())
    }

    /// The sub-record of field `name`, created empty when absent.
    pub fn subrecord_mut(&mut self, name: &str) -> Result<&mut Record> {
        let i = match self.field(name) {
            Some(i) => i,
            None => {
                self.define(name, KeywordValue::Record)?;
                self.desc.fields.len() - 1
            }
        };
        match &mut self.values[i] {
            Value::Record(r) => Ok(r),
            Value::Raw(_) => Err(MsError(format!("keyword {name} is not a record"))),
        }
    }

    pub fn remove(&mut self, name: &str) -> Result<()> {
        let i = self
            .field(name)
            .ok_or_else(|| MsError(format!("keyword {name} does not exist")))?;
        self.desc.fields.remove(i);
        self.values.remove(i);
        Ok(())
    }
}

/// A keyword value to define.
#[derive(Clone, Debug)]
pub enum KeywordValue {
    /// A scalar of a numeric or Bool type code, native-endian bytes
    /// (Bool: one byte, 0 or 1).
    Scalar(i32, Vec<u8>),
    String(String),
    /// An array of a scalar type code: shape in casacore (Fortran) order,
    /// native-endian values in Fortran order (Bool: one byte each).
    Array(i32, Vec<i64>, Vec<u8>),
    StringArray(Vec<i64>, Vec<String>),
    /// An empty sub-record.
    Record,
}

impl KeywordValue {
    /// The field type, the shape for the description and the canonical
    /// (big-endian) value bytes.
    fn encode(&self) -> Result<(i32, Option<Vec<i64>>, Value)> {
        Ok(match self {
            KeywordValue::Scalar(code, bytes) => {
                let size = tp::scalar_size(*code);
                if size == 0 || bytes.len() != size {
                    return Err(MsError(format!(
                        "keyword scalar of type {code} needs {size} bytes"
                    )));
                }
                (*code, None, Value::Raw(to_canonical(*code, bytes)))
            }
            KeywordValue::String(s) => {
                let mut w = Writer::new(true);
                w.string(s);
                (tp::STRING, None, Value::Raw(w.buf))
            }
            KeywordValue::Array(code, shape, bytes) => {
                let array = tp::array_of(*code)
                    .filter(|&a| a != tp::ARRAY_STRING)
                    .ok_or_else(|| MsError(format!("no array type for {code}")))?;
                let n: usize = shape.iter().map(|&s| s.max(0) as usize).product();
                let size = tp::scalar_size(*code);
                if bytes.len() != n * size {
                    return Err(MsError("keyword array size mismatches its shape".into()));
                }
                let mut w = Writer::new(true);
                w.putstart(tp::array_object_name(array), 3);
                w.u32(shape.len() as u32);
                for &s in shape {
                    w.u32(s as u32);
                }
                w.u32(n as u32);
                if *code == tp::BOOL {
                    w.bytes(&pack_bits(bytes));
                } else {
                    w.bytes(&to_canonical(*code, bytes));
                }
                w.putend();
                // Nested object: drop the magic value of the top level.
                (array, Some(vec![-1]), Value::Raw(w.buf[4..].to_vec()))
            }
            KeywordValue::StringArray(shape, strings) => {
                let n: usize = shape.iter().map(|&s| s.max(0) as usize).product();
                if strings.len() != n {
                    return Err(MsError("keyword array size mismatches its shape".into()));
                }
                let mut w = Writer::new(true);
                w.putstart("Array<String>", 3);
                w.u32(shape.len() as u32);
                for &s in shape {
                    w.u32(s as u32);
                }
                w.u32(n as u32);
                for s in strings {
                    w.string(s);
                }
                w.putend();
                (
                    tp::ARRAY_STRING,
                    Some(vec![-1]),
                    Value::Raw(w.buf[4..].to_vec()),
                )
            }
            KeywordValue::Record => (tp::RECORD, None, Value::Record(Box::default())),
        })
    }
}

/// Native-endian values to canonical big-endian (complex as two floats).
fn to_canonical(code: i32, bytes: &[u8]) -> Vec<u8> {
    let unit = match code {
        tp::COMPLEX => 4,
        tp::DCOMPLEX => 8,
        c => tp::scalar_size(c),
    };
    if unit <= 1 || cfg!(target_endian = "big") {
        return bytes.to_vec();
    }
    let mut out = bytes.to_vec();
    for chunk in out.chunks_exact_mut(unit) {
        chunk.reverse();
    }
    out
}

/// Pack one-byte booleans into bits, least significant first.
pub fn pack_bits(values: &[u8]) -> Vec<u8> {
    let mut out = vec![0u8; values.len().div_ceil(8)];
    for (i, &v) in values.iter().enumerate() {
        if v != 0 {
            out[i / 8] |= 1 << (i % 8);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nested_objects_patch_their_lengths() {
        let mut w = Writer::new(true);
        w.putstart("Outer", 2);
        w.u32(5);
        w.iposition(&[3, -1]);
        w.u32(9);
        w.putend();
        let mut c = Cursor::new(&w.buf, true);
        c.magic().unwrap();
        let outer = c.start_expect("Outer").unwrap();
        assert_eq!(outer.version, 2);
        assert_eq!(c.u32().unwrap(), 5);
        assert_eq!(c.iposition().unwrap(), vec![3, -1]);
        assert_eq!(c.u32().unwrap(), 9);
        c.end(&outer);
        assert_eq!(c.pos, w.buf.len());
        assert_eq!(outer.length, w.buf.len() - 4);
    }

    #[test]
    fn little_endian_blocks_and_maps_round_trip() {
        let mut w = Writer::new(false);
        w.putstart("SSMIndex", 1);
        w.int_map(&[(8, 4088), (100, 12)]);
        w.block_u32(&[31, 63]);
        w.block_u64(&[7]);
        w.putend();
        let mut c = Cursor::new(&w.buf, false);
        c.magic().unwrap();
        let o = c.start_expect("SSMIndex").unwrap();
        assert_eq!(read_int_map(&mut c).unwrap(), vec![(8, 4088), (100, 12)]);
        assert_eq!(c.block_u32().unwrap(), vec![31, 63]);
        assert_eq!(c.block_u64().unwrap(), vec![7]);
        c.end(&o);
        assert_eq!(c.pos, w.buf.len());
    }

    fn record_bytes(r: &Record) -> Vec<u8> {
        let mut w = Writer::new(true);
        w.putstart("Holder", 1);
        r.write(&mut w);
        w.putend();
        w.buf
    }

    fn reparse(bytes: &[u8]) -> Record {
        let mut c = Cursor::new(bytes, true);
        c.magic().unwrap();
        c.start_expect("Holder").unwrap();
        Record::read(&mut c).unwrap()
    }

    #[test]
    fn records_with_every_kind_of_field_round_trip() {
        let mut r = Record::default();
        r.define(
            "D",
            KeywordValue::Scalar(tp::DOUBLE, 1.5f64.to_ne_bytes().to_vec()),
        )
        .unwrap();
        r.define(
            "I",
            KeywordValue::Scalar(tp::INT, 7i32.to_ne_bytes().to_vec()),
        )
        .unwrap();
        r.define("B", KeywordValue::Scalar(tp::BOOL, vec![1]))
            .unwrap();
        r.define("S", KeywordValue::String("Jy".into())).unwrap();
        let values: Vec<u8> = [1.0f64, 2.0, 3.0]
            .iter()
            .flat_map(|v| v.to_ne_bytes())
            .collect();
        r.define("A", KeywordValue::Array(tp::DOUBLE, vec![3], values))
            .unwrap();
        r.define(
            "SA",
            KeywordValue::StringArray(vec![2], vec!["m".into(), "s".into()]),
        )
        .unwrap();
        r.define("BA", KeywordValue::Array(tp::BOOL, vec![9], vec![1; 9]))
            .unwrap();
        let sub = r.subrecord_mut("SUB").unwrap();
        sub.define("type", KeywordValue::String("epoch".into()))
            .unwrap();
        let bytes = record_bytes(&r);
        let back = reparse(&bytes);
        assert_eq!(back, r);
        assert_eq!(record_bytes(&back), bytes);
        // Replacing a field keeps its place.
        let mut r2 = back.clone();
        r2.define(
            "I",
            KeywordValue::Scalar(tp::INT, 8i32.to_ne_bytes().to_vec()),
        )
        .unwrap();
        assert_eq!(r2.field("I"), Some(1));
        r2.remove("S").unwrap();
        assert_eq!(r2.desc.fields.len(), 7);
        assert!(r2.remove("S").is_err());
    }

    #[test]
    fn fixed_subrecords_store_data_without_an_object() {
        // A sub-record whose description has fields is written inline.
        let mut inner = Record::default();
        inner
            .define(
                "x",
                KeywordValue::Scalar(tp::INT, 3i32.to_ne_bytes().to_vec()),
            )
            .unwrap();
        let mut r = Record {
            desc: RecordDesc {
                fields: vec![FieldDesc {
                    name: "fixed".into(),
                    dtype: tp::RECORD,
                    sub: Some(inner.desc.clone()),
                    shape: None,
                    table_desc: None,
                    comment: String::new(),
                }],
            },
            record_type: 0,
            values: vec![Value::Record(Box::new(Record {
                record_type: 0,
                ..inner
            }))],
        };
        let bytes = record_bytes(&r);
        assert_eq!(record_bytes(&reparse(&bytes)), bytes);
        r.record_type = 1;
        assert_ne!(record_bytes(&r), bytes);
    }

    #[test]
    fn bits_pack_least_significant_first() {
        assert_eq!(pack_bits(&[1, 0, 1, 0, 0, 0, 0, 0, 1]), vec![0b101, 1]);
    }
}
