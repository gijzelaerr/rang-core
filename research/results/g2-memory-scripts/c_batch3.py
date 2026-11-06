# Class-A batch 3: the 2n PSF is cropped to the n x n image the binary writes as soon as nothing else
# reads it (after the beam, the restoring fit and the certified rule's bound), instead of being held
# through the run.
import sys
root=(sys.argv[1] if len(sys.argv) > 1 else "/home/gijsm/Worktrees/rang/fp-g2-memory") + "/core/src/"
def edit(path, pairs):
    p=root+path; s=open(p).read()
    for old,new in pairs:
        assert s.count(old)==1,(path,old[:90],s.count(old))
        s=s.replace(old,new)
    open(p,"w").write(s)

edit("bin/gemclean.rs", [
("""/// The beam, the fitted restoring beam and the CLEAN run.
struct Cleaned {
    psf2n: Vec<f64>,""",
"""/// The beam, the fitted restoring beam and the CLEAN run.
struct Cleaned {
    /// The PSF on the `n × n` image, cropped from the `2n` PSF.
    psf: Vec<f64>,"""),
("""        None => None,
    };
    let outcome = match gram_operator {""",
"""        None => None,
    };
    // Nothing reads the 2n PSF from here on but the PSF image written at the end.
    let mut psf = vec![0.0; n * n];
    for i in 0..n {
        for j in 0..n {
            psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
        }
    }
    let psf2n_bytes = bytes_of(&psf2n);
    drop(psf2n);
    let outcome = match gram_operator {"""),
("""    memory::note("psf 2n image", bytes_of(&psf2n));""",
"""    memory::note("psf 2n image (freed before the run)", psf2n_bytes);
    memory::note("psf n x n crop", bytes_of(&psf));"""),
("""    Ok(Cleaned {
        psf2n,
        beam,""",
"""    Ok(Cleaned {
        psf,
        beam,"""),
("""    let Cleaned {
        psf2n,
        beam,""",
"""    let Cleaned {
        psf,
        beam,"""),
("""    let mut psf = vec![0.0; n * n];
    for i in 0..n {
        for j in 0..n {
            psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
        }
    }
    write_image(&path("psf"), n, &psf, args.bitpix, &base, &[])?;""",
"""    write_image(&path("psf"), n, &psf, args.bitpix, &base, &[])?;"""),
])
