// SPDX-License-Identifier: MIT
//! The diagonal gain solve of `diag` streamed over its cells (issue #34,
//! `research/selfcal-memory.md`): for solution intervals too large to hold.
//!
//! The caller lists the unflagged cells of every interval once (as
//! `solve::data_flags` and `diag`'s `init_flags` select them), in the order
//! `diag` sweeps them: by row, then by channel. Each iteration then reads
//! them in blocks and adds each block to its intervals' sums
//! (`diag::accumulate_cells`), steps every gain (`diag::step_states`) and
//! applies the global stop test serially; `diag::finish` ends the solve.
//! An interval's sums see its cells in the sweep's order whatever the
//! blocks, and `diag::solve` gives the serial loop's result, so the
//! solution is `diag::solve`'s bit for bit. Only the cells of one block are
//! resident, whatever the length of an interval.

use super::diag::{self, CellRef, Error, FRESH, GainState, Kind, Settings, Snapshot, Solution};
use crate::fused::Model;
use crate::solve::Problem;
use rayon::prelude::*;
use std::io::{self, Read};
use std::path::Path;

/// 4-byte words of one cell record: interval, antenna 1, antenna 2, then
/// data (8, complex64 as float32 pairs), model (8) and weights (4).
pub const RECORD_WORDS: usize = 23;
/// Bytes of one cell record (little-endian words).
pub const RECORD_BYTES: usize = 4 * RECORD_WORDS;

/// Consecutive unflagged cells: `interval[i]` is cell i's solution interval
/// (`time bin * nfreq_bins + frequency bin`); the cell arrays hold 8, 8 and
/// 4 values per cell (four correlations).
#[derive(Default)]
pub struct Block {
    pub interval: Vec<u32>,
    pub antenna1: Vec<u32>,
    pub antenna2: Vec<u32>,
    pub data: Vec<f32>,
    pub model: Vec<f32>,
    pub weights: Vec<f32>,
}

impl Block {
    pub fn len(&self) -> usize {
        self.interval.len()
    }

    pub fn is_empty(&self) -> bool {
        self.interval.is_empty()
    }

    fn clear(&mut self) {
        self.interval.clear();
        self.antenna1.clear();
        self.antenna2.clear();
        self.data.clear();
        self.model.clear();
        self.weights.clear();
    }

    /// Append the records in `bytes` (a whole number of records).
    pub fn extend_from_records(&mut self, bytes: &[u8]) {
        let word = |r: &[u8], k: usize| [r[4 * k], r[4 * k + 1], r[4 * k + 2], r[4 * k + 3]];
        for r in bytes.chunks_exact(RECORD_BYTES) {
            self.interval.push(u32::from_le_bytes(word(r, 0)));
            self.antenna1.push(u32::from_le_bytes(word(r, 1)));
            self.antenna2.push(u32::from_le_bytes(word(r, 2)));
            self.data
                .extend((3..11).map(|k| f32::from_le_bytes(word(r, k))));
            self.model
                .extend((11..19).map(|k| f32::from_le_bytes(word(r, k))));
            self.weights
                .extend((19..23).map(|k| f32::from_le_bytes(word(r, k))));
        }
    }
}

/// The failures of a streamed solve.
#[derive(Debug)]
pub enum StreamError {
    Solve(Error),
    Io(io::Error),
}

impl std::fmt::Display for StreamError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            StreamError::Solve(e) => write!(f, "{e}"),
            StreamError::Io(e) => write!(f, "reading the cell stream: {e}"),
        }
    }
}

impl From<Error> for StreamError {
    fn from(e: Error) -> Self {
        StreamError::Solve(e)
    }
}

impl From<io::Error> for StreamError {
    fn from(e: io::Error) -> Self {
        StreamError::Io(e)
    }
}

/// A source of the cells, passed over once per iteration.
pub trait CellSource {
    /// Call `visit` on consecutive blocks of every cell, in order.
    fn pass(&mut self, visit: &mut dyn FnMut(&Block)) -> Result<(), StreamError>;
}

/// Cells held in memory, handed out in blocks of `block` cells (tests).
pub struct Blocks {
    pub cells: Block,
    pub block: usize,
}

impl CellSource for Blocks {
    fn pass(&mut self, visit: &mut dyn FnMut(&Block)) -> Result<(), StreamError> {
        let n = self.cells.len();
        let step = self.block.max(1);
        let mut piece = Block::default();
        for start in (0..n).step_by(step) {
            let end = (start + step).min(n);
            piece.clear();
            piece
                .interval
                .extend_from_slice(&self.cells.interval[start..end]);
            piece
                .antenna1
                .extend_from_slice(&self.cells.antenna1[start..end]);
            piece
                .antenna2
                .extend_from_slice(&self.cells.antenna2[start..end]);
            piece
                .data
                .extend_from_slice(&self.cells.data[8 * start..8 * end]);
            piece
                .model
                .extend_from_slice(&self.cells.model[8 * start..8 * end]);
            piece
                .weights
                .extend_from_slice(&self.cells.weights[4 * start..4 * end]);
            visit(&piece);
        }
        Ok(())
    }
}

