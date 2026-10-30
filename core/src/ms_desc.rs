//! The `table.dat` model of the table writer (research/e3-table-writer.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Parses and serialises the whole of `table.dat` as casacore 3.8 writes it
//! (`BaseTable::writeStart/writeEnd`, `TableDesc::putFile`,
//! `BaseColumnDesc::putFile`, `ColumnSet::putFile`, `PlainColumn::putFile`):
//! the Table object (version 2, or 3 beyond 2^31 rows), the endian flag,
//! the table description with its keyword records, the column descriptions,
//! the column set with the data-manager list, the column bindings and the
//! per-manager blobs. `serialise(parse(x)) == x` for the tables casacore
//! writes; older layouts (Table version 1, TableDesc version 1, ColumnSet
//! version 1) are refused.

use crate::aipsio::{Record, Writer};
use crate::ms::{Cursor, MsError, Result};

fn err<T>(message: impl Into<String>) -> Result<T> {
    Err(MsError(message.into()))
}

/// One column description (`ColumnDesc` with its `BaseColumnDesc`).
#[derive(Clone, Debug, PartialEq)]
pub struct ColDesc {
    /// `ScalarColumnDesc<double>`, `ArrayColumnDesc<Complex>`, ...
    pub class: String,
    pub name: String,
    pub comment: String,
    pub dm_type: String,
    pub dm_group: String,
    pub dtype: i32,
    pub option: i32,
    pub ndim: i32,
    /// The shape of an array column (empty when not fixed); None for scalars.
    pub shape: Option<Vec<i64>>,
    pub max_length: u32,
    pub keywords: Record,
    /// The derived part after its version: the default value of a scalar
    /// column (canonical bytes), the unused default switch of an array.
    pub derived: Vec<u8>,
}

impl ColDesc {
    pub fn is_array(&self) -> bool {
        self.shape.is_some()
    }
}

/// A column binding in the column set (`PlainColumn` and its data part).
#[derive(Clone, Debug, PartialEq)]
pub struct ColBinding {
    pub original_name: String,
    pub seq: u32,
    /// For array columns: the shape defined for the whole column, if any.
    pub shape: Option<Option<Vec<i64>>>,
}

/// The parsed `table.dat`.
#[derive(Clone, Debug, PartialEq)]
pub struct TableDat {
    pub nrows: u64,
    pub little_endian: bool,
    pub desc_name: String,
    pub desc_version: String,
    pub desc_comment: String,
    pub keywords: Record,
    pub private_keywords: Record,
    pub columns: Vec<ColDesc>,
    /// ColumnSet version as written (-3 or -2).
    pub set_version: i32,
    /// StorageOption (option, block size) of a version -3 column set.
    pub storage: (i32, i32),
    pub seq_count: u32,
    /// (data-manager type, sequence number), in table.dat order.
    pub managers: Vec<(String, u32)>,
    pub bindings: Vec<ColBinding>,
    pub blobs: Vec<Vec<u8>>,
}

