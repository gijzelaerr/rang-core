//! Model visibilities from model images, and the model column of a
//! Measurement Set (task G6, `research/g6-predict.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! As WSClean 3.7 does after a clean and with `-predict`: the model images
//! (`<name>-model.fits`, or `<name>-000k-model.fits` per output channel) are
//! predicted with the gridder's `dirty2vis`, without weights or mask, at the
//! Measurement Set's own channel frequencies, into every selected row (the
//! field and data description, cross-correlations; flags play no part).
//! Under `-pol I` on linear feeds the model column gets `XX = YY = I` and
//! `XY = YX = 0`. Channels outside `-channel-range` keep their values, as do
//! rows outside the selection; a column added here starts at zero in every
//! row (WSClean's `FillModelColumn`), laid out as W1's `ensure_column` lays
//! it out (TiledShapeStMan, DATA's comment).
//!
//! The selected rows are predicted in fixed blocks ([`block_rows`]), so that
//! the binary and `rang-core image` (through the extension) give the same
//! bits: the gridder's plan depends on the rows of a call.

use super::fits;
use super::input::{self, Selection};
use super::spectral;
use crate::ms::DataType;
use crate::ms_write::{NewColumn, NewManager, TableWriter};
use crate::wgridder::{self, Options, Real};
use rayon::prelude::*;
use rustfft::num_complex::Complex;
use std::path::{Path, PathBuf};

/// Cells (rows × channels) predicted per gridder call.
pub const BLOCK_CELLS: usize = 1 << 27;
/// Bytes of complex64 cells per written chunk (W1's `CHUNK_BYTES`).
pub const CHUNK_BYTES: usize = 64 << 20;
/// Bytes per tile of an added column (W1's `TILE_BYTES`).
pub const TILE_BYTES: usize = 1 << 20;

/// Selected rows per gridder call for `nchan` channels.
pub fn block_rows(nchan: usize) -> usize {
    (BLOCK_CELLS / nchan.max(1)).max(1)
}

/// Rows per written chunk: about [`CHUNK_BYTES`] of complex64 cells, a
/// multiple of 64 rows (W1's `chunk_rows_for`).
pub fn chunk_rows(cells_per_row: usize) -> usize {
    let rows = CHUNK_BYTES / (cells_per_row.max(1) * 8);
    (rows / 64 * 64).max(64)
}

/// The model image files WSClean's `-predict` reads.
pub fn model_paths(name: &str, channels_out: usize) -> Vec<PathBuf> {
    if channels_out <= 1 {
        vec![PathBuf::from(format!("{name}-model.fits"))]
    } else {
        (0..channels_out)
            .map(|k| PathBuf::from(format!("{name}-{k:04}-model.fits")))
            .collect()
    }
}

/// One model image in the gridder's layout (`pixels[x * n + y]`).
#[derive(Clone, Debug)]
pub struct ModelImage {
    pub path: PathBuf,
    pub n: usize,
    /// Pixel size in radians (`CDELT2`).
    pub scale: f64,
    /// `CRVAL1`, `CRVAL2` in radians.
    pub centre: (f64, f64),
    pub pixels: Vec<f64>,
}

fn card<'a>(cards: &'a fits::RawCards, key: &str) -> Option<&'a str> {
    cards
        .iter()
        .find(|(k, _)| k == key)
        .map(|(_, v)| v.as_str())
}

fn float(cards: &fits::RawCards, key: &str, path: &Path) -> Result<f64, String> {
    let text = card(cards, key).ok_or_else(|| format!("{}: no {key}", path.display()))?;
    text.trim()
        .replace(['D', 'd'], "E")
        .parse::<f64>()
        .map_err(|_| format!("{}: {key} = {text:?} is not a number", path.display()))
}

