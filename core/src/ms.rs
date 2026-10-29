//! Read-only reader for casacore tables (research/core-e-ms-reader.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Reads `table.dat` and the StandardStMan, IncrementalStMan,
//! TiledShapeStMan and TiledColumnStMan files of a casacore table as the
//! MeerKAT Measurement Sets in `outputs/` use them. The on-disk format was
//! read from the casacore 3.8.1 sources listed in the research file; nothing
//! is copied from casacore (LGPL-2.1-or-later). Scope: scalar, direct-array
//! and indirect-array columns of the numeric, boolean and string types,
//! returned as native bytes in casacore's Fortran cell order. Outside the
//! scope, refused with an error: IncrementalStMan arrays and strings, other
//! storage managers, MultiFile tables and big-endian hosts.

use std::collections::HashMap;
use std::fmt;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

const MAGIC: u32 = 0xbebe_bebe;
/// Buckets of StandardStMan and IncrementalStMan files start after a header.
const BUCKET_START: u64 = 512;
/// Tiles kept in memory during one column read (DATA tiles are 1 MiB here).
const TILE_CACHE: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MsError(pub String);

impl fmt::Display for MsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for MsError {}

impl From<std::io::Error> for MsError {
    fn from(e: std::io::Error) -> Self {
        MsError(format!("io: {e}"))
    }
}

pub type Result<T> = std::result::Result<T, MsError>;

fn err<T>(message: impl Into<String>) -> Result<T> {
    Err(MsError(message.into()))
}

/// casacore `DataType` codes (casa/Utilities/DataType.h) that a column can hold.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DataType {
    Bool,
    Char,
    UChar,
    Short,
    UShort,
    Int,
    UInt,
    Float,
    Double,
    Complex,
    DComplex,
    Str,
    Int64,
}

impl DataType {
    pub fn from_code(code: i32) -> Result<Self> {
        Ok(match code {
            0 => Self::Bool,
            1 => Self::Char,
            2 => Self::UChar,
            3 => Self::Short,
            4 => Self::UShort,
            5 => Self::Int,
            6 => Self::UInt,
            7 => Self::Float,
            8 => Self::Double,
            9 => Self::Complex,
            10 => Self::DComplex,
            11 => Self::Str,
            29 => Self::Int64,
            other => return err(format!("unsupported column data type code {other}")),
        })
    }

    pub fn code(self) -> i32 {
        match self {
            Self::Bool => 0,
            Self::Char => 1,
            Self::UChar => 2,
            Self::Short => 3,
            Self::UShort => 4,
            Self::Int => 5,
            Self::UInt => 6,
            Self::Float => 7,
            Self::Double => 8,
            Self::Complex => 9,
            Self::DComplex => 10,
            Self::Str => 11,
            Self::Int64 => 29,
        }
    }

    /// NumPy dtype name of the native representation; booleans are one byte.
    pub fn numpy(self) -> &'static str {
        match self {
            Self::Bool => "bool",
            Self::Char => "int8",
            Self::UChar => "uint8",
            Self::Short => "int16",
            Self::UShort => "uint16",
            Self::Int => "int32",
            Self::UInt => "uint32",
            Self::Float => "float32",
            Self::Double => "float64",
            Self::Complex => "complex64",
            Self::DComplex => "complex128",
            Self::Str => "str",
            Self::Int64 => "int64",
        }
    }

    /// Bytes of one value in the canonical (and native) format; 0 for
    /// booleans, which are bit packed on disk, and for strings.
    pub fn size(self) -> usize {
        match self {
            Self::Bool | Self::Str => 0,
            Self::Char | Self::UChar => 1,
            Self::Short | Self::UShort => 2,
            Self::Int | Self::UInt | Self::Float => 4,
            Self::Double | Self::Int64 | Self::Complex => 8,
            Self::DComplex => 16,
        }
    }

    /// Width of the units that are byte swapped (complex values are two floats).
    fn swap_unit(self) -> usize {
        match self {
            Self::Complex => 4,
            Self::DComplex => 8,
            other => other.size(),
        }
    }

    /// Native bytes per value as returned to the caller (booleans as one byte).
    pub fn native_size(self) -> usize {
        if self == Self::Bool { 1 } else { self.size() }
    }
}

/// A column description from `table.dat`, with its data manager binding.
#[derive(Clone, Debug)]
pub struct ColumnDesc {
    pub name: String,
    pub dtype: DataType,
    pub is_array: bool,
    /// `ColumnDesc::Option` bits: 1 Direct, 2 Undefined, 4 FixedShape.
    pub option: i32,
    pub ndim: i32,
    /// Fixed cell shape in casacore (Fortran) axis order, empty if not fixed.
    pub shape: Vec<i64>,
    pub max_length: u32,
    pub manager_type: String,
    pub manager_name: String,
    pub manager_seq: u32,
}

impl ColumnDesc {
    pub fn is_direct(&self) -> bool {
        self.option & 1 != 0
    }
}

/// One column read: native bytes of `nrows` cells of `shape` in Fortran
/// order, or `strings` for string columns.
#[derive(Clone, Debug, Default)]
pub struct ColumnData {
    pub dtype: Option<DataType>,
    pub shape: Vec<i64>,
    pub nrows: u64,
    pub bytes: Vec<u8>,
    pub strings: Vec<String>,
}

// ---------------------------------------------------------------------------
// AipsIO: the serialisation used by table.dat and the storage-manager headers.

struct Object {
    start: usize,
    length: usize,
    kind: String,
    version: u32,
}

struct Cursor<'a> {
    bytes: &'a [u8],
    pos: usize,
    big: bool,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8], big: bool) -> Self {
        Cursor { bytes, pos: 0, big }
    }

    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let out = self
            .bytes
            .get(self.pos..self.pos + n)
            .ok_or_else(|| MsError(format!("truncated AipsIO object at byte {}", self.pos)))?;
        self.pos += n;
        Ok(out)
    }

    fn u8(&mut self) -> Result<u8> {
        Ok(self.take(1)?[0])
    }

    fn bool(&mut self) -> Result<bool> {
        Ok(self.u8()? != 0)
    }

    fn u32(&mut self) -> Result<u32> {
        let b: [u8; 4] = self.take(4)?.try_into().unwrap();
        Ok(if self.big {
            u32::from_be_bytes(b)
        } else {
            u32::from_le_bytes(b)
        })
    }

    fn i32(&mut self) -> Result<i32> {
        Ok(self.u32()? as i32)
    }

    fn u64(&mut self) -> Result<u64> {
        let b: [u8; 8] = self.take(8)?.try_into().unwrap();
        Ok(if self.big {
            u64::from_be_bytes(b)
        } else {
            u64::from_le_bytes(b)
        })
    }

    fn i64(&mut self) -> Result<i64> {
        Ok(self.u64()? as i64)
    }

    fn string(&mut self) -> Result<String> {
        let n = self.u32()? as usize;
        Ok(String::from_utf8_lossy(self.take(n)?).into_owned())
    }

    fn magic(&mut self) -> Result<()> {
        if self.u32()? != MAGIC {
            return err("AipsIO magic value missing");
        }
        Ok(())
    }

    fn start(&mut self) -> Result<Object> {
        let start = self.pos;
        let length = self.u32()? as usize;
        let kind = self.string()?;
        let version = self.u32()?;
        Ok(Object {
            start,
            length,
            kind,
            version,
        })
    }

    fn start_expect(&mut self, kind: &str) -> Result<Object> {
        let object = self.start()?;
        if object.kind != kind {
            return err(format!(
                "expected AipsIO object {kind}, found {}",
                object.kind
            ));
        }
        Ok(object)
    }

    fn end(&mut self, object: &Object) {
        self.pos = object.start + object.length;
    }

    fn skip_object(&mut self) -> Result<()> {
        let object = self.start()?;
        self.end(&object);
        Ok(())
    }

    fn iposition(&mut self) -> Result<Vec<i64>> {
        let object = self.start_expect("IPosition")?;
        let n = self.u32()? as usize;
        let mut out = Vec::with_capacity(n);
        for _ in 0..n {
            out.push(match object.version {
                1 => i64::from(self.i32()?),
                2 => self.i64()?,
                v => return err(format!("IPosition version {v}")),
            });
        }
        self.end(&object);
        Ok(out)
    }

    fn block_u32(&mut self) -> Result<Vec<u32>> {
        let object = self.start_expect("Block")?;
        let n = self.u32()? as usize;
        let out = (0..n).map(|_| self.u32()).collect::<Result<Vec<_>>>()?;
        self.end(&object);
        Ok(out)
    }

    fn block_u64(&mut self) -> Result<Vec<u64>> {
        let object = self.start_expect("Block")?;
        let n = self.u32()? as usize;
        let out = (0..n).map(|_| self.u64()).collect::<Result<Vec<_>>>()?;
        self.end(&object);
        Ok(out)
    }
}