/// Cell records in a file (`RECORD_BYTES` each), read in blocks of `block`
/// records on every pass.
pub struct RecordFile<'a> {
    pub path: &'a Path,
    pub ncells: usize,
    pub block: usize,
}

impl CellSource for RecordFile<'_> {
    fn pass(&mut self, visit: &mut dyn FnMut(&Block)) -> Result<(), StreamError> {
        let mut file = io::BufReader::with_capacity(1 << 20, std::fs::File::open(self.path)?);
        let step = self.block.max(1);
        let mut bytes = vec![0u8; step.min(self.ncells.max(1)) * RECORD_BYTES];
        let mut piece = Block::default();
        let mut left = self.ncells;
        while left > 0 {
            let n = step.min(left);
            file.read_exact(&mut bytes[..n * RECORD_BYTES])?;
            piece.clear();
            piece.extend_from_records(&bytes[..n * RECORD_BYTES]);
            visit(&piece);
            left -= n;
        }
        Ok(())
    }
}

/// Add one block to its intervals' sums (`width` gains per interval).
fn accumulate_block(
    block: &Block,
    kind: Kind,
    nant: usize,
    width: usize,
    states: &mut [GainState],
    bad: &mut Option<Error>,
) {
    let n = block.len();
    if n == 0 || bad.is_some() {
        return;
    }
    let nintervals = states.len() / width;
    // The block's cells grouped by interval, each group in stream order.
    let mut start = vec![0usize; nintervals + 1];
    for &k in &block.interval {
        let k = k as usize;
        if k >= nintervals {
            *bad = Some(Error::Shape("cell interval out of range"));
            return;
        }
        start[k + 1] += 1;
    }
    if block
        .antenna1
        .iter()
        .chain(&block.antenna2)
        .any(|&a| a as usize >= nant)
    {
        *bad = Some(Error::Shape("cell antenna out of range"));
        return;
    }
    let mut total = 0;
    for s in start.iter_mut() {
        total += *s;
        *s = total;
    }
    let mut next = start.clone();
    let mut cells: Vec<CellRef> = (0..n)
        .map(|_| CellRef {
            cell: 0,
            p: 0,
            q: 0,
        })
        .collect();
    for (i, &k) in block.interval.iter().enumerate() {
        let at = &mut next[k as usize];
        cells[*at] = CellRef {
            cell: i,
            p: block.antenna1[i],
            q: block.antenna2[i],
        };
        *at += 1;
    }
    // One channel per cell: the model of cell i is its own (`model_at`).
    let problem = Problem {
        nrow: n,
        nchan: 1,
        ntime_bins: 1,
        nfreq_bins: 1,
        nant,
        data: &block.data,
        weights: &block.weights,
        model: Model::Stored(&block.model),
        flag: &[],
        flag_row: &[],
        antenna1: &block.antenna1,
        antenna2: &block.antenna2,
        time_bin: &[],
        freq_bin: &[],
    };
    states
        .par_chunks_mut(width)
        .enumerate()
        .for_each(|(k, chunk)| {
            let group = &cells[start[k]..start[k + 1]];
            if !group.is_empty() {
                diag::accumulate_cells(&problem, kind, group, chunk);
            }
        });
}

/// Solve one diagonal term over `source`'s cells: `ntime_bins *
/// nfreq_bins` intervals of `nant` gains; `live[g]` true for a gain an
/// unflagged cell involves (`diag`'s `init_flags`). The result equals
/// `diag::solve` on the problem whose unflagged cells `source` lists.
pub fn solve(
    source: &mut dyn CellSource,
    ntime_bins: usize,
    nfreq_bins: usize,
    nant: usize,
    live: &[bool],
    settings: &Settings,
) -> Result<Solution, StreamError> {
    let ngains = ntime_bins * nfreq_bins * nant;
    if live.len() != ngains {
        return Err(Error::Shape("live must hold one value per gain").into());
    }
    if let Some(r) = settings.reference_antenna
        && r >= nant
    {
        return Err(Error::Settings("reference antenna out of range").into());
    }
    if !(settings.stop_criterion.is_finite() && settings.stop_fraction.is_finite()) {
        return Err(Error::Settings("stop criterion and fraction must be finite").into());
    }
    let width = nant.max(1);
    let mut states = vec![FRESH; ngains];
    for (state, &l) in states.iter_mut().zip(live) {
        if l {
            state.set_live();
        }
    }
    let stop2 = settings.stop_criterion * settings.stop_criterion;
    let kind = settings.kind;
    let iterations = settings.max_iterations.max(1);
    let (mut done, mut fraction) = (0, 0.);
    for k in 0..iterations {
        diag::reset_sums(&mut states);
        let mut bad = None;
        source.pass(&mut |block| {
            accumulate_block(block, kind, nant, width, &mut states, &mut bad);
        })?;
        if let Some(e) = bad {
            return Err(e.into());
        }
        let counts: Vec<Result<(usize, usize), Error>> = states
            .par_chunks_mut(width)
            .map(|chunk| diag::step_states(chunk, kind, k, stop2))
            .collect();
        let (mut c, mut x) = (0, 0);
        for r in counts {
            let (a, b) = r?;
            c += a;
            x += b;
        }
        fraction = diag::converged_fraction(c, x, ngains);
        done = k + 1;
        if fraction >= settings.stop_fraction {
            break;
        }
    }
    let snapshots = states.iter().map(Snapshot::of).collect();
    Ok(diag::finish(snapshots, width, settings, done, fraction))
}

