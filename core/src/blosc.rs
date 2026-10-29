//! Blosc-1 chunk decoding for zarr ingest (research/core-section6.md).
//!
//! Supports what the public MeerKAT zarr stores use: format version 2,
//! LZ4-compressed blocks, optional byte shuffle and split streams, and
//! memcpyed chunks. The split rule, raw-stream rule and unshuffle follow
//! `blosc_d` in c-blosc 1.21.6. Bit shuffle and other codecs are refused.
//! Rows can be decoded selectively: only blocks that contain requested rows
//! are expanded, so a large chunk is never decoded in full.

const DOSHUFFLE: u8 = 0x01;
const MEMCPYED: u8 = 0x02;
const DOBITSHUFFLE: u8 = 0x04;
const DONT_SPLIT: u8 = 0x10;
const LZ4_FORMAT: u8 = 1;
const MIN_BUFFERSIZE: usize = 128;
const MAX_SPLITS: usize = 16;
const HEADER: usize = 16;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Header {
    pub flags: u8,
    pub typesize: usize,
    pub nbytes: usize,
    pub blocksize: usize,
    pub cbytes: usize,
}

impl Header {
    pub fn nblocks(&self) -> usize {
        self.nbytes.div_ceil(self.blocksize.max(1))
    }
}

fn u32_at(src: &[u8], offset: usize) -> Result<usize, &'static str> {
    let bytes = src.get(offset..offset + 4).ok_or("truncated chunk")?;
    Ok(u32::from_le_bytes(bytes.try_into().unwrap()) as usize)
}

/// Full-chunk header check, including the total compressed length.
pub fn header(src: &[u8]) -> Result<Header, &'static str> {
    let h = parse_header(src)?;
    if h.cbytes != src.len() {
        return Err("blosc compressed size disagrees with chunk length");
    }
    Ok(h)
}

/// Header check from the first bytes only (no total-length check).
pub fn parse_header(src: &[u8]) -> Result<Header, &'static str> {
    if src.len() < HEADER {
        return Err("truncated blosc header");
    }
    let flags = src[2];
    let h = Header {
        flags,
        typesize: src[3] as usize,
        nbytes: u32_at(src, 4)?,
        blocksize: u32_at(src, 8)?,
        cbytes: u32_at(src, 12)?,
    };
    if src[0] != 2 && src[0] != 1 {
        return Err("unsupported blosc format version");
    }
    if h.typesize == 0 || (h.nbytes > 0 && h.blocksize == 0) {
        return Err("invalid blosc typesize or blocksize");
    }
    if flags & 0x08 != 0 || flags & DOBITSHUFFLE != 0 {
        return Err("bit shuffle or unknown blosc flags are not supported");
    }
    if flags & MEMCPYED == 0 && (flags & 0xe0) >> 5 != LZ4_FORMAT {
        return Err("only LZ4-compressed blosc chunks are supported");
    }
    Ok(h)
}

/// Decompress one LZ4 block into exactly `out.len()` bytes.
pub fn lz4_decompress(src: &[u8], out: &mut [u8]) -> Result<(), &'static str> {
    let (mut s, mut d) = (0usize, 0usize);
    let read_length = |s: &mut usize, mut length: usize| -> Result<usize, &'static str> {
        if length == 15 {
            loop {
                let byte = *src.get(*s).ok_or("truncated LZ4 length")?;
                *s += 1;
                length += byte as usize;
                if byte != 255 {
                    break;
                }
            }
        }
        Ok(length)
    };
    loop {
        let token = *src.get(s).ok_or("truncated LZ4 token")?;
        s += 1;
        let literals = read_length(&mut s, (token >> 4) as usize)?;
        let end = s.checked_add(literals).ok_or("LZ4 overflow")?;
        let target = d.checked_add(literals).ok_or("LZ4 overflow")?;
        if end > src.len() || target > out.len() {
            return Err("LZ4 literals out of range");
        }
        out[d..target].copy_from_slice(&src[s..end]);
        s = end;
        d = target;
        if s == src.len() {
            break;
        }
        let offset = src
            .get(s..s + 2)
            .map(|b| u16::from_le_bytes([b[0], b[1]]) as usize)
            .ok_or("truncated LZ4 offset")?;
        s += 2;
        if offset == 0 || offset > d {
            return Err("invalid LZ4 match offset");
        }
        let length = read_length(&mut s, (token & 15) as usize)? + 4;
        if d + length > out.len() {
            return Err("LZ4 match out of range");
        }
        // A match may overlap its own output: copy in runs of at most
        // `offset` bytes, each of which reads only already-written bytes.
        let mut copied = 0;
        while copied < length {
            let run = (length - copied).min(offset + copied);
            let from = d - offset;
            out.copy_within(from..from + run, d + copied);
            copied += run;
        }
        d += length;
    }
    if d != out.len() {
        return Err("LZ4 block decoded to the wrong size");
    }
    Ok(())
}

