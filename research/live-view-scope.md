# Live view: insight during and after a run, scoping note

Written 2026-11-20 on the owner's request ("getting more insight and
visualisations DURING the work ... a browser UI that connects to a running
process ... integrate with other systems ... 0.5.0 or later?").
**Status: direction decided by the owner on 2026-11-20 (section 6); nothing is
built or measured.** The inventory in
section 1 was read from `main` at `92e67e2f`; the candidate table in section 4
was checked on the web and the GitHub API on 2026-11-20. No scientific or
performance claim; tooling only.

## 0. The answer in brief

1. **Build the record first, the viewers second.** A run writes an append-only
   event stream and small array snapshots into its run directory. Every viewer
   (terminal, browser, notebook, agent, an external tool) only reads them. A
   live view and an after-the-run view are then the same thing: one follows
   the files as they grow, the other replays them.
2. **Files, not a socket, are the contract.** Runs are on nash or glacier and
   the owner sits at a Windows machine; runs crash, resume and run as spool
   shards. Files survive all of that. A viewer may open a socket of its own.
3. **Three readers, in order of cost:** `rang-core watch` in the terminal
   (plain lines and JSON for agents and SSH); two MCP tools so an agent can
   read the events and look at a snapshot; `rang-core view`, a local web
   server on 127.0.0.1 that a browser follows live, reached through an SSH
   port forward for a remote run.
4. **Browser viewer: try Rerun before writing one.** Rerun (MIT or
   Apache-2.0, 0.43.2 of 2026-11-13, Rust and Python SDKs, native viewer on
   Windows and a web viewer) attaches to a live stream, replays a saved
   recording and has one timeline per counter (time, minor iteration, major
   cycle, selfcal round). A one-day spike on an archived run decides between
   it and a small page of our own. The Makepad application of the earlier
   discussion is a later reader of the same record, not the first.
5. **Placement (owner decision 3):** not v0.4.0 (fork on 2026-11-23). The
   record, `watch` and the MCP tools as one small item of v0.5.0, whose theme
   (Scale) needs remote status anyway; the browser view as a second item of
   v0.5.0 if the spike is good; steering a run from the view (pause, edit the
   mask, stop) later, with its own note.

## 1. What a run shows today

| Source | Granularity | Live |
| --- | --- | --- |
| `<run_dir>/state.json` (`core_pipeline`) | per stage: running, done, failed, stale; times | yes, on stage boundaries |
| receipts (`receipts/*.rang-receipt.json`) | per stage, after it finishes | no |
| MCP `run_status`, `receipts` (`mcp_tools.py`) | reads the two above and the job files | stage level |
| spool executor (`core_spool.py`) | tasks waiting and claimed, a heartbeat per worker | yes, but only as files nobody renders |
| stage `log` callable (`core_pipeline.execute(..., log=print)`) | free-text lines to stderr | yes, unstructured |
| `gemclean.log` per image (GeMClean runs as a subprocess) | a summary per scale, one auto-mask line per major iteration (σ, threshold), the stop line; 22 lines for 12,924 s in E2-N round 1 | not checked whether lines appear as they happen; `gemclean_stop` reads the stop line with a regular expression |
| notebooks, `rang.notebook.carta` | plots and CARTA after the run | no |
| `outputs/status/<task>.md` | written by hand by each agent, every 30 minutes | by hand |

So a stage is visible at its boundaries and through free text. Nothing
structured is written while one runs (corrected 2026-11-20: GeMClean's
`image-report.json` holds every major cycle's peak, threshold, objective and
times, written when the image is finished): no image per major cycle,
nothing per solve interval, nothing inside a minor cycle (`core/src` has no
callback or progress code; GeMClean prints with `println!`).

Where it would have paid, from this repository's own record:

- E2-N's selfcal took 49,613 s, 65 % of it in the minor cycle and resyncs
  ([dl0-profile.md](dl0-profile.md)); nothing was visible inside those hours.
- E2-A's frozen 0.5σ multiscale depth ran into `niter` 1e6 after 30,615 s
  ([e2-acceptance.md](e2-acceptance.md) 9.5-9.8). A peak-residual curve
  would have shown, hours earlier, whether it was still converging. GeMClean
  keeps the curve per major cycle (`Cycle`: peak, threshold, objective before
  and after) but writes it only at the end, in `image-report.json`.
