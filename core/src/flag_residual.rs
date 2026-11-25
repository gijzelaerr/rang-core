// SPDX-License-Identifier: MIT
//! Residual flagging (`flag.residual`, issue #51, `research/flag-residual.md`).
//!
//! Two rules on one block of rows (a field's scan, chosen by the caller):
//!
//! - [`flags_rang`]: per channel block and correlation, a noise level per
//!   antenna fitted so that a baseline's median |r| is the product of its two
//!   antennas' levels (least squares on the logarithms); z = |r| / σ with
//!   σ = level / sqrt(2 ln 2) (the median of a Rayleigh amplitude); a cell is
//!   flagged when any correlation has z above `sigma`; a baseline's channel
//!   over time, or a dump over the band, when its mean z² exceeds `persist`
//!   times the block's median z²; with `guard` below 1, a baseline whose new
//!   flags would take it past that flagged fraction gets none.
//! - [`flags_quartical`]: QuartiCal 0.2.7's `mad_flags`
//!   (`quartical/flagging/flagging_kernels.py`: `compute_bl_mad_and_med`,
//!   `compute_gbl_mad_and_med`, `compute_mad_flags`), on one QuartiCal data
//!   chunk, unwhitened, in single precision as QuartiCal's numba kernels.
//!
//! Flags at the gain solve (`calibrate.solver_flags`, issue #58,
//! `research/solver-flags.md`): [`diag_residual`] forms a diagonal term's
//! parallel-hand residual `d - g_p m g_q^*`, and [`solver_flags`] runs either
//! rule on one solution interval's chunk, then a minimum-sample rule and a
//! per-baseline guard.
//!
//! Portions are a Rust translation of QuartiCal 0.2.7's
//! `quartical/flagging/flagging_kernels.py`, distributed under the MIT
//! License:
//!
//! > MIT License
//! >
//! > Copyright (c) 2022 Jonathan Simon Kenyon
//! >
//! > Permission is hereby granted, free of charge, to any person obtaining a
//! > copy of this software and associated documentation files (the
//! > "Software"), to deal in the Software without restriction, including
//! > without limitation the rights to use, copy, modify, merge, publish,
//! > distribute, sublicense, and/or sell copies of the Software, and to permit
//! > persons to whom the Software is furnished to do so, subject to the
//! > following conditions:
//! >
//! > The above copyright notice and this permission notice shall be included
//! > in all copies or substantial portions of the Software.
//! >
//! > THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
//! > OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
//! > MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
//! > NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
//! > DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
//! > OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
//! > USE OR OTHER DEALINGS IN THE SOFTWARE.
//!
//! The translation and the rest of this file are part of Rang (MIT).
//!
//! Arrays: residual `(row, chan, corr)` complex64 as interleaved f32 pairs;
//! flags `(row, chan, corr)` bytes (0 or 1) for [`flags_rang`] and
//! `(row, chan)` bytes for [`flags_quartical`], as QuartiCal's flag column;
//! the result is `(row, chan)` bytes of new flags (cells to flag in every
//! correlation).

use rayon::prelude::*;

/// Settings of [`flags_rang`].
#[derive(Clone, Copy, Debug)]
pub struct RangSettings {
    pub sigma: f64,
    pub persist: f64,
    /// Channels per noise block.
    pub block: usize,
    /// Largest flagged fraction a baseline may reach (1 or more: no guard).
    pub guard: f64,
}

/// What [`flags_rang`] did.
#[derive(Clone, Debug, Default)]
pub struct RangCounts {
    pub cells: u64,
    pub cell_rule: u64,
    pub persist_chan: u64,
    pub persist_dump: u64,
    pub guarded_baselines: u64,
    pub added: u64,
}

fn check(
    nrow: usize,
    nchan: usize,
    ncorr: usize,
    res: &[f32],
    a1: &[u32],
    a2: &[u32],
) -> Result<(), String> {
    if res.len() != nrow * nchan * ncorr * 2 {
        return Err(format!(
            "residual has {} values, expected {}",
            res.len(),
            nrow * nchan * ncorr * 2
        ));
    }
    if a1.len() != nrow || a2.len() != nrow {
        return Err("antenna1/antenna2 must have one entry per row".into());
    }
    Ok(())
}

/// Median of `v` (reordered), numpy's definition: the mean of the two middle
/// values for an even count, in f32; `None` when empty.
fn median_f32(v: &mut [f32]) -> Option<f32> {
    let n = v.len();
    if n == 0 {
        return None;
    }
    let mid = n / 2;
    let (_, &mut hi, _) = v.select_nth_unstable_by(mid, |a, b| a.total_cmp(b));
    if n % 2 == 1 {
        return Some(hi);
    }
    let lo = v[..mid].iter().copied().fold(f32::NEG_INFINITY, f32::max);
    Some((lo + hi) / 2.0)
}

/// Median of f64 values (reordered), the mean of the two middle values.
fn median_f64(v: &mut [f64]) -> Option<f64> {
    let n = v.len();
    if n == 0 {
        return None;
    }
    let mid = n / 2;
    let (_, &mut hi, _) = v.select_nth_unstable_by(mid, |a, b| a.total_cmp(b));
    if n % 2 == 1 {
        return Some(hi);
    }
    let lo = v[..mid].iter().copied().fold(f64::NEG_INFINITY, f64::max);
    Some(0.5 * (lo + hi))
}

