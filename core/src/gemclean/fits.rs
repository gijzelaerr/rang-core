//! A minimal FITS writer (and reader, for tests) for gemclean's images.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! One primary HDU: 80-character header cards in 2880-byte blocks, then the
//! pixels big-endian (`BITPIX` −32 or −64), zero-padded to a block. The
//! image has four axes (`RA---SIN`, `DEC--SIN`, `FREQ`, `STOKES`) as
//! WSClean writes them, with the WCS of `rang.core_grid.wcs_header`. Pixel
//! order follows WSClean's FITS files: the data are `[y][x]`, and FITS
//! pixel `(x, y)` is the gridder's pixel `x * n + y` with `flip_v` and
//! `flip_w` set (`research/clean-certified-imaging.md` §3).

use std::io::Write;
use std::path::Path;

/// A header value.
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Logical(bool),
    Int(i64),
    Float(f64),
    Str(String),
}

/// Header cards as read: keyword and raw value text.
pub type RawCards = Vec<(String, String)>;

/// One header card: keyword, value and an optional comment.
pub type Card = (String, Value, String);

pub fn card(key: &str, value: Value, comment: &str) -> Card {
    (key.to_string(), value, comment.to_string())
}

fn format_card(key: &str, value: &Value, comment: &str) -> Result<String, String> {
    if key.len() > 8
        || !key
            .bytes()
            .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'-' || b == b'_')
    {
        return Err(format!("invalid FITS keyword {key:?}"));
    }
    let v = match value {
        Value::Logical(b) => format!("{:>20}", if *b { "T" } else { "F" }),
        Value::Int(i) => format!("{i:>20}"),
        Value::Float(f) => {
            if !f.is_finite() {
                return Err(format!("{key}: a FITS value must be finite"));
            }
            format!("{:>20}", format!("{f:.15E}"))
        }
        Value::Str(s) => {
            if !s.is_ascii() {
                return Err(format!("{key}: FITS strings are ASCII"));
            }
            let quoted = s.replace('\'', "''");
            format!("'{quoted:<8}'")
        }
    };
    let mut text = format!("{key:<8}= {v}");
    if !comment.is_empty() {
        text.push_str(" / ");
        text.push_str(comment);
    }
    if !text.is_ascii() {
        return Err(format!("{key}: FITS comments are ASCII"));
    }
    text.truncate(80);
    Ok(format!("{text:<80}"))
}

/// Write `data` (`height` rows of `width`, FITS order `[y][x]`) as a
/// four-axis image with the given extra cards. `bitpix` is −32 or −64.
pub fn write(
    path: &Path,
    width: usize,
    height: usize,
    data: &[f64],
    bitpix: i32,
    cards: &[Card],
) -> Result<(), String> {
    if data.len() != width * height {
        return Err("data must be width × height".into());
    }
    if bitpix != -32 && bitpix != -64 {
        return Err("BITPIX must be -32 or -64".into());
    }
    let mut header = String::new();
    let mut put = |key: &str, value: Value, comment: &str| -> Result<(), String> {
        header.push_str(&format_card(key, &value, comment)?);
        Ok(())
    };
    put("SIMPLE", Value::Logical(true), "conforms to FITS")?;
    put("BITPIX", Value::Int(bitpix as i64), "IEEE floating point")?;
    put("NAXIS", Value::Int(4), "")?;
    put("NAXIS1", Value::Int(width as i64), "")?;
    put("NAXIS2", Value::Int(height as i64), "")?;
    put("NAXIS3", Value::Int(1), "")?;
    put("NAXIS4", Value::Int(1), "")?;
    put("EXTEND", Value::Logical(true), "")?;
    for (k, v, c) in cards {
        put(k, v.clone(), c)?;
    }
    header.push_str(&format!("{:<80}", "END"));
    while !header.len().is_multiple_of(2880) {
        header.push(' ');
    }
    let mut bytes = header.into_bytes();
    for &v in data {
        if bitpix == -32 {
            bytes.extend_from_slice(&(v as f32).to_be_bytes());
        } else {
            bytes.extend_from_slice(&v.to_be_bytes());
        }
    }
    while !bytes.len().is_multiple_of(2880) {
        bytes.push(0);
    }
    let mut file = std::fs::File::create(path).map_err(|e| format!("{}: {e}", path.display()))?;
    file.write_all(&bytes)
        .map_err(|e| format!("{}: {e}", path.display()))
}

