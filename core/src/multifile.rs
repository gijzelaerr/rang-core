// SPDX-License-Identifier: GPL-3.0-or-later
//! MultiFile tables (research/e5-table-writer-rest.md,
//! research/e6-table-writer-final.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! casacore's `MultiFile` container (version 2, as casacore 3.8.1 writes
//! it): block 0 holds the header (the change counter, block size and count,
//! then an AipsIO `MultiFile` object with every logical file's name, size
//! and nesting flag, then each file's packed block list, the free list, the
//! CRC list and the two header-continuation lists, all canonical
//! big-endian); a header longer than a block continues in continuation
//! blocks (two alternating sets, each block starting with the number of the
//! next), every other block belongs to one logical file.
//!
//! The table writer keeps the logical files in a staging directory inside
//! the table while it is open. Its managers report the writes casacore's
//! managers make, in casacore's order (`Event`s on a shared log: a file
//! created anew, which deletes an old one of the name, and every write with
//! its offset and length); the container replays them through a model of
//! `MultiFileBase` (`write` extending a file at every write that reaches its
//! last block, taking free blocks from the tail of the descending free list
//! first, and marking the header changed; `deleteFile` freeing a file's
//! blocks and truncating the container when they are at its end) and, at
//! each table flush, writes the blocks of the files written since the last
//! one from the staged contents (zero past a file's end) and the header if
//! it changed. The format was read in the casacore sources; nothing is
//! copied from casacore (LGPL-2.1-or-later).

use std::cell::RefCell;
use std::fs::{File, OpenOptions};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use crate::aipsio::Writer;
use crate::ms::{Cursor, MsError, Result};
use crate::ms_write::{read_at, write_at};

fn err<T>(message: impl Into<String>) -> Result<T> {
    Err(MsError(message.into()))
}

/// The container's name in a table directory.
pub const CONTAINER: &str = "table.mf";
/// Where the table writer keeps the logical files while a table is open.
pub const STAGING: &str = "table.mf.rang-staging";
/// casacore's default block size (`table.storage.blocksize`).
pub const DEFAULT_BLOCK_SIZE: i64 = 4 * 1024 * 1024;

// ---------------------------------------------------------------------------
// The write log.

/// A write casacore's managers make to a logical file.
#[derive(Clone, Debug, PartialEq)]
pub enum Event {
    /// `createFile(name, ByteIO::New)`: an old file of the name is deleted.
    Create(String),
    /// `write(file, offset, length)`.
    Write(String, u64, u64),
}

/// The log of a MultiFile table's writes, shared by its managers.
pub type MfLog = Arc<Mutex<Vec<Event>>>;

thread_local! {
    static CURRENT: RefCell<Option<MfLog>> = const { RefCell::new(None) };
}

/// Run `f` with `log` as the log new managers attach to (creation and
/// opening of a MultiFile table's managers).
pub fn with_log<T>(log: Option<&MfLog>, f: impl FnOnce() -> T) -> T {
    let old = CURRENT.with(|c| c.replace(log.cloned()));
    let out = f();
    CURRENT.with(|c| *c.borrow_mut() = old);
    out
}

/// The log of the MultiFile table whose managers are being made, if any.
pub fn current() -> Option<MfLog> {
    CURRENT.with(|c| c.borrow().clone())
}

/// Report an event (nothing for a table without MultiFile).
pub fn emit(log: &Option<MfLog>, event: Event) {
    if let Some(l) = log {
        l.lock().unwrap().push(event);
    }
}

/// The base name of a staged file's path.
pub fn name_of(path: &Path) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default()
}

// ---------------------------------------------------------------------------
// The header.

/// One logical file (`MultiFileInfo`); an empty name is a free slot.
#[derive(Clone, Debug, PartialEq)]
pub struct Info {
    pub name: String,
    pub fsize: i64,
    pub nested: bool,
    pub blocks: Vec<i64>,
}

/// The header of a MultiFile container.
#[derive(Clone, Debug, PartialEq)]
pub struct Header {
    pub counter: i64,
    pub block_size: i64,
    pub nr_block: i64,
    pub use_crc: bool,
    pub infos: Vec<Info>,
    pub free: Vec<i64>,
    pub crc: Vec<u32>,
    pub cont: [Vec<i64>; 2],
    pub ncont_used: [u32; 2],
    /// The first continuation block (bytes 8-15; 0: none).
    pub first_cont: i64,
    /// The continuation set in use (`itsHdrContInx`).
    pub cont_inx: usize,
}

