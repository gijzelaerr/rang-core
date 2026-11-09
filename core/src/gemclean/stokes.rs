//! Polarisations for gemclean: WSClean 3.7's `-pol` list, the conversion of
//! linear-feed correlations to Stokes I, Q, U, V (and XX, YY as they are), the
//! weights of each, and the rules that pick which polarisation's weights build
//! the imaging-weight grid (`research/g9-stokes.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The sources, WSClean v3.7 (`4f395b2`) and its submodules:
//!
//! - `aocommon/polarization.h`, `Polarization::ParseList`: the list is parsed
//!   case-insensitively with `,`, ` ` or `/` between entries, into a set in
//!   enum order I < Q < U < V < RR < RL < LR < LL < XX < XY < YX < YY. The first
//!   of the set images the PSF (`WSClean::runIndependentGroup`).
//! - `schaapcommon/reordering/reordering.cc`, `ExtractData` and
//!   `ExtractWeights`: a correlation the MS holds is copied, with its own weight
//!   (zero when flagged or not finite); I = (XX + YY)/2, Q = (XX − YY)/2,
//!   U = (XY + YX)/2, V = −i (XY − YX)/2, each with the weight
//!   `min(4 w_a, 4 w_b)` of its two correlations (zero when either is flagged
//!   or not finite) and zero where the formed value is not finite.
//! - `radler/cpp/image_set.h`: the polarisation normalisation of joined
//!   polarisations, `1/P` for Stokes parameters without I, `0.5` for a dual
//!   (XX, YY) or full linear set, else 1.
//!
//! XY, YX (complex images) and circular correlations are not ported.

use std::fmt;

/// A polarisation gemclean images, in WSClean's enum order.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Pol {
    I,
    Q,
    U,
    V,
    XX,
    YY,
}

impl Pol {
    /// WSClean's short name (file names: `-I-`, `-XX-`).
    pub fn name(self) -> &'static str {
        match self {
            Pol::I => "I",
            Pol::Q => "Q",
            Pol::U => "U",
            Pol::V => "V",
            Pol::XX => "XX",
            Pol::YY => "YY",
        }
    }

    /// The FITS `STOKES` axis value WSClean writes (`CRVAL4`).
    pub fn fits_code(self) -> f64 {
        match self {
            Pol::I => 1.0,
            Pol::Q => 2.0,
            Pol::U => 3.0,
            Pol::V => 4.0,
            Pol::XX => -5.0,
            Pol::YY => -6.0,
        }
    }

    pub fn is_stokes(self) -> bool {
        matches!(self, Pol::I | Pol::Q | Pol::U | Pol::V)
    }
}

impl fmt::Display for Pol {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.name())
    }
}

/// The entries WSClean's parser knows; those gemclean does not image are
/// refused after parsing.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Parsed {
    I,
    Q,
    U,
    V,
    RR,
    RL,
    LR,
    LL,
    XX,
    XY,
    YX,
    YY,
}

