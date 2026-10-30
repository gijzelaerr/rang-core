//! Gain correction and the WSClean Stokes I reader in one pass (big plan task
//! P5, `research/p5-memory.md`).
//!
//! `correct_stokes_i` replaces `core_campaign.apply_gains` followed by
//! `core_grid.stokes_i_reader` on the campaign's final flags: per cell it
//! forms `G_p^{-1} V G_q^{-H}` in double precision from inverses the caller
//! computed (NumPy's `np.linalg.inv`, so the inverses are the ones
//! `apply_gains` uses), rounds the corrected XX and YY to complex64, and
//! writes the reader's Stokes I sample `(XX + YY) / 2` and weight
//! `4 min(w_XX, w_YY)` into caller buffers. The final flag of a correlation
//! is the original FLAG, FLAG_ROW, the cell's addition, or an invalid gain of
//! either station, exactly the `protected_flags(...) | ~ok` rule of the
//! campaign. Nothing per cell is allocated.
//!
//! `decode_rows_strided` decodes selected rows of a blosc chunk straight
//! into a strided destination (one tile of a `(row, channel, corr)` array),
//! so a decoded column is never held twice.

use crate::blosc::{self, Header};
use rayon::prelude::*;

/// Borrowed inputs of `correct_stokes_i`.
pub struct CorrectInputs<'a> {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime_bins: usize,
    pub nfreq_bins: usize,
    pub nant: usize,
    /// Interleaved complex64 `(row, chan, 4)`: `8 * nrow * nchan` floats.
    pub data: &'a [f32],
    /// WEIGHT_SPECTRUM `(row, chan, 4)`.
    pub weights: &'a [f32],
    /// Original FLAG `(row, chan, 4)`, 0 or 1.
    pub flags: &'a [u8],
    /// Original FLAG_ROW `(row,)`.
    pub flag_row: &'a [u8],
    /// The arm's additions `(row, chan)`, or empty for none.
    pub added: &'a [u8],
    pub antenna1: &'a [u32],
    pub antenna2: &'a [u32],
    /// Gain time bin per row and gain frequency bin per channel.
    pub time_bin: &'a [u32],
    pub freq_bin: &'a [u32],
    /// Inverse gains `(t, f, ant, 2, 2)` as interleaved complex128.
    pub inverse: &'a [f64],
    /// Gain validity `(t, f, ant)`.
    pub valid: &'a [u8],
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct C64 {
    re: f64,
    im: f64,
}

impl C64 {
    fn mul(self, o: C64) -> C64 {
        C64 {
            re: self.re * o.re - self.im * o.im,
            im: self.re * o.im + self.im * o.re,
        }
    }

    fn add(self, o: C64) -> C64 {
        C64 {
            re: self.re + o.re,
            im: self.im + o.im,
        }
    }

    fn conj(self) -> C64 {
        C64 {
            re: self.re,
            im: -self.im,
        }
    }
}

/// `a @ b` for 2x2 matrices in row-major order, accumulating each element
/// as `(0 + a[i,0] b[0,j]) + a[i,1] b[1,j]`, NumPy's matmul loop order.
fn matmul(a: &[C64; 4], b: &[C64; 4]) -> [C64; 4] {
    let mut c = [C64 { re: 0., im: 0. }; 4];
    for i in 0..2 {
        for j in 0..2 {
            let mut sum = C64 { re: 0., im: 0. };
            for k in 0..2 {
                sum = sum.add(a[2 * i + k].mul(b[2 * k + j]));
            }
            c[2 * i + j] = sum;
        }
    }
    c
}

fn matrix(values: &[f64]) -> [C64; 4] {
    std::array::from_fn(|k| C64 {
        re: values[2 * k],
        im: values[2 * k + 1],
    })
}

/// NumPy's `np.minimum` for float32: a NaN in either operand is returned.
fn np_minimum(a: f32, b: f32) -> f32 {
    if a.is_nan() || a <= b { a } else { b }
}