fn be64(b: &[u8], at: usize) -> Result<i64> {
    b.get(at..at + 8)
        .map(|x| i64::from_be_bytes(x.try_into().unwrap()))
        .ok_or_else(|| MsError("truncated MultiFile header".into()))
}

fn be32(b: &[u8], at: usize) -> Result<u32> {
    b.get(at..at + 4)
        .map(|x| u32::from_be_bytes(x.try_into().unwrap()))
        .ok_or_else(|| MsError("truncated MultiFile header".into()))
}

/// `MultiFile::packIndex`: runs of consecutive blocks as the first block
/// and minus the count of the rest.
pub fn pack_index(blocks: &[i64]) -> Vec<i64> {
    let mut out = Vec::new();
    let Some(&first) = blocks.first() else {
        return out;
    };
    out.push(first);
    let mut start = first;
    let mut next = first + 1;
    for &b in &blocks[1..] {
        if b != next {
            let nr = next - start - 1;
            if nr > 0 {
                out.push(-nr);
            }
            start = b;
            out.push(b);
            next = b;
        }
        next += 1;
    }
    let nr = next - start - 1;
    if nr > 0 {
        out.push(-nr);
    }
    out
}

/// `MultiFile::unpackIndex`.
pub fn unpack_index(packed: &[i64]) -> Vec<i64> {
    let mut out: Vec<i64> = Vec::with_capacity(packed.len());
    for &b in packed {
        if b < 0 {
            let next = out.last().copied().unwrap_or(0) + 1;
            for i in 0..(-b) {
                out.push(next + i);
            }
        } else {
            out.push(b);
        }
    }
    out
}

fn vector(out: &mut Vec<u8>, v: &[i64]) {
    out.extend((v.len() as i64).to_be_bytes());
    for &x in v {
        out.extend(x.to_be_bytes());
    }
}

impl Header {
    pub fn new(block_size: i64) -> Self {
        Header {
            counter: 0,
            block_size,
            nr_block: 1,
            use_crc: false,
            infos: Vec::new(),
            free: Vec::new(),
            crc: Vec::new(),
            cont: [Vec::new(), Vec::new()],
            ncont_used: [0, 0],
            first_cont: 0,
            cont_inx: 0,
        }
    }

    /// The whole header from block 0 and its continuation blocks
    /// (`readRemainder`); `block` reads one block of the container.
    pub fn read(block0: &[u8], mut block: impl FnMut(i64) -> Result<Vec<u8>>) -> Result<Vec<u8>> {
        let size = be64(block0, 32)? as usize;
        let bs = be64(block0, 40)? as usize;
        let mut h = block0[..bs.min(block0.len())].to_vec();
        let mut next = be64(block0, 8)?;
        let cbs = bs - 8;
        while h.len() < size {
            if next == 0 {
                return err("MultiFile header continuation ends early");
            }
            let b = block(next)?;
            let n = (size - h.len()).min(cbs);
            h.extend_from_slice(&b[8..8 + n]);
            next = be64(&b, 0)?;
        }
        if size > bs && next != 0 {
            return err("MultiFile header continuation does not end");
        }
        h.truncate(size);
        Ok(h)
    }