/// Read a model image written by gemclean or WSClean (a square SIN image of
/// one frequency and one Stokes plane, BITPIX −32 or −64).
pub fn read_model(path: &Path) -> Result<ModelImage, String> {
    let (cards, data) = fits::read(path)?;
    let n = float(&cards, "NAXIS1", path)? as usize;
    if float(&cards, "NAXIS2", path)? as usize != n || n < 2 {
        return Err(format!(
            "{}: the model image must be square",
            path.display()
        ));
    }
    for axis in ["NAXIS3", "NAXIS4"] {
        if card(&cards, axis).is_some() && float(&cards, axis, path)? != 1.0 {
            return Err(format!(
                "{}: {axis} must be 1 (one frequency and one Stokes plane)",
                path.display()
            ));
        }
    }
    for (key, want) in [("CTYPE1", "RA---SIN"), ("CTYPE2", "DEC--SIN")] {
        if card(&cards, key).map(str::trim) != Some(want) {
            return Err(format!("{}: {key} must be {want}", path.display()));
        }
    }
    for (key, want) in [("BSCALE", 1.0), ("BZERO", 0.0)] {
        if card(&cards, key).is_some() && float(&cards, key, path)? != want {
            return Err(format!("{}: {key} must be {want}", path.display()));
        }
    }
    let cdelt1 = float(&cards, "CDELT1", path)?;
    let cdelt2 = float(&cards, "CDELT2", path)?;
    if cdelt2.is_nan() || cdelt2 <= 0.0 || ((cdelt1 + cdelt2) / cdelt2).abs() > 1e-12 {
        return Err(format!(
            "{}: CDELT1 = {cdelt1}, CDELT2 = {cdelt2}: square pixels with RA \
             increasing to the left are needed",
            path.display()
        ));
    }
    let centre = (n / 2 + 1) as f64;
    for key in ["CRPIX1", "CRPIX2"] {
        if float(&cards, key, path)? != centre {
            return Err(format!(
                "{}: {key} must be {centre} (the phase centre at pixel n/2)",
                path.display()
            ));
        }
    }
    let ra = float(&cards, "CRVAL1", path)?.to_radians();
    let dec = float(&cards, "CRVAL2", path)?.to_radians();
    if data.len() != n * n {
        return Err(format!(
            "{}: {} pixels, not {n}²",
            path.display(),
            data.len()
        ));
    }
    // `fits::gridder_to_fits` is a transpose, its own inverse.
    let pixels = fits::gridder_to_fits(n, &data);
    Ok(ModelImage {
        path: path.to_path_buf(),
        n,
        scale: cdelt2.to_radians(),
        centre: (ra, dec),
        pixels,
    })
}

fn angle_gap(a: f64, b: f64) -> f64 {
    let d = (a - b).rem_euclid(std::f64::consts::TAU);
    d.min(std::f64::consts::TAU - d)
}

/// The output channel of each channel of the MS (in its order), as the
/// imaging groups them: `-channel-range` on the channels in ascending
/// frequency, then `-average-channels`, then the `-channels-out` groups of
/// the averaged channels; None outside the range.
pub fn channel_map(
    freq: &[f64],
    range: Option<(usize, usize)>,
    average: usize,
    channels_out: usize,
) -> Result<Vec<Option<usize>>, String> {
    let keep = spectral::channel_groups(freq, range, 1)?.remove(0);
    let a = average.max(1);
    let averaged: Vec<&[usize]> = keep.chunks(a).collect();
    let mean: Vec<f64> = averaged
        .iter()
        .map(|g| g.iter().map(|&c| freq[c]).sum::<f64>() / g.len() as f64)
        .collect();
    let groups = spectral::channel_groups(&mean, None, channels_out)?;
    let mut out = vec![None; freq.len()];
    for (k, group) in groups.iter().enumerate() {
        for &j in group {
            for &c in averaged[j] {
                out[c] = Some(k);
            }
        }
    }
    Ok(out)
}

/// Model images and how the channels of the MS map onto them.
#[derive(Clone, Debug)]
pub struct Predictor {
    pub models: Vec<ModelImage>,
    /// Output channel of each channel of the MS (None: not predicted).
    pub map: Vec<Option<usize>>,
    pub opts: Options,
    pub single: bool,
}

impl Predictor {
    /// `models` in output-channel order; the gridder's options are those of
    /// gemclean's measurement (`flip_v`, `flip_w`, accuracy, w-term).
    pub fn new(
        models: Vec<ModelImage>,
        map: Vec<Option<usize>>,
        epsilon: f64,
        wgridding: bool,
        single: bool,
    ) -> Result<Predictor, String> {
        let first = models.first().ok_or("no model image")?;
        for m in &models[1..] {
            if m.n != first.n
                || m.scale != first.scale
                || angle_gap(m.centre.0, first.centre.0) > 1e-9
                || (m.centre.1 - first.centre.1).abs() > 1e-9
            {
                return Err(format!(
                    "{} and {} differ in size, scale or centre",
                    first.path.display(),
                    m.path.display()
                ));
            }
        }
        let used = map.iter().flatten().copied().max().map_or(0, |k| k + 1);
        if used != models.len() {
            return Err(format!(
                "{} model images for {used} output channels",
                models.len()
            ));
        }
        let opts = Options {
            nx: first.n,
            ny: first.n,
            pixsize_x: first.scale,
            pixsize_y: first.scale,
            epsilon,
            do_wgridding: wgridding,
            flip_v: true,
            flip_w: true,
            ..Options::default()
        };
        Ok(Predictor {
            models,
            map,
            opts,
            single,
        })
    }