/// `solve` over a record file (`RecordFile`).
#[allow(clippy::too_many_arguments)]
pub fn solve_file(
    path: &Path,
    ncells: usize,
    block: usize,
    ntime_bins: usize,
    nfreq_bins: usize,
    nant: usize,
    live: &[bool],
    settings: &Settings,
) -> Result<Solution, StreamError> {
    let mut source = RecordFile {
        path,
        ncells,
        block,
    };
    solve(&mut source, ntime_bins, nfreq_bins, nant, live, settings)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(state: &mut u64) -> f64 {
        *state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*state >> 11) as f64) / ((1u64 << 53) as f64) - 0.5
    }

    struct Case {
        nrow: usize,
        nchan: usize,
        ntime: usize,
        nfreq: usize,
        nant: usize,
        data: Vec<f32>,
        model: Vec<f32>,
        weights: Vec<f32>,
        flag: Vec<u8>,
        flag_row: Vec<u8>,
        a1: Vec<u32>,
        a2: Vec<u32>,
        tb: Vec<u32>,
        fb: Vec<u32>,
    }

    /// Random data on `nant` antennas (the last one without data), with
    /// flags, zero weights, zero data and a non-zero cross-hand model.
    fn case(nant: usize, ntime: usize, nchan: usize, nfreq: usize, seed: u64) -> Case {
        let mut s = seed;
        let mut a1 = Vec::new();
        let mut a2 = Vec::new();
        let mut tb = Vec::new();
        for t in 0..ntime {
            for _dump in 0..3 {
                for p in 0..nant - 1 {
                    for q in p..nant - 1 {
                        a1.push(p as u32);
                        a2.push(q as u32);
                        tb.push(t as u32);
                    }
                }
            }
        }
        let nrow = a1.len();
        let cells = nrow * nchan;
        let mut data = vec![0f32; 8 * cells];
        let mut model = vec![0f32; 8 * cells];
        let mut weights = vec![0f32; 4 * cells];
        let mut flag = vec![0u8; 4 * cells];
        for c in 0..cells {
            for k in 0..8 {
                model[8 * c + k] = (lcg(&mut s) + if k == 0 || k == 6 { 1.0 } else { 0.0 }) as f32;
                data[8 * c + k] = (model[8 * c + k] as f64 * 1.3 + 0.2 * lcg(&mut s)) as f32;
            }
            for k in 0..4 {
                weights[4 * c + k] = (1.0 + lcg(&mut s)) as f32;
            }
            let u = lcg(&mut s);
            if u < -0.45 {
                flag[4 * c + 1] = 1;
            } else if u < -0.42 {
                weights[4 * c + 3] = 0.;
            } else if u < -0.40 {
                data[8 * c] = 0.;
                data[8 * c + 1] = 0.;
            }
        }
        // rang.cal_gain flags the autocorrelations as rows before the kernel.
        let mut flag_row: Vec<u8> = a1.iter().zip(&a2).map(|(p, q)| u8::from(p == q)).collect();
        flag_row[nrow / 3] = 1;
        let fb = (0..nchan).map(|c| (c * nfreq / nchan) as u32).collect();
        Case {
            nrow,
            nchan,
            ntime,
            nfreq,
            nant,
            data,
            model,
            weights,
            flag,
            flag_row,
            a1,
            a2,
            tb,
            fb,
        }
    }

    fn problem(c: &Case) -> Problem<'_> {
        Problem {
            nrow: c.nrow,
            nchan: c.nchan,
            ntime_bins: c.ntime,
            nfreq_bins: c.nfreq,
            nant: c.nant,
            data: &c.data,
            weights: &c.weights,
            model: Model::Stored(&c.model),
            flag: &c.flag,
            flag_row: &c.flag_row,
            antenna1: &c.a1,
            antenna2: &c.a2,
            time_bin: &c.tb,
            freq_bin: &c.fb,
        }
    }

    /// The unflagged cells in sweep order and the live gains.
    fn stream(c: &Case) -> (Block, Vec<bool>) {
        let p = problem(c);
        let flagged = crate::solve::data_flags(&p);
        let mut b = Block::default();
        let mut live = vec![false; c.ntime * c.nfreq * c.nant];
        for row in 0..c.nrow {
            for chan in 0..c.nchan {
                let cell = row * c.nchan + chan;
                if flagged[cell] {
                    continue;
                }
                let k = c.tb[row] as usize * c.nfreq + c.fb[chan] as usize;
                b.interval.push(k as u32);
                b.antenna1.push(c.a1[row]);
                b.antenna2.push(c.a2[row]);
                b.data.extend_from_slice(&c.data[8 * cell..8 * cell + 8]);
                b.model.extend_from_slice(&c.model[8 * cell..8 * cell + 8]);
                b.weights
                    .extend_from_slice(&c.weights[4 * cell..4 * cell + 4]);
                live[k * c.nant + c.a1[row] as usize] = true;
                live[k * c.nant + c.a2[row] as usize] = true;
            }
        }
        (b, live)
    }

    fn records(b: &Block) -> Vec<u8> {
        let mut out = Vec::with_capacity(b.len() * RECORD_BYTES);
        for i in 0..b.len() {
            for w in [b.interval[i], b.antenna1[i], b.antenna2[i]] {
                out.extend_from_slice(&w.to_le_bytes());
            }
            for v in b.data[8 * i..8 * i + 8]
                .iter()
                .chain(&b.model[8 * i..8 * i + 8])
                .chain(&b.weights[4 * i..4 * i + 4])
            {
                out.extend_from_slice(&v.to_le_bytes());
            }
        }
        out
    }

    fn same(a: &Solution, b: &Solution) {
        assert_eq!(a.iterations, b.iterations);
        assert_eq!(
            a.converged_fraction.to_bits(),
            b.converged_fraction.to_bits()
        );
        assert_eq!(a.flags, b.flags);
        for (x, y) in a.gains.iter().flatten().zip(b.gains.iter().flatten()) {
            assert_eq!(x.re.to_bits(), y.re.to_bits());
            assert_eq!(x.im.to_bits(), y.im.to_bits());
        }
    }

    #[test]
    fn streamed_equals_whole_at_every_block_size() {
        for (kind, seed) in [(Kind::DiagComplex, 3), (Kind::Phase, 5)] {
            for (ntime, nchan, nfreq) in [(1, 6, 1), (3, 8, 2), (2, 5, 5)] {
                let c = case(6, ntime, nchan, nfreq, seed);
                let settings = Settings::new(kind);
                let whole = diag::solve(&problem(&c), &settings).expect("whole solve");
                assert!(whole.flags.contains(&1)); // the antenna without data
                let (cells, live) = stream(&c);
                for block in [1, 7, 64, cells.len()] {
                    let mut source = Blocks {
                        cells: Block {
                            interval: cells.interval.clone(),
                            antenna1: cells.antenna1.clone(),
                            antenna2: cells.antenna2.clone(),
                            data: cells.data.clone(),
                            model: cells.model.clone(),
                            weights: cells.weights.clone(),
                        },
                        block,
                    };
                    let s = solve(&mut source, c.ntime, c.nfreq, c.nant, &live, &settings)
                        .expect("streamed solve");
                    same(&whole, &s);
                }
            }
        }
    }

    #[test]
    fn record_file_round_trips() {
        let c = case(5, 2, 4, 1, 11);
        let (cells, live) = stream(&c);
        let dir = std::env::temp_dir().join(format!("rang-diag-stream-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("cells.bin");
        std::fs::write(&path, records(&cells)).unwrap();
        let settings = Settings::new(Kind::DiagComplex);
        let whole = diag::solve(&problem(&c), &settings).unwrap();
        let s = solve_file(
            &path,
            cells.len(),
            13,
            c.ntime,
            c.nfreq,
            c.nant,
            &live,
            &settings,
        )
        .unwrap();
        same(&whole, &s);
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn a_short_file_is_an_io_error() {
        let dir = std::env::temp_dir().join(format!("rang-diag-short-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("cells.bin");
        std::fs::write(&path, vec![0u8; RECORD_BYTES]).unwrap();
        let settings = Settings::new(Kind::Phase);
        let r = solve_file(&path, 2, 4, 1, 1, 2, &[true, true], &settings);
        assert!(matches!(r, Err(StreamError::Io(_))));
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
