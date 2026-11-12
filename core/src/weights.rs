// SPDX-License-Identifier: GPL-3.0-or-later
//! WSClean 3.6 imaging weights and Stokes I formation, ported from source.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Upstream copyright, verbatim from `debian/copyright` of wsclean 3.6-1
//! (WSClean's source files carry no notice of their own):
//! Copyright: 2008-2015 A. R. Offringa
//!  2009 ASTRON (Netherlands Institute for Radio Astronomy)
//!  2014-2016 Gijs Molenaar <gijs@pythonic.nl>
//! License: GPL-3.0+
//!
//! A Rust translation of the weighting path of WSClean 3.6 (GPL-3.0-or-later,
//! André Offringa and contributors): `structures/imageweights.{h,cpp}`
//! (gridding, Briggs/uniform/natural finish, rank filter, lookup),
//! `main/settings.cpp` (padded image size), the Stokes I rules of
//! `schaapcommon/reordering/reordering.cc` and `aocommon/polarization.h`, and
//! the weight sums of `gridding/msgridderdata.h`. Validation protocol:
//! `research/core-b-weighting.md`. Arithmetic order and precision follow the
//! C++ (float weights accumulated in doubles, float lookups), so results are
//! meant to be bit-identical to WSClean's `-store-imaging-weights` column.

/// The weighting class of `-weight natural|uniform|briggs <robust>`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum WeightClass {
    Natural,
    Uniform,
    Briggs(f64),
}

/// WSClean's padded image size: `ceil(trimmed * padding)` rounded up to a
/// multiple of four. `trimmed` is the even `-size` value.
pub fn padded_size(trimmed: usize, padding: f64) -> usize {
    let mut padded = (trimmed as f64 * padding).ceil() as usize;
    padded += (4 - (padded % 4)) % 4;
    padded
}

/// The half-plane weight grid of `ImageWeights`.
#[derive(Clone, Debug)]
pub struct WeightGrid {
    class: WeightClass,
    width: usize,
    height: usize,
    scale_x: f64,
    scale_y: f64,
    grid: Vec<f64>,
    total: f64,
    finished: bool,
}

/// Sums that WSClean writes to the FITS header after applying the weights.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct WeightSums {
    /// `WSCVWSUM`: visibility weights where the applied weight is non-zero.
    pub visibility_weight_sum: f64,
    /// `WSCIMGWG` and `WSCNORMF`: applied (visibility × imaging) weights.
    pub total_weight: f64,
    pub max_gridded_weight: f64,
    /// `WSCNVIS`: visibilities with a non-zero applied weight.
    pub count: u64,
}

