Target: https://github.com/ska-sa/katdal/issues
Status: ready to post
Reproduced on: katdal 0.23 (latest on PyPI, 2024-06-28), setuptools 84.2.1, python-casacore 3.8.1, Python 3.13.16, Linux (WSL Ubuntu), 2026-11-12; fixed on master 84432ef (read in source at 918c281)
Duplicates checked: all 19 open issues and 7 open PRs listed (none is a release request or release PR); search/issues repo:ska-sa/katdal "pkg_resources" (#379 closed by 84432ef, #394 PR, #20, #46), "release", "new release", "setuptools", "parse_version": no open request for a release

Title: Release request: katdal 0.23 on PyPI fails to import ms_extra (pkg_resources) with current setuptools
---
The fix for #379 (84432ef, "Remove problematic pkg_resources", 2026-07-09) is on master but not on PyPI. katdal 0.23 is the latest release (2024-06-28), and with current setuptools it cannot run `mvftoms.py`:

```
$ uv venv -p 3.13 && uv pip install katdal==0.23 python-casacore
$ mvftoms.py --help
  ...
    from . import ms_extra
  File ".../site-packages/katdal/ms_extra.py", line 30, in <module>
    from pkg_resources import parse_version
ModuleNotFoundError: No module named 'pkg_resources'
```

Versions resolved by that install: katdal 0.23, setuptools 84.2.1 (pulled in by `katsdptelstate[rdb]` on Python >= 3.12), python-casacore 3.8.1, katsdptelstate 1.0.0. setuptools removed `pkg_resources` in 82, so any fresh environment hits this; the workaround is pinning `setuptools<82`.

`katdal/ms_extra.py` lines 30-34 at v0.23 (2a09df9) import `pkg_resources.parse_version` for a python-casacore >= 2.2.1 check; master (src/katdal/ms_extra.py) no longer has it. Could you publish a release (0.24) with the current master?