    /// `MultiFile::readHeader` (version 2) of the whole header bytes.
    pub fn parse(h: &[u8]) -> Result<Self> {
        if be64(h, 0)? != 0 {
            return err("MultiFile header version 1 is not supported");
        }
        let first_cont = be64(h, 8)?;
        let counter = be64(h, 16)?;
        let version = be32(h, 24)?;
        if version != 2 {
            return err(format!("MultiFile version {version} is not supported"));
        }
        let size = be64(h, 32)? as usize;
        let block_size = be64(h, 40)?;
        let nr_block = be64(h, 48)?;
        let use_crc = h.get(56).copied().unwrap_or(0) != 0;
        if use_crc {
            return err("MultiFile containers with block CRCs are not supported");
        }
        let h = h
            .get(..size)
            .ok_or_else(|| MsError("truncated MultiFile header".into()))?;
        let mut c = Cursor::new(&h[64..], true);
        c.magic()?;
        let object = c.start_expect("MultiFile")?;
        let block = c.start_expect("Block")?;
        let n = c.u32()? as usize;
        let mut infos = Vec::with_capacity(n);
        for _ in 0..n {
            let name = c.string()?;
            let fsize = c.i64()?;
            let nested = c.bool()?;
            infos.push(Info {
                name,
                fsize,
                nested,
                blocks: Vec::new(),
            });
        }
        c.end(&block);
        c.end(&object);
        let mut at = 64 + c.pos;
        let read_vector = |at: &mut usize| -> Result<Vec<i64>> {
            let n = be64(h, *at)? as usize;
            *at += 8;
            let v = (0..n)
                .map(|i| be64(h, *at + 8 * i))
                .collect::<Result<Vec<_>>>()?;
            *at += 8 * n;
            Ok(v)
        };
        for info in &mut infos {
            info.blocks = unpack_index(&read_vector(&mut at)?);
        }
        let free = unpack_index(&read_vector(&mut at)?);
        let ncrc = be64(h, at)? as usize;
        at += 8;
        let crc = (0..ncrc)
            .map(|i| be32(h, at + 4 * i))
            .collect::<Result<Vec<_>>>()?;
        at += 4 * ncrc;
        let cont0 = read_vector(&mut at)?;
        let cont1 = read_vector(&mut at)?;
        let ncont_used = [be32(h, at)?, be32(h, at + 4)?];
        at += 8;
        if at != size {
            return err("MultiFile header length mismatches its contents");
        }
        let cont_inx = usize::from(!cont1.is_empty() && first_cont == cont1[0]);
        Ok(Header {
            counter,
            block_size,
            nr_block,
            use_crc,
            infos,
            free,
            crc,
            cont: [cont0, cont1],
            ncont_used,
            first_cont,
            cont_inx,
        })
    }