impl WeightGrid {
    /// `width` and `height` are the padded image size; `super_weight` is
    /// `-super-weight` (1.0 by default).
    pub fn new(
        class: WeightClass,
        width: usize,
        height: usize,
        scale_x: f64,
        scale_y: f64,
        super_weight: f64,
    ) -> Result<Self, &'static str> {
        if width == 0
            || height == 0
            || super_weight.partial_cmp(&0.0) != Some(std::cmp::Ordering::Greater)
            || scale_x <= 0.0
            || scale_y <= 0.0
        {
            return Err("positive grid size, scales and super weight required");
        }
        let (width, height) = Self::shape(width, height, super_weight);
        Ok(Self {
            class,
            width,
            height,
            scale_x,
            scale_y,
            grid: vec![0.0; width * height / 2],
            total: 0.0,
            finished: false,
        })
    }

    /// The grid shape after the super weight: rounded, then made even.
    pub fn shape(width: usize, height: usize, super_weight: f64) -> (usize, usize) {
        let mut w = (width as f64 / super_weight).round() as usize;
        let mut h = (height as f64 / super_weight).round() as usize;
        if !w.is_multiple_of(2) {
            w += 1;
        }
        if !h.is_multiple_of(2) {
            h += 1;
        }
        (w, h)
    }

    pub fn width(&self) -> usize {
        self.width
    }

    pub fn height(&self) -> usize {
        self.height
    }

    /// The half-plane cells, row-major, `width * height / 2` values.
    pub fn cells(&self) -> &[f64] {
        &self.grid
    }

    pub fn total(&self) -> f64 {
        self.total
    }

    fn uv_to_xy(&self, mut u: f64, mut v: f64) -> (i64, i64) {
        if v < 0.0 {
            u = -u;
            v = -v;
        }
        // The C++ adds the integer `width / 2` after the double products.
        let x = (u * self.width as f64 * self.scale_x + (self.width / 2) as f64).floor();
        let y = (v * self.height as f64 * self.scale_y).floor();
        (x as i64, y as i64)
    }

    fn within(&self, x: i64, y: i64) -> bool {
        x >= 0 && x < self.width as i64 && y < (self.height / 2) as i64
    }

    /// Add one sample at (u, v) in wavelengths with a float weight.
    pub fn grid_sample(&mut self, u: f64, v: f64, weight: f32) {
        let (x, y) = self.uv_to_xy(u, v);
        if self.within(x, y) {
            self.grid[x as usize + y as usize * self.width] += f64::from(weight);
            self.total += f64::from(weight);
        }
    }

    /// Grid every selected row and channel as `ImageWeights::Grid` does:
    /// `uvw` is `nrow × 3` metres, `wavelength` has `nchan` values and
    /// `weights` is `nrow × nchan` Stokes I weights (zero where flagged).
    pub fn grid_rows(
        &mut self,
        uvw: &[f64],
        wavelength: &[f64],
        weights: &[f32],
        selected: &[bool],
    ) -> Result<(), &'static str> {
        if self.finished {
            return Err("grid already finished");
        }
        let nrow = selected.len();
        let nchan = wavelength.len();
        if uvw.len() != 3 * nrow || weights.len() != nrow * nchan {
            return Err("uvw, wavelength, weights and selection lengths disagree");
        }
        for row in 0..nrow {
            if !selected[row] {
                continue;
            }
            let (mut u_m, mut v_m) = (uvw[3 * row], uvw[3 * row + 1]);
            if v_m < 0.0 {
                u_m = -u_m;
                v_m = -v_m;
            }
            for (ch, &lambda) in wavelength.iter().enumerate() {
                self.grid_sample(u_m / lambda, v_m / lambda, weights[row * nchan + ch]);
            }
        }
        Ok(())
    }

    /// `ImageWeights::FinishGridding`.
    pub fn finish(&mut self) -> Result<(), &'static str> {
        if self.finished {
            return Err("grid already finished");
        }
        self.finished = true;
        match self.class {
            WeightClass::Briggs(robust) => {
                let mut avg_w = 0.0;
                for &val in &self.grid {
                    avg_w += val * val;
                }
                avg_w /= self.total;
                let numerator_sqrt = 5.0 * (-std::f64::consts::LN_10 * robust).exp();
                let s_sq = numerator_sqrt * numerator_sqrt / avg_w;
                for val in &mut self.grid {
                    if *val != 0.0 {
                        *val = 1.0 / (1.0 + *val * s_sq);
                    }
                }
            }
            WeightClass::Uniform => {
                for val in &mut self.grid {
                    if *val != 0.0 {
                        *val = 1.0 / *val;
                    }
                }
            }
            WeightClass::Natural => {
                for val in &mut self.grid {
                    if *val != 0.0 {
                        *val = 1.0;
                    }
                }
            }
        }
        Ok(())
    }

    fn window_mean(&self, x: usize, y: usize, window: usize) -> f64 {
        let d = window / 2;
        let half = self.height / 2;
        let x1 = x.saturating_sub(d);
        let y1 = y.saturating_sub(d);
        let x2 = if x + d >= self.width {
            self.width
        } else {
            x + d
        };
        let y2 = if y + d >= half { half } else { y + d };
        let mut count = 0usize;
        let mut sum = 0.0;
        for yi in y1..y2 {
            for xi in x1..x2 {
                let w = self.grid[yi * self.width + xi];
                if w != 0.0 {
                    count += 1;
                    sum += w;
                }
            }
        }
        sum / count as f64
    }

    /// `ImageWeights::RankFilter`: clip cells above `limit × window mean`.
    pub fn rank_filter(&mut self, limit: f64, window: usize) {
        let mut new_grid = self.grid.clone();
        for y in 0..self.height / 2 {
            for x in 0..self.width {
                let w = self.grid[y * self.width + x];
                if w != 0.0 {
                    let mean = self.window_mean(x, y, window);
                    if w > mean * limit {
                        new_grid[y * self.width + x] = mean * limit;
                    }
                }
            }
        }
        self.grid = new_grid;
    }

    /// `ImageWeights::GetWeight`: the cell value at (u, v), zero outside.
    pub fn sample(&self, u: f64, v: f64) -> f64 {
        let (x, y) = self.uv_to_xy(u, v);
        if self.within(x, y) {
            self.grid[x as usize + y as usize * self.width]
        } else {
            0.0
        }
    }

    /// Look up the imaging weight of every selected row and channel as
    /// `CalculateWeightsImplementation` does, as floats; unselected rows get
    /// zero.
    pub fn lookup_rows(
        &self,
        uvw: &[f64],
        wavelength: &[f64],
        selected: &[bool],
        out: &mut [f32],
    ) -> Result<(), &'static str> {
        let nrow = selected.len();
        let nchan = wavelength.len();
        if uvw.len() != 3 * nrow || out.len() != nrow * nchan {
            return Err("uvw, wavelength, output and selection lengths disagree");
        }
        for row in 0..nrow {
            let cells = &mut out[row * nchan..(row + 1) * nchan];
            if !selected[row] {
                cells.fill(0.0);
                continue;
            }
            for (ch, &lambda) in wavelength.iter().enumerate() {
                let u = uvw[3 * row] / lambda;
                let v = uvw[3 * row + 1] / lambda;
                cells[ch] = self.sample(u, v) as f32;
            }
        }
        Ok(())
    }
}

