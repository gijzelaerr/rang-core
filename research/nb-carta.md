# An optional CARTA helper for the notebooks (task NB-CARTA)

Task NB-CARTA of [big-plan.md](big-plan.md), branch `nbcarta-helper` from
`d4dcb20`. Defined by [ecosystem-survey.md](ecosystem-survey.md) sections 4.3
(the helper proposal) and 5.2 item 10: a `[carta]` extra and
`rang.notebook.carta.open/snapshot`, so a whole-array dirty image or a cube
can be inspected in CARTA from a notebook. Tooling only: no scientific
protocol, no claim about calibration or imaging quality.

Status: **implemented and measured 2026-10-31.** Plan frozen in `b505eaf`
before the implementation (a scratch probe ran first, below). Both named
images open from a notebook kernel on Linux (WSL) in CARTA 6.0.0 in its
pinned container and snapshot with the raster drawn; the LUNO slice, which
had no cube, was imaged as an 8-plane channel-block cube by the core and
opened with its 8-channel frequency axis. On native Windows and without
CARTA, `available()` is False, `open` raises `CartaUnavailable`, and the
notebook 04 cell prints its skip line (papermill, switch off).

## Scratch probe (before freezing)

`~/Build/tmp/20261031-nbcarta/scripts/probe*.py` (scratch): CARTA 6.0.0
backend in `cartavis/carta@sha256:951834b9…f79f2` with `--enable_scripting`,
a headless Chromium in `selenium/standalone-chromium@sha256:c7c17cd7…70` in
the CARTA container's network namespace, ports published on 127.0.0.1 only;
carta-python at commit `989af8ed` driving it through
`selenium.webdriver.Remote`. The LUNO whole-array dirty image (1024 x 1024)
opened in 7 s (session) + 1 s; `save_rendered_view` drew axes but an empty
raster until Chromium ran with SwiftShader WebGL
(`--enable-unsafe-swiftshader --use-angle=swiftshader
--ignore-gpu-blocklist`), after which the raster rendered within 2 s.
No `*.fits` under `outputs/` has `NAXIS3 > 1`: there is no LUNO cube yet.

## Plan

### Install path

- **The wrapper has no PyPI release**, and its distribution name in
  `setup.py` is `carta`, the same name as the unrelated PyPI package
  `carta` 1.3.3 (never install that). rang-core publishes to PyPI
  (`wheels.yml` `publish`), and PyPI refuses direct-URL requirements, so the
  wrapper cannot be a dependency of the extra.
- **`[carta]` holds the wrapper's PyPI dependencies only**
  (`requests`, `simplejson`, `selenium` for the headless browser,
  `astropy` for the FITS writer). The wrapper is installed by a documented,
  pinned command, by commit (the `v1.2.0` tag is an annotated tag object
  `2fa28da5…`, commit `989af8ed97238931abe5f235add37e0813bf7e0b`):

  ```sh
  pip install -e '.[carta]'   # rang-core[carta] once released
  pip install 'carta @ git+https://github.com/CARTAvis/carta-python@989af8ed97238931abe5f235add37e0813bf7e0b'
  ```

- **The backend runs in a pinned container**:
  `cartavis/carta:6.0.0@sha256:951834b9ff3f2de5b5ced18aa486ed6cdc00e52b526945ca321d53cf2d3d79f2`
  (CARTA 6.0.0, entrypoint `carta_backend --no_browser --top_level_folder
  /images /images`), with `--enable_scripting`, the session directory
  mounted read-only at `/images`, port 3002 published on 127.0.0.1 only.
  For headless snapshots, a pinned Chromium shares its network namespace:
  `selenium/standalone-chromium:155.0@sha256:c7c17cd79c62819a8329df00e610dbc4073c279da034a6f37135d454eb0d8870`
  (WebDriver on 127.0.0.1:4444). A native `carta` (AppImage, deb, KERN)
  works the same through `RANG_CARTA_URL` and an identity path mapping.
- **Licence.** carta-python and the CARTA backend and frontend are
  GPL-3.0; selenium is Apache-2.0. An optional DEPEND is compatible with
  rang's GPL-3.0-or-later. Nothing is vendored.

### API (`python/rang/notebook/carta.py`)

Plain functions, as the other notebook modules; nothing starts a container
or opens a port unless a function named for it is called.

- `available()`: True when the platform is not Windows, the CARTA wrapper
  (not the unrelated `carta`) imports, and the backend at `RANG_CARTA_URL`
  answers. `problem()` returns the reason when it is False.
