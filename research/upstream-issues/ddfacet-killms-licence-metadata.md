# DDFacet and killMS: classifier "GPLv2" against "GPL-2 or later" headers

Repositories: saopicc/DDFacet and saopicc/killMS (one issue and one PR each). Status:
**filed 2026-10-30**: https://github.com/saopicc/DDFacet/issues/73, PR
https://github.com/saopicc/DDFacet/pull/74 (fbd2521f); https://github.com/saopicc/killMS/issues/23,
PR https://github.com/saopicc/killMS/pull/24 (fbfdbf6). Branch `licence-classifier-gplv2plus` in
both forks. Task U3, [../upstream-saopicc.md](../upstream-saopicc.md).

- **Versions.** DDFacet 1.0.0.0 = `master` 2fe05ab4; killMS 3.3.0 = `master` 350f22c. PyPI JSON for
  both: classifier `GNU General Public License v2 (GPLv2)`, `license` field = full GPL-2 text,
  no `license_expression`.
- **Reproduction.** `grep "License ::" pyproject.toml` (DDFacet line 60, killMS line 29) against
  `README.rst`/`README.md` lines 8-11 ("either version 2 of the License, or (at your option) any
  later version") and the file headers. `LICENSE.md` is the bare GPL-2 text in both.
- **Counts on master** (`research/upstream-saopicc-files/count_headers.sh`: git-tracked
  `*.py *.c *.cc *.cpp *.h *.hpp`; "or later" = contains "any later version"; no other GPL
  wording found): DDFacet 350 files, 182 or-later, **168 without header** (21 empty
  `__init__.py`); killMS 90 files, 73 or-later, **17 without header** (3 empty `__init__.py`).
  The study's 173 and 78 used a different file set (it also counted other file types); the
  issues quote these counts. DDFacet's `Other/logger.py` says "distributed under the terms of
  GPLv2"; vendored files without headers include `Imager/MultiSliceDeconv/Orieux/edwin/`
  (`tifffile.py`, `viridis.py`, Orieux's code).
- **Expected.** If or-later is intended (README and headers say so), the classifier
  `GNU General Public License v2 or later (GPLv2+)`. Worded as a question to the maintainers.
- **Impact.** Licence scanners and packagers report GPL-2.0-only, which looks incompatible with
  GPL-3 code (rang is GPL-3.0-or-later) although the headers allow it. No effect on rang's own
  position (translation from GPL-2-or-later headers, see the study).
- **Fix (PRs).** One-line classifier change. Missing headers mentioned as a note only; no headers
  added. Verified: `uv build --sdist` of each branch (0.9 s, 1.8 s) has
  `Classifier: License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)` in
  `PKG-INFO`.
- **Duplicates.** `gh issue list --search license|GPL` and `gh pr list` in both repositories:
  none (DDFacet #56 mentions "license" only in a build log).
- **CI.** No GitHub Actions in either repository: no checks on the PRs.