/// WSClean 3.7's weight tapers and uv-range cuts (task G4,
/// `research/g4-masks.md`): `-taper-gaussian` (the beam size in radians),
/// `-minuv-l`, `-maxuv-l`, `-taper-tukey`, `-taper-inner-tukey`,
/// `-taper-edge` and `-taper-edge-tukey` (wavelengths). Zero is off. They
/// act on the cells of the weight grid, evaluated at each cell's lower
/// corner (`xyToUV`), not on the visibilities.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct UvTapers {
    pub gaussian_beam: f64,
    pub min_uv_l: f64,
    pub max_uv_l: f64,
    pub tukey: f64,
    pub inner_tukey: f64,
    pub edge: f64,
    pub edge_tukey: f64,
}

impl UvTapers {
    /// Whether any taper or cut is set.
    pub fn any(&self) -> bool {
        *self != UvTapers::default()
    }
}

/// `tukeyFrom0ToN`: 0 at `x = 0`, 1 at `x = n`.
fn tukey_0_to_n(x: f64, n: f64) -> f64 {
    0.5 * (1.0 + ((std::f64::consts::PI / n) * (x - n)).cos())
}

impl WeightGrid {
    /// `xyToUV` on the half plane (`y ≥ 0`).
    fn xy_to_uv(&self, x: i64, y: i64) -> (f64, f64) {
        let u = (x - (self.width / 2) as i64) as f64 / (self.width as f64 * self.scale_x);
        let v = y as f64 / (self.height as f64 * self.scale_y);
        (u, v)
    }

    /// Multiply every cell by `f(u, v, value)`.
    fn map_cells(&mut self, f: impl Fn(f64, f64, f64) -> f64) {
        let w = self.width;
        for y in 0..self.height / 2 {
            for x in 0..w {
                let (u, v) = self.xy_to_uv(x as i64, y as i64);
                let k = y * w + x;
                self.grid[k] = f(u, v, self.grid[k]);
            }
        }
    }

