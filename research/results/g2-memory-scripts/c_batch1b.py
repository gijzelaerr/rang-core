root="/home/gijsm/Worktrees/rang/fp-g2-memory/core/src/"
def edit(path, pairs):
    p=root+path; s=open(p).read()
    for old,new in pairs:
        assert s.count(old)==1,(path,old[:80],s.count(old))
        s=s.replace(old,new)
    open(p,"w").write(s)

edit("bin/gemclean.rs", [
("""    let weights = input::gridding_weights(&data, args.weight, n, args.scale)?;""",
"""    let mut weights = input::gridding_weights(&data, args.weight, n, args.scale)?;"""),
("""    // Keep the rows that carry weight.
    let nchan = data.freq.len();
    let mut uvw = Vec::new();
    let mut vis = Vec::new();
    let mut wgt = Vec::new();
    for row in 0..data.rows() {
        let w = &weights.weights[row * nchan..(row + 1) * nchan];
        if w.iter().any(|&x| x != 0.0) {
            uvw.extend_from_slice(&data.uvw[3 * row..3 * row + 3]);
            vis.extend_from_slice(&data.vis[row * nchan..(row + 1) * nchan]);
            wgt.extend_from_slice(w);
        }
    }
    let kept_rows = uvw.len() / 3;
    let freq = data.freq.clone();
    let phase_dir = data.phase_dir;
    drop(data);""",
"""    // Keep the rows that carry weight, in place: the rows kept move down over
    // the rows dropped, so no second copy of the visibilities is held, and the
    // gridding weights are not kept beside the copy the measurement takes.
    let nchan = data.freq.len();
    let rows = data.rows();
    let phase_dir = data.phase_dir;
    let input::StokesI {
        mut uvw,
        freq,
        mut vis,
        weight,
        flag_row,
        ..
    } = data;
    drop((weight, flag_row));
    let mut wgt = std::mem::take(&mut weights.weights);
    let mut kept_rows = 0;
    for row in 0..rows {
        let (a, b) = (row * nchan, (row + 1) * nchan);
        if wgt[a..b].iter().any(|&x| x != 0.0) {
            if kept_rows != row {
                uvw.copy_within(3 * row..3 * row + 3, 3 * kept_rows);
                vis.copy_within(a..b, kept_rows * nchan);
                wgt.copy_within(a..b, kept_rows * nchan);
            }
            kept_rows += 1;
        }
    }
    uvw.truncate(3 * kept_rows);
    vis.truncate(kept_rows * nchan);
    wgt.truncate(kept_rows * nchan);
    uvw.shrink_to_fit();
    vis.shrink_to_fit();
    wgt.shrink_to_fit();"""),
("""    uvw: Vec<f64>,
    freq: &[f64],
    vis: Vec<Complex<f64>>,
    wgt: Vec<f64>,
    opts: Options,
) -> Result<Cleaned, String> {""",
"""    uvw: Vec<f64>,
    freq: &[f64],
    vis: Vec<Complex<f32>>,
    wgt: Vec<f64>,
    opts: Options,
) -> Result<Cleaned, String> {"""),
("""    let measurement: GridMeasurement<T> = GridMeasurement::new(
        uvw,
        freq.to_vec(),
        vis,
        wgt,""",
"""    let measurement: GridMeasurement<T> = GridMeasurement::from_single(
        uvw,
        freq.to_vec(),
        vis,
        wgt,"""),
])

