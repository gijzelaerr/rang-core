# An optional CARTA helper for the notebooks (task NB-CARTA)

Task NB-CARTA of [big-plan.md](big-plan.md), branch `nbcarta-helper` from
`d4dcb20`. Defined by [ecosystem-survey.md](ecosystem-survey.md) sections 4.3
(the helper proposal) and 5.2 item 10: a `[carta]` extra and
`rang.notebook.carta.open/snapshot`, so a whole-array dirty image or a cube
can be inspected in CARTA from a notebook. Tooling only: no scientific
protocol, no claim about calibration or imaging quality.

Status: **plan frozen 2026-10-31** (this section), before the
implementation. A scratch probe ran first (below).

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