    /// `initializeWeightTapers` after the rank filter: the Gaussian taper,
    /// then the inner Tukey taper or the minimum uv distance, then the outer
    /// Tukey taper or the maximum, then the edge Tukey taper or the edge.
    pub fn apply_tapers(&mut self, t: &UvTapers) {
        if t.gaussian_beam != 0.0 {
            // `SetGaussianTaper`: the half-power width times the long double
            // `2 sqrt(2 ln 2)` (x87, 64-bit mantissa; its f64 part and rest),
            // the product rounded to double.
            let half_power_uv = 1.0 / (t.gaussian_beam * 2.0 * std::f64::consts::PI);
            const SIGMA_HI: f64 = 2.3548200450309493;
            const SIGMA_LO: f64 = 5.5077470362263625e-17;
            let p = half_power_uv * SIGMA_HI;
            let e = half_power_uv.mul_add(SIGMA_HI, -p) + half_power_uv * SIGMA_LO;
            let m = p + e;
            let m = m * (-2.0 * m);
            self.map_cells(|u, v, val| {
                if val != 0.0 {
                    val * ((u * u + v * v) / m).exp()
                } else {
                    val
                }
            });
        }
        if t.inner_tukey != 0.0 {
            let (min, n) = (t.min_uv_l, t.inner_tukey);
            let (min_sq, total_sq) = (min * min, (min + n) * (min + n));
            self.map_cells(|u, v, val| {
                let d = u * u + v * v;
                if d < min_sq {
                    0.0
                } else if d < total_sq {
                    val * tukey_0_to_n(d.sqrt() - min, n)
                } else {
                    val
                }
            });
        } else if t.min_uv_l != 0.0 {
            let min_sq = t.min_uv_l * t.min_uv_l;
            self.map_cells(|u, v, val| if u * u + v * v < min_sq { 0.0 } else { val });
        }
        if t.tukey != 0.0 {
            let (max, n) = (t.max_uv_l, t.tukey);
            let (max_sq, trans_sq) = (max * max, (max - n) * (max - n));
            self.map_cells(|u, v, val| {
                let d = u * u + v * v;
                if d > max_sq {
                    0.0
                } else if d > trans_sq {
                    val * tukey_0_to_n(max - d.sqrt(), n)
                } else {
                    val
                }
            });
        } else if t.max_uv_l != 0.0 {
            let max_sq = t.max_uv_l * t.max_uv_l;
            self.map_cells(|u, v, val| if u * u + v * v > max_sq { 0.0 } else { val });
        }
        if t.edge_tukey != 0.0 || t.edge != 0.0 {
            let (max_u, max_v) = self.xy_to_uv(self.width as i64, (self.height / 2) as i64);
            let (edge, n) = (t.edge, t.edge_tukey);
            if n != 0.0 {
                let total = n + edge;
                self.map_cells(|u, v, val| {
                    let (ud, vd) = (max_u - u.abs(), max_v - v.abs());
                    if ud < edge || vd < edge {
                        0.0
                    } else if ud < total || vd < total {
                        let ru = (ud - edge).min(n);
                        let rv = (vd - edge).min(n);
                        val * (tukey_0_to_n(ru, n) * tukey_0_to_n(rv, n))
                    } else {
                        val
                    }
                });
            } else {
                self.map_cells(|u, v, val| {
                    if max_u - u.abs() < edge || max_v - v.abs() < edge {
                        0.0
                    } else {
                        val
                    }
                });
            }
        }
    }
}

/// Settings of one WSClean weighting pass.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct WeightSettings {
    pub class: WeightClass,
    /// Padded image size (see [`padded_size`]).
    pub width: usize,
    pub height: usize,
    /// Pixel scales in radians.
    pub scale_x: f64,
    pub scale_y: f64,
    pub super_weight: f64,
    /// `-weight-rank-filter <level> <size>`; applied when `level >= 1`.
    pub rank_filter_level: f64,
    pub rank_filter_size: usize,
}

/// Grid, finish, rank-filter and look up: the imaging weight of every row
/// and channel, plus the finished grid.
pub fn imaging_weights(
    settings: &WeightSettings,
    uvw: &[f64],
    wavelength: &[f64],
    weights: &[f32],
    selected: &[bool],
) -> Result<(Vec<f32>, WeightGrid), &'static str> {
    imaging_weights_tapered(
        settings,
        &UvTapers::default(),
        uvw,
        wavelength,
        weights,
        selected,
    )
}