/// WSClean's `-pol` list (`Polarization::ParseList`), as a set in enum order.
pub fn parse_list(list: &str) -> Result<Vec<Pol>, String> {
    #[derive(PartialEq)]
    enum St {
        Start,
        X,
        Y,
        L,
        R,
        Sep,
    }
    let bad = |c: &str| Err(format!("-pol {list:?}: parse error near '{c}'"));
    let mut set: Vec<Parsed> = Vec::new();
    let mut state = St::Start;
    for ch in list.chars() {
        let c = ch.to_ascii_uppercase();
        let fresh = state == St::Start || state == St::Sep;
        match c {
            'X' | 'Y' | 'R' | 'L' if fresh => {
                state = match c {
                    'X' => St::X,
                    'Y' => St::Y,
                    'R' => St::R,
                    _ => St::L,
                };
            }
            'X' | 'Y' | 'R' | 'L' => {
                let p = match (&state, c) {
                    (St::X, 'X') => Parsed::XX,
                    (St::Y, 'X') => Parsed::YX,
                    (St::X, 'Y') => Parsed::XY,
                    (St::Y, 'Y') => Parsed::YY,
                    (St::R, 'R') => Parsed::RR,
                    (St::L, 'R') => Parsed::LR,
                    (St::R, 'L') => Parsed::RL,
                    (St::L, 'L') => Parsed::LL,
                    _ => return bad(&c.to_string()),
                };
                set.push(p);
                state = St::Start;
            }
            'I' | 'Q' | 'U' | 'V' => {
                if !fresh {
                    return bad(&c.to_string());
                }
                set.push(match c {
                    'I' => Parsed::I,
                    'Q' => Parsed::Q,
                    'U' => Parsed::U,
                    _ => Parsed::V,
                });
                state = St::Start;
            }
            ',' | ' ' | '/' => {
                if state != St::Start {
                    return bad("separator");
                }
                state = St::Sep;
            }
            other => return Err(format!("-pol {list:?}: unexpected symbol '{other}'")),
        }
    }
    if state != St::Start {
        return bad("string end");
    }
    set.sort();
    set.dedup();
    if set.is_empty() {
        return Err("-pol needs at least one polarisation".into());
    }
    let mut out = Vec::with_capacity(set.len());
    for p in set {
        out.push(match p {
            Parsed::I => Pol::I,
            Parsed::Q => Pol::Q,
            Parsed::U => Pol::U,
            Parsed::V => Pol::V,
            Parsed::XX => Pol::XX,
            Parsed::YY => Pol::YY,
            Parsed::XY | Parsed::YX => {
                return Err(format!(
                    "-pol {list:?}: XY and YX (complex images) are not implemented \
                     (research/g9-stokes.md, owner decisions); image U and V instead"
                ));
            }
            _ => {
                return Err(format!(
                    "-pol {list:?}: circular correlations (RR, RL, LR, LL) are not \
                     implemented (research/g9-stokes.md, owner decisions)"
                ));
            }
        });
    }
    Ok(out)
}

/// radler's `polarization_normalization_factor_` for a joined set.
pub fn normalisation(pols: &[Pol]) -> f64 {
    let stokes_without_i = pols.iter().all(|&p| p.is_stokes() && p != Pol::I);
    let dual = pols == [Pol::XX, Pol::YY];
    if stokes_without_i {
        1.0 / pols.len() as f64
    } else if dual {
        0.5
    } else {
        1.0
    }
}

/// Indices into `CORR_TYPE` of the correlations `pol` is formed from: one
/// (copied as it is) or two (a pair). Linear correlations only, besides
/// Stokes I from RR and LL or an I column as gemclean read them before.
pub fn correlation_indices(pol: Pol, corr: &[i32]) -> Result<(usize, usize, bool), String> {
    let find = |code: i32| corr.iter().position(|&c| c == code);
    let pair = |a: i32, b: i32| match (find(a), find(b)) {
        (Some(i), Some(j)) => Ok((i, j, false)),
        _ => Err(format!(
            "can not form the requested polarisation (Stokes {pol}) from the \
             available correlations {corr:?}"
        )),
    };
    match pol {
        Pol::I => unreachable!("Stokes I is read by input::read_ms's own rule"),
        Pol::Q => pair(9, 12),
        Pol::U | Pol::V => pair(10, 11),
        Pol::XX | Pol::YY => {
            let code = if pol == Pol::XX { 9 } else { 12 };
            find(code)
                .map(|i| (i, i, true))
                .ok_or_else(|| format!("the MS has no {pol} correlation (CORR_TYPE {corr:?})"))
        }
    }
}

/// One cell of `pol` from its correlations `a`, `b` (`ExtractData`,
/// `ExtractWeights`); `direct` copies correlation `a` with its own weight.
pub fn cell(
    pol: Pol,
    d: &[f32],
    w: &[f32],
    f: &[u8],
    a: usize,
    b: usize,
    direct: bool,
) -> ((f32, f32), f32) {
    let finite = |re: f32, im: f32| re.is_finite() && im.is_finite();
    let (ar, ai, br, bi) = (d[2 * a], d[2 * a + 1], d[2 * b], d[2 * b + 1]);
    if direct {
        let ok = f[a] == 0 && finite(ar, ai);
        let v = if finite(ar, ai) { (ar, ai) } else { (0.0, 0.0) };
        return (v, if ok { w[a] } else { 0.0 });
    }
    let (re, im) = match pol {
        // Q = (XX − YY)/2, U = (XY + YX)/2 (float arithmetic as WSClean's).
        Pol::Q => ((ar - br) * 0.5, (ai - bi) * 0.5),
        Pol::U => ((ar + br) * 0.5, (ai + bi) * 0.5),
        // V = −i (XY − YX)/2: (XY − YX)/2 = (x, y), then (y, −x).
        Pol::V => {
            let (x, y) = ((ar - br) * 0.5, (ai - bi) * 0.5);
            (y, -x)
        }
        _ => unreachable!("I, XX and YY are not formed from a pair here"),
    };
    let v = if finite(re, im) { (re, im) } else { (0.0, 0.0) };
    let mut weight = if f[a] == 0 && finite(ar, ai) {
        w[a] * 4.0
    } else {
        0.0
    };
    weight = if f[b] == 0 && finite(br, bi) {
        let bw = w[b] * 4.0;
        if bw < weight { bw } else { weight }
    } else {
        0.0
    };
    (v, weight)
}