impl TableDat {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        let mut c = Cursor::new(bytes, true);
        c.magic()?;
        let table = c.start_expect("Table")?;
        let nrows = match table.version {
            2 => u64::from(c.u32()?),
            3 => c.u64()?,
            v => {
                return err(format!(
                    "table.dat version {v} is not supported for writing"
                ));
            }
        };
        let little_endian = c.u32()? != 0;
        let kind = c.string()?;
        if kind != "PlainTable" {
            return err(format!("table type {kind} is not supported"));
        }
        let desc = c.start_expect("TableDesc")?;
        if desc.version != 2 {
            return err(format!(
                "TableDesc version {} is not supported",
                desc.version
            ));
        }
        let desc_name = c.string()?;
        let desc_version = c.string()?;
        let desc_comment = c.string()?;
        let keywords = Record::read(&mut c)?;
        let private_keywords = Record::read(&mut c)?;
        let ncol = c.u32()? as usize;
        let mut columns = Vec::with_capacity(ncol);
        for _ in 0..ncol {
            columns.push(read_coldesc(&mut c)?);
        }
        c.end(&desc);
        let set_version = c.i32()?;
        let (set_nrows, storage) = match set_version {
            -3 => {
                let n = c.u64()?;
                (n, (c.i32()?, c.i32()?))
            }
            -2 => (u64::from(c.u32()?), (0, 0)),
            v => return err(format!("ColumnSet version {v} is not supported")),
        };
        if set_nrows != nrows {
            return err("ColumnSet row count mismatches table.dat");
        }
        let seq_count = c.u32()?;
        let n = c.u32()? as usize;
        let mut managers = Vec::with_capacity(n);
        for _ in 0..n {
            let kind = c.string()?;
            managers.push((kind, c.u32()?));
        }
        let mut bindings = Vec::with_capacity(ncol);
        for col in &columns {
            if c.u32()? != 2 {
                return err("PlainColumn version is not 2");
            }
            let original_name = c.string()?;
            if c.u32()? != 1 {
                return err("column data version is not 1");
            }
            let seq = c.u32()?;
            let shape = if col.is_array() {
                Some(if c.bool()? {
                    Some(c.iposition()?)
                } else {
                    None
                })
            } else {
                None
            };
            bindings.push(ColBinding {
                original_name,
                seq,
                shape,
            });
        }
        let mut blobs = Vec::with_capacity(n);
        for _ in 0..n {
            let len = c.u32()? as usize;
            blobs.push(c.take(len)?.to_vec());
        }
        c.end(&table);
        if c.pos != bytes.len() {
            return err("trailing bytes after the Table object");
        }
        Ok(TableDat {
            nrows,
            little_endian,
            desc_name,
            desc_version,
            desc_comment,
            keywords,
            private_keywords,
            columns,
            set_version,
            storage,
            seq_count,
            managers,
            bindings,
            blobs,
        })
    }

    /// Serialise as `PlainTable::putFile` does with `always`.
    pub fn serialise(&self) -> Vec<u8> {
        let mut w = Writer::new(true);
        let wide = self.nrows > i32::MAX as u64;
        if wide {
            w.putstart("Table", 3);
            w.u64(self.nrows);
        } else {
            w.putstart("Table", 2);
            w.u32(self.nrows as u32);
        }
        w.u32(u32::from(self.little_endian));
        w.string("PlainTable");
        w.putstart("TableDesc", 2);
        w.string(&self.desc_name);
        w.string(&self.desc_version);
        w.string(&self.desc_comment);
        self.keywords.write(&mut w);
        self.private_keywords.write(&mut w);
        w.u32(self.columns.len() as u32);
        for col in &self.columns {
            write_coldesc(&mut w, col);
        }
        w.putend();
        if self.set_version == -3 || wide {
            w.i32(-3);
            w.u64(self.nrows);
            w.i32(self.storage.0);
            w.i32(self.storage.1);
        } else {
            w.i32(-2);
            w.u32(self.nrows as u32);
        }
        w.u32(self.seq_count);
        w.u32(self.managers.len() as u32);
        for (kind, seq) in &self.managers {
            w.string(kind);
            w.u32(*seq);
        }
        for b in &self.bindings {
            w.u32(2);
            w.string(&b.original_name);
            w.u32(1);
            w.u32(b.seq);
            if let Some(shape) = &b.shape {
                w.bool(shape.is_some());
                if let Some(shape) = shape {
                    w.iposition(shape);
                }
            }
        }
        for blob in &self.blobs {
            w.uchar_block(blob);
        }
        w.putend();
        w.buf
    }

    pub fn column(&self, name: &str) -> Result<usize> {
        self.columns
            .iter()
            .position(|c| c.name == name)
            .ok_or_else(|| MsError(format!("column {name} does not exist")))
    }
}

fn read_coldesc(c: &mut Cursor<'_>) -> Result<ColDesc> {
    if c.u32()? != 1 {
        return err("ColumnDesc version is not 1");
    }
    let class = c.string()?;
    if c.u32()? != 1 {
        return err("BaseColumnDesc version is not 1");
    }
    let name = c.string()?;
    let comment = c.string()?;
    let dm_type = c.string()?;
    let dm_group = c.string()?;
    let dtype = c.i32()?;
    let option = c.i32()?;
    let ndim = c.i32()?;
    let is_array = class.starts_with("ArrayColumnDesc");
    if !is_array && !class.starts_with("ScalarColumnDesc") {
        return err(format!("column class {class} of {name} is not supported"));
    }
    let shape = if is_array { Some(c.iposition()?) } else { None };
    let max_length = c.u32()?;
    let keywords = Record::read(c)?;
    if c.u32()? != 1 {
        return err("column description version is not 1");
    }
    let at = c.pos;
    if is_array {
        c.bool()?;
    } else {
        match dtype {
            11 => {
                c.string()?;
            }
            code => {
                let size = crate::aipsio::tp::scalar_size(code);
                if size == 0 {
                    return err(format!("column {name} has unsupported type {code}"));
                }
                c.take(size)?;
            }
        }
    }
    let derived = c.bytes[at..c.pos].to_vec();
    Ok(ColDesc {
        class,
        name,
        comment,
        dm_type,
        dm_group,
        dtype,
        option,
        ndim,
        shape,
        max_length,
        keywords,
        derived,
    })
}