/// [`imaging_weights`] with WSClean's tapers and uv-range cuts applied to
/// the finished (and rank-filtered) grid, as `initializeWeightTapers` does.
pub fn imaging_weights_tapered(
    settings: &WeightSettings,
    tapers: &UvTapers,
    uvw: &[f64],
    wavelength: &[f64],
    weights: &[f32],
    selected: &[bool],
) -> Result<(Vec<f32>, WeightGrid), &'static str> {
    let mut grid = WeightGrid::new(
        settings.class,
        settings.width,
        settings.height,
        settings.scale_x,
        settings.scale_y,
        settings.super_weight,
    )?;
    grid.grid_rows(uvw, wavelength, weights, selected)?;
    grid.finish()?;
    if settings.rank_filter_level >= 1.0 {
        grid.rank_filter(settings.rank_filter_level, settings.rank_filter_size);
    }
    grid.apply_tapers(tapers);
    let mut out = vec![0.0f32; weights.len()];
    grid.lookup_rows(uvw, wavelength, selected, &mut out)?;
    Ok((out, grid))
}

fn finite(re: f32, im: f32) -> bool {
    re.is_finite() && im.is_finite()
}

/// Stokes I visibilities and weights from XX, XY, YX, YY cells, as
/// `ExtractData` and `ExtractWeights` form them for `-pol I`:
/// `I = 0.5 (XX + YY)` in complex float (zero when not finite) and
/// `w = min(4 w_XX, 4 w_YY)`, zero when either cell is flagged or its data is
/// not finite. `data` holds `ncell × 4` interleaved complex floats, `weights`
/// and `flags` `ncell × 4` values; returns `ncell` interleaved complex floats
/// and `ncell` weights.
pub fn stokes_i_from_linear(
    data: &[f32],
    weights: &[f32],
    flags: &[u8],
    ncell: usize,
) -> Result<(Vec<f32>, Vec<f32>), &'static str> {
    if data.len() != ncell * 8 || weights.len() != ncell * 4 || flags.len() != ncell * 4 {
        return Err("data, weights and flags must hold ncell × 4 correlations");
    }
    let mut vis = vec![0.0f32; 2 * ncell];
    let mut out = vec![0.0f32; ncell];
    for cell in 0..ncell {
        let d = &data[8 * cell..8 * cell + 8];
        let (xx_re, xx_im, yy_re, yy_im) = (d[0], d[1], d[6], d[7]);
        let re = (yy_re + xx_re) * 0.5;
        let im = (yy_im + xx_im) * 0.5;
        if finite(re, im) {
            vis[2 * cell] = re;
            vis[2 * cell + 1] = im;
        }
        let w = &weights[4 * cell..4 * cell + 4];
        let f = &flags[4 * cell..4 * cell + 4];
        let mut weight = if f[0] == 0 && finite(xx_re, xx_im) {
            w[0] * 4.0
        } else {
            0.0
        };
        weight = if f[3] == 0 && finite(yy_re, yy_im) {
            let yy = w[3] * 4.0;
            // std::min: the second argument only when strictly smaller.
            if yy < weight { yy } else { weight }
        } else {
            0.0
        };
        out[cell] = weight;
    }
    Ok((vis, out))
}

