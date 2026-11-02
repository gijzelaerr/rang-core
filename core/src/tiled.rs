//! Tile shapes and hypercube records of casacore's tiled storage managers
//! (research/e6-table-writer-final.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! `TSMCube::adjustTileShape` and `TiledStMan::makeTileShape` as casacore
//! 3.8.1 computes them (the default tile of a hypercube whose manager has no
//! DEFAULTTILESHAPE, or axes of it left 0), and the id and coordinate values
//! record of a hypercube (`TSMCube::values_p`, a `Record` object in the
//! tiled header). The algorithms were read in the casacore sources; nothing
//! is copied from casacore (LGPL-2.1-or-later).

use crate::aipsio::{KeywordValue, Record, Value, Writer};
use crate::ms::{Cursor, MsError, Result};

/// `TiledStMan::makeTileShape(shape, tolerance, nrPixelsPerTile)` with
/// weights 1: a tile of about `npix` pixels shaped like the cube, then, when
/// it does not fit the cube exactly and the cube is more than 4 tiles, the
/// cheapest shape near it (cost: axis deviation + 10 × waste + size
/// deviation), lengths evened out over the tiles of each axis.
pub fn make_tile_shape(cube: &[i64], tolerance: f64, npix: u64) -> Vec<i64> {
    let nrdim = cube.len();
    let mut left = npix as f64;
    let mut tmp = vec![0f64; nrdim];
    let mut tile = vec![0i64; nrdim];
    loop {
        let mut prod = 1f64;
        let mut n = 0u32;
        for i in 0..nrdim {
            if tile[i] == 0 {
                prod *= cube[i] as f64;
                n += 1;
            }
        }
        if n == 0 {
            break;
        }
        let factor = (left / prod).powf(1.0 / f64::from(n));
        let mut max_diff = 0f64;
        let mut max_index: isize = -1;
        for i in 0..nrdim {
            if tile[i] == 0 {
                let mut diff = cube[i] as f64 * factor;
                tmp[i] = diff;
                if diff > 1.0 {
                    diff = cube[i] as f64 / diff;
                }
                if max_index < 0 || diff < max_diff {
                    max_diff = diff;
                    max_index = i as isize;
                }
            }
        }
        if max_diff >= 1.0 {
            for i in 0..nrdim {
                if tile[i] == 0 {
                    tile[i] = (tmp[i] + 0.5) as i64;
                }
            }
            break;
        }
        let m = max_index as usize;
        if tmp[m] < 1.0 {
            tile[m] = 1;
        } else {
            tile[m] = cube[m];
            left /= tile[m] as f64;
        }
    }
    let mut fit = true;
    let mut size = 1f64;
    for i in 0..nrdim {
        if cube[i] % tile[i] != 0 {
            fit = false;
        }
        size *= cube[i] as f64;
    }
    if fit {
        return tile;
    }
    if size <= 4.0 * npix as f64 {
        return cube.to_vec();
    }
    let mut best = tile.clone();
    let mut min_shape = vec![0i64; nrdim];
    let mut max_shape = vec![0i64; nrdim];
    let mut cube_space = 1f64;
    for i in 0..nrdim {
        min_shape[i] = (tile[i] as f64 * tolerance) as i64;
        max_shape[i] = (tile[i] as f64 / tolerance + 0.5) as i64;
        if min_shape[i] > max_shape[i] {
            std::mem::swap(&mut min_shape[i], &mut max_shape[i]);
        }
        min_shape[i] = min_shape[i].max(1);
        max_shape[i] = max_shape[i].min(cube[i]);
        cube_space *= cube[i] as f64;
    }
    let mut values: Vec<Vec<i64>> = Vec::with_capacity(nrdim);
    for i in 0..nrdim {
        let mut v: Vec<i64> = (min_shape[i]..=max_shape[i])
            .filter(|&j| cube[i] % j == 0)
            .collect();
        if v.is_empty() {
            v = ((tile[i] + min_shape[i]) / 2..=(tile[i] + max_shape[i]) / 2).collect();
        }
        values.push(v);
    }
    let mut done = vec![0usize; nrdim];
    let mut tshape: Vec<i64> = values.iter().map(|v| v[0]).collect();
    let mut min_cost = 1_000_000f64;
    loop {
        let mut total_size = 1i64;
        let mut total_space = 1f64;
        let mut cost_axes = 0f64;
        for i in 0..nrdim {
            total_size *= tshape[i];
            let ntile = (cube[i] + tshape[i] - 1) / tshape[i];
            total_space *= (ntile * tshape[i]) as f64;
            cost_axes += (tile[i] - tshape[i]).abs() as f64 / tile[i] as f64;
        }
        let waste = (total_space - cube_space) / cube_space;
        let diff = (total_size as f64 - npix as f64).abs() / npix as f64;
        let cost = cost_axes + 10.0 * waste + diff;
        if cost < min_cost {
            best = tshape.clone();
            min_cost = cost;
        }
        let mut i = 0;
        while i < nrdim {
            done[i] += 1;
            if done[i] < values[i].len() {
                tshape[i] = values[i][done[i]];
                break;
            }
            done[i] = 0;
            tshape[i] = values[i][0];
            i += 1;
        }
        if i == nrdim {
            break;
        }
    }
    for i in 0..nrdim {
        let ntile = (cube[i] + best[i] - 1) / best[i];
        best[i] = (cube[i] + ntile - 1) / ntile;
    }
    best
}

