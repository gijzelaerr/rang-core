# Purr: setup.py declares `kittens`, while Purr imports `Kittens` from astro-kittens

Repository: ratt-ru/purr (PyPI `purr` 1.5.3 metadata: home page ska-sa/purr, which redirects). Status:
**filed 2026-11-02 (U4), https://github.com/ratt-ru/purr/issues/39**; PR: **https://github.com/ratt-ru/purr/pull/40 (branch gijzelaerr/purr `astro-kittens-dependency`, b3e039a)**. A dependency-name mistake. Measured by U4 on 2026-11-02.

Correction to the first U4 report: a fresh astro-tigger-lsm does **not** fail on import on an ordinary
Linux filesystem. The failure seen first came from the scratch directory being on NTFS through WSL (`/mnt/d`), where
`kittens/` and `Kittens/` are one directory. Logs: `outputs/u4-20261102-04/logs/`.

<!-- issue-title: setup.py declares kittens, an unrelated PyPI package; Purr imports Kittens from astro-kittens -->
<!-- issue-body -->
`setup.py` has `install_requires=['kittens', ...]`. On PyPI, `kittens` is an unrelated package with a lowercase `kittens` module. Purr imports `Kittens`, which is provided by `astro-kittens` (ska-sa/kittens). It looks like the name was missed when the package became `astro-kittens`; `meqtrees-cattery` already declares `astro_kittens`.

Measured with purr 1.5.3 (Python 3.12, fresh uv venv, 2026-11-02):

- **Purr alone, case-sensitive filesystem.** `pip install purr` installs `kittens` 0.1.2 and no `astro-kittens`, and `import Purr` fails with `ModuleNotFoundError: No module named 'Kittens'`.
- **With astro-tigger-lsm 1.8.0, case-sensitive filesystem.** `import Tigger` works, because `astro-kittens` also comes in, and `kittens` sits beside it unused.
- **With astro-tigger-lsm 1.8.0, case-insensitive filesystem (NTFS through WSL).** `kittens/` and `Kittens/` land in the same directory, so `kittens/__init__.py` replaces `Kittens/__init__.py`, and `import Tigger` fails with `No module named 'requests'`, or `No module named 'Kittens'`, depending on the install. I would expect the same on a default macOS volume, but have not tested it.

After `astro-kittens` the next missing import is `six` (`Purr/Render.py` and others), which is not declared either. With both declared, `import Tigger` works on the NTFS volume, and on a case-sensitive one `import Purr` gets as far as `Failed to load Qt4. Purr is not available`, which I have left alone.

A PR follows with the one changed line in `setup.py`.
<!-- /issue-body -->
