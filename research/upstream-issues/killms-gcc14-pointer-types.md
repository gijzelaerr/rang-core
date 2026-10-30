# killMS: build fails with GCC 14+ (incompatible pointer type in `Gridder.c`)

Repository: saopicc/killMS. Status: **filed 2026-10-30, https://github.com/saopicc/killMS/issues/25;
PR https://github.com/saopicc/killMS/pull/26** (branch `gijzelaerr:gcc15-incompatible-pointer-types`,
commit 26af26e). Task U3, [../upstream-saopicc.md](../upstream-saopicc.md). Origin:
[ddfacet-feasibility.md](../ddfacet-feasibility.md), installation section.

- **Versions.** killMS 3.3.0 = `master` 350f22c (PyPI has only the sdist, so every install
  compiles); GCC 15.2.0 (Ubuntu 15.2.0-16ubuntu1); Python 3.12.15; NumPy 2.3.2 in the build env.
- **Reproduction.** `uv pip install --no-deps ./killMS` fails in 13.4 s:
  `Gridder.c:309:60: error: passing argument 1 of ... from incompatible pointer type
  [-Wincompatible-pointer-types]`. The build uses `-fmax-errors=1`; with
  `CFLAGS=-Wno-error=incompatible-pointer-types` it builds (13.3 s) and the verbose log has exactly
  two such diagnostics (lines 309, 310) and none of the other GCC 14 error categories.
- **Expected.** Builds with the default flags of current compilers.
- **Observed cause.** `pyGridderPoints` declares `PyArrayObject *ObjGridIn,*ObjWIn;` (line 293);
  both come from `PyArg_ParseTuple` format `O` (a `PyObject *`) and go to
  `PyArray_ContiguousFromObject(PyObject *, ...)`. GCC 14 made this an error by default
  ([porting notes](https://gcc.gnu.org/gcc-14/porting_to.html#incompatible-pointer-types),
  checked). The other functions in the file already use `PyObject *` (lines 88, 194, 500).
- **Impact.** `pip install killMS` fails on current distributions (Ubuntu 26.04 ships GCC 15).
- **Fix (PR #26).** Declare the two variables `PyObject *`. One line.
- **Tests.** No automated tests in killMS cover the C module (the TestHarness needs private data).
  Checked: `uv pip install ./DDFacet ./killMS` with the fix builds without CFLAGS (132.7 s, both
  packages) with no `incompatible-pointer-types` diagnostic, and `_pyGridder` imports; `Gridder.c`
  compiled with the CMake release flags gives **identical disassembly** before (with the
  workaround) and after (`research/upstream-saopicc-files/objcmp.sh`).
- **CI.** killMS has no GitHub Actions (Jenkins on a private host): no checks on the PR.