- `write_fits(array, path, *, wcs=None)`: a NumPy image or cube as FITS
  (float32; `wcs` an astropy WCS or a dict of FITS keys; a 2-D image or a
  3-D cube gains the degenerate axes the header names).
- `image_header(ds, img)` and `channel_cube(ds, sol=None, planes=8, ...)`:
  the WSClean-convention header of an `image.image` result
  (`core_grid.wcs_header`), and a channel-block cube of dirty images made
  by `image.image` with the channels outside each block flagged (nothing
  reimplemented).
- `connect(url=None, *, webdriver=None, session_id=None)`: a carta-python
  `Session`, headless through the WebDriver (default `RANG_CARTA_WEBDRIVER`)
  or attached to the user's own browser tab (`session_id`).
- `open(path_or_array, *, wcs=None, name=None, session=None)`: writes a
  NumPy array, or the dirty image of an `image.image` result, to a FITS file
  in the session directory (`RANG_CARTA_DIR`, default
  `<notebook cache>/carta`), or copies a FITS path there, opens it in the
  running backend and returns the session handle. Raises `CartaUnavailable`
  with the install or start command when `available()` is False.
- `snapshot(session, path)`: a PNG of the current view
  (`save_rendered_view`), retried until the raster is drawn.
- `close(session)`; `docker_commands(data_dir)` (the two `docker run`
  lines, printed, not run); `start_docker(data_dir)` and `stop_docker()`
  (explicit, for the acceptance and for users who ask for it).
- The switch `RANG_NOTEBOOK_CARTA=1` (default off) and `skip_line()` in the
  format of `rang.notebook.science`.

### Notebook, docs, tests

- One cell at the end of `notebooks/04-imaging.ipynb`: with the switch on
  and `available()`, it opens the corrected dirty image (with its header)
  and saves a snapshot; otherwise it prints the skip line (with the reason
  when the switch is on). Outputs cleared.
- `docs/tutorials/index.md`: the switch in the switches list.
- `tests/test_nb_carta.py`: the FITS writer (array, cube, header round
  trip through astropy), `image_header`, the unavailable path (Windows,
  missing or wrong wrapper, no URL, unreachable URL: `available()` False,
  `open` raises with the command), the skip line; the live path behind
  `RANG_NOTEBOOK_CARTA=1` and `available()`.

### Acceptance

1. On Linux (WSL) with the two containers: the whole-array dirty image
   `outputs/luno-array-campaign-20261030-01/images/original-dirty.fits`
   opens from a notebook kernel, and a snapshot PNG shows its raster.
2. The LUNO slice as a cube: no cube exists, so a channel-block cube of the
   four-station LUNO slice (`channel_cube`, 8 planes) is written and opened
   the same way, and CARTA reports the frequency axis of 8 channels.
3. On Windows and without CARTA: `available()` is False, `open` raises a
   clear error, and the notebook cell prints its skip line; notebook 04
   executes through `docs/execute_notebooks.py`'s papermill call with the
   switch off.
4. `bash tools/check-all.sh` prints `overall: PASS`.

Snapshot PNGs and FITS files stay in ignored outputs; no image is
committed.

## Implementation

| File | What |
| --- | --- |
| `python/rang/notebook/carta.py` | `available`, `problem`, `write_fits`, `image_header`, `channel_cube`, `connect`, `open`, `snapshot`, `close`, `docker_commands`, `start_docker`, `stop_docker`, `switch`, `skip_line`; the pinned images and wrapper commit as constants |
| `pyproject.toml` | `carta = ["astropy>=6", "requests>=2.31", "simplejson>=3.19", "selenium>=4.40"]` with the wrapper's pinned install command in a comment |
| `notebooks/04-imaging.ipynb` | a markdown cell and one code cell at the end, behind `RANG_NOTEBOOK_CARTA=1`; outputs cleared |
| `docs/tutorials/index.md` | the fourth switch in the switches paragraph |
| `tests/test_nb_carta.py` | 15 tests: FITS writer (image with WSClean axes, cube, astropy WCS), `image_header`, staging, the unavailable path (Windows, wrapper missing, the unrelated `carta`, no URL, unreachable URL), the loopback-only docker lines, the skip line, the notebook cell executed in isolation (switch off; on but unavailable); the live open/snapshot behind `RANG_NOTEBOOK_CARTA=1` and `available()` |

Behaviour worth knowing:

