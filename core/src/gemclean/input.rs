//! Measurement Set input of gemclean: Stokes I visibilities, WSClean's
//! imaging weights and the field and band metadata, through the core's own
//! read-only reader ([`crate::ms`]).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The rules follow `examples/clean_certified_export.py`, which reproduces
//! WSClean 3.7's visibility count and weight sum (`WSCNVIS`, `WSCIMGWG`) on
//! the LUNO slice: rows of the selected field and data description that are
//! cross-correlations; Stokes I as WSClean's `-pol I` forms it
//! (`I = ½(XX + YY)`, weight `min(4 w_XX, 4 w_YY)`, zero when a hand is
//! flagged or not finite; [`crate::weights::stokes_i_from_linear`]); the
//! imaging weights on the padded grid (padding 1.2, rank filter 3 over 16
//! cells, WSClean's defaults); the gridding weight is the Stokes I weight
//! times the imaging weight, zero on `FLAG_ROW` rows (which still enter the
//! weight grid, as in WSClean). Wavelengths are `c / f` in double precision
//! (WSClean divides in `long double`; a rare last-bit difference can move a
//! sample by one weight cell).

use crate::ms::{ColumnData, DataType, Table};
use crate::weights::{WeightClass, WeightSettings, imaging_weights, padded_size};
use rayon::prelude::*;
use rustfft::num_complex::Complex;
use std::path::Path;

pub const SPEED_OF_LIGHT: f64 = 299_792_458.0;

/// Which rows and column to image.
#[derive(Clone, Debug)]
pub struct Selection {
    pub data_column: String,
    pub field: i32,
    pub data_desc: i32,
    /// Rows read per chunk.
    pub chunk_rows: u64,
}

impl Default for Selection {
    fn default() -> Selection {
        Selection {
            data_column: "DATA".into(),
            field: 0,
            data_desc: 0,
            chunk_rows: 20_000,
        }
    }
}

/// The selected rows as Stokes I, `rows × nchan` in row order.
#[derive(Clone, Debug)]
pub struct StokesI {
    pub uvw: Vec<f64>,
    pub freq: Vec<f64>,
    pub vis: Vec<Complex<f64>>,
    pub weight: Vec<f32>,
    pub flag_row: Vec<bool>,
    /// Phase centre (RA, Dec) in radians.
    pub phase_dir: (f64, f64),
    pub rows_total: u64,
    pub correlations: Vec<i32>,
    /// `WEIGHT_SPECTRUM` (true) or `WEIGHT` broadcast over channels.
    pub weight_spectrum: bool,
}

impl StokesI {
    pub fn rows(&self) -> usize {
        self.flag_row.len()
    }
}

fn err<T>(e: impl std::fmt::Display) -> Result<T, String> {
    Err(e.to_string())
}

fn expect(data: &ColumnData, dtype: DataType, name: &str) -> Result<(), String> {
    if data.dtype != Some(dtype) {
        return err(format!(
            "{name}: expected {dtype:?}, found {:?}",
            data.dtype
        ));
    }
    Ok(())
}

fn ints(data: &ColumnData, name: &str) -> Result<Vec<i32>, String> {
    expect(data, DataType::Int, name)?;
    Ok(data
        .bytes
        .chunks_exact(4)
        .map(|b| i32::from_ne_bytes(b.try_into().unwrap()))
        .collect())
}

fn doubles(data: &ColumnData, name: &str) -> Result<Vec<f64>, String> {
    expect(data, DataType::Double, name)?;
    Ok(data
        .bytes
        .chunks_exact(8)
        .map(|b| f64::from_ne_bytes(b.try_into().unwrap()))
        .collect())
}

fn floats(data: &ColumnData, name: &str) -> Result<Vec<f32>, String> {
    expect(data, DataType::Float, name)?;
    Ok(data
        .bytes
        .chunks_exact(4)
        .map(|b| f32::from_ne_bytes(b.try_into().unwrap()))
        .collect())
}

fn bools(data: &ColumnData, name: &str) -> Result<Vec<u8>, String> {
    expect(data, DataType::Bool, name)?;
    Ok(data.bytes.clone())
}

