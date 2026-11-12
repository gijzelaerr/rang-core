// SPDX-License-Identifier: GPL-3.0-or-later
//! Writes into existing casacore tables (research/e3-table-writer.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! In-place `putcol` for StandardStMan (scalars, Direct and indirect
//! arrays, strings), TiledColumnStMan and TiledShapeStMan (rows with a
//! hypercube), table and column keywords, `addcols` into an existing
//! StandardStMan or as a new data manager, and the `table.lock` write lock
//! and sync record, all laid out as casacore 3.8.1 lays them out. The
//! format was read in the casacore sources listed in the research file;
//! nothing is copied from casacore (LGPL-2.1-or-later).

use std::collections::BTreeMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::aipsio::{KeywordValue, Writer, read_int_map};
use crate::ms::{BUCKET_START, ColumnData, Cursor, DataType, MsError, Result};
use crate::ms_desc::{ColBinding, ColDesc, TableDat};

fn err<T>(message: impl Into<String>) -> Result<T> {
    Err(MsError(message.into()))
}

pub(crate) fn read_at(file: &mut File, offset: u64, n: usize) -> Result<Vec<u8>> {
    let mut out = vec![0u8; n];
    file.seek(SeekFrom::Start(offset))?;
    file.read_exact(&mut out)
        .map_err(|e| MsError(format!("read of {n} bytes at {offset} failed: {e}")))?;
    Ok(out)
}

pub(crate) fn write_at(file: &mut File, offset: u64, bytes: &[u8]) -> Result<()> {
    file.seek(SeekFrom::Start(offset))?;
    file.write_all(bytes).map_err(|e| {
        MsError(format!(
            "write of {} bytes at {offset} failed: {e}",
            bytes.len()
        ))
    })?;
    Ok(())
}

fn be_i32(bytes: &[u8], at: usize) -> i32 {
    i32::from_be_bytes(bytes[at..at + 4].try_into().unwrap())
}

// ---------------------------------------------------------------------------
// The table.lock file: casacore's fcntl lock and the sync record.

/// Bytes of the lock request list before the sync record (`LockFile.cc`).
pub const LOCK_REQUESTS: usize = (1 + 2 * 32) * 4;

#[cfg(target_os = "linux")]
mod fcntl {
    use std::os::fd::AsRawFd;

    #[repr(C)]
    struct Flock {
        l_type: i16,
        l_whence: i16,
        l_start: i64,
        l_len: i64,
        l_pid: i32,
    }

    unsafe extern "C" {
        fn fcntl(fd: i32, cmd: i32, ...) -> i32;
    }

    const F_SETLK: i32 = 6;
    const F_RDLCK: i16 = 0;
    const F_WRLCK: i16 = 1;
    const F_UNLCK: i16 = 2;

    fn set(file: &std::fs::File, kind: i16, start: i64) -> bool {
        let lock = Flock {
            l_type: kind,
            l_whence: 0,
            l_start: start,
            l_len: 1,
            l_pid: 0,
        };
        // SAFETY: a valid descriptor and a valid `struct flock` (x86-64 and
        // aarch64 Linux layout) for F_SETLK, which does not block.
        unsafe { fcntl(file.as_raw_fd(), F_SETLK, &lock as *const Flock) != -1 }
    }

    pub fn write_lock(file: &std::fs::File, start: i64) -> bool {
        set(file, F_WRLCK, start)
    }

    pub fn read_lock(file: &std::fs::File, start: i64) -> bool {
        set(file, F_RDLCK, start)
    }

    pub fn unlock(file: &std::fs::File, start: i64) {
        set(file, F_UNLCK, start);
    }
}

#[cfg(not(target_os = "linux"))]
mod fcntl {
    // No inter-process lock on this platform (research/e3-table-writer.md).
    pub fn write_lock(_: &std::fs::File, _: i64) -> bool {
        true
    }
    pub fn read_lock(_: &std::fs::File, _: i64) -> bool {
        true
    }
    pub fn unlock(_: &std::fs::File, _: i64) {}
}

/// The sync record of `table.lock` (`TableSyncData`).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct SyncRecord {
    pub nrows: u64,
    pub ncolumns: i32,
    pub modify: u32,
    pub table_change: u32,
    pub dm_change: Vec<u32>,
}

impl SyncRecord {
    /// Parse the bytes after the request list; None when there is no record.
    pub fn parse(lock: &[u8]) -> Result<Option<Self>> {
        if lock.len() < LOCK_REQUESTS + 4 {
            return Ok(None);
        }
        let length = be_i32(lock, LOCK_REQUESTS) as u32 as usize;
        if length == 0 {
            return Ok(None);
        }
        let info = lock
            .get(LOCK_REQUESTS + 4..LOCK_REQUESTS + 4 + length)
            .ok_or_else(|| MsError("truncated table.lock sync record".into()))?;
        let mut c = Cursor::new(info, true);
        c.magic()?;
        let sync = c.start_expect("sync")?;
        let nrows = if sync.version == 1 {
            u64::from(c.u32()?)
        } else {
            c.u64()?
        };
        let ncolumns = c.i32()?;
        let modify = c.u32()?;
        let (mut table_change, mut dm_change) = (0, Vec::new());
        if ncolumns >= 0 {
            table_change = c.u32()?;
            dm_change = c.block_u32()?;
        }
        c.end(&sync);
        Ok(Some(SyncRecord {
            nrows,
            ncolumns,
            modify,
            table_change,
            dm_change,
        }))
    }

    /// The length-prefixed record as `LockFile::putInfo` writes it.
    pub fn serialise(&self) -> Vec<u8> {
        let mut w = Writer::new(true);
        if self.nrows > u64::from(u32::MAX) {
            w.putstart("sync", 2);
            w.u64(self.nrows);
        } else {
            w.putstart("sync", 1);
            w.u32(self.nrows as u32);
        }
        w.i32(self.ncolumns);
        w.u32(self.modify);
        if self.ncolumns >= 0 {
            w.u32(self.table_change);
            w.block_u32(&self.dm_change);
        }
        w.putend();
        let mut out = (w.buf.len() as u32).to_be_bytes().to_vec();
        out.extend(w.buf);
        out
    }

    /// `TableSyncData::write`: count the changes of one flush.
    pub fn update(&mut self, nrows: u64, ncolumns: u32, table_changed: bool, dm_changed: &[bool]) {
        self.nrows = nrows;
        self.ncolumns = ncolumns as i32;
        let mut changed = false;
        if table_changed {
            self.table_change += 1;
            changed = true;
        }
        self.dm_change.resize(dm_changed.len(), 0);
        for (counter, &c) in self.dm_change.iter_mut().zip(dm_changed) {
            if c {
                *counter += 1;
                changed = true;
            }
        }
        if changed {
            self.modify += 1;
        }
    }
}

/// An open `table.lock` holding casacore's write lock (lock number 0:
/// byte 0, length 1) and the "in use" read lock (byte 1).
pub struct LockFile {
    file: File,
}

impl LockFile {
    /// Take the write lock, trying `attempts` times one `wait` apart.
    pub fn acquire(dir: &Path, attempts: u32, wait: std::time::Duration) -> Result<Self> {
        let path = dir.join("table.lock");
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .map_err(|e| MsError(format!("{}: {e}", path.display())))?;
        for i in 0..attempts.max(1) {
            if fcntl::write_lock(&file, 0) {
                fcntl::read_lock(&file, 1);
                return Ok(LockFile { file });
            }
            if i + 1 < attempts {
                std::thread::sleep(wait);
            }
        }
        err(format!(
            "table is locked by another process ({})",
            path.display()
        ))
    }

    /// The whole lock file, read through the locked descriptor (opening and
    /// closing another descriptor of it would drop this process's locks).
    pub fn contents(&mut self) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        self.file.seek(SeekFrom::Start(0))?;
        self.file.read_to_end(&mut bytes)?;
        Ok(bytes)
    }

    /// Take the write lock again before writing: a no-op while it is held,
    /// and it is held unless this process closed another descriptor of
    /// `table.lock` (POSIX then drops all of a process's locks on the file;
    /// for example a reader of the same table in the same process). Fails
    /// when another process took it meanwhile.
    pub fn reassert(&self) -> Result<()> {
        if fcntl::write_lock(&self.file, 0) {
            fcntl::read_lock(&self.file, 1);
            Ok(())
        } else {
            err("the table's write lock was lost to another process")
        }
    }

    /// Read, update and write the sync record (fsync'd, as casacore does).
    pub fn write_sync(
        &mut self,
        nrows: u64,
        ncolumns: u32,
        table_changed: bool,
        dm_changed: &[bool],
    ) -> Result<()> {
        let mut bytes = Vec::new();
        self.file.seek(SeekFrom::Start(0))?;
        self.file.read_to_end(&mut bytes)?;
        let mut sync = SyncRecord::parse(&bytes)?.unwrap_or_default();
        sync.update(nrows, ncolumns, table_changed, dm_changed);
        write_at(&mut self.file, LOCK_REQUESTS as u64, &sync.serialise())?;
        self.file.sync_all()?;
        Ok(())
    }
}

impl Drop for LockFile {
    fn drop(&mut self) {
        fcntl::unlock(&self.file, 1);
        fcntl::unlock(&self.file, 0);
    }
}

// ---------------------------------------------------------------------------
// StandardStMan.

/// One `SSMIndex`.
#[derive(Clone, Debug, PartialEq)]
pub struct SsmIndexFull {
    pub rows_per_bucket: u32,
    pub n_columns: i32,
    /// Free space in each bucket of this index: (offset, bytes).
    pub free: Vec<(i32, i32)>,
    pub last_row: Vec<u64>,
    pub bucket: Vec<u32>,
}

impl SsmIndexFull {
    fn read(c: &mut Cursor<'_>) -> Result<Self> {
        c.magic()?;
        let object = c.start_expect("SSMIndex")?;
        let n_used = c.u32()? as usize;
        let rows_per_bucket = c.u32()?;
        let n_columns = c.i32()?;
        let free = read_int_map(c)?;
        let last_row = if object.version == 1 {
            c.block_u32()?.into_iter().map(u64::from).collect()
        } else {
            c.block_u64()?
        };
        let bucket = c.block_u32()?;
        c.end(&object);
        if last_row.len() != n_used || bucket.len() != n_used {
            return err("SSMIndex block lengths mismatch its use count");
        }
        Ok(SsmIndexFull {
            rows_per_bucket,
            n_columns,
            free,
            last_row,
            bucket,
        })
    }

    /// `SSMIndex::put` at the top level of a memory AipsIO.
    fn write(&self, w: &mut Writer) {
        let wide = self
            .last_row
            .last()
            .is_some_and(|&r| r > u64::from(u32::MAX));
        w.putstart("SSMIndex", if wide { 2 } else { 1 });
        w.u32(self.last_row.len() as u32);
        w.u32(self.rows_per_bucket);
        w.i32(self.n_columns);
        w.int_map(&self.free);
        if wide {
            w.block_u64(&self.last_row);
        } else {
            w.block_u32(&self.last_row.iter().map(|&r| r as u32).collect::<Vec<_>>());
        }
        w.block_u32(&self.bucket);
        w.putend();
    }

    /// (bucket, first row of the bucket) holding `row`.
    pub fn find(&self, row: u64) -> Result<(u32, u64)> {
        let i = self.last_row.partition_point(|&last| last < row);
        if i >= self.last_row.len() {
            return err(format!("row {row} beyond the StandardStMan index"));
        }
        let first = if i == 0 { 0 } else { self.last_row[i - 1] + 1 };
        Ok((self.bucket[i], first))
    }
}

/// The 512-byte StandardStMan header (`SSMBase::writeIndex`).
#[derive(Clone, Debug, PartialEq)]
pub struct SsmHeader {
    pub big: bool,
    pub bucket_size: u32,
    pub nr_buckets: u32,
    pub pers_cache: u32,
    pub nr_free: u32,
    pub first_free: i32,
    pub nr_idx_buckets: u32,
    pub first_idx_bucket: i32,
    pub idx_bucket_offset: u32,
    pub last_string_bucket: i32,
    pub idx_length: u32,
    pub nr_indices: u32,
}

impl SsmHeader {
    pub fn parse(header: &[u8], little: bool) -> Result<Self> {
        let mut h = Cursor::new(header, !little);
        h.magic()?;
        let object = h.start_expect("StandardStMan")?;
        let big = if object.version >= 3 { h.bool()? } else { true };
        if !(object.version == 3 || object.version == 2 && big) || big == little {
            return err(format!(
                "StandardStMan header version {} (big-endian {big}) is not written",
                object.version
            ));
        }
        let out = SsmHeader {
            big,
            bucket_size: h.u32()?,
            nr_buckets: h.u32()?,
            pers_cache: h.u32()?,
            nr_free: h.u32()?,
            first_free: h.i32()?,
            nr_idx_buckets: h.u32()?,
            first_idx_bucket: h.i32()?,
            idx_bucket_offset: h.u32()?,
            last_string_bucket: h.i32()?,
            idx_length: h.u32()?,
            nr_indices: h.u32()?,
        };
        h.end(&object);
        Ok(out)
    }

    pub fn serialise(&self) -> Vec<u8> {
        // `SSMBase::writeIndex`: the endian flag only in little-endian
        // headers (version 3); big-endian ones keep version 2.
        let mut w = Writer::new(self.big);
        if self.big {
            w.putstart("StandardStMan", 2);
        } else {
            w.putstart("StandardStMan", 3);
            w.bool(self.big);
        }
        w.u32(self.bucket_size);
        w.u32(self.nr_buckets);
        w.u32(self.pers_cache);
        w.u32(self.nr_free);
        w.i32(self.first_free);
        w.u32(self.nr_idx_buckets);
        w.i32(self.first_idx_bucket);
        w.u32(self.idx_bucket_offset);
        w.i32(self.last_string_bucket);
        w.u32(self.idx_length);
        w.u32(self.nr_indices);
        w.putend();
        w.buf
    }
}

/// The StandardStMan blob in `table.dat`: name, column offsets, index map.
#[derive(Clone, Debug, PartialEq)]
pub struct SsmBlob {
    pub name: String,
    pub col_offset: Vec<u32>,
    pub col_index: Vec<u32>,
}

impl SsmBlob {
    pub fn parse(blob: &[u8]) -> Result<Self> {
        let mut c = Cursor::new(blob, true);
        c.magic()?;
        let object = c.start_expect("SSM")?;
        let name = c.string()?;
        let col_offset = c.block_u32()?;
        let col_index = c.block_u32()?;
        c.end(&object);
        Ok(SsmBlob {
            name,
            col_offset,
            col_index,
        })
    }

    pub fn serialise(&self) -> Vec<u8> {
        let mut w = Writer::new(true);
        w.putstart("SSM", 2);
        w.string(&self.name);
        w.block_u32(&self.col_offset);
        w.block_u32(&self.col_index);
        w.putend();
        w.buf
    }
}

/// Read the header and index of a StandardStMan file.
pub fn read_ssm(path: &Path, little: bool) -> Result<(Vec<u8>, SsmHeader, Vec<SsmIndexFull>)> {
    let mut file = File::open(path)?;
    let raw = read_at(&mut file, 0, BUCKET_START as usize)?;
    let header = SsmHeader::parse(&raw, little)?;
    let index = read_ssm_index(&mut file, &header)?;
    let mut c = Cursor::new(&index, header.big);
    let mut indices = Vec::with_capacity(header.nr_indices as usize);
    for _ in 0..header.nr_indices {
        indices.push(SsmIndexFull::read(&mut c)?);
    }
    Ok((raw, header, indices))
}

/// The index bytes of a StandardStMan file, from its bucket chain.
pub fn read_ssm_index(file: &mut File, h: &SsmHeader) -> Result<Vec<u8>> {
    let size = h.bucket_size as usize;
    let mut out = Vec::with_capacity(h.idx_length as usize);
    let mut bucket = h.first_idx_bucket;
    let mut left = h.idx_length as usize;
    for _ in 0..h.nr_idx_buckets {
        if bucket < 0 {
            return err("StandardStMan index bucket chain ends early");
        }
        let bytes = read_at(file, BUCKET_START + bucket as u64 * size as u64, size)?;
        let next = be_i32(&bytes, 4);
        let at = if h.idx_bucket_offset > 0 {
            h.idx_bucket_offset as usize
        } else {
            8
        };
        let take = left.min(size - at);
        out.extend_from_slice(&bytes[at..at + take]);
        left -= take;
        bucket = next;
    }
    Ok(out)
}

/// Serialise the indices as `SSMBase::writeIndex` puts them in memory.
pub fn serialise_ssm_index(indices: &[SsmIndexFull], big: bool) -> Vec<u8> {
    let mut out = Vec::new();
    for index in indices {
        let mut w = Writer::new(big);
        index.write(&mut w);
        out.extend(w.buf);
    }
    out
}

// ---------------------------------------------------------------------------
// The header files of the tiled managers (TiledColumnStMan,
// TiledShapeStMan, TiledCellStMan, TiledDataStMan).

/// A hypercube record of a tiled header (`TSMCube::putObject`).
#[derive(Clone, Debug, PartialEq)]
pub struct TsmCube {
    /// The id and coordinate values record, kept as its object bytes.
    pub values: Vec<u8>,
    pub extensible: bool,
    pub nrdim: u32,
    pub shape: Vec<i64>,
    pub tile: Vec<i64>,
    pub file_seq: i32,
    pub offset: u64,
}

/// A tile file entry (`TSMFile::putObject`): sequence number and length.
#[derive(Clone, Debug, PartialEq)]
pub struct TsmFileEntry {
    pub seq: u32,
    pub length: u64,
}

/// A whole tiled header file (`TiledStMan::headerFilePut` inside the
/// manager's own object).
#[derive(Clone, Debug, PartialEq)]
pub struct TsmHeader {
    /// `TiledColumnStMan`, `TiledShapeStMan`, `TiledCellStMan` or
    /// `TiledDataStMan`.
    pub kind: String,
    /// The tile shape a TiledColumnStMan or TiledCellStMan writes before
    /// the `TiledStMan` part (its tile shape, its default tile shape).
    pub column_tile: Option<Vec<i64>>,
    pub big: bool,
    pub seq: u32,
    pub nrows: u64,
    pub dtypes: Vec<i32>,
    pub hypercolumn: String,
    pub max_cache: u64,
    pub nrdim: u32,
    pub files: Vec<Option<TsmFileEntry>>,
    pub cubes: Vec<TsmCube>,
    /// TiledShapeStMan: default tile shape and the row maps.
    pub default_tile: Vec<i64>,
    pub row_map: Vec<u32>,
    pub cube_map: Vec<u32>,
    pub pos_map: Vec<u32>,
    /// TiledDataStMan: the rows the hypercubes cover (`nrrowLast_p`) and
    /// its row map (64-bit; `cube_map` and `pos_map` are shared).
    pub nrrow_last: u64,
    pub data_row_map: Vec<u64>,
}

/// casacore writes `TSMFile` and `TSMCube` as version 2 (a 64-bit length or
/// offset) from 2 GiB, and as version 1 below it.
const TSM_VERSION_2_FROM: u64 = 2 * 1024 * 1024 * 1024;

impl TsmHeader {
    pub fn is_column(&self) -> bool {
        self.kind == "TiledColumnStMan"
    }

    pub fn is_shape(&self) -> bool {
        self.kind == "TiledShapeStMan"
    }

    pub fn is_cell(&self) -> bool {
        self.kind == "TiledCellStMan"
    }

    pub fn is_data(&self) -> bool {
        self.kind == "TiledDataStMan"
    }

    pub fn parse(bytes: &[u8]) -> Result<Self> {
        let mut h = Cursor::new(bytes, true);
        h.magic()?;
        let outer = h.start()?;
        let kind = outer.kind.clone();
        let expect = match kind.as_str() {
            "TiledColumnStMan" | "TiledShapeStMan" | "TiledCellStMan" => 1,
            "TiledDataStMan" => 2,
            _ => return err(format!("tiled manager {kind} is not supported")),
        };
        if outer.version != expect {
            return err(format!(
                "{kind} header version {} is not supported",
                outer.version
            ));
        }
        let column_tile = if kind == "TiledColumnStMan" || kind == "TiledCellStMan" {
            Some(h.iposition()?)
        } else {
            None
        };
        let inner = h.start_expect("TiledStMan")?;
        // `headerFilePut`: version 2 with the endian flag (little-endian
        // tables), version 1 without it (big-endian ones).
        let big = match inner.version {
            1 => true,
            2 => h.bool()?,
            v => {
                return err(format!(
                    "TiledStMan header version {v} (more than 2^31 rows) is not supported"
                ));
            }
        };
        let seq = h.u32()?;
        let nrows = u64::from(h.u32()?);
        let ncol = h.u32()? as usize;
        let dtypes = (0..ncol).map(|_| h.i32()).collect::<Result<Vec<_>>>()?;
        let hypercolumn = h.string()?;
        let max_cache = u64::from(h.u32()?);
        let nrdim = h.u32()?;
        let nfile = h.u32()? as usize;
        let mut files = Vec::with_capacity(nfile);
        for _ in 0..nfile {
            files.push(if h.bool()? {
                // casacore `TSMFile`: version 2 holds a 64-bit length, from 2 GiB.
                let version = h.u32()?;
                let seq = h.u32()?;
                let length = match version {
                    1 => u64::from(h.u32()?),
                    2 => h.u64()?,
                    v => return err(format!("TSMFile version {v} is not supported")),
                };
                Some(TsmFileEntry { seq, length })
            } else {
                None
            });
        }
        let ncube = h.u32()? as usize;
        let mut cubes = Vec::with_capacity(ncube);
        for _ in 0..ncube {
            // casacore `TSMCube`: version 2 holds a 64-bit offset, from 2 GiB.
            let version = h.i32()?;
            if version != 1 && version != 2 {
                return err(format!("TSMCube version {version} is not supported"));
            }
            let values = crate::aipsio::raw_object(&mut h)?;
            cubes.push(TsmCube {
                values,
                extensible: h.bool()?,
                nrdim: h.u32()?,
                shape: h.iposition()?,
                tile: h.iposition()?,
                file_seq: h.i32()?,
                offset: if version == 1 {
                    u64::from(h.u32()?)
                } else {
                    h.u64()?
                },
            });
        }
        h.end(&inner);
        let (mut default_tile, mut row_map, mut cube_map, mut pos_map) =
            (Vec::new(), Vec::new(), Vec::new(), Vec::new());
        let (mut nrrow_last, mut data_row_map) = (0, Vec::new());
        if kind == "TiledShapeStMan" {
            default_tile = h.iposition()?;
            let n = h.u32()? as usize;
            row_map = h.block_u32()?;
            cube_map = h.block_u32()?;
            pos_map = h.block_u32()?;
            if row_map.len() != n || cube_map.len() != n || pos_map.len() != n {
                return err("TiledShapeStMan row maps mismatch their use count");
            }
        } else if kind == "TiledDataStMan" {
            nrrow_last = h.u64()?;
            data_row_map = h.block_u64()?;
            cube_map = h.block_u32()?;
            pos_map = h.block_u32()?;
            if data_row_map.len() != cube_map.len() || cube_map.len() != pos_map.len() {
                return err("TiledDataStMan row maps mismatch");
            }
        }
        h.end(&outer);
        if h.pos != bytes.len() {
            return err("trailing bytes after the tiled header");
        }
        Ok(TsmHeader {
            kind,
            column_tile,
            big,
            seq,
            nrows,
            dtypes,
            hypercolumn,
            max_cache,
            nrdim,
            files,
            cubes,
            default_tile,
            row_map,
            cube_map,
            pos_map,
            nrrow_last,
            data_row_map,
        })
    }

    pub fn serialise(&self) -> Vec<u8> {
        let mut w = Writer::new(true);
        w.putstart(&self.kind, if self.is_data() { 2 } else { 1 });
        if let Some(tile) = &self.column_tile {
            w.iposition(tile);
        }
        if self.big {
            w.putstart("TiledStMan", 1);
        } else {
            w.putstart("TiledStMan", 2);
            w.bool(self.big);
        }
        w.u32(self.seq);
        w.u32(self.nrows as u32);
        w.u32(self.dtypes.len() as u32);
        for &d in &self.dtypes {
            w.i32(d);
        }
        w.string(&self.hypercolumn);
        w.u32(self.max_cache as u32);
        w.u32(self.nrdim);
        w.u32(self.files.len() as u32);
        for f in &self.files {
            w.bool(f.is_some());
            if let Some(f) = f {
                if f.length < TSM_VERSION_2_FROM {
                    w.u32(1);
                    w.u32(f.seq);
                    w.u32(f.length as u32);
                } else {
                    w.u32(2);
                    w.u32(f.seq);
                    w.u64(f.length);
                }
            }
        }
        w.u32(self.cubes.len() as u32);
        for c in &self.cubes {
            let small = c.offset < TSM_VERSION_2_FROM;
            w.i32(if small { 1 } else { 2 });
            w.bytes(&c.values);
            w.bool(c.extensible);
            w.u32(c.nrdim);
            w.iposition(&c.shape);
            w.iposition(&c.tile);
            w.i32(c.file_seq);
            if small {
                w.u32(c.offset as u32);
            } else {
                w.u64(c.offset);
            }
        }
        w.putend();
        if self.is_shape() {
            w.iposition(&self.default_tile);
            w.u32(self.row_map.len() as u32);
            w.block_u32(&self.row_map);
            w.block_u32(&self.cube_map);
            w.block_u32(&self.pos_map);
        } else if self.is_data() {
            w.u64(self.nrrow_last);
            w.block_u64(&self.data_row_map);
            w.block_u32(&self.cube_map);
            w.block_u32(&self.pos_map);
        }
        w.putend();
        w.buf
    }

    /// Whether a header can be written by this writer: fewer than 2^31 rows
    /// (a larger table is written in a version this writer does not make).
    pub fn writable(&self) -> Result<()> {
        if self.nrows > 0x7fff_ffff {
            return err("tiled managers of 2^31 rows or more are not supported");
        }
        Ok(())
    }
}

/// The empty `Record` object of a hypercube's id/coordinate values.
fn empty_values_record() -> Vec<u8> {
    let mut w = Writer::new(true);
    w.putstart("Holder", 1);
    w.putstart("Record", 1);
    crate::aipsio::RecordDesc::default().write(&mut w);
    w.i32(1);
    w.putend();
    w.putend();
    // Drop the magic value and the holder's own header.
    let holder = 4 + 4 + 4 + "Holder".len() + 4;
    w.buf[holder..].to_vec()
}

// ---------------------------------------------------------------------------
// The indirect-array file `table.fNi` (`StManArrayFile`).

/// casacore's `FilebufIO` (the `RegularFileIO` under `StManArrayFile`), step
/// for step: one block-aligned buffer of `size` bytes; partial-block reads
/// and writes go through it, whole blocks of a write bypass it; a block
/// read past the end of the file leaves the rest of the buffer as it was.
/// Gaps the arrays leave (alignment padding) therefore hold what the buffer
/// held, and only replaying the same operations reproduces them.
struct FileBuf {
    file: File,
    size: u64,
    buf: Vec<u8>,
    buf_off: i64,
    buf_len: u64,
    dirty: bool,
    off: u64,
    /// In a MultiFile table: the log and the logical file's name. The file
    /// is then written directly, as `MFFileIO` does (no `FilebufIO`).
    mf: Option<(crate::multifile::MfLog, String)>,
}

impl FileBuf {
    fn new(file: File, size: u64) -> Self {
        FileBuf {
            file,
            size,
            buf: vec![0; size as usize],
            buf_off: -(size as i64 + 1),
            buf_len: 0,
            dirty: false,
            off: 0,
            mf: None,
        }
    }

