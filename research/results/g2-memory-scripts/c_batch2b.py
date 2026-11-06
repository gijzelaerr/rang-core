# Batch 2, measurement side: use Prepared::residual where it gives the same bits.
root="/home/gijsm/Worktrees/rang/fp-g2-memory/core/src/"
def edit(path, pairs):
    p=root+path; s=open(p).read()
    for old,new in pairs:
        assert s.count(old)==1,(path,old[:90],s.count(old))
        s=s.replace(old,new)
    open(p,"w").write(s)

edit("wgridder.rs", [
("""                .for_each(|(out, refs)| {
                    for (o, &r) in out.iter_mut().zip(refs) {
                        *o = data.get::<T>(index(r)) - *o;
                    }
                });
        } else {""",
"""                .for_each(|(out, refs)| {
                    for (o, &r) in out.iter_mut().zip(refs) {
                        *o = data.get::<T>(index(r)) - *o;
                    }
                });
            crate::gemclean::memory::mark("residual: predict");
        } else {"""),
])

edit("gemclean/measure.rs", [
("""use crate::wgridder::{self, Options, Prepared, Real, VisData, Weights};""",
"""use crate::wgridder::{self, Options, Prepared, Real, VisData, Weights};"""),
("""    /// The plan and layout of the image grid, reused by every major cycle.
    prepared: Option<Prepared<T>>,
    buffer: Mutex<Vec<Complex<T>>>,
}""",
"""    /// The plan and layout of the image grid, reused by every major cycle.
    prepared: Option<Prepared<T>>,
    buffer: Mutex<Vec<Complex<T>>>,
    /// Form residuals in the gridder's sorted values ([`Prepared::residual`]),
    /// with no visibility-sized buffer: set where that gives the same bits.
    sorted_residual: bool,
}"""),
("""        // In place where `T` is `f64`: the same layout, so no second copy.
        m.vis = Data::Native(
            vis.into_iter()
                .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
                .collect(),
        );
        Ok(m)
    }""",
"""        // In place where `T` is `f64`: the same layout, so no second copy.
        m.vis = Data::Native(
            vis.into_iter()
                .map(|v| Complex::new(T::of(v.re), T::of(v.im)))
                .collect(),
        );
        m.sorted_residual = m.inactive_add_zero();
        Ok(m)
    }"""),
("""        let mut m = GridMeasurement::build(uvw, freq, wgt, side, cell, epsilon, opts)?;
        m.vis = Data::Single(vis);
        Ok(m)
    }""",
"""        let mut m = GridMeasurement::build(uvw, freq, wgt, side, cell, epsilon, opts)?;
        m.vis = Data::Single(vis);
        m.sorted_residual = m.inactive_add_zero();
        Ok(m)
    }

    /// Whether every visibility of zero weight adds exactly zero to the
    /// misfit's serial sum (`0 × |v|²` with `|v|²` finite), so that the sum
    /// over the active visibilities alone has the same bits.
    fn inactive_add_zero(&self) -> bool {
        let finite = |re: f64, im: f64| (re * re + im * im).is_finite();
        match &self.vis {
            Data::Single(vis) => vis.par_iter().zip(self.wgt.par_iter()).all(|(v, w)| {
                let v = widen_vis::<T>(*v);
                w.to() != 0.0 || finite(v.re.to(), v.im.to())
            }),
            Data::Native(vis) => vis
                .par_iter()
                .zip(self.wgt.par_iter())
                .all(|(v, w)| w.to() != 0.0 || finite(v.re.to(), v.im.to())),
        }
    }

    /// Form every residual through a visibility-sized buffer, as before
    /// [`Prepared::residual`] (for comparison: the same bits, more memory).
    pub fn with_dense_residual(mut self) -> Self {
        self.sorted_residual = false;
        self
    }"""),
("""            prepared,
            buffer: Mutex::new(Vec::new()),
        })""",
"""            prepared,
            buffer: Mutex::new(Vec::new()),
            sorted_residual: false,
        })"""),
("""    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        let mut guard = self.buffer.lock().expect("no panic while predicting");""",
"""    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        if let (Some(p), true) = (&self.prepared, self.sorted_residual) {
            let m: Option<Vec<T>> = model
                .par_iter()
                .any(|&c| c != 0.0)
                .then(|| model.par_iter().map(|&c| T::of(c)).collect());
            let data = match &self.vis {
                Data::Single(v) => VisData::C64(v),
                Data::Native(v) => T::vis_data(v),
            };
            let mut out = vec![T::of(0.0); self.opts.nx * self.opts.ny];
            let q = p.residual(data, &self.wgt, m.as_deref(), &mut out)?;
            drop(m);
            crate::gemclean::memory::mark("residual: grid");
            return Ok((widen(&out), 0.5 * q));
        }
        let mut guard = self.buffer.lock().expect("no panic while predicting");"""),
])
