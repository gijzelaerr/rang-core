Target: https://github.com/tmolteno/casacure/issues
Status: ready to post
Reproduced on: repository tree read at de45b5d (v3.8.41); casacure 3.8.41 wheel from PyPI (cp39-abi3 manylinux x86_64) inspected, 2026-11-12
Duplicates checked: open and closed issues and PRs, searches "license", "licence", "COPYING"; none
Title: No LICENSE/COPYING file in the repository or the wheel (LGPL-3.0-or-later declared)

---

`Cargo.toml` declares `license = "LGPL-3.0-or-later"`, and the wheel metadata has `License-Expression: LGPL-3.0-or-later` and the LGPLv3+ classifier. But the repository at de45b5d (v3.8.41) has no `LICENSE`, `COPYING` or `COPYING.LESSER` file, and the 3.8.41 wheel's `.dist-info` has no licence file either (`METADATA`, `RECORD`, `WHEEL`, `entry_points.txt`, `sboms` only). GitHub shows no licence for the repository for the same reason.

The LGPL-3.0 builds on the GPL-3.0, whose section 4 asks that copies of the program carry the licence. LGPL-3.0 section 4 asks the same of combined works: the GPL and the LGPL texts. Downstream packagers (conda-forge, Debian) and licence scanners also look for the file, and they fall back to "no licence" without it.

Suggested fix: add `COPYING` (GPL-3.0) and `COPYING.LESSER` (LGPL-3.0) at the root, and set `license-files` in `pyproject.toml` (or `[tool.maturin] include`) so they reach the wheel and sdist. Setting `license-file` or `include` in the crate's `Cargo.toml` puts them in the crate too.