/// Which polarisations' weights build the imaging-weight grid of an output
/// channel, as WSClean 3.7's image-weight cache ends up using them
/// (`ImageWeightCache::Get` keyed on the channel only, the run order of
/// `WSClean::runIndependentGroup`, `InitializeMfWeights` over the squared
/// groups). Indices into the imaged polarisations.
///
/// - MF weighting: one grid of all channels, from the first polarisation when
///   the polarisations are joined (one squared group per channel), else from
///   every polarisation (each entry is a squared group of its own).
/// - Per-channel weighting: the first polarisation, except with joined
///   channels, more than one output channel and polarisations not joined,
///   where each polarisation's run recomputes the cache from its own weights.
pub fn weight_sources(
    npol: usize,
    pol: usize,
    mf: bool,
    join_pols: bool,
    join_channels: bool,
    channels_out: usize,
) -> Vec<usize> {
    if mf {
        if join_pols {
            vec![0]
        } else {
            (0..npol).collect()
        }
    } else if join_channels && channels_out > 1 && !join_pols {
        vec![pol]
    } else {
        vec![0]
    }
}

/// The imaging weights (`rows × chans.len()`, in `chans`' order) of one
/// WSClean weight grid built from the visibility weights of every data set in
/// `sources` over the channels `chans`, with the settings of
/// [`super::input::gridding_weights`] (padding 1.2, rank filter 3 over 16
/// cells). The sources share their rows and uvw (one MS, other
/// polarisations); with one source and every channel this is the imaging
/// weight `gridding_weights` multiplies by.
pub fn imaging_weights(
    sources: &[&super::input::StokesI],
    chans: &[usize],
    class: crate::weights::WeightClass,
    size: usize,
    scale: f64,
) -> Result<Vec<f32>, String> {
    use crate::weights::{WeightGrid, WeightSettings, padded_size};
    let first = sources.first().ok_or("no weight source")?;
    let padded = padded_size(size, 1.2);
    let s = WeightSettings {
        class,
        width: padded,
        height: padded,
        scale_x: scale,
        scale_y: scale,
        super_weight: 1.0,
        rank_filter_level: 3.0,
        rank_filter_size: 16,
    };
    let nchan = first.freq.len();
    let all = chans.len() == nchan && chans.iter().enumerate().all(|(i, &c)| i == c);
    let wavelength: Vec<f64> = chans
        .iter()
        .map(|&c| super::input::SPEED_OF_LIGHT / first.freq[c])
        .collect();
    let rows = first.rows();
    let selected = vec![true; rows];
    let mut grid = WeightGrid::new(
        s.class,
        s.width,
        s.height,
        s.scale_x,
        s.scale_y,
        s.super_weight,
    )
    .map_err(|e| e.to_string())?;
    for src in sources {
        if src.rows() != rows || src.freq.len() != nchan {
            return Err("weight sources must share rows and channels".into());
        }
        if all {
            grid.grid_rows(&src.uvw, &wavelength, &src.weight, &selected)
        } else {
            let mut w = Vec::with_capacity(rows * chans.len());
            for row in 0..rows {
                for &c in chans {
                    w.push(src.weight[row * nchan + c]);
                }
            }
            grid.grid_rows(&src.uvw, &wavelength, &w, &selected)
        }
        .map_err(|e| e.to_string())?;
    }
    grid.finish().map_err(|e| e.to_string())?;
    if s.rank_filter_level >= 1.0 {
        grid.rank_filter(s.rank_filter_level, s.rank_filter_size);
    }
    let mut out = vec![0.0f32; rows * chans.len()];
    grid.lookup_rows(&first.uvw, &wavelength, &selected, &mut out)
        .map_err(|e| e.to_string())?;
    Ok(out)
}

