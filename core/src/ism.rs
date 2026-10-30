//! IncrementalStMan writes (research/e5-table-writer-rest.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The IncrementalStMan of casacore 3.8.1, step for step: `ISMColumn`
//! (values valid from a row on, contracted with equal neighbours, the last
//! row put propagated into later buckets), `ISMIndColumn` (indirect arrays
//! shared between rows through reference counts in a version-1 array file),
//! `ISMBucket` (data, then per column the row numbers and offsets of its
//! values; the simple split at the end of the table and the general split
//! into halves of about equal length), `ISMIndex` (first row and bucket
//! number of every bucket) and `ISMBase` (bucket sizing, the header and the
//! index after the last bucket, rows added and removed, recreated at no
//! rows). casacore's `BucketCache` is modelled with its slots and its one
//! scratch buffer, because a bucket written to disk holds the scratch
//! buffer's earlier bytes after its own index. Little- and big-endian. The
//! format was read in the casacore sources; nothing is copied from casacore
//! (LGPL-2.1-or-later).

use std::collections::BTreeMap;
use std::fs::{File, OpenOptions};
use std::path::{Path, PathBuf};

use crate::aipsio::Writer;
use crate::ms::{Cursor, DataType, MsError, Result};
use crate::ms_desc::{ColBinding, ColDesc};
use crate::ms_write::{
    ArrayFile, Cell, bool_to_bits_from_zero, get_bits, order_u32, order_u64, product, read_at,
    read_order_u32, read_order_u64, to_order, write_at,
};

fn err<T>(message: impl Into<String>) -> Result<T> {
    Err(MsError(message.into()))
}

/// Where the buckets start: after the 512-byte header.
const START: u64 = 512;
/// `DataManager::MAXROWNR32`.
const MAXROWNR32: u64 = 2_147_483_647;

/// One column's kind in an IncrementalStMan.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum IsmKind {
    /// A scalar or a Direct array of `n` numeric or Bool values.
    Values(usize),
    /// A scalar string or a Direct string array of `n` strings.
    Strings(usize),
    /// An indirect array (`ISMIndColumn`): FixedShape or variable.
    Indirect(Option<Vec<i64>>),
}

/// The state of `ISMIndColumn::indArray_p` (`StIndArray`).
#[derive(Clone, Debug, Default)]
struct IndArray {
    offset: u64,
    /// Bytes from the record to its values; 0 until its shape was read.
    arr_offset: u64,
    shape: Vec<i64>,
}

#[derive(Clone, Debug)]
pub(crate) struct IsmCol {
    pub(crate) name: String,
    pub(crate) dtype: DataType,
    pub(crate) kind: IsmKind,
    last_row_put: u64,
    /// Rows for which the last value read is valid (`startRow_p`,
    /// `endRow_p`; invalid when start > end).
    start_row: u64,
    end_row: u64,
    /// `ISMIndColumn`: the value last read and whether it has an array.
    ind: IndArray,
    found: bool,
    /// The cell shape of an array column (empty when not fixed); None for
    /// a scalar.
    pub(crate) cell: Option<Vec<i64>>,
}

impl IsmCol {
    fn invalidate(&mut self) {
        self.start_row = 1;
        self.end_row = 0;
    }

    fn valid(&self, row: u64) -> bool {
        row >= self.start_row && row <= self.end_row
    }
}

/// The column of a description in an IncrementalStMan.
pub(crate) fn ism_col(desc: &ColDesc, binding: &ColBinding) -> Result<IsmCol> {
    let dtype = DataType::from_code(desc.dtype)?;
    let fixed = match (&binding.shape, &desc.shape) {
        (Some(Some(s)), _) => Some(s.clone()),
        (_, Some(s)) if !s.is_empty() && desc.option & 4 != 0 => Some(s.clone()),
        _ => None,
    };
    let kind = if !desc.is_array() {
        if dtype == DataType::Str {
            IsmKind::Strings(1)
        } else {
            IsmKind::Values(1)
        }
    } else if desc.option & 1 != 0 {
        let n = product(fixed.as_deref().unwrap_or(&[]));
        if dtype == DataType::Str {
            IsmKind::Strings(n)
        } else {
            IsmKind::Values(n)
        }
    } else {
        if dtype == DataType::Str {
            return err(format!(
                "{}: indirect string arrays in an IncrementalStMan are not written (E6)",
                desc.name
            ));
        }
        IsmKind::Indirect(fixed.clone())
    };
    Ok(IsmCol {
        name: desc.name.clone(),
        dtype,
        kind,
        last_row_put: 0,
        start_row: 1,
        end_row: 0,
        ind: IndArray::default(),
        found: false,
        cell: desc.is_array().then(|| fixed.clone().unwrap_or_default()),
    })
}

impl IsmCol {
    /// `nelements()` as `ISMBase::init` sees it (indirect columns: 1).
    fn nelements(&self) -> u32 {
        match &self.kind {
            IsmKind::Values(n) | IsmKind::Strings(n) => *n as u32,
            IsmKind::Indirect(_) => 1,
        }
    }

    /// `fixedLength_p` after `ISMColumn::init` (0: variable, strings).
    fn fixed_length(&self) -> u32 {
        match &self.kind {
            IsmKind::Strings(_) => 0,
            IsmKind::Indirect(_) => 8,
            IsmKind::Values(n) => match self.dtype {
                DataType::Bool => n.div_ceil(8) as u32,
                dt => (dt.size() * n) as u32,
            },
        }
    }
}

// ---------------------------------------------------------------------------
// Value encodings (`writeFunc_p`, `readFunc_p`, `compareValue`).

/// The stored form of native values (Bool one byte each) of a column.
fn encode_values(dtype: DataType, native: &[u8], big: bool) -> Vec<u8> {
    if dtype == DataType::Bool {
        let mut out = vec![0u8; native.len().div_ceil(8)];
        bool_to_bits_from_zero(&mut out, native);
        return out;
    }
    to_order(dtype, native, big)
}

/// `ISMColumn::fromString`: one string as its total length and characters,
/// several as the total length, then each length and its characters.
pub(crate) fn encode_strings(strings: &[String], big: bool) -> Vec<u8> {
    let mut out = Vec::new();
    if strings.len() > 1 {
        out.extend([0u8; 4]);
    }
    for s in strings {
        out.extend(order_u32(s.len() as u32, big));
        out.extend(s.as_bytes());
    }
    let total = out.len() as u32;
    out[..4].copy_from_slice(&order_u32(total, big));
    out
}

/// `ISMColumn::toString` of `n` strings.
pub(crate) fn decode_strings(bytes: &[u8], n: usize, big: bool) -> Result<Vec<String>> {
    let get = |at: usize| -> Result<u32> {
        bytes
            .get(at..at + 4)
            .map(|b| read_order_u32(b, big))
            .ok_or_else(|| MsError("truncated IncrementalStMan string".into()))
    };
    let mut strleng = get(0)?.wrapping_sub(4) as usize;
    let mut at = 4;
    let mut out = Vec::with_capacity(n);
    for _ in 0..n {
        if n > 1 {
            strleng = get(at)? as usize;
            at += 4;
        }
        let s = bytes
            .get(at..at + strleng)
            .ok_or_else(|| MsError("truncated IncrementalStMan string".into()))?;
        out.push(String::from_utf8_lossy(s).into_owned());
        at += strleng;
    }
    Ok(out)
}

/// `compareValue` of two stored values: `ObjCompare` (`<` then `==`), so
/// IEEE equality for floating point (signed zeros equal, NaN unequal) and
/// exact equality otherwise; indirect columns never compare equal.
fn values_equal(col: &IsmCol, a: &[u8], b: &[u8], big: bool) -> bool {
    match &col.kind {
        IsmKind::Indirect(_) => false,
        IsmKind::Strings(_) => a == b,
        IsmKind::Values(n) => match col.dtype {
            DataType::Bool => get_bits(a, 0, *n) == get_bits(b, 0, *n),
            DataType::Float | DataType::Complex => {
                a.chunks_exact(4).zip(b.chunks_exact(4)).all(|(x, y)| {
                    f32::from_bits(read_order_u32(x, big)) == f32::from_bits(read_order_u32(y, big))
                })
            }
            DataType::Double | DataType::DComplex => {
                a.chunks_exact(8).zip(b.chunks_exact(8)).all(|(x, y)| {
                    f64::from_bits(read_order_u64(x, big)) == f64::from_bits(read_order_u64(y, big))
                })
            }
            _ => a == b,
        },
    }
}

// ---------------------------------------------------------------------------
// ISMBucket.