- `open` checks `problem()` before anything is written; it starts nothing.
  The connection is a headless Chromium (WebDriver, `selenium.webdriver.Remote`)
  by default or, with `RANG_CARTA_SESSION_ID`, a session open in the user's
  own browser (`Session.interact`).
- Paths: CARTA's `openFile` takes the directory **relative to the backend's
  top-level folder** even when it starts with `/` (`/images` became
  "Directory /images/images does not exist"), so `RANG_CARTA_ROOT` defaults
  to `/` (the container mounts the session directory as its top-level folder
  `/images`); for a native backend started with top-level `/` it is the
  directory's absolute path.
- `start_docker` creates the session directory before `docker run`: a
  bind-mount source that docker creates is owned by root, and the first
  acceptance attempt failed with `PermissionError` for that reason.
- `channel_cube` composes `image.image` with the channels outside each
  block flagged; a block whose cells are all flagged becomes a NaN plane
  (the LUNO slice's planes 3 and 4, 1177–1284 MHz, are 100 % flagged in the
  original flags; the gridder returns code 1 on an empty block).
- `snapshot` re-renders until the centre of the view is opaque (matplotlib
  decodes the PNG; without matplotlib it saves the first render).
- `close` closes the headless browser and disarms carta-python's
  `Session.__del__`, which otherwise closes again at interpreter shutdown
  and prints an `ImportError: sys.meta_path is None` traceback.

## Measured acceptance

Driver `~/Build/tmp/20261031-nbcarta/scripts/acceptance.py` (scratch,
deleted): builds a five-cell notebook and executes it in a `python3`
kernel (nbconvert `ExecutePreprocessor`), with the containers started by
`carta.start_docker` and stopped afterwards. Executed notebook, FITS
files, PNGs and `acceptance.json` in `outputs/nbcarta-20261031-01`.