fn unshuffle(typesize: usize, src: &[u8], dest: &mut [u8]) {
    let quot = src.len() / typesize;
    let tail = quot * typesize;
    // Write sequentially, reading the `typesize` byte streams in step.
    let streams: Vec<&[u8]> = (0..typesize)
        .map(|j| &src[j * quot..(j + 1) * quot])
        .collect();
    for (i, element) in dest[..tail].chunks_exact_mut(typesize).enumerate() {
        for (byte, stream) in element.iter_mut().zip(&streams) {
            *byte = stream[i];
        }
    }
    dest[tail..].copy_from_slice(&src[tail..]);
}

/// Byte range of block `j` within the chunk: from its start offset to the
/// next block's start (or the end of the chunk). Lets a caller read only the
/// blocks it needs from a file or an HTTP range request.
pub fn block_span(src_head: &[u8], h: &Header, j: usize) -> Result<(usize, usize), &'static str> {
    let nblocks = h.nblocks();
    if j >= nblocks {
        return Err("block index out of range");
    }
    if h.flags & MEMCPYED != 0 {
        let start = HEADER + j * h.blocksize;
        return Ok((start, (start + h.blocksize).min(HEADER + h.nbytes)));
    }
    let start = u32_at(src_head, HEADER + 4 * j)?;
    let end = if j + 1 < nblocks {
        u32_at(src_head, HEADER + 4 * (j + 1))?
    } else {
        h.cbytes
    };
    if end < start {
        return Err("blosc block offsets are not ascending");
    }
    Ok((start, end))
}

/// Decode block `j` from its own compressed bytes `block` (as returned by
/// `block_span`) into `dest`, the block's decoded length.
pub fn decode_block_bytes(
    h: &Header,
    j: usize,
    block: &[u8],
    dest: &mut [u8],
    scratch: &mut Vec<u8>,
) -> Result<(), &'static str> {
    let nblocks = h.nblocks();
    let leftover = h.nbytes % h.blocksize;
    let last = j + 1 == nblocks && leftover > 0;
    let bsize = if last { leftover } else { h.blocksize };
    if dest.len() != bsize {
        return Err("block destination has the wrong size");
    }
    if h.flags & MEMCPYED != 0 {
        dest.copy_from_slice(block.get(..bsize).ok_or("truncated memcpyed block")?);
        return Ok(());
    }
    let shuffled = h.flags & DOSHUFFLE != 0 && h.typesize > 1;
    let dont_split = h.flags & DONT_SPLIT != 0;
    let nsplits =
        if !dont_split && h.typesize <= MAX_SPLITS && bsize / h.typesize >= MIN_BUFFERSIZE && !last
        {
            h.typesize
        } else {
            1
        };
    let neblock = bsize / nsplits;
    let mut offset = 0;
    scratch.resize(bsize, 0);
    let target: &mut [u8] = if shuffled { scratch } else { dest };
    for k in 0..nsplits {
        let cbytes = u32_at(block, offset)?;
        offset += 4;
        let stream = block
            .get(offset..offset + cbytes)
            .ok_or("truncated blosc stream")?;
        let out = &mut target[k * neblock..(k + 1) * neblock];
        if cbytes == neblock {
            out.copy_from_slice(stream);
        } else {
            lz4_decompress(stream, out)?;
        }
        offset += cbytes;
    }
    if shuffled {
        unshuffle(h.typesize, scratch, dest);
    }
    Ok(())
}

/// Decode block `j` of a complete chunk into `dest`.
pub fn decode_block(
    src: &[u8],
    h: &Header,
    j: usize,
    dest: &mut [u8],
    scratch: &mut Vec<u8>,
) -> Result<(), &'static str> {
    if h.flags & MEMCPYED == 0 && h.nblocks() > (src.len() - HEADER) / 4 {
        return Err("blosc block table out of range");
    }
    let (start, end) = block_span(src, h, j)?;
    let block = src.get(start..end).ok_or("truncated blosc block")?;
    decode_block_bytes(h, j, block, dest, scratch)
}

/// Decode the consecutive blocks `first..first + nblocks_in_span` from their
/// compressed bytes `span` (which starts at block `first`'s offset, given as
/// `span_start`), and copy rows `rows` (ascending, each lying entirely inside
/// those blocks) into `out` at `row_bytes` per row.
#[allow(clippy::too_many_arguments)]
pub fn decode_span_rows(
    head: &[u8],
    h: &Header,
    first: usize,
    count: usize,
    span: &[u8],
    span_start: usize,
    row_bytes: usize,
    rows: &[usize],
    out: &mut [u8],
) -> Result<(), &'static str> {
    if out.len() != rows.len() * row_bytes {
        return Err("row selection buffer mismatch");
    }
    let mut block = Vec::new();
    let mut scratch = Vec::new();
    let mut next = 0usize;
    for j in first..first + count {
        let (start, end) = block_span(head, h, j)?;
        let bytes = span
            .get(start - span_start..end - span_start)
            .ok_or("block outside the span")?;
        let block_lo = j * h.blocksize;
        let bsize = h.blocksize.min(h.nbytes - block_lo);
        block.resize(bsize, 0);
        decode_block_bytes(h, j, bytes, &mut block, &mut scratch)?;
        let block_hi = block_lo + bsize;
        // Copy the parts of every row that overlap this block.
        while next < rows.len() && (rows[next] + 1) * row_bytes <= block_lo {
            next += 1;
        }
        let mut i = next;
        while i < rows.len() && rows[i] * row_bytes < block_hi {
            let lo = (rows[i] * row_bytes).max(block_lo);
            let hi = ((rows[i] + 1) * row_bytes).min(block_hi);
            let dest = i * row_bytes + (lo - rows[i] * row_bytes);
            out[dest..dest + hi - lo].copy_from_slice(&block[lo - block_lo..hi - block_lo]);
            i += 1;
        }
    }
    Ok(())
}

