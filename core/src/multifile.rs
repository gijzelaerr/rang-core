//! MultiFile tables (research/e5-table-writer-rest.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! casacore's `MultiFile` container (version 2, as casacore 3.8.1 writes
//! it): block 0 holds the header (the change counter, block size and count,
//! then an AipsIO `MultiFile` object with every logical file's name, size
//! and nesting flag, then each file's packed block list, the free list, the
//! CRC list and the header-continuation lists, all canonical big-endian);
//! every other block belongs to one logical file. A logical file gets its
//! blocks when it is first written (`MultiFileBase::write` extends it,
//! taking free blocks first); bytes of a block past the file's end are
//! zero. The table writer keeps the logical files in a staging directory
//! inside the table while it is open and packs them into `table.mf` on
//! every flush, giving new files their blocks in the order casacore first
//! writes them. The format was read in the casacore sources; nothing is
//! copied from casacore (LGPL-2.1-or-later).

use std::fs::{File, OpenOptions};
use std::path::{Path, PathBuf};

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

/// One logical file (`MultiFileInfo`).
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
        }
    }

    /// `MultiFile::readHeader` (version 2, the header in block 0).
    pub fn parse(b: &[u8]) -> Result<Self> {
        if be64(b, 0)? != 0 {
            return err("MultiFile header version 1 is not read");
        }
        let first_cont = be64(b, 8)?;
        let counter = be64(b, 16)?;
        let version = be32(b, 24)?;
        if version != 2 {
            return err(format!("MultiFile version {version} is not read"));
        }
        let size = be64(b, 32)? as usize;
        let block_size = be64(b, 40)?;
        let nr_block = be64(b, 48)?;
        let use_crc = b.get(56).copied().unwrap_or(0) != 0;
        if size > block_size as usize || first_cont != 0 {
            return err("MultiFile headers with continuation blocks are not read (E6)");
        }
        let h = b
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
        let vector = |at: &mut usize| -> Result<Vec<i64>> {
            let n = be64(h, *at)? as usize;
            *at += 8;
            let v = (0..n)
                .map(|i| be64(h, *at + 8 * i))
                .collect::<Result<Vec<_>>>()?;
            *at += 8 * n;
            Ok(v)
        };
        for info in &mut infos {
            info.blocks = unpack_index(&vector(&mut at)?);
        }
        let free = unpack_index(&vector(&mut at)?);
        let ncrc = be64(h, at)? as usize;
        at += 8;
        let crc = (0..ncrc)
            .map(|i| be32(h, at + 4 * i))
            .collect::<Result<Vec<_>>>()?;
        at += 4 * ncrc;
        let cont0 = vector(&mut at)?;
        let cont1 = vector(&mut at)?;
        let ncont_used = [be32(h, at)?, be32(h, at + 4)?];
        at += 8;
        if at != size {
            return err("MultiFile header length mismatches its contents");
        }
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
        })
    }

    /// `MultiFile::writeHeader` without continuation blocks: the header
    /// bytes (the rest of block 0 is not part of them).
    pub fn serialise(&self) -> Result<Vec<u8>> {
        let mut out = Vec::new();
        out.extend(0i64.to_be_bytes());
        out.extend(self.first_cont.to_be_bytes());
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
        let vector = |out: &mut Vec<u8>, v: &[i64]| {
            out.extend((v.len() as i64).to_be_bytes());
            for &x in v {
                out.extend(x.to_be_bytes());
            }
        };
        for info in &self.infos {
            vector(&mut out, &pack_index(&info.blocks));
        }
        vector(&mut out, &pack_index(&self.free));
        out.extend((self.crc.len() as i64).to_be_bytes());
        for &x in &self.crc {
            out.extend(x.to_be_bytes());
        }
        vector(&mut out, &self.cont[0]);
        vector(&mut out, &self.cont[1]);
        out.extend(self.ncont_used[0].to_be_bytes());
        out.extend(self.ncont_used[1].to_be_bytes());
        if out.len() as i64 > self.block_size {
            return err("MultiFile headers with continuation blocks are not written (E6)");
        }
        let n = out.len() as i64;
        out[32..40].copy_from_slice(&n.to_be_bytes());
        Ok(out)
    }

    fn info_mut(&mut self, name: &str) -> Option<&mut Info> {
        self.infos.iter_mut().find(|i| i.name == name)
    }

    /// `MultiFile::extendVF` with free blocks: give `name` blocks for
    /// `nblocks` in all.
    fn extend(&mut self, name: &str, nblocks: usize) {
        let mut take = Vec::new();
        let have = self.info_mut(name).map_or(0, |i| i.blocks.len());
        for _ in have..nblocks {
            take.push(match self.free.pop() {
                Some(b) => b,
                None => {
                    self.nr_block += 1;
                    self.nr_block - 1
                }
            });
        }
        if let Some(info) = self.info_mut(name) {
            info.blocks.extend(take);
        }
    }
}

