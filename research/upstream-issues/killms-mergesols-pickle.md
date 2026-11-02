# killMS: MergeSols.py passes options through a pickle in the working directory

Repository: saopicc/killMS. Status: **filed 2026-11-02 (U4), https://github.com/saopicc/killMS/issues/28**. Security policy checked first (2026-11-02): no
`SECURITY.md`, no organisation `.github` repository, GitHub private vulnerability reporting
disabled; so a public issue, as the owner approved. Reproduced by U4 on v3.3.0 = `master`
350f22c with a harmless marker only
([../u4-upstream-files/killms_repro.py](../u4-upstream-files/killms_repro.py), DDFacet logger stubbed).

<!-- issue-title: MergeSols.py: options go through a pickle in the working directory, and inputs load with allow_pickle=True -->
<!-- issue-body -->
Two notes on `killMS/MergeSols.py` in v3.3.0 (the same as `master`, 350f22c). Both mean that loading a file can run code from that file.

1. `read_options()` pickles the options to `last_InterPol.obj` in the working directory (lines 35 and 51), and `driver()` reads them straight back (line 245). `main()` called without options reads whatever file of that name is there (line 207). I confirmed with a harmless marker object that `main()` unpickles a `last_InterPol.obj` already in the directory. In the normal `driver()` path the file is overwritten just before the read, so the exposure there is small, but two runs in one directory do share this file.

2. `ClassMergeSols.__init__` opens each input with `np.load(FSol, allow_pickle=True)` (line 59). An object array in the `.npz` is unpickled when `DictSols["Sols"]` is read, which I also confirmed with the marker.

Possible changes: pass `options` directly from `read_options()` to `main()`, which removes the file; and use `allow_pickle=False` if the solution files do not need object arrays (I have not checked every field killMS writes).

I found no security policy for this repository, so I am noting it here.
<!-- /issue-body -->