/// Complex values as interleaved `f32` pairs (DComplex is rounded to float,
/// as WSClean reads the data column in single precision).
fn complex_f32(data: &ColumnData, name: &str) -> Result<Vec<f32>, String> {
    match data.dtype {
        Some(DataType::Complex) => Ok(data
            .bytes
            .chunks_exact(4)
            .map(|b| f32::from_ne_bytes(b.try_into().unwrap()))
            .collect()),
        Some(DataType::DComplex) => Ok(data
            .bytes
            .chunks_exact(8)
            .map(|b| f64::from_ne_bytes(b.try_into().unwrap()) as f32)
            .collect()),
        other => err(format!(
            "{name}: expected a complex column, found {other:?}"
        )),
    }
}

fn read(table: &Table, name: &str, start: u64, count: u64) -> Result<ColumnData, String> {
    table
        .read_column(name, start, count)
        .map_err(|e| format!("{}: {e}", table.path.display()))
}

/// Indices of the two parallel hands among the correlations (XX and YY, or
/// RR and LL), or one index for a Stokes I column.
fn parallel_hands(corr: &[i32]) -> Result<(usize, usize), String> {
    let find = |codes: &[i32]| corr.iter().position(|c| codes.contains(c));
    if let (Some(a), Some(b)) = (find(&[9, 5]), find(&[12, 8])) {
        return Ok((a, b));
    }
    if let Some(i) = find(&[1]) {
        return Ok((i, i));
    }
    err(format!("no XX/YY, RR/LL or I correlations in {corr:?}"))
}

/// One visibility's Stokes I and weight from its correlations, with the
/// arithmetic of [`crate::weights::stokes_i_from_linear`] (float sums,
/// `std::min` semantics); `a == b` takes a Stokes I correlation as is.
fn stokes_cell(d: &[f32], w: &[f32], f: &[u8], a: usize, b: usize) -> ((f32, f32), f32) {
    let finite = |re: f32, im: f32| re.is_finite() && im.is_finite();
    let (xr, xi, yr, yi) = (d[2 * a], d[2 * a + 1], d[2 * b], d[2 * b + 1]);
    if a == b {
        let ok = f[a] == 0 && finite(xr, xi);
        let v = if finite(xr, xi) { (xr, xi) } else { (0.0, 0.0) };
        return (v, if ok { w[a] } else { 0.0 });
    }
    let re = (yr + xr) * 0.5;
    let im = (yi + xi) * 0.5;
    let v = if finite(re, im) { (re, im) } else { (0.0, 0.0) };
    let mut weight = if f[a] == 0 && finite(xr, xi) {
        w[a] * 4.0
    } else {
        0.0
    };
    weight = if f[b] == 0 && finite(yr, yi) {
        let yy = w[b] * 4.0;
        if yy < weight { yy } else { weight }
    } else {
        0.0
    };
    (v, weight)
}

