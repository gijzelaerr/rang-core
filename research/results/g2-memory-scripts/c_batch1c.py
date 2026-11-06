root="/home/gijsm/Worktrees/rang/fp-g2-memory/core/"
def edit(path, pairs, count=1):
    p=root+path; s=open(p).read()
    for old,new,c in pairs:
        assert s.count(old)==c,(path,old[:90],s.count(old))
        s=s.replace(old,new)
    open(p,"w").write(s)

edit("src/gemclean/input.rs", [
("""impl StokesI {
    pub fn rows(&self) -> usize {
        self.flag_row.len()
    }
""", """impl StokesI {
    pub fn rows(&self) -> usize {
        self.flag_row.len()
    }

    /// The visibilities widened to `f64` (exact), as a new vector.
    pub fn vis_f64(&self) -> Vec<Complex<f64>> {
        self.vis
            .iter()
            .map(|v| Complex::new(f64::from(v.re), f64::from(v.im)))
            .collect()
    }
""", 1),
])
edit("examples/gemclean_sim.rs", [
("""                    vis.extend_from_slice(&data.vis[row * nchan..(row + 1) * nchan]);""",
"""                    vis.extend(
                        data.vis[row * nchan..(row + 1) * nchan]
                            .iter()
                            .map(|v| Complex::new(f64::from(v.re), f64::from(v.im))),
                    );""", 1),
("""        data.vis.clone(),""", """        data.vis_f64(),""", 3),
])