/// Read a file written by [`write`]: the header cards as `(key, raw value
/// text)` and the pixels as `f64` in FITS order.
pub fn read(path: &Path) -> Result<(RawCards, Vec<f64>), String> {
    let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut cards = Vec::new();
    let mut pos = 0;
    loop {
        if pos + 80 > bytes.len() {
            return Err("no END card".into());
        }
        let text = String::from_utf8_lossy(&bytes[pos..pos + 80]).to_string();
        pos += 80;
        let key = text[..8].trim().to_string();
        if key == "END" {
            break;
        }
        if text.len() > 10 && &text[8..10] == "= " {
            let rest = &text[10..];
            let value = if rest.trim_start().starts_with('\'') {
                let start = rest.find('\'').unwrap() + 1;
                let end = rest[start..].find('\'').map_or(rest.len(), |e| start + e);
                rest[start..end].trim_end().to_string()
            } else {
                rest.split('/').next().unwrap_or("").trim().to_string()
            };
            cards.push((key, value));
        }
    }
    let data_start = pos.div_ceil(2880) * 2880;
    let get = |k: &str| -> Result<i64, String> {
        cards
            .iter()
            .find(|(key, _)| key == k)
            .ok_or(format!("{k} missing"))?
            .1
            .parse()
            .map_err(|e| format!("{k}: {e}"))
    };
    let bitpix = get("BITPIX")?;
    let count = (get("NAXIS1")? * get("NAXIS2")?) as usize;
    let size = if bitpix == -32 { 4 } else { 8 };
    let raw = bytes
        .get(data_start..data_start + count * size)
        .ok_or("truncated data")?;
    let data = raw
        .chunks_exact(size)
        .map(|c| {
            if size == 4 {
                f32::from_be_bytes(c.try_into().unwrap()) as f64
            } else {
                f64::from_be_bytes(c.try_into().unwrap())
            }
        })
        .collect();
    Ok((cards, data))
}

/// FITS order of a square gridder image: `fits[y * n + x] = grid[x * n + y]`.
pub fn gridder_to_fits(n: usize, grid: &[f64]) -> Vec<f64> {
    let mut out = vec![0.0; n * n];
    for y in 0..n {
        for x in 0..n {
            out[y * n + x] = grid[x * n + y];
        }
    }
    out
}