- The K outlier of [calchain-floor.md](calchain-floor.md) (ID 50, interval 7,
  2,335 ns against 0.11 ns elsewhere) was found after the fact; a delay
  panel shows it when the solve finishes.

## 2. The record (proposed)

- **Events:** `<run_dir>/events/<stage>-<process>.jsonl`, one JSON object per
  line, appended and flushed; one file per writing process, so spool workers
  and a resumed run never share a file. Fields: UTC time, stage, kind,
  counters (chunk, scan, solve interval, major cycle, minor iteration,
  selfcal round), scalars. A `schema` integer in the first line.
- **Snapshots:** `<run_dir>/snapshots/<name>-<counter>.npy` (small float32
  arrays, written to a temporary name and renamed), each announced by an
  event. Bounded: a decimated residual (at most 512²) per major cycle, gain
  tables as solved, a time-frequency flag occupancy per scan.
- **Written by the Rust core for the hot loops** (GeMClean, the solvers), at
  major-cycle and solve-interval boundaries and at most once every few
  seconds inside a minor cycle; by Python for stage and chunk boundaries. No
  Python callback inside a kernel.
- **Kinds, first set:**

  | Stage | Events | Snapshots |
  | --- | --- | --- |
  | all | stage and chunk start and end, rows done of total, CPU, memory, IO wait, warnings | – |
  | flag | fraction flagged per scan, per antenna, per pass | occupancy, time × frequency |
  | calibrate | per solve interval: iterations, χ², converged, refant; per term outliers | gains (amplitude, phase, delay) per antenna |
  | image, selfcal | per major cycle: peak residual, RMS, model flux, components, scale, stop-rule state; per selfcal round: dynamic range | decimated residual and model, mask |
  | learned stages (v0.4.0) | inference time, proposals accepted | – |

- **Gates before it merges:** every output of the pipeline bit-identical with
  the record on and off (the record only reads); overhead at most 1 % of wall
  time on an E2-scale selfcal, measured exclusive and logged in
  `tool-timings.md`; the switch stays out of `core_config.stage_hash`, so
  turning the record on or off makes no finished stage stale (as DL1 did for
  `learned:`); a reader on Windows never blocks or breaks the writer (files
  being appended and renamed; the sharing violation of
  [v030-review.md](v030-review.md) R-01 is the precedent); the five wheel
  platforms; no new required dependency; a `RANG_*` switch listed in
  `rang.core.ENVIRONMENT`.

## 3. The readers (proposed)

| Reader | What it is | Cost | Notes |
| --- | --- | --- | --- |
| `rang-core watch <run_dir>` | follows the events; plain lines, `--json`, `--once`; an optional full-screen mode | S | works over SSH and in a job log; can write `outputs/status/<task>.md` itself |
| MCP `run_events`, `run_snapshot` | the events since a cursor; one snapshot as a PNG | S | the agent can say "the residual stopped falling at cycle 7" and show the image; the main integration for ra-ng |
| `rang.notebook.live(run_dir)` | the existing notebook plots fed from the record | S | – |
| `rang-core view <run_dir>` | a server on 127.0.0.1 and a browser page that follows the run; panels of section 2; two runs side by side after the fact | M | remote through `ssh -L`; viewer choice in section 4 |
| open in CARTA | the full-resolution residual of the last major cycle in a running CARTA session, through the existing helper | S | Linux only; carta-python documents `open_image`, no reload |
| steering | pause, edit the mask, stop after this cycle, from the view | L | changes results, so it must be recorded in the receipt; own note; casagui's interactive clean is the prior art |

## 4. Candidates checked (2026-11-20)