    /// Read `name`'s model images and map the channels `freq` onto them.
    #[allow(clippy::too_many_arguments)]
    pub fn from_files(
        name: &str,
        freq: &[f64],
        channels_out: usize,
        range: Option<(usize, usize)>,
        average: usize,
        epsilon: f64,
        wgridding: bool,
        single: bool,
    ) -> Result<Predictor, String> {
        let models = model_paths(name, channels_out)
            .iter()
            .map(|p| read_model(p))
            .collect::<Result<Vec<_>, _>>()?;
        let map = channel_map(freq, range, average, channels_out)?;
        Predictor::new(models, map, epsilon, wgridding, single)
    }

    /// Refuse a model whose centre is not the field's phase centre.
    pub fn check_centre(&self, phase_dir: (f64, f64)) -> Result<(), String> {
        let m = &self.models[0];
        if angle_gap(m.centre.0, phase_dir.0) > 1e-9 || (m.centre.1 - phase_dir.1).abs() > 1e-9 {
            return Err(format!(
                "{}: the image centre ({:.9}, {:.9}) deg is not the field's phase centre \
                 ({:.9}, {:.9}) deg; a shifted model is not supported",
                m.path.display(),
                m.centre.0.to_degrees(),
                m.centre.1.to_degrees(),
                phase_dir.0.to_degrees(),
                phase_dir.1.to_degrees()
            ));
        }
        Ok(())
    }

    /// Stokes I model visibilities of the rows `uvw` (metres, 3 per row) at
    /// the MS's channels `freq`: `rows × nchan`, zero in channels without a
    /// model.
    pub fn predict(&self, uvw: &[f64], freq: &[f64]) -> Result<Vec<Complex<f32>>, String> {
        if self.single {
            self.predict_in::<f32>(uvw, freq)
        } else {
            self.predict_in::<f64>(uvw, freq)
        }
    }

    fn predict_in<T: Real + Send + Sync>(
        &self,
        uvw: &[f64],
        freq: &[f64],
    ) -> Result<Vec<Complex<f32>>, String> {
        if freq.len() != self.map.len() {
            return Err(format!(
                "{} channels given, the channel map has {}",
                freq.len(),
                self.map.len()
            ));
        }
        let rows = uvw.len() / 3;
        let nchan = freq.len();
        let mut out = vec![Complex::new(0.0f32, 0.0); rows * nchan];
        if rows == 0 {
            return Ok(out);
        }
        for (k, model) in self.models.iter().enumerate() {
            let chans: Vec<usize> = (0..nchan).filter(|&c| self.map[c] == Some(k)).collect();
            if chans.is_empty() || model.pixels.iter().all(|&p| p == 0.0) {
                continue;
            }
            let f: Vec<f64> = chans.iter().map(|&c| freq[c]).collect();
            let image: Vec<T> = model.pixels.par_iter().map(|&p| T::of(p)).collect();
            let m = chans.len();
            let mut vis = vec![Complex::new(T::of(0.0), T::of(0.0)); rows * m];
            wgridder::dirty2vis(&self.opts, uvw, &f, &image, None, None, &mut vis)?;
            drop(image);
            out.par_chunks_mut(nchan)
                .zip(vis.par_chunks(m))
                .for_each(|(o, v)| {
                    for (j, &c) in chans.iter().enumerate() {
                        o[c] = Complex::new(v[j].re.to() as f32, v[j].im.to() as f32);
                    }
                });
        }
        Ok(out)
    }
}

/// What [`write_model_column`] did.
#[derive(Clone, Debug)]
pub struct Written {
    pub column: String,
    pub added: bool,
    pub rows_selected: u64,
    pub rows_total: u64,
    pub channels_predicted: usize,
    pub blocks: usize,
}

fn complex_bytes(v: &[Complex<f32>]) -> Vec<u8> {
    let mut out = Vec::with_capacity(v.len() * 8);
    for c in v {
        out.extend_from_slice(&c.re.to_ne_bytes());
        out.extend_from_slice(&c.im.to_ne_bytes());
    }
    out
}

fn complex_of(bytes: &[u8]) -> Vec<Complex<f32>> {
    bytes
        .chunks_exact(8)
        .map(|b| {
            Complex::new(
                f32::from_ne_bytes(b[..4].try_into().unwrap()),
                f32::from_ne_bytes(b[4..].try_into().unwrap()),
            )
        })
        .collect()
}

fn ms_err(e: crate::ms::MsError) -> String {
    e.to_string()
}