/// Per-antenna levels `l` with `log m_pq ≈ l_p + l_q` by least squares over the
/// baselines with a finite positive median (Gauss-Seidel on the normal
/// equations; antennas on no such baseline stay NaN).
fn fit_antenna_levels(nant: usize, bl: &[(usize, usize, f64)]) -> Vec<f64> {
    let mut l = vec![0.0_f64; nant];
    let mut deg = vec![0usize; nant];
    for &(p, q, _) in bl {
        deg[p] += 1;
        deg[q] += 1;
    }
    if bl.is_empty() {
        return vec![f64::NAN; nant];
    }
    let mean = bl.iter().map(|b| b.2).sum::<f64>() / bl.len() as f64;
    for (a, d) in deg.iter().enumerate() {
        if *d > 0 {
            l[a] = 0.5 * mean;
        }
    }
    for _ in 0..200 {
        let mut num = vec![0.0_f64; nant];
        for &(p, q, y) in bl {
            num[p] += y - l[q];
            num[q] += y - l[p];
        }
        let mut change = 0.0_f64;
        for a in 0..nant {
            if deg[a] > 0 {
                let new = num[a] / deg[a] as f64;
                change = change.max((new - l[a]).abs());
                l[a] = new;
            }
        }
        if change < 1e-10 {
            break;
        }
    }
    for a in 0..nant {
        if deg[a] == 0 {
            l[a] = f64::NAN;
        }
    }
    l
}

/// The rang rule on one block of rows (see the module docs). `dump` is each
/// row's dump index (0..ndump) for the persistence rule over the band.
#[allow(clippy::too_many_arguments)]
pub fn flags_rang(
    res: &[f32],
    flag: &[u8],
    nrow: usize,
    nchan: usize,
    ncorr: usize,
    a1: &[u32],
    a2: &[u32],
    dump: &[u32],
    nant: usize,
    s: &RangSettings,
) -> Result<(Vec<u8>, RangCounts), String> {
    check(nrow, nchan, ncorr, res, a1, a2)?;
    if flag.len() != nrow * nchan * ncorr || dump.len() != nrow || s.block == 0 {
        return Err("flag must be (row, chan, corr), dump one per row, block > 0".into());
    }
    let nbl = nant * nant;
    let blk_of = |c: usize| c / s.block;
    let nblk = nchan.div_ceil(s.block);
    let cross: Vec<bool> = (0..nrow).map(|r| a1[r] != a2[r]).collect();
    let bl_id: Vec<usize> = (0..nrow)
        .map(|r| a1[r] as usize * nant + a2[r] as usize)
        .collect();
    let amp = |r: usize, c: usize, k: usize| -> f32 {
        let i = ((r * nchan + c) * ncorr + k) * 2;
        (res[i] * res[i] + res[i + 1] * res[i + 1]).sqrt()
    };
    let ok = |r: usize, c: usize, k: usize| flag[(r * nchan + c) * ncorr + k] == 0;
    // Expected Rayleigh sigma per (block, corr, baseline).
    let rayleigh = (2.0_f64 * std::f64::consts::LN_2).sqrt();
    let sig: Vec<Vec<f64>> = (0..nblk * ncorr)
        .into_par_iter()
        .map(|bk| {
            let (b, k) = (bk / ncorr, bk % ncorr);
            let mut per_bl: Vec<Vec<f32>> = vec![Vec::new(); nbl];
            for r in 0..nrow {
                if !cross[r] {
                    continue;
                }
                for c in (b * s.block)..((b + 1) * s.block).min(nchan) {
                    if ok(r, c, k) {
                        per_bl[bl_id[r]].push(amp(r, c, k));
                    }
                }
            }
            let mut obs = Vec::new();
            for (id, v) in per_bl.iter_mut().enumerate() {
                if let Some(m) = median_f32(v)
                    && m > 0.0
                {
                    obs.push((id / nant, id % nant, (m as f64).ln()));
                }
            }
            let l = fit_antenna_levels(nant, &obs);
            let mut out = vec![f64::NAN; nbl];
            for (id, o) in out.iter_mut().enumerate() {
                let (p, q) = (id / nant, id % nant);
                if p != q {
                    *o = (l[p] + l[q]).exp() / rayleigh;
                }
            }
            out
        })
        .collect();
    // z per cell: the largest over the unflagged correlations (NaN when none).
    let mut z = vec![f32::NAN; nrow * nchan];
    z.par_chunks_mut(nchan).enumerate().for_each(|(r, zr)| {
        if !cross[r] {
            return;
        }
        for (c, zc) in zr.iter_mut().enumerate() {
            let mut best = f32::NAN;
            for k in 0..ncorr {
                let sg = sig[blk_of(c) * ncorr + k][bl_id[r]];
                if ok(r, c, k) && sg.is_finite() && sg > 0.0 {
                    let v = (amp(r, c, k) as f64 / sg) as f32;
                    if best.is_nan() || v > best {
                        best = v;
                    }
                }
            }
            *zc = best;
        }
    });
    let mut new = vec![0u8; nrow * nchan];
    let mut counts = RangCounts::default();
    for (i, &v) in z.iter().enumerate() {
        if v.is_finite() {
            counts.cells += 1;
            if v as f64 > s.sigma {
                new[i] = 1;
                counts.cell_rule += 1;
            }
        }
    }
    // Persistence: mean z^2 per (baseline, channel) over dumps and per
    // (baseline, dump) over channels, against the block's median z^2.
    let mut z2: Vec<f64> = z
        .iter()
        .filter(|v| v.is_finite())
        .map(|&v| (v as f64) * (v as f64))
        .collect();
    if let Some(med) = median_f64(&mut z2) {
        let limit = s.persist * med;
        let ndump = dump.iter().copied().max().map_or(0, |d| d as usize + 1);
        let mut chan_sum = vec![0.0_f64; nbl * nchan];
        let mut chan_n = vec![0u32; nbl * nchan];
        let mut dump_sum = vec![0.0_f64; nbl * ndump];
        let mut dump_n = vec![0u32; nbl * ndump];
        for r in 0..nrow {
            for c in 0..nchan {
                let v = z[r * nchan + c];
                if v.is_finite() {
                    let v2 = (v as f64) * (v as f64);
                    chan_sum[bl_id[r] * nchan + c] += v2;
                    chan_n[bl_id[r] * nchan + c] += 1;
                    dump_sum[bl_id[r] * ndump + dump[r] as usize] += v2;
                    dump_n[bl_id[r] * ndump + dump[r] as usize] += 1;
                }
            }
        }
        for r in 0..nrow {
            if !cross[r] {
                continue;
            }
            let d = bl_id[r] * ndump + dump[r] as usize;
            let dump_bad = dump_n[d] > 0 && dump_sum[d] / dump_n[d] as f64 > limit;
            for c in 0..nchan {
                let i = r * nchan + c;
                if !z[i].is_finite() || new[i] == 1 {
                    continue;
                }
                let j = bl_id[r] * nchan + c;
                if chan_n[j] > 0 && chan_sum[j] / chan_n[j] as f64 > limit {
                    new[i] = 1;
                    counts.persist_chan += 1;
                } else if dump_bad {
                    new[i] = 1;
                    counts.persist_dump += 1;
                }
            }
        }
    }
    // Guard: drop a baseline's new flags when they would take it past `guard`.
    if s.guard < 1.0 {
        let mut total = vec![0u64; nbl];
        let mut flagged = vec![0u64; nbl];
        let mut added = vec![0u64; nbl];
        for r in 0..nrow {
            if !cross[r] {
                continue;
            }
            for c in 0..nchan {
                total[bl_id[r]] += 1;
                let was = (0..ncorr).all(|k| !ok(r, c, k));
                if was {
                    flagged[bl_id[r]] += 1;
                } else if new[r * nchan + c] == 1 {
                    added[bl_id[r]] += 1;
                }
            }
        }
        let over: Vec<bool> = (0..nbl)
            .map(|b| total[b] > 0 && (flagged[b] + added[b]) as f64 > s.guard * total[b] as f64)
            .collect();
        counts.guarded_baselines = over.iter().filter(|&&o| o).count() as u64;
        for r in 0..nrow {
            if over[bl_id[r]] {
                new[r * nchan..(r + 1) * nchan].fill(0);
            }
        }
    }
    counts.added = new.iter().map(|&v| v as u64).sum();
    Ok((new, counts))
}

