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
        if literals <= WILD && end + WILD <= src.len() && target + WILD <= out.len() {
            // Short literal run with slack on both sides: one 16-byte copy.
            // The bytes past `target` are rewritten by the sequences that
            // follow, which never read at or beyond the write cursor.
            out[d..d + WILD].copy_from_slice(&src[s..s + WILD]);
        } else {
            out[d..target].copy_from_slice(&src[s..end]);
        }
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
        if offset >= WILD && d + length + WILD <= out.len() {
            // Non-overlapping 16-byte steps: every step reads bytes that lie
            // at least `offset` >= 16 behind the write cursor.
            let mut copied = 0;
            while copied < length {
                let from = d - offset + copied;
                let block: [u8; WILD] = out[from..from + WILD].try_into().unwrap();
                out[d + copied..d + copied + WILD].copy_from_slice(&block);
                copied += WILD;
            }
        } else if length <= 2 * WILD {
            for i in d..d + length {
                out[i] = out[i - offset];
            }
        } else if offset < WILD && d + length + WILD <= out.len() {
            // Short offset: the match is periodic with period `offset`, so
            // write 16-byte windows of a 32-byte pattern, each starting at
            // the phase of its position.
            let from = d - offset;
            let pattern: [u8; 2 * WILD] = std::array::from_fn(|i| out[from + i % offset]);
            let mut copied = 0;
            while copied < length {
                let phase = copied % offset;
                out[d + copied..d + copied + WILD].copy_from_slice(&pattern[phase..phase + WILD]);
                copied += WILD;
            }
        } else {
            // A match may overlap its own output: copy in runs of at most
            // `offset` bytes, each of which reads only already-written bytes.
            let mut copied = 0;
            while copied < length {
                let run = (length - copied).min(offset + copied);
                let from = d - offset;
                out.copy_within(from..from + run, d + copied);
                copied += run;
            }
        }
        d += length;
    }
    if d != out.len() {
        return Err("LZ4 block decoded to the wrong size");
    }
    Ok(())
}

/// Width of the speculative copies in `lz4_decompress`.
const WILD: usize = 16;

/// Byte-wise unshuffle of elements `first..quot` of the `typesize` streams.
fn unshuffle_scalar(typesize: usize, quot: usize, first: usize, src: &[u8], dest: &mut [u8]) {
    for i in first..quot {
        for j in 0..typesize {
            dest[i * typesize + j] = src[j * quot + i];
        }
    }
}

/// Reverse c-blosc's byte shuffle: stream `j` holds byte `j` of every element.
fn unshuffle(typesize: usize, src: &[u8], dest: &mut [u8]) {
    let quot = src.len() / typesize;
    let tail = quot * typesize;
    let done = unshuffle_simd(typesize, quot, src, dest);
    unshuffle_scalar(typesize, quot, done, src, dest);
    dest[tail..].copy_from_slice(&src[tail..]);
}

/// Unshuffle as many whole groups of 16 elements as possible with SSE2 for
/// typesizes 2, 4, 8 and 16 (what the MeerKAT stores use) and return the
/// number of elements done. The byte transposition follows c-blosc's
/// `shuffle-sse2.c`: `log2(typesize)` rounds of `unpacklo`/`unpackhi` at
/// doubling widths, with the registers read out in bit-reversed order.
#[cfg(target_arch = "x86_64")]
fn unshuffle_simd(typesize: usize, quot: usize, src: &[u8], dest: &mut [u8]) -> usize {
    match typesize {
        2 => unshuffle_sse2::<2, 1>(quot, src, dest),
        4 => unshuffle_sse2::<4, 2>(quot, src, dest),
        8 => unshuffle_sse2::<8, 3>(quot, src, dest),
        16 => unshuffle_sse2::<16, 4>(quot, src, dest),
        _ => 0,
    }
}

#[cfg(not(target_arch = "x86_64"))]
fn unshuffle_simd(_typesize: usize, _quot: usize, _src: &[u8], _dest: &mut [u8]) -> usize {
    0
}