// ---------------------------------------------------------------------------
// Byte helpers for the data files.

/// Read `n` bytes at `offset` of `file`.
fn read_at(file: &mut File, offset: u64, n: usize) -> Result<Vec<u8>> {
    let mut out = vec![0u8; n];
    file.seek(SeekFrom::Start(offset))?;
    file.read_exact(&mut out)
        .map_err(|e| MsError(format!("read of {n} bytes at {offset} failed: {e}")))?;
    Ok(out)
}

fn read_u32(bytes: &[u8], at: usize, big: bool) -> Result<u32> {
    let b: [u8; 4] = bytes
        .get(at..at + 4)
        .ok_or_else(|| MsError("truncated bucket".into()))?
        .try_into()
        .unwrap();
    Ok(if big {
        u32::from_be_bytes(b)
    } else {
        u32::from_le_bytes(b)
    })
}

fn read_i32(bytes: &[u8], at: usize, big: bool) -> Result<i32> {
    Ok(read_u32(bytes, at, big)? as i32)
}

fn read_u64(bytes: &[u8], at: usize, big: bool) -> Result<u64> {
    let b: [u8; 8] = bytes
        .get(at..at + 8)
        .ok_or_else(|| MsError("truncated bucket".into()))?
        .try_into()
        .unwrap();
    Ok(if big {
        u64::from_be_bytes(b)
    } else {
        u64::from_le_bytes(b)
    })
}

/// Append `count` values of `dtype` from the file bytes, swapping to the
/// host order when the file is big-endian.
fn convert_into(
    out: &mut Vec<u8>,
    src: &[u8],
    dtype: DataType,
    count: usize,
    big: bool,
) -> Result<()> {
    let size = dtype.size();
    let bytes = src
        .get(..count * size)
        .ok_or_else(|| MsError("truncated value run".into()))?;
    if big == cfg!(target_endian = "big") || size <= 1 {
        out.extend_from_slice(bytes);
    } else {
        let unit = dtype.swap_unit();
        for chunk in bytes.chunks_exact(unit) {
            out.extend(chunk.iter().rev());
        }
    }
    Ok(())
}

/// Append `count` booleans stored as bits from bit `bit0` of `src`, least
/// significant bit first.
fn bits_into(out: &mut Vec<u8>, src: &[u8], bit0: usize, count: usize) -> Result<()> {
    if count == 0 {
        return Ok(());
    }
    if bit0 + count > src.len() * 8 {
        return err("truncated boolean bits");
    }
    let (first, last) = (bit0 / 8, (bit0 + count - 1) / 8);
    let skip = bit0 % 8;
    let mut expanded = Vec::with_capacity((last - first + 1) * 8);
    for &byte in &src[first..=last] {
        expanded.extend_from_slice(&[
            byte & 1,
            (byte >> 1) & 1,
            (byte >> 2) & 1,
            (byte >> 3) & 1,
            (byte >> 4) & 1,
            (byte >> 5) & 1,
            (byte >> 6) & 1,
            (byte >> 7) & 1,
        ]);
    }
    out.extend_from_slice(&expanded[skip..skip + count]);
    Ok(())
}

fn product(shape: &[i64]) -> usize {
    shape.iter().map(|&s| s.max(0) as usize).product()
}

// ---------------------------------------------------------------------------
// StandardStMan.

struct SsmIndex {
    last_row: Vec<u64>,
    bucket: Vec<u32>,
}

impl SsmIndex {
    /// The index entry and first row of the bucket holding `row`.
    fn find(&self, row: u64) -> Result<(usize, u64)> {
        let i = self.last_row.partition_point(|&last| last < row);
        if i >= self.last_row.len() {
            return err(format!("row {row} beyond the StandardStMan index"));
        }
        let first = if i == 0 { 0 } else { self.last_row[i - 1] + 1 };
        Ok((i, first))
    }
}

enum SsmKind {
    Scalar,
    FixedString(usize),
    IndirectString,
    Direct(usize),
    Indirect,
}

struct SsmColumn {
    dtype: DataType,
    kind: SsmKind,
    /// Bytes per row in the bucket (bits for booleans).
    external_bits: usize,
}

struct Ssm {
    data_file: PathBuf,
    big: bool,
    bucket_size: usize,
    nr_buckets: u32,
    col_offset: Vec<u32>,
    col_index: Vec<u32>,
    indices: Vec<SsmIndex>,
    columns: Vec<SsmColumn>,
}

impl Ssm {
    fn open(table: &TableFiles, seq: u32, blob: &[u8], columns: &[&ColumnDesc]) -> Result<Self> {
        let mut c = Cursor::new(blob, true);
        c.magic()?;
        let object = c.start_expect("SSM")?;
        let _name = c.string()?;
        let col_offset = c.block_u32()?;
        let col_index = c.block_u32()?;
        c.end(&object);
        let data_file = table.file(seq, "");
        let header = read_at(&mut File::open(&data_file)?, 0, BUCKET_START as usize)?;
        let mut h = Cursor::new(&header, !table.little);
        h.magic()?;
        let object = h.start_expect("StandardStMan")?;
        let big = if object.version >= 3 { h.bool()? } else { true };
        if big == table.little {
            return err("StandardStMan endian flag mismatches the table");
        }
        let bucket_size = h.u32()? as usize;
        let nr_buckets = h.u32()?;
        let _pers_cache = h.u32()?;
        let _free = h.u32()?;
        let _first_free = h.i32()?;
        let nr_idx_buckets = h.u32()?;
        let first_idx_bucket = h.i32()?;
        let idx_bucket_offset = if object.version >= 2 {
            h.u32()? as usize
        } else {
            0
        };
        let _last_string_bucket = h.i32()?;
        let index_length = h.u32()? as usize;
        let nr_indices = h.u32()? as usize;
        // The index lives in a chain of buckets; each starts with two copies
        // of its own number (canonical format).
        let mut file = File::open(&data_file)?;
        let mut index_bytes = Vec::with_capacity(index_length);
        let mut bucket = first_idx_bucket;
        let mut left = index_length;
        for _ in 0..nr_idx_buckets {
            if bucket < 0 {
                return err("StandardStMan index bucket chain ends early");
            }
            let bytes = read_at(
                &mut file,
                BUCKET_START + bucket as u64 * bucket_size as u64,
                bucket_size,
            )?;
            let next = read_i32(&bytes, 4, true)?;
            let take = if idx_bucket_offset > 0 {
                &bytes[idx_bucket_offset..idx_bucket_offset + left]
            } else if left < bucket_size - 8 {
                &bytes[8..8 + left]
            } else {
                &bytes[8..bucket_size]
            };
            index_bytes.extend_from_slice(take);
            left = left.saturating_sub(bucket_size - 8);
            bucket = next;
        }
        let mut ic = Cursor::new(&index_bytes, big);
        let mut indices = Vec::with_capacity(nr_indices);
        for _ in 0..nr_indices {
            ic.magic()?;
            let object = ic.start_expect("SSMIndex")?;
            let n_used = ic.u32()? as usize;
            let _rows_per_bucket = ic.u32()?;
            let _n_columns = ic.u32()?;
            ic.skip_object()?; // free-space map
            let mut last_row = if object.version == 1 {
                ic.block_u32()?
                    .into_iter()
                    .map(u64::from)
                    .collect::<Vec<_>>()
            } else {
                ic.block_u64()?
            };
            let mut bucket = ic.block_u32()?;
            last_row.truncate(n_used);
            bucket.truncate(n_used);
            indices.push(SsmIndex { last_row, bucket });
            ic.end(&object);
        }
        let mut cols = Vec::with_capacity(columns.len());
        for desc in columns {
            let (kind, external_bits) = match (desc.dtype, desc.is_array, desc.is_direct()) {
                (DataType::Str, false, _) if desc.max_length > 0 => (
                    SsmKind::FixedString(desc.max_length as usize),
                    8 * desc.max_length as usize,
                ),
                (DataType::Str, false, _) => (SsmKind::IndirectString, 8 * 12),
                (DataType::Bool, false, _) => (SsmKind::Scalar, 1),
                (dt, false, _) => (SsmKind::Scalar, 8 * dt.size()),
                (DataType::Str, true, true) => (SsmKind::Direct(product(&desc.shape)), 8 * 12),
                (DataType::Bool, true, true) => {
                    (SsmKind::Direct(product(&desc.shape)), product(&desc.shape))
                }
                (dt, true, true) => (
                    SsmKind::Direct(product(&desc.shape)),
                    8 * dt.size() * product(&desc.shape),
                ),
                (_, true, false) => (SsmKind::Indirect, 64),
            };
            cols.push(SsmColumn {
                dtype: desc.dtype,
                kind,
                external_bits,
            });
        }
        if col_offset.len() != cols.len() || col_index.len() != cols.len() {
            return err("StandardStMan column count mismatches the table");
        }
        Ok(Ssm {
            data_file,
            big,
            bucket_size,
            nr_buckets,
            col_offset,
            col_index,
            indices,
            columns: cols,
        })
    }