edit("gemclean/measure.rs", [
("""/// The measurement operator in precision `T`.
pub struct GridMeasurement<T: Real> {
    uvw: Vec<f64>,
    freq: Vec<f64>,
    vis: Vec<Complex<T>>,""",
"""/// The visibilities, in precision `T` or, when they came in single precision
/// (as read from a Measurement Set), as they came: widening an `f32` to `f64`
/// is exact, so the `f64` arithmetic sees the same values at half the memory.
enum Data<T> {
    Single(Vec<Complex<f32>>),
    Native(Vec<Complex<T>>),
}

#[inline(always)]
fn widen_vis<T: Real>(v: Complex<f32>) -> Complex<T> {
    Complex::new(T::of(f64::from(v.re)), T::of(f64::from(v.im)))
}

/// The measurement operator in precision `T`.
pub struct GridMeasurement<T: Real> {
    uvw: Vec<f64>,
    freq: Vec<f64>,
    vis: Data<T>,"""),
("""    /// `wgt` is normalised here; `vis` and `wgt` are `nrow × nchan`.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        uvw: Vec<f64>,
        freq: Vec<f64>,
        vis: Vec<Complex<f64>>,
        wgt: Vec<f64>,
        side: usize,
        cell: f64,
        epsilon: f64,
        opts: Options,
    ) -> Result<GridMeasurement<T>, String> {
        let nrow = uvw.len() / 3;
        if vis.len() != nrow * freq.len() || wgt.len() != vis.len() {
            return Err("vis and wgt must be nrow * nchan".into());
        }
        let sum: f64 = wgt.iter().sum();
        if sum <= 0.0 || sum.is_nan() {
            return Err("weights must have a positive sum".into());
        }
        let wgt: Vec<T> = wgt.iter().map(|w| T::of(w / sum)).collect();""",
"""    /// `wgt` is normalised here; `vis` and `wgt` are `nrow × nchan`.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        uvw: Vec<f64>,
        freq: Vec<f64>,
        vis: Vec<Complex<f64>>,
        wgt: Vec<f64>,
        side: usize,
        cell: f64,
        epsilon: f64,
        opts: Options,
    ) -> Result<GridMeasurement<T>, String> {
        if vis.len() != wgt.len() {
            return Err("vis and wgt must be nrow * nchan".into());
        }
        let mut m = GridMeasurement::build(uvw, freq, wgt, side, cell, epsilon, opts)?;
        // In place where `T` is `f64`: the same layout, so no second copy.
        m.vis = Data::Native(
            vis.into_iter()
                .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
                .collect(),
        );
        Ok(m)
    }

    /// [`GridMeasurement::new`] with single-precision visibilities, held as
    /// they are and widened where they are used: the same results as `new` of
    /// the widened values, with half the memory for them when `T` is `f64`.
    #[allow(clippy::too_many_arguments)]
    pub fn from_single(
        uvw: Vec<f64>,
        freq: Vec<f64>,
        vis: Vec<Complex<f32>>,
        wgt: Vec<f64>,
        side: usize,
        cell: f64,
        epsilon: f64,
        opts: Options,
    ) -> Result<GridMeasurement<T>, String> {
        if vis.len() != wgt.len() {
            return Err("vis and wgt must be nrow * nchan".into());
        }
        let mut m = GridMeasurement::build(uvw, freq, wgt, side, cell, epsilon, opts)?;
        m.vis = Data::Single(vis);
        Ok(m)
    }

    /// Everything but the visibilities.
    fn build(
        uvw: Vec<f64>,
        freq: Vec<f64>,
        wgt: Vec<f64>,
        side: usize,
        cell: f64,
        epsilon: f64,
        opts: Options,
    ) -> Result<GridMeasurement<T>, String> {
        let nrow = uvw.len() / 3;
        if wgt.len() != nrow * freq.len() {
            return Err("vis and wgt must be nrow * nchan".into());
        }
        let sum: f64 = wgt.iter().sum();
        if sum <= 0.0 || sum.is_nan() {
            return Err("weights must have a positive sum".into());
        }
        // In place where `T` is `f64`.
        let wgt: Vec<T> = wgt.into_iter().map(|w| T::of(w / sum)).collect();"""),
("""        Ok(GridMeasurement {
            uvw,
            freq,
            vis: vis
                .iter()
                .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
                .collect(),
            wgt,""",
"""        Ok(GridMeasurement {
            uvw,
            freq,
            vis: Data::Native(Vec::new()),
            wgt,"""),
("""            ("measurement: visibilities", bytes_of(&self.vis)),""",
"""            (
                "measurement: visibilities",
                match &self.vis {
                    Data::Single(v) => bytes_of(v),
                    Data::Native(v) => bytes_of(v),
                },
            ),"""),
("""        let mut guard = self.buffer.lock().expect("no panic while predicting");
        guard.resize(self.vis.len(), Complex::new(T::of(0.0), T::of(0.0)));
        let e = guard.as_mut_slice();
        if model.par_iter().any(|&c| c != 0.0) {
            self.predict_into(model, e)?;
            e.par_iter_mut()
                .zip(self.vis.par_iter())
                .for_each(|(p, v)| *p = *v - *p);
        } else {
            e.par_iter_mut()
                .zip(self.vis.par_iter())
                .for_each(|(p, v)| *p = *v);
        }""",
"""        let mut guard = self.buffer.lock().expect("no panic while predicting");
        guard.resize(self.wgt.len(), Complex::new(T::of(0.0), T::of(0.0)));
        let e = guard.as_mut_slice();
        let predicted = model.par_iter().any(|&c| c != 0.0);
        if predicted {
            self.predict_into(model, e)?;
        }
        match (&self.vis, predicted) {
            (Data::Native(vis), true) => e
                .par_iter_mut()
                .zip(vis.par_iter())
                .for_each(|(p, v)| *p = *v - *p),
            (Data::Native(vis), false) => {
                e.par_iter_mut().zip(vis.par_iter()).for_each(|(p, v)| *p = *v)
            }
            (Data::Single(vis), true) => e
                .par_iter_mut()
                .zip(vis.par_iter())
                .for_each(|(p, v)| *p = widen_vis::<T>(*v) - *p),
            (Data::Single(vis), false) => e
                .par_iter_mut()
                .zip(vis.par_iter())
                .for_each(|(p, v)| *p = widen_vis::<T>(*v)),
        }"""),
("""        let mut guard = self.buffer.lock().expect("no panic while predicting");
        guard.resize(self.vis.len(), Complex::new(T::of(0.0), T::of(0.0)));
        self.predict_into(x, guard.as_mut_slice())?;""",
"""        let mut guard = self.buffer.lock().expect("no panic while predicting");
        guard.resize(self.wgt.len(), Complex::new(T::of(0.0), T::of(0.0)));
        self.predict_into(x, guard.as_mut_slice())?;"""),
])
