// SPDX-License-Identifier: GPL-3.0-or-later
// Follows CASA's FlagAgentExtension.cc (Copyright (C) Associated
// Universities, Inc. Washington DC, USA 2011; Copyright (C) European
// Southern Observatory, 2011; LGPL-2.1 or later): notices in
// THIRD-PARTY-NOTICES.txt.
//! CASA's `flagdata(mode='extend')` on one flag cube per (chunk, baseline)
//! segment (task E0, `research/e0-refant-extend.md` section 1.3), as
//! `FlagAgentExtension::computeAntennaPairFlags` in CASA's flagging code:
//! grow flags around (near time, near frequency, more than four flagged
//! neighbours), then extend across frequency and time by the `growfreq` and
//! `growtime` percentages, then across correlations. The chunking (CASA's
//! 60 s `MSInterval` chunks) is the caller's (`rang.flag_extend`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Flags are `(row, chan, corr)` bytes (0 or 1), the Measurement Set's cell
//! order. A segment is a list of row indices in time order; its time axis is
//! those rows, so a missing integration is skipped, as in CASA.

use rayon::prelude::*;

/// The rule settings of `flagdata` mode `extend`.
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    /// Percentage of rows flagged in a channel above which the channel is
    /// flagged in every row (0: off).
    pub growtime: f64,
    /// Percentage of channels flagged in a row above which the row is
    /// flagged in every channel (0: off).
    pub growfreq: f64,
    pub growaround: bool,
    pub flagneartime: bool,
    pub flagnearfreq: bool,
    pub extendpols: bool,
}

/// Cells each rule turned from unflagged to flagged. The three growth rules
/// of step 1 are applied together, so a cell two of them mark counts for
/// both; `grown` counts each such cell once.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Counts {
    pub neartime: u64,
    pub nearfreq: u64,
    pub growaround: u64,
    pub grown: u64,
    pub growfreq: u64,
    pub growtime: u64,
    pub extendpols: u64,
}

impl Counts {
    fn add(&mut self, o: &Counts) {
        self.neartime += o.neartime;
        self.nearfreq += o.nearfreq;
        self.growaround += o.growaround;
        self.grown += o.grown;
        self.growfreq += o.growfreq;
        self.growtime += o.growtime;
        self.extendpols += o.extendpols;
    }
}