    fn bucket(&self, file: &mut File, n: u32) -> Result<Vec<u8>> {
        if n >= self.nr_buckets {
            return err(format!("StandardStMan bucket {n} beyond the file"));
        }
        read_at(
            file,
            BUCKET_START + u64::from(n) * self.bucket_size as u64,
            self.bucket_size,
        )
    }

    /// The raw per-row slots of column `col` for rows `start..start+count`,
    /// as (bucket bytes, byte offset of the slot run, first row of the run,
    /// number of rows) chunks, visited in row order.
    fn visit_rows(
        &self,
        file: &mut File,
        col: usize,
        start: u64,
        count: u64,
        mut f: impl FnMut(&[u8], usize, usize, usize) -> Result<()>,
    ) -> Result<()> {
        let index = &self.indices[self.col_index[col] as usize];
        let offset = self.col_offset[col] as usize;
        let bits = self.columns[col].external_bits;
        let mut row = start;
        while row < start + count {
            let (entry, first) = index.find(row)?;
            let last = index.last_row[entry].min(start + count - 1);
            let bytes = self.bucket(file, index.bucket[entry])?;
            let in_bucket = (row - first) as usize;
            f(&bytes, offset, in_bucket, (last - row + 1) as usize).map_err(|e| {
                MsError(format!(
                    "{e} (bits per row {bits}, bucket {})",
                    index.bucket[entry]
                ))
            })?;
            row = last + 1;
        }
        Ok(())
    }

    fn read(&self, desc: &ColumnDesc, col: usize, start: u64, count: u64) -> Result<ColumnData> {
        let mut file = File::open(&self.data_file)?;
        let column = &self.columns[col];
        let big = self.big;
        let mut data = ColumnData {
            dtype: Some(column.dtype),
            nrows: count,
            ..Default::default()
        };
        match &column.kind {
            SsmKind::Scalar => {
                let dtype = column.dtype;
                self.visit_rows(&mut file, col, start, count, |bucket, offset, first, n| {
                    if dtype == DataType::Bool {
                        bits_into(&mut data.bytes, &bucket[offset..], first, n)
                    } else {
                        convert_into(
                            &mut data.bytes,
                            &bucket[offset + first * dtype.size()..],
                            dtype,
                            n,
                            big,
                        )
                    }
                })?;
            }
            SsmKind::FixedString(len) => {
                let len = *len;
                self.visit_rows(&mut file, col, start, count, |bucket, offset, first, n| {
                    for i in 0..n {
                        let slot =
                            &bucket[offset + (first + i) * len..offset + (first + i + 1) * len];
                        let end = slot.iter().position(|&b| b == 0).unwrap_or(len);
                        data.strings
                            .push(String::from_utf8_lossy(&slot[..end]).into_owned());
                    }
                    Ok(())
                })?;
            }
            SsmKind::IndirectString => {
                let mut handler = StringBuckets::new(self)?;
                self.visit_rows(&mut file, col, start, count, |bucket, offset, first, n| {
                    for i in 0..n {
                        let at = offset + (first + i) * 12;
                        let (b, o, l) = (
                            read_i32(bucket, at, big)?,
                            read_i32(bucket, at + 4, big)?,
                            read_i32(bucket, at + 8, big)?,
                        );
                        let text = if l <= 8 {
                            bucket[at..at + l.max(0) as usize].to_vec()
                        } else {
                            handler.chars(b, o as usize, l as usize)?
                        };
                        data.strings
                            .push(String::from_utf8_lossy(&text).into_owned());
                    }
                    Ok(())
                })?;
            }
            SsmKind::Direct(nelem) => {
                let (nelem, dtype) = (*nelem, column.dtype);
                data.shape = desc.shape.clone();
                let mut handler = StringBuckets::new(self)?;
                self.visit_rows(
                    &mut file,
                    col,
                    start,
                    count,
                    |bucket, offset, first, n| match dtype {
                        DataType::Bool => {
                            bits_into(&mut data.bytes, &bucket[offset..], first * nelem, n * nelem)
                        }
                        DataType::Str => {
                            for i in 0..n {
                                let at = offset + (first + i) * 12;
                                let (b, o, l) = (
                                    read_i32(bucket, at, big)?,
                                    read_i32(bucket, at + 4, big)?,
                                    read_i32(bucket, at + 8, big)?,
                                );
                                data.strings
                                    .extend(handler.strings(b, o as usize, l, nelem)?);
                            }
                            Ok(())
                        }
                        dt => convert_into(
                            &mut data.bytes,
                            &bucket[offset + first * nelem * dt.size()..],
                            dt,
                            n * nelem,
                            big,
                        ),
                    },
                )?;
            }
            SsmKind::Indirect => {
                let mut offsets = Vec::with_capacity(count as usize);
                self.visit_rows(&mut file, col, start, count, |bucket, offset, first, n| {
                    for i in 0..n {
                        offsets.push(read_u64(bucket, offset + (first + i) * 8, big)?);
                    }
                    Ok(())
                })?;
                let mut ind = IndirectFile::open(&self.data_file, big)?;
                for (i, &offset) in offsets.iter().enumerate() {
                    if offset == 0 {
                        return err(format!(
                            "row {} of {} has no array",
                            start + i as u64,
                            desc.name
                        ));
                    }
                    let shape = ind.shape(offset)?;
                    if i == 0 {
                        data.shape = shape.clone();
                    } else if shape != data.shape {
                        return err(format!(
                            "rows of {} differ in shape; read fewer rows at once",
                            desc.name
                        ));
                    }
                    ind.values(column.dtype, &shape, &mut data)?;
                }
            }
        }
        Ok(data)
    }
}

/// The string buckets of a StandardStMan file: 16 bytes of canonical
/// (big-endian) bookkeeping (a copy of the bucket number, the used length,
/// the deleted count, the next bucket), then characters. A string that does
/// not fit continues in the next bucket of the chain.
struct StringBuckets<'a> {
    ssm: &'a Ssm,
    file: File,
    current: i32,
    bytes: Vec<u8>,
    offset: usize,
}