/// The header sums of `MsGridderData::ApplyWeights` for one polarisation:
/// `weights` are the per-visibility weights, `imaging` the imaging weights,
/// both `nrow × nchan` floats in row order.
pub fn weight_sums(weights: &[f32], imaging: &[f32]) -> Result<WeightSums, &'static str> {
    if weights.len() != imaging.len() {
        return Err("weights and imaging weights differ in length");
    }
    let mut sums = WeightSums::default();
    for (&w, &img) in weights.iter().zip(imaging) {
        let cum = w * img;
        let has_weight = cum != 0.0;
        if has_weight {
            sums.visibility_weight_sum += f64::from(w);
            sums.count += 1;
        }
        sums.max_gridded_weight = sums.max_gridded_weight.max(f64::from(cum));
        sums.total_weight += f64::from(cum);
    }
    Ok(sums)
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCALE: f64 = 8.0 * std::f64::consts::PI / (180.0 * 60.0 * 60.0);

    #[test]
    fn padded_size_follows_settings_cpp() {
        assert_eq!(padded_size(512, 1.2), 616);
        assert_eq!(padded_size(1024, 1.2), 1232);
        for trimmed in (2..=4096).step_by(2) {
            let mut expected = (trimmed as f64 * 1.2).ceil() as usize;
            while !expected.is_multiple_of(4) {
                expected += 1;
            }
            assert_eq!(padded_size(trimmed, 1.2), expected, "size {trimmed}");
        }
    }

    #[test]
    fn shape_rounds_super_weight_and_makes_even() {
        assert_eq!(WeightGrid::shape(616, 616, 1.0), (616, 616));
        assert_eq!(WeightGrid::shape(616, 616, 3.0), (206, 206));
        assert_eq!(
            WeightGrid::shape(610, 610, 4.0),
            (154, 154),
            "152.5 rounds up"
        );
        assert_eq!(WeightGrid::shape(614, 614, 4.0), (154, 154));
    }

    fn one_sample(class: WeightClass) -> (WeightGrid, f64, f64) {
        let mut grid = WeightGrid::new(class, 616, 616, SCALE, SCALE, 1.0).unwrap();
        let (u, v) = (120.5, 33.25);
        grid.grid_sample(u, v, 2.0);
        grid.grid_sample(u, v, 3.0);
        grid.grid_sample(u + 1e6, v, 1.0); // off the grid
        grid.finish().unwrap();
        (grid, u, v)
    }

    #[test]
    fn briggs_uniform_natural_match_the_formulas() {
        let (grid, u, v) = one_sample(WeightClass::Briggs(0.5));
        let avg_w = 25.0 / 5.0;
        let f = 5.0 * (-std::f64::consts::LN_10 * 0.5).exp();
        let s_sq = f * f / avg_w;
        let expected = 1.0 / (1.0 + 5.0 * s_sq);
        assert_eq!(grid.sample(u, v), expected);
        assert_eq!(grid.sample(-u, -v), expected, "conjugate sample");
        assert_eq!(grid.sample(u + 1e6, v), 0.0);
        let (grid, u, v) = one_sample(WeightClass::Uniform);
        assert_eq!(grid.sample(u, v), 0.2);
        let (grid, u, v) = one_sample(WeightClass::Natural);
        assert_eq!(grid.sample(u, v), 1.0);
        assert_eq!(grid.total(), 5.0);
    }

    #[test]
    fn rank_filter_clips_to_window_mean() {
        let mut grid = WeightGrid::new(WeightClass::Natural, 32, 32, SCALE, SCALE, 1.0).unwrap();
        let w = grid.width();
        grid.grid[5 * w + 5] = 100.0;
        for &(x, y) in &[(6, 5), (5, 6), (4, 5), (5, 4), (9, 9)] {
            grid.grid[y * w + x] = 1.0;
        }
        grid.rank_filter(3.0, 16);
        let mean = 105.0 / 6.0;
        assert_eq!(grid.grid[5 * w + 5], mean * 3.0);
        assert_eq!(grid.grid[5 * w + 6], 1.0);
        assert_eq!(grid.grid[9 * w + 9], 1.0);
    }

    #[test]
    fn stokes_i_rules() {
        let nan = f32::NAN;
        // cell 0: ordinary; cell 1: YY flagged; cell 2: XX not finite; cell 3: both ok, YY smaller
        let data = [
            1.0, 2.0, 9.0, 9.0, 9.0, 9.0, 3.0, -2.0, //
            1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, //
            nan, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, //
            2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.0, 0.0,
        ];
        let weights = [
            2.0, 7.0, 7.0, 3.0, //
            1.0, 1.0, 1.0, 1.0, //
            1.0, 1.0, 1.0, 1.0, //
            5.0, 1.0, 1.0, 0.5,
        ];
        let flags = [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0];
        let (vis, w) = stokes_i_from_linear(&data, &weights, &flags, 4).unwrap();
        assert_eq!(&vis[..2], &[2.0, 0.0]);
        assert_eq!(&vis[2..4], &[1.0, 0.0]);
        assert_eq!(&vis[4..6], &[0.0, 0.0], "non-finite collapses to zero");
        assert_eq!(&vis[6..8], &[3.0, 0.0]);
        assert_eq!(w, [8.0, 0.0, 0.0, 2.0]);
    }

    #[test]
    fn weight_sums_follow_apply_weights() {
        let weights = [1.0f32, 2.0, 3.0, 4.0];
        let imaging = [0.5f32, 0.0, 0.25, 1.0];
        let sums = weight_sums(&weights, &imaging).unwrap();
        assert_eq!(sums.count, 3);
        assert_eq!(sums.visibility_weight_sum, 8.0);
        assert_eq!(sums.total_weight, 0.5 + 0.75 + 4.0);
        assert_eq!(sums.max_gridded_weight, 4.0);
    }

    #[test]
    fn imaging_weights_zero_unselected_rows() {
        let settings = WeightSettings {
            class: WeightClass::Briggs(0.5),
            width: 616,
            height: 616,
            scale_x: SCALE,
            scale_y: SCALE,
            super_weight: 1.0,
            rank_filter_level: 3.0,
            rank_filter_size: 16,
        };
        let uvw = [100.0, 50.0, 0.0, 100.0, 50.0, 0.0];
        let wavelength = [0.2, 0.25];
        let weights = [1.0f32, 1.0, 1.0, 1.0];
        let (out, grid) =
            imaging_weights(&settings, &uvw, &wavelength, &weights, &[true, false]).unwrap();
        assert!(out[0] > 0.0 && out[1] > 0.0);
        assert_eq!(&out[2..], &[0.0, 0.0]);
        assert_eq!(grid.cells().iter().filter(|&&c| c != 0.0).count(), 2);
    }

    /// Task G4: the uv cuts zero cells by their lower corner, the Gaussian
    /// taper is `exp(-(u² + v²) / (2 (h · 2 sqrt(2 ln 2))²))` with `h` the
    /// half-power uv width, and no taper leaves the grid as it was.
    #[test]
    fn tapers_act_on_the_cells() {
        let mut grid = WeightGrid::new(WeightClass::Natural, 64, 64, SCALE, SCALE, 1.0).unwrap();
        // One sample per cell along v = 0 (u > 0) and along u = 0.
        let du = 1.0 / (64.0 * SCALE);
        for k in 1..30 {
            grid.grid_sample((k as f64 + 0.5) * du, 0.0, 1.0);
            grid.grid_sample(0.0, (k as f64 + 0.5) * du, 1.0);
        }
        grid.finish().unwrap();
        let before = grid.cells().to_vec();
        grid.apply_tapers(&UvTapers::default());
        assert_eq!(grid.cells(), &before[..]);
        let cut = UvTapers {
            min_uv_l: 4.5 * du,
            max_uv_l: 20.5 * du,
            ..UvTapers::default()
        };
        let mut g = grid.clone();
        g.apply_tapers(&cut);
        // Cell k on the u axis has its corner at u = k du.
        let cell = |g: &WeightGrid, k: usize| g.cells()[32 + k];
        assert_eq!(cell(&g, 4), 0.0);
        assert_eq!(cell(&g, 5), 1.0);
        assert_eq!(cell(&g, 20), 1.0);
        assert_eq!(cell(&g, 21), 0.0);
        let beam = 30.0 * SCALE;
        let mut g = grid.clone();
        g.apply_tapers(&UvTapers {
            gaussian_beam: beam,
            ..UvTapers::default()
        });
        let h = 1.0 / (beam * 2.0 * std::f64::consts::PI) * 2.0 * (2.0 * 2f64.ln()).sqrt();
        for k in [1usize, 7, 15] {
            let u = k as f64 * du;
            let want = (-(u * u) / (2.0 * h * h)).exp();
            assert!((cell(&g, k) - want).abs() < 1e-12 * want.max(1e-300));
        }
        let mut g = grid.clone();
        g.apply_tapers(&UvTapers {
            max_uv_l: 20.0 * du,
            tukey: 10.0 * du,
            ..UvTapers::default()
        });
        assert_eq!(cell(&g, 8), 1.0);
        assert!((cell(&g, 15) - 0.5).abs() < 1e-12);
        assert_eq!(cell(&g, 21), 0.0);
    }
}