/// Read the selected rows of a Measurement Set as Stokes I.
pub fn read_ms(path: &Path, sel: &Selection) -> Result<StokesI, String> {
    let main = Table::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    // Data description -> spectral window and polarisation.
    let (spw, pol) = match Table::open(path.join("DATA_DESCRIPTION")) {
        Ok(dd) if dd.nrows > sel.data_desc as u64 => {
            let row = sel.data_desc as u64;
            (
                ints(
                    &read(&dd, "SPECTRAL_WINDOW_ID", row, 1)?,
                    "SPECTRAL_WINDOW_ID",
                )?[0],
                ints(&read(&dd, "POLARIZATION_ID", row, 1)?, "POLARIZATION_ID")?[0],
            )
        }
        _ => (sel.data_desc, 0),
    };
    let spw_table = Table::open(path.join("SPECTRAL_WINDOW")).map_err(|e| e.to_string())?;
    let freq = doubles(&read(&spw_table, "CHAN_FREQ", spw as u64, 1)?, "CHAN_FREQ")?;
    let pol_table = Table::open(path.join("POLARIZATION")).map_err(|e| e.to_string())?;
    let correlations = ints(&read(&pol_table, "CORR_TYPE", pol as u64, 1)?, "CORR_TYPE")?;
    let field_table = Table::open(path.join("FIELD")).map_err(|e| e.to_string())?;
    if sel.field < 0 || sel.field as u64 >= field_table.nrows {
        return err(format!(
            "field {} does not exist ({} fields)",
            sel.field, field_table.nrows
        ));
    }
    let dir = doubles(
        &read(&field_table, "PHASE_DIR", sel.field as u64, 1)?,
        "PHASE_DIR",
    )?;
    if dir.len() < 2 {
        return err("PHASE_DIR has fewer than two values");
    }
    let (a, b) = parallel_hands(&correlations)?;
    let nchan = freq.len();
    let ncorr = correlations.len();
    let weight_spectrum = main.column("WEIGHT_SPECTRUM").is_ok()
        && main.nrows > 0
        && read(&main, "WEIGHT_SPECTRUM", 0, 1).is_ok();
    let mut out = StokesI {
        uvw: Vec::new(),
        freq,
        vis: Vec::new(),
        weight: Vec::new(),
        flag_row: Vec::new(),
        phase_dir: (dir[0], dir[1]),
        rows_total: main.nrows,
        correlations,
        weight_spectrum,
    };
    let mut start = 0;
    while start < main.nrows {
        let count = sel.chunk_rows.max(1).min(main.nrows - start);
        let field = ints(&read(&main, "FIELD_ID", start, count)?, "FIELD_ID")?;
        let ant1 = ints(&read(&main, "ANTENNA1", start, count)?, "ANTENNA1")?;
        let ant2 = ints(&read(&main, "ANTENNA2", start, count)?, "ANTENNA2")?;
        let ddid = ints(&read(&main, "DATA_DESC_ID", start, count)?, "DATA_DESC_ID")?;
        let keep: Vec<bool> = (0..count as usize)
            .map(|i| field[i] == sel.field && ant1[i] != ant2[i] && ddid[i] == sel.data_desc)
            .collect();
        if keep.iter().any(|&k| k) {
            let flag_row = bools(&read(&main, "FLAG_ROW", start, count)?, "FLAG_ROW")?;
            let uvw = doubles(&read(&main, "UVW", start, count)?, "UVW")?;
            let data = complex_f32(
                &read(&main, &sel.data_column, start, count)?,
                &sel.data_column,
            )?;
            let flag = bools(&read(&main, "FLAG", start, count)?, "FLAG")?;
            let weights = if weight_spectrum {
                floats(
                    &read(&main, "WEIGHT_SPECTRUM", start, count)?,
                    "WEIGHT_SPECTRUM",
                )?
            } else {
                let w = floats(&read(&main, "WEIGHT", start, count)?, "WEIGHT")?;
                let mut full = Vec::with_capacity(count as usize * nchan * ncorr);
                for row in w.chunks_exact(ncorr) {
                    for _ in 0..nchan {
                        full.extend_from_slice(row);
                    }
                }
                full
            };
            let cells = nchan * ncorr;
            if data.len() != count as usize * cells * 2
                || flag.len() != count as usize * cells
                || weights.len() != count as usize * cells
            {
                return err(format!(
                    "rows {start}..{}: data, FLAG or weights do not hold {ncorr} correlations × {nchan} channels",
                    start + count
                ));
            }
            // Stokes I per row in parallel: the rows are independent.
            let kept: Vec<usize> = (0..keep.len()).filter(|&i| keep[i]).collect();
            for &i in &kept {
                out.uvw.extend_from_slice(&uvw[3 * i..3 * i + 3]);
                out.flag_row.push(flag_row[i] != 0);
            }
            let first = out.vis.len();
            let cells_kept = kept.len() * nchan;
            out.vis.resize(first + cells_kept, Complex::new(0.0, 0.0));
            out.weight.resize(first + cells_kept, 0.0);
            out.vis[first..]
                .par_chunks_mut(nchan)
                .zip(out.weight[first..].par_chunks_mut(nchan))
                .zip(kept.par_iter())
                .for_each(|((vis, wgt), &i)| {
                    for ch in 0..nchan {
                        let cell = i * cells + ch * ncorr;
                        let (v, w) = stokes_cell(
                            &data[2 * cell..2 * (cell + ncorr)],
                            &weights[cell..cell + ncorr],
                            &flag[cell..cell + ncorr],
                            a,
                            b,
                        );
                        vis[ch] = Complex::new(f64::from(v.0), f64::from(v.1));
                        wgt[ch] = w;
                    }
                });
        }
        start += count;
    }
    Ok(out)
}

/// Gridding weights and WSClean's header counters.
#[derive(Clone, Debug)]
pub struct GriddingWeights {
    /// `rows × nchan`, Stokes I weight × imaging weight.
    pub weights: Vec<f64>,
    /// `WSCNVIS`: visibilities with a nonzero weight.
    pub count: u64,
    /// `WSCIMGWG`: the sum of the gridding weights.
    pub total: f64,
    /// `WSCVWSUM`: Stokes I weights where the gridding weight is nonzero.
    pub visibility_weight_sum: f64,
    pub padded: usize,
}