| Tool | Licence | Activity | Attach to a live run | Fit |
| --- | --- | --- | --- | --- |
| [Rerun](https://github.com/rerun-io/rerun) | MIT or Apache-2.0 | 0.43.2, 2026-11-13; 0.33 on 2026-05-29, so about two minor releases a month, with breaking changes | yes: `serve_grpc` in the process (late viewers get the history, 1 GiB buffer by default), `serve_web_viewer`, `rerun --connect` over a forwarded port; `.rrd` files for replay | **spike first.** Rust and Python SDKs. Versions: a viewer opens the previous minor version's `.rrd` only (N-1 since 0.23), and SDK and viewer should match, so the bridge runs next to the viewer, both pinned, and `.rrd` is never archived (regenerated from the record). To confirm in the spike, not checked today: scalar, image and tensor views, one timeline per counter, the native Windows viewer, no astronomy axes (WCS) |
| Bokeh / Panel | BSD-3 | both pushed this week | yes, a Bokeh server | what ragavi, casagui and the Dask dashboard use (shadeMS is datashader and matplotlib), so astronomers know it; a Python server process per view and a large dependency |
| A page of our own (standard-library server, server-sent events, one small plotting script) | – | – | yes | smallest dependency, full control over panels, JavaScript to maintain |
| [casagui](https://github.com/casangi/casagui) interactive clean | LGPL-2.1 | PyPI 0.3.111; pushed 2026-11-18 | yes, it drives `tclean` between major cycles | prior art for the imaging panel and for steering; tied to casatools, not reusable as is |
| TensorBoard, [trackio](https://github.com/gradio-app/trackio) (MIT, SQLite, local dashboard), Aim | Apache-2.0 / MIT | active | yes, they poll their log files | right for v0.4.0's training curves; an exporter from the record would also show peak residual against iteration and residual thumbnails with no UI work. Not built for per-antenna or waterfall panels |
| CARTA 6.0 | GPL-3 | 2026-06 | a session can be scripted to open an image | stays the full-resolution image and cube viewer; no Windows build |
| [radiopadre](https://github.com/ratt-ru/radiopadre) | MIT | 1.2.0 of 2023; pushed 2026-02 | no, after the run | browses a run directory over a slow SSH link; a default notebook could be shipped later |
| SKA SDP signal display | not checked | QA Data API 1.6.x | yes: metrics on Kafka topics, served to the browser over WebSockets | built for the receive pipeline inside an SDP deployment; a later exporter if rang ever runs there. Keep event kinds mappable (spectrum, waterfall) |
| [katsdpdisp](https://github.com/ska-sa/katsdpdisp) (MeerKAT signal displays) | BSD-3 | pushed 2026-11-18 | yes, at the telescope (Tornado and WebSockets according to a 2020 SKA assessment; repository not read) | not for offline reduction; prior art for panels |
| Prometheus, OpenTelemetry, Grafana | Apache-2.0 / AGPL | – | yes | host and cluster metrics; an exporter with #3 and #4 (multi-node), not a science view |
| Textual (Python) or ratatui (Rust) | MIT | active | – | the optional full-screen mode of `watch` |
| Makepad | MIT | pushed 2026-11-18 | – | a native and WebAssembly reader of the same record, later; every plot and axis built by hand |
| Dask and Ray dashboards | BSD-3 / Apache-2.0 | – | yes | show tasks and workers, not science; what QuartiCal users see on a distributed scheduler (not checked here) |

Not checked: what Stimela 2 and WSClean show during a run beyond their logs;
QuartiCal's and pfb-imaging's dashboards; forums and mailing lists.

## 5. Where it fits

- **v0.4.0:** no. Its fork is dated 2026-11-23 and it is already moving issues
  to v0.5.0 ([v040-plan.md](v040-plan.md)). The record touches GeMClean and
  the solvers, whose gates are in use this week.
- **v0.5.0 (Scale, and more of MeerKAT):** the record, `watch` and the MCP
  tools as one item (S to M), first after the 0.4.0 tag, because every later
  campaign and the multi-process executor (#3) gain from it: on a cluster
  `state.json` and the spool heartbeats say that a stage runs, not how it is
  going. The browser view as a second item (M) if the spike of section 0
  item 4 is good. v0.5.0 already holds two L items (#5, #15) and
  [v040-plan.md](v040-plan.md) proposes five more issues for it (#44, #45,
  #4, #7, #34); this item depends on none of them and blocks none.
- **The spike** (one day, shared slots; started 2026-11-20 on the owner's
  word; section 7). It can run before v0.5.0 starts; the roadmap lets research
  run ahead.
- **Later (v0.6.0 or its own package):** steering; a Makepad reader; the
  exporters to an SDP or a Grafana.

## 6. Owner decisions (taken 2026-11-20)

1. **Record first, viewers as readers.** Decided: yes.
2. **Browser viewer.** Decided: the one-day spike, Rerun against a page of
   our own; the outcome picks the viewer. Bokeh/Panel and Makepad not chosen
   (Makepad stays a possible later reader).
3. **Placement.** Decided: the record, `rang-core watch` and the MCP tools
   right after the 0.4.0 tag, before the rest of v0.5.0; the browser view in
   v0.5.0; steering later, with its own note.
4. **Default.** Decided: the record ships off and becomes the default once
   both gates of section 2 hold (bit-identical outputs, overhead at most 1 %).
5. **Packaging.** Decided: the browser view is an extra of `rang-core`
   (`[view]`); a separate package only if it brings a dependency `rang-core`
   must not carry.

## 7. The spike: protocol (written 2026-11-20, before any spike code)

One record, two viewers, the same input.

- **Capture.** A scratch branch (not pushed) makes GeMClean append an event
  per major cycle and write a decimated residual, on the path one test run
  takes, on a simulated MeerKAT MS under `D:ang\data`. Outputs hashed with
  the hook on and off and wall time noted (indicative, not the gate of
  section 2). The gain panel is fed from an existing MeerKAT-size calibration
  table converted by a script, labelled replay; no solver is instrumented.
- **Replayer.** A script re-emits the captured record with its original
  timing (or faster), so both viewers see the same input and live attach is
  tested without a long run.
- **Viewers.** Rerun, SDK and viewer pinned to one version from public PyPI in
  the spike's own venv, fed by a bridge that follows the record; and a page
  of our own (standard-library server, server-sent events).
- **Scored for each viewer** (yes, partly, no; with what was seen):
  1. attach to a run in progress; join late with the history; replay after
     the end;
  2. gain amplitude and phase for 64 antennas, readable;
  3. residual image with a slider over major cycles and a stretch control;
  4. peak residual and threshold on a log axis;
  5. works in the browser and (Rerun) as a native Windows viewer;
  6. one remote arrangement: record on the remote end (WSL stands in for
     nash), view on Windows through a forwarded port;
  7. install size, and lines of glue code written.
- **Decision rule.** Rerun is chosen if it scores yes on 1 to 4 and 6; a page
  of our own if Rerun fails any of those and the page passes it; otherwise
  both outcomes are recorded and the owner decides. A blank canvas in an
  embedded browser is not scored against a viewer before it is confirmed in a
  normal browser or the native viewer (the WebGL case of
  [nb-carta.md](nb-carta.md)).

## For the coordinator

- Branch `live-view-scope` (worktree `~/Worktrees/rang/live-view-scope`), one
  note and one index line; no code touched, nothing run, no heavy lock used.
  `tools/check_all.py --quick` not run; not pushed; the worktree remains
  until the branch is merged or dropped.
- To schedule (section 6): the spike as a shared-slot task, any time; an
  issue for the record, `watch` and the MCP tools, first after the 0.4.0 tag;
  an issue on the v0.5.0 milestone for the browser view. No issue opened yet.

## Sources

- Rerun: [operating modes](https://rerun.io/docs/reference/sdk/operating-modes),
  [remote viewing](https://rerun.io/docs/howto/visualization/remote-viewing),
  [releases](https://github.com/rerun-io/rerun/releases),
  [compatibility policy](https://github.com/rerun-io/rerun/blob/main/RELEASES.md).
- SKA: [signal display overview](https://developer.skao.int/projects/ska-sdp-qa-display/en/latest/userguide/overview.html),
  [QA Data API](https://developer.skao.int/projects/ska-sdp-qa-data-api/en/latest/overview.html).
- [casagui on PyPI](https://pypi.org/project/casagui),
  [carta-python quick start](https://carta-python.readthedocs.io/en/latest/quickstart.html),
  [radiopadre](https://github.com/ratt-ru/radiopadre),
  [trackio](https://huggingface.co/docs/trackio/en/index),
  [Dask dashboard](https://docs.dask.org/en/latest/dashboard.html).
- Licences and last pushes: the GitHub API, 2026-11-20.
