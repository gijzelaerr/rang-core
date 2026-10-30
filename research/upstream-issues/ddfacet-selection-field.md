# DDFacet: an MS with data in another field fails with an error that names no fields

Repository: saopicc/DDFacet. Status: **filed 2026-10-30, https://github.com/saopicc/DDFacet/issues/75;
PR https://github.com/saopicc/DDFacet/pull/76** (branch `gijzelaerr:selection-field-hint`, commit
4c1794e3). Task U3, [../upstream-saopicc.md](../upstream-saopicc.md). Origin: the first measured
run of [ddfacet-feasibility.md](../ddfacet-feasibility.md) (LUNO slice, field 1).

- **Versions.** DDFacet 1.0.0.0 = `master` 2fe05ab4; Python 3.12.15; python-casacore backend.
- **Reproduction** (`research/upstream-saopicc-files/field_repro.sh`). Copy of
  `outputs/luno-solve-20261029-02/work.ms` (192 rows, pairs `{(1, 0)}`, 3 FIELD rows);
  `DDF.py --Data-MS f1.ms --Output-Mode Dirty --Image-NPix 128 --Image-Cell 30`: log
  "MS ... (field 0, ddid 0): no rows, skipping", then `RuntimeError: --Data-MS does not specify
  any valid Measurement Set(s)` (exit 1, 5.4 s). `--Selection-Field 1` and `f1.ms//F1` both image
  (exit 0, 6.6-6.7 s).
- **Correction to the study's wording.** Not silent: the skip is logged (in red) and the run
  raises; what is missing is which fields the MS has. The issue says so. Skipping is deliberate
  (many MSs, some without a DDID), so the PR changes only the message.
- **Expected.** The message names the field/DDID pairs present and how to select them.
- **Fix (PR #76, one function).** `ClassMS.ReadMSInfo` already holds `ddid_fields` (the
  quick-check set); the skip message now ends "Field/DDID present in this MS: 1/0. Select them
  with --Selection-Field/--Selection-DDID, or with a //F<field>//D<ddid> suffix on the MS name".
  `ClassDaskMS.ReadMSInfo` has the same message without the set: left unchanged, stated in the PR.
- **Test.** New `DDFacet/Tests/FastUnitTests/TestClassMSSelection.py` (three-row MS from
  `casacore.tables.default_ms`, fields 1 and 2, opened with `Field=0`; asserts the skip and
  "1/0, 2/0" in the message via a `logging` handler on `app.ClassMS`): fails before, passes
  after (pytest, 0.5 s). `nosetests DDFacet.Tests.FastUnitTests`: 35 tests OK before, 36 OK
  after (17-23 s). Pitfall: nose skips executable test files; the file is mode 644.
- **CI.** No GitHub Actions (Jenkins on a private host): no checks on the PR.
- **Duplicates.** `gh issue list --search "Selection-Field" / "field" / "no rows"`: none.