/// One bucket in memory (`ISMBucket`): the data, the index length counted
/// with 64-bit row numbers, and per column the rows and offsets of values.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct Bucket {
    data: Vec<u8>,
    index_leng: u32,
    rows: Vec<Vec<u64>>,
    offs: Vec<Vec<u32>>,
}

/// The parameters bucket operations need: byte order, bucket size and the
/// fixed length of every column (0: variable, read from the value).
struct Params<'a> {
    big: bool,
    size: u32,
    fixed: &'a [u32],
}

/// The first index whose row is at least `row`, and whether it equals it
/// (`binarySearchBrackets`).
fn brackets(rows: &[u64], row: u64) -> (usize, bool) {
    let i = rows.partition_point(|&r| r < row);
    (i, i < rows.len() && rows[i] == row)
}

impl Bucket {
    fn new(ncol: usize) -> Self {
        Bucket {
            data: Vec::new(),
            index_leng: 4 + 4 * ncol as u32,
            rows: vec![Vec::new(); ncol],
            offs: vec![Vec::new(); ncol],
        }
    }

    /// `ISMBucket::read`.
    fn read(storage: &[u8], ncol: usize, big: bool) -> Result<Self> {
        let word = read_order_u32(storage, big);
        let use32 = word & 0xf000_0000 == 0;
        let mut at = (word & 0x0fff_ffff) as usize;
        if at < 4 || at > storage.len() {
            return err("IncrementalStMan bucket offset out of range");
        }
        let mut b = Bucket {
            data: storage[4..at].to_vec(),
            index_leng: 4,
            rows: Vec::with_capacity(ncol),
            offs: Vec::with_capacity(ncol),
        };
        let need = |at: usize, n: usize| -> Result<()> {
            if at + n > storage.len() {
                err("truncated IncrementalStMan bucket index")
            } else {
                Ok(())
            }
        };
        for _ in 0..ncol {
            need(at, 4)?;
            let n = read_order_u32(&storage[at..], big) as usize;
            at += 4;
            b.index_leng += 4;
            let mut rows = Vec::with_capacity(n);
            for _ in 0..n {
                if use32 {
                    need(at, 4)?;
                    rows.push(u64::from(read_order_u32(&storage[at..], big)));
                    at += 4;
                } else {
                    need(at, 8)?;
                    rows.push(read_order_u64(&storage[at..], big));
                    at += 8;
                }
            }
            let mut offs = Vec::with_capacity(n);
            for _ in 0..n {
                need(at, 4)?;
                offs.push(read_order_u32(&storage[at..], big));
                at += 4;
            }
            b.index_leng += n as u32 * 12;
            b.rows.push(rows);
            b.offs.push(offs);
        }
        Ok(b)
    }

    /// `ISMBucket::write` into the start of `storage` (the rest is kept).
    fn write(&self, storage: &mut [u8], big: bool) {
        let use32 = self
            .rows
            .iter()
            .all(|r| r.last().is_none_or(|&l| l <= MAXROWNR32));
        let mut offset = self.data.len() + 4;
        let mut word = offset as u32;
        if !use32 {
            word |= 0x8000_0000;
        }
        storage[..4].copy_from_slice(&order_u32(word, big));
        storage[4..4 + self.data.len()].copy_from_slice(&self.data);
        for (rows, offs) in self.rows.iter().zip(&self.offs) {
            storage[offset..offset + 4].copy_from_slice(&order_u32(rows.len() as u32, big));
            offset += 4;
            for &r in rows {
                if use32 {
                    storage[offset..offset + 4].copy_from_slice(&order_u32(r as u32, big));
                    offset += 4;
                } else {
                    storage[offset..offset + 8].copy_from_slice(&order_u64(r, big));
                    offset += 8;
                }
            }
            for &o in offs {
                storage[offset..offset + 4].copy_from_slice(&order_u32(o, big));
                offset += 4;
            }
        }
    }

    /// The length of the value at `at` of a column of fixed length `fixed`.
    fn length(&self, fixed: u32, at: u32, big: bool) -> u32 {
        if fixed != 0 {
            fixed
        } else {
            read_order_u32(&self.data[at as usize..], big)
        }
    }

    fn value(&self, c: usize, idx: usize, p: &Params) -> &[u8] {
        let at = self.offs[c][idx];
        let n = self.length(p.fixed[c], at, p.big);
        &self.data[at as usize..(at + n) as usize]
    }

    /// `getInterval`: (index, interval start, end, offset of its value);
    /// the index is that of the interval when `row` starts it, else of the
    /// next one. `nrrow` 0 makes the last interval's end wrap, as in
    /// casacore (`putData` passes 0).
    fn interval(&self, c: usize, row: u64, nrrow: u64) -> (usize, u64, u64, u32) {
        let rows = &self.rows[c];
        let (index, found) = brackets(rows, row);
        let mut inx = index;
        if !found {
            inx -= 1;
        }
        let offset = self.offs[c][inx];
        let start = rows[inx];
        inx += 1;
        let end = if inx == rows.len() { nrrow } else { rows[inx] };
        (index, start, end.wrapping_sub(1), offset)
    }

    /// `getOffset`: the index of the value valid at `row`.
    fn offset_index(&self, c: usize, row: u64) -> usize {
        let (index, found) = brackets(&self.rows[c], row);
        if found { index } else { index - 1 }
    }

    fn can_replace(&self, new: u32, old: u32, p: &Params) -> bool {
        (self.data.len() as u32)
            .wrapping_add(new)
            .wrapping_sub(old)
            .wrapping_add(self.index_leng)
            <= p.size
    }

    fn can_add(&self, len: u32, p: &Params) -> bool {
        self.data.len() as u32 + len + self.index_leng + 4 + 8 <= p.size
    }

    /// `removeData`: drop `leng` bytes (0: the value's own length) at
    /// `offset`, moving later values and their offsets down.
    fn remove_data(&mut self, offset: u32, leng: u32, big: bool) {
        let leng = self.length(leng, offset, big);
        let new_len = self.data.len() as u32 - leng;
        if new_len > offset {
            self.data.drain(offset as usize..(offset + leng) as usize);
            for offs in &mut self.offs {
                for o in offs.iter_mut() {
                    if *o > offset {
                        *o -= leng;
                    }
                }
            }
        } else {
            self.data.truncate(new_len as usize);
        }
    }

    fn insert_data(&mut self, data: &[u8]) -> u32 {
        let at = self.data.len() as u32;
        self.data.extend_from_slice(data);
        at
    }

    /// `ISMBucket::replaceData` of the value at index `idx` of column `c`.
    fn replace(&mut self, c: usize, idx: usize, data: &[u8], old: u32, big: bool) {
        let at = self.offs[c][idx];
        if old as usize == data.len() {
            self.data[at as usize..at as usize + data.len()].copy_from_slice(data);
        } else {
            self.remove_data(at, old, big);
            self.offs[c][idx] = self.insert_data(data);
        }
    }

    /// `ISMBucket::addData`.
    fn add(&mut self, c: usize, row: u64, index: usize, data: &[u8]) {
        let rows = &mut self.rows[c];
        if index < rows.len() && rows[index] == row {
            rows[index] += 1;
        }
        rows.insert(index, row);
        self.index_leng += 12;
        let at = self.insert_data(data);
        self.offs[c].insert(index, at);
    }

    /// `ISMBucket::shiftLeft`: remove `nr` values from `index` on.
    fn shift_left(&mut self, c: usize, index: usize, nr: usize, p: &Params) {
        for i in 0..nr {
            let at = self.offs[c][index + i];
            self.remove_data(at, p.fixed[c], p.big);
        }
        self.rows[c].drain(index..index + nr);
        self.offs[c].drain(index..index + nr);
        self.index_leng -= nr as u32 * 12;
    }

    /// `copyData` of the value at `from` of column `c` into `other`.
    fn copy_data(
        &self,
        other: &mut Bucket,
        c: usize,
        to_row: u64,
        from: usize,
        to: usize,
        p: &Params,
    ) {
        let v = self.value(c, from, p).to_vec();
        other.add(c, to_row, to, &v);
    }

    /// `simpleSplit`: the last values start the right bucket.
    #[allow(clippy::needless_range_loop)]
    fn simple_split(&self, row: u64, p: &Params) -> Option<(Bucket, Bucket, Vec<bool>, u64)> {
        let ncol = self.rows.len();
        let last = self
            .rows
            .iter()
            .map(|r| *r.last().unwrap())
            .max()
            .unwrap_or(0);
        if row < last {
            return None;
        }
        let mut left = self.clone();
        let mut right = Bucket::new(ncol);
        let mut dup = vec![false; ncol];
        for i in 0..ncol {
            let index = self.rows[i].len() - 1;
            let r = self.rows[i][index];
            self.copy_data(&mut right, i, 0, index, 0, p);
            dup[i] = true;
            if r == row {
                left.shift_left(i, index, 1, p);
                dup[i] = false;
            }
        }
        Some((left, right, dup, row))
    }