    /// The header bytes before the continuation lists (`writeHeader` up to
    /// the CRC list); the first-continuation field and size are patched
    /// later.
    fn head(&self) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend(0i64.to_be_bytes());
        out.extend(0i64.to_be_bytes());
        out.extend(self.counter.to_be_bytes());
        out.extend(2i32.to_be_bytes());
        out.extend(0u32.to_be_bytes());
        out.extend(0i64.to_be_bytes()); // header size, patched below
        out.extend(self.block_size.to_be_bytes());
        out.extend(self.nr_block.to_be_bytes());
        let mut flags = [0u8; 8];
        flags[0] = u8::from(self.use_crc);
        out.extend(flags);
        let mut w = Writer::new(true);
        w.putstart("MultiFile", 2);
        w.putstart("Block", 1);
        w.u32(self.infos.len() as u32);
        for info in &self.infos {
            w.string(&info.name);
            w.i64(info.fsize);
            w.bool(info.nested);
        }
        w.putend();
        w.putend();
        out.extend(w.buf);
        for info in &self.infos {
            vector(&mut out, &pack_index(&info.blocks));
        }
        vector(&mut out, &pack_index(&self.free));
        out.extend((self.crc.len() as i64).to_be_bytes());
        for &x in &self.crc {
            out.extend(x.to_be_bytes());
        }
        out
    }

    /// The header bytes as they are (no change made): what `parse` read.
    pub fn serialise(&self) -> Vec<u8> {
        let mut out = self.head();
        vector(&mut out, &self.cont[0]);
        vector(&mut out, &self.cont[1]);
        out.extend(self.ncont_used[0].to_be_bytes());
        out.extend(self.ncont_used[1].to_be_bytes());
        let n = out.len() as i64;
        out[8..16].copy_from_slice(&self.first_cont.to_be_bytes());
        out[32..40].copy_from_slice(&n.to_be_bytes());
        out
    }

    /// `MultiFile::writeHeader`: the counter incremented, then the blocks
    /// to write (block 0 last): with continuation (`writeRemainder`) the
    /// other set is used, extended at the end of the container when it is
    /// too short, its chunks written through one buffer (a chunk shorter
    /// than a block leaves the previous chunk's bytes after it; the first
    /// leaves zeros here, uninitialised memory in casacore).
    pub fn write(&mut self) -> Vec<(i64, Vec<u8>)> {
        self.counter += 1;
        let bs = self.block_size as usize;
        let mut mio = self.head();
        let todo = mio.len();
        let total = todo + 8 + (2 + self.cont[0].len() + self.cont[1].len()) * 8;
        let mut blocks = Vec::new();
        if total > bs {
            let rem = (todo - bs) as i64;
            let new = 1 - self.cont_inx;
            let cbs = self.block_size - 8;
            let other = self.cont[self.cont_inx].len() as i64;
            let old = self.cont[new].len() as i64;
            let mut ncont = (rem + cbs - 1) / cbs;
            let mut ncont_new = ncont.max(old);
            loop {
                let sz = rem + 8 + (other + ncont_new + 2) * 8;
                ncont = (sz + cbs - 1) / cbs;
                if ncont <= ncont_new {
                    break;
                }
                ncont_new = ncont;
            }
            for _ in old..ncont_new {
                self.cont[new].push(self.nr_block);
                self.nr_block += 1;
            }
            vector(&mut mio, &self.cont[0]);
            vector(&mut mio, &self.cont[1]);
            self.ncont_used[new] = ncont_new as u32;
            mio.extend(self.ncont_used[0].to_be_bytes());
            mio.extend(self.ncont_used[1].to_be_bytes());
            let mut buf = vec![0u8; bs];
            let mut from = bs;
            for i in 0..ncont as usize {
                let next = if i == ncont as usize - 1 {
                    0
                } else {
                    self.cont[new][i + 1]
                };
                buf[..8].copy_from_slice(&next.to_be_bytes());
                let n = (mio.len() - from).min(bs - 8);
                buf[8..8 + n].copy_from_slice(&mio[from..from + n]);
                from += bs - 8;
                blocks.push((self.cont[new][i], buf.clone()));
            }
            self.first_cont = self.cont[new][0];
            mio[8..16].copy_from_slice(&self.first_cont.to_be_bytes());
            self.cont_inx = new;
            mio[48..56].copy_from_slice(&self.nr_block.to_be_bytes());
        } else {
            vector(&mut mio, &self.cont[0]);
            vector(&mut mio, &self.cont[1]);
            self.ncont_used[self.cont_inx] = 0;
            mio.extend(self.ncont_used[0].to_be_bytes());
            mio.extend(self.ncont_used[1].to_be_bytes());
            self.first_cont = 0;
        }
        let n = mio.len() as i64;
        mio[32..40].copy_from_slice(&n.to_be_bytes());
        let mut block0 = vec![0u8; bs];
        let k = mio.len().min(bs);
        block0[..k].copy_from_slice(&mio[..k]);
        blocks.push((0, block0));
        blocks
    }

    fn id(&self, name: &str) -> Option<usize> {
        self.infos.iter().position(|i| i.name == name)
    }

    /// `MultiFileBase::addFile`: the last free slot, else a new one.
    fn add_file(&mut self, name: &str) -> usize {
        let at = self
            .infos
            .iter()
            .rposition(|i| i.name.is_empty())
            .unwrap_or(self.infos.len());
        let info = Info {
            name: name.to_string(),
            fsize: 0,
            nested: false,
            blocks: Vec::new(),
        };
        if at == self.infos.len() {
            self.infos.push(info);
        } else {
            self.infos[at] = info;
        }
        at
    }

    /// `MultiFile::doTruncateFile` to `nrblk` blocks: the rest to the free
    /// list (descending), the container shortened for free blocks at its
    /// end (`truncateIfNeeded`); returns the new container length when it
    /// shrank.
    fn truncate_blocks(&mut self, id: usize, nrblk: usize) -> Option<i64> {
        let info = &mut self.infos[id];
        if nrblk >= info.blocks.len() {
            return None;
        }
        self.free.extend(info.blocks.drain(nrblk..));
        self.free.sort_unstable_by(|a, b| b.cmp(a));
        let mut last = self.nr_block - 1;
        let mut i = 0;
        while i < self.free.len() && self.free[i] == last {
            last -= 1;
            i += 1;
        }
        if i > 0 {
            self.free.drain(..i);
            self.nr_block -= i as i64;
            return Some(self.nr_block * self.block_size);
        }
        None
    }

    /// `MultiFile::extendVF` with free blocks first.
    fn extend(&mut self, id: usize, lastblk: usize) {
        let have = self.infos[id].blocks.len();
        if lastblk < have {
            self.infos[id].blocks.truncate(lastblk);
            return;
        }
        for _ in have..lastblk {
            let b = match self.free.pop() {
                Some(b) => b,
                None => {
                    self.nr_block += 1;
                    self.nr_block - 1
                }
            };
            self.infos[id].blocks.push(b);
        }
    }
}

/// Whether `table.mf` of a table parses and serialises to its header bytes
/// (read only).
pub fn check(dir: impl AsRef<Path>) -> Result<bool> {
    let path = dir.as_ref().join(CONTAINER);
    let mut file = File::open(&path).map_err(|e| MsError(format!("{}: {e}", path.display())))?;
    let bytes = read_header(&mut file)?;
    let h = Header::parse(&bytes)?;
    Ok(h.serialise() == bytes)
}

