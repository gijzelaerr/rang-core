# Class-A batch 1: exact-size read with Stokes I in f32, in-place compaction, no kept copy of the
# gridding weights, f32 visibilities held as read by the measurement, in-place shrink of large blocks.
root="/home/gijsm/Worktrees/rang/fp-g2-memory/core/src/"
def edit(path, pairs):
    p=root+path; s=open(p).read()
    for old,new in pairs:
        assert s.count(old)==1,(path,old[:80],s.count(old))
        s=s.replace(old,new)
    open(p,"w").write(s)

# ---- input.rs
edit("gemclean/input.rs", [
("""/// The selected rows as Stokes I, `rows × nchan` in row order.
#[derive(Clone, Debug)]
pub struct StokesI {
    pub uvw: Vec<f64>,
    pub freq: Vec<f64>,
    pub vis: Vec<Complex<f64>>,""",
"""/// The selected rows as Stokes I, `rows × nchan` in row order. The
/// visibilities are single precision, as formed from the column (which is read
/// in single precision); a user widens them exactly to `f64`.
#[derive(Clone, Debug)]
pub struct StokesI {
    pub uvw: Vec<f64>,
    pub freq: Vec<f64>,
    pub vis: Vec<Complex<f32>>,"""),
("""    let mut start = 0;
    while start < main.nrows {
        let count = sel.chunk_rows.max(1).min(main.nrows - start);
        let field = ints(&read(&main, "FIELD_ID", start, count)?, "FIELD_ID")?;
        let ant1 = ints(&read(&main, "ANTENNA1", start, count)?, "ANTENNA1")?;
        let ant2 = ints(&read(&main, "ANTENNA2", start, count)?, "ANTENNA2")?;
        let ddid = ints(&read(&main, "DATA_DESC_ID", start, count)?, "DATA_DESC_ID")?;
        let keep: Vec<bool> = (0..count as usize)
            .map(|i| field[i] == sel.field && ant1[i] != ant2[i] && ddid[i] == sel.data_desc)
            .collect();
        if keep.iter().any(|&k| k) {""",
"""    let selected = |start: u64, count: u64| -> Result<Vec<bool>, String> {
        let field = ints(&read(&main, "FIELD_ID", start, count)?, "FIELD_ID")?;
        let ant1 = ints(&read(&main, "ANTENNA1", start, count)?, "ANTENNA1")?;
        let ant2 = ints(&read(&main, "ANTENNA2", start, count)?, "ANTENNA2")?;
        let ddid = ints(&read(&main, "DATA_DESC_ID", start, count)?, "DATA_DESC_ID")?;
        Ok((0..count as usize)
            .map(|i| field[i] == sel.field && ant1[i] != ant2[i] && ddid[i] == sel.data_desc)
            .collect())
    };
    // Count the selected rows first, so that each array is allocated once at
    // its size: grown by doubling, the visibilities would pass through up to
    // three times their size.
    let mut rows = 0usize;
    let mut start = 0;
    while start < main.nrows {
        let count = sel.chunk_rows.max(1).min(main.nrows - start);
        rows += selected(start, count)?.iter().filter(|&&k| k).count();
        start += count;
    }
    out.uvw.reserve_exact(3 * rows);
    out.flag_row.reserve_exact(rows);
    out.vis.reserve_exact(rows * nchan);
    out.weight.reserve_exact(rows * nchan);
    let mut start = 0;
    while start < main.nrows {
        let count = sel.chunk_rows.max(1).min(main.nrows - start);
        let keep = selected(start, count)?;
        if keep.iter().any(|&k| k) {"""),
("""                        vis[ch] = Complex::new(f64::from(v.0), f64::from(v.1));""",
"""                        vis[ch] = Complex::new(v.0, v.1);"""),
])

# ---- the gram bench (a user of read_ms)
edit("bin/gridder_gram_bench.rs", [
("""            vis.extend_from_slice(&data.vis[row * nchan..(row + 1) * nchan]);""",
"""            vis.extend(
                data.vis[row * nchan..(row + 1) * nchan]
                    .iter()
                    .map(|v| Complex::new(f64::from(v.re), f64::from(v.im))),
            );"""),
])

# ---- host.rs: shrink large blocks in place
edit("gemclean/host.rs", [
("""                if is_large(&layout)
                    && is_large(&new)
                    && rounded(new_size) == rounded(layout.size())
                {
                    memory::resize(layout.size(), new_size);
                    return ptr;
                }""",
"""                if is_large(&layout)
                    && is_large(&new)
                    && rounded(new_size) <= rounded(layout.size())
                {
                    // Shrink in place: unmap the whole pages past the new end,
                    // so a shrinking block is never held twice.
                    let (old, kept) = (rounded(layout.size()), rounded(new_size));
                    if kept < old {
                        munmap(ptr.add(kept).cast(), old - kept);
                    }
                    memory::resize(layout.size(), new_size);
                    return ptr;
                }"""),
])