/// WSClean's `-weight` on an image of `size` pixels of `scale` radians.
pub fn gridding_weights(
    data: &StokesI,
    class: WeightClass,
    size: usize,
    scale: f64,
) -> Result<GriddingWeights, String> {
    let padded = padded_size(size, 1.2);
    let settings = WeightSettings {
        class,
        width: padded,
        height: padded,
        scale_x: scale,
        scale_y: scale,
        super_weight: 1.0,
        rank_filter_level: 3.0,
        rank_filter_size: 16,
    };
    let wavelength: Vec<f64> = data.freq.iter().map(|f| SPEED_OF_LIGHT / f).collect();
    let selected = vec![true; data.rows()];
    let (imaging, _) = imaging_weights(&settings, &data.uvw, &wavelength, &data.weight, &selected)
        .map_err(|e| e.to_string())?;
    let nchan = data.freq.len();
    let mut weights = vec![0.0; imaging.len()];
    let (mut count, mut total, mut vsum) = (0u64, 0.0, 0.0);
    for row in 0..data.rows() {
        if data.flag_row[row] {
            continue;
        }
        for ch in 0..nchan {
            let k = row * nchan + ch;
            let g = f64::from(data.weight[k]) * f64::from(imaging[k]);
            if g != 0.0 {
                count += 1;
                total += g;
                vsum += f64::from(data.weight[k]);
            }
            weights[k] = g;
        }
    }
    Ok(GriddingWeights {
        weights,
        count,
        total,
        visibility_weight_sum: vsum,
        padded,
    })
}

/// Arrays of a simulated observation for [`write_ms`]: one field, one
/// spectral window, four linear correlations.
pub struct MsArrays<'a> {
    /// `nrow × 3`, metres.
    pub uvw: &'a [f64],
    pub antenna1: &'a [i32],
    pub antenna2: &'a [i32],
    /// MJD seconds per row.
    pub time: &'a [f64],
    pub interval: f64,
    /// Hz.
    pub freq: &'a [f64],
    /// `nrow × nchan × 4` interleaved complex floats (corr fastest).
    pub data: &'a [f32],
    /// `nrow × nchan × 4` floats.
    pub weight_spectrum: &'a [f32],
    /// ITRF metres per antenna.
    pub antennas: &'a [[f64; 3]],
    pub dish_diameter: f64,
    /// (RA, Dec), radians.
    pub phase_dir: (f64, f64),
}

fn f32_bytes(v: &[f32]) -> Vec<u8> {
    v.iter().flat_map(|x| x.to_ne_bytes()).collect()
}

fn f64_bytes(v: &[f64]) -> Vec<u8> {
    v.iter().flat_map(|x| x.to_ne_bytes()).collect()
}

fn i32_bytes(v: &[i32]) -> Vec<u8> {
    v.iter().flat_map(|x| x.to_ne_bytes()).collect()
}

