// SPDX-License-Identifier: GPL-3.0-or-later
//! Temporary files for gemclean's `-reorder` (research/gemclean-memory2.md,
//! issue #32): data written once and read back where it is used, as
//! WSClean's reordered visibility files. Values come back with the bits they
//! were written with (little-endian raw bytes), so nothing computed from
//! them changes. A file is removed when its last handle is dropped, also on
//! an error return or a panic that unwinds.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

use crate::clean_certified::Complex;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Bytes moved per read or write call.
const BLOCK: usize = 1 << 22;

/// An append-only temporary file, read back at recorded offsets.
pub struct TempFile {
    path: PathBuf,
    file: Mutex<Option<File>>,
    written: Mutex<u64>,
}

impl TempFile {
    /// Create (truncate) `path`.
    pub fn create(path: PathBuf) -> Result<TempFile, String> {
        let file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(&path)
            .map_err(|e| format!("{}: {e}", path.display()))?;
        Ok(TempFile {
            path,
            file: Mutex::new(Some(file)),
            written: Mutex::new(0),
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Bytes written so far.
    pub fn len(&self) -> u64 {
        *self.written.lock().expect("no panic while writing")
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    fn err(&self, e: std::io::Error) -> String {
        format!("{}: {e}", self.path.display())
    }

    /// Append `bytes(i)` for every block of `n` values of `size` bytes, and
    /// return the offset of the first.
    fn append_with(
        &self,
        n: usize,
        size: usize,
        mut fill: impl FnMut(usize, usize, &mut Vec<u8>),
    ) -> Result<u64, String> {
        let mut guard = self.file.lock().expect("no panic while writing");
        let file = guard.as_mut().ok_or("the temporary file is closed")?;
        let mut written = self.written.lock().expect("no panic while writing");
        let offset = *written;
        file.seek(SeekFrom::Start(offset))
            .map_err(|e| self.err(e))?;
        let per = (BLOCK / size).max(1);
        let mut buf = Vec::with_capacity(per * size);
        let mut start = 0;
        while start < n {
            let end = (start + per).min(n);
            buf.clear();
            fill(start, end, &mut buf);
            file.write_all(&buf).map_err(|e| self.err(e))?;
            start = end;
        }
        *written = offset + (n * size) as u64;
        Ok(offset)
    }

    /// Read `n` values of `size` bytes at `offset`, block by block.
    fn read_with(
        &self,
        offset: u64,
        n: usize,
        size: usize,
        mut take: impl FnMut(&[u8]),
    ) -> Result<(), String> {
        let mut guard = self.file.lock().expect("no panic while reading");
        let file = guard.as_mut().ok_or("the temporary file is closed")?;
        file.seek(SeekFrom::Start(offset))
            .map_err(|e| self.err(e))?;
        let per = (BLOCK / size).max(1);
        let mut buf = vec![0u8; per * size];
        let mut left = n;
        while left > 0 {
            let k = left.min(per);
            file.read_exact(&mut buf[..k * size])
                .map_err(|e| self.err(e))?;
            take(&buf[..k * size]);
            left -= k;
        }
        Ok(())
    }

    /// Append single-precision complex values; their offset.
    pub fn append_c32(&self, v: &[Complex<f32>]) -> Result<u64, String> {
        self.append_with(v.len(), 8, |a, b, buf| {
            for x in &v[a..b] {
                buf.extend_from_slice(&x.re.to_le_bytes());
                buf.extend_from_slice(&x.im.to_le_bytes());
            }
        })
    }

    /// Read `n` values written by [`TempFile::append_c32`] at `offset`.
    pub fn read_c32(&self, offset: u64, n: usize) -> Result<Vec<Complex<f32>>, String> {
        let mut out = Vec::with_capacity(n);
        self.read_with(offset, n, 8, |b| {
            for c in b.chunks_exact(8) {
                out.push(Complex::new(
                    f32::from_le_bytes(c[..4].try_into().expect("4 bytes")),
                    f32::from_le_bytes(c[4..].try_into().expect("4 bytes")),
                ));
            }
        })?;
        Ok(out)
    }

    /// Append `f32` values; their offset.
    pub fn append_f32(&self, v: &[f32]) -> Result<u64, String> {
        self.append_with(v.len(), 4, |a, b, buf| {
            for x in &v[a..b] {
                buf.extend_from_slice(&x.to_le_bytes());
            }
        })
    }

    /// Read `n` values written by [`TempFile::append_f32`] at `offset`.
    pub fn read_f32(&self, offset: u64, n: usize) -> Result<Vec<f32>, String> {
        let mut out = Vec::with_capacity(n);
        self.read_with(offset, n, 4, |b| {
            for c in b.chunks_exact(4) {
                out.push(f32::from_le_bytes(c.try_into().expect("4 bytes")));
            }
        })?;
        Ok(out)
    }
}

impl Drop for TempFile {
    fn drop(&mut self) {
        // Closed before it is removed: Windows does not remove an open file.
        if let Ok(f) = self.file.get_mut() {
            drop(f.take());
        }
        let _ = std::fs::remove_file(&self.path);
    }
}

/// The path of a temporary file `<dir>/<stem of name>-<what>-<pid>.tmp`:
/// `dir` is `-temp-dir`, else the directory of `-name`.
pub fn temp_path(temp_dir: Option<&Path>, name: &str, what: &str) -> PathBuf {
    let name = Path::new(name);
    let stem = name
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "gemclean".into());
    let dir = match temp_dir {
        Some(d) => d.to_path_buf(),
        None => name
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .map(Path::to_path_buf)
            .unwrap_or_else(|| PathBuf::from(".")),
    };
    dir.join(format!("{stem}-{what}-{}.tmp", std::process::id()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn values_come_back_bit_for_bit_and_the_file_goes() {
        let dir = std::env::temp_dir();
        let path = temp_path(Some(&dir), "scratch-test", "t");
        let f = TempFile::create(path.clone()).unwrap();
        let a: Vec<Complex<f32>> = (0..300_000)
            .map(|i| Complex::new(i as f32 * 1.5e-3, -(i as f32).sqrt()))
            .chain([
                Complex::new(f32::NAN, -0.0),
                Complex::new(f32::MIN_POSITIVE / 2.0, 1e38),
            ])
            .collect();
        let b: Vec<f32> = (0..1_100_000).map(|i| (i as f32).sin()).collect();
        let oa = f.append_c32(&a).unwrap();
        let ob = f.append_f32(&b).unwrap();
        assert_eq!(oa, 0);
        assert_eq!(ob, 8 * a.len() as u64);
        let a2 = f.read_c32(oa, a.len()).unwrap();
        let b2 = f.read_f32(ob, b.len()).unwrap();
        let bits = |v: &[Complex<f32>]| -> Vec<(u32, u32)> {
            v.iter().map(|c| (c.re.to_bits(), c.im.to_bits())).collect()
        };
        assert_eq!(bits(&a), bits(&a2));
        assert!(b.iter().zip(&b2).all(|(x, y)| x.to_bits() == y.to_bits()));
        assert!(path.exists());
        drop(f);
        assert!(!path.exists());
    }
}
