# Class-A batch 2: the residual of a prepared measurement formed in the layout's sorted order, in the
# gridder's own stored-value buffer, so no visibility-sized residual buffer is held. The misfit is
# still summed serially in visibility order (through a permutation, 4 bytes per active visibility).
root="/home/gijsm/Worktrees/rang/fp-g2-memory/core/src/"
def edit(path, pairs):
    p=root+path; s=open(p).read()
    for old,new in pairs:
        assert s.count(old)==1,(path,old[:90],s.count(old))
        s=s.replace(old,new)
    open(p,"w").write(s)

edit("wgridder.rs", [
# DegridIn: the output order
("""struct DegridIn<'a, T: Real> {
    setup: &'a Setup,
    bl: &'a Baselines,
    lay: &'a Layout,
    coeff: &'a [T],
}""",
"""struct DegridIn<'a, T: Real> {
    setup: &'a Setup,
    bl: &'a Baselines,
    lay: &'a Layout,
    coeff: &'a [T],
    /// `out` in the layout's sorted order (index `k` of `refs`), not in
    /// visibility order.
    sorted: bool,
}"""),
("""                if let Some(next) = lay.refs.get(k + PREFETCH_AHEAD) {
                    prefetch(&self.bl.coord[next.row as usize]);
                    // SAFETY: inside `out`, as every visibility index is.
                    prefetch(unsafe {
                        out.get().add(next.row as usize * nchan + next.ch as usize)
                    });
                }
                let ([u, v, w], imflip) = uvw_of(self.bl, r);
                let (ku0, kv, iu0, iv0) = taps_uv::<T, S>(s, self.coeff, u, v);
                let ou = offset(iu0, s.nu, bu);
                let ov = offset(iv0, s.nv, bv);
                let idx = r.row as usize * nchan + r.ch as usize;
                for (g, buf) in bufs.iter().enumerate().take(g1).skip(g0) {""",
"""                if let Some(next) = lay.refs.get(k + PREFETCH_AHEAD) {
                    prefetch(&self.bl.coord[next.row as usize]);
                    let at = if self.sorted {
                        k + PREFETCH_AHEAD
                    } else {
                        next.row as usize * nchan + next.ch as usize
                    };
                    // SAFETY: inside `out`, as every visibility index is.
                    prefetch(unsafe { out.get().add(at) });
                }
                let ([u, v, w], imflip) = uvw_of(self.bl, r);
                let (ku0, kv, iu0, iv0) = taps_uv::<T, S>(s, self.coeff, u, v);
                let ou = offset(iu0, s.nu, bu);
                let ov = offset(iv0, s.nv, bv);
                let idx = if self.sorted {
                    k
                } else {
                    r.row as usize * nchan + r.ch as usize
                };
                for (g, buf) in bufs.iter().enumerate().take(g1).skip(g0) {"""),
# degrid_images: the sorted flag
("""fn degrid_images<T: Real>(
    setup: &Setup,
    bl: &Baselines,
    lay: &Layout,
    tables: &Tables<T>,
    grids: &mut Vec<Vec<Complex<T>>>,
    leave_zero: bool,
    dirty: &[T],
    wgt: Weights,
    vis: &mut [Complex<T>],
    mut timer: Timer,
) -> Plan {""",
"""fn degrid_images<T: Real>(
    setup: &Setup,
    bl: &Baselines,
    lay: &Layout,
    tables: &Tables<T>,
    grids: &mut Vec<Vec<Complex<T>>>,
    leave_zero: bool,
    dirty: &[T],
    wgt: Weights,
    vis: &mut [Complex<T>],
    sorted: bool,
    mut timer: Timer,
) -> Plan {"""),
("""    let input = DegridIn {
        setup,
        bl,
        lay,
        coeff,
    };""",
"""    let input = DegridIn {
        setup,
        bl,
        lay,
        coeff,
        sorted,
    };"""),
("""    let nchan = bl.f_over_c.len();
    lay.refs.par_iter().for_each(|&r| {
        let idx = r.row as usize * nchan + r.ch as usize;
        let twgt = wgt.get::<T>(idx).unwrap_or(T::one());
        // SAFETY: each visibility index appears once in `refs`.
        unsafe {
            let o = out.get().add(idx);""",
"""    let nchan = bl.f_over_c.len();
    lay.refs.par_iter().enumerate().for_each(|(k, &r)| {
        let idx = r.row as usize * nchan + r.ch as usize;
        let twgt = wgt.get::<T>(idx).unwrap_or(T::one());
        // SAFETY: each visibility index appears once in `refs`.
        unsafe {
            let o = out.get().add(if sorted { k } else { idx });"""),
("""    Ok(degrid_images::<T>(
        &setup, &bl, &lay, &tables, &mut grids, false, dirty, wgt, vis, timer,
    ))""",
"""    Ok(degrid_images::<T>(
        &setup, &bl, &lay, &tables, &mut grids, false, dirty, wgt, vis, false, timer,
    ))"""),
("""                &mut self.grids.lock().expect("no panic while degridding").grids,
                true,
                dirty,
                wgt,
                vis,
                Timer::new(),""",
"""                &mut self.grids.lock().expect("no panic while degridding").grids,
                true,
                dirty,
                wgt,
                vis,
                false,
                Timer::new(),"""),
# grid_images: values already stored
("""    dirty: Option<&mut [T]>,
    psf: Option<&mut [T]>,
    mut timer: Timer,
) -> Plan {
    // A dirty image alone stores data values; a PSF (alone or with the
    // dirty image) stores unit values, the dirty value formed per plane.
    let both = dirty.is_some() && psf.is_some();
    let stored_data = (psf.is_none()).then_some(data);
    let GridWork { grids, stored } = buffers;
    values::<T>(setup, bl, &lay.refs, stored_data, wgt, stored);""",
"""    dirty: Option<&mut [T]>,
    psf: Option<&mut [T]>,
    timer: Timer,
) -> Plan {
    grid_images_from::<T>(
        setup, bl, lay, tables, buffers, data, wgt, dirty, psf, false, timer,
    )
}

/// [`grid_images`], or with `prestored` the data values of a dirty image
/// alone already in `buffers.stored` (as [`Prepared::residual`] forms them).
#[allow(clippy::too_many_arguments)]
fn grid_images_from<T: Real>(
    setup: &Setup,
    bl: &Baselines,
    lay: &Layout,
    tables: &Tables<T>,
    buffers: &mut GridWork<T>,
    data: VisData,
    wgt: Weights,
    dirty: Option<&mut [T]>,
    psf: Option<&mut [T]>,
    prestored: bool,
    mut timer: Timer,
) -> Plan {
    // A dirty image alone stores data values; a PSF (alone or with the
    // dirty image) stores unit values, the dirty value formed per plane.
    let both = dirty.is_some() && psf.is_some();
    let stored_data = (psf.is_none()).then_some(data);
    let GridWork { grids, stored } = buffers;
    if !prestored {
        values::<T>(setup, bl, &lay.refs, stored_data, wgt, stored);
    }"""),
# Prepared: the permutation and the residual
("""pub struct Prepared<T: Real> {
    opts: Options,
    bl: Baselines,
    prepared: Option<(Setup, Layout, Tables<T>)>,
    n: usize,
    /// The work space of both directions; its grids are zero between passes.
    grids: std::sync::Mutex<GridWork<T>>,
}""",
"""pub struct Prepared<T: Real> {
    opts: Options,
    bl: Baselines,
    prepared: Option<(Setup, Layout, Tables<T>)>,
    n: usize,
    /// The work space of both directions; its grids are zero between passes.
    grids: std::sync::Mutex<GridWork<T>>,
    /// The sorted index of each active visibility, in visibility order
    /// ([`Prepared::residual`]), made on first use.
    order: std::sync::OnceLock<Vec<u32>>,
}"""),
("""        Ok(Prepared {
            opts: *opts,
            bl,
            prepared,
            n,
            grids: std::sync::Mutex::new(GridWork::default()),
        })
    }""",
"""        Ok(Prepared {
            opts: *opts,
            bl,
            prepared,
            n,
            grids: std::sync::Mutex::new(GridWork::default()),
            order: std::sync::OnceLock::new(),
        })
    }

    /// The residual image of `data` against the image `model` (`None`: the
    /// data alone), gridded with weights `wgt`, and `Σ w |v − m|²` over the
    /// active visibilities, summed serially in visibility order. The same
    /// values, bit for bit, as `vis − dirty2vis(model)` into a visibility
    /// buffer, then `vis2dirty` of it and the serial sum over that buffer,
    /// wherever the inactive visibilities add exactly zero to that sum (the
    /// caller checks); but the prediction and the residual live in the
    /// gridder's sorted stored values, so no visibility-sized buffer is held.
    pub fn residual(
        &self,
        data: VisData,
        wgt: &[T],
        model: Option<&[T]>,
        dirty: &mut [T],
    ) -> Result<f64, String> {
        if data.len().is_some_and(|l| l != self.n)
            || wgt.len() != self.n
            || dirty.len() != self.opts.nx * self.opts.ny
            || model.is_some_and(|m| m.len() != dirty.len())
        {
            return Err("array lengths disagree".into());
        }
        dirty.fill(T::zero());
        let Some((setup, lay, tables)) = &self.prepared else {
            return Ok(0.0);
        };
        let nchan = self.bl.f_over_c.len();
        let index = |r: VisRef| r.row as usize * nchan + r.ch as usize;
        let mut work = self.grids.lock().expect("no panic while gridding");
        let GridWork { grids, stored } = &mut *work;
        stored.resize(lay.refs.len(), czero());
        const CHUNK: usize = 1 << 12;
        if let Some(model) = model {
            stored.par_iter_mut().for_each(|v| *v = czero());
            degrid_images::<T>(
                setup,
                &self.bl,
                lay,
                tables,
                grids,
                true,
                model,
                Weights::None,
                stored,
                true,
                Timer::new(),
            );
            stored
                .par_chunks_mut(CHUNK)
                .zip(lay.refs.par_chunks(CHUNK))
                .for_each(|(out, refs)| {
                    for (o, &r) in out.iter_mut().zip(refs) {
                        *o = data.get::<T>(index(r)) - *o;
                    }
                });
        } else {
            stored
                .par_chunks_mut(CHUNK)
                .zip(lay.refs.par_chunks(CHUNK))
                .for_each(|(out, refs)| {
                    for (o, &r) in out.iter_mut().zip(refs) {
                        *o = data.get::<T>(index(r));
                    }
                });
        }
        // The misfit in visibility order, serial, as over the dense buffer.
        let order = self.order.get_or_init(|| {
            let mut order: Vec<u32> = (0..lay.refs.len() as u32).collect();
            order.par_sort_unstable_by_key(|&k| index(lay.refs[k as usize]));
            order
        });
        let mut q = 0.0;
        for (i, &k) in order.iter().enumerate() {
            if let Some(&next) = order.get(i + PREFETCH_AHEAD) {
                prefetch(&stored[next as usize]);
            }
            let d = stored[k as usize];
            let w = wgt[index(lay.refs[k as usize])];
            let (re, im) = (d.re.to(), d.im.to());
            q += w.to() * (re * re + im * im);
        }
        // The data values `values` would store for this residual.
        let w = T::weights(wgt);
        stored
            .par_chunks_mut(CHUNK)
            .zip(lay.refs.par_chunks(CHUNK))
            .for_each(|(out, refs)| {
                for (o, &r) in out.iter_mut().zip(refs) {
                    let p = unit_value::<T>(setup, &self.bl, r, w.get::<T>(index(r)));
                    let (_, imflip) = fix_w(self.bl.coord[r.row as usize]);
                    *o = data_value(*o, p, T::of(imflip));
                }
            });
        grid_images_from::<T>(
            setup,
            &self.bl,
            lay,
            tables,
            &mut work,
            VisData::Unit,
            w,
            Some(dirty),
            None,
            true,
            Timer::new(),
        );
        Ok(q)
    }"""),
# memory: the permutation
("""        out.push(("gridder: stored sorted values", b(&work.stored)));
        out
    }""",
"""        out.push(("gridder: stored sorted values", b(&work.stored)));
        out.push(("gridder: visibility-order permutation", self.order.get().map_or(0, b)));
        out
    }"""),
])