/// QuartiCal's baseline id with autocorrelations, `a1 (2 n - a1 - 1) / 2 + a2`.
fn qc_bl_id(a1: u32, a2: u32, nant: usize) -> usize {
    let (a1, a2) = (a1 as usize, a2 as usize);
    a1 * (2 * nant - a1 - 1) / 2 + a2
}

/// Median and MAD of `v` (reordered), as QuartiCal: `med = median(v)`,
/// `mad = median(|v - med|)`, single precision.
fn med_mad(v: &mut [f32]) -> Option<(f32, f32)> {
    let med = median_f32(v)?;
    let mut dev: Vec<f32> = v.iter().map(|x| (x - med).abs()).collect();
    let mad = median_f32(&mut dev)?;
    Some((mad, med))
}

/// QuartiCal 0.2.7's `mad_flags` on one data chunk (unwhitened residual,
/// the selected correlations `corr_sel`, `max_deviation` 0 as its default
/// unless given). `flag` is `(row, chan)`.
#[allow(clippy::too_many_arguments)]
pub fn flags_quartical(
    res: &[f32],
    flag: &[u8],
    nrow: usize,
    nchan: usize,
    ncorr: usize,
    a1: &[u32],
    a2: &[u32],
    nant: usize,
    corr_sel: &[usize],
    bl_threshold: f64,
    gbl_threshold: f64,
    max_deviation: f64,
) -> Result<Vec<u8>, String> {
    check(nrow, nchan, ncorr, res, a1, a2)?;
    if flag.len() != nrow * nchan {
        return Err("flag must be (row, chan) for the QuartiCal rule".into());
    }
    let nbl = nant * (nant + 1) / 2;
    let ids: Vec<usize> = (0..nrow).map(|r| qc_bl_id(a1[r], a2[r], nant)).collect();
    let part =
        |r: usize, c: usize, k: usize, im: usize| res[((r * nchan + c) * ncorr + k) * 2 + im];
    let unflagged = |r: usize, c: usize| flag[r * nchan + c] != 1;
    let scale = 1.4826_f32;
    let inf_or = |t: f64| if t * t == 0.0 { f64::INFINITY } else { t * t };
    let (bl_t2, gbl_t2, maxdev2) = (
        inf_or(bl_threshold),
        inf_or(gbl_threshold),
        inf_or(max_deviation),
    );
    let mut out = vec![0u8; nrow * nchan];
    for &k in corr_sel {
        // Global and per-baseline (mad, med) of the real and imaginary parts.
        let mut gbl = [(0.0_f32, 0.0_f32); 2];
        let mut bl = vec![[(0.0_f32, 0.0_f32); 2]; nbl];
        for im in 0..2 {
            let mut all = Vec::new();
            let mut per: Vec<Vec<f32>> = vec![Vec::new(); nbl];
            for r in 0..nrow {
                for c in 0..nchan {
                    if unflagged(r, c) {
                        let v = part(r, c, k, im);
                        all.push(v);
                        per[ids[r]].push(v);
                    }
                }
            }
            if let Some(m) = med_mad(&mut all) {
                gbl[im] = m;
            }
            for (b, v) in per.iter_mut().enumerate() {
                if let Some(m) = med_mad(v) {
                    bl[b][im] = m;
                }
            }
        }
        let (gmad_re, gmed_re) = (gbl[0].0 * scale, gbl[0].1);
        let (gmad_im, gmed_im) = (gbl[1].0 * scale, gbl[1].1);
        if gmad_re == 0.0 || gmad_im == 0.0 {
            out.fill(1);
            continue;
        }
        let bmad_re: Vec<f32> = bl.iter().map(|b| b[0].0 * scale).collect();
        let bmad_im: Vec<f32> = bl.iter().map(|b| b[1].0 * scale).collect();
        let stats = |v: &[f32]| -> (f64, f64) {
            let x: Vec<f64> = v.iter().filter(|&&m| m > 0.0).map(|&m| m as f64).collect();
            let n = x.len() as f64;
            let mean = x.iter().sum::<f64>() / n;
            let var = x.iter().map(|m| (m - mean) * (m - mean)).sum::<f64>() / n;
            (mean, var.sqrt())
        };
        let use_dev = maxdev2.is_finite();
        let (mre, sre) = if use_dev { stats(&bmad_re) } else { (0.0, 1.0) };
        let (mim, sim) = if use_dev { stats(&bmad_im) } else { (0.0, 1.0) };
        for r in 0..nrow {
            if a1[r] == a2[r] {
                continue;
            }
            let b = ids[r];
            let (mad_re, med_re) = (bmad_re[b], bl[b][0].1);
            let (mad_im, med_im) = (bmad_im[b], bl[b][1].1);
            if mad_re == 0.0 || mad_im == 0.0 {
                out[r * nchan..(r + 1) * nchan].fill(1);
                continue;
            }
            if use_dev {
                let dre = (mad_re as f64 - mre).abs() / sre;
                let dim = (mad_im as f64 - mim).abs() / sim;
                if dre * dre + dim * dim > maxdev2 {
                    out[r * nchan..(r + 1) * nchan].fill(1);
                    continue;
                }
            }
            for c in 0..nchan {
                // QuartiCal subtracts each real median (of the real part, and of
                // the imaginary part) from the complex whitened residual and
                // takes the complex magnitude: `np.abs(wres[row, chan, corr] -
                // med_pq_im)` shifts the real part by the imaginary median.
                // Reproduced as is (the oracle arm), research/flag-residual.md
                // amendment 5.
                let (vre, vim) = (part(r, c, k, 0), part(r, c, k, 1));
                let bre = (vre - med_re).hypot(vim) / mad_re;
                let bim = (vre - med_im).hypot(vim) / mad_im;
                if ((bre * bre + bim * bim) as f64) > bl_t2 {
                    out[r * nchan + c] = 1;
                }
                let gre = (vre - gmed_re).hypot(vim) / gmad_re;
                let gim = (vre - gmed_im).hypot(vim) / gmad_im;
                if ((gre * gre + gim * gim) as f64) > gbl_t2 {
                    out[r * nchan + c] = 1;
                }
            }
        }
    }
    Ok(out)
}

