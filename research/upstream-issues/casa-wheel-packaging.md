Target: NRAO helpdesk https://help.nrao.edu (CASA department; my.nrao.edu login) or casa-feedback@nrao.edu. TEXT-ONLY: CASA has no public issue tracker (casa6 source is read-only on open-bitbucket.nrao.edu).
Status: not sent, owner decision 2026-11-12: no contributions to CASA (research/v8-open-casa.md section 5). Kept as the record of CASA's defects; rang's tests check it does not copy them.
Reproduced on: casatools 6.7.6.14 / casatasks 6.7.6.14 (latest on PyPI, 2026-08-07), cp312, run 2026-11-12: manylinux_2_34 wheel on Ubuntu 24.04.5 (OpenSSL 3.0.13, container) and Ubuntu 26.04 (OpenSSL 3.5.5); manylinux_2_28 wheel on Ubuntu 26.04. Metadata read from the installed wheels and in source at casa6 master 90e9d3dae955.
Duplicates checked: CASA Docs Known Issues and 6.7.6 platform table (casadocs.readthedocs.io, stable); GitHub-wide issue search "casatools libssl", "casatools OPENSSL_3.0.1", "manylinux_2_34 casatools", "casatools openssl": no matches. NRAO JIRA is not public, so a duplicate there cannot be ruled out.

Title: casatools 6.7.6.14 manylinux_2_34 wheel does not import on Ubuntu 24.04/26.04 (bundled libssl without its libcrypto); wheel licence metadata contradicts itself

---

Two packaging problems in the casatools 6.7.6.14 wheels on PyPI.

**1. The manylinux_2_34 wheel fails to import outside RHEL 9**

pip and uv pick `casatools-6.7.6.14-cp312-cp312-manylinux_2_34_x86_64.whl` on any glibc >= 2.34 host. On Ubuntu 24.04 (listed in the CASA 6.7.6 test table for Python 3.12) it does not import:

```
python3.12 -m venv v && v/bin/pip install casatools==6.7.6.14
v/bin/python -c "import casatools"
ImportError: /lib/x86_64-linux-gnu/libcrypto.so.3: version `OPENSSL_3.0.1' not found
  (required by .../casatools/__casac__/lib/libssl.so.3)
```

Ubuntu 26.04 (OpenSSL 3.5.5) fails with the same error. Preloading the system libssl moves the failure to the bundled libldap:

```
ImportError: .../casatools/__casac__/lib/libldap.so.2: undefined symbol: EVP_md2, version OPENSSL_3.0.0
```

Cause, from `objdump -T` of the wheel's `casatools/__casac__/lib`:

- `libssl.so.3` is bundled; its debug link names `libssl.so.3.2.2-3.2.2-6.el9_5.1`, i.e. the RHEL/AlmaLinux 9 openssl package. It needs `libcrypto.so.3` but libcrypto is not bundled, so the system one is used.
- The bundled libssl imports `ossl_ctx_legacy_digest_signatures_allowed@OPENSSL_3.0.1`. Neither Ubuntu's 3.0.13 nor its 3.5.5 exports that symbol version; it looks like a distribution-patched OpenSSL symbol. The SBOM in the wheel (`casatools-6.7.6.14.dist-info/sboms/auditwheel.cdx.json`) shows the build host is AlmaLinux 9, e.g. `openldap 2.6.6-3.el9`.
- It also imports 19 `OPENSSL_3.2.0` symbols (`OSSL_ERR_STATE_save`, `BIO_sendmmsg`, ...), so it cannot work with any 3.0/3.1 libcrypto either.
- The bundled `libldap.so.2` needs `EVP_md2`, which upstream OpenSSL 3.x builds do not provide by default.

The manylinux_2_28 wheel of the same release imports on Ubuntu 26.04. It bundles `libssl.so.1.1` together with its own `casatools.libs/libcrypto-401bea5d.so.1.1.1k`, so the pair is consistent. The workaround is `pip install --only-binary :all: --platform manylinux_2_28_x86_64 ...` (or `uv pip install --python-platform x86_64-manylinux_2_28`).

Suggested fix: bundle libcrypto alongside libssl and libldap in the 2_34 wheel (as the 2_28 wheel does), or link them against the system OpenSSL without the bundled copies. Test the 2_34 wheel on a non-RHEL host, e.g. Ubuntu 24.04, which pip selects it for.

**2. The licence metadata contradicts itself**

From the installed 6.7.6.14 wheels' `METADATA`:

| | `License:` field | `License ::` classifier | file headers |
| --- | --- | --- | --- |
| casatools | `GPLv2` | GNU Library or Lesser General Public License (LGPL) | `setup.py`: `SPDX-License-Identifier: GPL-2.0-or-later` followed by the GNU *Library* GPL v2-or-later notice |
| casatasks | `GNU Library or Lesser General Public License (LGPL)` | none | LGPL v2-or-later (e.g. `casatasks/private/imagerhelpers/_gclean.py`); `casatasks/LICENSE.txt` is the GNU LGPL 2 text |

In source at casa6 master 90e9d3dae955:

- `casatools/setup.cfg:6` has `license = GPLv2`.
- `casatools/setup.cfg:22` has the LGPL classifier.
- `casatools/setup.cfg:7` has `license_files = LICENSE.txt`, but no licence file is in the casatools wheel's dist-info or package.
- `casatools/setup.py:2` has the GPL-2.0-or-later SPDX tag, but the notice below it is the LGPL notice.
- The same `setup.cfg` also lists classifiers for Python 3.6 to 3.10 and `python_requires = >=3.6`, while the wheels are cp312/cp313 only.

GPL-2.0-only, GPL-2.0-or-later and LGPL-2.0-or-later give downstream users different rights, so licence scanners and redistributors cannot tell which one applies. Please state one licence and use it consistently: an SPDX `License-Expression` (Metadata 2.4, already used by these wheels), the matching classifier, and the licence text shipped in both wheels.