    /// `ISMBucket::split` (the simple split when this is the last bucket and
    /// the row is at its end, else halves of about equal length).
    #[allow(clippy::too_many_arguments, clippy::needless_range_loop)]
    fn split(
        &self,
        bstart: u64,
        bnrrow: u64,
        nrow: u64,
        c: usize,
        row: u64,
        leng_to_add: u32,
        p: &Params,
    ) -> Result<(Bucket, Bucket, Vec<bool>, u64)> {
        if bnrrow <= 1 {
            return err("IncrementalStMan bucket of one row cannot be split");
        }
        let ncol = self.rows.len();
        if bstart + bnrrow >= nrow
            && let Some(s) = self.simple_split(row, p)
        {
            return Ok(s);
        }
        let mut rows: Vec<u64> = std::iter::once(row)
            .chain(self.rows.iter().flatten().copied())
            .collect();
        rows.sort_unstable();
        rows.dedup();
        let nruniq = rows.len();
        if nruniq == 1 {
            return self
                .simple_split(row, p)
                .ok_or_else(|| MsError("IncrementalStMan simple split failed".into()));
        }
        let mut item = vec![vec![0u32; nruniq]; ncol];
        let mut cursor = vec![0usize; ncol];
        let mut index = 0;
        for (j, &r) in rows.iter().enumerate() {
            for i in 0..ncol {
                if cursor[i] < self.rows[i].len() && self.rows[i][cursor[i]] == r {
                    let leng = self.length(p.fixed[i], self.offs[i][cursor[i]], p.big);
                    item[i][j] = 8 + leng;
                    cursor[i] += 1;
                }
            }
            if row == r {
                index = j;
            }
        }
        if item[c][index] == 0 {
            item[c][index] = leng_to_add.wrapping_add(8);
        } else {
            item[c][index] = item[c][index].wrapping_add(leng_to_add);
        }
        let mut size = vec![0u32; ncol];
        let mut row_leng = vec![0u32; nruniq];
        let mut cum_leng = vec![0u32; nruniq];
        let mut tot = 0u32;
        for j in 0..nruniq {
            for i in 0..ncol {
                if item[i][j] != 0 {
                    size[i] = item[i][j];
                    tot = tot.wrapping_add(item[i][j]);
                }
                row_leng[j] = row_leng[j].wrapping_add(size[i]);
            }
            cum_leng[j] = tot;
        }
        let mut index = get_split(tot, &row_leng, &cum_leng);
        let mut left = Bucket::new(ncol);
        let mut right = Bucket::new(ncol);
        let mut dup = vec![false; ncol];
        let mut cursor = vec![0usize; ncol];
        for &r in &rows[..index] {
            for i in 0..ncol {
                if cursor[i] < self.rows[i].len() && self.rows[i][cursor[i]] == r {
                    self.copy_data(&mut left, i, r, cursor[i], cursor[i], p);
                    cursor[i] += 1;
                }
            }
        }
        let split_row = rows[index];
        for i in 0..ncol {
            if cursor[i] < self.rows[i].len() && self.rows[i][cursor[i]] == split_row {
                self.copy_data(&mut right, i, 0, cursor[i], 0, p);
                cursor[i] += 1;
                dup[i] = false;
            } else {
                self.copy_data(&mut right, i, 0, cursor[i] - 1, 0, p);
                dup[i] = true;
            }
        }
        let mut to = vec![1usize; ncol];
        index += 1;
        while index < nruniq {
            let r = rows[index];
            for i in 0..ncol {
                if cursor[i] < self.rows[i].len() && self.rows[i][cursor[i]] == r {
                    self.copy_data(&mut right, i, r - split_row, cursor[i], to[i], p);
                    cursor[i] += 1;
                    to[i] += 1;
                }
            }
            index += 1;
        }
        Ok((left, right, dup, split_row))
    }
}

/// `ISMBucket::getSplit` (unsigned arithmetic, as casacore's).
fn get_split(tot: u32, row_leng: &[u32], cum: &[u32]) -> usize {
    let nr = row_leng.len();
    if nr <= 2 {
        return 1;
    }
    let mut i = 1;
    let mut diff = 0u32;
    while cum[i - 1] < row_leng[i].wrapping_add(tot).wrapping_sub(cum[i]) && i < nr - 1 {
        diff = row_leng[i]
            .wrapping_add(tot)
            .wrapping_sub(cum[i])
            .wrapping_sub(cum[i - 1]);
        i += 1;
    }
    if diff > 0
        && cum[i - 1]
            .wrapping_add(cum[i])
            .wrapping_sub(row_leng[i])
            .wrapping_sub(tot)
            > diff
    {
        i -= 1;
    }
    i
}

// ---------------------------------------------------------------------------
// ISMIndex.

/// `ISMIndex`: the first row of every bucket (and the row count at the
/// end) and the bucket numbers.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Index {
    rows: Vec<u64>,
    bucket: Vec<u32>,
}

impl Index {
    fn new() -> Self {
        Index {
            rows: vec![0, 0],
            bucket: vec![0],
        }
    }

    fn read(c: &mut Cursor<'_>) -> Result<Self> {
        let object = c.start_expect("ISMIndex")?;
        let nused = c.u32()? as usize;
        let rows = if object.version > 1 {
            c.block_u64()?
        } else {
            c.block_u32()?.into_iter().map(u64::from).collect()
        };
        let bucket = c.block_u32()?;
        c.end(&object);
        if rows.len() != nused + 1 || bucket.len() != nused {
            return err("ISMIndex block lengths mismatch its use count");
        }
        Ok(Index { rows, bucket })
    }

    fn write(&self, w: &mut Writer) {
        let wide = *self.rows.last().unwrap() > MAXROWNR32;
        w.putstart("ISMIndex", if wide { 2 } else { 1 });
        w.u32(self.bucket.len() as u32);
        if wide {
            w.block_u64(&self.rows);
        } else {
            w.block_u32(&self.rows.iter().map(|&r| r as u32).collect::<Vec<_>>());
        }
        w.block_u32(&self.bucket);
        w.putend();
    }

    fn nused(&self) -> usize {
        self.bucket.len()
    }

    /// `getIndex`.
    fn index(&self, row: u64) -> usize {
        let (i, found) = brackets(&self.rows, row);
        if found { i } else { i - 1 }
    }

    /// `getBucketNr`: (bucket, its first row, its rows).
    fn bucket_nr(&self, row: u64) -> Result<(u32, u64, u64)> {
        let i = self.index(row);
        if i >= self.nused() {
            return err(format!("row {row} beyond the IncrementalStMan index"));
        }
        Ok((
            self.bucket[i],
            self.rows[i],
            self.rows[i + 1] - self.rows[i],
        ))
    }

    /// `nextBucketNr`.
    fn next(&self, cursor: &mut usize, start: &mut u64, nrrow: &mut u64) -> Option<u32> {
        if *cursor == 0 {
            if *start >= self.rows[self.nused()] {
                return None;
            }
            *cursor = self.index(*start);
        } else if *cursor >= self.nused() {
            return None;
        }
        *start = self.rows[*cursor];
        *nrrow = self.rows[*cursor + 1] - *start;
        let b = self.bucket[*cursor];
        *cursor += 1;
        Some(b)
    }

    fn add_bucket_nr(&mut self, row: u64, nr: u32) -> Result<()> {
        let nused = self.nused();
        let (i, found) = brackets(&self.rows[..nused], row);
        if found {
            return err("IncrementalStMan bucket start row is used twice");
        }
        self.rows.insert(i, row);
        self.bucket.insert(i, nr);
        Ok(())
    }

    fn add_rows(&mut self, n: u64) {
        *self.rows.last_mut().unwrap() += n;
    }

    /// `removeRow`: the bucket that became empty, if any.
    fn remove_row(&mut self, row: u64) -> Option<u32> {
        let i = self.index(row);
        for r in &mut self.rows[i + 1..] {
            *r -= 1;
        }
        if self.rows[i] == self.rows[i + 1] {
            let b = self.bucket[i];
            if self.nused() > 1 {
                self.rows.remove(i + 1);
                self.bucket.remove(i);
            }
            Some(b)
        } else {
            None
        }
    }
}

// ---------------------------------------------------------------------------
// The bucket cache.

struct Slot {
    bucket: u32,
    data: Option<Bucket>,
    dirty: bool,
    lru: u32,
}