/// Extend one segment's cube `f`, `(time, chan, pol)` row-major.
pub fn extend_cube(f: &mut [u8], nt: usize, nchan: usize, npol: usize, s: &Settings) -> Counts {
    let at = |t: usize, c: usize, p: usize| (t * nchan + c) * npol + p;
    let mut n = Counts::default();
    // STEP 1: grow into separate cubes (padded by one on the time and
    // channel axes), every test reading the flags as they were.
    if s.flagneartime || s.flagnearfreq || s.growaround {
        let (pt, pc) = (nt + 2, nchan + 2);
        let gat = |t: usize, c: usize, p: usize| (t * pc + c) * npol + p;
        let mut by_time = vec![false; pt * pc * npol];
        let mut by_freq = vec![false; pt * pc * npol];
        let mut by_around = vec![false; pt * pc * npol];
        for t in 0..nt {
            for c in 0..nchan {
                for p in 0..npol {
                    if f[at(t, c, p)] != 0 {
                        if s.flagneartime {
                            by_time[gat(t + 2, c + 1, p)] = true;
                            by_time[gat(t, c + 1, p)] = true;
                        }
                        if s.flagnearfreq {
                            by_freq[gat(t + 1, c + 2, p)] = true;
                            by_freq[gat(t + 1, c, p)] = true;
                        }
                    } else if s.growaround {
                        let mut around = 0u32;
                        for ti in t.saturating_sub(1)..=(t + 1).min(nt - 1) {
                            for ci in c.saturating_sub(1)..=(c + 1).min(nchan - 1) {
                                around += u32::from(f[at(ti, ci, p)] != 0);
                            }
                        }
                        if around > 4 {
                            by_around[gat(t + 1, c + 1, p)] = true;
                        }
                    }
                }
            }
        }
        for t in 0..nt {
            for c in 0..nchan {
                for p in 0..npol {
                    let g = gat(t + 1, c + 1, p);
                    let i = at(t, c, p);
                    if f[i] == 0 {
                        n.neartime += u64::from(by_time[g]);
                        n.nearfreq += u64::from(by_freq[g]);
                        n.growaround += u64::from(by_around[g]);
                    }
                    if by_time[g] || by_freq[g] || by_around[g] {
                        n.grown += u64::from(f[i] == 0);
                        f[i] = 1;
                    }
                }
            }
        }
    }
    // STEP 2: both counts first, then frequency, then time.
    if s.growtime > 0.0 || s.growfreq > 0.0 {
        let mut acc_time = vec![0f64; npol * nt];
        let mut acc_freq = vec![0f64; npol * nchan];
        for t in 0..nt {
            for c in 0..nchan {
                for p in 0..npol {
                    let v = f64::from(f[at(t, c, p)]);
                    acc_time[p * nt + t] += v;
                    acc_freq[p * nchan + c] += v;
                }
            }
        }
        if s.growfreq > 0.0 {
            for t in 0..nt {
                for p in 0..npol {
                    if 100.0 * acc_time[p * nt + t] / nchan as f64 >= s.growfreq {
                        for c in 0..nchan {
                            let i = at(t, c, p);
                            n.growfreq += u64::from(f[i] == 0);
                            f[i] = 1;
                        }
                    }
                }
            }
        }
        if s.growtime > 0.0 {
            for c in 0..nchan {
                for p in 0..npol {
                    if 100.0 * acc_freq[p * nchan + c] / nt as f64 >= s.growtime {
                        for t in 0..nt {
                            let i = at(t, c, p);
                            n.growtime += u64::from(f[i] == 0);
                            f[i] = 1;
                        }
                    }
                }
            }
        }
    }
    // STEP 3: across correlations.
    if s.extendpols {
        for t in 0..nt {
            for c in 0..nchan {
                let base = at(t, c, 0);
                if f[base..base + npol].iter().any(|&v| v != 0) {
                    for v in &mut f[base..base + npol] {
                        n.extendpols += u64::from(*v == 0);
                        *v = 1;
                    }
                }
            }
        }
    }
    n
}

/// Extend `flag` (`(nrow, nchan, npol)` bytes) in place: segment `k` is
/// the rows `order[starts[k]..starts[k + 1]]`, in time order. Segments must
/// not share rows. Segments run in parallel; the result does not depend on
/// the thread count.
pub fn extend(
    flag: &mut [u8],
    nchan: usize,
    npol: usize,
    order: &[u64],
    starts: &[u64],
    s: &Settings,
) -> Result<Counts, String> {
    let cell = nchan * npol;
    if cell == 0 || !flag.len().is_multiple_of(cell) {
        return Err(format!(
            "flag holds {} bytes, not rows of {cell}",
            flag.len()
        ));
    }
    let nrow = flag.len() / cell;
    if starts.is_empty() || starts[0] != 0 || *starts.last().unwrap() as usize != order.len() {
        return Err("starts must run from 0 to len(order)".into());
    }
    if starts.windows(2).any(|w| w[1] <= w[0]) {
        return Err("starts must increase (no empty segment)".into());
    }
    let mut seen = vec![false; nrow];
    for &r in order {
        let r = r as usize;
        if r >= nrow {
            return Err(format!("row {r} outside the {nrow} rows of flag"));
        }
        if seen[r] {
            return Err(format!("row {r} is in two segments"));
        }
        seen[r] = true;
    }
    let src: &[u8] = flag;
    let results: Vec<(Vec<u8>, Counts)> = starts
        .par_windows(2)
        .map(|w| {
            let rows = &order[w[0] as usize..w[1] as usize];
            let mut cube = Vec::with_capacity(rows.len() * cell);
            for &r in rows {
                let r = r as usize;
                cube.extend_from_slice(&src[r * cell..(r + 1) * cell]);
            }
            let counts = extend_cube(&mut cube, rows.len(), nchan, npol, s);
            (cube, counts)
        })
        .collect();
    let mut total = Counts::default();
    for (w, (cube, counts)) in starts.windows(2).zip(results) {
        let rows = &order[w[0] as usize..w[1] as usize];
        for (k, &r) in rows.iter().enumerate() {
            let r = r as usize;
            flag[r * cell..(r + 1) * cell].copy_from_slice(&cube[k * cell..(k + 1) * cell]);
        }
        total.add(&counts);
    }
    Ok(total)
}