    fn seek(&mut self, pos: u64) {
        self.off = pos;
    }

    fn flush(&mut self) -> Result<()> {
        if self.dirty {
            let n = self.buf_len as usize;
            write_at(&mut self.file, self.buf_off as u64, &self.buf[..n])?;
            self.dirty = false;
        }
        Ok(())
    }

    /// `readBuffer` into the whole buffer: what the file has, rest untouched.
    fn load(&mut self) -> Result<()> {
        if self.dirty {
            self.flush()?;
        }
        self.buf_off = (self.off / self.size * self.size) as i64;
        self.file.seek(SeekFrom::Start(self.buf_off as u64))?;
        let mut got = 0;
        loop {
            let n = self.file.read(&mut self.buf[got..])?;
            if n == 0 {
                break;
            }
            got += n;
        }
        self.buf_len = got as u64;
        Ok(())
    }

    fn in_buffer(&self) -> bool {
        (self.off as i64) >= self.buf_off && (self.off as i64) < self.buf_off + self.size as i64
    }

    fn write_block(&mut self, data: &[u8]) -> Result<()> {
        if !self.in_buffer() {
            self.load()?;
        }
        let st = (self.off as i64 - self.buf_off) as usize;
        self.buf[st..st + data.len()].copy_from_slice(data);
        self.dirty = true;
        self.buf_len = self.buf_len.max((st + data.len()) as u64);
        Ok(())
    }

    fn read_block(&mut self, out: &mut [u8]) -> Result<()> {
        if !self.in_buffer() {
            self.load()?;
        }
        let st = (self.off as i64 - self.buf_off) as usize;
        if (st + out.len()) as u64 > self.buf_len {
            return err("read beyond the end of the array file");
        }
        out.copy_from_slice(&self.buf[st..st + out.len()]);
        Ok(())
    }

    /// `FilebufIO::write` (`MFFileIO::write` in a MultiFile table).
    fn write(&mut self, data: &[u8]) -> Result<()> {
        if let Some((log, name)) = &self.mf {
            write_at(&mut self.file, self.off, data)?;
            log.lock().unwrap().push(crate::multifile::Event::Write(
                name.clone(),
                self.off,
                data.len() as u64,
            ));
            self.off += data.len() as u64;
            return Ok(());
        }
        let size = data.len() as u64;
        let st = self.off.div_ceil(self.size);
        let end = (self.off + size) / self.size;
        let mut blkst = st * self.size - self.off;
        let mut sz = 0;
        if st < end {
            sz = (end - st) * self.size;
            write_at(
                &mut self.file,
                st * self.size,
                &data[blkst as usize..(blkst + sz) as usize],
            )?;
            if (st * self.size) as i64 <= self.buf_off
                && (end * self.size) as i64 >= self.buf_off + self.size as i64
            {
                self.dirty = false;
                self.buf_off = -(self.size as i64 + 1);
                self.buf_len = 0;
            }
        }
        if blkst > 0 {
            blkst = blkst.min(size);
            self.write_block(&data[..blkst as usize])?;
        }
        blkst += sz;
        self.off += blkst;
        if blkst < size {
            self.write_block(&data[blkst as usize..])?;
            self.off += size - blkst;
        }
        Ok(())
    }

    /// `FilebufIO::read` of small values (never whole blocks here).
    fn read(&mut self, n: usize) -> Result<Vec<u8>> {
        if self.mf.is_some() {
            let out = read_at(&mut self.file, self.off, n)?;
            self.off += n as u64;
            return Ok(out);
        }
        let mut out = vec![0u8; n];
        let st = self.off.div_ceil(self.size);
        let end = (self.off + n as u64) / self.size;
        if st < end {
            // Reads of shapes and single bytes never span a whole block.
            return err("unexpected whole-block read of the array file");
        }
        let blkst = ((st * self.size - self.off) as usize).min(n);
        if blkst > 0 {
            self.read_block(&mut out[..blkst])?;
        }
        self.off += blkst as u64;
        if blkst < n {
            self.read_block(&mut out[blkst..])?;
            self.off += (n - blkst) as u64;
        }
        Ok(out)
    }
}

/// The indirect-array file `table.fNi` (`StManArrayFile`, version 0 or 1,
/// little or big endian), driven through `FileBuf` as casacore drives it.
pub(crate) struct ArrayFile {
    io: FileBuf,
    pub(crate) version: u32,
    leng: u64,
    has_put: bool,
    big: bool,
}

/// `n` in the byte order of a big- or little-endian table.
pub(crate) fn order_u32(n: u32, big: bool) -> [u8; 4] {
    if big {
        n.to_be_bytes()
    } else {
        n.to_le_bytes()
    }
}

pub(crate) fn order_u64(n: u64, big: bool) -> [u8; 8] {
    if big {
        n.to_be_bytes()
    } else {
        n.to_le_bytes()
    }
}

pub(crate) fn read_order_u32(b: &[u8], big: bool) -> u32 {
    let a: [u8; 4] = b[..4].try_into().unwrap();
    if big {
        u32::from_be_bytes(a)
    } else {
        u32::from_le_bytes(a)
    }
}

pub(crate) fn read_order_u64(b: &[u8], big: bool) -> u64 {
    let a: [u8; 8] = b[..8].try_into().unwrap();
    if big {
        u64::from_be_bytes(a)
    } else {
        u64::from_le_bytes(a)
    }
}

/// Native values of `dtype` in a table's byte order (a copy; swapped per
/// float of a complex value when the table is big-endian).
pub(crate) fn to_order(dtype: DataType, native: &[u8], big: bool) -> Vec<u8> {
    let unit = match dtype {
        DataType::Complex => 4,
        DataType::DComplex => 8,
        dt => dt.size(),
    };
    if big == cfg!(target_endian = "big") || unit <= 1 {
        return native.to_vec();
    }
    let mut out = native.to_vec();
    for chunk in out.chunks_exact_mut(unit) {
        chunk.reverse();
    }
    out
}

impl ArrayFile {
    /// Open the file as `StManArrayFile::resync` does: read the version and
    /// length, or write version 0, length 16 and a zero Int to a new file.
    #[cfg(test)]
    fn open(path: &Path) -> Result<Self> {
        Self::open_ext(path, false, 0, false)
    }

    /// Open (or, `new`, create anew as `ByteIO::New` does) an array file of
    /// a table of byte order `big`; a new file gets `version`.
    pub(crate) fn open_ext(path: &Path, big: bool, version: u32, new: bool) -> Result<Self> {
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(new)
            .open(path)
            .map_err(|e| MsError(format!("{}: {e}", path.display())))?;
        let exists = file.metadata()?.len() > 0;
        let mut io = FileBuf::new(file, 65536);
        if let Some(log) = crate::multifile::current() {
            let name = crate::multifile::name_of(path);
            if !exists {
                crate::multifile::emit(
                    &Some(log.clone()),
                    crate::multifile::Event::Create(name.clone()),
                );
            }
            io.mf = Some((log, name));
        }
        if exists {
            io.seek(0);
            let version = read_order_u32(&io.read(4)?, big);
            let leng = read_order_u64(&io.read(8)?, big);
            Ok(ArrayFile {
                io,
                version,
                leng,
                has_put: false,
                big,
            })
        } else {
            io.seek(0);
            io.write(&order_u32(version, big))?;
            io.write(&order_u64(16, big))?;
            io.write(&order_u32(0, big))?;
            Ok(ArrayFile {
                io,
                version,
                leng: 16,
                has_put: true,
                big,
            })
        }
    }

    /// `StManArrayFile::getShape`: the shape at `offset` and the offset of
    /// its values.
    fn shape(&mut self, offset: u64) -> Result<(Vec<i64>, u64)> {
        let (shape, n) = self.get_shape(offset)?;
        Ok((shape, offset + n))
    }

    /// `StManArrayFile::getShape` as casacore returns it: the shape and the
    /// length of the header (reference count, ndim, dimensions).
    pub(crate) fn get_shape(&mut self, offset: u64) -> Result<(Vec<i64>, u64)> {
        let big = self.big;
        self.io.seek(offset);
        let mut n = 0;
        if self.version > 0 {
            self.io.read(4)?;
            n += 4;
        }
        let ndim = read_order_u32(&self.io.read(4)?, big) as usize;
        let mut shape = Vec::with_capacity(ndim);
        for _ in 0..ndim {
            shape.push(i64::from(read_order_u32(&self.io.read(4)?, big) as i32));
        }
        n += 4 + 4 * ndim as u64;
        Ok((shape, n))
    }

    /// `StManArrayFile::getRefCount` (1 in a version-0 file).
    pub(crate) fn ref_count(&mut self, offset: u64) -> Result<u32> {
        if self.version == 0 {
            return Ok(1);
        }
        self.io.seek(offset);
        Ok(read_order_u32(&self.io.read(4)?, self.big))
    }

    /// `StManArrayFile::putRefCount` (it does not mark the file changed).
    pub(crate) fn put_ref_count(&mut self, offset: u64, count: u32) -> Result<()> {
        if self.version == 0 {
            return if count == 1 {
                Ok(())
            } else {
                err("reference count of a version-0 array file")
            };
        }
        self.io.seek(offset);
        self.io.write(&order_u32(count, self.big))
    }

    /// `StManArrayFile::putRes`: reserve an array of `shape` at the end
    /// (8-byte aligned); returns the array's offset.
    pub(crate) fn put_res(&mut self, shape: &[i64], dtype: DataType) -> Result<u64> {
        let big = self.big;
        self.leng = self.leng.div_ceil(8) * 8;
        let offset = self.leng;
        self.io.seek(offset);
        let mut n = 0;
        if self.version > 0 {
            self.io.write(&order_u32(1, big))?;
            n += 4;
        }
        self.io.write(&order_u32(shape.len() as u32, big))?;
        for &s in shape {
            self.io.write(&order_u32(s as i32 as u32, big))?;
        }
        n += 4 + 4 * shape.len() as u64;
        let count = product(shape) as u64;
        // Int64(n * lenElem + 0.95): ceil(n / 8) for Bool; a string array
        // reserves one uInt offset per string.
        let bytes = match dtype {
            DataType::Bool => count.div_ceil(8),
            DataType::Str => count * 4,
            dt => count * dt.size() as u64,
        };
        self.leng += n + bytes;
        self.io.seek(self.leng - 1);
        self.io.write(&[0])?;
        self.has_put = true;
        Ok(offset)
    }

    /// `StManArrayFile::put` of one array's values (native bytes; Bool one
    /// byte each, packed to bits keeping the trailing bits of the last
    /// byte, which casacore reads first).
    pub(crate) fn put_values(&mut self, at: u64, dtype: DataType, values: &[u8]) -> Result<()> {
        if dtype == DataType::Bool {
            let n = values.len();
            let nbytes = n.div_ceil(8);
            let mut packed = vec![0u8; nbytes];
            if !n.is_multiple_of(8) {
                self.io.seek(at + nbytes as u64 - 1);
                packed[nbytes - 1] = self.io.read(1)?[0];
            }
            put_bits(&mut packed, 0, values);
            self.io.seek(at);
            self.io.write(&packed)?;
        } else if self.big != cfg!(target_endian = "big") && dtype.size() > 1 {
            self.io.seek(at);
            self.io.write(&to_order(dtype, values, self.big))?;
        } else {
            self.io.seek(at);
            self.io.write(values)?;
        }
        self.has_put = true;
        Ok(())
    }

    /// `StManArrayFile::put` of `values.len()` uInts at `at` (one write).
    pub(crate) fn put_u32s(&mut self, at: u64, values: &[u32]) -> Result<()> {
        let mut bytes = Vec::with_capacity(4 * values.len());
        for &v in values {
            bytes.extend(order_u32(v, self.big));
        }
        self.io.seek(at);
        self.io.write(&bytes)?;
        self.has_put = true;
        Ok(())
    }

    /// `StManArrayFile::putShape` of a string array: `putRes` with one uInt
    /// per string, then those offsets put as zeros; returns the record's
    /// offset.
    pub(crate) fn put_res_strings(&mut self, shape: &[i64]) -> Result<u64> {
        let offset = self.put_res(shape, DataType::Str)?;
        let head = if self.version > 0 { 4 } else { 0 } + 4 + 4 * shape.len() as u64;
        self.put_u32s(offset + head, &vec![0; product(shape)])?;
        Ok(offset)
    }

    /// `StManArrayFile::put` of strings whose offsets start at `at`: in
    /// batches of 4096, each string's length and characters appended at the
    /// end of the file, then the batch's offsets.
    pub(crate) fn put_strings(&mut self, at: u64, strings: &[String]) -> Result<()> {
        let mut offs = at;
        for batch in strings.chunks(4096) {
            let mut buf = Vec::with_capacity(batch.len());
            self.io.seek(self.leng);
            for s in batch {
                if self.leng >= 1 << 32 {
                    return err("StManArrayFile: string offset beyond 2^32");
                }
                buf.push(self.leng as u32);
                self.io.write(&order_u32(s.len() as u32, self.big))?;
                self.io.write(s.as_bytes())?;
                self.leng += 4 + s.len() as u64;
            }
            self.put_u32s(offs, &buf)?;
            offs += 4 * batch.len() as u64;
        }
        self.has_put = true;
        Ok(())
    }

    /// `StManArrayFile::get` of `n` strings whose offsets start at `at`
    /// (offset 0: an empty string), straight from the file after a flush.
    pub(crate) fn read_strings(&mut self, at: u64, n: usize) -> Result<Vec<String>> {
        self.io.flush()?;
        let big = self.big;
        let offs = read_at(&mut self.io.file, at, 4 * n)?;
        let mut out = Vec::with_capacity(n);
        for k in 0..n {
            let o = u64::from(read_order_u32(&offs[4 * k..], big));
            if o == 0 {
                out.push(String::new());
                continue;
            }
            let len = read_order_u32(&read_at(&mut self.io.file, o, 4)?, big) as usize;
            let chars = read_at(&mut self.io.file, o + 4, len)?;
            out.push(String::from_utf8_lossy(&chars).into_owned());
        }
        Ok(out)
    }

    /// `StManArrayFile::flush` and the buffer's own flush at close.
    fn flush(&mut self) -> Result<()> {
        self.flush_changed().map(|_| ())
    }

    /// `StManArrayFile::flush`, returning whether the file had changed (the
    /// manager then reports a change), then the buffer's own flush.
    pub(crate) fn flush_changed(&mut self) -> Result<bool> {
        let changed = self.has_put;
        if self.has_put {
            let (version, leng) = (
                order_u32(self.version, self.big),
                order_u64(self.leng, self.big),
            );
            self.io.seek(0);
            self.io.write(&version)?;
            self.io.write(&leng)?;
            self.has_put = false;
            self.io.flush()?;
            self.io.seek(self.leng);
        }
        self.io.flush()?;
        Ok(changed)
    }

    /// Read `n` values of an array whose values start at `at` (native bytes;
    /// Bool one byte each), straight from the file after a flush.
    pub(crate) fn read_values(&mut self, at: u64, dtype: DataType, n: usize) -> Result<Vec<u8>> {
        self.io.flush()?;
        if dtype == DataType::Bool {
            let bytes = read_at(&mut self.io.file, at, n.div_ceil(8))?;
            return Ok(get_bits(&bytes, 0, n));
        }
        let bytes = read_at(&mut self.io.file, at, n * dtype.size())?;
        Ok(to_order(dtype, &bytes, self.big))
    }
}

pub(crate) fn product(shape: &[i64]) -> usize {
    shape.iter().map(|&s| s.max(0) as usize).product()
}

/// Set `count` bits from bit `dst` of `out` to the one-byte booleans of
/// `src`, least significant bit first; whole bytes are packed at once.
pub(crate) fn put_bits(out: &mut [u8], dst: usize, src: &[u8]) {
    let mut k = 0;
    while k < src.len() {
        let bit = dst + k;
        if bit.is_multiple_of(8) && src.len() - k >= 8 {
            let mut byte = 0u8;
            for (j, &v) in src[k..k + 8].iter().enumerate() {
                byte |= u8::from(v != 0) << j;
            }
            out[bit / 8] = byte;
            k += 8;
        } else {
            if src[k] != 0 {
                out[bit / 8] |= 1 << (bit % 8);
            } else {
                out[bit / 8] &= !(1 << (bit % 8));
            }
            k += 1;
        }
    }
}

// ---------------------------------------------------------------------------
// StandardStMan writes.

#[derive(Clone, Copy, Debug, PartialEq)]
enum SsmKind {
    Scalar,
    FixedString(usize),
    String,
    Direct(usize),
    Indirect,
    /// A string array: a 12-byte slot (bucket, offset, length) into the
    /// string buckets; `SsmCol::fixed` set for Direct or FixedShape columns
    /// (`SSMDirColumn`: no shape stored), else variable-shape
    /// (`SSMIndStringColumn`: shape and a filled flag stored first).
    StrArray,
}

#[derive(Clone, Debug)]
struct SsmCol {
    name: String,
    dtype: DataType,
    kind: SsmKind,
    bits: usize,
    /// The shape every row has (Direct and FixedShape indirect columns).
    fixed: Option<Vec<i64>>,
}

fn ssm_col(desc: &ColDesc, binding: &ColBinding) -> Result<SsmCol> {
    let dtype = DataType::from_code(desc.dtype)?;
    let fixed = match (&binding.shape, &desc.shape) {
        (Some(Some(s)), _) => Some(s.clone()),
        (_, Some(s)) if !s.is_empty() && desc.option & 4 != 0 => Some(s.clone()),
        _ => None,
    };
    let direct = desc.option & 1 != 0;
    let (kind, bits) = match (dtype, desc.is_array(), direct) {
        (DataType::Str, false, _) if desc.max_length > 0 => (
            SsmKind::FixedString(desc.max_length as usize),
            8 * desc.max_length as usize,
        ),
        (DataType::Str, false, _) => (SsmKind::String, 96),
        (DataType::Bool, false, _) => (SsmKind::Scalar, 1),
        (dt, false, _) => (SsmKind::Scalar, 8 * dt.size()),
        (DataType::Str, true, _) => (SsmKind::StrArray, 96),
        (dt, true, true) => {
            let n = product(fixed.as_deref().unwrap_or(&[]));
            let bits = if dt == DataType::Bool {
                n
            } else {
                8 * dt.size() * n
            };
            (SsmKind::Direct(n), bits)
        }
        (_, true, false) => (SsmKind::Indirect, 64),
    };
    Ok(SsmCol {
        name: desc.name.clone(),
        dtype,
        kind,
        bits,
        fixed,
    })
}

/// casacore's `SSMStringHandler` state (string buckets).
#[derive(Default)]
struct Strings {
    current: i32,
    last: i32,
    used: i32,
    deleted: i32,
    next: i32,
    data: Vec<u8>,
    changed: bool,
}

struct SsmW {
    file: File,
    header_raw: Vec<u8>,
    h: SsmHeader,
    indices: Vec<SsmIndexFull>,
    blob: SsmBlob,
    cols: Vec<SsmCol>,
    buckets: BTreeMap<u32, Vec<u8>>,
    dirty: std::collections::BTreeSet<u32>,
    changed: bool,
    arrays: Option<ArrayFile>,
    array_path: PathBuf,
    scratch: Vec<u8>,
    strings: Strings,
    /// casacore's bucket-cache bookkeeping (`scratch` is its buffer).
    cache: Cache,
    /// Read from a file (its index is read through the cache first).
    opened: bool,
    /// `itsBucketRows` and `itsBucketSize` as `SSMBase::init` left them
    /// (read from a file: 0 and the header's), for a `recreate`.
    sizing: (usize, usize),
    /// The manager's file (`table.fN`).
    path: PathBuf,
    /// The write log of a MultiFile table.
    mf: Option<crate::multifile::MfLog>,
}

/// casacore's `BucketCache` slots for one StandardStMan (LRU counters,
/// dirty flags), kept only to know what its scratch buffer `its_Buffer`
/// holds when a bucket is freed (research/e4-table-create.md).
#[derive(Default)]
struct Cache {
    ready: bool,
    size: usize,
    used: usize,
    bucket: Vec<u32>,
    lru: Vec<u32>,
    dirty: Vec<bool>,
    live: Vec<bool>,
    counter: u32,
    actual: usize,
    slot_of: BTreeMap<u32, usize>,
}

impl SsmW {
    fn open(dir: &Path, seq: u32, blob: &[u8], cols: Vec<SsmCol>, big: bool) -> Result<Self> {
        Self::open_mode(dir, seq, blob, cols, true, big)
    }

    /// Open read-only (`writable` false) for the cell reads of
    /// `read_cells`, which never write.
    fn open_mode(
        dir: &Path,
        seq: u32,
        blob: &[u8],
        cols: Vec<SsmCol>,
        writable: bool,
        big: bool,
    ) -> Result<Self> {
        let path = dir.join(format!("table.f{seq}"));
        let (header_raw, h, indices) = read_ssm(&path, !big)?;
        let bucket_size = h.bucket_size as usize;
        let blob = SsmBlob::parse(blob)?;
        if blob.col_offset.len() != cols.len() {
            return err("StandardStMan column count mismatches the table");
        }
        let file = OpenOptions::new()
            .read(true)
            .write(writable)
            .open(&path)
            .map_err(|e| MsError(format!("{}: {e}", path.display())))?;
        let strings = Strings {
            current: -1,
            last: h.last_string_bucket,
            next: -1,
            ..Default::default()
        };
        Ok(SsmW {
            file,
            header_raw,
            scratch: vec![0; h.bucket_size as usize],
            h,
            indices,
            blob,
            cols,
            buckets: BTreeMap::new(),
            dirty: Default::default(),
            changed: false,
            arrays: None,
            array_path: dir.join(format!("table.f{seq}i")),
            sizing: (0, bucket_size),
            path: path.clone(),
            strings,
            cache: Cache::default(),
            opened: true,
            mf: crate::multifile::current(),
        })
    }

    /// `SSMBase::init`: rows per bucket (and the sizing state) for columns
    /// of `bits` bits a row with the advised rows and bucket size.
    fn init_sizing(bits: &[usize], rows: usize, size: usize) -> (usize, usize, usize) {
        let mut rows = rows;
        let mut size = size;
        let set_size = |rows: usize, size: &mut usize| -> usize {
            let total: usize = bits.iter().map(|b| b.div_ceil(8)).sum();
            *size = (*size).max(128);
            let mut adv = rows;
            let mut rpb = if adv == 0 { *size / total } else { adv };
            loop {
                let this: usize = bits.iter().map(|b| (rpb * b).div_ceil(8)).sum();
                let next: usize = bits.iter().map(|b| ((rpb + 1) * b).div_ceil(8)).sum();
                if adv > 0 {
                    *size = this.clamp(128, 32768);
                    if *size == this {
                        break;
                    }
                    rpb = *size / total;
                    adv = 0;
                } else {
                    if next > *size {
                        break;
                    }
                    rpb += 1;
                }
            }
            if rpb < 1 {
                *size = total;
                rpb = 1;
            }
            rpb
        };
        let mut rpb = set_size(rows, &mut size);
        if rows > 0 && rows > rpb {
            let nb = rows.div_ceil(rpb);
            rows = rows.div_ceil(nb);
            rpb = set_size(rows, &mut size);
        }
        (rpb, rows, size)
    }

    /// The column offsets in a bucket of `rpb` rows and the new index
    /// (`SSMIndex` with the rest of the bucket free).
    fn layout(bits: &[usize], rpb: usize, size: usize) -> (Vec<u32>, SsmIndexFull) {
        let mut offsets = Vec::with_capacity(bits.len());
        let mut total = 0usize;
        for b in bits {
            offsets.push(total as u32);
            total += (rpb * b).div_ceil(8);
        }
        let mut free = Vec::new();
        if size > total {
            free.push((total as i32, (size - total) as i32));
        }
        (
            offsets,
            SsmIndexFull {
                rows_per_bucket: rpb as u32,
                n_columns: bits.len() as i32,
                free,
                last_row: Vec::new(),
                bucket: Vec::new(),
            },
        )
    }

    /// `SSMBase::removeRow64` at its last row: `create64(0)` (`init` and
    /// `recreate`): the file made anew, one new index, the string handler
    /// and the array file (of indirect columns) new; nothing of the old
    /// file is kept.
    fn recreate(&mut self) -> Result<()> {
        let bits: Vec<usize> = self.cols.iter().map(|c| c.bits).collect();
        let (rpb, rows, size) = Self::init_sizing(&bits, self.sizing.0, self.sizing.1);
        self.sizing = (rows, size);
        let (offsets, index) = Self::layout(&bits, rpb, size);
        self.file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(&self.path)
            .map_err(|e| MsError(format!("{}: {e}", self.path.display())))?;
        self.event_create();
        let pers = self.h.pers_cache;
        self.h = SsmHeader {
            big: self.h.big,
            bucket_size: size as u32,
            nr_buckets: 0,
            pers_cache: pers,
            nr_free: 0,
            first_free: -1,
            nr_idx_buckets: 0,
            first_idx_bucket: -1,
            idx_bucket_offset: 0,
            last_string_bucket: -1,
            idx_length: 0,
            nr_indices: 1,
        };
        self.header_raw = vec![0; BUCKET_START as usize];
        self.scratch = vec![0; size];
        self.indices = vec![index];
        self.blob.col_offset = offsets;
        self.blob.col_index = vec![0; self.cols.len()];
        self.buckets.clear();
        self.dirty.clear();
        self.cache = Cache::default();
        self.strings = Strings {
            current: -1,
            last: -1,
            next: -1,
            ..Default::default()
        };
        self.opened = false;
        if let Some(mut a) = self.arrays.take() {
            a.flush()?;
        }
        if self.cols.iter().any(|c| c.kind == SsmKind::Indirect) {
            let _ = std::fs::remove_file(&self.array_path);
            self.arrays()?;
        }
        self.changed = true;
        Ok(())
    }

    /// A new StandardStMan for `cols` (`SSMBase::create64`: `init` sizes the
    /// bucket with `setBucketSize`, one index holds every column; then the
    /// rows are added). `bucket_rows` and `bucket_size` are the SPEC values
    /// BUCKETROWS and BUCKETSIZE (0: not given; 32 rows by default).
    #[allow(clippy::too_many_arguments)]
    fn create(
        dir: &Path,
        seq: u32,
        name: &str,
        cols: Vec<SsmCol>,
        nrows: u64,
        bucket_rows: u32,
        bucket_size: u32,
        pers_cache: u32,
        big: bool,
    ) -> Result<Self> {
        let bits: Vec<usize> = cols.iter().map(|c| c.bits).collect();
        if bits.contains(&0) {
            return err("unsupported column for a new StandardStMan");
        }
        let mut rows = if bucket_rows > 0 {
            bucket_rows as usize
        } else {
            0
        };
        let size = bucket_size as usize;
        if rows == 0 && size == 0 {
            rows = 32;
        }
        let (rpb, rows, size) = Self::init_sizing(&bits, rows, size);
        let (offsets, index) = Self::layout(&bits, rpb, size);
        let path = dir.join(format!("table.f{seq}"));
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(&path)
            .map_err(|e| MsError(format!("{}: {e}", path.display())))?;
        let h = SsmHeader {
            big,
            bucket_size: size as u32,
            nr_buckets: 0,
            pers_cache: pers_cache.max(2),
            nr_free: 0,
            first_free: -1,
            nr_idx_buckets: 0,
            first_idx_bucket: -1,
            idx_bucket_offset: 0,
            last_string_bucket: -1,
            idx_length: 0,
            nr_indices: 1,
        };
        let ncol = cols.len();
        let mut s = SsmW {
            file,
            header_raw: vec![0; BUCKET_START as usize],
            scratch: vec![0; size],
            h,
            indices: vec![index],
            blob: SsmBlob {
                name: name.to_string(),
                col_offset: offsets,
                col_index: vec![0; ncol],
            },
            cols,
            buckets: BTreeMap::new(),
            dirty: Default::default(),
            changed: true,
            arrays: None,
            array_path: dir.join(format!("table.f{seq}i")),
            strings: Strings {
                current: -1,
                last: -1,
                next: -1,
                ..Default::default()
            },
            cache: Cache::default(),
            opened: false,
            sizing: (rows, size),
            path: path.clone(),
            mf: crate::multifile::current(),
        };
        s.event_create();
        if s.cols.iter().any(|c| c.kind == SsmKind::Indirect) {
            // `SSMIndColumn::doCreate` opens a new array file.
            let _ = std::fs::remove_file(&s.array_path);
            s.arrays()?;
        }
        // `SSMIndex::addRow` then the columns' `addRow`.
        let mut row = 0u64;
        while row < nrows {
            let n = (nrows - row).min(rpb as u64);
            let b = s.new_bucket()?;
            row += n;
            s.indices[0].bucket.push(b);
            s.indices[0].last_row.push(row - 1);
        }
        for k in 0..ncol {
            if let (SsmKind::Indirect, Some(shape)) = (s.cols[k].kind, s.cols[k].fixed.clone()) {
                let dtype = s.cols[k].dtype;
                for row in 0..nrows {
                    let (b, at) = s.slot(k, row)?;
                    let array = s.arrays()?.put_res(&shape, dtype)?;
                    s.set_u64(b, at, array)?;
                    s.set_dirty(b);
                }
            }
        }
        Ok(s)
    }