/// casacore's `BucketCache` for one IncrementalStMan.
struct Cache {
    size: usize,
    slots: Vec<Slot>,
    slot_of: BTreeMap<u32, usize>,
    counter: u32,
    actual: usize,
    cur: u32,
    new: u32,
    nfree: u32,
    first_free: i32,
    /// `its_Buffer`: every bucket goes through it to and from the file.
    buffer: Vec<u8>,
}

impl Cache {
    fn new(size: usize, bucket_size: u32, nr: u32, nfree: u32, first_free: i32) -> Self {
        Cache {
            size: size.max(1),
            slots: Vec::new(),
            slot_of: BTreeMap::new(),
            counter: 0,
            actual: 0,
            cur: nr,
            new: nr,
            nfree,
            first_free,
            buffer: vec![0; bucket_size as usize],
        }
    }

    fn set_lru(&mut self) {
        if self.counter == u32::MAX {
            self.counter = 0;
            for s in &mut self.slots {
                s.lru = 0;
            }
        }
        self.counter += 1;
        self.slots[self.actual].lru = self.counter;
    }
}

// ---------------------------------------------------------------------------
// The manager.

/// An IncrementalStMan open for writing (or reading, `writable` false).
pub(crate) struct IsmW {
    path: PathBuf,
    file: File,
    big: bool,
    pub(crate) name: String,
    bucket_size: u32,
    pers_cache: u32,
    uniq: u32,
    index: Index,
    cache: Cache,
    pub(crate) cols: Vec<IsmCol>,
    fixed: Vec<u32>,
    nrow: u64,
    data_changed: bool,
    arrays: Option<ArrayFile>,
    array_path: PathBuf,
}

/// The header fields of an IncrementalStMan file.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct IsmHeader {
    pub big: bool,
    pub version: u32,
    pub bucket_size: u32,
    pub nbuckets: u32,
    pub pers_cache: u32,
    pub uniq: u32,
    pub nfree: u32,
    pub first_free: i32,
}

impl IsmHeader {
    pub(crate) fn parse(bytes: &[u8], table_big: bool) -> Result<(Self, usize)> {
        let mut h = Cursor::new(bytes, table_big);
        h.magic()?;
        let object = h.start_expect("IncrementalStMan")?;
        let big = if object.version >= 5 { h.bool()? } else { true };
        if big != table_big {
            return err("IncrementalStMan endian flag mismatches the table");
        }
        let bucket_size = h.u32()?;
        let nbuckets = h.u32()?;
        let pers_cache = h.u32()?;
        let uniq = h.u32()?;
        let (nfree, first_free) = if object.version > 1 {
            (h.u32()?, h.i32()?)
        } else {
            (0, -1)
        };
        h.end(&object);
        Ok((
            IsmHeader {
                big,
                version: object.version,
                bucket_size,
                nbuckets,
                pers_cache,
                uniq,
                nfree,
                first_free,
            },
            h.pos,
        ))
    }

    pub(crate) fn serialise(&self) -> Vec<u8> {
        let mut w = Writer::new(self.big);
        if self.big {
            w.putstart("IncrementalStMan", 4);
        } else {
            w.putstart("IncrementalStMan", 5);
            w.bool(false);
        }
        w.u32(self.bucket_size);
        w.u32(self.nbuckets);
        w.u32(self.pers_cache);
        w.u32(self.uniq);
        w.u32(self.nfree);
        w.i32(self.first_free);
        w.putend();
        w.buf
    }
}

/// The `table.dat` blob of an IncrementalStMan (`ISM` version 3).
pub(crate) fn ism_blob(name: &str) -> Vec<u8> {
    let mut blob = Writer::new(true);
    blob.putstart("ISM", 3);
    blob.string(name);
    blob.putend();
    blob.buf
}

/// The name in an `ISM` blob.
pub(crate) fn ism_blob_name(blob: &[u8]) -> Result<String> {
    let mut c = Cursor::new(blob, true);
    c.magic()?;
    let object = c.start_expect("ISM")?;
    let name = c.string()?;
    c.end(&object);
    Ok(name)
}

/// What a check of an IncrementalStMan file found: the header, index and
/// every bucket parse and serialise to their bytes.
pub(crate) fn check_file(path: &Path, ncol: usize, big: bool) -> Result<bool> {
    let bytes = std::fs::read(path)?;
    let (h, end) = IsmHeader::parse(&bytes, big)?;
    if h.serialise()[..] != bytes[..end] {
        return Ok(false);
    }
    let at = START as usize + h.nbuckets as usize * h.bucket_size as usize;
    let mut c = Cursor::new(&bytes[at..], big);
    c.magic()?;
    let index = Index::read(&mut c)?;
    let mut w = Writer::new(big);
    index.write(&mut w);
    if w.buf[..] != bytes[at..at + w.buf.len()] {
        return Ok(false);
    }
    let size = h.bucket_size as usize;
    for &b in &index.bucket {
        let from = START as usize + b as usize * size;
        let storage = &bytes[from..from + size];
        let bucket = Bucket::read(storage, ncol, big)?;
        let mut again = storage.to_vec();
        bucket.write(&mut again, big);
        if again != storage {
            return Ok(false);
        }
    }
    Ok(true)
}