| Check | Result |
| --- | --- |
| 1. whole-array dirty image `outputs/luno-array-campaign-20261030-01/images/original-dirty.fits` (1024 x 1024, 4.2 MB) | opened: CARTA frame shape `[1, 1, 1024, 1024]`, FK5 axes, raster drawn (centre opaque fraction 1.0); open 7.1 s (of which the headless session about 6 s), snapshot 2.3 s |
| 2. LUNO slice as a cube | `data.load_luno()` (local slice), `gains.solve`, `channel_cube(planes=8)` in 2.0 s: 8 planes of 512 x 512 at 1096.6–1471.1 MHz (53.5 MHz blocks), peaks 14.97, 14.67, NaN, NaN, 14.99, 14.97, 14.87, 14.81 Jy/beam (PKS 1934-638 at the phase centre); written as `(1, 8, 512, 512)` FITS (8.4 MB) and opened in the same session in 0.27 s: CARTA frame shape `[1, 8, 512, 512]`, depth 8; channel 4 selected and snapshot with the raster drawn |
| 3a. live pytest (`RANG_NOTEBOOK_CARTA=1`, containers up, `outputs/nbcarta-20261031-02`) | 15 passed in 10.4 s, the live test included |
| 3b. notebook 04 with the switch on (nbconvert, same backend) | the cell opened the corrected fixture dirty image with its header and displayed the snapshot (`outputs/nbcarta-20261031-02/04-imaging.ipynb`), 19.9 s for the notebook |
| 3c. notebook 04 with the switch off through `docs/execute_notebooks.py`'s `execute` (papermill), `outputs/nbcarta-20261031-03` | 8.2 s; the cell printed `skipped: set RANG_NOTEBOOK_CARTA=1 to open the images in a running CARTA backend (Linux or macOS)` |
| 3d. native Windows (the main mirror's `.venv` Python 3.14, read-only; `carta.py` and the tests copied to the session scratchpad and loaded as `rang.notebook.carta`) | `available()` False, `problem()` "CARTA has no Windows build; …", `open` raised `CartaUnavailable`; pytest 8 passed, 7 skipped (no astropy or IPython in that venv; the live test) |
| 4. `bash tools/check-all.sh` | see below |

## Deviations

- **The LUNO "cube slice" did not exist as an image.** No FITS under
  `outputs/` has `NAXIS3 > 1` and the LUNO slice is visibilities. The cube
  is an 8-plane channel-block dirty cube made by `channel_cube` (as frozen
  in the plan, acceptance 2). Two of its planes are empty (fully flagged
  original data), written as NaN.
- **`RANG_CARTA_ROOT` default** is `/`, not `/images` as the plan's API
  paragraph implied: CARTA resolves `openFile` directories relative to its
  top-level folder (Implementation). Found by the first acceptance run.
- **Notebook 04 got a markdown heading cell as well as the one code cell**,
  so the optional section does not sit under "Steer it yourself".
- The helper also exports `channel_cube`, `docker_commands`,
  `start_docker`/`stop_docker` and `close`, as the frozen API lists.

## Open items

- macOS was not tried (CARTA has native macOS builds; the helper does not
  depend on Linux beyond the container commands).
- carta-python v1.2.0 is the last tag (2026-10-25 push on the default
  branch); when a release adds a PyPI upload, the extra can name it
  directly and the comment goes.
- IDIA HDF5 for multi-GB cubes (survey 4.4) is not written; `open` refuses
  to copy files over 1 GiB and asks for `RANG_CARTA_DIR` at the file's
  directory instead.
- The headless Chromium image is 2.3 GB; a user with CARTA open in a
  browser can skip it (`RANG_CARTA_SESSION_ID`).

### Check-all

`bash tools/check-all.sh` (`OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`) on
the branch at `654c61e`: `overall: PASS`; pytest 731 passed, 14 skipped in 172.9 s. Log
`outputs/nbcarta-20261031-check-all.log`.

## Timings

| Date | Tool run | Input | Wall time | Peak memory | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-31 | big plan NB-CARTA: `uv venv` + editable install (`pointing,beam,test,imaging,notebook`, ruff, maturin, pip) | worktree | 169.4 s | — | includes the extension build; shared host |
| 2026-10-31 | big plan NB-CARTA: `docker pull cartavis/carta:6.0.0` | Docker Hub | 20.2 s | — | 312 MB image, digest `sha256:951834b9…f79f2` |
| 2026-10-31 | big plan NB-CARTA: `docker pull selenium/standalone-chromium@sha256:c7c17cd7…` | Docker Hub | 103.2 s | — | 2.29 GB image (155.0) |
| 2026-10-31 | big plan NB-CARTA: `git clone --depth 1 --branch v1.2.0 carta-python` | GitHub | not timed (seconds) | — | read as data, scratch |
| 2026-10-31 | big plan NB-CARTA: `uv pip install` carta-python at `989af8ed` + selenium, requests, simplejson | PyPI + GitHub | 7.6 s | — | selenium 4.52.0, simplejson 4.2.0 |
| 2026-10-31 | big plan NB-CARTA: scratch probes (headless session, open, snapshot) | whole-array dirty image | 12.6 s each | — | first probe drew an empty raster (no WebGL); SwiftShader flags fixed it |
| 2026-10-31 | big plan NB-CARTA: live acceptance notebook (start containers, both images, snapshots, stop) | whole-array image; LUNO slice | 35.7 s | 606 MB | open 7.1 s + snapshot 2.3 s; cube 2.0 s + open 0.27 s; two earlier attempts failed (root-owned mount, top-level-relative path), fixed |
| 2026-10-31 | big plan NB-CARTA: `pytest tests/test_nb_carta.py`, `RANG_NOTEBOOK_CARTA=1`, backend up | worktree | 11.0 s | — | 15 passed |
| 2026-10-31 | big plan NB-CARTA: nbconvert notebook 04, switch on | fixture | 19.9 s | — | cell opened the dirty image and showed the snapshot |
| 2026-10-31 | big plan NB-CARTA: papermill notebook 04 via `docs/execute_notebooks.py` `execute`, switch off | fixture | 8.2 s | — | skip line printed |
| 2026-10-31 | big plan NB-CARTA: Windows: `pytest` of the scratch copy, main mirror's `.venv` | Windows | 2.3 s | — | 8 passed, 7 skipped |
| 2026-10-31 | big plan NB-CARTA: `bash tools/check-all.sh` | branch at `654c61e` | 502.4 s including the lock wait | 2.06 GB | `overall: PASS`; pytest 731 passed, 14 skipped in 172.9 s |

## For the coordinator

### Shared-file hunks

`python/rang/notebook/__init__.py`, the module list in the docstring (after
the `steer` line):

```text
- `carta`: optional; open images and cubes in a running CARTA backend (research/nb-carta.md).
```

and `__all__` (sorted):

```python
__all__ = [
    "carta",
    "data",
    "experiment",
    "flags",
    "gains",
    "image",
    "science",
    "steer",
    "survey",
]
```

`README.md`, a bullet after "Science notebooks: …" (optional):

```text
- CARTA from the notebooks (optional; Linux or macOS): `pip install -e '.[carta]'`,
  CARTA's wrapper from its pinned commit and a backend (the pinned container);
  `rang.notebook.carta.open/snapshot`, notebook 04 with `RANG_NOTEBOOK_CARTA=1`;
  see `research/nb-carta.md`.
```

### STATE paragraph

> NB-CARTA, an optional CARTA helper for the notebooks (big plan;
> [nb-carta.md](nb-carta.md)), 2026-10-31 (implemented; measured):
> `rang.notebook.carta` writes a NumPy image or cube, or the core's dirty
> image, to FITS in a session directory and opens it in a running CARTA
> backend through CARTA's wrapper (`open`, `snapshot`, `available`;
> `channel_cube` images channel blocks with the core). The `[carta]` extra
> holds the PyPI dependencies only: carta-python has no PyPI release, its
> distribution name collides with the unrelated PyPI `carta`, and PyPI
> refuses direct references, so the wrapper installs from commit
> `989af8ed` (v1.2.0) by a documented command. The backend runs in
> `cartavis/carta:6.0.0` and the views render in a pinned headless
> Chromium (SwiftShader WebGL), both by digest and on 127.0.0.1 only;
> nothing starts unless asked. On WSL the LUNO whole-array dirty image
> (1024²) and an 8-plane channel-block cube of the LUNO slice open from a
> notebook kernel (7.1 s and 0.27 s) and snapshot with the raster drawn;
> on native Windows `available()` is False, `open` raises, and notebook
> 04's new cell (`RANG_NOTEBOOK_CARTA=1`, default off) prints its skip
> line. `outputs/nbcarta-20261031-01`.