/// The per-channel, per-correlation complex median of `(row, chan, corr)`
/// data over cells unflagged in that correlation (real and imaginary parts
/// separately), interleaved `(chan, corr, 2)`; NaN where no cell is unflagged.
pub fn median_model(
    data: &[f32],
    flag: &[u8],
    nrow: usize,
    nchan: usize,
    ncorr: usize,
) -> Result<Vec<f32>, String> {
    if data.len() != nrow * nchan * ncorr * 2 || flag.len() != nrow * nchan * ncorr {
        return Err("data must be (row, chan, corr) complex, flag (row, chan, corr)".into());
    }
    let out: Vec<[f32; 2]> = (0..nchan * ncorr)
        .into_par_iter()
        .map(|ck| {
            let (c, k) = (ck / ncorr, ck % ncorr);
            let mut re = Vec::with_capacity(nrow);
            let mut im = Vec::with_capacity(nrow);
            for r in 0..nrow {
                if flag[(r * nchan + c) * ncorr + k] == 0 {
                    let i = ((r * nchan + c) * ncorr + k) * 2;
                    re.push(data[i]);
                    im.push(data[i + 1]);
                }
            }
            [
                median_f32(&mut re).unwrap_or(f32::NAN),
                median_f32(&mut im).unwrap_or(f32::NAN),
            ]
        })
        .collect();
    Ok(out.into_iter().flatten().collect())
}