/// `TSMCube::adjustTileShape(cubeShape, tileShape)`: a tile of the cube's
/// length (tile axes not given or 0 computed with `make_tile_shape` for
/// about 32768 pixels in all, a given axis at most the cube's; the
/// extensible last axis, 0 in the cube, as given or from the rest of the
/// 32768 pixels). casacore's `Float rem` is kept in single precision.
pub fn adjust_tile_shape(cube: &[i64], tile: &[i64]) -> Vec<i64> {
    let nrdim = cube.len();
    let mut out = vec![0i64; nrdim];
    let mut unknown = Vec::new();
    let mut length: u32 = 1;
    for i in 0..nrdim {
        if i < tile.len() {
            out[i] = tile[i];
        }
        if out[i] == 0 {
            if cube[i] != 0 {
                unknown.push(cube[i]);
            }
        } else {
            if out[i] > cube[i] && cube[i] != 0 {
                out[i] = cube[i];
            }
            length = length.wrapping_mul(out[i] as u32);
        }
    }
    if !unknown.is_empty() {
        let rem = (32768.0f64 / f64::from(length)) as f32;
        let leng = ((f64::from(rem) + 0.5) as i32).max(1);
        let unk = make_tile_shape(&unknown, 0.5, leng as u64);
        length = length.wrapping_mul(unk.iter().product::<i64>() as u32);
        let mut j = 0;
        for o in out.iter_mut() {
            if *o == 0 && j < unk.len() {
                *o = unk[j];
                j += 1;
            }
        }
    }
    if cube[nrdim - 1] == 0 && out[nrdim - 1] == 0 {
        let rem = (32768.0f64 / f64::from(length)) as f32;
        out[nrdim - 1] = ((f64::from(rem) + 0.5) as i32).max(1) as i64;
    }
    out
}

/// A hypercube's values record from its object bytes in a tiled header.
pub fn parse_values(bytes: &[u8]) -> Result<Record> {
    let mut c = Cursor::new(bytes, true);
    let r = Record::read(&mut c)?;
    if c.pos != bytes.len() {
        return Err(MsError("trailing bytes after a hypercube record".into()));
    }
    Ok(r)
}

/// The object bytes of a hypercube's values record (`Record`, version 1,
/// no magic value, as nested in the tiled header).
pub fn values_bytes(r: &Record) -> Vec<u8> {
    let mut w = Writer::new(true);
    w.putstart("Holder", 1);
    r.write_kind(&mut w, "Record");
    w.putend();
    let holder = 4 + 4 + 4 + "Holder".len() + 4;
    w.buf[holder..].to_vec()
}

/// The `Record` field type code of an array of scalar type `code`.
fn array_code(code: i32) -> Option<i32> {
    crate::aipsio::tp::array_of(code)
}

/// The element bytes (canonical, big-endian) and shape of an array field.
pub fn array_field(r: &Record, name: &str) -> Option<(i32, Vec<i64>, Vec<u8>)> {
    let i = r.field(name)?;
    let dtype = r.desc.fields[i].dtype;
    let Value::Raw(raw) = &r.values[i] else {
        return None;
    };
    // An `Array<T>` object: length, type name, version 3, ndim, shape,
    // nelements, values.
    let mut c = Cursor::new(raw, true);
    let obj = c.start().ok()?;
    let ndim = c.u32().ok()? as usize;
    let shape = (0..ndim)
        .map(|_| c.u32().map(|s| i64::from(s as i32)))
        .collect::<Result<Vec<_>>>()
        .ok()?;
    let n = c.u32().ok()? as usize;
    let at = c.pos;
    let size = raw.len() - at;
    let _ = (obj, n);
    Some((dtype, shape, raw[at..at + size].to_vec()))
}

/// Define (or replace) the array field `name` of scalar type `code` with
/// native-endian `values` of `shape`.
pub fn define_array(
    r: &mut Record,
    name: &str,
    code: i32,
    shape: &[i64],
    values: &[u8],
) -> Result<()> {
    if array_code(code).is_none() {
        return Err(MsError(format!("no array type for type {code}")));
    }
    r.define(
        name,
        KeywordValue::Array(code, shape.to_vec(), values.to_vec()),
    )
}