    fn size(&self) -> usize {
        self.h.bucket_size as usize
    }

    /// The 8-byte array offset at `at` of bucket `b` (the table's order).
    fn get_u64(&mut self, b: u32, at: usize) -> Result<u64> {
        let big = self.h.big;
        Ok(read_order_u64(&self.bucket(b)?[at..at + 8], big))
    }

    fn set_u64(&mut self, b: u32, at: usize, v: u64) -> Result<()> {
        let bytes = order_u64(v, self.h.big);
        self.bucket(b)?[at..at + 8].copy_from_slice(&bytes);
        Ok(())
    }

    fn get_i32(&mut self, b: u32, at: usize) -> Result<i32> {
        let big = self.h.big;
        Ok(read_order_u32(&self.bucket(b)?[at..at + 4], big) as i32)
    }

    fn set_i32(&mut self, b: u32, at: usize, v: i32) -> Result<()> {
        let bytes = order_u32(v as u32, self.h.big);
        self.bucket(b)?[at..at + 4].copy_from_slice(&bytes);
        Ok(())
    }

    /// The current bytes of bucket `n` (loaded from the file once).
    fn content(&mut self, n: u32) -> Result<&mut Vec<u8>> {
        if !self.buckets.contains_key(&n) {
            let size = self.size();
            let bytes = read_at(
                &mut self.file,
                BUCKET_START + u64::from(n) * size as u64,
                size,
            )?;
            self.buckets.insert(n, bytes);
        }
        Ok(self.buckets.get_mut(&n).unwrap())
    }

    /// `BucketCache::getBucket`: the bucket's bytes, with the cache's slot
    /// bookkeeping (research/e4-table-create.md, "bucket cache").
    fn bucket(&mut self, n: u32) -> Result<&mut Vec<u8>> {
        if n >= self.h.nr_buckets {
            return err(format!("StandardStMan bucket {n} beyond the file"));
        }
        self.access(n)?;
        self.content(n)
    }

    /// Create the cache as `SSMBase::makeCache` does: for a manager read
    /// from a file, `readIndexBuckets` reads the index through it first.
    fn cache_ready(&mut self) -> Result<()> {
        if self.cache.ready {
            return Ok(());
        }
        let size = self.h.pers_cache.max(2) as usize;
        self.cache = Cache {
            size,
            bucket: vec![0; size],
            lru: vec![0; size],
            dirty: vec![false; size],
            live: vec![false; size],
            ready: true,
            ..Default::default()
        };
        if self.opened {
            let mut b = self.h.first_idx_bucket;
            for _ in 0..self.h.nr_idx_buckets {
                if b < 0 {
                    break;
                }
                self.access(b as u32)?;
                b = be_i32(self.content(b as u32)?, 4);
            }
        }
        Ok(())
    }

    fn set_lru(&mut self) {
        let c = &mut self.cache;
        c.counter = c.counter.wrapping_add(1);
        c.lru[c.actual] = c.counter;
    }

    /// `BucketCache::getSlot`: a free slot or the least recently used one,
    /// whose bucket is written (through the scratch buffer) when dirty.
    fn get_slot(&mut self, n: u32) -> Result<()> {
        if self.cache.used < self.cache.size {
            self.cache.actual = self.cache.used;
            self.cache.used += 1;
        } else {
            let c = &self.cache;
            let mut slot = 0;
            for i in 1..c.used {
                if c.lru[i] < c.lru[slot] {
                    slot = i;
                }
            }
            self.cache.actual = slot;
            if self.cache.dirty[slot] {
                let old = self.cache.bucket[slot];
                let bytes = self.content(old)?.clone();
                self.scratch.copy_from_slice(&bytes);
                self.cache.dirty[slot] = false;
                self.event_bucket(old);
            }
            if self.cache.live[slot] {
                self.cache.live[slot] = false;
                let old = self.cache.bucket[slot];
                self.cache.slot_of.remove(&old);
            }
        }
        self.set_lru();
        let slot = self.cache.actual;
        self.cache.bucket[slot] = n;
        self.cache.live[slot] = true;
        self.cache.slot_of.insert(n, slot);
        Ok(())
    }

    /// The slot bookkeeping of `BucketCache::getBucket` for bucket `n`.
    fn access(&mut self, n: u32) -> Result<()> {
        self.cache_ready()?;
        if let Some(&slot) = self.cache.slot_of.get(&n) {
            self.cache.actual = slot;
            self.set_lru();
            return Ok(());
        }
        self.get_slot(n)?;
        // `readBucket` reads the bucket through the scratch buffer.
        let bytes = self.content(n)?.clone();
        self.scratch.copy_from_slice(&bytes);
        Ok(())
    }

    fn set_dirty(&mut self, n: u32) {
        self.dirty.insert(n);
        self.changed = true;
        if let Some(&slot) = self.cache.slot_of.get(&n) {
            self.cache.dirty[slot] = true;
        }
    }

    /// `SSMBase::getNewBucket` through `BucketCache::addBucket`: the first
    /// free bucket (its list link read into the scratch buffer) or a new
    /// one, zeroed.
    fn new_bucket(&mut self) -> Result<u32> {
        self.cache_ready()?;
        let n = if self.h.first_free >= 0 {
            let n = self.h.first_free as u32;
            let head = self.content(n)?[..4].to_vec();
            self.scratch[..4].copy_from_slice(&head);
            self.h.first_free = be_i32(&head, 0);
            self.h.nr_free -= 1;
            n
        } else {
            self.h.nr_buckets += 1;
            self.h.nr_buckets - 1
        };
        self.get_slot(n)?;
        let size = self.size();
        self.buckets.insert(n, vec![0; size]);
        self.set_dirty(n);
        Ok(n)
    }

    /// `SSMBase::removeBucket`: `getBucket`, then `BucketCache::removeBucket`
    /// writes its scratch buffer into the bucket with the old free-list head
    /// in front and frees the slot; the rest of the bucket is unreferenced.
    fn remove_bucket(&mut self, n: u32) -> Result<()> {
        self.access(n)?;
        self.event_bucket(n);
        let mut bytes = self.scratch.clone();
        bytes[..4].copy_from_slice(&self.h.first_free.to_be_bytes());
        self.scratch[..4].copy_from_slice(&self.h.first_free.to_be_bytes());
        self.buckets.insert(n, bytes);
        self.dirty.insert(n);
        let slot = self.cache.actual;
        self.cache.dirty[slot] = false;
        self.cache.live[slot] = false;
        self.cache.slot_of.remove(&n);
        self.cache.lru[slot] = 0;
        self.cache.actual = 0;
        self.h.first_free = n as i32;
        self.h.nr_free += 1;
        self.changed = true;
        Ok(())
    }

    /// `BucketCache::flush`: the dirty slots in slot order, each written
    /// through the scratch buffer.
    fn cache_flush(&mut self) -> Result<()> {
        if !self.cache.ready {
            return Ok(());
        }
        for i in 0..self.cache.used {
            if self.cache.dirty[i] {
                let b = self.cache.bucket[i];
                let bytes = self.content(b)?.clone();
                self.scratch.copy_from_slice(&bytes);
                self.cache.dirty[i] = false;
                self.event_bucket(b);
            }
        }
        Ok(())
    }

    /// (bucket, byte offset of the column in it, index of `row` in it, last
    /// row of the bucket).
    fn locate(&self, col: usize, row: u64) -> Result<(u32, usize, usize, u64)> {
        let index = &self.indices[self.blob.col_index[col] as usize];
        let (bucket, first) = index.find(row)?;
        let i = index.last_row.partition_point(|&l| l < row);
        Ok((
            bucket,
            self.blob.col_offset[col] as usize,
            (row - first) as usize,
            index.last_row[i],
        ))
    }

    /// (bucket, byte offset) of the 8-byte array offset of an indirect row.
    fn slot(&self, col: usize, row: u64) -> Result<(u32, usize)> {
        let (b, offset, first, _) = self.locate(col, row)?;
        Ok((b, offset + first * 8))
    }

    fn arrays(&mut self) -> Result<&mut ArrayFile> {
        if self.arrays.is_none() {
            let (path, big) = (self.array_path.clone(), self.h.big);
            self.arrays = Some(crate::multifile::with_log(self.mf.as_ref(), || {
                ArrayFile::open_ext(&path, big, 0, false)
            })?);
        }
        Ok(self.arrays.as_mut().unwrap())
    }

    /// MultiFile events: the file made anew (`BucketFile` with
    /// `ByteIO::New`), a write of `n` bytes at `at`.
    fn event_create(&self) {
        crate::multifile::emit(
            &self.mf,
            crate::multifile::Event::Create(crate::multifile::name_of(&self.path)),
        );
    }

    fn event_write(&self, at: u64, n: usize) {
        crate::multifile::emit(
            &self.mf,
            crate::multifile::Event::Write(crate::multifile::name_of(&self.path), at, n as u64),
        );
    }

    fn event_bucket(&self, b: u32) {
        let size = self.size();
        self.event_write(BUCKET_START + u64::from(b) * size as u64, size);
    }

    /// Write `count` rows of a numeric or Bool column from native bytes.
    fn put(
        &mut self,
        col: usize,
        start: u64,
        count: u64,
        shape: &[i64],
        data: &[u8],
    ) -> Result<()> {
        let c = self.cols[col].clone();
        let cell = product(shape);
        let row_bytes = cell * c.dtype.native_size();
        match c.kind {
            SsmKind::Scalar | SsmKind::Direct(_) => {
                let nelem = if let SsmKind::Direct(n) = c.kind {
                    n
                } else {
                    1
                };
                if c.kind != SsmKind::Scalar && c.fixed.as_deref() != Some(shape) {
                    return err(format!(
                        "{}: cell shape {shape:?} differs from the column's",
                        c.name
                    ));
                }
                let mut row = start;
                while row < start + count {
                    let (b, offset, first, last) = self.locate(col, row)?;
                    let n = (last.min(start + count - 1) - row + 1) as usize;
                    let src = &data[(row - start) as usize * row_bytes..][..n * row_bytes];
                    let src = to_order(c.dtype, src, self.h.big);
                    let bucket = self.bucket(b)?;
                    if c.dtype == DataType::Bool {
                        put_bits(&mut bucket[offset..], first * nelem, &src);
                    } else {
                        let at = offset + first * nelem * c.dtype.size();
                        bucket[at..at + src.len()].copy_from_slice(&src);
                    }
                    self.set_dirty(b);
                    row += n as u64;
                }
            }
            SsmKind::Indirect => {
                if c.dtype == DataType::Str {
                    return err(format!("{}: string arrays are not written (E4/E5)", c.name));
                }
                if let Some(fixed) = &c.fixed
                    && fixed.as_slice() != shape
                {
                    return err(format!(
                        "{}: the column has the fixed shape {fixed:?}, not {shape:?}",
                        c.name
                    ));
                }
                // As `ArrayColumnBase::acbPutColumn(Cells)`: a variable-shape
                // column first gets every row's shape set (`setShape` reads the
                // old shape and reserves a new array when it differs), then
                // `putArrayV` reads each row's shape and writes its values.
                if c.fixed.is_none() {
                    for i in 0..count {
                        let (b, at) = self.slot(col, start + i)?;
                        let current = self.get_u64(b, at)?;
                        if current != 0 && self.arrays()?.shape(current)?.0 == shape {
                            continue;
                        }
                        let new = self.arrays()?.put_res(shape, c.dtype)?;
                        self.set_u64(b, at, new)?;
                        self.set_dirty(b);
                    }
                }
                for i in 0..count {
                    let (b, at) = self.slot(col, start + i)?;
                    let current = self.get_u64(b, at)?;
                    if current == 0 {
                        return err(format!("row {} of {} has no array", start + i, c.name));
                    }
                    let (old, values_at) = self.arrays()?.shape(current)?;
                    if old != shape {
                        return err(format!(
                            "row {} of {} has the shape {old:?}",
                            start + i,
                            c.name
                        ));
                    }
                    let src = &data[i as usize * row_bytes..][..row_bytes];
                    self.arrays()?.put_values(values_at, c.dtype, src)?;
                }
            }
            SsmKind::FixedString(_) | SsmKind::String | SsmKind::StrArray => {
                return err(format!("{}: use put_strings for string columns", c.name));
            }
        }
        Ok(())
    }

    /// Write strings into a scalar string column (`SSMColumn::putString`).
    fn put_strings(&mut self, col: usize, start: u64, values: &[String]) -> Result<()> {
        let c = self.cols[col].clone();
        for (i, s) in values.iter().enumerate() {
            let row = start + i as u64;
            let (b, offset, first, _) = self.locate(col, row)?;
            match c.kind {
                SsmKind::FixedString(len) => {
                    let at = offset + first * len;
                    let n = len.min(s.len() + 1);
                    let mut bytes = s.as_bytes().to_vec();
                    bytes.push(0);
                    self.bucket(b)?[at..at + n].copy_from_slice(&bytes[..n]);
                    self.set_dirty(b);
                }
                SsmKind::String => {
                    let at = offset + first * 12;
                    let (mut sb, mut so, mut sl) = (
                        self.get_i32(b, at)?,
                        self.get_i32(b, at + 4)?,
                        self.get_i32(b, at + 8)?,
                    );
                    if s.len() <= 8 {
                        if sl > 8 {
                            self.str_remove(sb, so, sl)?;
                        }
                        self.set_i32(b, at + 8, s.len() as i32)?;
                        self.bucket(b)?[at..at + s.len()].copy_from_slice(s.as_bytes());
                    } else {
                        if sl <= 8 {
                            (sb, so, sl) = (0, 0, 0);
                        }
                        self.str_put(&mut sb, &mut so, &mut sl, s.as_bytes())?;
                        self.set_i32(b, at, sb)?;
                        self.set_i32(b, at + 4, so)?;
                        self.set_i32(b, at + 8, sl)?;
                    }
                    self.set_dirty(b);
                }
                _ => return err(format!("{} is not a scalar string column", c.name)),
            }
        }
        Ok(())
    }

    // The string-bucket handler, step for step as `SSMStringHandler`.

    fn str_length(&self) -> i32 {
        self.h.bucket_size as i32 - 16
    }

    fn str_flush(&mut self) -> Result<()> {
        if self.strings.changed {
            let n = self.strings.current as u32;
            let (used, deleted, next) =
                (self.strings.used, self.strings.deleted, self.strings.next);
            let data = self.strings.data.clone();
            let bucket = self.bucket(n)?;
            bucket[4..8].copy_from_slice(&used.to_be_bytes());
            bucket[8..12].copy_from_slice(&deleted.to_be_bytes());
            bucket[12..16].copy_from_slice(&next.to_be_bytes());
            bucket[16..].copy_from_slice(&data);
            self.set_dirty(n);
            self.strings.changed = false;
        }
        Ok(())
    }

    fn str_get_bucket(&mut self, n: i32, is_new: bool) -> Result<()> {
        self.str_flush()?;
        self.strings.current = n;
        if !is_new {
            let bucket = self.bucket(n as u32)?.clone();
            self.strings.data = bucket[16..].to_vec();
            self.strings.used = be_i32(&bucket, 4);
            self.strings.deleted = be_i32(&bucket, 8);
            self.strings.next = be_i32(&bucket, 12);
        }
        Ok(())
    }

    fn str_new_bucket(&mut self, concat: bool) -> Result<()> {
        let n = self.new_bucket()? as i32;
        if concat {
            self.strings.next = n;
            self.strings.changed = true;
        }
        self.str_get_bucket(n, true)?;
        self.strings.used = 0;
        self.strings.deleted = self.str_length();
        self.strings.next = -1;
        self.strings.last = n;
        // casacore keeps one character buffer, zeroed once (`init`): a new
        // bucket starts with what the previous bucket left in it.
        let length = self.str_length() as usize;
        if self.strings.data.len() != length {
            self.strings.data = vec![0; length];
        }
        Ok(())
    }

    fn str_remove(&mut self, bucket: i32, offset: i32, length: i32) -> Result<()> {
        if self.strings.current != bucket {
            self.str_get_bucket(bucket, false)?;
        }
        let n = (self.str_length() - offset).min(length);
        self.strings.deleted += n;
        if offset + n == self.strings.used {
            self.strings.used = offset;
        }
        self.strings.changed = true;
        if self.strings.deleted == self.str_length() {
            self.remove_bucket(self.strings.current as u32)?;
            if self.strings.current == self.strings.last {
                self.strings.last = -1;
            }
            self.strings.current = -1;
            self.strings.changed = false;
        }
        let left = length - n;
        if left > 0 {
            let next = self.strings.next;
            self.strings.next = -1;
            self.str_remove(next, 0, left)?;
        }
        Ok(())
    }

    fn str_put_data(&mut self, mut data: &[u8]) -> Result<()> {
        while !data.is_empty() {
            let todo = data
                .len()
                .min((self.str_length() - self.strings.used) as usize);
            let at = self.strings.used as usize;
            self.strings.data[at..at + todo].copy_from_slice(&data[..todo]);
            data = &data[todo..];
            self.strings.deleted -= todo as i32;
            self.strings.used += todo as i32;
            self.strings.changed = true;
            if !data.is_empty() {
                self.str_new_bucket(true)?;
            }
        }
        Ok(())
    }

    fn str_replace_data(&mut self, offset: &mut i32, mut data: &[u8]) -> Result<()> {
        while !data.is_empty() {
            let n = data.len().min((self.str_length() - *offset) as usize);
            let at = *offset as usize;
            self.strings.data[at..at + n].copy_from_slice(&data[..n]);
            data = &data[n..];
            *offset += n as i32;
            self.strings.changed = true;
            if !data.is_empty() {
                *offset = 0;
                let next = self.strings.next;
                self.str_get_bucket(next, false)?;
            }
        }
        Ok(())
    }

    fn str_put(
        &mut self,
        bucket: &mut i32,
        offset: &mut i32,
        length: &mut i32,
        s: &[u8],
    ) -> Result<()> {
        let len = s.len() as i32;
        if *length > 0 && (len > *length || len == 0) {
            self.str_remove(*bucket, *offset, *length)?;
            (*bucket, *offset, *length) = (0, 0, 0);
        }
        if len == 0 {
            return Ok(());
        }
        if *length > 0 {
            if self.strings.current != *bucket {
                self.str_get_bucket(*bucket, false)?;
            }
            let mut at = *offset;
            self.str_replace_data(&mut at, s)?;
            if *length - len > 0 {
                let current = self.strings.current;
                self.str_remove(current, at, *length - len)?;
            }
            *length = len;
            return Ok(());
        }
        if self.strings.last == -1 {
            self.str_new_bucket(false)?;
        } else if self.strings.current != self.strings.last {
            let last = self.strings.last;
            self.str_get_bucket(last, false)?;
        }
        let room = self.str_length() - self.strings.used;
        if len > room && room < 50 {
            self.str_new_bucket(false)?;
        }
        *offset = self.strings.used;
        *bucket = self.strings.current;
        *length = len;
        self.str_put_data(s)
    }

    /// `SSMBase::writeIndex`.
    fn write_index(&mut self) -> Result<()> {
        let idx = serialise_ssm_index(&self.indices, self.h.big);
        let size = self.size();
        let ibs = size - 8;
        let mut nbuckets = idx.len() / ibs;
        let mut rest = idx.len() % ibs;
        if rest != 0 {
            nbuckets += 1;
        } else {
            rest = ibs;
        }
        if self.h.idx_bucket_offset > 0 && idx.len() <= ibs / 2 {
            self.h.idx_bucket_offset = if self.h.idx_bucket_offset == 8 {
                8 + (ibs / 2) as u32
            } else {
                8
            };
            let (first, at) = (
                self.h.first_idx_bucket as u32,
                self.h.idx_bucket_offset as usize,
            );
            self.bucket(first)?[at..at + idx.len()].copy_from_slice(&idx);
            self.set_dirty(first);
        } else {
            let mut old = -1i32;
            for i in (1..=nbuckets).rev() {
                let n = self.new_bucket()?;
                let bucket = self.bucket(n)?;
                bucket[..4].copy_from_slice(&old.to_be_bytes());
                bucket[4..8].copy_from_slice(&old.to_be_bytes());
                let from = (i - 1) * ibs;
                bucket[8..8 + rest].copy_from_slice(&idx[from..from + rest]);
                rest = ibs;
                old = n as i32;
            }
            let mut b = self.h.first_idx_bucket;
            while b != -1 {
                let next = be_i32(self.bucket(b as u32)?, 4);
                self.remove_bucket(b as u32)?;
                b = next;
            }
            self.h.first_idx_bucket = old;
            self.h.idx_bucket_offset = if idx.len() <= ibs / 2 { 8 } else { 0 };
        }
        self.h.nr_idx_buckets = nbuckets as u32;
        self.h.last_string_bucket = self.strings.last;
        self.h.idx_length = idx.len() as u32;
        self.h.nr_indices = self.indices.len() as u32;
        self.str_flush()?;
        self.cache_flush()
    }

    /// `SSMBase::flush`; returns whether the manager changed.
    fn flush(&mut self) -> Result<bool> {
        self.str_flush()?;
        // The cache writes its dirty buckets before the index is rewritten.
        self.cache_flush()?;
        let changed = self.changed;
        if changed {
            self.write_index()?;
        }
        let size = self.size() as u64;
        for &n in &self.dirty {
            write_at(
                &mut self.file,
                BUCKET_START + u64::from(n) * size,
                &self.buckets[&n],
            )?;
        }
        self.dirty.clear();
        if changed {
            let header = self.h.serialise();
            self.header_raw[..header.len()].copy_from_slice(&header);
            write_at(&mut self.file, 0, &header)?;
            self.event_write(0, header.len());
        }
        if let Some(a) = self.arrays.as_mut() {
            a.flush()?;
        }
        self.changed = false;
        Ok(changed)
    }