/// Replace `CRVAL4` of WSClean's header cards with `pol`'s value.
pub fn set_stokes_card(cards: &mut [super::fits::Card], pol: Pol) {
    for c in cards.iter_mut() {
        if c.0 == "CRVAL4" {
            c.1 = super::fits::Value::Float(pol.fits_code());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lists_parse_as_wsclean_parses_them() {
        assert_eq!(parse_list("I").unwrap(), [Pol::I]);
        assert_eq!(
            parse_list("iquv").unwrap(),
            [Pol::I, Pol::Q, Pol::U, Pol::V]
        );
        assert_eq!(
            parse_list("VUQI").unwrap(),
            [Pol::I, Pol::Q, Pol::U, Pol::V]
        );
        assert_eq!(parse_list("xx,yy").unwrap(), [Pol::XX, Pol::YY]);
        assert_eq!(parse_list("YY/XX").unwrap(), [Pol::XX, Pol::YY]);
        assert_eq!(parse_list("Q U").unwrap(), [Pol::Q, Pol::U]);
        assert_eq!(parse_list("II").unwrap(), [Pol::I]);
        assert!(parse_list("XY,YX").unwrap_err().contains("complex"));
        assert!(parse_list("RR").unwrap_err().contains("circular"));
        assert!(parse_list("X").is_err());
        assert!(parse_list("XQ").is_err());
        assert!(parse_list("I,,Q").is_err());
        assert!(parse_list("Z").is_err());
        assert!(parse_list("").is_err());
    }

    #[test]
    fn normalisation_follows_radler() {
        assert_eq!(normalisation(&[Pol::I, Pol::Q, Pol::U, Pol::V]), 1.0);
        assert_eq!(normalisation(&[Pol::Q, Pol::U]), 0.5);
        assert_eq!(normalisation(&[Pol::Q, Pol::U, Pol::V]), 1.0 / 3.0);
        assert_eq!(normalisation(&[Pol::XX, Pol::YY]), 0.5);
        assert_eq!(normalisation(&[Pol::I, Pol::V]), 1.0);
    }

    /// The four Stokes parameters of XX = I + Q, XY = U + iV, YX = U − iV,
    /// YY = I − Q come back, with WSClean's weights.
    #[test]
    fn stokes_of_the_sky_frame_coherencies() {
        let (i, q, u, v) = (1.0f32, 0.25f32, -0.5f32, 0.125f32);
        // Corr order XX, XY, YX, YY; a small imaginary part on Q and I.
        let d = [i + q, 0.5, u, v, u, -v, i - q, 0.5];
        let w = [1.0, 2.0, 3.0, 4.0];
        let f = [0u8; 4];
        let corr = [9, 10, 11, 12];
        let get = |p| {
            let (a, b, direct) = correlation_indices(p, &corr).unwrap();
            cell(p, &d, &w, &f, a, b, direct)
        };
        assert_eq!(get(Pol::Q), ((q, 0.0), 4.0));
        assert_eq!(get(Pol::U), ((u, 0.0), 8.0));
        assert_eq!(get(Pol::V), ((v, 0.0), 8.0));
        assert_eq!(get(Pol::XX), ((i + q, 0.5), 1.0));
        assert_eq!(get(Pol::YY), ((i - q, 0.5), 4.0));
        // A flag on one hand of the pair zeroes the pair's weight only.
        let f = [0u8, 1, 0, 0];
        let (a, b, _) = correlation_indices(Pol::U, &corr).unwrap();
        assert_eq!(cell(Pol::U, &d, &w, &f, a, b, false).1, 0.0);
        let (a, b, _) = correlation_indices(Pol::Q, &corr).unwrap();
        assert_eq!(cell(Pol::Q, &d, &w, &f, a, b, false).1, 4.0);
        assert!(correlation_indices(Pol::U, &[9, 12]).is_err());
        assert!(correlation_indices(Pol::XX, &[1]).is_err());
    }

    #[test]
    fn weight_sources_follow_the_cache() {
        // IQUV, one channel, not joined: I's weights for every polarisation.
        assert_eq!(weight_sources(4, 2, false, false, false, 1), [0]);
        // Joined channels without MF weighting, pols not joined: each its own.
        assert_eq!(weight_sources(4, 2, false, false, true, 2), [2]);
        assert_eq!(weight_sources(4, 2, false, true, true, 2), [0]);
        assert_eq!(weight_sources(4, 2, true, false, true, 2), [0, 1, 2, 3]);
        assert_eq!(weight_sources(4, 2, true, true, true, 2), [0]);
    }
}