#[cfg(test)]
mod tests {
    use super::*;

    const CARACAL: Settings = Settings {
        growtime: 80.0,
        growfreq: 80.0,
        growaround: true,
        flagneartime: true,
        flagnearfreq: true,
        extendpols: true,
    };
    const NONE: Settings = Settings {
        growtime: 0.0,
        growfreq: 0.0,
        growaround: false,
        flagneartime: false,
        flagnearfreq: false,
        extendpols: false,
    };

    #[test]
    fn near_time_and_frequency() {
        let (nt, nc) = (5, 5);
        let mut f = vec![0u8; nt * nc];
        f[2 * nc + 2] = 1;
        let s = Settings {
            flagneartime: true,
            flagnearfreq: true,
            ..NONE
        };
        let n = extend_cube(&mut f, nt, nc, 1, &s);
        let set: Vec<usize> = (0..nt * nc).filter(|&i| f[i] == 1).collect();
        assert_eq!(set, vec![7, 11, 12, 13, 17]);
        assert_eq!((n.neartime, n.nearfreq, n.grown), (2, 2, 4));
    }

    #[test]
    fn grow_around_needs_more_than_four() {
        // A cross of five: every unflagged corner sees three flagged cells.
        let (nt, nc) = (3, 3);
        let mut f = vec![0u8, 1, 0, 1, 1, 1, 0, 1, 0];
        let s = Settings {
            growaround: true,
            ..NONE
        };
        assert_eq!(extend_cube(&mut f, nt, nc, 1, &s).growaround, 0);
        // The centre (1, 1) sees five flagged neighbours.
        let mut g = vec![1u8, 1, 1, 1, 0, 1, 0, 0, 0];
        assert_eq!(extend_cube(&mut g, nt, nc, 1, &s).growaround, 1);
        assert_eq!(g[4], 1);
    }

    #[test]
    fn grow_counts_are_taken_before_either_extension() {
        // Row 0 is 80 % flagged in frequency; channel 4 is not >= 80 % in time
        // before the frequency extension, so it stays as it was.
        let (nt, nc) = (5, 5);
        let mut f = vec![0u8; nt * nc];
        for v in f.iter_mut().take(4) {
            *v = 1;
        }
        f[nc + 4] = 1;
        f[2 * nc + 4] = 1;
        f[3 * nc + 4] = 1;
        let s = Settings {
            growtime: 80.0,
            growfreq: 80.0,
            ..NONE
        };
        let n = extend_cube(&mut f, nt, nc, 1, &s);
        assert_eq!(n.growfreq, 1); // (0, 4)
        assert_eq!(n.growtime, 0); // channel 4 had 3 of 5 = 60 %
        assert_eq!(f[4 * nc + 4], 0);
    }

    #[test]
    fn extend_pols_and_segments() {
        let (nc, np) = (2, 4);
        let mut flag = vec![0u8; 3 * nc * np];
        flag[np + 1] = 1; // row 0, chan 1, pol 1
        let s = Settings {
            extendpols: true,
            ..NONE
        };
        let n = extend(&mut flag, nc, np, &[2, 0, 1], &[0, 1, 3], &s).unwrap();
        assert_eq!(n.extendpols, 3);
        assert_eq!(&flag[np..2 * np], &[1, 1, 1, 1]);
        assert!(extend(&mut flag, nc, np, &[0, 0], &[0, 2], &s).is_err());
    }

    #[test]
    fn caracal_settings_on_a_burst() {
        let (nt, nc, np) = (6, 10, 2);
        let mut f = vec![0u8; nt * nc * np];
        // One time row 90 % flagged in pol 0.
        for c in 0..9 {
            f[(2 * nc + c) * np] = 1;
        }
        let n = extend_cube(&mut f, nt, nc, np, &CARACAL);
        assert!(n.grown > 0 && n.extendpols > 0);
        for c in 0..nc {
            assert_eq!(f[(2 * nc + c) * np + 1], 1);
        }
    }
}