/// The WCS cards of `rang.core_grid.wcs_header`: a SIN image of `n × n`
/// pixels of `scale` radians at the phase centre `(ra, dec)` (radians), the
/// frequency axis spanning the channel edges.
pub fn wcs_cards(ra: f64, dec: f64, n: usize, scale: f64, freq: &[f64]) -> Vec<Card> {
    let mut ra_deg = ra.to_degrees();
    if ra_deg > 180.0 {
        ra_deg -= 360.0;
    }
    let step = if freq.len() > 1 {
        freq[1] - freq[0]
    } else {
        0.0
    };
    let low = freq.first().copied().unwrap_or(0.0) - step / 2.0;
    let high = freq.last().copied().unwrap_or(0.0) + step / 2.0;
    let deg = scale.to_degrees();
    let crpix = (n / 2 + 1) as f64;
    vec![
        card("BSCALE", Value::Float(1.0), ""),
        card("BZERO", Value::Float(0.0), ""),
        card(
            "BUNIT",
            Value::Str("JY/BEAM".into()),
            "Units are in Jansky per beam",
        ),
        card("BTYPE", Value::Str("Intensity".into()), ""),
        card("EQUINOX", Value::Float(2000.0), "J2000"),
        card("LONPOLE", Value::Float(180.0), ""),
        card(
            "CTYPE1",
            Value::Str("RA---SIN".into()),
            "Right ascension angle cosine",
        ),
        card("CRPIX1", Value::Float(crpix), ""),
        card("CRVAL1", Value::Float(ra_deg), ""),
        card("CDELT1", Value::Float(-deg), ""),
        card("CUNIT1", Value::Str("deg".into()), ""),
        card(
            "CTYPE2",
            Value::Str("DEC--SIN".into()),
            "Declination angle cosine",
        ),
        card("CRPIX2", Value::Float(crpix), ""),
        card("CRVAL2", Value::Float(dec.to_degrees()), ""),
        card("CDELT2", Value::Float(deg), ""),
        card("CUNIT2", Value::Str("deg".into()), ""),
        card("CTYPE3", Value::Str("FREQ".into()), "Central frequency"),
        card("CRPIX3", Value::Float(1.0), ""),
        card("CRVAL3", Value::Float((low + high) / 2.0), ""),
        card("CDELT3", Value::Float(high - low), ""),
        card("CUNIT3", Value::Str("Hz".into()), ""),
        card("CTYPE4", Value::Str("STOKES".into()), ""),
        card("CRPIX4", Value::Float(1.0), ""),
        card("CRVAL4", Value::Float(1.0), ""),
        card("CDELT4", Value::Float(1.0), ""),
        card("CUNIT4", Value::Str("".into()), ""),
        card("SPECSYS", Value::Str("TOPOCENT".into()), ""),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_header_blocks_and_orientation() {
        let dir = std::env::temp_dir().join(format!("gemclean-fits-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let n = 6;
        // A gridder image with one off-centre pixel at (x = 4, y = 1).
        let mut grid = vec![0.0; n * n];
        grid[4 * n + 1] = 3.0;
        let fits = gridder_to_fits(n, &grid);
        assert_eq!(fits[n + 4], 3.0);
        let scale = (8.0 / 3600.0_f64).to_radians();
        let mut cards = wcs_cards(5.1461782, -1.11199581, n, scale, &[1e9, 1.1e9]);
        cards.push(card("BMAJ", Value::Float(0.01), ""));
        cards.push(card("ORIGIN", Value::Str("gemclean test".into()), ""));
        for bitpix in [-32, -64] {
            let path = dir.join(format!("t{}.fits", -bitpix));
            write(&path, n, n, &fits, bitpix, &cards).unwrap();
            let len = std::fs::metadata(&path).unwrap().len();
            assert_eq!(len % 2880, 0);
            let (back_cards, back) = read(&path).unwrap();
            assert_eq!(back[n + 4], 3.0);
            assert_eq!(back.iter().filter(|&&v| v != 0.0).count(), 1);
            let get = |k: &str| {
                back_cards
                    .iter()
                    .find(|(key, _)| key == k)
                    .unwrap()
                    .1
                    .clone()
            };
            assert_eq!(get("CTYPE1"), "RA---SIN");
            assert_eq!(get("CRPIX1").parse::<f64>().unwrap(), 4.0);
            assert!((get("CRVAL1").parse::<f64>().unwrap() + 65.1457083333333).abs() < 1e-6);
            assert!((get("CRVAL2").parse::<f64>().unwrap() + 63.7126666666667).abs() < 1e-6);
            assert_eq!(get("ORIGIN"), "gemclean test");
            assert!((get("CDELT2").parse::<f64>().unwrap() - 8.0 / 3600.0).abs() < 1e-15);
            assert_eq!(get("NAXIS"), "4");
        }
        std::fs::remove_dir_all(&dir).unwrap();
        assert!(format_card("lower", &Value::Int(1), "").is_err());
    }
}