/// Whether `table.mf` of a table parses and serialises to its header bytes
/// (read only).
pub fn check(dir: impl AsRef<Path>) -> Result<bool> {
    let bytes = std::fs::read(dir.as_ref().join(CONTAINER))?;
    let h = Header::parse(&bytes)?;
    let size = be64(&bytes, 32)? as usize;
    Ok(h.serialise()? == bytes[..size])
}

/// Write every logical file of a container into `dest` (its content up to
/// its size).
pub fn extract(container: &Path, dest: &Path) -> Result<Header> {
    let mut file =
        File::open(container).map_err(|e| MsError(format!("{}: {e}", container.display())))?;
    let head = read_at(&mut file, 0, 64)?;
    let block = be64(&head, 40)?;
    let bytes = read_at(&mut file, 0, block as usize)?;
    let h = Header::parse(&bytes)?;
    std::fs::create_dir_all(dest)?;
    for info in &h.infos {
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

/// A MultiFile container being written: its header, the staging directory
/// with the logical files, and what was packed last.
pub struct Container {
    pub path: PathBuf,
    pub staging: PathBuf,
    pub header: Header,
    /// Contents written by the last pack, by file.
    last: std::collections::BTreeMap<String, Vec<u8>>,
    /// Files whose blocks exist (casacore wrote them).
    touched: std::collections::BTreeSet<String>,
}

impl Container {
    /// A new container (`MultiFile` with `ByteIO::New`).
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
            last: Default::default(),
            touched: Default::default(),
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
        let mut last = std::collections::BTreeMap::new();
        let mut touched = std::collections::BTreeSet::new();
        for info in &header.infos {
            last.insert(info.name.clone(), std::fs::read(staging.join(&info.name))?);
            if !info.blocks.is_empty() {
                touched.insert(info.name.clone());
            }
        }
        Ok(Container {
            path,
            staging,
            header,
            last,
            touched,
        })
    }

    /// `createFile` of a logical file (its entry in the header).
    pub fn add_file(&mut self, name: &str) {
        if self.header.info_mut(name).is_none() {
            self.header.infos.push(Info {
                name: name.to_string(),
                fsize: 0,
                nested: false,
                blocks: Vec::new(),
            });
        }
    }

    fn staged_len(&self, name: &str) -> u64 {
        std::fs::metadata(self.staging.join(name)).map_or(0, |m| m.len())
    }

    /// The first write of a logical file: its blocks for its present size.
    pub fn touch(&mut self, name: &str) {
        self.add_file(name);
        if !self.touched.insert(name.to_string()) {
            return;
        }
        let len = self.staged_len(name) as i64;
        let need = (len.max(1) + self.header.block_size - 1) / self.header.block_size;
        self.header.extend(name, need as usize);
    }

    pub fn is_touched(&self, name: &str) -> bool {
        self.touched.contains(name)
    }

    /// Write the logical files into the container: blocks for files that
    /// grew, every block of a changed file (zero past its end), and the
    /// header with its change counter when anything changed.
    pub fn pack(&mut self) -> Result<()> {
        let mut changed = false;
        let mut names: Vec<String> = Vec::new();
        for entry in std::fs::read_dir(&self.staging)? {
            let n = entry?.file_name().to_string_lossy().into_owned();
            names.push(n);
        }
        names.sort();
        for n in &names {
            if self.header.info_mut(n).is_none() {
                self.touch(n);
                changed = true;
            }
        }
        let infos: Vec<String> = self.header.infos.iter().map(|i| i.name.clone()).collect();
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&self.path)
            .map_err(|e| MsError(format!("{}: {e}", self.path.display())))?;
        let bs = self.header.block_size;
        for name in infos {
            let content = std::fs::read(self.staging.join(&name)).unwrap_or_default();
            if !self.touched.contains(&name) && content.is_empty() {
                continue;
            }
            if !self.touched.contains(&name) {
                self.touch(&name);
            }
            let need = ((content.len() as i64).max(1) + bs - 1) / bs;
            let have = self.header.info_mut(&name).unwrap().blocks.len() as i64;
            if need > have {
                self.header.extend(&name, need as usize);
            }
            let info = self.header.info_mut(&name).unwrap();
            if info.fsize != content.len() as i64 {
                info.fsize = content.len() as i64;
                changed = true;
            }
            if self.last.get(&name) == Some(&content) {
                continue;
            }
            changed = true;
            let blocks = info.blocks.clone();
            for (k, &b) in blocks.iter().enumerate() {
                let from = (k as i64 * bs) as usize;
                let mut chunk = vec![0u8; bs as usize];
                if from < content.len() {
                    let n = (content.len() - from).min(bs as usize);
                    chunk[..n].copy_from_slice(&content[from..from + n]);
                }
                write_at(&mut file, (b * bs) as u64, &chunk)?;
            }
            self.last.insert(name, content);
        }
        if changed {
            self.header.counter += 1;
            let mut block0 = vec![0u8; bs as usize];
            let h = self.header.serialise()?;
            block0[..h.len()].copy_from_slice(&h);
            write_at(&mut file, 0, &block0)?;
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
        let bytes = h.serialise().unwrap();
        let mut block = bytes.clone();
        block.resize(4096, 0);
        assert_eq!(Header::parse(&block).unwrap(), h);
    }
}