/// Make sure the model column exists with DATA's cell shape; returns true
/// when it was added (then every row is to be written, zero outside the
/// selection).
fn ensure_column(
    w: &mut TableWriter,
    name: &str,
    ncorr: usize,
    nchan: usize,
) -> Result<bool, String> {
    let cell = ncorr * nchan;
    if let Ok(index) = w.dat.column(name) {
        let desc = &w.dat.columns[index];
        if desc.dtype != DataType::Complex.code() || !desc.is_array() {
            return Err(format!("{name} exists but is not a complex array column"));
        }
        let first = w.read_column(name, 0, 1).map_err(|e| {
            format!("{name}: row 0 cannot be read ({e}); remove the column or write it first")
        })?;
        if first.bytes.len() != cell * 8 {
            return Err(format!(
                "{name}: row 0 is not a cell of {ncorr} correlations × {nchan} channels; \
                 WSClean would reset it, gemclean refuses (research/g6-predict.md)"
            ));
        }
        return Ok(false);
    }
    let data = w.dat.column("DATA").map_err(ms_err)?;
    let comment = w.dat.columns[data].comment.clone();
    let manager = if name == "MODEL_DATA" {
        "TiledModel".to_string()
    } else {
        "Tiled".to_string()
            + &name
                .to_lowercase()
                .split('_')
                .map(|p| {
                    let mut c = p.chars();
                    c.next().map_or(String::new(), |f| {
                        f.to_uppercase().collect::<String>() + c.as_str()
                    })
                })
                .collect::<String>()
    };
    let tile_rows = (TILE_BYTES / (cell * 8)).max(1);
    w.add_column(&NewColumn {
        name: name.to_string(),
        dtype: DataType::Complex.code(),
        array: true,
        ndim: 2,
        shape: vec![ncorr as i64, nchan as i64],
        option: 4,
        max_length: 0,
        comment,
        dm_type: "TiledShapeStMan".into(),
        dm_group: manager.clone(),
        default: Vec::new(),
        manager: NewManager::TiledShape {
            name: manager,
            tile: vec![ncorr as i64, nchan as i64, tile_rows as i64],
        },
    })
    .map_err(ms_err)?;
    w.flush().map_err(ms_err)?;
    Ok(true)
}

