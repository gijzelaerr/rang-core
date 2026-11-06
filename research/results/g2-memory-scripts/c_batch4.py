# Class-A batch 4: the binary forms the 2n PSF before the measurement's plan (sorted index, tables)
# exists, so the PSF pass's own index, values and grid do not sit on top of the plan.
import sys
root=(sys.argv[1] if len(sys.argv) > 1 else "/home/gijsm/Worktrees/rang/fp-g2-memory") + "/core/src/"
def edit(path, pairs):
    p=root+path; s=open(p).read()
    for old,new in pairs:
        assert s.count(old)==1,(path,old[:90],s.count(old))
        s=s.replace(old,new)
    open(p,"w").write(s)

edit("gemclean/measure.rs", [
("""    /// The plan and layout of the image grid, reused by every major cycle.
    prepared: Option<Prepared<T>>,""",
"""    /// The plan and layout of the image grid, reused by every major cycle.
    prepared: Option<Prepared<T>>,
    /// The plan is still to be made ([`GridMeasurement::prepare`]).
    pending: bool,"""),
("""        let mut m = GridMeasurement::build(uvw, freq, wgt, side, cell, epsilon, opts)?;
        // In place where `T` is `f64`: the same layout, so no second copy.
        m.vis = Data::Native(
            vis.into_iter()
                .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
                .collect(),
        );
        m.sorted_residual = m.inactive_add_zero();
        Ok(m)
    }""",
"""        let mut m = GridMeasurement::build(uvw, freq, wgt, side, cell, epsilon, opts)?;
        // In place where `T` is `f64`: the same layout, so no second copy.
        m.vis = Data::Native(
            vis.into_iter()
                .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
                .collect(),
        );
        m.sorted_residual = m.inactive_add_zero();
        m.prepare()
    }"""),
("""        let mut m = GridMeasurement::build(uvw, freq, wgt, side, cell, epsilon, opts)?;
        m.vis = Data::Single(vis);
        m.sorted_residual = m.inactive_add_zero();
        Ok(m)
    }""",
"""        GridMeasurement::from_single_unprepared(uvw, freq, vis, wgt, side, cell, epsilon, opts)?
            .prepare()
    }

    /// [`GridMeasurement::from_single`] without the plan of the image grid:
    /// the PSF can be formed first ([`GridMeasurement::psf_image_with`] does
    /// not use the plan), so that its pass does not hold the plan's sorted
    /// index beside its own. [`GridMeasurement::prepare`] (or
    /// [`GridMeasurement::without_plan_reuse`]) must follow before any
    /// residual; until then those calls fail.
    #[allow(clippy::too_many_arguments)]
    pub fn from_single_unprepared(
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
        m.sorted_residual = m.inactive_add_zero();
        Ok(m)
    }

    /// Make the plan of the image grid, if it is still to be made.
    pub fn prepare(mut self) -> Result<GridMeasurement<T>, String> {
        if self.pending {
            self.prepared = Some(Prepared::new(
                &self.opts,
                &self.uvw,
                &self.freq,
                T::weights(&self.wgt),
            )?);
            self.pending = false;
        }
        Ok(self)
    }

    fn ready(&self) -> Result<(), String> {
        if self.pending {
            return Err("the measurement must be prepared before use".into());
        }
        Ok(())
    }"""),
("""        let prepared = Some(Prepared::new(&opts, &uvw, &freq, T::weights(&wgt))?);
        Ok(GridMeasurement {
            uvw,
            freq,
            vis: Data::Native(Vec::new()),
            wgt,
            opts,
            prepared,""",
"""        Ok(GridMeasurement {
            uvw,
            freq,
            vis: Data::Native(Vec::new()),
            wgt,
            opts,
            prepared: None,
            pending: true,"""),
("""    pub fn without_plan_reuse(mut self) -> Self {
        self.prepared = None;
        self
    }""",
"""    pub fn without_plan_reuse(mut self) -> Self {
        self.prepared = None;
        self.pending = false;
        self
    }"""),
("""    fn image(&self, vis: &[Complex<T>]) -> Result<Vec<f64>, String> {
        let mut out""",
"""    fn image(&self, vis: &[Complex<T>]) -> Result<Vec<f64>, String> {
        self.ready()?;
        let mut out"""),
("""    fn predict_into(&self, model: &[f64], out: &mut [Complex<T>]) -> Result<(), String> {
        let m""",
"""    fn predict_into(&self, model: &[f64], out: &mut [Complex<T>]) -> Result<(), String> {
        self.ready()?;
        let m"""),
("""    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        if let""",
"""    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        self.ready()?;
        if let"""),
])

edit("bin/gemclean.rs", [
("""    let measurement: GridMeasurement<T> = GridMeasurement::from_single(""",
"""    // The plan of the image grid is made after the 2n PSF, which does not use it.
    let measurement: GridMeasurement<T> = GridMeasurement::from_single_unprepared("""),
("""    let measurement = if args.plan_reuse {
        measurement
    } else {
        measurement.without_plan_reuse()
    };
    memory::mark("measurement");
    let t = Instant::now();
    // With the operator and -beam-no-w the PSF needs no gridding pass of its own.
    let psf2n = match (&gram_operator, args.beam_no_w) {
        (Some(op), true) => op.psf_no_w.clone(),
        _ => measurement.psf_image_with(2 * n, args.wgridding && !args.beam_no_w)?,
    };
    let t_psf = t.elapsed().as_secs_f64();
    memory::mark("psf 2n");""",
"""    memory::mark("measurement");
    let t = Instant::now();
    // With the operator and -beam-no-w the PSF needs no gridding pass of its own.
    let psf2n = match (&gram_operator, args.beam_no_w) {
        (Some(op), true) => op.psf_no_w.clone(),
        _ => measurement.psf_image_with(2 * n, args.wgridding && !args.beam_no_w)?,
    };
    let t_psf = t.elapsed().as_secs_f64();
    memory::mark("psf 2n");
    let measurement = if args.plan_reuse {
        measurement.prepare()?
    } else {
        measurement.without_plan_reuse()
    };
    memory::mark("plan");"""),
])