impl<'a> StringBuckets<'a> {
    fn new(ssm: &'a Ssm) -> Result<Self> {
        Ok(StringBuckets {
            ssm,
            file: File::open(&ssm.data_file)?,
            current: -1,
            bytes: Vec::new(),
            offset: 0,
        })
    }

    fn seek(&mut self, bucket: i32, offset: usize) -> Result<()> {
        if bucket != self.current {
            if bucket < 0 {
                return err("string bucket chain ends early");
            }
            self.bytes = self.ssm.bucket(&mut self.file, bucket as u32)?;
            self.current = bucket;
        }
        self.offset = offset;
        Ok(())
    }

    /// The next `length` characters, following the chain as casacore does.
    fn read(&mut self, length: usize) -> Result<Vec<u8>> {
        let mut out = Vec::with_capacity(length);
        let mut guard = 0;
        while out.len() < length {
            let used = read_i32(&self.bytes, 4, true)?.max(0) as usize;
            let take = (length - out.len()).min(used.saturating_sub(self.offset));
            let at = 16 + self.offset;
            out.extend_from_slice(
                self.bytes
                    .get(at..at + take)
                    .ok_or_else(|| MsError("string bucket overrun".into()))?,
            );
            self.offset += take;
            if out.len() < length {
                let next = read_i32(&self.bytes, 12, true)?;
                guard += 1;
                if guard > self.ssm.nr_buckets {
                    return err("string bucket chain loops");
                }
                self.seek(next, 0)?;
            }
        }
        Ok(out)
    }

    /// `length` characters at (`bucket`, `offset`): one variable-length string.
    fn chars(&mut self, bucket: i32, offset: usize, length: usize) -> Result<Vec<u8>> {
        self.seek(bucket, offset)?;
        self.read(length)
    }

    /// `nelem` strings of a direct array at (`bucket`, `offset`): each a
    /// canonical int length and its characters; an unset array is empty.
    fn strings(
        &mut self,
        bucket: i32,
        offset: usize,
        length: i32,
        nelem: usize,
    ) -> Result<Vec<String>> {
        if length <= 0 {
            return Ok(vec![String::new(); nelem]);
        }
        self.seek(bucket, offset)?;
        let mut out = Vec::with_capacity(nelem);
        for _ in 0..nelem {
            let len = self.read(4)?;
            let len = i32::from_be_bytes(len.try_into().unwrap()).max(0) as usize;
            let text = self.read(len)?;
            out.push(String::from_utf8_lossy(&text).into_owned());
        }
        Ok(out)
    }
}

/// The `table.fNi` file of indirect arrays (StManArrayFile).
struct IndirectFile {
    file: File,
    big: bool,
    version: u32,
    /// Byte offset of the values of the last `shape` call.
    data_at: u64,
}

impl IndirectFile {
    fn open(data_file: &Path, big: bool) -> Result<Self> {
        let mut name = data_file.as_os_str().to_owned();
        name.push("i");
        let mut file = File::open(PathBuf::from(name))?;
        let head = read_at(&mut file, 0, 4)?;
        let version = read_u32(&head, 0, big)?;
        Ok(IndirectFile {
            file,
            big,
            version,
            data_at: 0,
        })
    }

    fn shape(&mut self, offset: u64) -> Result<Vec<i64>> {
        let head = read_at(&mut self.file, offset, 8)?;
        let mut at = 0;
        if self.version > 0 {
            at += 4; // reference count
        }
        let ndim = read_u32(&head, at, self.big)? as usize;
        at += 4;
        let dims = read_at(&mut self.file, offset + at as u64, 4 * ndim)?;
        let shape = (0..ndim)
            .map(|i| read_i32(&dims, 4 * i, self.big).map(i64::from))
            .collect::<Result<Vec<_>>>()?;
        self.data_at = offset + (at + 4 * ndim) as u64;
        Ok(shape)
    }

    fn values(&mut self, dtype: DataType, shape: &[i64], data: &mut ColumnData) -> Result<()> {
        let n = product(shape);
        match dtype {
            DataType::Bool => {
                let bytes = read_at(&mut self.file, self.data_at, n.div_ceil(8))?;
                bits_into(&mut data.bytes, &bytes, 0, n)
            }
            DataType::Str => {
                let offsets = read_at(&mut self.file, self.data_at, 4 * n)?;
                for i in 0..n {
                    let at = u64::from(read_u32(&offsets, 4 * i, self.big)?);
                    if at == 0 {
                        data.strings.push(String::new());
                        continue;
                    }
                    let len = read_u32(&read_at(&mut self.file, at, 4)?, 0, self.big)? as usize;
                    let text = read_at(&mut self.file, at + 4, len)?;
                    data.strings
                        .push(String::from_utf8_lossy(&text).into_owned());
                }
                Ok(())
            }
            dt => {
                // Read straight into the output; swap in place if needed.
                let at = data.bytes.len();
                data.bytes.resize(at + n * dt.size(), 0);
                self.file.seek(SeekFrom::Start(self.data_at))?;
                self.file.read_exact(&mut data.bytes[at..]).map_err(|e| {
                    MsError(format!(
                        "indirect array read at {} failed: {e}",
                        self.data_at
                    ))
                })?;
                if self.big != cfg!(target_endian = "big") && dt.size() > 1 {
                    for unit in data.bytes[at..].chunks_exact_mut(dt.swap_unit()) {
                        unit.reverse();
                    }
                }
                Ok(())
            }
        }
    }
}

// ---------------------------------------------------------------------------
// IncrementalStMan (scalar columns only).

struct Ism {
    data_file: PathBuf,
    big: bool,
    bucket_size: usize,
    /// Start rows of the buckets, with the total row count last.
    rows: Vec<u64>,
    buckets: Vec<u32>,
    columns: Vec<(DataType, usize)>,
}

impl Ism {
    fn open(table: &TableFiles, seq: u32, blob: &[u8], columns: &[&ColumnDesc]) -> Result<Self> {
        let mut c = Cursor::new(blob, true);
        c.magic()?;
        let object = c.start_expect("ISM")?;
        let _name = c.string()?;
        c.end(&object);
        let data_file = table.file(seq, "");
        let mut file = File::open(&data_file)?;
        let header = read_at(&mut file, 0, BUCKET_START as usize)?;
        let mut h = Cursor::new(&header, !table.little);
        h.magic()?;
        let object = h.start_expect("IncrementalStMan")?;
        let big = if object.version >= 5 { h.bool()? } else { true };
        if big == table.little {
            return err("IncrementalStMan endian flag mismatches the table");
        }
        let bucket_size = h.u32()? as usize;
        let nbucket_init = h.u32()?;
        // The index object follows the initial buckets, as a top-level object.
        let index_at = BUCKET_START + u64::from(nbucket_init) * bucket_size as u64;
        let size = file.metadata()?.len();
        let index_bytes = read_at(&mut file, index_at, (size - index_at) as usize)?;
        let mut ic = Cursor::new(&index_bytes, big);
        ic.magic()?;
        let object = ic.start_expect("ISMIndex")?;
        let n_used = ic.u32()? as usize;
        let mut rows = if object.version > 1 {
            ic.block_u64()?
        } else {
            ic.block_u32()?.into_iter().map(u64::from).collect()
        };
        let mut buckets = ic.block_u32()?;
        rows.truncate(n_used + 1);
        buckets.truncate(n_used);
        let mut cols = Vec::with_capacity(columns.len());
        for desc in columns {
            if desc.is_array || desc.dtype == DataType::Str {
                return err(format!(
                    "IncrementalStMan array or string column {} is not supported",
                    desc.name
                ));
            }
            cols.push((desc.dtype, 1));
        }
        Ok(Ism {
            data_file,
            big,
            bucket_size,
            rows,
            buckets,
            columns: cols,
        })
    }