fn write_coldesc(w: &mut Writer, col: &ColDesc) {
    w.u32(1);
    w.string(&col.class);
    w.u32(1);
    w.string(&col.name);
    w.string(&col.comment);
    w.string(&col.dm_type);
    w.string(&col.dm_group);
    w.i32(col.dtype);
    w.i32(col.option);
    w.i32(col.ndim);
    if let Some(shape) = &col.shape {
        w.iposition(shape);
    }
    w.u32(col.max_length);
    col.keywords.write(w);
    w.u32(1);
    w.bytes(&col.derived);
}

/// The class name casacore gives a column description of a type code.
pub fn column_class(dtype: i32, array: bool) -> Result<String> {
    // `ValType::getTypeStr`: eight characters; casacore adds no bracket.
    let t = match dtype {
        0 => "Bool    ",
        1 => "Char    ",
        2 => "uChar   ",
        3 => "Short   ",
        4 => "uShort  ",
        5 => "Int     ",
        6 => "uInt    ",
        7 => "float   ",
        8 => "double  ",
        9 => "Complex ",
        10 => "DComplex",
        11 => "String  ",
        29 => "Int64   ",
        other => return err(format!("no column class for type {other}")),
    };
    Ok(format!(
        "{}ColumnDesc<{t}",
        if array { "Array" } else { "Scalar" }
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::aipsio::{KeywordValue, tp};

    fn sample() -> TableDat {
        let mut kw = Record::default();
        kw.define(
            "MS_VERSION",
            KeywordValue::Scalar(tp::FLOAT, 2.0f32.to_ne_bytes().to_vec()),
        )
        .unwrap();
        TableDat {
            nrows: 3,
            little_endian: true,
            desc_name: String::new(),
            desc_version: String::new(),
            desc_comment: String::new(),
            keywords: kw,
            private_keywords: Record::default(),
            columns: vec![
                ColDesc {
                    class: column_class(8, false).unwrap(),
                    name: "TIME".into(),
                    comment: "c".into(),
                    dm_type: "StandardStMan".into(),
                    dm_group: String::new(),
                    dtype: 8,
                    option: 0,
                    ndim: 0,
                    shape: None,
                    max_length: 0,
                    keywords: Record::default(),
                    derived: 0f64.to_be_bytes().to_vec(),
                },
                ColDesc {
                    class: column_class(0, true).unwrap(),
                    name: "FLAG".into(),
                    comment: String::new(),
                    dm_type: "StandardStMan".into(),
                    dm_group: "G".into(),
                    dtype: 0,
                    option: 4,
                    ndim: 2,
                    shape: Some(vec![4, 8]),
                    max_length: 0,
                    keywords: Record::default(),
                    derived: vec![0],
                },
            ],
            set_version: -2,
            storage: (0, 0),
            seq_count: 1,
            managers: vec![("StandardStMan".into(), 0)],
            bindings: vec![
                ColBinding {
                    original_name: "TIME".into(),
                    seq: 0,
                    shape: None,
                },
                ColBinding {
                    original_name: "FLAG".into(),
                    seq: 0,
                    shape: Some(Some(vec![4, 8])),
                },
            ],
            blobs: vec![vec![1, 2, 3]],
        }
    }

    #[test]
    fn table_dat_round_trips() {
        let t = sample();
        let bytes = t.serialise();
        let back = TableDat::parse(&bytes).unwrap();
        assert_eq!(back, t);
        assert_eq!(back.serialise(), bytes);
        assert_eq!(back.column("FLAG").unwrap(), 1);
        assert!(back.column("DATA").is_err());
    }

    #[test]
    fn trailing_bytes_are_refused() {
        let mut bytes = sample().serialise();
        bytes.push(0);
        assert!(TableDat::parse(&bytes).is_err());
    }

    /// `serialise(parse(x)) == x` on a real table when `RANG_MS_FIXTURE`
    /// names one (all its subtables too); the checker covers all inputs.
    #[test]
    fn real_table_dat_round_trips_when_given() {
        let Ok(path) = std::env::var("RANG_MS_FIXTURE") else {
            return;
        };
        let root = std::path::Path::new(&path);
        let mut dirs = vec![root.to_path_buf()];
        for entry in std::fs::read_dir(root).unwrap() {
            let p = entry.unwrap().path();
            if p.join("table.dat").is_file() {
                dirs.push(p);
            }
        }
        for dir in dirs {
            let bytes = std::fs::read(dir.join("table.dat")).unwrap();
            let t = TableDat::parse(&bytes).unwrap();
            assert_eq!(t.serialise(), bytes, "{}", dir.display());
        }
    }
}