#[cfg(target_arch = "x86_64")]
fn unshuffle_sse2<const T: usize, const ROUNDS: usize>(
    quot: usize,
    src: &[u8],
    dest: &mut [u8],
) -> usize {
    use std::arch::x86_64::{
        __m128i, _mm_loadu_si128, _mm_storeu_si128, _mm_unpackhi_epi8, _mm_unpackhi_epi16,
        _mm_unpackhi_epi32, _mm_unpackhi_epi64, _mm_unpacklo_epi8, _mm_unpacklo_epi16,
        _mm_unpacklo_epi32, _mm_unpacklo_epi64,
    };
    let groups = quot / 16;
    if groups == 0 {
        return 0;
    }
    assert!(src.len() >= T * quot && dest.len() >= T * quot);
    let order: [usize; T] = std::array::from_fn(|k| {
        // Bit reversal of `k` over ROUNDS bits.
        (0..ROUNDS).fold(0, |acc, bit| acc | (((k >> bit) & 1) << (ROUNDS - 1 - bit)))
    });
    for g in 0..groups {
        let i = g * 16;
        // SAFETY: SSE2 is part of the x86_64 baseline; every load reads 16
        // bytes at `j * quot + i` with `i + 16 <= quot`, and every store
        // writes 16 bytes at `i * T + 16 * m` with `m < T`, both inside the
        // slices by the assertion above.
        unsafe {
            let mut regs: [__m128i; T] = std::array::from_fn(|j| {
                _mm_loadu_si128(src.as_ptr().add(j * quot + i) as *const __m128i)
            });
            for round in 0..ROUNDS {
                let mut next = regs;
                for k in 0..T / 2 {
                    let (a, b) = (regs[2 * k], regs[2 * k + 1]);
                    let (lo, hi) = match round {
                        0 => (_mm_unpacklo_epi8(a, b), _mm_unpackhi_epi8(a, b)),
                        1 => (_mm_unpacklo_epi16(a, b), _mm_unpackhi_epi16(a, b)),
                        2 => (_mm_unpacklo_epi32(a, b), _mm_unpackhi_epi32(a, b)),
                        _ => (_mm_unpacklo_epi64(a, b), _mm_unpackhi_epi64(a, b)),
                    };
                    next[k] = lo;
                    next[k + T / 2] = hi;
                }
                regs = next;
            }
            let base = dest.as_mut_ptr().add(i * T);
            for (m, &r) in order.iter().enumerate() {
                _mm_storeu_si128(base.add(16 * m) as *mut __m128i, regs[r]);
            }
        }
    }
    groups * 16
}