    fn read(&self, col: usize, start: u64, count: u64) -> Result<ColumnData> {
        let (dtype, nelem) = self.columns[col];
        let mut file = File::open(&self.data_file)?;
        let mut data = ColumnData {
            dtype: Some(dtype),
            nrows: count,
            ..Default::default()
        };
        let mut row = start;
        while row < start + count {
            let i = self.rows.partition_point(|&r| r <= row).saturating_sub(1);
            if i + 1 >= self.rows.len() {
                return err(format!("row {row} beyond the IncrementalStMan index"));
            }
            let (bucket_start, bucket_end) = (self.rows[i], self.rows[i + 1]);
            let bytes = read_at(
                &mut file,
                BUCKET_START + u64::from(self.buckets[i]) * self.bucket_size as u64,
                self.bucket_size,
            )?;
            let intervals = self.intervals(&bytes, col)?;
            let last = (bucket_end - 1).min(start + count - 1);
            while row <= last {
                let local = row - bucket_start;
                let k = intervals
                    .partition_point(|&(r, _)| r <= local)
                    .saturating_sub(1);
                let (_, offset) = intervals[k];
                let until = intervals
                    .get(k + 1)
                    .map_or(bucket_end - bucket_start, |&(r, _)| r);
                let n = (until.min(last - bucket_start + 1) - local) as usize;
                let value_at = 4 + offset as usize;
                match dtype {
                    DataType::Bool => {
                        let bit = (bytes.get(value_at).copied().unwrap_or(0)) & 1;
                        data.bytes.extend(std::iter::repeat_n(bit, n * nelem));
                    }
                    dt => {
                        let mut one = Vec::with_capacity(dt.size() * nelem);
                        convert_into(&mut one, &bytes[value_at..], dt, nelem, self.big)?;
                        for _ in 0..n {
                            data.bytes.extend_from_slice(&one);
                        }
                    }
                }
                row += n as u64;
            }
        }
        Ok(data)
    }

    /// (first local row, data offset) of the value intervals of `col` in a bucket.
    fn intervals(&self, bytes: &[u8], col: usize) -> Result<Vec<(u64, u32)>> {
        let big = self.big;
        let word = read_u32(bytes, 0, big)?;
        let wide = word & 0xf000_0000 != 0;
        let mut at = (word & 0x0fff_ffff) as usize;
        let mut out = Vec::new();
        for c in 0..self.columns.len() {
            let n = read_u32(bytes, at, big)? as usize;
            at += 4;
            let mut rows = Vec::with_capacity(n);
            for _ in 0..n {
                rows.push(if wide {
                    let r = read_u64(bytes, at, big)?;
                    at += 8;
                    r
                } else {
                    let r = u64::from(read_u32(bytes, at, big)?);
                    at += 4;
                    r
                });
            }
            let mut offsets = Vec::with_capacity(n);
            for _ in 0..n {
                offsets.push(read_u32(bytes, at, big)?);
                at += 4;
            }
            if c == col {
                out = rows.into_iter().zip(offsets).collect();
                break;
            }
        }
        if out.is_empty() {
            return err("IncrementalStMan bucket without values for the column");
        }
        Ok(out)
    }
}

// ---------------------------------------------------------------------------
// TiledShapeStMan and TiledColumnStMan.

struct Cube {
    shape: Vec<i64>,
    tile: Vec<i64>,
    tiles_per_dim: Vec<i64>,
    file: Option<usize>,
    file_offset: u64,
    bucket_size: usize,
    tile_pixels: usize,
}

struct Tsm {
    big: bool,
    files: Vec<Option<PathBuf>>,
    cubes: Vec<Cube>,
    /// Per data column (in table order): its byte offset in a tile.
    column_offset: Vec<usize>,
    columns: Vec<DataType>,
    nrdim: usize,
    row_map: Vec<u32>,
    cube_map: Vec<u32>,
    pos_map: Vec<u32>,
    by_row: bool,
}

impl Tsm {
    fn open(table: &TableFiles, seq: u32, kind: &str, columns: &[&ColumnDesc]) -> Result<Self> {
        let header_file = table.file(seq, "");
        let header = std::fs::read(&header_file)?;
        let mut h = Cursor::new(&header, true);
        h.magic()?;
        let outer = h.start_expect(kind)?;
        let fixed_tile = if kind == "TiledColumnStMan" {
            Some(h.iposition()?)
        } else {
            None
        };
        let inner = h.start_expect("TiledStMan")?;
        let big = if inner.version >= 2 { h.bool()? } else { true };
        if big == table.little {
            return err("TiledStMan endian flag mismatches the table");
        }
        let seqnr = h.u32()?;
        let nrrow = if inner.version >= 3 {
            h.u64()?
        } else {
            u64::from(h.u32()?)
        };
        let ncol = h.u32()? as usize;
        if seqnr != seq || ncol != columns.len() || nrrow != table.nrows {
            return err(format!(
                "TiledStMan header of {} mismatches the table",
                header_file.display()
            ));
        }
        let mut dtypes = Vec::with_capacity(ncol);
        for desc in columns {
            let code = h.i32()?;
            if code != desc.dtype.code() {
                return err("TiledStMan header data type mismatches the column");
            }
            dtypes.push(desc.dtype);
        }
        let _hypercolumn = h.string()?;
        let _max_cache = if inner.version >= 3 {
            h.u64()?
        } else {
            u64::from(h.u32()?)
        };
        let nrdim = h.u32()? as usize;
        let nfile = if inner.version >= 3 {
            h.u64()?
        } else {
            u64::from(h.u32()?)
        } as usize;
        let mut files = Vec::with_capacity(nfile);
        for _ in 0..nfile {
            if h.bool()? {
                let version = h.u32()?;
                let file_seq = h.u32()?;
                let _length = if version == 1 {
                    u64::from(h.u32()?)
                } else {
                    h.u64()?
                };
                files.push(Some(table.file(seq, &format!("_TSM{file_seq}"))));
            } else {
                files.push(None);
            }
        }
        // Data columns share a tile in descending order of pixel size
        // (stable), each column's values contiguous.
        let pixel = |dt: DataType| dt.size();
        let mut order: Vec<usize> = (0..ncol).collect();
        order.sort_by(|&a, &b| pixel(dtypes[b]).cmp(&pixel(dtypes[a])));
        let ncube = if inner.version >= 3 {
            h.u64()?
        } else {
            u64::from(h.u32()?)
        } as usize;
        let mut cubes = Vec::with_capacity(ncube);
        for _ in 0..ncube {
            let version = h.u32()?;
            h.skip_object()?; // id/coordinate values record
            let _extensible = h.bool()?;
            let _nrdim = h.u32()?;
            let shape = h.iposition()?;
            let tile = h.iposition()?;
            let file_seq = h.i32()?;
            let file_offset = if version == 1 {
                u64::from(h.u32()?)
            } else {
                h.u64()?
            };
            let tiles_per_dim: Vec<i64> = shape
                .iter()
                .zip(&tile)
                .map(|(&s, &t)| if t > 0 { (s + t - 1) / t } else { 0 })
                .collect();
            let tile_pixels = product(&tile);
            let bucket_size: usize = dtypes.iter().map(|&dt| tile_bytes(dt, tile_pixels)).sum();
            cubes.push(Cube {
                shape,
                tile,
                tiles_per_dim,
                file: (file_seq >= 0).then_some(file_seq as usize),
                file_offset,
                bucket_size,
                tile_pixels,
            });
        }
        h.end(&inner);
        let (mut row_map, mut cube_map, mut pos_map) = (Vec::new(), Vec::new(), Vec::new());
        let by_row = fixed_tile.is_none();
        if by_row {
            let _default_tile = h.iposition()?;
            let n = h.u32()? as usize;
            row_map = h.block_u32()?;
            cube_map = h.block_u32()?;
            pos_map = h.block_u32()?;
            row_map.truncate(n);
            cube_map.truncate(n);
            pos_map.truncate(n);
        }
        h.end(&outer);
        // Byte offsets of the columns within a tile depend on the tile size,
        // which may differ per cube; store the order and compute per read.
        let mut column_offset = vec![0usize; ncol];
        for (rank, &c) in order.iter().enumerate() {
            column_offset[c] = rank;
        }
        Ok(Tsm {
            big,
            files,
            cubes,
            column_offset,
            columns: dtypes,
            nrdim,
            row_map,
            cube_map,
            pos_map,
            by_row,
        })
    }

