# Tricolour: `License: GPLv2` metadata against a BSD-3-Clause LICENSE

Repository: ratt-ru/tricolour. Status: **not filed: already corrected on the development
branch.** Checked 2026-10-30.

- Latest release 0.2.1 (PyPI, 2026-04-01): PyPI JSON `license: GPLv2`; `pyproject.toml`
  line 10 on `master` (7514d81) still says `license = "GPLv2"`, and the `LICENSE` file is the
  BSD-3-Clause text (evidence and hashes in [core-d-tricolour.md](../core-d-tricolour.md),
  section 1). Reproduced: unchanged on `master`.
- The 0.5.0-dev branch (b01ac8f, open PR #101 "0.5.0 development branch") has
  `license = "BSD-3-Clause"` in `pyproject.toml` (line 7) and a BSD 3-Clause `LICENSE`,
  introduced in c36d982 (Simon Perkins, 2026-03-03, "Add hip-cargo project outline").
- Reading: the maintainers' current metadata states BSD-3-Clause, which agrees with the
  licence file and resolves the residual risk recorded in core-d section 1 in the direction
  rang assumed. The stale string on `master` and in 0.2.1 disappears with the 0.5.0 release;
  an issue would only ask for something already done.
- What an issue would have said: "0.2.x declares `License: GPLv2` (classifier
  `Other/Proprietary License`, Poetry's fallback) but ships only BSD-3-Clause text; please
  set `license = "BSD-3-Clause"` on `master` if another 0.2.x release is planned."
- Searched: `gh issue list --repo ratt-ru/tricolour --state all --search license` and `GPL`:
  no report (#41, #35, #66 are unrelated).