/// The residual of a diagonal gain term on the parallel hands (issue #58,
/// `research/solver-flags.md` 3.1): `r = d - g_p m g_q^*` per hand, from
/// `(row, chan, 4)` data and model (complex64 as f32 pairs), the gains
/// `(ntime, nfreq, nant, 2)` complex128 as f64 pairs, each row's interval
/// `time_bin` and each channel's `freq_bin`. Returns the residual `(row,
/// chan, 2)` complex64 as f32 pairs and a `(row, chan)` byte that is 1
/// where a gain of either antenna is flagged (`gain_flags` `(ntime, nfreq,
/// nant, 2)`, nonzero flagged) or not finite.
#[allow(clippy::too_many_arguments)]
pub fn diag_residual(
    data: &[f32],
    model: &[f32],
    nrow: usize,
    nchan: usize,
    a1: &[u32],
    a2: &[u32],
    time_bin: &[u32],
    freq_bin: &[u32],
    gains: &[f64],
    gain_flags: &[u8],
    ntime: usize,
    nfreq: usize,
    nant: usize,
) -> Result<(Vec<f32>, Vec<u8>), String> {
    let cells = nrow * nchan;
    if data.len() != cells * 8 || model.len() != cells * 8 {
        return Err("data and model must be (row, chan, 4) complex".into());
    }
    if a1.len() != nrow || a2.len() != nrow || time_bin.len() != nrow {
        return Err("antenna1, antenna2 and time_bin must have one entry per row".into());
    }
    if freq_bin.len() < nchan {
        return Err("freq_bin must have one entry per channel".into());
    }
    let ngain = ntime * nfreq * nant * 2;
    if gains.len() != ngain * 2 || gain_flags.len() != ngain {
        return Err("gains must be (ntime, nfreq, nant, 2) complex, gain_flags the same".into());
    }
    for r in 0..nrow {
        if time_bin[r] as usize >= ntime || a1[r] as usize >= nant || a2[r] as usize >= nant {
            return Err(format!("row {r}: interval or antenna out of range"));
        }
    }
    if freq_bin[..nchan].iter().any(|&f| f as usize >= nfreq) {
        return Err("freq_bin out of range".into());
    }
    let mut res = vec![0.0_f32; cells * 4];
    let mut bad = vec![0u8; cells];
    if nchan == 0 {
        return Ok((res, bad));
    }
    res.par_chunks_mut(nchan * 4)
        .zip(bad.par_chunks_mut(nchan))
        .enumerate()
        .for_each(|(r, (rrow, brow))| {
            let (p, q, t) = (a1[r] as usize, a2[r] as usize, time_bin[r] as usize);
            for c in 0..nchan {
                let f = freq_bin[c] as usize;
                let base = (t * nfreq + f) * nant;
                for (h, k) in [(0usize, 0usize), (1, 3)] {
                    let (ip, iq) = ((base + p) * 2 + h, (base + q) * 2 + h);
                    let gp = (gains[2 * ip], gains[2 * ip + 1]);
                    let gq = (gains[2 * iq], gains[2 * iq + 1]);
                    let finite = gp.0.is_finite()
                        && gp.1.is_finite()
                        && gq.0.is_finite()
                        && gq.1.is_finite();
                    if gain_flags[ip] != 0 || gain_flags[iq] != 0 || !finite {
                        brow[c] = 1;
                    }
                    let i = ((r * nchan + c) * 4 + k) * 2;
                    let (mr, mi) = (model[i] as f64, model[i + 1] as f64);
                    // g_p m, then times conj(g_q).
                    let (ar, ai) = (gp.0 * mr - gp.1 * mi, gp.0 * mi + gp.1 * mr);
                    let (vr, vi) = (ar * gq.0 + ai * gq.1, ai * gq.0 - ar * gq.1);
                    let o = (c * 2 + h) * 2;
                    rrow[o] = (data[i] as f64 - vr) as f32;
                    rrow[o + 1] = (data[i + 1] as f64 - vi) as f32;
                }
            }
        });
    Ok((res, bad))
}

/// Settings of [`solver_flags`] (`calibrate.solver_flags`).
#[derive(Clone, Copy, Debug)]
pub struct SolverSettings {
    /// QuartiCal's `mad_flags` rule; otherwise the rang rule.
    pub quartical: bool,
    pub sigma: f64,
    /// QuartiCal's `threshold_global` (quartical only).
    pub global_sigma: f64,
    /// The rang rule's persistence factor (rang only).
    pub persist: f64,
    /// The rang rule's channels per noise block (rang only).
    pub block: usize,
    /// Largest flagged fraction new flags may take a baseline to within the
    /// chunk (1 or more: no guard).
    pub guard: f64,
    /// A baseline with fewer unflagged cells in the chunk gets no new flags.
    pub min_cells: usize,
}

/// What [`solver_flags`] did on one chunk.
#[derive(Clone, Debug, Default)]
pub struct SolverCounts {
    pub cells: u64,
    pub input_flagged: u64,
    /// Cells the rule flagged that were not flagged before.
    pub rule: u64,
    pub sparse_baselines: u64,
    pub guarded_baselines: u64,
    pub added: u64,
}