    /// Byte offset of column `col` in a tile of `cube`.
    fn offset_in_tile(&self, col: usize, cube: &Cube) -> usize {
        let rank = self.column_offset[col];
        let mut sizes: Vec<(usize, usize)> = (0..self.columns.len())
            .map(|c| {
                (
                    self.column_offset[c],
                    tile_bytes(self.columns[c], cube.tile_pixels),
                )
            })
            .collect();
        sizes.sort();
        sizes.iter().take(rank).map(|&(_, bytes)| bytes).sum()
    }

    /// Hypercube index and position along the last axis of `row`.
    fn locate(&self, row: u64) -> Result<(usize, i64)> {
        if !self.by_row {
            return Ok((0, row as i64));
        }
        if self.row_map.is_empty() || row > u64::from(*self.row_map.last().unwrap()) {
            return err(format!("row {row} has no tiled array"));
        }
        let i = self.row_map.partition_point(|&r| u64::from(r) < row);
        let cube = self.cube_map[i] as usize;
        if cube == 0 {
            return err(format!("row {row} has no tiled array"));
        }
        Ok((
            cube,
            i64::from(self.pos_map[i]) - (i64::from(self.row_map[i]) - row as i64),
        ))
    }

    fn read(&self, desc: &ColumnDesc, col: usize, start: u64, count: u64) -> Result<ColumnData> {
        let dtype = self.columns[col];
        if self.nrdim < 2 {
            return err(format!(
                "tiled scalar column {} is not supported",
                desc.name
            ));
        }
        let mut data = ColumnData {
            dtype: Some(dtype),
            nrows: count,
            ..Default::default()
        };
        let mut cache: HashMap<(usize, usize), Vec<u8>> = HashMap::new();
        let mut handles: HashMap<usize, File> = HashMap::new();
        let last = self.nrdim - 1;
        let native = dtype.native_size();
        for row in start..start + count {
            let (cube_index, pos) = self.locate(row)?;
            let cube = &self.cubes[cube_index];
            let cell = &cube.shape[..last];
            if row == start {
                data.shape = cell.to_vec();
            } else if cell != data.shape.as_slice() {
                return err(format!(
                    "rows of {} differ in shape; read fewer rows at once",
                    desc.name
                ));
            }
            let file_index = cube
                .file
                .ok_or_else(|| MsError(format!("hypercube of {} has no file", desc.name)))?;
            let path = self
                .files
                .get(file_index)
                .and_then(|f| f.as_ref())
                .ok_or_else(|| {
                    MsError(format!(
                        "tile file {file_index} of {} is missing from the header",
                        desc.name
                    ))
                })?;
            if let std::collections::hash_map::Entry::Vacant(slot) = handles.entry(file_index) {
                slot.insert(File::open(path)?);
            }
            let file = handles.get_mut(&file_index).unwrap();
            let column_at = self.offset_in_tile(col, cube);
            let tile_last = (pos / cube.tile[last]) as usize;
            let in_tile_last = pos % cube.tile[last];
            // Strides of the tile grid, of the pixels inside a tile and of the cell.
            let mut grid_stride = vec![1i64; self.nrdim];
            let mut pixel_stride = vec![1i64; self.nrdim];
            let mut cell_stride = vec![1i64; last.max(1)];
            for i in 1..self.nrdim {
                grid_stride[i] = grid_stride[i - 1] * cube.tiles_per_dim[i - 1];
                pixel_stride[i] = pixel_stride[i - 1] * cube.tile[i - 1];
                if i < last {
                    cell_stride[i] = cell_stride[i - 1] * cell[i - 1];
                }
            }
            let cell_pixels = product(cell);
            let out_at = data.bytes.len();
            data.bytes.resize(out_at + cell_pixels * native, 0);
            let out = &mut data.bytes[out_at..];
            let contiguous =
                (0..last).all(|i| cube.tiles_per_dim[i] == 1 && cube.tile[i] == cell[i]);
            // Visit every tile the cell intersects (the grid over axes
            // 0..last-1 at the row's tile along the last axis) and copy its
            // block of the cell as runs along axis 0.
            let mut tpos = vec![0i64; last];
            loop {
                let tile_nr = tile_last * grid_stride[last] as usize
                    + (0..last)
                        .map(|i| (tpos[i] * grid_stride[i]) as usize)
                        .sum::<usize>();
                let key = (cube_index, tile_nr);
                if !cache.contains_key(&key) {
                    if cache.len() >= TILE_CACHE {
                        cache.clear();
                    }
                    let at = cube.file_offset + tile_nr as u64 * cube.bucket_size as u64;
                    cache.insert(key, read_at(file, at, cube.bucket_size)?);
                }
                let tile = &cache[&key][column_at..];
                let base = (in_tile_last * pixel_stride[last]) as usize;
                if contiguous {
                    copy_pixels(out, 0, tile, base, cell_pixels, dtype, self.big)?;
                    break;
                }
                // The block of this tile: pixel range per axis of the cell.
                let block_start: Vec<i64> = (0..last).map(|i| tpos[i] * cube.tile[i]).collect();
                let block_len: Vec<i64> = (0..last)
                    .map(|i| (block_start[i] + cube.tile[i]).min(cell[i]) - block_start[i])
                    .collect();
                let run = block_len[0] as usize;
                let mut idx = vec![0i64; last];
                loop {
                    let src = base
                        + (1..last)
                            .map(|i| (idx[i] * pixel_stride[i]) as usize)
                            .sum::<usize>();
                    let dst = block_start[0] as usize
                        + (1..last)
                            .map(|i| ((block_start[i] + idx[i]) * cell_stride[i]) as usize)
                            .sum::<usize>();
                    copy_pixels(out, dst, tile, src, run, dtype, self.big)?;
                    let mut i = 1;
                    while i < last {
                        idx[i] += 1;
                        if idx[i] < block_len[i] {
                            break;
                        }
                        idx[i] = 0;
                        i += 1;
                    }
                    if i >= last {
                        break;
                    }
                }
                let mut i = 0;
                while i < last {
                    tpos[i] += 1;
                    if tpos[i] < cube.tiles_per_dim[i] {
                        break;
                    }
                    tpos[i] = 0;
                    i += 1;
                }
                if i >= last {
                    break;
                }
            }
        }
        Ok(data)
    }
}

/// Copy `count` pixels from pixel `src` of a tile's column data into pixel
/// `dst` of a native cell buffer (booleans from bits to bytes).
fn copy_pixels(
    out: &mut [u8],
    dst: usize,
    tile: &[u8],
    src: usize,
    count: usize,
    dtype: DataType,
    big: bool,
) -> Result<()> {
    if dtype == DataType::Bool {
        let mut bits = Vec::with_capacity(count + 8);
        bits_into(&mut bits, tile, src, count)?;
        out.get_mut(dst..dst + count)
            .ok_or_else(|| MsError("tiled cell overrun".into()))?
            .copy_from_slice(&bits);
        return Ok(());
    }
    let size = dtype.size();
    let from = tile
        .get(src * size..(src + count) * size)
        .ok_or_else(|| MsError("tile overrun".into()))?;
    let to = out
        .get_mut(dst * size..(dst + count) * size)
        .ok_or_else(|| MsError("tiled cell overrun".into()))?;
    to.copy_from_slice(from);
    if big != cfg!(target_endian = "big") && size > 1 {
        for unit in to.chunks_exact_mut(dtype.swap_unit()) {
            unit.reverse();
        }
    }
    Ok(())
}