/// Check every index and length; returns a message for the first problem.
pub fn check(
    inputs: &CorrectInputs,
    sample_len: usize,
    weight_len: usize,
) -> Result<(), &'static str> {
    let cells = inputs
        .nrow
        .checked_mul(inputs.nchan)
        .ok_or("cell count overflows")?;
    let gains = inputs.ntime_bins * inputs.nfreq_bins * inputs.nant;
    if inputs.data.len() != 8 * cells
        || inputs.weights.len() != 4 * cells
        || inputs.flags.len() != 4 * cells
        || inputs.flag_row.len() != inputs.nrow
        || !(inputs.added.is_empty() || inputs.added.len() == cells)
        || inputs.antenna1.len() != inputs.nrow
        || inputs.antenna2.len() != inputs.nrow
        || inputs.time_bin.len() != inputs.nrow
        || inputs.freq_bin.len() != inputs.nchan
        || inputs.inverse.len() != 8 * gains
        || inputs.valid.len() != gains
    {
        return Err("buffer length mismatch");
    }
    if sample_len != 2 * cells || weight_len != cells {
        return Err("output length mismatch");
    }
    if inputs
        .antenna1
        .iter()
        .chain(inputs.antenna2)
        .any(|&a| a as usize >= inputs.nant)
        || inputs
            .time_bin
            .iter()
            .any(|&t| t as usize >= inputs.ntime_bins)
        || inputs
            .freq_bin
            .iter()
            .any(|&f| f as usize >= inputs.nfreq_bins)
    {
        return Err("index out of range");
    }
    Ok(())
}

/// One row: samples `(nchan, 2)` and weights `(nchan,)`.
fn correct_row(inputs: &CorrectInputs, row: usize, sample: &mut [f32], weight: &mut [f32]) {
    let nchan = inputs.nchan;
    let (p, q) = (inputs.antenna1[row] as usize, inputs.antenna2[row] as usize);
    let t = inputs.time_bin[row] as usize;
    let row_flagged = inputs.flag_row[row] != 0;
    let gain_at = |f: usize, ant: usize| (t * inputs.nfreq_bins + f) * inputs.nant + ant;
    for chan in 0..nchan {
        let cell = row * nchan + chan;
        let f = inputs.freq_bin[chan] as usize;
        let (gp, gq) = (gain_at(f, p), gain_at(f, q));
        let ok = inputs.valid[gp] != 0 && inputs.valid[gq] != 0;
        let (xx, yy) = if ok {
            let inv_p = matrix(&inputs.inverse[8 * gp..8 * gp + 8]);
            let inv_q = matrix(&inputs.inverse[8 * gq..8 * gq + 8]);
            // inv_q^H: conjugate transpose.
            let inv_qh = [
                inv_q[0].conj(),
                inv_q[2].conj(),
                inv_q[1].conj(),
                inv_q[3].conj(),
            ];
            let d = &inputs.data[8 * cell..8 * cell + 8];
            let v: [C64; 4] = std::array::from_fn(|k| C64 {
                re: f64::from(d[2 * k]),
                im: f64::from(d[2 * k + 1]),
            });
            let corrected = matmul(&matmul(&inv_p, &v), &inv_qh);
            (
                [corrected[0].re as f32, corrected[0].im as f32],
                [corrected[3].re as f32, corrected[3].im as f32],
            )
        } else {
            ([0f32; 2], [0f32; 2])
        };
        let re = (xx[0] + yy[0]) * 0.5f32;
        let im = (xx[1] + yy[1]) * 0.5f32;
        let finite = re.is_finite() && im.is_finite();
        sample[2 * chan] = if finite { re } else { 0. };
        sample[2 * chan + 1] = if finite { im } else { 0. };
        let flagged = row_flagged || !ok || (!inputs.added.is_empty() && inputs.added[cell] != 0);
        let good_xx =
            !flagged && inputs.flags[4 * cell] == 0 && xx[0].is_finite() && xx[1].is_finite();
        let good_yy =
            !flagged && inputs.flags[4 * cell + 3] == 0 && yy[0].is_finite() && yy[1].is_finite();
        weight[chan] = if good_xx && good_yy {
            np_minimum(
                inputs.weights[4 * cell] * 4f32,
                inputs.weights[4 * cell + 3] * 4f32,
            )
        } else {
            0.
        };
    }
}

/// Corrected Stokes I sample (interleaved complex64 `(row, chan)`) and
/// reader weight (`(row, chan)`), in parallel over rows.
pub fn correct_stokes_i(
    inputs: &CorrectInputs,
    sample: &mut [f32],
    weight: &mut [f32],
) -> Result<(), &'static str> {
    check(inputs, sample.len(), weight.len())?;
    let nchan = inputs.nchan;
    if nchan == 0 {
        return Ok(());
    }
    sample
        .par_chunks_mut(2 * nchan)
        .zip(weight.par_chunks_mut(nchan))
        .enumerate()
        .for_each(|(row, (s, w))| correct_row(inputs, row, s, w));
    Ok(())
}

/// A raw destination pointer shared by the block tasks; each byte of the
/// chunk belongs to exactly one block, so the tasks write disjoint bytes.
#[derive(Clone, Copy)]
struct Destination(*mut u8);
// SAFETY: tasks write disjoint byte ranges (see above).
unsafe impl Send for Destination {}
unsafe impl Sync for Destination {}