/// New flags of one statistics chunk (one solution interval, every
/// channel): the rule on the parallel-hand residual `res` `(row, chan, 2)`
/// complex64 as f32 pairs, with `flag` `(row, chan)` the cells that take no
/// part (nonzero), then `min_cells` and `guard` per baseline. Returns the
/// `(row, chan)` bytes of cells to flag (none already flagged, none on an
/// autocorrelation) and the counts. `dump` is each row's dump index (the
/// rang rule's persistence over the band).
#[allow(clippy::too_many_arguments)]
pub fn solver_flags(
    res: &[f32],
    flag: &[u8],
    nrow: usize,
    nchan: usize,
    a1: &[u32],
    a2: &[u32],
    dump: &[u32],
    nant: usize,
    s: &SolverSettings,
) -> Result<(Vec<u8>, SolverCounts), String> {
    check(nrow, nchan, 2, res, a1, a2)?;
    if flag.len() != nrow * nchan || dump.len() != nrow {
        return Err("flag must be (row, chan), dump one per row".into());
    }
    if a1.iter().chain(a2).any(|&a| a as usize >= nant) {
        return Err("antenna out of range".into());
    }
    let input: Vec<u8> = flag.iter().map(|&f| u8::from(f != 0)).collect();
    let mut new = if s.quartical {
        flags_quartical(
            res,
            &input,
            nrow,
            nchan,
            2,
            a1,
            a2,
            nant,
            &[0, 1],
            s.sigma,
            s.global_sigma,
            0.0,
        )?
    } else {
        let per_corr: Vec<u8> = input.iter().flat_map(|&f| [f, f]).collect();
        let rs = RangSettings {
            sigma: s.sigma,
            persist: s.persist,
            block: s.block,
            guard: 1.0,
        };
        flags_rang(res, &per_corr, nrow, nchan, 2, a1, a2, dump, nant, &rs)?.0
    };
    let mut counts = SolverCounts {
        cells: (nrow * nchan) as u64,
        ..Default::default()
    };
    for r in 0..nrow {
        let auto = a1[r] == a2[r];
        for c in 0..nchan {
            let i = r * nchan + c;
            counts.input_flagged += u64::from(input[i]);
            if input[i] != 0 || auto {
                new[i] = 0;
            }
            counts.rule += u64::from(new[i] != 0);
        }
    }
    // Per baseline: cells, already flagged, new.
    let nbl = nant * nant;
    let mut tot = vec![0u64; nbl];
    let mut was = vec![0u64; nbl];
    let mut add = vec![0u64; nbl];
    let bl = |r: usize| a1[r] as usize * nant + a2[r] as usize;
    for r in 0..nrow {
        let b = bl(r);
        tot[b] += nchan as u64;
        for c in 0..nchan {
            let i = r * nchan + c;
            was[b] += u64::from(input[i]);
            add[b] += u64::from(new[i] != 0);
        }
    }
    let mut drop = vec![false; nbl];
    for b in 0..nbl {
        if add[b] == 0 {
            continue;
        }
        if tot[b] - was[b] < s.min_cells as u64 {
            drop[b] = true;
            counts.sparse_baselines += 1;
        } else if s.guard < 1.0 && (was[b] + add[b]) as f64 > s.guard * tot[b] as f64 {
            drop[b] = true;
            counts.guarded_baselines += 1;
        }
    }
    for r in 0..nrow {
        if drop[bl(r)] {
            new[r * nchan..(r + 1) * nchan].fill(0);
        }
    }
    counts.added = new.iter().map(|&x| u64::from(x != 0)).sum();
    Ok((new, counts))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(seed: &mut u64) -> f64 {
        *seed = seed
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*seed >> 11) as f64) / ((1u64 << 53) as f64)
    }

    fn gauss(seed: &mut u64) -> f64 {
        let u = lcg(seed).max(1e-300);
        let v = lcg(seed);
        (-2.0 * u.ln()).sqrt() * (2.0 * std::f64::consts::PI * v).cos()
    }

    /// Noise with antenna-dependent levels and a few strong RFI cells:
    /// the rule flags the RFI, not the warm antenna's baselines.
    #[test]
    fn rang_rule_flags_rfi_not_a_warm_antenna() {
        let (nant, ndump, nchan, ncorr) = (8usize, 40usize, 32usize, 4usize);
        let level: Vec<f64> = (0..nant).map(|a| if a == 3 { 3.0 } else { 1.0 }).collect();
        let mut a1 = Vec::new();
        let mut a2 = Vec::new();
        let mut dump = Vec::new();
        for d in 0..ndump {
            for p in 0..nant {
                for q in (p + 1)..nant {
                    a1.push(p as u32);
                    a2.push(q as u32);
                    dump.push(d as u32);
                }
            }
        }
        let nrow = a1.len();
        let mut seed = 7u64;
        let mut res = vec![0f32; nrow * nchan * ncorr * 2];
        for r in 0..nrow {
            let s = level[a1[r] as usize] * level[a2[r] as usize];
            for c in 0..nchan {
                for k in 0..ncorr {
                    let i = ((r * nchan + c) * ncorr + k) * 2;
                    res[i] = (s * gauss(&mut seed)) as f32;
                    res[i + 1] = (s * gauss(&mut seed)) as f32;
                }
            }
        }
        let rfi: Vec<(usize, usize)> = vec![(5, 3), (100, 17), (200, 30), (333, 8)];
        for &(r, c) in &rfi {
            let s = level[a1[r] as usize] * level[a2[r] as usize];
            res[((r * nchan + c) * ncorr) * 2] += (40.0 * s) as f32;
        }
        let flag = vec![0u8; nrow * nchan * ncorr];
        let st = RangSettings {
            sigma: 5.0,
            persist: 3.0,
            block: 16,
            guard: 0.8,
        };
        let (new, counts) =
            flags_rang(&res, &flag, nrow, nchan, ncorr, &a1, &a2, &dump, nant, &st).unwrap();
        for &(r, c) in &rfi {
            assert_eq!(new[r * nchan + c], 1, "RFI cell ({r}, {c}) not flagged");
        }
        // The warm antenna's baselines are not flagged wholesale.
        let warm: usize = (0..nrow)
            .filter(|&r| a1[r] == 3 || a2[r] == 3)
            .map(|r| {
                new[r * nchan..(r + 1) * nchan]
                    .iter()
                    .map(|&v| v as usize)
                    .sum::<usize>()
            })
            .sum();
        let warm_cells = (0..nrow).filter(|&r| a1[r] == 3 || a2[r] == 3).count() * nchan;
        assert!(
            (warm as f64) < 0.01 * warm_cells as f64,
            "{warm} of {warm_cells} warm cells flagged"
        );
        assert!(counts.added < (nrow * nchan / 100) as u64);
    }

    #[test]
    fn guard_keeps_a_baseline_below_its_limit() {
        // Six antennas (with three, one bad baseline is fitted exactly by the
        // antenna levels and nothing is flagged: a limit of the factorisation).
        let (nant, ndump, nchan, ncorr) = (6usize, 20usize, 16usize, 4usize);
        let (mut a1, mut a2, mut dump) = (Vec::new(), Vec::new(), Vec::new());
        for d in 0..ndump {
            for p in 0..nant {
                for q in (p + 1)..nant {
                    a1.push(p as u32);
                    a2.push(q as u32);
                    dump.push(d as u32);
                }
            }
        }
        let nrow = a1.len();
        let mut seed = 11u64;
        let mut res: Vec<f32> = (0..nrow * nchan * ncorr * 2)
            .map(|_| gauss(&mut seed) as f32)
            .collect();
        // Baseline 0-1 carries strong RFI in every cell.
        for r in 0..nrow {
            if a1[r] == 0 && a2[r] == 1 {
                for c in 0..nchan {
                    res[((r * nchan + c) * ncorr) * 2] += 100.0;
                }
            }
        }
        let flag = vec![0u8; nrow * nchan * ncorr];
        let rows01: Vec<usize> = (0..nrow).filter(|&r| a1[r] == 0 && a2[r] == 1).collect();
        let st = RangSettings {
            sigma: 5.0,
            persist: 1e9,
            block: 16,
            guard: 1.0,
        };
        let (new, _) =
            flags_rang(&res, &flag, nrow, nchan, ncorr, &a1, &a2, &dump, nant, &st).unwrap();
        let hit: usize = rows01
            .iter()
            .map(|&r| {
                new[r * nchan..(r + 1) * nchan]
                    .iter()
                    .map(|&v| v as usize)
                    .sum::<usize>()
            })
            .sum();
        assert!(
            hit as f64 > 0.8 * (rows01.len() * nchan) as f64,
            "without the guard: {hit}"
        );
        let st = RangSettings { guard: 0.8, ..st };
        let (new, counts) =
            flags_rang(&res, &flag, nrow, nchan, ncorr, &a1, &a2, &dump, nant, &st).unwrap();
        assert!(
            rows01
                .iter()
                .all(|&r| new[r * nchan..(r + 1) * nchan].iter().all(|&v| v == 0))
        );
        assert_eq!(counts.guarded_baselines, 1);
    }

    #[test]
    fn quartical_rule_flags_an_outlier_and_not_autos() {
        let (nant, nchan, ncorr) = (4usize, 16usize, 4usize);
        let mut a1 = Vec::new();
        let mut a2 = Vec::new();
        for _ in 0..30 {
            for p in 0..nant {
                for q in p..nant {
                    a1.push(p as u32);
                    a2.push(q as u32);
                }
            }
        }
        let nrow = a1.len();
        let mut seed = 3u64;
        let mut res: Vec<f32> = (0..nrow * nchan * ncorr * 2)
            .map(|_| gauss(&mut seed) as f32)
            .collect();
        let r0 = 1; // a cross row (0, 1)
        assert_ne!(a1[r0], a2[r0]);
        res[((r0 * nchan + 4) * ncorr) * 2] = 50.0;
        let flag = vec![0u8; nrow * nchan];
        let out = flags_quartical(
            &res,
            &flag,
            nrow,
            nchan,
            ncorr,
            &a1,
            &a2,
            nant,
            &[0, 3],
            5.0,
            10.0,
            0.0,
        )
        .unwrap();
        assert_eq!(out[r0 * nchan + 4], 1);
        for r in 0..nrow {
            if a1[r] == a2[r] {
                assert!(out[r * nchan..(r + 1) * nchan].iter().all(|&v| v == 0));
            }
        }
        let n: usize = out.iter().map(|&v| v as usize).sum();
        assert!(n < nrow * nchan / 50, "{n} flagged");
    }

    #[test]
    fn median_model_is_per_channel_and_skips_flags() {
        let data = vec![1.0f32, 0.0, 3.0, 0.0, 100.0, 0.0]; // 3 rows, 1 chan, 1 corr
        let flag = vec![0u8, 0, 1];
        let m = median_model(&data, &flag, 3, 1, 1).unwrap();
        assert_eq!(m, vec![2.0, 0.0]);
    }

    /// Rows of every cross baseline of `nant` antennas over `ndump` dumps.
    fn layout(nant: usize, ndump: usize) -> (Vec<u32>, Vec<u32>, Vec<u32>) {
        let (mut a1, mut a2, mut dump) = (Vec::new(), Vec::new(), Vec::new());
        for d in 0..ndump {
            for p in 0..nant {
                for q in (p + 1)..nant {
                    a1.push(p as u32);
                    a2.push(q as u32);
                    dump.push(d as u32);
                }
            }
        }
        (a1, a2, dump)
    }

    #[test]
    #[allow(clippy::needless_range_loop)]
    fn diag_residual_is_zero_on_the_model_corrupted_by_the_gains() {
        let (nant, nchan) = (4usize, 3usize);
        let (a1, a2, _) = layout(nant, 2);
        let nrow = a1.len();
        let tb: Vec<u32> = (0..nrow).map(|r| (r / 6) as u32).collect();
        let fb = vec![0u32, 0, 1];
        let (ntime, nfreq) = (2usize, 2usize);
        let mut seed = 7u64;
        let mut gains = vec![0.0f64; ntime * nfreq * nant * 2 * 2];
        for g in gains.iter_mut() {
            *g = 0.5 + lcg(&mut seed);
        }
        let mut model = vec![0.0f32; nrow * nchan * 8];
        for m in model.iter_mut() {
            *m = (lcg(&mut seed) - 0.5) as f32;
        }
        let mut data = vec![0.0f32; nrow * nchan * 8];
        for r in 0..nrow {
            for c in 0..nchan {
                for (h, k) in [(0usize, 0usize), (1, 3)] {
                    let gi = |a: u32| {
                        let i = (((tb[r] as usize * nfreq + fb[c] as usize) * nant + a as usize)
                            * 2
                            + h)
                            * 2;
                        (gains[i], gains[i + 1])
                    };
                    let (gp, gq) = (gi(a1[r]), gi(a2[r]));
                    let i = ((r * nchan + c) * 4 + k) * 2;
                    let (mr, mi) = (model[i] as f64, model[i + 1] as f64);
                    let ar = gp.0 * mr - gp.1 * mi;
                    let ai = gp.0 * mi + gp.1 * mr;
                    data[i] = (ar * gq.0 + ai * gq.1) as f32;
                    data[i + 1] = (ai * gq.0 - ar * gq.1) as f32;
                }
            }
        }
        let mut gflags = vec![0u8; ntime * nfreq * nant * 2];
        gflags[((nfreq + 1) * nant + 2) * 2 + 1] = 1; // time 1, bin 1, antenna 2, y
        let (res, bad) = diag_residual(
            &data, &model, nrow, nchan, &a1, &a2, &tb, &fb, &gains, &gflags, ntime, nfreq, nant,
        )
        .unwrap();
        assert!(res.iter().all(|v| v.abs() < 1e-6));
        for r in 0..nrow {
            for c in 0..nchan {
                let expect = tb[r] == 1 && fb[c] == 1 && (a1[r] == 2 || a2[r] == 2);
                assert_eq!(bad[r * nchan + c] == 1, expect, "row {r} chan {c}");
            }
        }
    }

    fn noise(nrow: usize, nchan: usize, seed: u64) -> Vec<f32> {
        let mut seed = seed;
        (0..nrow * nchan * 4)
            .map(|_| gauss(&mut seed) as f32)
            .collect()
    }

    fn settings(quartical: bool) -> SolverSettings {
        SolverSettings {
            quartical,
            sigma: 5.0,
            global_sigma: 10.0,
            persist: 3.0,
            block: 16,
            guard: 1.0,
            min_cells: 0,
        }
    }

    #[test]
    fn solver_flags_find_rfi_with_both_rules() {
        let (nant, nchan) = (8usize, 32usize);
        let (a1, a2, dump) = layout(nant, 30);
        let nrow = a1.len();
        for quartical in [true, false] {
            let mut res = noise(nrow, nchan, 11);
            let hits = [(5usize, 3usize), (40, 20), (300, 9)];
            for &(r, c) in &hits {
                res[(r * nchan + c) * 4] = 80.0;
            }
            let flag = vec![0u8; nrow * nchan];
            let (new, counts) = solver_flags(
                &res,
                &flag,
                nrow,
                nchan,
                &a1,
                &a2,
                &dump,
                nant,
                &settings(quartical),
            )
            .unwrap();
            for &(r, c) in &hits {
                assert_eq!(new[r * nchan + c], 1, "quartical {quartical}: ({r}, {c})");
            }
            assert!(counts.added < (nrow * nchan / 100) as u64, "{counts:?}");
            assert_eq!(counts.added, new.iter().map(|&v| v as u64).sum::<u64>());
        }
    }

    #[test]
    fn solver_flags_keep_input_flags_and_obey_guard_and_min_cells() {
        let (nant, nchan) = (6usize, 16usize);
        let (a1, a2, dump) = layout(nant, 20);
        let nrow = a1.len();
        let mut res = noise(nrow, nchan, 3);
        // Baseline (0, 1) is RFI over most of its cells; (0, 2) almost all flagged.
        let mut flag = vec![0u8; nrow * nchan];
        for r in 0..nrow {
            if a1[r] == 0 && a2[r] == 1 && dump[r] % 5 != 0 {
                for c in 0..nchan {
                    res[(r * nchan + c) * 4] = 200.0;
                }
            }
            if a1[r] == 0 && a2[r] == 2 {
                for c in 0..nchan {
                    if !(dump[r] == 0 && c < 4) {
                        flag[r * nchan + c] = 1;
                    }
                }
                res[(r * nchan) * 4] = 200.0;
            }
        }
        let mut s = settings(true);
        let (open, _) = solver_flags(&res, &flag, nrow, nchan, &a1, &a2, &dump, nant, &s).unwrap();
        let bl01: Vec<usize> = (0..nrow).filter(|&r| a1[r] == 0 && a2[r] == 1).collect();
        assert!(bl01.iter().any(|&r| open[r * nchan] == 1));
        for (i, &f) in flag.iter().enumerate() {
            if f != 0 {
                assert_eq!(open[i], 0, "an input flag is not new");
            }
        }
        s.guard = 0.5;
        s.min_cells = 5;
        let (new, counts) =
            solver_flags(&res, &flag, nrow, nchan, &a1, &a2, &dump, nant, &s).unwrap();
        assert!(
            bl01.iter()
                .all(|&r| new[r * nchan..(r + 1) * nchan].iter().all(|&v| v == 0))
        );
        for r in 0..nrow {
            if a1[r] == 0 && a2[r] == 2 {
                assert!(new[r * nchan..(r + 1) * nchan].iter().all(|&v| v == 0));
            }
        }
        assert!(counts.guarded_baselines >= 1, "{counts:?}");
        assert_eq!(counts.sparse_baselines, 1, "{counts:?}");
    }
}