/// Bytes a column's values occupy in a tile of `pixels` pixels.
fn tile_bytes(dtype: DataType, pixels: usize) -> usize {
    match dtype {
        DataType::Bool => pixels.div_ceil(8),
        dt => dt.size() * pixels,
    }
}

// ---------------------------------------------------------------------------
// The table.

enum Manager {
    Ssm(Ssm),
    Ism(Ism),
    Tsm(Tsm),
    Unsupported(String),
}

struct ManagerSlot {
    seq: u32,
    kind: String,
    manager: Manager,
}

struct TableFiles {
    dir: PathBuf,
    little: bool,
    nrows: u64,
}

impl TableFiles {
    fn file(&self, seq: u32, suffix: &str) -> PathBuf {
        self.dir.join(format!("table.f{seq}{suffix}"))
    }
}

/// An opened casacore table (one directory with `table.dat`).
pub struct Table {
    pub path: PathBuf,
    pub nrows: u64,
    pub little_endian: bool,
    pub columns: Vec<ColumnDesc>,
    managers: Vec<ManagerSlot>,
    /// (manager slot, column index within the manager) per table column.
    binding: Vec<(usize, usize)>,
}

impl Table {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let dir = path.as_ref().to_path_buf();
        let bytes = std::fs::read(dir.join("table.dat"))
            .map_err(|e| MsError(format!("{}: {e}", dir.join("table.dat").display())))?;
        let mut c = Cursor::new(&bytes, true);
        c.magic()?;
        let table = c.start_expect("Table")?;
        if table.version > 3 {
            return err(format!(
                "table.dat version {} is not supported",
                table.version
            ));
        }
        let nrows = if table.version > 2 {
            c.u64()?
        } else {
            u64::from(c.u32()?)
        };
        // Rows added after table.dat was written are counted in the sync
        // record of table.lock (read, never written); 0 there means use
        // table.dat, as PlainTable does.
        let nrows = match lock_sync_rows(&dir)? {
            Some(n) if n > 0 => n,
            _ => nrows,
        };
        let format = c.u32()?;
        let little = format != 0;
        let kind = c.string()?;
        if kind != "PlainTable" {
            return err(format!("table type {kind} is not supported"));
        }
        // TableDesc: name, version, comment, keywords, private keywords, columns.
        let desc = c.start_expect("TableDesc")?;
        let _name = c.string()?;
        let _version = c.string()?;
        let _comment = c.string()?;
        c.skip_object()?;
        if desc.version != 1 {
            c.skip_object()?;
        }
        let ncol = c.u32()? as usize;
        let mut columns = Vec::with_capacity(ncol);
        for _ in 0..ncol {
            let _version = c.u32()?;
            let class = c.string()?;
            let _base_version = c.u32()?;
            let name = c.string()?;
            let _comment = c.string()?;
            let manager_type = c.string()?;
            let manager_name = c.string()?;
            let dtype = DataType::from_code(c.i32()?)?;
            let option = c.i32()?;
            let ndim = c.i32()?;
            let is_array = class.starts_with("ArrayColumnDesc");
            if !is_array && !class.starts_with("ScalarColumnDesc") {
                return err(format!("column class {class} of {name} is not supported"));
            }
            let shape = if is_array { c.iposition()? } else { Vec::new() };
            let max_length = c.u32()?;
            c.skip_object()?; // keywords
            let _desc_version = c.u32()?;
            if is_array {
                c.bool()?;
            } else {
                // The default value, one value of the type.
                match dtype {
                    DataType::Str => {
                        c.string()?;
                    }
                    DataType::Bool => {
                        c.u8()?;
                    }
                    dt => {
                        c.take(dt.size())?;
                    }
                }
            }
            columns.push(ColumnDesc {
                name,
                dtype,
                is_array,
                option,
                ndim,
                shape,
                max_length,
                manager_type,
                manager_name,
                manager_seq: 0,
            });
        }
        c.end(&desc);
        if table.version == 1 {
            c.skip_object()?; // keywords kept outside the description
        }
        // ColumnSet: version, storage option, data managers, column bindings.
        let first = c.i32()?;
        let set_version = if first < 0 {
            let v = -first;
            if v <= 2 {
                c.u32()?;
            } else {
                c.u64()?;
            }
            v
        } else {
            1
        };
        if set_version >= 3 {
            // StorageOption (option, buffer size): MultiFile tables fail later
            // when their `table.fN` files are missing.
            let _option = c.i32()?;
            let _buffer = c.i32()?;
        }
        let _nr_managers = c.u32()?;
        let n = c.u32()? as usize;
        let mut managers_raw = Vec::with_capacity(n);
        for _ in 0..n {
            let kind = c.string()?;
            let seq = c.u32()?;
            managers_raw.push((kind, seq));
        }
        for column in columns.iter_mut() {
            let _version = c.u32()?;
            let _original_name = c.string()?;
            let _derived_version = c.u32()?;
            column.manager_seq = c.u32()?;
            if column.is_array && c.bool()? {
                let shape = c.iposition()?;
                if column.shape.is_empty() {
                    column.shape = shape;
                }
            }
        }
        let mut blobs = Vec::with_capacity(n);
        for _ in 0..n {
            let len = c.u32()? as usize;
            blobs.push(c.take(len)?.to_vec());
        }
        let files = TableFiles {
            dir: dir.clone(),
            little,
            nrows,
        };
        let mut managers = Vec::with_capacity(n);
        let mut binding = vec![(usize::MAX, usize::MAX); columns.len()];
        for (slot, ((kind, seq), blob)) in managers_raw.into_iter().zip(blobs).enumerate() {
            let mine: Vec<usize> = (0..columns.len())
                .filter(|&i| columns[i].manager_seq == seq)
                .collect();
            for (k, &i) in mine.iter().enumerate() {
                binding[i] = (slot, k);
            }
            let descs: Vec<&ColumnDesc> = mine.iter().map(|&i| &columns[i]).collect();
            let manager = match kind.as_str() {
                "StandardStMan" => Manager::Ssm(Ssm::open(&files, seq, &blob, &descs)?),
                "IncrementalStMan" => match Ism::open(&files, seq, &blob, &descs) {
                    Ok(ism) => Manager::Ism(ism),
                    Err(e) => Manager::Unsupported(e.0),
                },
                "TiledShapeStMan" | "TiledColumnStMan" => {
                    Manager::Tsm(Tsm::open(&files, seq, &kind, &descs)?)
                }
                other => Manager::Unsupported(format!("storage manager {other} is not supported")),
            };
            managers.push(ManagerSlot { seq, kind, manager });
        }
        Ok(Table {
            path: dir,
            nrows,
            little_endian: little,
            columns,
            managers,
            binding,
        })
    }

    pub fn column(&self, name: &str) -> Result<usize> {
        self.columns
            .iter()
            .position(|c| c.name == name)
            .ok_or_else(|| MsError(format!("column {name} does not exist")))
    }

    /// Read rows `start..start+count` of a column; `count` 0 means to the end.
    pub fn read_column(&self, name: &str, start: u64, count: u64) -> Result<ColumnData> {
        let index = self.column(name)?;
        let desc = &self.columns[index];
        let count = if count == 0 {
            self.nrows.saturating_sub(start)
        } else {
            count
        };
        if start + count > self.nrows {
            return err(format!(
                "rows {start}..{} exceed the {} rows of the table",
                start + count,
                self.nrows
            ));
        }
        let (slot, col) = self.binding[index];
        let manager = &self.managers[slot];
        let mut data = match &manager.manager {
            Manager::Ssm(ssm) => ssm.read(desc, col, start, count),
            Manager::Ism(ism) => ism.read(col, start, count),
            Manager::Tsm(tsm) => tsm.read(desc, col, start, count),
            Manager::Unsupported(reason) => err(reason.clone()),
        }
        .map_err(|e| MsError(format!("{}: {e}", desc.name)))?;
        if count == 0 {
            data.shape = desc.shape.clone();
        }
        Ok(data)
    }

    /// JSON description of the table for the Python layer.
    pub fn describe_json(&self) -> String {
        let mut out = format!(
            "{{\"path\":\"{}\",\"nrows\":{},\"little_endian\":{},\"columns\":[",
            json_escape(&self.path.to_string_lossy()),
            self.nrows,
            self.little_endian
        );
        for (i, c) in self.columns.iter().enumerate() {
            let (slot, _) = self.binding[i];
            let manager = &self.managers[slot];
            let supported = !matches!(manager.manager, Manager::Unsupported(_));
            if i > 0 {
                out.push(',');
            }
            out.push_str(&format!(
                "{{\"name\":\"{}\",\"dtype\":\"{}\",\"is_array\":{},\"option\":{},\"ndim\":{},\"shape\":[{}],\"max_length\":{},\"manager_type\":\"{}\",\"manager_name\":\"{}\",\"manager_seq\":{},\"supported\":{}}}",
                json_escape(&c.name),
                c.dtype.numpy(),
                c.is_array,
                c.option,
                c.ndim,
                c.shape.iter().map(|s| s.to_string()).collect::<Vec<_>>().join(","),
                c.max_length,
                json_escape(&manager.kind),
                json_escape(&c.manager_name),
                manager.seq,
                supported
            ));
        }
        out.push_str("]}");
        out
    }
}