/// The whole header of an open container.
fn read_header(file: &mut File) -> Result<Vec<u8>> {
    let head = read_at(file, 0, 64)?;
    let bs = be64(&head, 40)?;
    let block0 = read_at(file, 0, bs as usize)?;
    Header::read(&block0, |b| read_at(file, (b * bs) as u64, bs as usize))
}

/// Write every logical file of a container into `dest` (its content up to
/// its size).
pub fn extract(container: &Path, dest: &Path) -> Result<Header> {
    let mut file =
        File::open(container).map_err(|e| MsError(format!("{}: {e}", container.display())))?;
    let h = Header::parse(&read_header(&mut file)?)?;
    let block = h.block_size;
    std::fs::create_dir_all(dest)?;
    for info in h.infos.iter().filter(|i| !i.name.is_empty()) {
        let mut content = Vec::with_capacity(info.fsize as usize);
        for &b in &info.blocks {
            let left = info.fsize as usize - content.len();
            if left == 0 {
                break;
            }
            let n = left.min(block as usize);
            content.extend(read_at(&mut file, (b * block) as u64, n)?);
        }
        std::fs::write(dest.join(&info.name), content)?;
    }
    Ok(h)
}

// ---------------------------------------------------------------------------
// The container being written.

/// A MultiFile container being written: casacore's `MultiFile` state, the
/// staging directory with the logical files, the log of the managers'
/// writes.
pub struct Container {
    pub path: PathBuf,
    pub staging: PathBuf,
    pub header: Header,
    pub log: MfLog,
    /// `itsChanged`: the header is written at the next flush.
    changed: bool,
    /// Files written since the last flush.
    dirty: std::collections::BTreeSet<String>,
    /// The container's length as casacore leaves it.
    length: u64,
}

impl Container {
    /// A new container (`MultiFile` with `ByteIO::New`: changed).
    pub fn create(dir: &Path, block_size: i64) -> Result<Self> {
        let staging = dir.join(STAGING);
        if staging.exists() {
            std::fs::remove_dir_all(&staging)?;
        }
        std::fs::create_dir_all(&staging)?;
        Ok(Container {
            path: dir.join(CONTAINER),
            staging,
            header: Header::new(block_size),
            log: Arc::new(Mutex::new(Vec::new())),
            changed: true,
            dirty: Default::default(),
            length: 0,
        })
    }

    /// An existing container, its files extracted into the staging
    /// directory.
    pub fn open(dir: &Path) -> Result<Self> {
        let staging = dir.join(STAGING);
        if staging.exists() {
            std::fs::remove_dir_all(&staging)?;
        }
        let path = dir.join(CONTAINER);
        let header = extract(&path, &staging)?;
        let length = std::fs::metadata(&path)?.len();
        Ok(Container {
            path,
            staging,
            header,
            log: Arc::new(Mutex::new(Vec::new())),
            changed: false,
            dirty: Default::default(),
            length,
        })
    }

    /// Replay the logged writes on casacore's `MultiFile` model.
    fn apply(&mut self) {
        let events: Vec<Event> = std::mem::take(&mut *self.log.lock().unwrap());
        let bs = self.header.block_size;
        for e in events {
            match e {
                Event::Create(name) => {
                    if let Some(id) = self.header.id(&name) {
                        if let Some(len) = self.header.truncate_blocks(id, 0) {
                            self.length = self.length.min(len as u64);
                        }
                        self.header.infos[id] = Info {
                            name: String::new(),
                            fsize: 0,
                            nested: false,
                            blocks: Vec::new(),
                        };
                    }
                    self.header.add_file(&name);
                    self.changed = true;
                    self.dirty.insert(name);
                }
                Event::Write(name, offset, size) => {
                    let id = match self.header.id(&name) {
                        Some(id) => id,
                        None => {
                            self.changed = true;
                            self.header.add_file(&name)
                        }
                    };
                    let (offset, size) = (offset as i64, size as i64);
                    let blknr = offset / bs;
                    let start = offset - blknr * bs;
                    let lastblk = blknr + (start + size + bs - 1) / bs;
                    let curnrb = (self.header.infos[id].fsize + bs - 1) / bs;
                    if lastblk >= curnrb {
                        self.header.extend(id, lastblk as usize);
                        self.changed = true;
                    }
                    let info = &mut self.header.infos[id];
                    info.fsize = info.fsize.max(offset + size);
                    self.dirty.insert(name);
                }
            }
        }
    }