/// Predict `pred`'s model into column `column` of `ms` for the rows `sel`
/// takes, through the core writer (`TableWriter`), flushing every chunk.
pub fn write_model_column(
    ms: &Path,
    sel: &Selection,
    column: &str,
    pred: &Predictor,
) -> Result<Written, String> {
    let band = input::band(ms, sel)?;
    pred.check_centre(band.phase_dir)?;
    let (a, b) = input::parallel_hand_indices(&band.correlations)?;
    let nchan = band.freq.len();
    let ncorr = band.correlations.len();
    if pred.map.len() != nchan {
        return Err(format!(
            "the channel map has {} channels, the MS {nchan}",
            pred.map.len()
        ));
    }
    let rows = input::selected_rows(ms, sel)?;
    let mut w = TableWriter::open(ms, 10, std::time::Duration::from_secs(1)).map_err(ms_err)?;
    let added = ensure_column(&mut w, column, ncorr, nchan)?;
    let nrows = w.nrows;
    let per_chunk = chunk_rows(nchan * ncorr) as u64;
    let shape = [ncorr as i64, nchan as i64];
    let mapped: Vec<usize> = (0..nchan).filter(|&c| pred.map[c].is_some()).collect();
    // Write rows `from..to`, the selected ones from `vis` (rows `first..` of
    // the block's selection), the others zero (added) or as they are.
    let write_span = |w: &mut TableWriter,
                      from: u64,
                      to: u64,
                      block: &[u64],
                      vis: &[Complex<f32>]|
     -> Result<(), String> {
        let mut start = from;
        let mut next = block.partition_point(|&r| r < from);
        while start < to {
            let n = per_chunk.min(to - start);
            if !added && block[next..].first().is_none_or(|&r| r >= start + n) {
                start += n; // nothing to change in this chunk
                continue;
            }
            let mut cells = if added {
                vec![Complex::new(0.0f32, 0.0); n as usize * nchan * ncorr]
            } else {
                complex_of(&w.read_column(column, start, n).map_err(ms_err)?.bytes)
            };
            while next < block.len() && block[next] < start + n {
                let r = (block[next] - start) as usize;
                let row = &mut cells[r * nchan * ncorr..(r + 1) * nchan * ncorr];
                for &c in &mapped {
                    let v = vis[next * nchan + c];
                    let cell = &mut row[c * ncorr..(c + 1) * ncorr];
                    cell.iter_mut().for_each(|x| *x = Complex::new(0.0, 0.0));
                    cell[a] = v;
                    cell[b] = v;
                }
                next += 1;
            }
            w.put_column(column, start, n, &shape, &complex_bytes(&cells))
                .map_err(ms_err)?;
            w.flush().map_err(ms_err)?;
            start += n;
        }
        Ok(())
    };
    let per_block = block_rows(nchan);
    let mut cursor = 0u64;
    let mut blocks = 0;
    for block in rows.chunks(per_block) {
        let (lo, hi) = (block[0], *block.last().unwrap() + 1);
        if added && cursor < lo {
            write_span(&mut w, cursor, lo, &[], &[])?;
        }
        let mut uvw = Vec::with_capacity(block.len() * 3);
        let mut s = lo;
        let mut next = 0;
        while s < hi {
            let n = per_chunk.min(hi - s);
            let data = w.read_column("UVW", s, n).map_err(ms_err)?;
            if data.dtype != Some(DataType::Double) || data.bytes.len() != n as usize * 24 {
                return Err("UVW is not three doubles per row".into());
            }
            while next < block.len() && block[next] < s + n {
                let r = (block[next] - s) as usize;
                for j in 0..3 {
                    let at = (3 * r + j) * 8;
                    uvw.push(f64::from_ne_bytes(
                        data.bytes[at..at + 8].try_into().unwrap(),
                    ));
                }
                next += 1;
            }
            s += n;
        }
        let vis = pred.predict(&uvw, &band.freq)?;
        drop(uvw);
        write_span(&mut w, lo, hi, block, &vis)?;
        cursor = hi;
        blocks += 1;
    }
    if added && cursor < nrows {
        write_span(&mut w, cursor, nrows, &[], &[])?;
    }
    w.close().map_err(ms_err)?;
    Ok(Written {
        column: column.to_string(),
        added,
        rows_selected: rows.len() as u64,
        rows_total: nrows,
        channels_predicted: mapped.len(),
        blocks,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn channel_map_follows_the_imaging_groups() {
        // Descending band: ascending order is 3, 2, 1, 0, ...
        let freq: Vec<f64> = (0..8).map(|i| 1.0e9 - i as f64 * 1e6).collect();
        let all = channel_map(&freq, None, 1, 1).unwrap();
        assert!(all.iter().all(|&k| k == Some(0)));
        let four = channel_map(&freq, None, 1, 4).unwrap();
        // Output channel 0 holds the two lowest frequencies (channels 7, 6).
        assert_eq!(four[7], Some(0));
        assert_eq!(four[6], Some(0));
        assert_eq!(four[0], Some(3));
        let ranged = channel_map(&freq, Some((2, 6)), 1, 2).unwrap();
        assert_eq!(ranged[7], None);
        assert_eq!(ranged[6], None);
        assert_eq!(ranged[5], Some(0));
        assert_eq!(ranged[2], Some(1));
        assert_eq!(ranged[1], None);
        let averaged = channel_map(&freq, None, 3, 2).unwrap();
        // Averaged groups (ascending): {7,6,5}, {4,3,2}, {1,0}; two output
        // channels of three averaged channels: [0], [1, 2].
        assert_eq!(averaged[5], Some(0));
        assert_eq!(averaged[4], Some(1));
        assert_eq!(averaged[0], Some(1));
    }

    #[test]
    fn blocks_and_chunks() {
        assert_eq!(block_rows(512), (1 << 27) / 512);
        assert_eq!(chunk_rows(4096 * 4), 512);
        assert_eq!(chunk_rows(1 << 30), 64);
    }

    #[test]
    fn a_centred_point_predicts_its_flux() {
        let n = 64;
        let mut pixels = vec![0.0; n * n];
        pixels[(n / 2) * n + n / 2] = 2.5;
        let model = ModelImage {
            path: PathBuf::from("m"),
            n,
            scale: (2.0f64 / 3600.0).to_radians(),
            centre: (0.0, -0.5),
            pixels,
        };
        let freq = vec![1.0e9, 1.1e9];
        let pred = Predictor::new(vec![model], vec![Some(0), Some(0)], 1e-6, true, false).unwrap();
        let uvw = vec![100.0, -50.0, 3.0, 1000.0, 200.0, -10.0];
        let v = pred.predict(&uvw, &freq).unwrap();
        for x in v {
            assert!((x.re - 2.5).abs() < 1e-5 && x.im.abs() < 1e-5, "{x}");
        }
        assert!(pred.check_centre((std::f64::consts::TAU, -0.5)).is_ok());
        assert!(pred.check_centre((0.0, -0.4)).is_err());
    }
}