/// Byte range of block `j` within the chunk: from its start offset to the
/// nearest larger block start (or the end of the chunk). Lets a caller read
/// only the blocks it needs from a file or an HTTP range request. Blocks
/// need not be stored in order: multithreaded blosc writes them as they
/// finish (QuartiCal's dask-ms stores have such chunks; research/dfio-formats.md).
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
    let mut end = h.cbytes;
    for k in 0..nblocks {
        let other = u32_at(src_head, HEADER + 4 * k)?;
        if other > start && other < end {
            end = other;
        }
    }
    if end < start {
        return Err("blosc block offset beyond the chunk");
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
    fn blocks_stored_out_of_order_decode() {
        // Two raw blocks of 8 bytes, typesize 1, the second stored first,
        // as a multithreaded compressor may write them.
        let a: Vec<u8> = (0..8u8).collect();
        let b: Vec<u8> = (100..108u8).collect();
        let second = HEADER + 8;
        let first = second + 4 + 8;
        let mut src = vec![2u8, 1, 0x20, 1];
        src.extend((16u32).to_le_bytes());
        src.extend((8u32).to_le_bytes());
        src.extend(((first + 4 + 8) as u32).to_le_bytes());
        src.extend((first as u32).to_le_bytes());
        src.extend((second as u32).to_le_bytes());
        src.extend((8u32).to_le_bytes());
        src.extend(&b);
        src.extend((8u32).to_le_bytes());
        src.extend(&a);
        let mut want = a.clone();
        want.extend(&b);
        assert_eq!(decode(&src).unwrap(), want);
    }

    #[test]
    fn unshuffle_restores_element_order() {
        let shuffled = [1u8, 3, 5, 2, 4, 6, 9];
        let mut out = [0u8; 7];
        unshuffle(2, &shuffled, &mut out);
        assert_eq!(out, [1, 2, 3, 4, 5, 6, 9]);
    }

    fn pseudo_random(n: usize, seed: u64) -> Vec<u8> {
        let mut state = seed;
        (0..n)
            .map(|_| {
                state = state
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add(1442695040888963407);
                (state >> 56) as u8
            })
            .collect()
    }

    #[test]
    fn simd_unshuffle_equals_the_scalar_reference() {
        for typesize in 1..=17 {
            for elements in [0usize, 1, 15, 16, 17, 31, 32, 33, 100, 257] {
                for leftover in [0usize, 1, 3] {
                    let n = elements * typesize + leftover;
                    let shuffled = pseudo_random(n, (typesize * 1000 + n) as u64);
                    let mut expected = vec![0u8; n];
                    let quot = n / typesize;
                    unshuffle_scalar(typesize, quot, 0, &shuffled, &mut expected);
                    expected[quot * typesize..].copy_from_slice(&shuffled[quot * typesize..]);
                    let mut out = vec![0u8; n];
                    unshuffle(typesize, &shuffled, &mut out);
                    assert_eq!(out, expected, "typesize {typesize}, {n} bytes");
                }
            }
        }
    }

    /// Greedy reference LZ4 block encoder for round trips (brute-force match
    /// search; fine for test sizes).
    fn lz4_encode(input: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        let mut literal_start = 0;
        let mut i = 0;
        let write_length = |out: &mut Vec<u8>, mut n: usize| {
            while n >= 255 {
                out.push(255);
                n -= 255;
            }
            out.push(n as u8);
        };
        let emit = |out: &mut Vec<u8>, literals: &[u8], m: Option<(usize, usize)>| {
            let lit_token = literals.len().min(15) as u8;
            let match_token = m.map_or(0, |(_, length)| (length - 4).min(15) as u8);
            out.push((lit_token << 4) | match_token);
            if literals.len() >= 15 {
                write_length(out, literals.len() - 15);
            }
            out.extend_from_slice(literals);
            if let Some((offset, length)) = m {
                out.extend((offset as u16).to_le_bytes());
                if length - 4 >= 15 {
                    write_length(out, length - 4 - 15);
                }
            }
        };
        while i + 4 < input.len() {
            let mut best = (0usize, 0usize);
            let window = i.saturating_sub(65535);
            for start in window..i {
                let mut length = 0;
                while i + length < input.len() && input[start + length] == input[i + length] {
                    length += 1;
                }
                if length >= 4 && length > best.1 {
                    best = (i - start, length);
                }
            }
            if best.1 >= 4 {
                emit(&mut out, &input[literal_start..i], Some(best));
                i += best.1;
                literal_start = i;
            } else {
                i += 1;
            }
        }
        emit(&mut out, &input[literal_start..], None);
        out
    }

    #[test]
    fn lz4_round_trips_runs_patterns_and_long_matches() {
        let mut cases: Vec<Vec<u8>> = Vec::new();
        cases.push(vec![7u8; 100]); // offset-1 run
        cases.push((0..300).map(|i| (i % 4) as u8).collect()); // offset 4
        cases.push((0..300).map(|i| (i % 8) as u8 * 3).collect()); // offset 8
        let mut long = pseudo_random(64, 1);
        long.extend_from_slice(&long.clone()); // offset 64, length 64
        long.extend_from_within(..40);
        cases.push(long);
        let mut mixed = pseudo_random(200, 2);
        mixed.extend(vec![0u8; 50]);
        mixed.extend_from_within(10..60);
        mixed.extend(pseudo_random(20, 3));
        cases.push(mixed);
        // Matches that end exactly at the output end, with and without slack.
        let mut tight = pseudo_random(30, 4);
        tight.extend_from_within(..17);
        cases.push(tight);
        cases.push(pseudo_random(5, 5));
        for case in cases {
            let encoded = lz4_encode(&case);
            let mut out = vec![0u8; case.len()];
            lz4_decompress(&encoded, &mut out).unwrap();
            assert_eq!(out, case);
        }
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