/// Write a new Measurement Set from arrays through the core's table writer
/// ([`crate::ms_create::default_ms`]): DATA, FLAG (all false) and
/// WEIGHT_SPECTRUM in tiled managers, the required scalars, and rows in
/// ANTENNA, DATA_DESCRIPTION, FIELD, POLARIZATION and SPECTRAL_WINDOW.
pub fn write_ms(path: &Path, a: &MsArrays) -> Result<(), String> {
    use crate::aipsio::{Record, tp};
    use crate::ms_create::{ManagerSpec, NewColumn, default_ms, new_coldesc};
    use crate::ms_write::TableWriter;
    let e = |e: crate::ms::MsError| e.to_string();
    let nrow = a.antenna1.len();
    let nchan = a.freq.len();
    let ncell = nrow * nchan * 4;
    if a.uvw.len() != 3 * nrow
        || a.antenna2.len() != nrow
        || a.time.len() != nrow
        || a.data.len() != 2 * ncell
        || a.weight_spectrum.len() != ncell
    {
        return Err("write_ms: array lengths disagree".into());
    }
    let cell = [4i64, nchan as i64];
    let tile = vec![4i64, nchan as i64, 1024];
    let tiled = |name: &str, dtype: i32| -> Result<_, String> {
        new_coldesc(&NewColumn {
            name: name.into(),
            dtype,
            array: true,
            ndim: 2,
            shape: cell.to_vec(),
            option: 4,
            max_length: 0,
            comment: String::new(),
            dm_type: "TiledShapeStMan".into(),
            dm_group: format!("Tiled{name}"),
            keywords: Record::default(),
        })
        .map_err(e)
    };
    let extra = [
        tiled("DATA", tp::COMPLEX)?,
        tiled("FLAG", tp::BOOL)?,
        tiled("WEIGHT_SPECTRUM", tp::FLOAT)?,
    ];
    let managers: Vec<ManagerSpec> = ["DATA", "FLAG", "WEIGHT_SPECTRUM"]
        .iter()
        .map(|name| ManagerSpec {
            kind: "TiledShapeStMan".into(),
            name: format!("Tiled{name}"),
            columns: vec![name.to_string()],
            tile: tile.clone(),
            ..Default::default()
        })
        .collect();
    let mut main = default_ms(path, &extra, &managers).map_err(e)?;
    main.add_rows(nrow as u64).map_err(e)?;
    let count = nrow as u64;
    main.put_column("UVW", 0, count, &[3], &f64_bytes(a.uvw))
        .map_err(e)?;
    main.put_column("ANTENNA1", 0, count, &[], &i32_bytes(a.antenna1))
        .map_err(e)?;
    main.put_column("ANTENNA2", 0, count, &[], &i32_bytes(a.antenna2))
        .map_err(e)?;
    main.put_column("TIME", 0, count, &[], &f64_bytes(a.time))
        .map_err(e)?;
    main.put_column("TIME_CENTROID", 0, count, &[], &f64_bytes(a.time))
        .map_err(e)?;
    let interval = vec![a.interval; nrow];
    main.put_column("INTERVAL", 0, count, &[], &f64_bytes(&interval))
        .map_err(e)?;
    main.put_column("EXPOSURE", 0, count, &[], &f64_bytes(&interval))
        .map_err(e)?;
    let zeros = vec![0i32; nrow];
    for name in [
        "ARRAY_ID",
        "DATA_DESC_ID",
        "FEED1",
        "FEED2",
        "FIELD_ID",
        "OBSERVATION_ID",
        "PROCESSOR_ID",
        "SCAN_NUMBER",
        "STATE_ID",
    ] {
        main.put_column(name, 0, count, &[], &i32_bytes(&zeros))
            .map_err(e)?;
    }
    main.put_column("FLAG_ROW", 0, count, &[], &vec![0u8; nrow])
        .map_err(e)?;
    let ones = vec![1.0f32; nrow * 4];
    main.put_column("WEIGHT", 0, count, &[4], &f32_bytes(&ones))
        .map_err(e)?;
    main.put_column("SIGMA", 0, count, &[4], &f32_bytes(&ones))
        .map_err(e)?;
    main.put_column("DATA", 0, count, &cell, &f32_bytes(a.data))
        .map_err(e)?;
    main.put_column("FLAG", 0, count, &cell, &vec![0u8; ncell])
        .map_err(e)?;
    main.put_column(
        "WEIGHT_SPECTRUM",
        0,
        count,
        &cell,
        &f32_bytes(a.weight_spectrum),
    )
    .map_err(e)?;
    main.close().map_err(e)?;

    let wait = std::time::Duration::from_millis(100);
    let open = |name: &str| TableWriter::open(path.join(name), 3, wait).map_err(e);

    let mut t = open("ANTENNA")?;
    let nant = a.antennas.len() as u64;
    t.add_rows(nant).map_err(e)?;
    let flat: Vec<f64> = a.antennas.iter().flatten().copied().collect();
    t.put_column("POSITION", 0, nant, &[3], &f64_bytes(&flat))
        .map_err(e)?;
    t.put_column("OFFSET", 0, nant, &[3], &f64_bytes(&vec![0.0; flat.len()]))
        .map_err(e)?;
    t.put_column(
        "DISH_DIAMETER",
        0,
        nant,
        &[],
        &f64_bytes(&vec![a.dish_diameter; a.antennas.len()]),
    )
    .map_err(e)?;
    let names: Vec<String> = (0..a.antennas.len()).map(|i| format!("m{i:03}")).collect();
    t.put_strings("NAME", 0, &names).map_err(e)?;
    t.put_strings("STATION", 0, &names).map_err(e)?;
    t.put_strings("TYPE", 0, &vec!["GROUND-BASED".to_string(); names.len()])
        .map_err(e)?;
    t.put_strings("MOUNT", 0, &vec!["ALT-AZ".to_string(); names.len()])
        .map_err(e)?;
    t.close().map_err(e)?;

    let mut t = open("OBSERVATION")?;
    t.add_rows(1).map_err(e)?;
    let (first, last) = (a.time[0], a.time[nrow - 1]);
    t.put_cell("TIME_RANGE", 0, &[2], &f64_bytes(&[first, last]))
        .map_err(e)?;
    t.put_strings("TELESCOPE_NAME", 0, &["MeerKAT".to_string()])
        .map_err(e)?;
    t.put_strings("OBSERVER", 0, &["rang".to_string()])
        .map_err(e)?;
    t.put_strings("PROJECT", 0, &["gemclean".to_string()])
        .map_err(e)?;
    t.put_strings("SCHEDULE_TYPE", 0, &[String::new()])
        .map_err(e)?;
    t.put_column("RELEASE_DATE", 0, 1, &[], &f64_bytes(&[0.0]))
        .map_err(e)?;
    t.put_column("FLAG_ROW", 0, 1, &[], &[0u8]).map_err(e)?;
    t.close().map_err(e)?;

    let mut t = open("POLARIZATION")?;
    t.add_rows(1).map_err(e)?;
    t.put_column("NUM_CORR", 0, 1, &[], &i32_bytes(&[4]))
        .map_err(e)?;
    t.put_cell("CORR_TYPE", 0, &[4], &i32_bytes(&[9, 10, 11, 12]))
        .map_err(e)?;
    t.put_cell(
        "CORR_PRODUCT",
        0,
        &[2, 4],
        &i32_bytes(&[0, 0, 0, 1, 1, 0, 1, 1]),
    )
    .map_err(e)?;
    t.close().map_err(e)?;

    let mut t = open("SPECTRAL_WINDOW")?;
    t.add_rows(1).map_err(e)?;
    let width = if nchan > 1 {
        a.freq[1] - a.freq[0]
    } else {
        1.0
    };
    let n = nchan as i64;
    t.put_column("NUM_CHAN", 0, 1, &[], &i32_bytes(&[nchan as i32]))
        .map_err(e)?;
    t.put_cell("CHAN_FREQ", 0, &[n], &f64_bytes(a.freq))
        .map_err(e)?;
    for name in ["CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"] {
        t.put_cell(name, 0, &[n], &f64_bytes(&vec![width; nchan]))
            .map_err(e)?;
    }
    t.put_column("REF_FREQUENCY", 0, 1, &[], &f64_bytes(&a.freq[..1]))
        .map_err(e)?;
    t.put_column(
        "TOTAL_BANDWIDTH",
        0,
        1,
        &[],
        &f64_bytes(&[width * nchan as f64]),
    )
    .map_err(e)?;
    t.put_column("MEAS_FREQ_REF", 0, 1, &[], &i32_bytes(&[5]))
        .map_err(e)?;
    t.put_strings("NAME", 0, &["SIM".to_string()]).map_err(e)?;
    t.close().map_err(e)?;

    let mut t = open("DATA_DESCRIPTION")?;
    t.add_rows(1).map_err(e)?;
    t.put_column("SPECTRAL_WINDOW_ID", 0, 1, &[], &i32_bytes(&[0]))
        .map_err(e)?;
    t.put_column("POLARIZATION_ID", 0, 1, &[], &i32_bytes(&[0]))
        .map_err(e)?;
    t.put_column("FLAG_ROW", 0, 1, &[], &[0u8]).map_err(e)?;
    t.close().map_err(e)?;

    let mut t = open("FIELD")?;
    t.add_rows(1).map_err(e)?;
    let dir = [a.phase_dir.0, a.phase_dir.1];
    for name in ["PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"] {
        t.put_cell(name, 0, &[2, 1], &f64_bytes(&dir)).map_err(e)?;
    }
    t.put_strings("NAME", 0, &["SIM".to_string()]).map_err(e)?;
    t.put_strings("CODE", 0, &[String::new()]).map_err(e)?;
    t.put_column("SOURCE_ID", 0, 1, &[], &i32_bytes(&[0]))
        .map_err(e)?;
    t.put_column("NUM_POLY", 0, 1, &[], &i32_bytes(&[0]))
        .map_err(e)?;
    t.put_column("TIME", 0, 1, &[], &f64_bytes(&a.time[..1]))
        .map_err(e)?;
    t.close().map_err(e)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn simulated_ms_round_trips_through_the_reader() {
        let dir = std::env::temp_dir().join(format!("gemclean-ms-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("t.ms");
        let (nrow, nchan) = (5usize, 3usize);
        let uvw: Vec<f64> = (0..3 * nrow).map(|i| i as f64 * 1.5 - 4.0).collect();
        let ant1 = vec![0, 0, 1, 2, 2];
        let ant2 = vec![1, 2, 2, 3, 2]; // the last is an autocorrelation
        let time = vec![5.0e9; nrow];
        let freq = vec![1.0e9, 1.1e9, 1.2e9];
        let mut data = vec![0.0f32; 2 * nrow * nchan * 4];
        let mut weight = vec![1.0f32; nrow * nchan * 4];
        for row in 0..nrow {
            for ch in 0..nchan {
                let cell = (row * nchan + ch) * 4;
                let v = (row * 10 + ch) as f32;
                data[2 * cell] = v; // XX real
                data[2 * cell + 1] = -v; // XX imaginary
                data[2 * (cell + 3)] = v + 2.0; // YY real
                data[2 * (cell + 3) + 1] = -v; // YY imaginary
                weight[cell] = 2.0;
                weight[cell + 3] = 3.0;
            }
        }
        let antennas = [[1.0, 2.0, 3.0]; 4];
        let phase_dir = (1.25, -0.5);
        write_ms(
            &path,
            &MsArrays {
                uvw: &uvw,
                antenna1: &ant1,
                antenna2: &ant2,
                time: &time,
                interval: 60.0,
                freq: &freq,
                data: &data,
                weight_spectrum: &weight,
                antennas: &antennas,
                dish_diameter: 13.5,
                phase_dir,
            },
        )
        .unwrap();
        let back = read_ms(&path, &Selection::default()).unwrap();
        assert_eq!(back.rows_total, 5);
        assert_eq!(back.rows(), 4, "the autocorrelation is not selected");
        assert_eq!(back.freq, freq);
        assert_eq!(back.correlations, [9, 10, 11, 12]);
        assert_eq!(back.phase_dir, phase_dir);
        assert!(back.weight_spectrum);
        assert_eq!(&back.uvw[..12], &uvw[..12]);
        for row in 0..4 {
            for ch in 0..nchan {
                let v = (row * 10 + ch) as f64;
                let got = back.vis[row * nchan + ch];
                assert_eq!((got.re, got.im), (v + 1.0, -v));
                assert_eq!(back.weight[row * nchan + ch], 8.0);
            }
        }
        // Natural weighting keeps the Stokes I weights of the grid's samples.
        let g = gridding_weights(&back, WeightClass::Natural, 64, 1e-3).unwrap();
        assert_eq!(g.count, 12);
        assert_eq!(g.total, 96.0);
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn stokes_cell_equals_the_weights_port() {
        let mut state = 7u64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 40) as f32 / (1u64 << 24) as f32
        };
        let ncell = 200;
        let mut data: Vec<f32> = (0..8 * ncell).map(|_| next() - 0.5).collect();
        let weights: Vec<f32> = (0..4 * ncell).map(|_| next()).collect();
        let flags: Vec<u8> = (0..4 * ncell).map(|_| u8::from(next() < 0.1)).collect();
        data[8 * 5] = f32::NAN;
        data[8 * 9 + 7] = f32::INFINITY;
        let (vis, w) =
            crate::weights::stokes_i_from_linear(&data, &weights, &flags, ncell).unwrap();
        for cell in 0..ncell {
            let (v, wt) = stokes_cell(
                &data[8 * cell..8 * cell + 8],
                &weights[4 * cell..4 * cell + 4],
                &flags[4 * cell..4 * cell + 4],
                0,
                3,
            );
            assert_eq!(v.0.to_bits(), vis[2 * cell].to_bits());
            assert_eq!(v.1.to_bits(), vis[2 * cell + 1].to_bits());
            assert_eq!(wt.to_bits(), w[cell].to_bits());
        }
        assert_eq!(parallel_hands(&[9, 10, 11, 12]).unwrap(), (0, 3));
        assert_eq!(parallel_hands(&[5, 8]).unwrap(), (0, 1));
        assert_eq!(parallel_hands(&[1]).unwrap(), (0, 0));
        assert!(parallel_hands(&[10, 11]).is_err());
    }
}