    /// The table's flush (`MultiFileBase::flush`): the logged writes
    /// replayed, the blocks of the files written since the last flush
    /// written from their staged contents, then the header when it changed.
    pub fn pack(&mut self) -> Result<()> {
        self.apply();
        let bs = self.header.block_size;
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&self.path)
            .map_err(|e| MsError(format!("{}: {e}", self.path.display())))?;
        for name in std::mem::take(&mut self.dirty) {
            let Some(id) = self.header.id(&name) else {
                continue;
            };
            let content = std::fs::read(self.staging.join(&name)).unwrap_or_default();
            // The staged file is what casacore's writes made; should it be
            // longer than they reached, the container keeps all of it.
            let len = content.len() as i64;
            if len > self.header.infos[id].fsize {
                let need = (len + bs - 1) / bs;
                if need as usize > self.header.infos[id].blocks.len() {
                    self.header.extend(id, need as usize);
                    self.changed = true;
                }
                self.header.infos[id].fsize = len;
            }
            let blocks = self.header.infos[id].blocks.clone();
            for (k, &b) in blocks.iter().enumerate() {
                let from = k * bs as usize;
                let mut chunk = vec![0u8; bs as usize];
                if from < content.len() {
                    let n = (content.len() - from).min(bs as usize);
                    chunk[..n].copy_from_slice(&content[from..from + n]);
                }
                write_at(&mut file, (b * bs) as u64, &chunk)?;
                self.length = self.length.max(((b + 1) * bs) as u64);
            }
        }
        if self.changed {
            for (b, bytes) in self.header.write() {
                write_at(&mut file, (b * bs) as u64, &bytes)?;
                self.length = self.length.max(((b + 1) * bs) as u64);
            }
            self.changed = false;
        }
        if file.metadata()?.len() != self.length {
            file.set_len(self.length)?;
        }
        file.sync_all()?;
        Ok(())
    }

    /// Remove the staging directory (the table is closed).
    pub fn close(&self) -> Result<()> {
        if self.staging.exists() {
            std::fs::remove_dir_all(&self.staging)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn block_lists_pack_and_unpack() {
        let blocks = vec![3, 4, 5, 9, 1, 2];
        let packed = pack_index(&blocks);
        assert_eq!(packed, vec![3, -2, 9, 1, -1]);
        assert_eq!(unpack_index(&packed), blocks);
        assert!(pack_index(&[]).is_empty());
    }

    #[test]
    fn header_round_trips() {
        let mut h = Header::new(4096);
        h.infos.push(Info {
            name: "table.f0".into(),
            fsize: 5000,
            nested: false,
            blocks: vec![1, 2],
        });
        h.nr_block = 3;
        h.counter = 2;
        let bytes = h.serialise();
        let mut block = bytes.clone();
        block.resize(4096, 0);
        let whole = Header::read(&block, |_| err("no continuation")).unwrap();
        assert_eq!(Header::parse(&whole).unwrap(), h);
    }

    #[test]
    fn long_headers_continue_in_two_sets() {
        let mut h = Header::new(128);
        for k in 0..6 {
            h.infos.push(Info {
                name: format!("table.f{k}"),
                fsize: 0,
                nested: false,
                blocks: vec![],
            });
        }
        let mut disk = std::collections::BTreeMap::new();
        for _ in 0..3 {
            for (b, bytes) in h.write() {
                disk.insert(b, bytes);
            }
            let whole = Header::read(&disk[&0], |b| Ok(disk[&b].clone())).unwrap();
            let again = Header::parse(&whole).unwrap();
            assert_eq!(again.serialise(), whole);
            assert_eq!(again.cont_inx, h.cont_inx);
        }
        assert!(!h.cont[0].is_empty() && !h.cont[1].is_empty());
    }

    #[test]
    fn freed_blocks_are_reused_from_the_lowest() {
        let mut h = Header::new(16);
        let a = h.add_file("a");
        h.extend(a, 3);
        let b = h.add_file("b");
        h.extend(b, 2);
        assert_eq!(h.infos[a].blocks, vec![1, 2, 3]);
        h.truncate_blocks(a, 0);
        assert_eq!(h.free, vec![3, 2, 1]);
        h.extend(b, 4);
        assert_eq!(h.infos[b].blocks, vec![4, 5, 1, 2]);
        // Blocks freed at the end shrink the container.
        assert_eq!(h.truncate_blocks(b, 0), Some(16));
        assert!(h.free.is_empty() && h.nr_block == 1);
    }
}