/// The row count in the sync record of `table.lock`: after the 260-byte
/// request list comes a canonical `uInt` length and an AipsIO `sync` object.
fn lock_sync_rows(dir: &Path) -> Result<Option<u64>> {
    let path = dir.join("table.lock");
    if !path.is_file() {
        return Ok(None);
    }
    let bytes = std::fs::read(&path)?;
    const REQUESTS: usize = (1 + 2 * 32) * 4;
    if bytes.len() < REQUESTS + 4 {
        return Ok(None);
    }
    let length = read_u32(&bytes, REQUESTS, true)? as usize;
    if length == 0 {
        return Ok(None);
    }
    let info = bytes
        .get(REQUESTS + 4..REQUESTS + 4 + length)
        .ok_or_else(|| MsError("truncated table.lock sync record".into()))?;
    let mut c = Cursor::new(info, true);
    c.magic()?;
    let sync = c.start_expect("sync")?;
    let nrows = if sync.version == 1 {
        u64::from(c.u32()?)
    } else {
        c.u64()?
    };
    Ok(Some(nrows))
}

fn json_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn object(kind: &str, version: u32, body: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        let length = 4 + 4 + kind.len() + 4 + body.len();
        out.extend((length as u32).to_be_bytes());
        out.extend((kind.len() as u32).to_be_bytes());
        out.extend(kind.as_bytes());
        out.extend(version.to_be_bytes());
        out.extend(body);
        out
    }

    #[test]
    fn aipsio_objects_nest_and_skip() {
        let inner = object("Inner", 7, &[1, 2, 3]);
        let mut body = Vec::new();
        body.extend(5u32.to_be_bytes());
        body.extend(inner);
        body.extend(9u32.to_be_bytes());
        let mut bytes = MAGIC.to_be_bytes().to_vec();
        bytes.extend(object("Outer", 2, &body));
        let mut c = Cursor::new(&bytes, true);
        c.magic().unwrap();
        let outer = c.start_expect("Outer").unwrap();
        assert_eq!(outer.version, 2);
        assert_eq!(c.u32().unwrap(), 5);
        c.skip_object().unwrap();
        assert_eq!(c.u32().unwrap(), 9);
        c.end(&outer);
        assert_eq!(c.pos, bytes.len());
    }

    #[test]
    fn iposition_and_block_versions() {
        let mut body = 2u32.to_be_bytes().to_vec();
        body.extend(3i32.to_be_bytes());
        body.extend((-1i32).to_be_bytes());
        let ipos = object("IPosition", 1, &body);
        let mut c = Cursor::new(&ipos, true);
        assert_eq!(c.iposition().unwrap(), vec![3, -1]);
        let mut body = 2u32.to_le_bytes().to_vec();
        body.extend(7u64.to_le_bytes());
        body.extend(8u64.to_le_bytes());
        let mut block = Vec::new();
        let length = 4 + 4 + 5 + 4 + body.len();
        block.extend((length as u32).to_le_bytes());
        block.extend(5u32.to_le_bytes());
        block.extend(b"Block");
        block.extend(1u32.to_le_bytes());
        block.extend(body);
        let mut c = Cursor::new(&block, false);
        assert_eq!(c.block_u64().unwrap(), vec![7, 8]);
    }

    #[test]
    fn bits_are_least_significant_first() {
        let mut out = Vec::new();
        bits_into(&mut out, &[0b0000_0101, 0b1000_0000], 1, 10).unwrap();
        assert_eq!(out, vec![0, 1, 0, 0, 0, 0, 0, 0, 0, 0]);
        let mut out = Vec::new();
        bits_into(&mut out, &[0b0000_0101, 0b1000_0000], 0, 16).unwrap();
        assert_eq!(out[15], 1);
        assert!(bits_into(&mut out, &[0], 0, 9).is_err());
    }

    #[test]
    fn big_endian_values_are_swapped_per_unit() {
        let mut out = Vec::new();
        convert_into(
            &mut out,
            &[0, 0, 0, 1, 0, 0, 0, 2],
            DataType::Complex,
            1,
            true,
        )
        .unwrap();
        assert_eq!(out, vec![1, 0, 0, 0, 2, 0, 0, 0]);
        let mut out = Vec::new();
        convert_into(&mut out, &[1, 0, 0, 0], DataType::Int, 1, false).unwrap();
        assert_eq!(out, vec![1, 0, 0, 0]);
    }

    #[test]
    fn ssm_index_lookup() {
        let index = SsmIndex {
            last_row: vec![31, 63, 95],
            bucket: vec![4, 5, 6],
        };
        assert_eq!(index.find(0).unwrap(), (0, 0));
        assert_eq!(index.find(31).unwrap(), (0, 0));
        assert_eq!(index.find(32).unwrap(), (1, 32));
        assert_eq!(index.find(95).unwrap(), (2, 64));
        assert!(index.find(96).is_err());
    }

    #[test]
    fn json_description_escapes_names() {
        assert_eq!(json_escape("a\"b\\c\n"), "a\\\"b\\\\c\\u000a");
    }

    /// Smoke test on a real table when `RANG_MS_FIXTURE` names one; the
    /// column-exact check is `examples/check_ms_reader.py`.
    #[test]
    fn reads_a_fixture_when_given() {
        let Ok(path) = std::env::var("RANG_MS_FIXTURE") else {
            return;
        };
        let table = Table::open(&path).unwrap();
        assert!(table.nrows > 0);
        for name in ["TIME", "ANTENNA1", "FLAG_ROW", "UVW", "DATA", "FLAG"] {
            let data = table.read_column(name, 0, 0).unwrap();
            assert_eq!(data.nrows, table.nrows, "{name}");
            let cell = if data.shape.is_empty() {
                1
            } else {
                product(&data.shape)
            };
            let dtype = data.dtype.unwrap();
            assert_eq!(
                data.bytes.len(),
                table.nrows as usize * cell * dtype.native_size(),
                "{name}"
            );
        }
        let one = table.read_column("TIME", 2, 1).unwrap();
        let all = table.read_column("TIME", 0, 0).unwrap();
        assert_eq!(one.bytes, all.bytes[16..24]);
        let antenna = Table::open(Path::new(&path).join("ANTENNA")).unwrap();
        let names = antenna.read_column("NAME", 0, 0).unwrap();
        assert_eq!(names.strings.len(), antenna.nrows as usize);
        assert!(names.strings.iter().all(|n| !n.is_empty()));
    }
}