impl IsmW {
    fn params(&self) -> Params<'_> {
        Params {
            big: self.big,
            size: self.bucket_size,
            fixed: &self.fixed,
        }
    }

    /// Open an existing IncrementalStMan (`open64`, then `makeCache`).
    pub(crate) fn open(
        dir: &Path,
        seq: u32,
        blob: &[u8],
        cols: Vec<IsmCol>,
        nrow: u64,
        big: bool,
        writable: bool,
    ) -> Result<Self> {
        let name = ism_blob_name(blob)?;
        let path = dir.join(format!("table.f{seq}"));
        let bytes =
            std::fs::read(&path).map_err(|e| MsError(format!("{}: {e}", path.display())))?;
        let (h, _) = IsmHeader::parse(&bytes, big)?;
        let at = START as usize + h.nbuckets as usize * h.bucket_size as usize;
        let mut c = Cursor::new(
            bytes
                .get(at..)
                .ok_or_else(|| MsError("IncrementalStMan index beyond the file".into()))?,
            big,
        );
        c.magic()?;
        let index = Index::read(&mut c)?;
        let file = OpenOptions::new()
            .read(true)
            .write(writable)
            .open(&path)
            .map_err(|e| MsError(format!("{}: {e}", path.display())))?;
        let fixed = cols.iter().map(IsmCol::fixed_length).collect();
        let mut cols = cols;
        for col in &mut cols {
            col.last_row_put = nrow;
        }
        let array_path = dir.join(format!("table.f{seq}i"));
        let any_indirect = cols.iter().any(|c| matches!(c.kind, IsmKind::Indirect(_)));
        let arrays = if any_indirect && writable {
            Some(ArrayFile::open_ext(&array_path, big, 1, false)?)
        } else {
            None
        };
        // The cache's constructor counts the buckets in the file (at most
        // the header's), then `resync` sets the header's counts.
        let cache = Cache::new(
            h.pers_cache as usize,
            h.bucket_size,
            h.nbuckets,
            h.nfree,
            h.first_free,
        );
        Ok(IsmW {
            path,
            file,
            big,
            name,
            bucket_size: h.bucket_size,
            pers_cache: h.pers_cache,
            uniq: h.uniq,
            index,
            cache,
            cols,
            fixed,
            nrow,
            data_changed: false,
            arrays,
            array_path,
        })
    }

    /// `ISMBase::init`'s bucket size when none is given: every column counts
    /// as variable (its fixed length is set later, in `ISMColumn::init`).
    pub(crate) fn default_bucket_size(cols: &[IsmCol]) -> u32 {
        let nrcol = cols.len() as u32;
        let header = 4 * (nrcol + 1);
        let (mut fixed, mut var) = (0u32, 0u32);
        for c in cols {
            let n = c.nelements();
            fixed += 8 + 4 * (n + 1);
            var += 32 * n;
        }
        let mut size = header + 100 * (fixed + var);
        if size < 32768 {
            size = 32768;
        } else if size > 327_680 {
            size = header + 10 * (fixed + var);
            if size > 327_680 {
                size = (header + 2 * (fixed + var)).max(327_680);
            }
        }
        size
    }

    /// A new IncrementalStMan with `nrow` rows (`ISMBase::create64`: `init`,
    /// `recreate`, `addRow64`).
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn create(
        dir: &Path,
        seq: u32,
        name: &str,
        cols: Vec<IsmCol>,
        nrow: u64,
        bucket_size: u32,
        pers_cache: u32,
        big: bool,
    ) -> Result<Self> {
        if cols.is_empty() {
            return err(format!("data manager {name} has no columns"));
        }
        if bucket_size >= 1 << 28 {
            return err("IncrementalStMan: bucketSize exceeds 28 bits");
        }
        let path = dir.join(format!("table.f{seq}"));
        let fixed = cols.iter().map(IsmCol::fixed_length).collect();
        let uniq = cols
            .iter()
            .filter(|c| matches!(c.kind, IsmKind::Indirect(_)))
            .count() as u32;
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(&path)
            .map_err(|e| MsError(format!("{}: {e}", path.display())))?;
        let mut s = IsmW {
            path,
            file,
            big,
            name: name.to_string(),
            bucket_size,
            pers_cache: pers_cache.max(1),
            uniq,
            index: Index::new(),
            cache: Cache::new(pers_cache.max(1) as usize, bucket_size, 1, 0, -1),
            cols,
            fixed,
            nrow: 0,
            data_changed: false,
            arrays: None,
            array_path: dir.join(format!("table.f{seq}i")),
        };
        s.recreate(false)?;
        s.add_rows(nrow)?;
        Ok(s)
    }

    /// `ISMBase::recreate`: a new file, index and cache (whose `resync`
    /// flushes an empty bucket 0), then each column's `doCreate` puts its
    /// undefined value at row 0 of bucket 0.
    fn recreate(&mut self, truncate: bool) -> Result<()> {
        if truncate {
            self.arrays = None;
            self.file = OpenOptions::new()
                .read(true)
                .write(true)
                .create(true)
                .truncate(true)
                .open(&self.path)
                .map_err(|e| MsError(format!("{}: {e}", self.path.display())))?;
        }
        self.index = Index::new();
        let ncol = self.cols.len();
        // `BucketCache` with no buckets in the file and one to be made;
        // `resync` clears it with a flush, which writes bucket 0.
        self.cache = Cache::new(self.pers_cache as usize, self.bucket_size, 1, 0, -1);
        self.cache.cur = 0;
        self.initialize_buckets(0)?;
        self.cache_flush_slots()?;
        self.cache.slots.clear();
        self.cache.slot_of.clear();
        self.cache.counter = 0;
        self.cache.actual = 0;
        self.cache.cur = 1;
        for c in 0..ncol {
            let slot = self.get_bucket_nr(0)?;
            let value = match &self.cols[c].kind {
                IsmKind::Values(n) => {
                    let n = *n;
                    match self.cols[c].dtype {
                        DataType::Bool => vec![0u8; n.div_ceil(8)],
                        dt => vec![0u8; n * dt.size()],
                    }
                }
                IsmKind::Strings(n) => encode_strings(&vec![String::new(); *n], self.big),
                IsmKind::Indirect(_) => {
                    if self.arrays.is_none() {
                        self.arrays =
                            Some(ArrayFile::open_ext(&self.array_path, self.big, 1, true)?);
                    }
                    vec![0u8; 8]
                }
            };
            let col = &mut self.cols[c];
            // A new manager's columns start at 0 (constructor); at a
            // recreate only `ISMIndColumn::doCreate` resets it.
            if !truncate || matches!(col.kind, IsmKind::Indirect(_)) {
                col.last_row_put = 0;
            }
            col.invalidate();
            self.slot_mut(slot).add(c, 0, 0, &value);
        }
        self.set_bucket_dirty();
        Ok(())
    }

    // -- the cache ---------------------------------------------------------

    fn slot_mut(&mut self, slot: usize) -> &mut Bucket {
        self.cache.slots[slot].data.as_mut().unwrap()
    }

    fn slot_ref(&self, slot: usize) -> &Bucket {
        self.cache.slots[slot].data.as_ref().unwrap()
    }

    fn set_bucket_dirty(&mut self) {
        let a = self.cache.actual;
        if a < self.cache.slots.len() {
            self.cache.slots[a].dirty = true;
        }
        self.data_changed = true;
    }

    fn bucket_offset(&self, n: u32) -> u64 {
        START + u64::from(n) * u64::from(self.bucket_size)
    }

    fn write_bucket(&mut self, slot: usize) -> Result<()> {
        let n = self.cache.slots[slot].bucket;
        let big = self.big;
        if let Some(b) = self.cache.slots[slot].data.as_ref() {
            b.write(&mut self.cache.buffer, big);
        }
        let at = self.bucket_offset(n);
        write_at(&mut self.file, at, &self.cache.buffer)?;
        self.cache.slots[slot].dirty = false;
        Ok(())
    }

    fn read_bucket(&mut self, slot: usize) -> Result<()> {
        let n = self.cache.slots[slot].bucket;
        let at = self.bucket_offset(n);
        let size = self.bucket_size as usize;
        let len = self.file.metadata()?.len();
        let avail = len.saturating_sub(at).min(size as u64) as usize;
        if avail < size {
            return err(format!(
                "{}: IncrementalStMan bucket {n} is truncated",
                self.path.display()
            ));
        }
        let bytes = read_at(&mut self.file, at, size)?;
        self.cache.buffer.copy_from_slice(&bytes);
        let b = Bucket::read(&self.cache.buffer, self.cols.len(), self.big)?;
        self.cache.slots[slot].data = Some(b);
        Ok(())
    }

    /// `BucketCache::getSlot`.
    fn get_slot(&mut self, n: u32) -> Result<()> {
        if self.cache.slots.len() < self.cache.size {
            self.cache.actual = self.cache.slots.len();
            self.cache.slots.push(Slot {
                bucket: n,
                data: None,
                dirty: false,
                lru: 0,
            });
        } else {
            let mut a = 0;
            let mut least = self.cache.slots[0].lru;
            for (i, s) in self.cache.slots.iter().enumerate().skip(1) {
                if s.lru < least {
                    least = s.lru;
                    a = i;
                }
            }
            self.cache.actual = a;
            if self.cache.slots[a].dirty {
                self.write_bucket(a)?;
            }
            if self.cache.slots[a].data.take().is_some() {
                let old = self.cache.slots[a].bucket;
                self.cache.slot_of.remove(&old);
            }
        }
        self.cache.set_lru();
        let a = self.cache.actual;
        self.cache.slots[a].bucket = n;
        self.cache.slot_of.insert(n, a);
        Ok(())
    }

    /// `BucketCache::initializeBuckets`.
    fn initialize_buckets(&mut self, n: u32) -> Result<()> {
        while self.cache.cur <= n {
            let b = self.cache.cur;
            self.get_slot(b)?;
            let a = self.cache.actual;
            self.cache.slots[a].data = Some(Bucket::new(self.cols.len()));
            self.cache.slots[a].dirty = true;
            self.cache.cur += 1;
        }
        Ok(())
    }

    /// `BucketCache::getBucket`: the slot holding bucket `n`.
    fn get_bucket_nr(&mut self, n: u32) -> Result<usize> {
        if n >= self.cache.new {
            return err(format!("IncrementalStMan bucket {n} does not exist"));
        }
        if let Some(&slot) = self.cache.slot_of.get(&n) {
            self.cache.actual = slot;
            self.cache.set_lru();
            return Ok(slot);
        }
        if n < self.cache.cur {
            self.get_slot(n)?;
            let a = self.cache.actual;
            self.read_bucket(a)?;
        } else {
            self.initialize_buckets(n)?;
        }
        Ok(self.cache.actual)
    }

    /// `ISMBase::getBucket`: (slot, first row, rows) of the bucket of `row`.
    fn get_bucket(&mut self, row: u64) -> Result<(usize, u64, u64)> {
        let (n, start, nrrow) = self.index.bucket_nr(row)?;
        Ok((self.get_bucket_nr(n)?, start, nrrow))
    }

    /// `ISMBase::nextBucket`.
    fn next_bucket(
        &mut self,
        cursor: &mut usize,
        start: &mut u64,
        nrrow: &mut u64,
    ) -> Result<Option<usize>> {
        match self.index.next(cursor, start, nrrow) {
            Some(n) => Ok(Some(self.get_bucket_nr(n)?)),
            None => Ok(None),
        }
    }

    /// `BucketCache::addBucket` and `ISMIndex::addBucketNr`.
    fn add_bucket(&mut self, row: u64, b: Bucket) -> Result<()> {
        let n = if self.cache.first_free >= 0 {
            let n = self.cache.first_free as u32;
            let at = self.bucket_offset(n);
            let head = read_at(&mut self.file, at, 4)?;
            self.cache.buffer[..4].copy_from_slice(&head);
            self.cache.first_free = i32::from_be_bytes(head.try_into().unwrap());
            self.cache.nfree -= 1;
            n
        } else {
            if self.cache.cur < self.cache.new {
                let last = self.cache.new - 1;
                self.initialize_buckets(last)?;
            }
            self.cache.new += 1;
            self.cache.cur += 1;
            self.cache.new - 1
        };
        self.get_slot(n)?;
        let a = self.cache.actual;
        self.cache.slots[a].data = Some(b);
        self.cache.slots[a].dirty = true;
        self.index.add_bucket_nr(row, n)
    }

    /// `BucketCache::removeBucket` of the actual slot.
    fn remove_bucket(&mut self) -> Result<()> {
        let a = self.cache.actual;
        let n = self.cache.slots[a].bucket;
        self.cache.buffer[..4].copy_from_slice(&self.cache.first_free.to_be_bytes());
        let at = self.bucket_offset(n);
        write_at(&mut self.file, at, &self.cache.buffer)?;
        self.cache.slots[a].dirty = false;
        self.cache.first_free = n as i32;
        self.cache.nfree += 1;
        self.cache.slots[a].data = None;
        self.cache.slot_of.remove(&n);
        self.cache.slots[a].lru = 0;
        self.cache.actual = 0;
        Ok(())
    }

    fn cache_flush_slots(&mut self) -> Result<()> {
        for i in 0..self.cache.slots.len() {
            if self.cache.slots[i].dirty {
                self.write_bucket(i)?;
            }
        }
        Ok(())
    }

    /// `BucketCache::flush`.
    fn cache_flush(&mut self) -> Result<()> {
        if self.cache.new > 0 {
            let last = self.cache.new - 1;
            self.initialize_buckets(last)?;
        }
        self.cache_flush_slots()
    }

    // -- reference counts (`ISMIndColumn::handleCopy/handleRemove`) ---------

    fn change_ref(&mut self, c: usize, value: &[u8], delta: i32) -> Result<()> {
        if !matches!(self.cols[c].kind, IsmKind::Indirect(_)) {
            return Ok(());
        }
        let offset = read_order_u64(value, self.big);
        if offset == 0 {
            return Ok(());
        }
        let arrays = self
            .arrays
            .as_mut()
            .ok_or_else(|| MsError("IncrementalStMan array file is not open".into()))?;
        let n = arrays.ref_count(offset)?;
        arrays.put_ref_count(offset, (n as i32 + delta) as u32)
    }

    fn handle_split(&mut self, right: &Bucket, dup: &[bool]) -> Result<()> {
        for (i, &d) in dup.iter().enumerate() {
            if d {
                let v = right
                    .value(i, right.offset_index(i, 0), &self.params())
                    .to_vec();
                self.change_ref(i, &v, 1)?;
            }
        }
        Ok(())
    }

    // -- ISMColumn writes ---------------------------------------------------

    /// `ISMColumn::replaceData` on bucket `b`; a split's right bucket is
    /// returned with its first row (to be added by the caller).
    #[allow(clippy::too_many_arguments)]
    fn replace_data(
        &mut self,
        b: &mut Bucket,
        bstart: u64,
        bnrrow: u64,
        brow: u64,
        c: usize,
        idx: usize,
        data: &[u8],
        can_split: bool,
    ) -> Result<Option<(u64, Bucket)>> {
        let big = self.big;
        let old = b.length(self.fixed[c], b.offs[c][idx], big);
        if b.can_replace(data.len() as u32, old, &self.params()) {
            let v = b.value(c, idx, &self.params()).to_vec();
            self.change_ref(c, &v, -1)?;
            b.replace(c, idx, data, old, big);
            return Ok(None);
        }
        if !can_split {
            return err("IncrementalStMan value does not fit its bucket");
        }
        let (left, mut right, dup, split) = b.split(
            bstart,
            bnrrow,
            self.nrow,
            c,
            brow,
            (data.len() as u32).wrapping_sub(old),
            &self.params(),
        )?;
        self.handle_split(&right, &dup)?;
        *b = left;
        if brow >= split {
            let row = brow - split;
            let i = right.offset_index(c, row);
            let v = right.value(c, i, &self.params()).to_vec();
            self.change_ref(c, &v, -1)?;
            right.replace(c, i, data, old, big);
        } else {
            let i = b.offset_index(c, brow);
            let v = b.value(c, i, &self.params()).to_vec();
            self.change_ref(c, &v, -1)?;
            b.replace(c, i, data, old, big);
        }
        Ok(Some((split + bstart, right)))
    }

    /// `ISMColumn::addData` on bucket `b`.
    #[allow(clippy::too_many_arguments)]
    fn add_data(
        &mut self,
        b: &mut Bucket,
        bstart: u64,
        bnrrow: u64,
        brow: u64,
        inx: usize,
        c: usize,
        data: &[u8],
        after_last: bool,
        can_split: bool,
    ) -> Result<Option<(u64, Bucket)>> {
        if b.can_add(data.len() as u32, &self.params()) {
            b.add(c, brow, inx, data);
            return Ok(None);
        }
        if !can_split {
            return err("IncrementalStMan value does not fit its bucket");
        }
        let (left, mut right, dup, split) = b.split(
            bstart,
            bnrrow,
            self.nrow,
            c,
            brow,
            data.len() as u32,
            &self.params(),
        )?;
        self.handle_split(&right, &dup)?;
        *b = left;
        if brow >= split {
            self.put_data(
                &mut right,
                bstart + split,
                bnrrow - split,
                brow - split,
                c,
                data,
                after_last,
            )?;
        } else {
            self.put_data(b, bstart, split, brow, c, data, after_last)?;
        }
        Ok(Some((split + bstart, right)))
    }

    /// `ISMColumn::putData` (never splits).
    #[allow(clippy::too_many_arguments)]
    fn put_data(
        &mut self,
        b: &mut Bucket,
        bstart: u64,
        bnrrow: u64,
        brow: u64,
        c: usize,
        data: &[u8],
        after_last: bool,
    ) -> Result<()> {
        let (inx, start, end, _) = b.interval(c, brow, 0);
        let r = if (after_last && brow == 0) || start == end {
            self.replace_data(b, bstart, bnrrow, brow, c, inx, data, false)?
        } else {
            self.add_data(b, bstart, bnrrow, brow, inx, c, data, after_last, false)?
        };
        debug_assert!(r.is_none());
        Ok(())
    }

    /// Run a split-capable operation on the bucket in `slot`, then add the
    /// split's right bucket, as casacore does at the end of the operation.
    fn on_slot<F>(&mut self, slot: usize, f: F) -> Result<()>
    where
        F: FnOnce(&mut Self, &mut Bucket) -> Result<Option<(u64, Bucket)>>,
    {
        let mut b = self.cache.slots[slot]
            .data
            .take()
            .ok_or_else(|| MsError("IncrementalStMan cache slot is empty".into()))?;
        let r = f(self, &mut b);
        self.cache.slots[slot].data = Some(b);
        if let Some((row, right)) = r? {
            self.add_bucket(row, right)?;
        }
        Ok(())
    }

    /// `ISMColumn::putFromRow`: the value starts every later bucket.
    fn put_from_row(&mut self, c: usize, row: u64, data: &[u8]) -> Result<()> {
        let mut cursor = 0;
        let mut start = row;
        let mut nrrow = 0;
        self.next_bucket(&mut cursor, &mut start, &mut nrrow)?;
        while let Some(slot) = self.next_bucket(&mut cursor, &mut start, &mut nrrow)? {
            self.set_bucket_dirty();
            let (bstart, bn) = (start, nrrow);
            self.on_slot(slot, |s, b| {
                let idx = b.offset_index(c, 0);
                s.replace_data(b, bstart, bn, 0, c, idx, data, true)
            })?;
            self.change_ref(c, data, 1)?;
        }
        Ok(())
    }

    /// `ISMColumn::putValue` of a stored value at `row`.
    pub(crate) fn put_value(&mut self, c: usize, row: u64, value: &[u8]) -> Result<()> {
        let (slot, bstart, bnrrow) = self.get_bucket(row)?;
        let brow = row - bstart;
        let (inx, stint, endint, offset) = self.slot_ref(slot).interval(c, brow, bnrrow);
        let mut after_last = false;
        if row >= self.cols[c].last_row_put {
            after_last = true;
            self.cols[c].last_row_put = row + 1;
        }
        self.cols[c].invalidate();
        let big = self.big;
        let current = {
            let b = self.slot_ref(slot);
            let n = b.length(self.fixed[c], offset, big);
            b.data[offset as usize..(offset + n) as usize].to_vec()
        };
        if values_equal(&self.cols[c], value, &current, big) {
            return Ok(());
        }
        self.set_bucket_dirty();
        let mut equal_prev = false;
        let mut equal_next = false;
        let mut next_inx = inx;
        if brow == stint {
            next_inx += 1;
            if brow > 0 {
                let prev = self
                    .slot_ref(slot)
                    .value(c, inx - 1, &self.params())
                    .to_vec();
                equal_prev = values_equal(&self.cols[c], value, &prev, big);
            }
        }
        if brow == endint && brow < bnrrow - 1 {
            let next = self
                .slot_ref(slot)
                .value(c, next_inx, &self.params())
                .to_vec();
            equal_next = values_equal(&self.cols[c], value, &next, big);
        }
        let p_fixed = self.fixed.clone();
        let params = |big| Params {
            big,
            size: 0,
            fixed: &p_fixed,
        };
        if after_last {
            if brow == 0 {
                self.on_slot(slot, |s, b| {
                    s.replace_data(b, bstart, bnrrow, brow, c, inx, value, true)
                })?;
            } else if equal_prev {
                let p = params(big);
                self.slot_mut(slot).shift_left(c, inx, 1, &p);
            } else {
                self.on_slot(slot, |s, b| {
                    s.add_data(b, bstart, bnrrow, brow, inx, c, value, true, true)
                })?;
            }
            return self.put_from_row(c, row, value);
        }
        if equal_prev && equal_next {
            let p = params(big);
            self.slot_mut(slot).shift_left(c, inx, 2, &p);
            return Ok(());
        }
        let single = stint == endint;
        if equal_prev {
            if single {
                let p = params(big);
                self.slot_mut(slot).shift_left(c, inx, 1, &p);
            } else {
                self.slot_mut(slot).rows[c][inx] += 1;
            }
            return Ok(());
        }
        if equal_next {
            if single {
                let p = params(big);
                self.slot_mut(slot).shift_left(c, inx, 1, &p);
            }
            self.slot_mut(slot).rows[c][inx] -= 1;
            return Ok(());
        }
        if single {
            return self.on_slot(slot, |s, b| {
                s.replace_data(b, bstart, bnrrow, brow, c, inx, value, true)
            });
        }
        if brow > stint && brow < endint {
            self.on_slot(slot, |s, b| {
                s.add_data(b, bstart, bnrrow, brow + 1, inx, c, &current, false, true)
            })?;
            self.change_ref(c, &current, 1)?;
            return self.put_value(c, row, value);
        }
        self.on_slot(slot, |s, b| {
            s.add_data(b, bstart, bnrrow, brow, inx, c, value, false, true)
        })
    }

    /// `ISMColumn::getValue`: the stored value at `row` (sets the rows for
    /// which it is valid).
    fn get_value(&mut self, c: usize, row: u64) -> Result<Vec<u8>> {
        let (slot, bstart, bnrrow) = self.get_bucket(row)?;
        let brow = row - bstart;
        let (_, stint, endint, offset) = self.slot_ref(slot).interval(c, brow, bnrrow);
        let b = self.slot_ref(slot);
        let n = b.length(self.fixed[c], offset, self.big);
        let v = b.data[offset as usize..(offset + n) as usize].to_vec();
        self.cols[c].start_row = bstart + stint;
        self.cols[c].end_row = bstart + endint;
        Ok(v)
    }

    // -- ISMIndColumn ------------------------------------------------------

    fn arrays(&mut self) -> Result<&mut ArrayFile> {
        self.arrays
            .as_mut()
            .ok_or_else(|| MsError("IncrementalStMan array file is not open".into()))
    }

    /// `getArrayPtr`: whether `row` has an array (re-read when the value
    /// read last is not valid for the row).
    fn get_array_ptr(&mut self, c: usize, row: u64) -> Result<bool> {
        if !self.cols[c].valid(row) {
            let v = self.get_value(c, row)?;
            let offset = read_order_u64(&v, self.big);
            if offset != 0 {
                self.cols[c].ind = IndArray {
                    offset,
                    arr_offset: 0,
                    shape: Vec::new(),
                };
                self.cols[c].found = true;
            } else {
                self.cols[c].found = false;
            }
        }
        Ok(self.cols[c].found)
    }

    /// `StIndArray::getShape`.
    fn ind_get_shape(&mut self, c: usize) -> Result<()> {
        if self.cols[c].ind.arr_offset == 0 {
            let offset = self.cols[c].ind.offset;
            let (shape, n) = self.arrays()?.get_shape(offset)?;
            self.cols[c].ind.shape = shape;
            self.cols[c].ind.arr_offset = n;
        }
        Ok(())
    }

    /// `StIndArray::setShape`: a new array unless the shape is known and
    /// equal.
    fn ind_set_shape(&mut self, c: usize, shape: &[i64]) -> Result<()> {
        if self.cols[c].ind.arr_offset != 0 && self.cols[c].ind.shape == shape {
            return Ok(());
        }
        let dtype = self.cols[c].dtype;
        let arrays = self.arrays()?;
        let offset = arrays.put_res(shape, dtype)?;
        let n = header_length(arrays.version, shape);
        let ind = &mut self.cols[c].ind;
        ind.shape = shape.to_vec();
        ind.offset = offset;
        ind.arr_offset = n;
        Ok(())
    }

    /// `ISMIndColumn::putArrayPtr` (without copying data).
    fn put_array_ptr(&mut self, c: usize, row: u64, shape: &[i64]) -> Result<()> {
        let found = self.get_array_ptr(c, row)?;
        if found && row + 1 == self.cols[c].last_row_put {
            self.ind_get_shape(c)?;
            if self.cols[c].ind.shape == shape {
                return Ok(());
            }
        }
        if found && self.cols[c].start_row == self.cols[c].end_row {
            let offset = self.cols[c].ind.offset;
            if self.arrays()?.ref_count(offset)? <= 1 {
                self.ind_set_shape(c, shape)?;
                let v = order_u64(self.cols[c].ind.offset, self.big).to_vec();
                return self.put_value(c, row, &v);
            }
        }
        self.cols[c].ind = IndArray::default();
        self.ind_set_shape(c, shape)?;
        let v = order_u64(self.cols[c].ind.offset, self.big).to_vec();
        self.put_value(c, row, &v)
    }

    /// `ISMIndColumn::setShape`.
    fn ind_shape_for(&mut self, c: usize, row: u64, shape: &[i64]) -> Result<()> {
        let found = self.get_array_ptr(c, row)?;
        if found {
            self.ind_get_shape(c)?;
        }
        if !found || self.cols[c].ind.shape != shape {
            self.put_array_ptr(c, row, shape)?;
        }
        Ok(())
    }

    /// `ISMIndColumn::putArrayV`: `putShape`, then the values.
    fn ind_put_array(&mut self, c: usize, row: u64, shape: &[i64], data: &[u8]) -> Result<()> {
        self.put_array_ptr(c, row, shape)?;
        let at = self.cols[c].ind.offset + self.cols[c].ind.arr_offset;
        let dtype = self.cols[c].dtype;
        self.arrays()?.put_values(at, dtype, data)
    }

    // -- the column operations of the writer --------------------------------

    /// Write `count` rows of a numeric or Bool column from native bytes
    /// (cells of `shape`), as `putColumn`/`put` do: values row by row; an
    /// indirect variable-shape column first sets every row's shape.
    pub(crate) fn put(
        &mut self,
        c: usize,
        start: u64,
        count: u64,
        shape: &[i64],
        data: &[u8],
        cell: bool,
    ) -> Result<()> {
        let col = self.cols[c].clone();
        let row_bytes = product(shape) * col.dtype.native_size();
        match &col.kind {
            IsmKind::Values(n) => {
                if product(shape).max(1) != *n {
                    return err(format!(
                        "{}: cell shape {shape:?} does not fit the column",
                        col.name
                    ));
                }
                let rb = n * col.dtype.native_size();
                for i in 0..count {
                    let src = &data[i as usize * rb..(i as usize + 1) * rb];
                    let v = encode_values(col.dtype, src, self.big);
                    self.put_value(c, start + i, &v)?;
                }
            }
            IsmKind::Strings(_) => {
                return err(format!("{}: use put_strings for string columns", col.name));
            }
            IsmKind::Indirect(fixed) => {
                if let Some(f) = fixed
                    && f.as_slice() != shape
                {
                    return err(format!(
                        "{}: the column has the fixed shape {f:?}, not {shape:?}",
                        col.name
                    ));
                }
                if cell && count == 1 {
                    // `ArrayColumn::put` (acbPut).
                    let row = start;
                    if !self.get_array_ptr(c, row)? {
                        self.ind_shape_for(c, row, shape)?;
                    } else {
                        self.ind_get_shape(c)?;
                        if self.cols[c].ind.shape != shape {
                            self.ind_shape_for(c, row, shape)?;
                        }
                    }
                    return self.ind_put_array(c, row, shape, data);
                }
                if fixed.is_none() {
                    for i in 0..count {
                        self.ind_shape_for(c, start + i, shape)?;
                    }
                }
                for i in 0..count {
                    let src = &data[i as usize * row_bytes..(i as usize + 1) * row_bytes];
                    self.ind_put_array(c, start + i, shape, src)?;
                }
            }
        }
        Ok(())
    }

    /// Write strings: a scalar string column (one string per row) or a
    /// Direct string array (`per_row` strings per row).
    pub(crate) fn put_strings(&mut self, c: usize, start: u64, strings: &[String]) -> Result<()> {
        let n = match self.cols[c].kind {
            IsmKind::Strings(n) => n.max(1),
            _ => return err(format!("{} is not a string column", self.cols[c].name)),
        };
        if !strings.len().is_multiple_of(n) {
            return err("string count mismatches the cell shape");
        }
        for (i, cell) in strings.chunks(n).enumerate() {
            let v = encode_strings(cell, self.big);
            self.put_value(c, start + i as u64, &v)?;
        }
        Ok(())
    }

    /// `ISMBase::addRow64`.
    pub(crate) fn add_rows(&mut self, n: u64) -> Result<()> {
        self.index.add_rows(n);
        let old = self.nrow;
        for c in 0..self.cols.len() {
            if let IsmKind::Indirect(Some(shape)) = self.cols[c].kind.clone()
                && old == 0
            {
                self.put_array_ptr(c, 0, &shape)?;
            }
        }
        self.nrow += n;
        self.data_changed = true;
        Ok(())
    }

    /// `ISMColumn::remove` of a row of bucket `slot`.
    fn remove_in(
        &mut self,
        c: usize,
        slot: usize,
        brow: u64,
        bnrrow: u64,
        new_nrow: u64,
    ) -> Result<()> {
        let (mut inx, stint, endint, offset) = self.slot_ref(slot).interval(c, brow, bnrrow);
        self.cols[c].invalidate();
        self.set_bucket_dirty();
        if stint == endint {
            let v = {
                let b = self.slot_ref(slot);
                let n = b.length(self.fixed[c], offset, self.big);
                b.data[offset as usize..(offset + n) as usize].to_vec()
            };
            self.change_ref(c, &v, -1)?;
            let fixed = self.fixed.clone();
            let p = Params {
                big: self.big,
                size: 0,
                fixed: &fixed,
            };
            self.slot_mut(slot).shift_left(c, inx, 1, &p);
        } else if brow == stint {
            inx += 1;
        }
        let b = self.slot_mut(slot);
        for r in &mut b.rows[c][inx..] {
            *r -= 1;
        }
        if self.cols[c].last_row_put > new_nrow {
            self.cols[c].last_row_put = new_nrow + 1;
        }
        Ok(())
    }

    /// `ISMBase::removeRow64`.
    pub(crate) fn remove_row(&mut self, row: u64) -> Result<()> {
        let (slot, bstart, bnrrow) = self.get_bucket(row)?;
        let brow = row - bstart;
        let new_nrow = self.nrow - 1;
        for c in 0..self.cols.len() {
            self.remove_in(c, slot, brow, bnrrow, new_nrow)?;
        }
        let empty = self.index.remove_row(row);
        self.nrow -= 1;
        if self.nrow == 0 {
            // The old array file is written as casacore deletes it, then
            // created anew.
            if let Some(mut a) = self.arrays.take() {
                a.flush_changed()?;
            }
            self.recreate(true)?;
        } else if let Some(b) = empty {
            self.get_bucket_nr(b)?;
            self.remove_bucket()?;
        }
        self.data_changed = true;
        Ok(())
    }

    /// `ISMBase::writeIndex`.
    fn write_index(&mut self) -> Result<()> {
        let h = IsmHeader {
            big: self.big,
            version: if self.big { 4 } else { 5 },
            bucket_size: self.bucket_size,
            nbuckets: self.cache.new,
            pers_cache: self.pers_cache,
            uniq: self.uniq,
            nfree: self.cache.nfree,
            first_free: self.cache.first_free,
        };
        write_at(&mut self.file, 0, &h.serialise())?;
        let mut w = Writer::new(self.big);
        self.index.write(&mut w);
        let at = self.bucket_offset(self.cache.new);
        write_at(&mut self.file, at, &w.buf)
    }

    /// `ISMBase::flush`: the columns (the array file), the cache, then the
    /// header and index when the data changed; whether anything changed.
    pub(crate) fn flush(&mut self) -> Result<bool> {
        let mut changed = false;
        if let Some(a) = self.arrays.as_mut()
            && a.flush_changed()?
        {
            changed = true;
        }
        self.cache_flush()?;
        if self.data_changed {
            self.write_index()?;
            changed = true;
            self.data_changed = false;
        }
        Ok(changed)
    }

    // -- reads ----------------------------------------------------------------

    /// Whether `row` has a value (an indirect column may have none).
    pub(crate) fn is_defined(&mut self, c: usize, row: u64) -> Result<bool> {
        if matches!(self.cols[c].kind, IsmKind::Indirect(_)) {
            let v = self.peek(c, row)?;
            return Ok(read_order_u64(&v, self.big) != 0);
        }
        Ok(true)
    }

    /// The stored value at `row`, read from the file (no cache effects; for
    /// a manager opened only to read).
    fn peek(&mut self, c: usize, row: u64) -> Result<Vec<u8>> {
        let (n, bstart, bnrrow) = self.index.bucket_nr(row)?;
        let at = self.bucket_offset(n);
        let size = self.bucket_size as usize;
        let storage = read_at(&mut self.file, at, size)?;
        let b = Bucket::read(&storage, self.cols.len(), self.big)?;
        let (_, _, _, offset) = b.interval(c, row - bstart, bnrrow);
        let len = b.length(self.fixed[c], offset, self.big);
        Ok(b.data[offset as usize..(offset + len) as usize].to_vec())
    }

    /// The distinct array records the rows of indirect columns reference:
    /// (offset, element bits), every bucket read once from the file.
    pub(crate) fn array_offsets(&mut self) -> Result<Vec<(u64, u32)>> {
        let mut seen = BTreeMap::new();
        let size = self.bucket_size as usize;
        for &n in &self.index.bucket.clone() {
            let at = self.bucket_offset(n);
            let storage = read_at(&mut self.file, at, size)?;
            let b = Bucket::read(&storage, self.cols.len(), self.big)?;
            for (c, col) in self.cols.iter().enumerate() {
                if !matches!(col.kind, IsmKind::Indirect(_)) {
                    continue;
                }
                let bits = match col.dtype {
                    DataType::Bool => 1,
                    dt => 8 * dt.size() as u32,
                };
                for &o in &b.offs[c] {
                    let offset = read_order_u64(&b.data[o as usize..], self.big);
                    if offset != 0 {
                        seen.insert(offset, bits);
                    }
                }
            }
        }
        Ok(seen.into_iter().collect())
    }

    /// One cell, read from the file.
    pub(crate) fn read_cell(&mut self, c: usize, row: u64) -> Result<Cell> {
        let col = self.cols[c].clone();
        let v = self.peek(c, row)?;
        match &col.kind {
            IsmKind::Values(n) => {
                let native = if col.dtype == DataType::Bool {
                    get_bits(&v, 0, *n)
                } else {
                    to_order(col.dtype, &v, self.big)
                };
                Ok(Cell::Values(col.cell.clone().unwrap_or_default(), native))
            }
            IsmKind::Strings(n) => {
                let strings = decode_strings(&v, *n, self.big)?;
                Ok(Cell::Strings(col.cell.clone().unwrap_or_default(), strings))
            }
            IsmKind::Indirect(_) => {
                let offset = read_order_u64(&v, self.big);
                if offset == 0 {
                    return Ok(Cell::Undefined);
                }
                let mut a = ArrayFile::open_ext(&self.array_path, self.big, 1, false)?;
                let (shape, n) = a.get_shape(offset)?;
                let values = a.read_values(offset + n, col.dtype, product(&shape))?;
                Ok(Cell::Values(shape, values))
            }
        }
    }
}

/// The header length of an array record of `shape` in a file of `version`
/// (reference count, ndim, dimensions).
fn header_length(version: u32, shape: &[i64]) -> u64 {
    (if version > 0 { 4 } else { 0 }) + 4 + 4 * shape.len() as u64
}