### `research/README.md` index entry

```text
- [nb-carta.md](nb-carta.md): NB-CARTA, `rang.notebook.carta` (open/snapshot in CARTA 6.0 from a notebook), the `[carta]` extra and the pinned wrapper/containers; implemented and measured 2026-10-31.
```

### Tool-timings rows

The rows of the Timings table above, as they stand.

### Non-RATT observations (CARTA and carta-python; not filed)

1. carta-python (v1.2.0, `989af8ed`) has no PyPI release and its
   `setup.py` names the distribution `carta`, the name of an unrelated
   PyPI package (`carta` 1.3.3): `pip install carta` installs the wrong
   thing, and a project cannot depend on the wrapper from PyPI.
2. `carta.browser.Chrome(driver_path=...)` passes `executable_path` to
   `selenium.webdriver.Chrome`, which Selenium 4.10+ no longer accepts
   (4.52.0 signature: `options, service, keep_alive`); verified from the
   signature, not run.
3. `Session.__del__` calls `close()` again; after an explicit `close()` of
   a headless session it prints `ImportError: sys.meta_path is None` at
   interpreter shutdown.
4. `carta/util.py` passes `re.sub`'s `count` positionally: a
   `DeprecationWarning` on Python 3.13+ at import.
5. CARTA 6.0.0's `openFile` scripting action treats an absolute directory
   as relative to the top-level folder (`/images` -> "Directory
   /images/images does not exist").
6. The `cartavis/carta:6.0.0` image's entrypoint does not enable the
   scripting interface (`--enable_scripting` has to be passed), and a
   headless Chromium without a GPU draws CARTA's axes around an empty
   raster unless SwiftShader WebGL is enabled
   (`--enable-unsafe-swiftshader --use-angle=swiftshader`).
7. `carta/backend.py` starts the backend with `preexec_fn=os.setpgrp`, so
   `Session.start_and_*` cannot work on Windows (consistent with CARTA
   having no Windows build).

### Ignored output directories

- `outputs/nbcarta-20261031-01`: the live acceptance (executed notebook,
  `acceptance.json`, the two snapshot PNGs, `session/` with the copied
  whole-array FITS and the LUNO channel cube FITS);
- `outputs/nbcarta-20261031-02`: notebook 04 and the live pytest with the
  switch on (executed notebook with the snapshot, `session/`);
- `outputs/nbcarta-20261031-03`: notebook 04 through papermill with the
  switch off;
- `outputs/nbcarta-20261031-check-all.log`.

Docker images left on the host: `cartavis/carta:6.0.0` (312 MB) and the
pinned `selenium/standalone-chromium` (2.29 GB), for reruns; remove with
`docker rmi` if space is needed. No container is left running.