/// Decode blocks `first..first + count` of a chunk from `span` (the
/// compressed bytes starting at block `first`'s offset) and copy the rows
/// `rows` (ascending, each inside those blocks) to `out`, row `i` at byte
/// `i * stride`. `out_len` bounds the destination. Blocks decode in
/// parallel.
///
/// # Safety
///
/// `out` must be valid for writes of `out_len` bytes and not aliased.
#[allow(clippy::too_many_arguments)]
pub unsafe fn decode_rows_strided(
    head: &[u8],
    h: &Header,
    first: usize,
    count: usize,
    span: &[u8],
    span_start: usize,
    row_bytes: usize,
    rows: &[usize],
    out: *mut u8,
    out_len: usize,
    stride: usize,
) -> Result<(), &'static str> {
    if rows.windows(2).any(|w| w[1] <= w[0]) {
        return Err("rows must be ascending and unique");
    }
    if stride < row_bytes {
        return Err("stride shorter than a row");
    }
    if !rows.is_empty() && (rows.len() - 1) * stride + row_bytes > out_len {
        return Err("destination too short");
    }
    if h.blocksize == 0 {
        return Err("zero block size");
    }
    let end_block = first.checked_add(count).ok_or("block range overflows")?;
    if end_block > h.nblocks() {
        return Err("block index out of range");
    }
    if let (Some(&lo), Some(&hi)) = (rows.first(), rows.last())
        && (lo * row_bytes < first * h.blocksize
            || (hi + 1) * row_bytes > (end_block * h.blocksize).min(h.nbytes))
    {
        return Err("row outside the decoded blocks");
    }
    let dest = Destination(out);
    (first..end_block)
        .into_par_iter()
        .map_init(
            || (Vec::new(), Vec::new()),
            |(block, scratch), j| -> Result<(), &'static str> {
                let (start, end) = blosc::block_span(head, h, j)?;
                let bytes = span
                    .get(
                        start
                            .checked_sub(span_start)
                            .ok_or("block before the span")?
                            ..end.checked_sub(span_start).ok_or("block before the span")?,
                    )
                    .ok_or("block outside the span")?;
                let block_lo = j * h.blocksize;
                let bsize = h.blocksize.min(h.nbytes - block_lo);
                let block_hi = block_lo + bsize;
                // Rows overlapping this block: the first whose end passes
                // block_lo, through the last starting before block_hi.
                let a = rows.partition_point(|&r| (r + 1) * row_bytes <= block_lo);
                let b = rows.partition_point(|&r| r * row_bytes < block_hi);
                if a >= b {
                    return Ok(());
                }
                block.resize(bsize, 0);
                blosc::decode_block_bytes(h, j, bytes, block, scratch)?;
                for (i, &r) in rows.iter().enumerate().take(b).skip(a) {
                    let lo = (r * row_bytes).max(block_lo);
                    let hi = ((r + 1) * row_bytes).min(block_hi);
                    let offset = i * stride + (lo - r * row_bytes);
                    let src = &block[lo - block_lo..hi - block_lo];
                    // SAFETY: offset + len <= out_len (checked above) and
                    // the byte range belongs to this block only.
                    let d = dest;
                    unsafe {
                        std::ptr::copy_nonoverlapping(src.as_ptr(), d.0.add(offset), src.len());
                    }
                }
                Ok(())
            },
        )
        .collect::<Result<Vec<()>, _>>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inverse_2x2(g: &[C64; 4]) -> [C64; 4] {
        let det = g[0]
            .mul(g[3])
            .add(g[1].mul(g[2]).mul(C64 { re: -1., im: 0. }));
        let n = det.re * det.re + det.im * det.im;
        let inv_det = C64 {
            re: det.re / n,
            im: -det.im / n,
        };
        [
            g[3].mul(inv_det),
            g[1].mul(inv_det).mul(C64 { re: -1., im: 0. }),
            g[2].mul(inv_det).mul(C64 { re: -1., im: 0. }),
            g[0].mul(inv_det),
        ]
    }

    #[test]
    fn identity_gains_give_the_reader_sample() {
        let data: Vec<f32> = vec![2., 1., 0.1, 0.2, 0.3, 0.4, 4., -1.];
        let weights = vec![1f32, 2., 3., 0.5];
        let mut inverse = Vec::new();
        for _ in 0..2 {
            inverse.extend_from_slice(&[1., 0., 0., 0., 0., 0., 1., 0.]);
        }
        let inputs = CorrectInputs {
            nrow: 1,
            nchan: 1,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 2,
            data: &data,
            weights: &weights,
            flags: &[0, 0, 0, 0],
            flag_row: &[0],
            added: &[],
            antenna1: &[0],
            antenna2: &[1],
            time_bin: &[0],
            freq_bin: &[0],
            inverse: &inverse,
            valid: &[1, 1],
        };
        let (mut s, mut w) = (vec![0f32; 2], vec![0f32; 1]);
        correct_stokes_i(&inputs, &mut s, &mut w).unwrap();
        assert_eq!(s, vec![3., 0.]);
        assert_eq!(w, vec![2.]);
    }

    #[test]
    fn flags_and_invalid_gains_zero_the_weight() {
        let data = vec![1f32; 16];
        let weights = vec![1f32; 8];
        let g = [
            C64 { re: 1.1, im: 0.2 },
            C64 {
                re: 0.05,
                im: -0.01,
            },
            C64 { re: 0.02, im: 0.03 },
            C64 { re: 0.9, im: -0.1 },
        ];
        let inv = inverse_2x2(&g);
        let mut inverse = Vec::new();
        for _ in 0..2 {
            for c in inv {
                inverse.extend_from_slice(&[c.re, c.im]);
            }
        }
        let mut flags = vec![0u8; 8];
        flags[3] = 1; // YY of channel 0
        let base = CorrectInputs {
            nrow: 1,
            nchan: 2,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 2,
            data: &data,
            weights: &weights,
            flags: &flags,
            flag_row: &[0],
            added: &[0, 1],
            antenna1: &[0],
            antenna2: &[1],
            time_bin: &[0],
            freq_bin: &[0, 0],
            inverse: &inverse,
            valid: &[1, 1],
        };
        let (mut s, mut w) = (vec![0f32; 4], vec![9f32; 2]);
        correct_stokes_i(&base, &mut s, &mut w).unwrap();
        assert_eq!(w, vec![0., 0.]);
        assert!(s.iter().all(|v| v.is_finite() && *v != 0.));
        let invalid = CorrectInputs {
            valid: &[1, 0],
            added: &[],
            flags: &[0; 8],
            ..base
        };
        correct_stokes_i(&invalid, &mut s, &mut w).unwrap();
        assert_eq!((s, w), (vec![0f32; 4], vec![0f32; 2]));
    }

    #[test]
    fn minimum_propagates_nan() {
        assert!(np_minimum(f32::NAN, 1.).is_nan());
        assert!(np_minimum(1., f32::NAN).is_nan());
        assert_eq!(np_minimum(2., 1.), 1.);
    }

    #[test]
    fn bad_lengths_are_refused() {
        let inputs = CorrectInputs {
            nrow: 1,
            nchan: 1,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 2,
            data: &[0.; 8],
            weights: &[0.; 4],
            flags: &[0; 4],
            flag_row: &[0],
            added: &[],
            antenna1: &[0],
            antenna2: &[2],
            time_bin: &[0],
            freq_bin: &[0],
            inverse: &[0.; 16],
            valid: &[1, 1],
        };
        let (mut s, mut w) = (vec![0f32; 2], vec![0f32; 1]);
        assert!(correct_stokes_i(&inputs, &mut s, &mut w).is_err());
    }

    #[test]
    fn strided_decode_matches_contiguous() {
        // A memcpyed chunk: header plus raw bytes, 4 blocks of 24 bytes.
        let nbytes = 96usize;
        let mut chunk = vec![2u8, 2, 0x02, 1];
        chunk.extend_from_slice(&(nbytes as u32).to_le_bytes());
        chunk.extend_from_slice(&24u32.to_le_bytes());
        chunk.extend_from_slice(&((16 + nbytes) as u32).to_le_bytes());
        chunk.extend((0..nbytes).map(|b| b as u8));
        let h = blosc::parse_header(&chunk).unwrap();
        let rows = [1usize, 2, 5, 7];
        let row_bytes = 12;
        let stride = 20;
        let mut out = vec![0xffu8; (rows.len() - 1) * stride + row_bytes];
        // SAFETY: `out` is a live vector of `out.len()` bytes.
        unsafe {
            decode_rows_strided(
                &chunk,
                &h,
                0,
                4,
                &chunk,
                0,
                row_bytes,
                &rows,
                out.as_mut_ptr(),
                out.len(),
                stride,
            )
        }
        .unwrap();
        for (i, &r) in rows.iter().enumerate() {
            let expected: Vec<u8> = (r * row_bytes..(r + 1) * row_bytes)
                .map(|b| b as u8)
                .collect();
            assert_eq!(&out[i * stride..i * stride + row_bytes], &expected[..]);
        }
        assert!(out[row_bytes..stride].iter().all(|&b| b == 0xff));
    }
}