    /// External bytes per row as `SSMColumn::getExternalSizeBytes` rounds.
    fn add_column(&mut self, col: SsmCol, nrows: u64) -> Result<()> {
        let bits = col.bits;
        if bits == 0 {
            return err(format!(
                "{}: unsupported column for StandardStMan",
                col.name
            ));
        }
        // Best fit in the free space of the existing indices (`getFree`).
        let mut best: Option<(usize, i32, i32)> = None; // (index, offset, excess)
        'search: for (i, index) in self.indices.iter().enumerate() {
            let need = ((index.rows_per_bucket as usize * bits).div_ceil(8)) as i32;
            let mut local: Option<(i32, i32)> = None;
            for &(k, v) in &index.free {
                if v == need {
                    best = Some((i, k, 0));
                    break 'search;
                }
                if v >= need && local.is_none_or(|(_, lv)| v < lv) {
                    local = Some((k, v));
                }
            }
            if let Some((k, v)) = local {
                let excess = v - need;
                if best.is_none_or(|(_, _, e)| excess < e) {
                    best = Some((i, k, excess));
                }
            }
        }
        let rows_bytes = bits.div_ceil(8);
        match best {
            Some((i, offset, _)) => {
                let need = ((self.indices[i].rows_per_bucket as usize * bits).div_ceil(8)) as i32;
                let index = &mut self.indices[i];
                let v = index.free.iter().find(|f| f.0 == offset).unwrap().1;
                index.free.retain(|f| f.0 != offset);
                index.n_columns += 1;
                if v != need {
                    index.free.push((offset + need, v - need));
                    index.free.sort();
                }
                self.blob.col_index.push(i as u32);
                self.blob.col_offset.push(offset as u32);
                // `SSMColumn::addRow` with doInit: zero the slots.
                let buckets: Vec<(u32, u64, u64)> = {
                    let index = &self.indices[i];
                    (0..index.bucket.len())
                        .map(|k| {
                            let first = if k == 0 { 0 } else { index.last_row[k - 1] + 1 };
                            (index.bucket[k], first, index.last_row[k])
                        })
                        .collect()
                };
                for (b, first, last) in buckets {
                    let n = (last - first + 1) as usize * rows_bytes;
                    let bucket = self.bucket(b)?;
                    let end = (offset as usize + n).min(bucket.len());
                    bucket[offset as usize..end].fill(0);
                    self.set_dirty(b);
                }
            }
            None => {
                let size = self.size();
                let rpb = (size * 8 / bits) as u32;
                if rpb < 1 {
                    return err(format!("{}: bucket size too small", col.name));
                }
                let used = (rpb as usize * bits).div_ceil(8);
                let mut index = SsmIndexFull {
                    rows_per_bucket: rpb,
                    n_columns: 1,
                    free: Vec::new(),
                    last_row: Vec::new(),
                    bucket: Vec::new(),
                };
                if size > used {
                    index.free.push((used as i32, (size - used) as i32));
                }
                let mut row = 0u64;
                while row < nrows {
                    let n = (nrows - row).min(u64::from(rpb));
                    index.bucket.push(self.new_bucket()?);
                    row += n;
                    index.last_row.push(row - 1);
                }
                self.indices.push(index);
                self.blob.col_index.push(self.indices.len() as u32 - 1);
                self.blob.col_offset.push(0);
            }
        }
        let fixed = col.fixed.clone();
        let indirect = col.kind == SsmKind::Indirect;
        self.cols.push(col);
        self.changed = true;
        if indirect {
            self.arrays()?;
            if let Some(shape) = fixed {
                let k = self.cols.len() - 1;
                let dtype = self.cols[k].dtype;
                for row in 0..nrows {
                    let (b, at) = self.slot(k, row)?;
                    let array = self.arrays()?.put_res(&shape, dtype)?;
                    self.set_u64(b, at, array)?;
                    self.set_dirty(b);
                }
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// E4: cells, string arrays and rows of StandardStMan
// (research/e4-table-create.md), step for step as `SSMIndStringColumn`,
// `SSMStringHandler`, `SSMIndex::addRow/deleteRow` and the columns'
// `addRow`/`deleteRow` do.

/// One cell as read back: undefined, numeric values (native bytes, Bool one
/// byte each) or strings; shapes in casacore (Fortran) order.
#[derive(Clone, Debug, PartialEq)]
pub enum Cell {
    Undefined,
    Values(Vec<i64>, Vec<u8>),
    Strings(Vec<i64>, Vec<String>),
}

/// `Conversion::boolToBit` without a start bit: whole bytes from the first
/// one, the bits after the last value in its byte cleared.
pub(crate) fn bool_to_bits_from_zero(out: &mut [u8], src: &[u8]) {
    for (i, chunk) in src.chunks(8).enumerate() {
        let mut byte = 0u8;
        for (j, &v) in chunk.iter().enumerate() {
            byte |= u8::from(v != 0) << j;
        }
        out[i] = byte;
    }
}

pub(crate) fn get_bits(bytes: &[u8], start: usize, n: usize) -> Vec<u8> {
    (start..start + n)
        .map(|b| (bytes[b / 8] >> (b % 8)) & 1)
        .collect()
}

impl SsmW {
    /// Bytes per row of a column in a bucket (not for Bool).
    fn external_bytes(&self, col: usize) -> usize {
        self.cols[col].bits / 8
    }

    /// `getRowValue` of a 12-byte string slot: (bucket, offset, length).
    fn str_slot(&mut self, col: usize, row: u64) -> Result<[i32; 3]> {
        let (b, offset, first, _) = self.locate(col, row)?;
        let at = offset + first * 12;
        Ok([
            self.get_i32(b, at)?,
            self.get_i32(b, at + 4)?,
            self.get_i32(b, at + 8)?,
        ])
    }

    /// `putValue` of a 12-byte string slot.
    fn put_str_slot(&mut self, col: usize, row: u64, words: [i32; 3]) -> Result<()> {
        let (b, offset, first, _) = self.locate(col, row)?;
        let at = offset + first * 12;
        for (k, &w) in words.iter().enumerate() {
            self.set_i32(b, at + 4 * k, w)?;
        }
        self.set_dirty(b);
        Ok(())
    }

    /// The handler's bucket for appending: the last string bucket, or a new
    /// one when there is none.
    fn str_to_last(&mut self) -> Result<()> {
        if self.strings.last == -1 {
            self.str_new_bucket(false)
        } else if self.strings.current != self.strings.last {
            let last = self.strings.last;
            self.str_get_bucket(last, false)
        } else {
            Ok(())
        }
    }

    /// Append a record of `total` bytes: a new bucket when it does not fit
    /// and fewer than 50 bytes are left.
    fn str_append_at(&mut self, total: i32) -> Result<[i32; 3]> {
        self.str_to_last()?;
        let room = self.str_length() - self.strings.used;
        if total > room && room < 50 {
            self.str_new_bucket(false)?;
        }
        Ok([self.strings.current, self.strings.used, total])
    }

    fn str_shape_bytes(shape: &[i64], flag: i32) -> Vec<Vec<u8>> {
        let mut out = vec![(shape.len() as u32).to_be_bytes().to_vec()];
        out.extend(shape.iter().map(|&d| (d as i32).to_be_bytes().to_vec()));
        out.push(flag.to_be_bytes().to_vec());
        out
    }

    /// `SSMStringHandler::putShape`: ndim, the dimensions and a 0 flag.
    fn str_put_shape(&mut self, w: &mut [i32; 3], shape: &[i64]) -> Result<()> {
        self.str_to_last()?;
        let total = (shape.len() as i32 + 2) * 4;
        if w[2] > 0 && (total > w[2] || total == 0) {
            self.str_remove(w[0], w[1], w[2])?;
            *w = [0, 0, 0];
        }
        let parts = Self::str_shape_bytes(shape, 0);
        if w[2] > 0 {
            if self.strings.current != w[0] {
                self.str_get_bucket(w[0], false)?;
            }
            let mut offset = w[1];
            for p in &parts {
                self.str_replace_data(&mut offset, p)?;
            }
            if w[2] - total > 0 {
                let current = self.strings.current;
                self.str_remove(current, offset, w[2] - total)?;
            }
            w[2] = total;
            return Ok(());
        }
        *w = self.str_append_at(total)?;
        for p in &parts {
            self.str_put_data(p)?;
        }
        Ok(())
    }

    /// `SSMStringHandler::put` of a string array, with the shape and a 1
    /// flag first when `handle_shape`.
    fn str_put_array(
        &mut self,
        w: &mut [i32; 3],
        shape: &[i64],
        strings: &[String],
        handle_shape: bool,
    ) -> Result<()> {
        let mut total: i32 = strings.iter().map(|s| s.len() as i32 + 4).sum();
        if handle_shape {
            total += (shape.len() as i32 + 2) * 4;
        }
        if w[2] > 0 && (total > w[2] || total == 0) {
            self.str_remove(w[0], w[1], w[2])?;
            *w = [0, 0, 0];
        }
        if total == 0 {
            return Ok(());
        }
        let mut parts = if handle_shape {
            Self::str_shape_bytes(shape, 1)
        } else {
            Vec::new()
        };
        for s in strings {
            parts.push((s.len() as u32).to_be_bytes().to_vec());
            parts.push(s.as_bytes().to_vec());
        }
        if w[2] > 0 {
            if self.strings.current != w[0] {
                self.str_get_bucket(w[0], false)?;
            }
            let mut offset = w[1];
            for p in &parts {
                self.str_replace_data(&mut offset, p)?;
            }
            if w[2] - total > 0 {
                let current = self.strings.current;
                self.str_remove(current, offset, w[2] - total)?;
            }
            w[2] = total;
            return Ok(());
        }
        *w = self.str_append_at(total)?;
        for p in &parts {
            self.str_put_data(p)?;
        }
        Ok(())
    }

    /// `SSMStringHandler::getData`: `n` bytes from `offset`, following the
    /// bucket chain.
    fn str_get_data(&mut self, offset: &mut i32, mut n: usize) -> Result<Vec<u8>> {
        let mut out = Vec::with_capacity(n);
        while n > 0 {
            let avail = (self.strings.used - *offset).max(0) as usize;
            let take = n.min(avail);
            let at = *offset as usize;
            out.extend_from_slice(&self.strings.data[at..at + take]);
            n -= take;
            *offset += take as i32;
            if n > 0 {
                let next = self.strings.next;
                if next < 0 {
                    return err("string bucket chain ends early");
                }
                self.str_get_bucket(next, false)?;
                *offset = 0;
            }
        }
        Ok(out)
    }

    fn str_get_int(&mut self, offset: &mut i32) -> Result<i32> {
        Ok(i32::from_be_bytes(
            self.str_get_data(offset, 4)?.try_into().unwrap(),
        ))
    }

    /// `SSMStringHandler::getShape` (moves the offset past the shape).
    fn str_get_shape(&mut self, w: [i32; 3], offset: &mut i32) -> Result<Vec<i64>> {
        if self.strings.current != w[0] {
            self.str_get_bucket(w[0], false)?;
        }
        *offset = w[1];
        let ndim = self.str_get_int(offset)?.max(0) as usize;
        let mut shape = Vec::with_capacity(ndim);
        for _ in 0..ndim {
            shape.push(i64::from(self.str_get_int(offset)?));
        }
        Ok(shape)
    }

    /// `SSMStringHandler::get` of a string array.
    fn str_get_array(
        &mut self,
        w: [i32; 3],
        fixed: Option<&[i64]>,
    ) -> Result<(Vec<i64>, Vec<String>)> {
        let mut shape = fixed.map(<[i64]>::to_vec).unwrap_or_default();
        let mut filled = 0;
        let mut offset = w[1];
        if w[2] > 0 {
            if self.strings.current != w[0] {
                self.str_get_bucket(w[0], false)?;
            }
            filled = 1;
            if fixed.is_none() {
                shape = self.str_get_shape(w, &mut offset)?;
                filled = self.str_get_int(&mut offset)?;
            }
        }
        let n = product(&shape);
        let mut strings = Vec::with_capacity(n);
        for _ in 0..n {
            if filled == 0 {
                strings.push(String::new());
            } else {
                let len = self.str_get_int(&mut offset)?.max(0) as usize;
                let bytes = self.str_get_data(&mut offset, len)?;
                strings.push(String::from_utf8_lossy(&bytes).into_owned());
            }
        }
        Ok((shape, strings))
    }

    /// Whether a row of an array column has a value (`isShapeDefined`).
    fn is_defined(&mut self, col: usize, row: u64) -> Result<bool> {
        let c = self.cols[col].clone();
        match c.kind {
            SsmKind::Indirect => {
                let (b, at) = self.slot(col, row)?;
                Ok(self.get_u64(b, at)? != 0)
            }
            SsmKind::StrArray if c.fixed.is_none() => Ok(self.str_slot(col, row)?[2] != 0),
            _ => Ok(true),
        }
    }

    /// `setShape` of a variable-shape string-array row unless it has this
    /// shape already.
    fn set_string_shape(&mut self, col: usize, row: u64, shape: &[i64]) -> Result<()> {
        let w = self.str_slot(col, row)?;
        let same = w[2] != 0 && {
            let mut offset = 0;
            self.str_get_shape(w, &mut offset)? == shape
        };
        if !same {
            let mut w = self.str_slot(col, row)?;
            self.str_put_shape(&mut w, shape)?;
            self.put_str_slot(col, row, w)?;
        }
        Ok(())
    }

    /// `putColumn` of a string-array column: shapes first (variable-shape
    /// columns), then the values, row by row.
    fn put_string_column(
        &mut self,
        col: usize,
        start: u64,
        count: u64,
        shape: &[i64],
        strings: &[String],
    ) -> Result<()> {
        let n = product(shape);
        if strings.len() != n * count as usize {
            return err("string count mismatches the rows and cell shape");
        }
        if self.cols[col].fixed.is_none() {
            for i in 0..count {
                self.set_string_shape(col, start + i, shape)?;
            }
        }
        for i in 0..count {
            let cell = &strings[i as usize * n..(i as usize + 1) * n];
            let mut w = self.str_slot(col, start + i)?;
            let handle_shape = self.cols[col].fixed.is_none();
            self.str_put_array(&mut w, shape, cell, handle_shape)?;
            self.put_str_slot(col, start + i, w)?;
        }
        Ok(())
    }

    /// Read one cell of an indirect or string-array column (others are
    /// read with the task E reader).
    fn read_cell(&mut self, col: usize, row: u64) -> Result<Cell> {
        let c = self.cols[col].clone();
        match c.kind {
            SsmKind::Indirect => {
                let (b, at) = self.slot(col, row)?;
                let offset = self.get_u64(b, at)?;
                if offset == 0 {
                    return Ok(Cell::Undefined);
                }
                let big = self.h.big;
                let mut file = File::open(&self.array_path)?;
                let version = read_order_u32(&read_at(&mut file, 0, 4)?, big);
                let mut at = offset + if version > 0 { 4 } else { 0 };
                let ndim = read_order_u32(&read_at(&mut file, at, 4)?, big) as usize;
                let dims = read_at(&mut file, at + 4, 4 * ndim)?;
                let shape: Vec<i64> = dims
                    .chunks_exact(4)
                    .map(|d| i64::from(read_order_u32(d, big) as i32))
                    .collect();
                at += 4 + 4 * ndim as u64;
                let n = product(&shape);
                let values = if c.dtype == DataType::Bool {
                    get_bits(&read_at(&mut file, at, n.div_ceil(8))?, 0, n)
                } else {
                    to_order(c.dtype, &read_at(&mut file, at, n * c.dtype.size())?, big)
                };
                Ok(Cell::Values(shape, values))
            }
            SsmKind::StrArray => {
                let w = self.str_slot(col, row)?;
                if c.fixed.is_none() && w[2] == 0 {
                    return Ok(Cell::Undefined);
                }
                let (shape, strings) = self.str_get_array(w, c.fixed.as_deref())?;
                Ok(Cell::Strings(shape, strings))
            }
            _ => err(format!(
                "{}: read cells of this column with the reader",
                c.name
            )),
        }
    }

    /// `SSMIndex::addRow` of index `i`: fill the last bucket, then new ones.
    fn index_add_rows(&mut self, i: usize, mut n: u64) -> Result<()> {
        if n == 0 {
            return Ok(());
        }
        let rpb = u64::from(self.indices[i].rows_per_bucket);
        let mut last_row = 0u64;
        {
            let index = &mut self.indices[i];
            let used = index.last_row.len();
            if used > 0 {
                last_row = index.last_row[used - 1] + 1;
                let mut in_last = last_row;
                if used > 1 {
                    in_last -= index.last_row[used - 2] + 1;
                }
                let add = (rpb - in_last).min(n);
                index.last_row[used - 1] += add;
                n -= add;
                last_row += add;
            }
        }
        while n > 0 {
            let b = self.new_bucket()?;
            let add = n.min(rpb);
            last_row += add;
            n -= add;
            self.indices[i].bucket.push(b);
            self.indices[i].last_row.push(last_row - 1);
        }
        Ok(())
    }

    /// `SSMBase::addRow64`: the indices, then the columns' `addRow` (a
    /// FixedShape indirect column gets an array for every new row).
    fn add_rows(&mut self, old: u64, n: u64) -> Result<()> {
        self.cache_ready()?;
        for i in 0..self.indices.len() {
            self.index_add_rows(i, n)?;
        }
        for k in 0..self.cols.len() {
            if let (SsmKind::Indirect, Some(shape)) =
                (self.cols[k].kind, self.cols[k].fixed.clone())
            {
                let dtype = self.cols[k].dtype;
                for row in old..old + n {
                    let (b, at) = self.slot(k, row)?;
                    let current = self.get_u64(b, at)?;
                    if current != 0 && self.arrays()?.shape(current)?.0 == shape {
                        continue;
                    }
                    let array = self.arrays()?.put_res(&shape, dtype)?;
                    self.set_u64(b, at, array)?;
                    self.set_dirty(b);
                }
            }
        }
        self.changed = true;
        Ok(())
    }

    /// `SSMColumn::shiftRows`: the slots after `first` move one to the left
    /// in the bucket and the last one is cleared.
    fn shift_rows(
        &mut self,
        b: u32,
        offset: usize,
        first: usize,
        last: usize,
        ext: usize,
    ) -> Result<()> {
        let bucket = self.bucket(b)?;
        let to = offset + first * ext;
        let len = (last - first) * ext;
        bucket.copy_within(to + ext..to + ext + len, to);
        bucket[to + len..to + len + ext].fill(0);
        self.set_dirty(b);
        Ok(())
    }

    /// The columns' `deleteRow` for one column.
    fn delete_row_in(&mut self, col: usize, row: u64) -> Result<()> {
        let c = self.cols[col].clone();
        let (b, offset, first, end) = self.locate(col, row)?;
        let start = row - first as u64;
        let last = (end - start) as usize;
        if c.kind == SsmKind::String {
            let w = self.str_slot(col, row)?;
            if w[2] > 8 {
                self.str_remove(w[0], w[1], w[2])?;
                return self.shift_rows(b, offset, first, last, 12);
            }
        }
        self.bucket(b)?;
        if row >= end {
            return Ok(());
        }
        match (c.kind, c.dtype) {
            (SsmKind::Scalar, DataType::Bool) => {
                // `getBool` caches the bucket's values; the cache without
                // the row is written back from bit 0 (`boolToBit`).
                let bucket = self.bucket(b)?;
                let mut values = get_bits(&bucket[offset..], 0, last + 1);
                values.remove(first);
                bool_to_bits_from_zero(&mut bucket[offset..], &values[..last]);
                self.set_dirty(b);
            }
            (SsmKind::Direct(nelem), DataType::Bool) => {
                let bucket = self.bucket(b)?;
                let values = get_bits(
                    &bucket[offset..],
                    (first + 1) * nelem,
                    (last - first) * nelem,
                );
                put_bits(&mut bucket[offset..], first * nelem, &values);
                self.set_dirty(b);
            }
            _ => {
                let ext = self.external_bytes(col);
                self.shift_rows(b, offset, first, last, ext)?;
            }
        }
        Ok(())
    }

    /// `SSMIndex::deleteRow`: the bucket that became empty, if any.
    fn index_delete_row(&mut self, i: usize, row: u64) -> Option<u32> {
        let index = &mut self.indices[i];
        let at = index.last_row.partition_point(|&l| l < row);
        let mut empty = false;
        for l in &mut index.last_row[at..] {
            if *l > 0 {
                *l -= 1;
            } else {
                empty = true;
            }
        }
        let before = if at > 0 {
            index.last_row[at - 1] as i64
        } else {
            -1
        };
        if index.last_row[at] as i64 == before || empty {
            index.last_row.remove(at);
            Some(index.bucket.remove(at))
        } else {
            None
        }
    }

    /// `SSMBase::removeRow64` of one row; `nrows` is the row count before.
    fn remove_row(&mut self, row: u64, nrows: u64) -> Result<()> {
        if nrows <= 1 {
            // What the deletes would write goes with the old file.
            return self.recreate();
        }
        for k in 0..self.cols.len() {
            self.delete_row_in(k, row)?;
        }
        for i in 0..self.indices.len() {
            if let Some(b) = self.index_delete_row(i, row) {
                self.remove_bucket(b)?;
            }
        }
        self.changed = true;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tiled writes.

/// The part a column plays in a hypercolumn (`TiledStMan::setup`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum TsmRole {
    /// A data column, its values in the tiles.
    Data,
    /// The coordinate of hypercube axis `n`, kept in each cube's record.
    Coord(usize),
    /// An id column, kept in each cube's record.
    Id,
}

/// One cell's place: its hypercube and its position on the axes after the
/// cell axes (the row axes; none for a TiledCellStMan).
type Place = (usize, Vec<i64>);

struct TsmW {
    dir: PathBuf,
    h: TsmHeader,
    /// The columns' roles and names (header column order).
    roles: Vec<TsmRole>,
    names: Vec<String>,
    /// Data columns' rank in a tile (descending pixel size, stable).
    rank: Vec<usize>,
    /// The cell dimensionality (`nrCoordVector_p`).
    ncell: usize,
    files: BTreeMap<usize, File>,
    changed: bool,
    write_header: bool,
    /// The FixedShape cell shape of the data columns (adding rows makes
    /// their cubes); None for variable-shape ones.
    fixed_cell: Option<Vec<i64>>,
    /// Tiles written since the last flush, by (tile file, offset): the
    /// cubes' caches, written at the manager's flush.
    pending: BTreeMap<(usize, u64), Vec<u8>>,
    /// The write log of a MultiFile table and each tile file's length at
    /// the last flush.
    mf: Option<crate::multifile::MfLog>,
    flushed: BTreeMap<usize, u64>,
    /// The hypercubes' tile caches (`TSMCube::cache_p`) and each tile
    /// file's physical size as casacore has written it.
    caches: BTreeMap<usize, TileCache>,
    phys: BTreeMap<usize, u64>,
}

impl TsmW {
    fn open(dir: &Path, seq: u32) -> Result<Self> {
        let h = TsmHeader::parse(&std::fs::read(dir.join(format!("table.f{seq}")))?)?;
        let n = h.dtypes.len();
        let mut t = Self::with_header(dir, h, vec![TsmRole::Data; n], vec![String::new(); n]);
        for (i, f) in t.h.files.iter().enumerate() {
            if let Some(f) = f {
                t.flushed.insert(i, f.length);
                let path = dir.join(format!("table.f{seq}_TSM{}", f.seq));
                t.phys
                    .insert(i, std::fs::metadata(path).map_or(0, |m| m.len()));
            }
        }
        Ok(t)
    }

    /// A MultiFile event of this manager's file `name`.
    fn event(&self, e: crate::multifile::Event) {
        crate::multifile::emit(&self.mf, e);
    }

    fn tile_name(&self, file: usize) -> String {
        let seq = self.h.files[file].as_ref().map_or(file as u32, |f| f.seq);
        format!("table.f{}_TSM{seq}", self.h.seq)
    }

    fn with_header(dir: &Path, h: TsmHeader, roles: Vec<TsmRole>, names: Vec<String>) -> Self {
        let size = |c: usize| {
            DataType::from_code(h.dtypes[c])
                .map(|d| d.size())
                .unwrap_or(0)
        };
        let data: Vec<usize> = (0..h.dtypes.len())
            .filter(|&c| roles[c] == TsmRole::Data)
            .collect();
        let mut order = data.clone();
        order.sort_by_key(|&c| std::cmp::Reverse(size(c)));
        let mut rank = vec![usize::MAX; h.dtypes.len()];
        for (r, &c) in order.iter().enumerate() {
            rank[c] = r;
        }
        let ncell = if h.is_cell() {
            h.nrdim as usize
        } else {
            (h.nrdim as usize).saturating_sub(1)
        };
        TsmW {
            dir: dir.to_path_buf(),
            h,
            roles,
            names,
            rank,
            ncell,
            files: BTreeMap::new(),
            changed: false,
            write_header: false,
            fixed_cell: None,
            pending: BTreeMap::new(),
            mf: crate::multifile::current(),
            flushed: BTreeMap::new(),
            caches: BTreeMap::new(),
            phys: BTreeMap::new(),
        }
    }

    /// Set the columns' roles, names and the cell dimensionality (from the
    /// hypercolumn definition; a TiledDataStMan's cells may have fewer axes
    /// than its hypercube minus one).
    fn set_columns(&mut self, roles: Vec<TsmRole>, names: Vec<String>, ncell: Option<usize>) {
        let h = std::mem::replace(&mut self.h, TsmHeader::parse_empty());
        let fixed = self.fixed_cell.take();
        let flushed = std::mem::take(&mut self.flushed);
        let phys = std::mem::take(&mut self.phys);
        *self = Self::with_header(&self.dir.clone(), h, roles, names);
        self.fixed_cell = fixed;
        self.flushed = flushed;
        self.phys = phys;
        if let Some(n) = ncell {
            self.ncell = n;
        }
    }

    /// A new TiledColumnStMan (`column`) or TiledShapeStMan with FixedShape
    /// columns of `cell` (casacore order), tile shape `tile` (cell axes
    /// then rows; empty or shorter: computed as casacore does), no rows yet
    /// (`create64`; rows come with `add_rows`).
    #[allow(clippy::too_many_arguments)]
    fn create(
        dir: &Path,
        seq: u32,
        column: bool,
        name: &str,
        dtypes: Vec<i32>,
        fixed: Option<Vec<i64>>,
        ndim: usize,
        tile: Vec<i64>,
        big: bool,
    ) -> Result<Self> {
        if tile.len() > ndim + 1 || tile.iter().any(|&t| t < 0) {
            return err(format!(
                "{name}: give a tile shape of at most {} axes of 0 or more (cell axes, then rows)",
                ndim + 1
            ));
        }
        let cell = fixed.clone().unwrap_or_default();
        let kind = if column {
            "TiledColumnStMan"
        } else {
            "TiledShapeStMan"
        };
        let mut h = TsmHeader::new(kind, seq, name, dtypes, ndim as u32 + 1, big);
        h.column_tile = column.then(|| tile.clone());
        h.files = vec![None];
        if !column {
            h.default_tile = tile.clone();
        }
        let n = h.dtypes.len();
        let mut t = Self::with_header(dir, h, vec![TsmRole::Data; n], vec![String::new(); n]);
        if column {
            t.h.files = vec![Some(TsmFileEntry { seq: 0, length: 0 })];
            let mut shape = cell.clone();
            shape.push(0);
            t.h.cubes = vec![Self::new_cube(&shape, &tile, 0, 0, empty_values_record())];
            File::create(dir.join(format!("table.f{seq}_TSM0")))?;
            crate::multifile::emit(
                &crate::multifile::current(),
                crate::multifile::Event::Create(format!("table.f{seq}_TSM0")),
            );
        } else {
            t.h.cubes = vec![TsmCube {
                values: empty_values_record(),
                extensible: false,
                nrdim: 0,
                shape: Vec::new(),
                tile: Vec::new(),
                file_seq: -1,
                offset: 0,
            }];
        }
        t.fixed_cell = fixed;
        t.write_header = true;
        t.changed = true;
        Ok(t)
    }

    /// A new TiledCellStMan (`create64`: tile file 0 created; rows come
    /// with `add_rows`, each with its own hypercube).
    #[allow(clippy::too_many_arguments)]
    fn create_cell(
        dir: &Path,
        seq: u32,
        name: &str,
        dtypes: Vec<i32>,
        fixed: Option<Vec<i64>>,
        ndim: usize,
        tile: Vec<i64>,
        big: bool,
    ) -> Result<Self> {
        let mut h = TsmHeader::new("TiledCellStMan", seq, name, dtypes, ndim as u32, big);
        h.column_tile = Some(tile);
        h.files = vec![Some(TsmFileEntry { seq: 0, length: 0 })];
        File::create(dir.join(format!("table.f{seq}_TSM0")))?;
        let n = h.dtypes.len();
        crate::multifile::emit(
            &crate::multifile::current(),
            crate::multifile::Event::Create(format!("table.f{seq}_TSM0")),
        );
        let mut t = Self::with_header(dir, h, vec![TsmRole::Data; n], vec![String::new(); n]);
        t.fixed_cell = fixed;
        t.write_header = true;
        t.changed = true;
        Ok(t)
    }

    /// A new TiledDataStMan (`create64`: no file and no hypercube; rows
    /// come with `add_rows`, hypercubes with `add_hypercube`).
    #[allow(clippy::too_many_arguments)]
    fn create_data(
        dir: &Path,
        seq: u32,
        name: &str,
        dtypes: Vec<i32>,
        roles: Vec<TsmRole>,
        names: Vec<String>,
        nrdim: u32,
        ncell: usize,
        big: bool,
    ) -> Self {
        let mut h = TsmHeader::new("TiledDataStMan", seq, name, dtypes, nrdim, big);
        h.files = vec![None];
        let mut t = Self::with_header(dir, h, roles, names);
        t.ncell = ncell;
        t.write_header = true;
        t.changed = true;
        t
    }

    /// A hypercube of `shape` (an extensible one has 0 rows on its last
    /// axis) at `offset` of tile file `file_seq`, its tile shape adjusted
    /// as `TSMCube::setShape` does.
    fn new_cube(
        shape: &[i64],
        tile: &[i64],
        file_seq: i32,
        offset: u64,
        values: Vec<u8>,
    ) -> TsmCube {
        let last = shape.len() - 1;
        TsmCube {
            values,
            extensible: shape[last] == 0,
            nrdim: shape.len() as u32,
            shape: shape.to_vec(),
            tile: crate::tiled::adjust_tile_shape(shape, tile),
            file_seq,
            offset,
        }
    }

    fn ntiles(cube: &TsmCube) -> u64 {
        cube.shape
            .iter()
            .zip(&cube.tile)
            .map(|(&s, &t)| ((s + t - 1) / t) as u64)
            .product()
    }

    /// Grow tile file `file` by `bytes` (`TSMFile::extend`; the new tiles
    /// are zeros, as casacore's cache initialises them).
    fn extend_file(&mut self, file: usize, bytes: u64) -> Result<u64> {
        let entry = self.h.files[file]
            .as_mut()
            .ok_or_else(|| MsError("hypercube without a tile file".into()))?;
        let at = entry.length;
        entry.length += bytes;
        let length = entry.length;
        let path = self
            .dir
            .join(format!("table.f{}_TSM{}", self.h.seq, entry.seq));
        let f = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&path)?;
        if f.metadata()?.len() < length {
            f.set_len(length)?;
        }
        Ok(at)
    }

    /// `TSMCube::extend` of cube `index` by `n` on its last axis.
    fn extend_cube(&mut self, index: usize, n: u64) -> Result<()> {
        // `TSMCube::extend`: the cache is made first, then extended.
        self.make_cache(index);
        let old = Self::ntiles(&self.h.cubes[index]);
        let cube = &mut self.h.cubes[index];
        let last = cube.shape.len() - 1;
        cube.shape[last] += n as i64;
        let cube = cube.clone();
        let new = Self::ntiles(&cube);
        let bucket = self.bucket_size(&cube) as u64;
        self.caches.get_mut(&index).unwrap().new += new - old;
        self.extend_file(cube.file_seq as usize, (new - old) * bucket)?;
        Ok(())
    }

    /// `addRow64` of each manager.
    fn add_rows(&mut self, n: u64) -> Result<()> {
        if n == 0 {
            return Ok(());
        }
        let old = self.h.nrows;
        if self.h.nrows + n > 0x7fff_ffff {
            return err("tiled managers of 2^31 rows or more are not supported");
        }
        self.h.nrows += n;
        if self.h.is_column() {
            self.extend_cube(0, n)?;
        } else if self.h.is_shape() {
            if let Some(cell) = self.fixed_cell.clone() {
                for row in old..old + n {
                    self.set_shape(row, &cell)?;
                }
            }
        } else if self.h.is_cell() {
            for row in old..old + n {
                self.h.cubes.push(TsmCube {
                    values: empty_values_record(),
                    extensible: false,
                    nrdim: 0,
                    shape: Vec::new(),
                    tile: Vec::new(),
                    file_seq: 0,
                    offset: 0,
                });
                if let Some(cell) = self.fixed_cell.clone() {
                    self.set_cell_shape(row, &cell)?;
                }
            }
        }
        self.write_header = true;
        self.changed = true;
        Ok(())
    }

    /// The cube of a TiledShapeStMan row (0: none) and its position.
    pub(crate) fn cube_of(&self, row: u64) -> (usize, i64) {
        let h = &self.h;
        if h.row_map.is_empty() || row > u64::from(*h.row_map.last().unwrap()) {
            return (0, 0);
        }
        let i = h.row_map.partition_point(|&r| u64::from(r) < row);
        let cube = h.cube_map[i] as usize;
        (
            cube,
            i64::from(h.pos_map[i]) - (i64::from(h.row_map[i]) - row as i64),
        )
    }

    /// Where a row's cell is (`getHypercube(rownr, position)`); None for a
    /// row without a hypercube.
    fn place(&self, row: u64) -> Result<Option<Place>> {
        let h = &self.h;
        if row >= h.nrows {
            return err(format!(
                "row {row} beyond the {} rows of {}",
                h.nrows, h.hypercolumn
            ));
        }
        if h.is_column() {
            return Ok(Some((0, vec![row as i64])));
        }
        if h.is_shape() {
            return Ok(match self.cube_of(row) {
                (0, _) => None,
                (c, p) => Some((c, vec![p])),
            });
        }
        if h.is_cell() {
            let r = row as usize;
            return Ok((h.cubes.get(r).is_some_and(|c| c.nrdim > 0)).then(|| (r, Vec::new())));
        }
        // TiledDataStMan.
        if row >= h.nrrow_last {
            return Ok(None);
        }
        let i = h.data_row_map.partition_point(|&r| r <= row) - 1;
        let cube = h.cube_map[i] as usize;
        let shape = &h.cubes[cube].shape;
        let nrdim = shape.len();
        let mut diff = row - h.data_row_map[i];
        let mut pos = Vec::with_capacity(nrdim - self.ncell);
        for &s in &shape[self.ncell..nrdim - 1] {
            pos.push((diff % s as u64) as i64);
            diff /= s as u64;
        }
        pos.push(diff as i64 + i64::from(h.pos_map[i]));
        Ok(Some((cube, pos)))
    }

    /// The cell shape of a row (None: no hypercube).
    pub(crate) fn cell_shape(&self, row: u64) -> Option<Vec<i64>> {
        let (cube, _) = self.place(row).ok()??;
        Some(self.h.cubes[cube].shape[..self.ncell].to_vec())
    }

    /// `TiledShapeStMan::setShape` of a row without a hypercube: extend the
    /// hypercube of this cell shape, or add one (with its own tile file),
    /// then `updateRowMap`.
    pub(crate) fn set_shape(&mut self, row: u64, shape: &[i64]) -> Result<()> {
        if row >= self.h.nrows {
            return err("TiledShapeStMan::updateRowMap: rownr is too high");
        }
        if shape.len() + 1 != self.h.nrdim as usize || shape.iter().any(|&s| s < 1) {
            return err(format!(
                "cell shape {shape:?} does not fit the {}-dimensional hypercolumn",
                self.h.nrdim
            ));
        }
        let found = (1..self.h.cubes.len()).find(|&i| {
            let c = &self.h.cubes[i].shape;
            c.len() == shape.len() + 1 && c[..shape.len()] == *shape
        });
        let index = match found {
            Some(i) => i,
            None => {
                let file = self.h.files.len();
                self.h.files.push(Some(TsmFileEntry {
                    seq: file as u32,
                    length: 0,
                }));
                File::create(self.dir.join(format!("table.f{}_TSM{file}", self.h.seq)))?;
                self.event(crate::multifile::Event::Create(format!(
                    "table.f{}_TSM{file}",
                    self.h.seq
                )));
                let mut cube_shape = shape.to_vec();
                cube_shape.push(0);
                let tile = self.h.default_tile.clone();
                let values = self.h.cubes[0].values.clone();
                self.h
                    .cubes
                    .push(Self::new_cube(&cube_shape, &tile, file as i32, 0, values));
                let c = self.h.cubes.len() - 1;
                self.make_cache(c);
                c
            }
        };
        let pos = *self.h.cubes[index].shape.last().unwrap() as u32;
        self.extend_cube(index, 1)?;
        self.update_row_map(index as u32, pos, row as u32);
        self.h.cubes[0].values = empty_values_record();
        self.write_header = true;
        self.changed = true;
        Ok(())
    }

    /// `TiledCellStMan::setShape` (`TSMCube::setShape` of the row's cube):
    /// the cube gets `shape` and new tiles at the end of tile file 0; a
    /// cube that had a shape leaves its old tiles in the file.
    pub(crate) fn set_cell_shape(&mut self, row: u64, shape: &[i64]) -> Result<()> {
        if shape.len() != self.h.nrdim as usize || shape.iter().any(|&s| s < 1) {
            return err(format!(
                "cell shape {shape:?} does not fit the {}-dimensional hypercolumn",
                self.h.nrdim
            ));
        }
        let tile = self.h.column_tile.clone().unwrap_or_default();
        let r = row as usize;
        let offset = self.h.files[0].as_ref().map_or(0, |f| f.length);
        let mut cube = self.h.cubes[r].clone();
        // `TSMCube::setShape`: the cube's cache is deleted unflushed (what
        // was put into the old shape since then is lost), a new one made.
        self.delete_cache(r);
        cube.nrdim = shape.len() as u32;
        cube.shape = shape.to_vec();
        cube.tile = crate::tiled::adjust_tile_shape(shape, &tile);
        cube.offset = offset;
        let bytes = Self::ntiles(&cube) * self.bucket_size(&cube) as u64;
        self.h.cubes[r] = cube;
        self.make_cache(r);
        self.extend_file(0, bytes)?;
        self.write_header = true;
        self.changed = true;
        Ok(())
    }

    /// `TiledShapeStMan::updateRowMap`.
    fn update_row_map(&mut self, cube: u32, pos: u32, row: u32) {
        let h = &mut self.h;
        let n = h.row_map.len();
        let next = if n > 0 { 1 + h.row_map[n - 1] } else { 0 };
        if row >= next {
            if cube == 0 {
                return;
            }
            if row == next && n > 0 {
                let i = n - 1;
                if cube == h.cube_map[i] && pos == 1 + h.pos_map[i] {
                    h.row_map[i] += 1;
                    h.pos_map[i] += 1;
                    return;
                }
            }
            if row > next {
                h.row_map.push(row - 1);
                h.cube_map.push(0);
                h.pos_map.push(0);
            }
            h.row_map.push(row);
            h.cube_map.push(cube);
            h.pos_map.push(pos);
            return;
        }
        let index = h.row_map.partition_point(|&r| r < row);
        let found = h.row_map[index] == row;
        let diff = h.row_map[index] - row;
        if cube == h.cube_map[index] && pos == h.pos_map[index].wrapping_sub(diff) {
            return;
        }
        let at_b = row == 0 || (index > 0 && row - 1 == h.row_map[index - 1]);
        let at_e = found;
        let mut eq_p = false;
        let mut eq_n = false;
        if at_e && index + 1 < n {
            let fpos = h.pos_map[index + 1].wrapping_sub(h.row_map[index + 1] - h.row_map[index]);
            eq_n = cube == h.cube_map[index + 1] && pos == fpos;
        }
        if at_b && index > 0 {
            eq_p = cube == h.cube_map[index - 1] && pos == 1 + h.pos_map[index - 1];
        }
        if at_b && at_e {
            h.cube_map[index] = cube;
            h.pos_map[index] = pos;
            let mut index = index;
            let mut nm = 0;
            if eq_n {
                nm += 1;
            }
            if eq_p {
                nm += 1;
                index -= 1;
            }
            if nm > 0 {
                h.row_map.drain(index..index + nm);
                h.cube_map.drain(index..index + nm);
                h.pos_map.drain(index..index + nm);
            }
            return;
        }
        if eq_p {
            h.row_map[index - 1] += 1;
            h.pos_map[index - 1] += 1;
            return;
        }
        if eq_n {
            h.row_map[index] -= 1;
            h.pos_map[index] -= 1;
            return;
        }
        let nm = if at_b || at_e { 1 } else { 2 };
        for _ in 0..nm {
            h.row_map.insert(index, 0);
            h.cube_map.insert(index, 0);
            h.pos_map.insert(index, 0);
        }
        // The old entry moved to index + nm; the new ones are at index.
        let (r, c, p) = (
            h.row_map[index + nm],
            h.cube_map[index + nm],
            h.pos_map[index + nm],
        );
        let mut index = index;
        if !at_b {
            h.row_map[index] = r;
            h.cube_map[index] = c;
            h.pos_map[index] = p;
            if at_e {
                h.row_map[index] -= 1;
                h.pos_map[index] -= 1;
            } else {
                h.pos_map[index] = h.pos_map[index].wrapping_sub(diff + 1);
                h.row_map[index] = row - 1;
            }
            index += 1;
        }
        h.row_map[index] = row;
        h.cube_map[index] = cube;
        h.pos_map[index] = pos;
    }

    // -- TiledDataStMan hypercubes (`TiledDataStManAccessor`) ---------------

    fn coord_columns(&self) -> Vec<(usize, usize)> {
        let mut out: Vec<(usize, usize)> = self
            .roles
            .iter()
            .enumerate()
            .filter_map(|(c, r)| match r {
                TsmRole::Coord(axis) => Some((*axis, c)),
                _ => None,
            })
            .collect();
        out.sort_unstable();
        out
    }

    /// `TSMCube::extendCoordinates`: the coordinate vector of column `c`
    /// grows to `length` (zeros), its last values set from `given` (when
    /// it has the field).
    fn extend_coordinates(
        rec: &mut crate::aipsio::Record,
        name: &str,
        code: i32,
        length: i64,
        given: Option<&crate::aipsio::Record>,
    ) -> Result<()> {
        let current = crate::tiled::array_field(rec, name);
        let have = current
            .as_ref()
            .map_or(0, |(_, s, _)| s.first().copied().unwrap_or(0));
        let extra = length - have;
        if extra == 0 {
            return Ok(());
        }
        let (code, mut native) = match current {
            Some((field_code, _, raw)) => {
                let scalar = crate::aipsio::tp::scalar_of(field_code).unwrap_or(code);
                let dt = DataType::from_code(scalar)?;
                (scalar, to_order(dt, &raw, true))
            }
            None => (code, Vec::new()),
        };
        let dt = DataType::from_code(code)?;
        native.resize(length as usize * dt.size(), 0);
        if let Some(g) = given
            && let Some((_, gshape, graw)) = crate::tiled::array_field(g, name)
        {
            let n = gshape.first().copied().unwrap_or(0);
            let start = (length - n) as usize * dt.size();
            let g = to_order(dt, &graw, true);
            native[start..start + g.len()].copy_from_slice(&g);
        }
        crate::tiled::define_array(rec, name, code, &[length], &native)
    }

    /// `TiledStMan::getCubeIndex`: the hypercube whose id values equal
    /// those given (the one cube when there are no id columns).
    fn cube_index(&self, values: &crate::aipsio::Record) -> Result<Option<usize>> {
        let ids: Vec<usize> = (0..self.roles.len())
            .filter(|&c| self.roles[c] == TsmRole::Id)
            .collect();
        if ids.is_empty() {
            return Ok((!self.h.cubes.is_empty()).then_some(0));
        }
        for (i, cube) in self.h.cubes.iter().enumerate() {
            let rec = crate::tiled::parse_values(&cube.values)?;
            let same = ids.iter().all(|&c| {
                let name = &self.names[c];
                match (rec.field(name), values.field(name)) {
                    (Some(a), Some(b)) => rec.values[a] == values.values[b],
                    _ => false,
                }
            });
            if same {
                return Ok(Some(i));
            }
        }
        Ok(None)
    }

    /// `TiledDataStMan::addHypercube(shape, tileShape, values)`.
    pub(crate) fn add_hypercube(
        &mut self,
        shape: &[i64],
        tile: &[i64],
        values: crate::aipsio::Record,
    ) -> Result<()> {
        if !self.h.is_data() {
            return err("hypercubes are added to a TiledDataStMan only");
        }
        let nrdim = self.h.nrdim as usize;
        if shape.len() != nrdim || shape[..nrdim - 1].iter().any(|&s| s < 1) || shape[nrdim - 1] < 0
        {
            return err(format!(
                "addHypercube dimensionality mismatch in {}",
                self.h.hypercolumn
            ));
        }
        let rows = self.added_rows(shape, shape[nrdim - 1] as u64);
        if self.h.nrrow_last + rows > self.h.nrows {
            return err("Insufficient #rows in table for add/extendHypercube");
        }
        for c in 0..self.roles.len() {
            if self.roles[c] == TsmRole::Id && values.field(&self.names[c]).is_none() {
                return err(format!("No value given for column {}", self.names[c]));
            }
        }
        if self.cube_index(&values)?.is_some() {
            return err(format!(
                "addHypercube with already existing id values in {}",
                self.h.hypercolumn
            ));
        }
        let file = if shape[nrdim - 1] == 0 {
            self.h.files.push(None);
            self.h.files.len() - 1
        } else {
            0
        };
        if self.h.files[file].is_none() {
            self.h.files[file] = Some(TsmFileEntry {
                seq: file as u32,
                length: 0,
            });
            File::create(self.dir.join(format!("table.f{}_TSM{file}", self.h.seq)))?;
            self.event(crate::multifile::Event::Create(format!(
                "table.f{}_TSM{file}",
                self.h.seq
            )));
        }
        let offset = self.h.files[file].as_ref().unwrap().length;
        let mut rec = values;
        for (axis, c) in self.coord_columns() {
            Self::extend_coordinates(
                &mut rec,
                &self.names[c],
                self.h.dtypes[c],
                shape[axis],
                None,
            )?;
        }
        let cube = Self::new_cube(
            shape,
            tile,
            file as i32,
            offset,
            crate::tiled::values_bytes(&rec),
        );
        let bytes = Self::ntiles(&cube) * self.bucket_size(&cube) as u64;
        self.h.cubes.push(cube);
        let ncube = self.h.cubes.len() - 1;
        self.make_cache(ncube);
        self.extend_file(file, bytes)?;
        self.update_data_row_map(ncube, shape[nrdim - 1] as u64);
        self.write_header = true;
        self.changed = true;
        Ok(())
    }

    /// `TiledDataStMan::extendHypercube(incr, values)`.
    pub(crate) fn extend_hypercube(
        &mut self,
        incr: u64,
        values: crate::aipsio::Record,
    ) -> Result<()> {
        if !self.h.is_data() {
            return err("hypercubes are extended in a TiledDataStMan only");
        }
        let index = self
            .cube_index(&values)?
            .ok_or_else(|| MsError("extendHypercube with unknown id values".into()))?;
        let shape = self.h.cubes[index].shape.clone();
        if self.h.nrrow_last + self.added_rows(&shape, incr) > self.h.nrows {
            return err("Insufficient #rows in table for add/extendHypercube");
        }
        if !self.h.cubes[index].extensible {
            return err(format!(
                "Hypercube in TSM {} is not extensible",
                self.h.hypercolumn
            ));
        }
        self.extend_cube(index, incr)?;
        let nrdim = self.h.nrdim as usize;
        let length = self.h.cubes[index].shape[nrdim - 1];
        if let Some(&(_, c)) = self.coord_columns().iter().find(|(a, _)| *a == nrdim - 1) {
            let mut rec = crate::tiled::parse_values(&self.h.cubes[index].values)?;
            Self::extend_coordinates(
                &mut rec,
                &self.names[c],
                self.h.dtypes[c],
                length,
                Some(&values),
            )?;
            self.h.cubes[index].values = crate::tiled::values_bytes(&rec);
        }
        self.update_data_row_map(index, incr);
        self.write_header = true;
        self.changed = true;
        Ok(())
    }

    /// `TiledStMan::addedNrrow`.
    fn added_rows(&self, shape: &[i64], incr: u64) -> u64 {
        let nrdim = shape.len();
        shape[self.ncell..nrdim - 1]
            .iter()
            .map(|&s| s as u64)
            .product::<u64>()
            * incr
    }

    /// `TiledDataStMan::updateRowMap`.
    fn update_data_row_map(&mut self, cube: usize, incr: u64) {
        if incr == 0 {
            return;
        }
        let shape = self.h.cubes[cube].shape.clone();
        let last = shape.len() - 1;
        self.h.data_row_map.push(self.h.nrrow_last);
        self.h.cube_map.push(cube as u32);
        self.h.pos_map.push((shape[last] as u64 - incr) as u32);
        self.h.nrrow_last += self.added_rows(&shape, incr);
    }

    // -- tiles ----------------------------------------------------------------

    fn dtype(&self, col: usize) -> DataType {
        DataType::from_code(self.h.dtypes[col]).unwrap_or(DataType::Bool)
    }

    fn tile_bytes(&self, col: usize, pixels: usize) -> usize {
        match self.dtype(col) {
            DataType::Bool => pixels.div_ceil(8),
            dt => dt.size() * pixels,
        }
    }

    fn bucket_size(&self, cube: &TsmCube) -> usize {
        let pixels = product(&cube.tile);
        (0..self.h.dtypes.len())
            .filter(|&c| self.roles[c] == TsmRole::Data)
            .map(|c| self.tile_bytes(c, pixels))
            .sum()
    }

    fn offset_in_tile(&self, col: usize, cube: &TsmCube) -> usize {
        let pixels = product(&cube.tile);
        (0..self.h.dtypes.len())
            .filter(|&c| self.roles[c] == TsmRole::Data && self.rank[c] < self.rank[col])
            .map(|c| self.tile_bytes(c, pixels))
            .sum()
    }

    fn file(&mut self, index: usize) -> Result<&mut File> {
        if !self.files.contains_key(&index) {
            let entry = self
                .h
                .files
                .get(index)
                .and_then(|f| f.as_ref())
                .ok_or_else(|| MsError(format!("tile file {index} is missing")))?;
            let path = self
                .dir
                .join(format!("table.f{}_TSM{}", self.h.seq, entry.seq));
            let file = OpenOptions::new()
                .read(true)
                .write(true)
                .open(&path)
                .or_else(|_| OpenOptions::new().read(true).open(&path))
                .map_err(|e| MsError(format!("{}: {e}", path.display())))?;
            self.files.insert(index, file);
        }
        Ok(self.files.get_mut(&index).unwrap())
    }

    /// The tile grid of a cube: tiles per axis, tile-number strides and
    /// pixel strides within a tile.
    fn grid(cube: &TsmCube) -> (Vec<i64>, Vec<i64>, Vec<i64>) {
        let nrdim = cube.shape.len();
        let per: Vec<i64> = cube
            .shape
            .iter()
            .zip(&cube.tile)
            .map(|(&s, &t)| (s + t - 1) / t)
            .collect();
        let mut grid = vec![1i64; nrdim];
        let mut pstride = vec![1i64; nrdim];
        for d in 1..nrdim {
            grid[d] = grid[d - 1] * per[d - 1];
            pstride[d] = pstride[d - 1] * cube.tile[d - 1];
        }
        (per, grid, pstride)
    }

    /// For one cell at `place`: (tile number, pixel in the tile) of every
    /// cell element in Fortran order, in runs: (tile, first pixel, first
    /// element, count) along axis 0.
    fn runs(&self, cube: &TsmCube, pos: &[i64]) -> Vec<(usize, usize, usize, usize)> {
        let nc = self.ncell;
        let (_, grid, pstride) = Self::grid(cube);
        let mut row_tile = 0i64;
        let mut base = 0i64;
        for (j, &p) in pos.iter().enumerate() {
            let d = nc + j;
            row_tile += (p / cube.tile[d]) * grid[d];
            base += (p % cube.tile[d]) * pstride[d];
        }
        let cell = &cube.shape[..nc];
        let mut out = Vec::new();
        if nc == 0 {
            out.push((row_tile as usize, base as usize, 0, 1));
            return out;
        }
        let mut idx = vec![0i64; nc];
        let mut element = 0usize;
        loop {
            // A run along axis 0 within one tile.
            let mut tile_nr = row_tile;
            let mut pixel = base;
            for d in 0..nc {
                tile_nr += (idx[d] / cube.tile[d]) * grid[d];
                pixel += (idx[d] % cube.tile[d]) * pstride[d];
            }
            let run = (cube.tile[0] - idx[0] % cube.tile[0]).min(cell[0] - idx[0]);
            out.push((tile_nr as usize, pixel as usize, element, run as usize));
            element += run as usize;
            idx[0] += run;
            let mut d = 0;
            while d < nc && idx[d] >= cell[d] {
                idx[d] = 0;
                d += 1;
                if d < nc {
                    idx[d] += 1;
                }
            }
            if d >= nc {
                break;
            }
        }
        out
    }

    /// Write `count` rows of data column `col` from native bytes in Fortran
    /// cell order.
    fn put(
        &mut self,
        col: usize,
        start: u64,
        count: u64,
        shape: &[i64],
        data: &[u8],
    ) -> Result<()> {
        if self.roles[col] != TsmRole::Data {
            return self.put_values(col, start, count, shape, data);
        }
        let dtype = self.dtype(col);
        let native = dtype.native_size();
        let cell_pixels = product(shape);
        let ordered;
        let data = if self.h.big != cfg!(target_endian = "big") && dtype.size() > 1 {
            ordered = to_order(dtype, data, self.h.big);
            &ordered[..]
        } else {
            data
        };
        // casacore's access path: a whole column of a manager of one
        // hypercube (`accessColumn`), a range of rows (`accessColumnCells`)
        // or cell by cell (`accessCell`).
        let column = start == 0 && count == self.h.nrows && count > 1 && self.h.cubes.len() == 1;
        let range = count > 1 && !(start == 0 && count == self.h.nrows);
        let mut last_cube = None;
        for i in 0..count {
            let row = start + i;
            let (ci, pos) = self
                .place(row)?
                .ok_or_else(|| MsError(format!("row {row} has no array (no hypercube)")))?;
            if column {
                if i == 0 {
                    self.touch_tiles(ci, None, true)?;
                }
            } else if range {
                if last_cube != Some(ci) {
                    let n = self.calc_cache_size(ci, &self.h.cubes[ci].shape.clone());
                    self.resize_cache(ci, n)?;
                    self.caches.get_mut(&ci).unwrap().cell_access = false;
                    last_cube = Some(ci);
                }
                for t in self.section_tiles(ci, Some(&pos)) {
                    self.get_tile(ci, t)?;
                    let cache = self.caches.get_mut(&ci).unwrap();
                    let a = cache.actual;
                    cache.slots[a].dirty = true;
                }
            } else {
                self.touch_tiles(ci, Some(&pos), false)?;
            }
            let cube = self.h.cubes[ci].clone();
            let cell = &cube.shape[..self.ncell];
            if cell != shape {
                return err(format!(
                    "row {row}: cell shape {shape:?} differs from the hypercube's {cell:?}"
                ));
            }
            let file = usize::try_from(cube.file_seq)
                .map_err(|_| MsError("hypercube without a file".into()))?;
            let bucket = self.bucket_size(&cube);
            let column_at = self.offset_in_tile(col, &cube);
            let src = &data[i as usize * cell_pixels * native..][..cell_pixels * native];
            for (tile_nr, pixel, element, n) in self.runs(&cube, &pos) {
                let at = cube.offset + (tile_nr * bucket) as u64;
                if !self.pending.contains_key(&(file, at)) {
                    let bytes = read_at(self.file(file)?, at, bucket)?;
                    self.pending.insert((file, at), bytes);
                }
                let tile = &mut self.pending.get_mut(&(file, at)).unwrap()[column_at..];
                put_pixels(tile, pixel, src, element, n, dtype);
            }
        }
        if count > 0 {
            self.changed = true;
        }
        Ok(())
    }

    /// Coordinate and id column puts: the cube's values record
    /// (`TSMCoordColumn::put`, `TSMIdColumn::put`).
    fn put_values(
        &mut self,
        col: usize,
        start: u64,
        count: u64,
        shape: &[i64],
        data: &[u8],
    ) -> Result<()> {
        let dt = self.dtype(col);
        let code = self.h.dtypes[col];
        let n = product(shape).max(1) * dt.size();
        let name = self.names[col].clone();
        for i in 0..count {
            let row = start + i;
            let (ci, pos) = self
                .place(row)?
                .ok_or_else(|| MsError(format!("{name}: row {row} has no hypercube")))?;
            let mut rec = crate::tiled::parse_values(&self.h.cubes[ci].values)?;
            let value = &data[i as usize * n..(i as usize + 1) * n];
            match self.roles[col] {
                TsmRole::Coord(axis) if axis < self.ncell => {
                    crate::tiled::define_array(&mut rec, &name, code, shape, value)?;
                }
                TsmRole::Coord(axis) => {
                    let (fcode, fshape, raw) =
                        crate::tiled::array_field(&rec, &name).ok_or_else(|| {
                            MsError(format!("{name}: no coordinate values in the hypercube"))
                        })?;
                    let scalar = crate::aipsio::tp::scalar_of(fcode).unwrap_or(code);
                    let fdt = DataType::from_code(scalar)?;
                    let mut native = to_order(fdt, &raw, true);
                    let at = pos[axis - self.ncell] as usize * fdt.size();
                    native[at..at + fdt.size()].copy_from_slice(value);
                    crate::tiled::define_array(&mut rec, &name, scalar, &fshape, &native)?;
                }
                _ => {
                    let current = self.value_of(&rec, col, &pos)?;
                    if current != value {
                        return err(format!(
                            "TSMIdColumn::put: new value mismatches existing value in column {name}"
                        ));
                    }
                    continue;
                }
            }
            self.h.cubes[ci].values = crate::tiled::values_bytes(&rec);
            self.write_header = true;
            self.changed = true;
        }
        Ok(())
    }

    /// The native bytes of a coordinate or id value of a cell.
    fn value_of(&self, rec: &crate::aipsio::Record, col: usize, pos: &[i64]) -> Result<Vec<u8>> {
        let name = &self.names[col];
        let i = rec
            .field(name)
            .ok_or_else(|| MsError(format!("{name}: no value in the hypercube")))?;
        let dt = self.dtype(col);
        match self.roles[col] {
            TsmRole::Coord(axis) => {
                let (fcode, _, raw) = crate::tiled::array_field(rec, name).unwrap_or_default();
                let fdt =
                    DataType::from_code(crate::aipsio::tp::scalar_of(fcode).unwrap_or(fcode))?;
                let native = to_order(fdt, &raw, true);
                if axis < self.ncell {
                    Ok(native)
                } else {
                    let at = pos[axis - self.ncell] as usize * fdt.size();
                    Ok(native[at..at + fdt.size()].to_vec())
                }
            }
            _ => match &rec.values[i] {
                crate::aipsio::Value::Raw(raw) => Ok(to_order(dt, &raw[..], true)),
                _ => err(format!("{name}: id value is a record")),
            },
        }
    }

    /// One cell of column `col`: undefined for a row without a hypercube.
    pub(crate) fn read_cell(&mut self, col: usize, row: u64) -> Result<Cell> {
        let Some((ci, pos)) = self.place(row)? else {
            return Ok(Cell::Undefined);
        };
        let cube = self.h.cubes[ci].clone();
        if self.roles[col] != TsmRole::Data {
            let rec = crate::tiled::parse_values(&cube.values)?;
            let v = self.value_of(&rec, col, &pos)?;
            let shape = match self.roles[col] {
                TsmRole::Coord(axis) if axis < self.ncell => vec![cube.shape[axis]],
                _ => Vec::new(),
            };
            return Ok(Cell::Values(shape, v));
        }
        let cell: Vec<i64> = cube.shape[..self.ncell].to_vec();
        let dtype = self.dtype(col);
        let bucket = self.bucket_size(&cube);
        let column_at = self.offset_in_tile(col, &cube);
        let file = usize::try_from(cube.file_seq)
            .map_err(|_| MsError("hypercube without a file".into()))?;
        let size = dtype.size();
        let n = product(&cell);
        let mut out = vec![0u8; n * dtype.native_size()];
        let mut tiles: BTreeMap<usize, Vec<u8>> = BTreeMap::new();
        for (tile_nr, pixel, element, count) in self.runs(&cube, &pos) {
            if let std::collections::btree_map::Entry::Vacant(e) = tiles.entry(tile_nr) {
                let at = cube.offset + (tile_nr * bucket) as u64;
                let bytes = match self.pending.get(&(file, at)) {
                    Some(b) => b.clone(),
                    None => read_at(self.file(file)?, at, bucket)?,
                };
                e.insert(bytes);
            }
            let tile = &tiles[&tile_nr][column_at..];
            if dtype == DataType::Bool {
                for k in 0..count {
                    let b = pixel + k;
                    out[element + k] = (tile[b / 8] >> (b % 8)) & 1;
                }
            } else {
                let bytes = &tile[pixel * size..(pixel + count) * size];
                out[element * size..(element + count) * size]
                    .copy_from_slice(&to_order(dtype, bytes, self.h.big));
            }
        }
        Ok(Cell::Values(cell, out))
    }

    /// `TiledStMan::flush`: the cubes' caches (new tiles, then the tiles
    /// written since the last flush), then, when anything changed, the
    /// header file made anew. The header goes through `table.f<N>_tmp` and
    /// a rename (casacore truncates and rewrites it), so a process killed
    /// during a flush leaves the old header or the new one, never a
    /// truncated one (research/w1-writeback.md); the bytes are unchanged.
    fn flush(&mut self) -> Result<bool> {
        // The cubes' caches in order (`flushCaches`), then what is left.
        for c in 0..self.h.cubes.len() {
            self.flush_cache(c)?;
        }
        for ((file, at), bytes) in std::mem::take(&mut self.pending) {
            write_at(self.file(file)?, at, &bytes)?;
        }
        let changed = self.changed || self.write_header;
        if changed {
            self.h.writable()?;
            let bytes = self.h.serialise();
            let header = self.dir.join(format!("table.f{}", self.h.seq));
            let tmp = self.dir.join(format!("table.f{}_tmp", self.h.seq));
            std::fs::write(&tmp, &bytes)?;
            std::fs::rename(&tmp, &header)?;
            let name = format!("table.f{}", self.h.seq);
            self.event(crate::multifile::Event::Create(name.clone()));
            self.event(crate::multifile::Event::Write(name, 0, bytes.len() as u64));
            self.write_header = false;
        }
        self.changed = false;
        Ok(changed)
    }
}

/// One slot of a hypercube's tile cache.
#[derive(Clone, Debug)]
struct TileSlot {
    tile: u64,
    dirty: bool,
    lru: u32,
}

/// A hypercube's `BucketCache` (its tiles): slots with LRU counters and
/// dirty flags, the tiles in the file (`its_CurNrOfBuckets`) and in all
/// (`its_NewNrOfBuckets`), and whether the last access was a cell access
/// (`TSMCube::CellAccess`).
#[derive(Clone, Debug)]
struct TileCache {
    size: usize,
    slots: Vec<TileSlot>,
    actual: usize,
    counter: u32,
    cur: u64,
    new: u64,
    cell_access: bool,
}

impl TsmW {
    fn cube_file(&self, c: usize) -> usize {
        self.h.cubes[c].file_seq.max(0) as usize
    }

    fn tile_at(&self, c: usize, tile: u64) -> u64 {
        let cube = &self.h.cubes[c];
        cube.offset + tile * self.bucket_size(cube) as u64
    }

    /// `TSMCube::makeCache`: one slot; the tiles in the file counted from
    /// its physical size (what casacore has written of it).
    fn make_cache(&mut self, c: usize) {
        if self.caches.contains_key(&c) {
            return;
        }
        let cube = &self.h.cubes[c];
        let bucket = self.bucket_size(cube) as u64;
        let new = Self::ntiles(cube);
        let phys = self.phys.get(&self.cube_file(c)).copied().unwrap_or(0);
        let cur = if phys > cube.offset && bucket > 0 {
            ((phys - cube.offset) / bucket).min(new)
        } else {
            0
        };
        self.caches.insert(
            c,
            TileCache {
                size: 1,
                slots: Vec::new(),
                actual: 0,
                counter: 0,
                cur,
                new,
                cell_access: false,
            },
        );
    }

    /// `TSMCube::deleteCache` (`setShape`): the cache dropped unflushed;
    /// what its dirty tiles held is lost.
    fn delete_cache(&mut self, c: usize) {
        if let Some(cache) = self.caches.remove(&c) {
            let file = self.cube_file(c);
            for s in cache.slots.iter().filter(|s| s.dirty) {
                let at = self.tile_at(c, s.tile);
                self.pending.remove(&(file, at));
            }
        }
    }

    /// `BucketCache::writeBucket` of slot `i`: the tile written (and its
    /// MultiFile event).
    fn write_slot(&mut self, c: usize, i: usize) -> Result<()> {
        let tile = self.caches[&c].slots[i].tile;
        let file = self.cube_file(c);
        let at = self.tile_at(c, tile);
        let bucket = self.bucket_size(&self.h.cubes[c]) as u64;
        if let Some(bytes) = self.pending.remove(&(file, at)) {
            write_at(self.file(file)?, at, &bytes)?;
        }
        let name = self.tile_name(file);
        self.event(crate::multifile::Event::Write(name, at, bucket));
        let p = self.phys.entry(file).or_insert(0);
        *p = (*p).max(at + bucket);
        self.caches.get_mut(&c).unwrap().slots[i].dirty = false;
        Ok(())
    }

    fn set_lru(&mut self, c: usize) {
        let cache = self.caches.get_mut(&c).unwrap();
        cache.counter = cache.counter.wrapping_add(1);
        let a = cache.actual;
        cache.slots[a].lru = cache.counter;
    }

    /// `BucketCache::getSlot` for `tile`.
    fn get_slot(&mut self, c: usize, tile: u64) -> Result<()> {
        let cache = &self.caches[&c];
        if cache.slots.len() < cache.size {
            let cache = self.caches.get_mut(&c).unwrap();
            cache.actual = cache.slots.len();
            cache.slots.push(TileSlot {
                tile,
                dirty: false,
                lru: 0,
            });
        } else {
            let mut a = 0;
            for i in 1..cache.slots.len() {
                if cache.slots[i].lru < cache.slots[a].lru {
                    a = i;
                }
            }
            let dirty = cache.slots[a].dirty;
            self.caches.get_mut(&c).unwrap().actual = a;
            if dirty {
                self.write_slot(c, a)?;
            }
            self.caches.get_mut(&c).unwrap().slots[a].tile = tile;
        }
        self.set_lru(c);
        Ok(())
    }

    /// `BucketCache::initializeBuckets` up to `tile`.
    fn initialize_tiles(&mut self, c: usize, tile: u64) -> Result<()> {
        while self.caches[&c].cur <= tile {
            let t = self.caches[&c].cur;
            self.get_slot(c, t)?;
            let cache = self.caches.get_mut(&c).unwrap();
            let a = cache.actual;
            cache.slots[a].dirty = true;
            cache.cur += 1;
        }
        Ok(())
    }

    /// `BucketCache::getBucket(tile)`; the slot is the actual one after.
    fn get_tile(&mut self, c: usize, tile: u64) -> Result<()> {
        self.make_cache(c);
        if let Some(i) = self.caches[&c].slots.iter().position(|s| s.tile == tile) {
            self.caches.get_mut(&c).unwrap().actual = i;
            self.set_lru(c);
            return Ok(());
        }
        if tile < self.caches[&c].cur {
            self.get_slot(c, tile)
        } else {
            self.initialize_tiles(c, tile)
        }
    }

    /// `BucketCache::resize(n)` (`clear(n)` writes the dirty slots past n).
    fn resize_cache(&mut self, c: usize, n: usize) -> Result<()> {
        self.make_cache(c);
        let used = self.caches[&c].slots.len();
        for i in n..used {
            if self.caches[&c].slots[i].dirty {
                self.write_slot(c, i)?;
            }
        }
        let cache = self.caches.get_mut(&c).unwrap();
        cache.slots.truncate(n);
        cache.size = n.max(1);
        cache.actual = 0;
        Ok(())
    }

    /// `BucketCache::flush`: the tiles not yet in the file made, then the
    /// dirty slots written in slot order.
    fn flush_cache(&mut self, c: usize) -> Result<()> {
        if !self.caches.contains_key(&c) {
            return Ok(());
        }
        let new = self.caches[&c].new;
        if new > 0 {
            self.initialize_tiles(c, new - 1)?;
        }
        for i in 0..self.caches[&c].slots.len() {
            if self.caches[&c].slots[i].dirty {
                self.write_slot(c, i)?;
            }
        }
        Ok(())
    }

    /// `TSMCube::calcCacheSize` for a slice of `slice` (window: the whole
    /// cube; access path: the axes in order).
    fn calc_cache_size(&self, c: usize, slice: &[i64]) -> usize {
        let cube = &self.h.cubes[c];
        let nrdim = cube.shape.len();
        let tile = &cube.tile;
        let start = vec![0i64; nrdim];
        let mut end = cube.shape.clone();
        if cube.extensible {
            // C++ integer division (towards zero), as casacore computes it.
            let i = nrdim - 1;
            end[i] = tile[i] * (1 + (end[i] - 1) / tile[i]);
        }
        let end: Vec<i64> = end.iter().map(|e| e - 1).collect();
        let mut ntiles = vec![0i64; nrdim];
        let mut reused = vec![false; nrdim];
        let mut slice_tiles = vec![0i64; nrdim];
        for i in 0..nrdim {
            let sl = slice.get(i).copied().filter(|&s| s > 0).unwrap_or(1);
            let st_tile = start[i] / tile[i];
            let en_tile = end[i].max(0) / tile[i];
            ntiles[i] = 1 + en_tile - st_tile;
            let st = start[i] % tile[i];
            slice_tiles[i] = 1 + (st + sl - 1) / tile[i];
            if sl < 1 + end[i] - start[i] && (sl < tile[i] || st != 0 || sl % tile[i] != 0) {
                reused[i] = true;
            }
        }
        let max = self.h.max_cache;
        let bucket = self.bucket_size(cube) as u64;
        let valid = |n: u64| {
            let maxnb = ((1024.0 * 1024.0 * max as f64 / bucket.max(1) as f64) as u64).max(1);
            if max > 0 && n > maxnb && 10 * n > 11 * maxnb {
                maxnb
            } else {
                n
            }
        };
        let mut nrd = nrdim;
        while nrd > 0 {
            nrd -= 1;
            let mut nr = nrd;
            while nr > 0 && !reused[nr] {
                nr -= 1;
            }
            let mut size: u64 = ntiles[..nr].iter().map(|&n| n as u64).product();
            if reused[nr] {
                for &s in &slice_tiles[nr + 1..=nrd] {
                    size *= s as u64;
                }
            }
            if size == valid(size) {
                return size as usize;
            }
            nrd = nr;
        }
        1
    }

    /// The tiles of a cell (or of the whole cube) in `accessSection`'s
    /// order (axis 0 fastest).
    fn section_tiles(&self, c: usize, pos: Option<&[i64]>) -> Vec<u64> {
        let cube = &self.h.cubes[c];
        let nrdim = cube.shape.len();
        let (_, grid, _) = Self::grid(cube);
        let mut lo = vec![0i64; nrdim];
        let mut hi = vec![0i64; nrdim];
        for d in 0..nrdim {
            let (s, e) = match pos {
                Some(p) if d >= self.ncell => (p[d - self.ncell], p[d - self.ncell]),
                _ => (0, cube.shape[d] - 1),
            };
            lo[d] = s / cube.tile[d];
            hi[d] = e.max(0) / cube.tile[d];
        }
        let mut out = Vec::new();
        let mut idx = lo.clone();
        loop {
            out.push(idx.iter().zip(&grid).map(|(&i, &g)| (i * g) as u64).sum());
            let mut d = 0;
            while d < nrdim {
                idx[d] += 1;
                if idx[d] <= hi[d] {
                    break;
                }
                idx[d] = lo[d];
                d += 1;
            }
            if d == nrdim {
                break;
            }
        }
        out
    }

    /// The cache's bookkeeping of a write of one cell (`accessCell`, sized
    /// for a cell when the last access was not one) or, `column`, of a
    /// whole cube (`accessColumn`): the tiles fetched in order, each made
    /// dirty.
    fn touch_tiles(&mut self, c: usize, pos: Option<&[i64]>, column: bool) -> Result<Vec<u64>> {
        self.make_cache(c);
        let cube = self.h.cubes[c].clone();
        if column {
            let n = self.calc_cache_size(c, &cube.shape);
            self.resize_cache(c, n)?;
            self.caches.get_mut(&c).unwrap().cell_access = false;
        } else if !self.caches[&c].cell_access {
            let mut slice = cube.shape[..self.ncell].to_vec();
            slice.resize(cube.shape.len(), 1);
            let n = self.calc_cache_size(c, &slice);
            self.resize_cache(c, n)?;
            self.caches.get_mut(&c).unwrap().cell_access = true;
        }
        let tiles = self.section_tiles(c, pos);
        for &t in &tiles {
            self.get_tile(c, t)?;
            let cache = self.caches.get_mut(&c).unwrap();
            let a = cache.actual;
            cache.slots[a].dirty = true;
        }
        Ok(tiles)
    }
}

impl TsmHeader {
    /// A header of a new manager of `kind` with no files, cubes or rows.
    fn new(kind: &str, seq: u32, name: &str, dtypes: Vec<i32>, nrdim: u32, big: bool) -> Self {
        TsmHeader {
            kind: kind.into(),
            column_tile: None,
            big,
            seq,
            nrows: 0,
            dtypes,
            hypercolumn: name.to_string(),
            max_cache: 0,
            nrdim,
            files: Vec::new(),
            cubes: Vec::new(),
            default_tile: Vec::new(),
            row_map: Vec::new(),
            cube_map: Vec::new(),
            pos_map: Vec::new(),
            nrrow_last: 0,
            data_row_map: Vec::new(),
        }
    }

    fn parse_empty() -> Self {
        Self::new("TiledColumnStMan", 0, "", Vec::new(), 0, false)
    }
}

/// The roles of a tiled manager's columns from the table's hypercolumn
/// definition (`Hypercolumn_<name>`: data, coord, id), the column names and
/// the cell dimensionality (the first data column's); all data columns
/// when the table defines no hypercolumn of that name.
fn tiled_columns(
    dat: &TableDat,
    seq: u32,
    hypercolumn: &str,
) -> (Vec<TsmRole>, Vec<String>, Option<usize>) {
    let cols: Vec<&ColDesc> = dat
        .columns
        .iter()
        .zip(&dat.bindings)
        .filter(|(_, b)| b.seq == seq)
        .map(|(c, _)| c)
        .collect();
    let names: Vec<String> = cols.iter().map(|c| c.name.clone()).collect();
    let mut roles = vec![TsmRole::Data; cols.len()];
    let key = format!("Hypercolumn_{hypercolumn}");
    let strings = |r: &crate::aipsio::Record, f: &str| -> Vec<String> {
        r.field(f)
            .and_then(|i| match &r.values[i] {
                crate::aipsio::Value::Raw(raw) => crate::aipsio::decode_string_array(raw).ok(),
                _ => None,
            })
            .unwrap_or_default()
    };
    let Some(i) = dat.private_keywords.field(&key) else {
        return (roles, names, None);
    };
    let crate::aipsio::Value::Record(h) = &dat.private_keywords.values[i] else {
        return (roles, names, None);
    };
    let data = strings(h, "data");
    for (axis, name) in strings(h, "coord").iter().enumerate() {
        if let Some(c) = names.iter().position(|n| n == name) {
            roles[c] = TsmRole::Coord(axis);
        }
    }
    for name in strings(h, "id") {
        if let Some(c) = names.iter().position(|n| *n == name) {
            roles[c] = TsmRole::Id;
        }
    }
    let ncell = data
        .first()
        .and_then(|d| cols.iter().find(|c| &c.name == d))
        .map(|c| c.ndim.max(0) as usize);
    (roles, names, ncell)
}

/// Open a tiled manager of a table with its columns' roles.
fn open_tiled(dir: &Path, dat: &TableDat, seq: u32) -> Result<TsmW> {
    let mut t = TsmW::open(dir, seq)?;
    let (roles, names, ncell) = tiled_columns(dat, seq, &t.h.hypercolumn.clone());
    t.set_columns(roles, names, if t.h.is_data() { ncell } else { None });
    // The FixedShape cell shape of the manager's data columns.
    t.fixed_cell = dat
        .columns
        .iter()
        .zip(&dat.bindings)
        .filter(|(_, b)| b.seq == seq)
        .zip(&t.roles)
        .filter(|(_, r)| **r == TsmRole::Data)
        .find_map(|((c, b), _)| match (&b.shape, &c.shape) {
            (Some(Some(s)), _) => Some(s.clone()),
            (_, Some(s)) if !s.is_empty() && c.option & 4 != 0 => Some(s.clone()),
            _ => None,
        });
    Ok(t)
}

/// Copy `count` native pixels from pixel `from` of `src` to pixel `dst` of a
/// tile's column data (booleans into bits).
fn put_pixels(tile: &mut [u8], dst: usize, src: &[u8], from: usize, count: usize, dtype: DataType) {
    if dtype == DataType::Bool {
        put_bits(tile, dst, &src[from..from + count]);
    } else {
        let size = dtype.size();
        tile[dst * size..(dst + count) * size]
            .copy_from_slice(&src[from * size..(from + count) * size]);
    }
}

// ---------------------------------------------------------------------------
// The table writer.

/// Why MultiHDF5 tables are not supported (research/e6-table-writer-final.md).
pub const MULTIHDF5_NOT_SUPPORTED: &str = "MultiHDF5 tables are not supported: a MultiHDF5 \
     container is a libhdf5 file whose layout is libhdf5's internal behaviour and whose object \
     headers carry modification times (two casacore runs differ), so it cannot be written \
     byte-identically without libhdf5";

/// Refuse a MultiHDF5 table (ColumnSet storage option 1).
pub(crate) fn check_storage(dir: &Path, dat: &TableDat) -> Result<()> {
    if (dat.set_version == -3 && dat.storage.0 == 1) || dir.join("table.mfh5").exists() {
        return err(MULTIHDF5_NOT_SUPPORTED);
    }
    Ok(())
}

/// Why a data manager's columns are not written.
pub(crate) fn unsupported_manager(kind: &str) -> String {
    let reason = match kind {
        "Adios2StMan" => "it needs the ADIOS2 library and no oracle of this writer makes it",
        "StManAipsIO" => "casacore no longer creates it and no oracle of this writer makes it",
        _ => "it is not one of the storage managers of a CASA MeasurementSet or calibration table",
    };
    format!("{kind} columns are not supported: {reason}")
}

enum Mgr {
    Ssm(Box<SsmW>),
    Tsm(Box<TsmW>),
    Ism(Box<crate::ism::IsmW>),
    /// A MemoryStMan: no file; its values live only in the session (here
    /// they are checked and dropped).
    Msm,
    Other(String),
}

/// Where `addcols` puts a new column.
#[derive(Clone, Debug)]
pub enum NewManager {
    /// casacore's `addColumn(desc)`: the first StandardStMan that can take
    /// it (the drivers' path).
    Default,
    /// A new StandardStMan (SPEC BUCKETROWS, BUCKETSIZE, PERSCACHESIZE; 0
    /// when not given).
    Standard {
        name: String,
        bucket_rows: u32,
        bucket_size: u32,
        cache: u32,
    },
    TiledColumn {
        name: String,
        tile: Vec<i64>,
    },
    TiledShape {
        name: String,
        tile: Vec<i64>,
    },
}

/// A column to add (python-casacore's `makescacoldesc`/`makearrcoldesc`).
#[derive(Clone, Debug)]
pub struct NewColumn {
    pub name: String,
    pub dtype: i32,
    pub array: bool,
    pub ndim: i32,
    /// Fixed cell shape in casacore (Fortran) order; empty if variable.
    pub shape: Vec<i64>,
    /// `ColumnDesc` options: 1 Direct, 4 FixedShape.
    pub option: i32,
    pub max_length: u32,
    pub comment: String,
    pub dm_type: String,
    pub dm_group: String,
    /// Default value of a scalar column, canonical bytes (empty: zero).
    pub default: Vec<u8>,
    pub manager: NewManager,
}

/// A casacore table opened for writing; holds the write lock until closed.
pub struct TableWriter {
    pub dir: PathBuf,
    lock: Option<LockFile>,
    pub dat: TableDat,
    pub nrows: u64,
    mgrs: Vec<Mgr>,
    table_changed: bool,
    /// `table.info` contents to write with the next `table.dat` write
    /// (`TableInfo::flush` writes only a changed info).
    info: Option<String>,
    /// Managers created in this session that have not been flushed: they
    /// report a change on their first flush (`create64` marks them
    /// changed), the unwritten ones (an empty IncrementalStMan) included.
    fresh: Vec<bool>,
    /// Where the managers' files are: the table directory, or the staging
    /// directory of a MultiFile container.
    files: PathBuf,
    /// The MultiFile container of a MultiFile table.
    mf: Option<crate::multifile::Container>,
}

/// The text of `table.info` (`TableInfo::flush`): type, subtype, an empty
/// line, then the readme lines.
pub fn table_info_text(kind: &str, sub_kind: &str, readme: &str) -> String {
    format!("Type = {kind}\nSubType = {sub_kind}\n\n{readme}")
}

impl TableWriter {
    /// Open an existing table for writing, taking casacore's write lock
    /// (`attempts` tries, `wait` apart).
    pub fn open(path: impl AsRef<Path>, attempts: u32, wait: std::time::Duration) -> Result<Self> {
        if cfg!(target_endian = "big") {
            return err("writing tables on a big-endian host is not supported (E5)");
        }
        let table_dir = path.as_ref().to_path_buf();
        let mut lock = LockFile::acquire(&table_dir, attempts, wait)?;
        let dat = TableDat::parse(&std::fs::read(table_dir.join("table.dat"))?)?;
        check_storage(&table_dir, &dat)?;
        // A MultiFile table: the logical files are worked on in a staging
        // directory and packed into `table.mf` on every flush.
        let mf = if table_dir.join(crate::multifile::CONTAINER).is_file() {
            Some(crate::multifile::Container::open(&table_dir)?)
        } else {
            None
        };
        let dir = mf.as_ref().map_or(table_dir.clone(), |m| m.staging.clone());

        let lock_bytes = lock.contents()?;
        let nrows = match SyncRecord::parse(&lock_bytes)? {
            Some(s) if s.nrows > 0 => s.nrows,
            _ => dat.nrows,
        };
        let log = mf.as_ref().map(|m| m.log.clone());
        let mgrs =
            crate::multifile::with_log(log.as_ref(), || Self::open_managers(&dir, &dat, nrows))?;
        Ok(TableWriter {
            dir: table_dir,
            lock: Some(lock),
            dat,
            nrows,
            mgrs,
            table_changed: false,
            info: None,
            fresh: Vec::new(),
            files: dir,
            mf,
        })
    }

    /// The managers of a table opened for writing.
    fn open_managers(dir: &Path, dat: &TableDat, nrows: u64) -> Result<Vec<Mgr>> {
        let dir = dir.to_path_buf();
        let mut mgrs = Vec::with_capacity(dat.managers.len());
        for (slot, (kind, seq)) in dat.managers.iter().enumerate() {
            mgrs.push(match kind.as_str() {
                "StandardStMan" => {
                    let mut cols = Vec::new();
                    for (c, b) in dat.columns.iter().zip(&dat.bindings) {
                        if b.seq == *seq {
                            cols.push(ssm_col(c, b)?);
                        }
                    }
                    Mgr::Ssm(Box::new(SsmW::open(
                        &dir,
                        *seq,
                        &dat.blobs[slot],
                        cols,
                        !dat.little_endian,
                    )?))
                }
                "TiledColumnStMan" | "TiledShapeStMan" | "TiledCellStMan" | "TiledDataStMan" => {
                    match open_tiled(&dir, dat, *seq) {
                        Ok(t) => Mgr::Tsm(Box::new(t)),
                        Err(e) => Mgr::Other(e.0),
                    }
                }
                "IncrementalStMan" => {
                    let mut cols = Vec::new();
                    for (c, b) in dat.columns.iter().zip(&dat.bindings) {
                        if b.seq == *seq {
                            cols.push(crate::ism::ism_col(c, b)?);
                        }
                    }
                    Mgr::Ism(Box::new(crate::ism::IsmW::open(
                        &dir,
                        *seq,
                        &dat.blobs[slot],
                        cols,
                        nrows,
                        !dat.little_endian,
                        true,
                    )?))
                }
                "MemoryStMan" => Mgr::Msm,
                other => Mgr::Other(unsupported_manager(other)),
            });
        }
        Ok(mgrs)
    }

    /// A table made by `ms_create::create_table`: its parts, every manager
    /// new, the table changed (written on the first flush) with its info.
    pub(crate) fn from_new(
        dir: PathBuf,
        lock: LockFile,
        dat: TableDat,
        mgrs: Vec<NewMgr>,
        info: String,
        mf: Option<crate::multifile::Container>,
    ) -> Self {
        let fresh = mgrs.iter().map(NewMgr::reports_creation).collect();
        let files = mf.as_ref().map_or(dir.clone(), |m| m.staging.clone());
        TableWriter {
            dir,
            lock: Some(lock),
            nrows: dat.nrows,
            dat,
            mgrs: mgrs.into_iter().map(|m| m.0).collect(),
            table_changed: true,
            info: Some(info),
            fresh,
            files,
            mf,
        }
    }

    /// The table's flush of its MultiFile container (after the managers'
    /// flushes, which logged their writes).
    fn mf_flush(&mut self) -> Result<()> {
        match self.mf.as_mut() {
            Some(mf) => mf.pack(),
            None => Ok(()),
        }
    }

    /// Mark the table changed without changing it, as casacore's
    /// `rwKeywordSet` does (`TableCopy::copySubTables` takes every
    /// column's keyword set for writing): the next flush writes
    /// `table.dat` and counts a table change.
    pub fn mark_changed(&mut self) -> Result<()> {
        self.guard()?;
        self.table_changed = true;
        Ok(())
    }

    /// Set `table.info` (python-casacore's `putinfo`): written with the
    /// next `table.dat` write.
    pub fn put_info(&mut self, kind: &str, sub_kind: &str, readme: &str) -> Result<()> {
        self.guard()?;
        self.info = Some(table_info_text(kind, sub_kind, readme));
        Ok(())
    }

    /// The TiledDataStMan named `name` (its hypercolumn).
    fn tds(&mut self, name: &str) -> Result<&mut TsmW> {
        self.guard()?;
        self.mgrs
            .iter_mut()
            .find_map(|m| match m {
                Mgr::Tsm(t) if t.h.is_data() && t.h.hypercolumn == name => Some(t.as_mut()),
                _ => None,
            })
            .ok_or_else(|| MsError(format!("no TiledDataStMan {name} in the table")))
    }

    /// `TiledDataStManAccessor::addHypercube(cubeShape, tileShape, values)`
    /// of the TiledDataStMan `name` (shapes in casacore order; `values` the
    /// id and coordinate values).
    pub fn add_hypercube(
        &mut self,
        name: &str,
        shape: &[i64],
        tile: &[i64],
        values: crate::aipsio::Record,
    ) -> Result<()> {
        self.tds(name)?.add_hypercube(shape, tile, values)
    }

    /// `TiledDataStManAccessor::extendHypercube(incrInLastDim, values)`.
    pub fn extend_hypercube(
        &mut self,
        name: &str,
        incr: u64,
        values: crate::aipsio::Record,
    ) -> Result<()> {
        self.tds(name)?.extend_hypercube(incr, values)
    }

    /// Add `n` rows (`Table::addRow`, not initialised): every manager adds
    /// them; IncrementalStMan and the other unwritten managers refuse (E5).
    pub fn add_rows(&mut self, n: u64) -> Result<()> {
        self.guard()?;
        if n == 0 {
            return Ok(());
        }
        for m in &self.mgrs {
            if let Mgr::Other(reason) = m {
                return err(format!("rows cannot be added: {reason}"));
            }
        }
        let old = self.nrows;
        for m in &mut self.mgrs {
            match m {
                Mgr::Ssm(s) => s.add_rows(old, n)?,
                Mgr::Tsm(t) => t.add_rows(n)?,
                Mgr::Ism(s) => s.add_rows(n)?,
                Mgr::Msm => {}
                Mgr::Other(_) => unreachable!(),
            }
        }
        self.nrows += n;
        Ok(())
    }

    /// Remove rows (`Table::removeRow`: sorted, from the last one down).
    /// casacore's tiled managers cannot remove rows, so a table with one
    /// refuses, as casacore does; IncrementalStMan refuses (E5).
    pub fn remove_rows(&mut self, rows: &[u64]) -> Result<()> {
        self.guard()?;
        for m in &self.mgrs {
            match m {
                Mgr::Ssm(_) | Mgr::Ism(_) | Mgr::Msm => {}
                Mgr::Tsm(t) => {
                    return err(format!(
                        "rows cannot be removed: {} cannot remove rows (as in casacore)",
                        t.h.kind
                    ));
                }
                Mgr::Other(reason) => return err(format!("rows cannot be removed: {reason}")),
            }
        }
        let mut sorted = rows.to_vec();
        sorted.sort_unstable();
        if sorted.windows(2).any(|w| w[0] == w[1]) {
            return err("a row is given twice");
        }
        if let Some(&last) = sorted.last()
            && last >= self.nrows
        {
            return err(format!("row {last} does not exist"));
        }
        for &row in sorted.iter().rev() {
            for m in &mut self.mgrs {
                match m {
                    Mgr::Ssm(s) => s.remove_row(row, self.nrows)?,
                    Mgr::Ism(s) => s.remove_row(row)?,
                    _ => {}
                }
            }
            self.nrows -= 1;
        }
        Ok(())
    }

    /// Write one cell of an array column (`ArrayColumn::put`): numeric
    /// arrays as native bytes (Bool one byte each), a variable-shape row
    /// gets a new array when it had none or another shape.
    pub fn put_cell(&mut self, name: &str, row: u64, shape: &[i64], data: &[u8]) -> Result<()> {
        self.put_rows(name, row, 1, shape, data, true)
    }

    /// Write rows of a string-array column, `strings` in Fortran order,
    /// `shape` (casacore order) the shape of every cell.
    pub fn put_string_cells(
        &mut self,
        name: &str,
        start: u64,
        count: u64,
        shape: &[i64],
        strings: &[String],
    ) -> Result<()> {
        self.put_string_rows(name, start, count, shape, strings, false)
    }

    /// Write one cell of a string-array column as `ArrayColumn::put` does
    /// (python-casacore's `putcell`; differs from a one-row `putcol` for an
    /// IncrementalStMan indirect column).
    pub fn put_string_cell(
        &mut self,
        name: &str,
        row: u64,
        shape: &[i64],
        strings: &[String],
    ) -> Result<()> {
        self.put_string_rows(name, row, 1, shape, strings, true)
    }

    fn put_string_rows(
        &mut self,
        name: &str,
        start: u64,
        count: u64,
        shape: &[i64],
        strings: &[String],
        cell: bool,
    ) -> Result<()> {
        let count = self.rows(start, count)?;
        let (_, slot, k) = self.binding(name)?;
        match &mut self.mgrs[slot] {
            Mgr::Ssm(s) => s.put_string_column(k, start, count, shape, strings),
            Mgr::Ism(s) if s.is_indirect_strings(k) => {
                s.put_string_cells(k, start, count, shape, strings, cell)
            }
            Mgr::Ism(s) => {
                if strings.len() != product(shape) * count as usize {
                    err("string count mismatches the rows and cell shape")
                } else {
                    s.put_strings(k, start, strings)
                }
            }
            Mgr::Msm => Ok(()),
            Mgr::Tsm(_) => err("tiled string columns do not exist"),
            Mgr::Other(reason) => err(reason.clone()),
        }
        .map_err(|e| MsError(format!("{name}: {e}")))
    }

    /// Whether a row of a column has a value (`isDefined`).
    pub fn is_defined(&mut self, name: &str, row: u64) -> Result<bool> {
        self.rows(row, 1)?;
        let (_, slot, k) = self.binding(name)?;
        match &mut self.mgrs[slot] {
            Mgr::Ssm(s) => s.is_defined(k, row),
            Mgr::Ism(s) => s.is_defined(k, row),
            Mgr::Tsm(t) => Ok(t.place(row)?.is_some()),
            _ => Ok(true),
        }
    }

    /// Flush, then read cells of an indirect-array or string-array column
    /// (undefined cells and rows of different shapes included) through a
    /// read-only view of the files.
    pub fn read_cells(&mut self, name: &str, start: u64, count: u64) -> Result<Vec<Cell>> {
        self.flush()?;
        read_cells(&self.dir, name, start, count, Some(self.nrows))
    }

    /// (manager slot, column index within the manager) of a column.
    fn binding(&self, name: &str) -> Result<(usize, usize, usize)> {
        let index = self.dat.column(name)?;
        let seq = self.dat.bindings[index].seq;
        let slot = self
            .dat
            .managers
            .iter()
            .position(|(_, s)| *s == seq)
            .ok_or_else(|| MsError(format!("{name}: data manager {seq} is missing")))?;
        let k = self.dat.bindings[..index]
            .iter()
            .filter(|b| b.seq == seq)
            .count();
        Ok((index, slot, k))
    }

    /// Re-take the write lock before any change (see `LockFile::reassert`).
    fn guard(&self) -> Result<()> {
        match &self.lock {
            Some(lock) => lock.reassert(),
            None => err("table is closed"),
        }
    }

    /// Flush, then read rows of a column with the task E reader, without
    /// touching `table.lock` (which would drop this process's lock).
    pub fn read_column(&mut self, name: &str, start: u64, count: u64) -> Result<ColumnData> {
        self.read_column_slice(name, start, count, None)
    }

    /// Flush, then read rows `start..start+count` (`count` 0: to the end)
    /// with each cell cut to `slice` (`crate::ms::Table::read_column_slice`).
    pub fn read_column_slice(
        &mut self,
        name: &str,
        start: u64,
        count: u64,
        slice: Option<&[(i64, i64)]>,
    ) -> Result<ColumnData> {
        self.flush()?;
        let direct = crate::ms::Table::open_with_rows(&self.dir, Some(self.nrows))
            .and_then(|t| t.read_column_slice(name, start, count, slice));
        match direct {
            Ok(d) => Ok(d),
            Err(e) => {
                // The task E reader does not read every kind E5 writes
                // (IncrementalStMan strings and arrays, ...): pack the
                // writer's own cell reads when every cell has one shape.
                let count = if count == 0 {
                    self.nrows.saturating_sub(start)
                } else {
                    count
                };
                let dtype = DataType::from_code(self.dat.columns[self.dat.column(name)?].dtype)?;
                let cells = read_cells(&self.dir, name, start, count, Some(self.nrows))?;
                let packed = pack_cells(dtype, count, cells).ok_or(e)?;
                match slice {
                    Some(s) if packed.nrows > 0 => crate::ms::cut_cells(packed, s),
                    _ => Ok(packed),
                }
            }
        }
    }

    /// Flush, then read the rows `rows` (any order) with each cell cut to
    /// `slice` (`crate::ms::Table::read_rows`), in the order of `rows`.
    pub fn read_rows(
        &mut self,
        name: &str,
        rows: &[u64],
        slice: Option<&[(i64, i64)]>,
    ) -> Result<ColumnData> {
        self.flush()?;
        let direct = crate::ms::Table::open_with_rows(&self.dir, Some(self.nrows))
            .and_then(|t| t.read_rows(name, rows, slice));
        match direct {
            Ok(d) => Ok(d),
            Err(e) => {
                // As `read_column_slice`: each run of consecutive rows through
                // the writer's own cell reads.
                let mut out: Option<ColumnData> = None;
                let mut at = 0;
                while at < rows.len() {
                    let mut n = 1;
                    while at + n < rows.len() && rows[at + n] == rows[at] + n as u64 {
                        n += 1;
                    }
                    let part = self
                        .read_column_slice(name, rows[at], n as u64, slice)
                        .map_err(|_| e.clone())?;
                    match &mut out {
                        None => out = Some(part),
                        Some(o) => {
                            if o.shape != part.shape {
                                return Err(e);
                            }
                            o.nrows += part.nrows;
                            o.bytes.extend_from_slice(&part.bytes);
                            o.strings.extend(part.strings);
                        }
                    }
                    at += n;
                }
                out.ok_or(e)
            }
        }
    }

    fn rows(&self, start: u64, count: u64) -> Result<u64> {
        self.guard()?;
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
        Ok(count)
    }

    /// Write rows `start..start+count` (`count` 0: to the end) of a numeric
    /// or Bool column: native bytes, one cell of `shape` (casacore order;
    /// empty for scalars) per row in Fortran order, booleans one byte each.
    pub fn put_column(
        &mut self,
        name: &str,
        start: u64,
        count: u64,
        shape: &[i64],
        data: &[u8],
    ) -> Result<()> {
        self.put_rows(name, start, count, shape, data, false)
    }

    /// `put_column`, or with `cell` one cell as `ArrayColumn::put` writes
    /// it (an IncrementalStMan indirect column reads the row's shape first).
    fn put_rows(
        &mut self,
        name: &str,
        start: u64,
        count: u64,
        shape: &[i64],
        data: &[u8],
        cell: bool,
    ) -> Result<()> {
        let count = self.rows(start, count)?;
        let (index, slot, k) = self.binding(name)?;
        let desc = &self.dat.columns[index];
        let dtype = DataType::from_code(desc.dtype)?;
        if dtype == DataType::Str {
            return err(format!("{name}: use put_strings for string columns"));
        }
        if desc.is_array() == shape.is_empty() {
            return err(format!(
                "{name}: cell shape {shape:?} does not fit the column"
            ));
        }
        let expect = count as usize * product(shape) * dtype.native_size();
        if data.len() != expect {
            return err(format!(
                "{name}: {} bytes given, {expect} expected",
                data.len()
            ));
        }
        let result = match &mut self.mgrs[slot] {
            Mgr::Ssm(s) => s.put(k, start, count, shape, data),
            Mgr::Ism(s) => s.put(k, start, count, shape, data, cell),
            Mgr::Tsm(t) => {
                if DataType::from_code(t.h.dtypes[k])? != dtype {
                    return err(format!("{name}: tiled header type mismatches the column"));
                }
                // A variable-shape TiledShapeStMan row gets its hypercube
                // when its shape is first set (`setShape`); a row that has
                // one cannot change shape (as in casacore). A TiledCellStMan
                // row gets a cube of the new shape whenever its shape
                // changes (`canChangeShape`).
                let data_col = t.roles[k] == TsmRole::Data;
                if data_col && t.h.is_cell() {
                    for row in start..start + count {
                        if t.cell_shape(row).as_deref() != Some(shape) {
                            if t.fixed_cell.is_some() {
                                return err(format!(
                                    "{name}: the column has a fixed shape, not {shape:?}"
                                ));
                            }
                            t.set_cell_shape(row, shape)?;
                        }
                    }
                }
                if data_col && t.h.is_shape() && t.fixed_cell.is_none() {
                    for row in start..start + count {
                        match t.cell_shape(row) {
                            None => t.set_shape(row, shape)?,
                            Some(s) if s != shape => {
                                return err(format!(
                                    "{name}: row {row} has the shape {s:?}; a TiledShapeStMan \
                                     cell cannot change shape (as in casacore)"
                                ));
                            }
                            Some(_) => {}
                        }
                    }
                }
                t.put(k, start, count, shape, data)
            }
            Mgr::Msm => {
                let _ = cell;
                Ok(())
            }
            Mgr::Other(reason) => err(reason.clone()),
        };
        result.map_err(|e| MsError(format!("{name}: {e}")))
    }

    /// Write rows `start..` of a scalar string column.
    pub fn put_strings(&mut self, name: &str, start: u64, values: &[String]) -> Result<()> {
        self.rows(start, values.len() as u64)?;
        let (_, slot, k) = self.binding(name)?;
        match &mut self.mgrs[slot] {
            Mgr::Ssm(s) => s.put_strings(k, start, values),
            Mgr::Ism(s) => s.put_strings(k, start, values),
            Mgr::Msm => Ok(()),
            Mgr::Tsm(_) => err(format!("{name}: tiled string columns do not exist")),
            Mgr::Other(reason) => err(reason.clone()),
        }
        .map_err(|e| MsError(format!("{name}: {e}")))
    }

    fn keywords_mut(&mut self, column: Option<&str>) -> Result<&mut crate::aipsio::Record> {
        self.guard()?;
        Ok(match column {
            None => &mut self.dat.keywords,
            Some(c) => {
                let i = self.dat.column(c)?;
                &mut self.dat.columns[i].keywords
            }
        })
    }

    /// Define or replace a keyword of the table (`column` None) or of a
    /// column; `path` names nested sub-records, the last element the field.
    pub fn put_keyword(
        &mut self,
        column: Option<&str>,
        path: &[&str],
        value: KeywordValue,
    ) -> Result<()> {
        let (field, parents) = path
            .split_last()
            .ok_or_else(|| MsError("empty keyword name".into()))?;
        let record = self.keywords_mut(column)?;
        edit_nested(record, parents, &mut |r| r.define(field, value.clone()))?;
        self.table_changed = true;
        Ok(())
    }

    pub fn remove_keyword(&mut self, column: Option<&str>, path: &[&str]) -> Result<()> {
        let (field, parents) = path
            .split_last()
            .ok_or_else(|| MsError("empty keyword name".into()))?;
        let record = self.keywords_mut(column)?;
        edit_nested(record, parents, &mut |r| r.remove(field))?;
        self.table_changed = true;
        Ok(())
    }

    /// Whether a data manager of this name exists (StandardStMan blob name
    /// or tiled hypercolumn name; other managers' blobs name them too).
    fn manager_name_used(&self, name: &str) -> bool {
        self.dat.blobs.iter().any(|b| {
            let mut c = Cursor::new(b, true);
            c.magic().is_ok() && c.start().is_ok() && c.string().is_ok_and(|n| n == name)
        }) || self.mgrs.iter().any(|m| match m {
            Mgr::Tsm(t) => t.h.hypercolumn == name,
            Mgr::Ism(s) => s.name == name,
            _ => false,
        })
    }

    /// `addcols` of one column.
    pub fn add_column(&mut self, spec: &NewColumn) -> Result<()> {
        let log = self.mf.as_ref().map(|m| m.log.clone());
        crate::multifile::with_log(log.as_ref(), || self.add_column_in(spec))
    }

    fn add_column_in(&mut self, spec: &NewColumn) -> Result<()> {
        self.guard()?;
        if self.dat.column(&spec.name).is_ok() {
            return err(format!("column {} already exists", spec.name));
        }
        let dm_type = if spec.dm_type.is_empty() {
            "StandardStMan".to_string()
        } else {
            spec.dm_type.clone()
        };
        let dm_group = if spec.dm_group.is_empty() {
            dm_type.clone()
        } else {
            spec.dm_group.clone()
        };
        let derived = if spec.array {
            vec![0]
        } else if spec.default.is_empty() {
            match spec.dtype {
                11 => vec![0; 4],
                code => vec![0; crate::aipsio::tp::scalar_size(code)],
            }
        } else {
            spec.default.clone()
        };
        let desc = ColDesc {
            class: crate::ms_desc::column_class(spec.dtype, spec.array)?,
            name: spec.name.clone(),
            comment: spec.comment.clone(),
            dm_type,
            dm_group,
            dtype: spec.dtype,
            option: spec.option,
            ndim: spec.ndim,
            shape: spec.array.then(|| spec.shape.clone()),
            max_length: spec.max_length,
            keywords: crate::aipsio::Record::default(),
            derived,
        };
        let fixed = spec.array && spec.option & 4 != 0 && !spec.shape.is_empty();
        let mut binding = ColBinding {
            original_name: spec.name.clone(),
            seq: 0,
            shape: spec.array.then(|| fixed.then(|| spec.shape.clone())),
        };
        match &spec.manager {
            NewManager::Default => {
                let slot = self
                    .mgrs
                    .iter()
                    .position(|m| matches!(m, Mgr::Ssm(_)))
                    .ok_or_else(|| MsError("no StandardStMan to add the column to (E4)".into()))?;
                binding.seq = self.dat.managers[slot].1;
                let col = ssm_col(&desc, &binding)?;
                if col.dtype == DataType::Str && spec.array {
                    return err("string array columns are not added (E4)");
                }
                let nrows = self.nrows;
                if let Mgr::Ssm(s) = &mut self.mgrs[slot] {
                    s.add_column(col, nrows)?;
                    self.dat.blobs[slot] = s.blob.serialise();
                }
            }
            NewManager::Standard {
                name,
                bucket_rows,
                bucket_size,
                cache,
            } => {
                if self.manager_name_used(name) {
                    return err(format!("data manager name {name} is already used"));
                }
                let seq = self.dat.seq_count;
                binding.seq = seq;
                let col = ssm_col(&desc, &binding)?;
                if col.dtype == DataType::Str && spec.array {
                    return err("string array columns are not added (E4)");
                }
                let s = SsmW::create(
                    &self.files,
                    seq,
                    name,
                    vec![col],
                    self.nrows,
                    *bucket_rows,
                    *bucket_size,
                    *cache,
                    !self.dat.little_endian,
                )?;
                self.dat.seq_count += 1;
                self.dat.managers.push(("StandardStMan".into(), seq));
                self.dat.blobs.push(s.blob.serialise());
                self.mgrs.push(Mgr::Ssm(Box::new(s)));
            }
            NewManager::TiledColumn { name, tile } | NewManager::TiledShape { name, tile } => {
                let column = matches!(spec.manager, NewManager::TiledColumn { .. });
                if !fixed {
                    return err("tiled columns are added with a fixed shape only (E4/E5)");
                }
                if self.nrows == 0 || self.nrows > u64::from(u32::MAX) {
                    return err("tiled columns are added to tables of 1 to 2^32-1 rows");
                }
                if self.manager_name_used(name) {
                    return err(format!("data manager name {name} is already used"));
                }
                let mut cube_shape = spec.shape.clone();
                cube_shape.push(self.nrows as i64);
                if tile.len() != cube_shape.len() || tile.iter().any(|&t| t < 1) {
                    return err(format!(
                        "tile shape {tile:?} does not fit the cube {cube_shape:?}"
                    ));
                }
                // `TSMCube::adjustTileShape`: a tile axis is at most the cube's;
                // the header keeps the tile shape as given.
                let cube_tile: Vec<i64> = tile
                    .iter()
                    .zip(&cube_shape)
                    .map(|(&t, &s)| t.min(s))
                    .collect();
                let seq = self.dat.seq_count;
                binding.seq = seq;
                let cube = TsmCube {
                    values: empty_values_record(),
                    extensible: true,
                    nrdim: cube_shape.len() as u32,
                    shape: cube_shape.clone(),
                    tile: cube_tile.clone(),
                    file_seq: if column { 0 } else { 1 },
                    offset: 0,
                };
                let mut h = TsmHeader {
                    kind: if column {
                        "TiledColumnStMan"
                    } else {
                        "TiledShapeStMan"
                    }
                    .into(),
                    column_tile: column.then(|| tile.clone()),
                    big: !self.dat.little_endian,
                    seq,
                    nrows: self.nrows,
                    dtypes: vec![spec.dtype],
                    hypercolumn: name.clone(),
                    max_cache: 0,
                    nrdim: cube_shape.len() as u32,
                    files: Vec::new(),
                    cubes: Vec::new(),
                    default_tile: Vec::new(),
                    row_map: Vec::new(),
                    cube_map: Vec::new(),
                    pos_map: Vec::new(),
                    nrrow_last: 0,
                    data_row_map: Vec::new(),
                };
                let ntiles: i64 = cube_shape
                    .iter()
                    .zip(&cube_tile)
                    .map(|(&s, &t)| (s + t - 1) / t)
                    .product();
                let mut t = TsmW::with_header(
                    &self.files,
                    h.clone(),
                    vec![TsmRole::Data],
                    vec![spec.name.clone()],
                );
                let length = ntiles as u64 * t.bucket_size(&cube) as u64;
                let file_seq = if column { 0 } else { 1 };
                if column {
                    h.files = vec![Some(TsmFileEntry { seq: 0, length })];
                    h.cubes = vec![cube];
                } else {
                    h.files = vec![None, Some(TsmFileEntry { seq: 1, length })];
                    let placeholder = TsmCube {
                        values: empty_values_record(),
                        extensible: false,
                        nrdim: 0,
                        shape: Vec::new(),
                        tile: Vec::new(),
                        file_seq: -1,
                        offset: 0,
                    };
                    h.cubes = vec![placeholder, cube];
                    h.default_tile = tile.clone();
                    let last = (self.nrows - 1) as u32;
                    h.row_map = vec![last];
                    h.cube_map = vec![1];
                    h.pos_map = vec![last];
                }
                let tiles = File::create(self.files.join(format!("table.f{seq}_TSM{file_seq}")))?;
                crate::multifile::emit(
                    &crate::multifile::current(),
                    crate::multifile::Event::Create(format!("table.f{seq}_TSM{file_seq}")),
                );
                tiles.set_len(length)?;
                t.h = h;
                t.write_header = true;
                t.changed = true;
                self.dat.seq_count += 1;
                self.dat.managers.push((t.h.kind.clone(), seq));
                self.dat.blobs.push(Vec::new());
                self.mgrs.push(Mgr::Tsm(Box::new(t)));
            }
        }
        self.dat.columns.push(desc);
        self.dat.bindings.push(binding);
        self.table_changed = true;
        Ok(())
    }

    /// `PlainTable::putFile(always)`: the managers' data; `table.dat`
    /// (through `table.dat_tmp` and a rename) when the table changed or
    /// `always`; then the sync record when anything was written.
    fn put_file(&mut self, always: bool) -> Result<()> {
        self.guard()?;
        let mut dm_changed = Vec::with_capacity(self.mgrs.len());
        for (i, m) in self.mgrs.iter_mut().enumerate() {
            let changed = match m {
                Mgr::Ssm(s) => s.flush()?,
                Mgr::Tsm(t) => t.flush()?,
                Mgr::Ism(s) => s.flush()?,
                Mgr::Msm | Mgr::Other(_) => false,
            };
            let fresh = self.fresh.get_mut(i).is_some_and(std::mem::take);
            dm_changed.push(changed || fresh);
        }
        self.mf_flush()?;
        let write_table = always || self.table_changed;
        if write_table {
            self.dat.nrows = self.nrows;
            // `SSMBase::flush` puts its current blob (a recreated manager
            // has new column offsets).
            for (i, m) in self.mgrs.iter().enumerate() {
                if let Mgr::Ssm(s) = m {
                    self.dat.blobs[i] = s.blob.serialise();
                }
            }
            let tmp = self.dir.join("table.dat_tmp");
            std::fs::write(&tmp, self.dat.serialise())?;
            std::fs::rename(&tmp, self.dir.join("table.dat"))?;
            // `flushTableInfo`: a changed info is written with table.dat.
            if let Some(info) = self.info.take() {
                std::fs::write(self.dir.join("table.info"), info)?;
            }
        }
        if (write_table || dm_changed.iter().any(|&c| c))
            && let Some(lock) = self.lock.as_mut()
        {
            lock.write_sync(
                self.nrows,
                self.dat.columns.len() as u32,
                self.table_changed,
                &dm_changed,
            )?;
        }
        self.table_changed = false;
        Ok(())
    }

    /// Flush as `Table::flush` does (`putFile(False)`).
    pub fn flush(&mut self) -> Result<()> {
        self.put_file(false)
    }

    /// Flush and release the lock. casacore writes `table.dat` and the sync
    /// record on every release of a write lock (`putFile(True)`), so a
    /// table whose `table.dat` row count is stale gets it corrected.
    pub fn close(mut self) -> Result<()> {
        let result = self.put_file(true);
        if let Some(mf) = self.mf.as_ref() {
            mf.close()?;
        }
        self.lock = None;
        result
    }
}

impl Drop for TableWriter {
    fn drop(&mut self) {
        if self.lock.is_some() {
            let _ = self.put_file(true);
            if let Some(mf) = self.mf.as_ref() {
                let _ = mf.close();
            }
        }
    }
}

/// A data manager made for a new table (`ms_create`).
pub struct NewMgr(Mgr);

impl NewMgr {
    /// A manager that is not written (writes refuse with `reason`).
    pub fn other(reason: &str) -> Self {
        NewMgr(Mgr::Other(reason.to_string()))
    }

    /// A new StandardStMan named `name` holding `columns` (description and
    /// binding, in table order) with `nrows` rows (`SSMBase::create64`).
    #[allow(clippy::too_many_arguments)]
    pub fn standard(
        dir: &Path,
        seq: u32,
        name: &str,
        columns: &[(ColDesc, ColBinding)],
        nrows: u64,
        bucket_rows: u32,
        bucket_size: u32,
        cache: u32,
        big: bool,
    ) -> Result<(Self, Vec<u8>)> {
        let cols = columns
            .iter()
            .map(|(c, b)| ssm_col(c, b))
            .collect::<Result<Vec<_>>>()?;
        if cols.is_empty() {
            return err(format!("data manager {name} has no columns"));
        }
        let s = SsmW::create(
            dir,
            seq,
            name,
            cols,
            nrows,
            bucket_rows,
            bucket_size,
            cache,
            big,
        )?;
        let blob = s.blob.serialise();
        Ok((NewMgr(Mgr::Ssm(Box::new(s))), blob))
    }

    /// A new MemoryStMan (no file; `MSMBase::flush` writes nothing).
    pub fn memory() -> Self {
        NewMgr(Mgr::Msm)
    }

    /// A new TiledDataStMan of hypercolumn `name` (ndim `nrdim`; data,
    /// coordinate and id columns by name) with no hypercube and `nrows`
    /// rows; hypercubes come with `TableWriter::add_hypercube`.
    #[allow(clippy::too_many_arguments)]
    pub fn tds(
        dir: &Path,
        seq: u32,
        name: &str,
        columns: &[(ColDesc, ColBinding)],
        data: &[String],
        coord: &[String],
        id: &[String],
        nrdim: u32,
        nrows: u64,
        big: bool,
    ) -> Result<Self> {
        let names: Vec<String> = columns.iter().map(|(c, _)| c.name.clone()).collect();
        let roles = names
            .iter()
            .map(|n| {
                if let Some(axis) = coord.iter().position(|c| c == n) {
                    TsmRole::Coord(axis)
                } else if id.contains(n) {
                    TsmRole::Id
                } else {
                    TsmRole::Data
                }
            })
            .collect();
        let ncell = data
            .first()
            .and_then(|d| columns.iter().find(|(c, _)| &c.name == d))
            .map_or(0, |(c, _)| c.ndim.max(0) as usize);
        let dtypes = columns.iter().map(|(c, _)| c.dtype).collect();
        let mut t = TsmW::create_data(dir, seq, name, dtypes, roles, names, nrdim, ncell, big);
        t.add_rows(nrows)?;
        Ok(NewMgr(Mgr::Tsm(Box::new(t))))
    }

    /// A new TiledCellStMan named `name` (one hypercube per row; default
    /// tile shape `tile`, possibly empty) with `nrows` rows.
    #[allow(clippy::too_many_arguments)]
    pub fn tiled_cell(
        dir: &Path,
        seq: u32,
        name: &str,
        dtypes: Vec<i32>,
        cell: Option<Vec<i64>>,
        ndim: usize,
        tile: Vec<i64>,
        nrows: u64,
        big: bool,
    ) -> Result<Self> {
        let mut t = TsmW::create_cell(dir, seq, name, dtypes, cell, ndim, tile, big)?;
        t.add_rows(nrows)?;
        Ok(NewMgr(Mgr::Tsm(Box::new(t))))
    }

    /// Whether the manager reports a change on its first flush.
    pub fn reports_creation(&self) -> bool {
        !matches!(self.0, Mgr::Msm)
    }

    /// A new IncrementalStMan named `name` holding `columns` with `nrows`
    /// rows (`ISMBase::create64`); `bucket_size` 0: sized by `init`.
    #[allow(clippy::too_many_arguments)]
    pub fn ism(
        dir: &Path,
        seq: u32,
        name: &str,
        columns: &[(ColDesc, ColBinding)],
        nrows: u64,
        bucket_size: u32,
        cache: u32,
        big: bool,
    ) -> Result<(Self, Vec<u8>)> {
        let cols = columns
            .iter()
            .map(|(c, b)| crate::ism::ism_col(c, b))
            .collect::<Result<Vec<_>>>()?;
        let size = if bucket_size == 0 {
            crate::ism::IsmW::default_bucket_size(&cols)
        } else {
            bucket_size
        };
        let s = crate::ism::IsmW::create(dir, seq, name, cols, nrows, size, cache, big)?;
        Ok((NewMgr(Mgr::Ism(Box::new(s))), crate::ism::ism_blob(name)))
    }

    /// A new TiledColumnStMan (`column`) or TiledShapeStMan named `name`
    /// (the hypercolumn) for FixedShape columns of one cell shape, with
    /// `nrows` rows.
    #[allow(clippy::too_many_arguments)]
    pub fn tiled(
        dir: &Path,
        seq: u32,
        column: bool,
        name: &str,
        dtypes: Vec<i32>,
        cell: Option<Vec<i64>>,
        ndim: usize,
        tile: Vec<i64>,
        nrows: u64,
        big: bool,
    ) -> Result<Self> {
        let mut t = TsmW::create(dir, seq, column, name, dtypes, cell, ndim, tile, big)?;
        t.add_rows(nrows)?;
        Ok(NewMgr(Mgr::Tsm(Box::new(t))))
    }
}

/// The array records the rows of a table reference in each `table.fNi`:
/// (file name, record offset, element size in bits), for the alignment-gap
/// mask of research/e4-table-create.md (read only).
pub fn array_records(dir: impl AsRef<Path>) -> Result<Vec<(String, u64, u32)>> {
    let dir = dir.as_ref();
    let dat = TableDat::parse(&std::fs::read(dir.join("table.dat"))?)?;
    let nrows = match std::fs::read(dir.join("table.lock"))
        .ok()
        .and_then(|b| SyncRecord::parse(&b).ok().flatten())
    {
        Some(s) if s.nrows > 0 => s.nrows,
        _ => dat.nrows,
    };
    let mut out = Vec::new();
    for (slot, (kind, seq)) in dat.managers.iter().enumerate() {
        if kind == "IncrementalStMan" && dir.join(format!("table.f{seq}i")).is_file() {
            let mut cols = Vec::new();
            for (c, b) in dat.columns.iter().zip(&dat.bindings) {
                if b.seq == *seq {
                    cols.push(crate::ism::ism_col(c, b)?);
                }
            }
            let mut s = crate::ism::IsmW::open(
                dir,
                *seq,
                &dat.blobs[slot],
                cols,
                nrows,
                !dat.little_endian,
                false,
            )?;
            for (offset, bits) in s.array_offsets()? {
                out.push((format!("table.f{seq}i"), offset, bits));
            }
            continue;
        }
        if kind != "StandardStMan" || !dir.join(format!("table.f{seq}i")).is_file() {
            continue;
        }
        let mut cols = Vec::new();
        for (c, b) in dat.columns.iter().zip(&dat.bindings) {
            if b.seq == *seq {
                cols.push(ssm_col(c, b)?);
            }
        }
        let mut s = SsmW::open_mode(dir, *seq, &dat.blobs[slot], cols, false, !dat.little_endian)?;
        for k in 0..s.cols.len() {
            if s.cols[k].kind != SsmKind::Indirect {
                continue;
            }
            let bits = match s.cols[k].dtype {
                DataType::Bool => 1,
                dt => 8 * dt.size() as u32,
            };
            for row in 0..nrows {
                let (b, at) = s.slot(k, row)?;
                let offset = s.get_u64(b, at)?;
                if offset != 0 {
                    out.push((format!("table.f{seq}i"), offset, bits));
                }
            }
        }
    }
    Ok(out)
}

/// A table's row count and columns (name, type code, is array), read
/// without writing and without the task E reader (which does not read
/// every kind of table E5 writes).
/// Columns as (name, type code, is array).
pub type ColumnList = Vec<(String, i32, bool)>;

pub fn describe(dir: impl AsRef<Path>) -> Result<(u64, ColumnList)> {
    let dir = dir.as_ref();
    let dat = TableDat::parse(&std::fs::read(dir.join("table.dat"))?)?;
    let columns = dat
        .columns
        .iter()
        .map(|c| (c.name.clone(), c.dtype, c.is_array()))
        .collect();
    Ok((table_rows(dir, &dat), columns))
}

/// Read cells of a column of a table without writing anything: indirect
/// and string arrays of StandardStMan cell by cell (undefined cells and
/// rows of different shapes included), every other column through the
/// task E reader. `nrows` overrides the row count (a table open for
/// writing in this process: `table.lock` must not be touched).
pub fn read_cells(
    dir: impl AsRef<Path>,
    name: &str,
    start: u64,
    count: u64,
    nrows: Option<u64>,
) -> Result<Vec<Cell>> {
    let dir = dir.as_ref();
    if dir.join(crate::multifile::CONTAINER).is_file() {
        let tmp = extracted(dir)?;
        let out = read_cells_in(&tmp, name, start, count, nrows);
        let _ = std::fs::remove_dir_all(&tmp);
        return out;
    }
    read_cells_in(dir, name, start, count, nrows)
}

/// A MultiFile table's files in a temporary directory (`table.dat` and
/// `table.lock` copied beside the logical files), for reading.
fn extracted(dir: &Path) -> Result<PathBuf> {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    let tmp = std::env::temp_dir().join(format!(
        "rang-mf-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::Relaxed)
    ));
    crate::multifile::extract(&dir.join(crate::multifile::CONTAINER), &tmp)?;
    for f in ["table.dat", "table.lock", "table.info"] {
        if dir.join(f).is_file() {
            std::fs::copy(dir.join(f), tmp.join(f))?;
        }
    }
    Ok(tmp)
}

fn read_cells_in(
    dir: &Path,
    name: &str,
    start: u64,
    count: u64,
    nrows: Option<u64>,
) -> Result<Vec<Cell>> {
    let dat = TableDat::parse(&std::fs::read(dir.join("table.dat"))?)?;
    check_storage(dir, &dat)?;
    let index = dat.column(name)?;
    let seq = dat.bindings[index].seq;
    let slot = dat
        .managers
        .iter()
        .position(|(_, s)| *s == seq)
        .ok_or_else(|| MsError(format!("{name}: data manager {seq} is missing")))?;
    let desc = &dat.columns[index];
    if dat.managers[slot].0 == "MemoryStMan" {
        return err(format!(
            "{name}: a MemoryStMan column holds no data once its table is closed"
        ));
    }
    if dat.managers[slot].0.starts_with("Tiled") {
        let k = dat.bindings[..index]
            .iter()
            .filter(|b| b.seq == seq)
            .count();
        let mut t = open_tiled(dir, &dat, seq)?;
        let nrows = nrows.unwrap_or(table_rows(dir, &dat));
        if start + count > nrows {
            return err(format!("rows {start}..{} beyond the table", start + count));
        }
        return (start..start + count).map(|r| t.read_cell(k, r)).collect();
    }
    if dat.managers[slot].0 == "IncrementalStMan" {
        let nrows = nrows.unwrap_or(table_rows(dir, &dat));
        let mut cols = Vec::new();
        let mut k = 0;
        for (c, b) in dat.columns.iter().zip(&dat.bindings) {
            if b.seq == seq {
                if c.name == name {
                    k = cols.len();
                }
                cols.push(crate::ism::ism_col(c, b)?);
            }
        }
        let mut s = crate::ism::IsmW::open(
            dir,
            seq,
            &dat.blobs[slot],
            cols,
            nrows,
            !dat.little_endian,
            false,
        )?;
        return (start..start + count).map(|r| s.read_cell(k, r)).collect();
    }
    if dat.managers[slot].0 == "StandardStMan" && desc.is_array() {
        let mut cols = Vec::new();
        let mut k = 0;
        for (c, b) in dat.columns.iter().zip(&dat.bindings) {
            if b.seq == seq {
                if c.name == name {
                    k = cols.len();
                }
                cols.push(ssm_col(c, b)?);
            }
        }
        let kind = cols[k].kind;
        if matches!(kind, SsmKind::Indirect | SsmKind::StrArray) {
            let mut s =
                SsmW::open_mode(dir, seq, &dat.blobs[slot], cols, false, !dat.little_endian)?;
            return (start..start + count).map(|r| s.read_cell(k, r)).collect();
        }
    }
    let table = crate::ms::Table::open_with_rows(dir, nrows)?;
    let mut out = Vec::with_capacity(count as usize);
    for r in start..start + count {
        let data = table.read_column(name, r, 1)?;
        out.push(
            if data.dtype == Some(DataType::Str) || data.dtype.is_none() {
                Cell::Strings(data.shape, data.strings)
            } else {
                Cell::Values(data.shape, data.bytes)
            },
        );
    }
    Ok(out)
}

/// Cells of one shape as a column (None when a cell is undefined or the
/// shapes differ).
fn pack_cells(dtype: DataType, nrows: u64, cells: Vec<Cell>) -> Option<ColumnData> {
    let mut out = ColumnData {
        dtype: Some(dtype),
        nrows,
        ..Default::default()
    };
    for (i, cell) in cells.into_iter().enumerate() {
        let (shape, bytes, strings) = match cell {
            Cell::Undefined => return None,
            Cell::Values(shape, bytes) => (shape, bytes, Vec::new()),
            Cell::Strings(shape, strings) => (shape, Vec::new(), strings),
        };
        if i == 0 {
            out.shape = shape;
        } else if shape != out.shape {
            return None;
        }
        out.bytes.extend(bytes);
        out.strings.extend(strings);
    }
    Some(out)
}

/// The row count of a table: the sync record's, else `table.dat`'s.
fn table_rows(dir: &Path, dat: &TableDat) -> u64 {
    match std::fs::read(dir.join("table.lock"))
        .ok()
        .and_then(|b| SyncRecord::parse(&b).ok().flatten())
    {
        Some(s) if s.nrows > 0 => s.nrows,
        _ => dat.nrows,
    }
}

/// Counts of a serialisation-identity check.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct SerialisationCheck {
    pub tables: usize,
    pub ssm_files: usize,
    pub tiled_headers: usize,
    /// IncrementalStMan files (header, index, every bucket).
    pub ism_files: usize,
    /// Files whose parse and serialisation differ (or fail), with a reason.
    pub failures: Vec<String>,
}

/// `serialise(parse(x)) == x` for `table.dat`, every StandardStMan header
/// and index and every tiled header file of a table and its subtables
/// (criterion 7; read only).
pub fn check_serialisation(path: impl AsRef<Path>) -> Result<SerialisationCheck> {
    let root = path.as_ref();
    if root.join(crate::multifile::CONTAINER).is_file() {
        // The logical files of a MultiFile table, extracted beside a copy
        // of `table.dat`.
        let tmp = extracted(root)?;
        let out = check_serialisation(&tmp);
        let _ = std::fs::remove_dir_all(&tmp);
        return out;
    }
    let mut dirs = vec![root.to_path_buf()];
    let mut subs: Vec<PathBuf> = std::fs::read_dir(root)?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.join("table.dat").is_file())
        .collect();
    subs.sort();
    dirs.extend(subs);
    let mut out = SerialisationCheck::default();
    for dir in dirs {
        out.tables += 1;
        let bytes = std::fs::read(dir.join("table.dat"))?;
        let dat = match TableDat::parse(&bytes) {
            Ok(d) => d,
            Err(e) => {
                out.failures.push(format!("{}: {e}", dir.display()));
                continue;
            }
        };
        if dat.serialise() != bytes {
            out.failures
                .push(format!("{}/table.dat differs", dir.display()));
        }
        for ((kind, seq), blob) in dat.managers.iter().zip(&dat.blobs) {
            let file = dir.join(format!("table.f{seq}"));
            let check = || -> Result<bool> {
                match kind.as_str() {
                    "StandardStMan" => {
                        let (raw, h, indices) = read_ssm(&file, dat.little_endian)?;
                        let header = h.serialise();
                        let index = serialise_ssm_index(&indices, h.big);
                        let on_disk = read_ssm_index(&mut File::open(&file)?, &h)?;
                        Ok(raw[..header.len()] == header[..]
                            && index == on_disk
                            && SsmBlob::parse(blob)?.serialise() == *blob)
                    }
                    "TiledColumnStMan" | "TiledShapeStMan" | "TiledCellStMan"
                    | "TiledDataStMan" => {
                        let bytes = std::fs::read(&file)?;
                        Ok(TsmHeader::parse(&bytes)?.serialise() == bytes)
                    }
                    "IncrementalStMan" => {
                        let ncol = dat.bindings.iter().filter(|b| b.seq == *seq).count();
                        crate::ism::check_file(&file, ncol, !dat.little_endian)
                    }
                    _ => Ok(true),
                }
            };
            match kind.as_str() {
                "StandardStMan" => out.ssm_files += 1,
                "TiledColumnStMan" | "TiledShapeStMan" | "TiledCellStMan" | "TiledDataStMan" => {
                    out.tiled_headers += 1
                }
                "IncrementalStMan" => out.ism_files += 1,
                _ => continue,
            }
            match check() {
                Ok(true) => {}
                Ok(false) => out.failures.push(format!("{} differs", file.display())),
                Err(e) => out.failures.push(format!("{}: {e}", file.display())),
            }
        }
    }
    Ok(out)
}

/// Apply `f` to the record at `parents` below `record`, keeping the
/// descriptions of fixed sub-records in step with their contents.
fn edit_nested(
    record: &mut crate::aipsio::Record,
    parents: &[&str],
    f: &mut dyn FnMut(&mut crate::aipsio::Record) -> Result<()>,
) -> Result<()> {
    let Some((first, rest)) = parents.split_first() else {
        return f(record);
    };
    let sub = record.subrecord_mut(first)?;
    edit_nested(sub, rest, f)?;
    let desc = sub.desc.clone();
    let i = record.field(first).unwrap();
    if let Some(s) = record.desc.fields[i].sub.as_mut()
        && !s.fields.is_empty()
    {
        *s = desc;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tsm_header_uses_version_2_records_from_two_gib() {
        let mut h = TsmHeader::new("TiledColumnStMan", 3, "H", vec![6], 3, false);
        h.column_tile = Some(vec![4, 512, 16]);
        h.files = vec![Some(TsmFileEntry {
            seq: 0,
            length: (1 << 31) - 1,
        })];
        let small = h.serialise();
        let parsed = TsmHeader::parse(&small).unwrap();
        assert_eq!(parsed.files[0].as_ref().unwrap().length, (1 << 31) - 1);
        h.files[0].as_mut().unwrap().length = 13 << 30;
        h.writable().unwrap();
        let big = h.serialise();
        assert_eq!(big.len(), small.len() + 4);
        let parsed = TsmHeader::parse(&big).unwrap();
        assert_eq!(parsed.files[0].as_ref().unwrap().length, 13 << 30);
    }

    #[test]
    fn real_tsm_headers_round_trip_when_given() {
        let Ok(path) = std::env::var("RANG_MS_FIXTURE") else {
            return;
        };
        let dir = PathBuf::from(path);
        let dat = TableDat::parse(&std::fs::read(dir.join("table.dat")).unwrap()).unwrap();
        for (kind, seq) in &dat.managers {
            if !kind.starts_with("Tiled") {
                continue;
            }
            let bytes = std::fs::read(dir.join(format!("table.f{seq}"))).unwrap();
            let h = TsmHeader::parse(&bytes).unwrap();
            assert_eq!(h.serialise(), bytes, "f{seq}");
            eprintln!("f{seq}: {h:?}");
        }
    }

    #[test]
    fn sync_record_counts_like_casacore() {
        let mut s = SyncRecord::default();
        s.update(140, 25, false, &[false, true]);
        assert_eq!(
            (s.modify, s.table_change, s.dm_change.clone()),
            (1, 0, vec![0, 1])
        );
        s.update(140, 26, true, &[false, false, true]);
        assert_eq!(
            (s.modify, s.table_change, s.dm_change.clone()),
            (2, 1, vec![0, 1, 1])
        );
        s.update(140, 26, false, &[false, false, false]);
        assert_eq!(s.modify, 2);
        let mut lock = vec![0u8; LOCK_REQUESTS];
        lock.extend(s.serialise());
        assert_eq!(SyncRecord::parse(&lock).unwrap(), Some(s));
    }

    #[test]
    fn ssm_header_and_index_round_trip() {
        let h = SsmHeader {
            big: false,
            bucket_size: 4096,
            nr_buckets: 4,
            pers_cache: 2,
            nr_free: 1,
            first_free: 3,
            nr_idx_buckets: 1,
            first_idx_bucket: 2,
            idx_bucket_offset: 8,
            last_string_bucket: -1,
            idx_length: 100,
            nr_indices: 1,
        };
        let bytes = h.serialise();
        assert_eq!(SsmHeader::parse(&bytes, true).unwrap(), h);
        let index = SsmIndexFull {
            rows_per_bucket: 32,
            n_columns: 2,
            free: vec![(1000, 3096)],
            last_row: vec![31, 63, 70],
            bucket: vec![0, 1, 3],
        };
        let raw = serialise_ssm_index(std::slice::from_ref(&index), false);
        let mut c = Cursor::new(&raw, false);
        assert_eq!(SsmIndexFull::read(&mut c).unwrap(), index);
        assert_eq!(index.find(64).unwrap(), (3, 64));
        assert!(index.find(71).is_err());
        let blob = SsmBlob {
            name: "SSM".into(),
            col_offset: vec![0, 4],
            col_index: vec![0, 0],
        };
        assert_eq!(SsmBlob::parse(&blob.serialise()).unwrap(), blob);
    }

    fn scratch_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("rang-e3-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn file_buffer_leaves_stale_bytes_past_the_end_as_casacore_does() {
        let dir = scratch_dir("filebuf");
        let path = dir.join("f");
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(&path)
            .unwrap();
        let mut io = FileBuf::new(file, 16);
        io.seek(0);
        io.write(b"ABCD").unwrap();
        // Byte 20 is in block 1, beyond the end of the file: the buffer is
        // flushed, nothing is read, and its old bytes stay.
        io.seek(20);
        io.write(b"Z").unwrap();
        io.flush().unwrap();
        let bytes = std::fs::read(&path).unwrap();
        assert_eq!(&bytes[..4], b"ABCD");
        assert_eq!(&bytes[16..21], b"ABCDZ");
        // A write of whole blocks bypasses the buffer.
        io.seek(32);
        io.write(&[7u8; 40]).unwrap();
        io.flush().unwrap();
        assert_eq!(std::fs::read(&path).unwrap()[32..72], [7u8; 40]);
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn array_file_reserves_aligned_arrays() {
        let dir = scratch_dir("arrays");
        let path = dir.join("table.f0i");
        let mut a = ArrayFile::open(&path).unwrap();
        assert_eq!((a.version, a.leng), (0, 16));
        let first = a.put_res(&[3, 4], DataType::Bool).unwrap();
        assert_eq!(first, 16);
        // 12 bytes of shape, 2 bytes of 12 bits: next array at 32.
        assert_eq!(a.leng, 30);
        let second = a.put_res(&[2], DataType::Complex).unwrap();
        assert_eq!(second, 32);
        let (shape, values) = a.shape(first).unwrap();
        assert_eq!((shape, values), (vec![3, 4], 28));
        a.put_values(values, DataType::Bool, &[1; 12]).unwrap();
        a.flush().unwrap();
        let bytes = std::fs::read(&path).unwrap();
        assert_eq!(bytes.len(), 32 + 8 + 16);
        assert_eq!(u64::from_le_bytes(bytes[4..12].try_into().unwrap()), 56);
        assert_eq!(&bytes[28..30], &[0xff, 0x0f]);
        let mut b = ArrayFile::open(&path).unwrap();
        assert_eq!(b.leng, 56);
        assert_eq!(b.shape(second).unwrap().0, vec![2]);
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn bits_are_set_without_touching_neighbours() {
        let mut out = vec![0b1000_0001u8, 0xff];
        put_bits(&mut out, 1, &[1, 0, 1]);
        assert_eq!(out[0], 0b1000_0011 | 0b1000);
        put_bits(&mut out, 8, &[0; 8]);
        assert_eq!(out[1], 0);
    }

    #[test]
    fn new_standard_manager_toggles_its_index_like_casacore() {
        let dir = scratch_dir("ssm");
        let col = SsmCol {
            name: "FLAG_ROW".into(),
            dtype: DataType::Bool,
            kind: SsmKind::Scalar,
            bits: 1,
            fixed: None,
        };
        let mut s = SsmW::create(&dir, 0, "SSM", vec![col], 10, 0, 1024, 2, false).unwrap();
        assert_eq!(s.h.bucket_size, 1024);
        assert!(s.flush().unwrap());
        // The first index goes to a new bucket; it fits half a bucket.
        let (_, h, indices) = read_ssm(&dir.join("table.f0"), true).unwrap();
        assert_eq!(
            (h.nr_buckets, h.first_idx_bucket, h.idx_bucket_offset),
            (2, 1, 8)
        );
        assert_eq!(indices[0].last_row, vec![9]);
        assert!(!s.flush().unwrap());
        s.put(0, 0, 10, &[], &[1, 0, 1, 0, 1, 0, 1, 0, 1, 1])
            .unwrap();
        assert!(s.flush().unwrap());
        let (_, h2, _) = read_ssm(&dir.join("table.f0"), true).unwrap();
        assert_eq!(h2.idx_bucket_offset, 8 + 508);
        let bucket = std::fs::read(dir.join("table.f0")).unwrap();
        assert_eq!(&bucket[512..514], &[0b0101_0101, 0b11]);
        s.put(0, 9, 1, &[], &[0]).unwrap();
        s.flush().unwrap();
        assert_eq!(
            read_ssm(&dir.join("table.f0"), true)
                .unwrap()
                .1
                .idx_bucket_offset,
            8
        );
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn tiled_header_round_trips() {
        let cube = TsmCube {
            values: empty_values_record(),
            extensible: true,
            nrdim: 3,
            shape: vec![4, 64, 10],
            tile: vec![4, 16, 4],
            file_seq: 0,
            offset: 0,
        };
        let h = TsmHeader {
            kind: "TiledColumnStMan".into(),
            column_tile: Some(vec![4, 16, 4]),
            big: false,
            seq: 3,
            nrows: 10,
            dtypes: vec![0],
            hypercolumn: "TCS".into(),
            max_cache: 0,
            nrdim: 3,
            files: vec![Some(TsmFileEntry {
                seq: 0,
                length: 4096,
            })],
            cubes: vec![cube],
            default_tile: Vec::new(),
            row_map: Vec::new(),
            cube_map: Vec::new(),
            pos_map: Vec::new(),
            nrrow_last: 0,
            data_row_map: Vec::new(),
        };
        let bytes = h.serialise();
        assert_eq!(TsmHeader::parse(&bytes).unwrap(), h);
        assert_eq!(empty_values_record().len(), 48);
    }

    /// `serialise(parse(x)) == x` and a write round trip on a copy of a real
    /// table when `RANG_MS_FIXTURE` names one (the checker covers all three
    /// MSs against casacore).
    #[test]
    fn real_table_writes_round_trip_when_given() {
        let Ok(path) = std::env::var("RANG_MS_FIXTURE") else {
            return;
        };
        let check = check_serialisation(&path).unwrap();
        assert!(check.failures.is_empty(), "{:?}", check.failures);
        let dir = scratch_dir("fixture");
        let copy = dir.join("t.ms");
        std::fs::create_dir_all(&copy).unwrap();
        for entry in std::fs::read_dir(&path).unwrap() {
            let p = entry.unwrap().path();
            if p.is_file() {
                std::fs::copy(&p, copy.join(p.file_name().unwrap())).unwrap();
            }
        }
        let before = crate::ms::Table::open(&copy).unwrap();
        let rows = before.read_column("FLAG_ROW", 0, 0).unwrap();
        let flipped: Vec<u8> = rows.bytes.iter().map(|&b| 1 - b).collect();
        let mut w = TableWriter::open(&copy, 1, std::time::Duration::ZERO).unwrap();
        w.put_column("FLAG_ROW", 0, 0, &[], &flipped).unwrap();
        w.put_keyword(None, &["RANG_E3"], KeywordValue::String("test".into()))
            .unwrap();
        w.close().unwrap();
        let after = crate::ms::Table::open(&copy).unwrap();
        assert_eq!(after.read_column("FLAG_ROW", 0, 0).unwrap().bytes, flipped);
        let dat = TableDat::parse(&std::fs::read(copy.join("table.dat")).unwrap()).unwrap();
        assert!(dat.keywords.field("RANG_E3").is_some());
        std::fs::remove_dir_all(dir).unwrap();
    }
}