/// Decode a whole chunk into `out`, which must have its decoded length.
pub fn decode_into(src: &[u8], out: &mut [u8]) -> Result<(), &'static str> {
    let h = header(src)?;
    if out.len() != h.nbytes {
        return Err("output buffer has the wrong size");
    }
    let mut scratch = Vec::new();
    for j in 0..h.nblocks() {
        let start = j * h.blocksize;
        let end = (start + h.blocksize).min(h.nbytes);
        decode_block(src, &h, j, &mut out[start..end], &mut scratch)?;
    }
    Ok(())
}

/// Decode a whole chunk.
pub fn decode(src: &[u8]) -> Result<Vec<u8>, &'static str> {
    let mut out = vec![0u8; header(src)?.nbytes];
    decode_into(src, &mut out)?;
    Ok(out)
}

/// Decode only the rows `rows` (ascending, unique) of a chunk whose decoded
/// layout is row-major with `row_bytes` bytes per row, into `out`
/// (`rows.len() * row_bytes`). Returns the number of blocks decoded.
pub fn decode_rows(
    src: &[u8],
    row_bytes: usize,
    rows: &[usize],
    out: &mut [u8],
) -> Result<usize, &'static str> {
    let h = header(src)?;
    if row_bytes == 0 || out.len() != rows.len() * row_bytes {
        return Err("row selection buffer mismatch");
    }
    if rows.windows(2).any(|w| w[1] <= w[0]) {
        return Err("rows must be ascending and unique");
    }
    if rows.last().is_some_and(|&r| (r + 1) * row_bytes > h.nbytes) {
        return Err("row beyond the chunk");
    }
    let mut block = Vec::new();
    let mut scratch = Vec::new();
    let mut current = usize::MAX;
    let mut decoded = 0;
    for (i, &row) in rows.iter().enumerate() {
        let (mut from, to) = (row * row_bytes, (row + 1) * row_bytes);
        let mut written = i * row_bytes;
        while from < to {
            let j = from / h.blocksize;
            if j != current {
                let start = j * h.blocksize;
                let end = (start + h.blocksize).min(h.nbytes);
                block.resize(end - start, 0);
                decode_block(src, &h, j, &mut block, &mut scratch)?;
                current = j;
                decoded += 1;
            }
            let start = j * h.blocksize;
            let stop = to.min(start + block.len());
            let n = stop - from;
            out[written..written + n].copy_from_slice(&block[from - start..stop - start]);
            written += n;
            from = stop;
        }
    }
    Ok(decoded)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lz4_literals_and_overlapping_match() {
        // "abc" then a match of offset 3, length 9 -> "abcabcabcabc"
        // token: 3 literals, match length 9-4=5.
        let src = [0x35, b'a', b'b', b'c', 3, 0, 0x00];
        // The final sequence must be literals only: token 0x00 with zero literals.
        let mut out = vec![0u8; 12];
        lz4_decompress(&src, &mut out).unwrap();
        assert_eq!(&out, b"abcabcabcabc");
    }

    #[test]
    fn memcpyed_unshuffled_chunk_round_trip() {
        let payload: Vec<u8> = (0..40u8).collect();
        let mut src = vec![2u8, 1, MEMCPYED, 4];
        src.extend((40u32).to_le_bytes());
        src.extend((40u32).to_le_bytes());
        src.extend(((HEADER + 40) as u32).to_le_bytes());
        src.extend(&payload);
        assert_eq!(decode(&src).unwrap(), payload);
        let mut rows = vec![0u8; 8];
        decode_rows(&src, 4, &[2, 7], &mut rows).unwrap();
        assert_eq!(rows, [8, 9, 10, 11, 28, 29, 30, 31]);
    }

    #[test]
    fn unshuffle_restores_element_order() {
        let shuffled = [1u8, 3, 5, 2, 4, 6, 9];
        let mut out = [0u8; 7];
        unshuffle(2, &shuffled, &mut out);
        assert_eq!(out, [1, 2, 3, 4, 5, 6, 9]);
    }

    #[test]
    fn refuses_other_codecs() {
        let mut src = vec![2u8, 1, (3 << 5) | DOSHUFFLE, 4];
        src.extend((4u32).to_le_bytes());
        src.extend((4u32).to_le_bytes());
        src.extend(((HEADER) as u32).to_le_bytes());
        assert!(header(&src).is_err());
    }
}
