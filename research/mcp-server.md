# MCP server over rang-core (issue #27, piece 1)

Piece 1 of gijzelaerr/rang-core issue 27, in the v0.3.0 milestone of
`research/roadmap.md`. Branch `claude/mcp-server-e5f325` from `main` `30d9412`.

**Status: proposed (2026-11-13).** This note is committed before any server
code. It is a scope note, not a proposal note in the sense of
`docs/agents/propose-and-measure.md`: there is **no scientific or performance
claim**, so no oracle, tolerance or decision rule applies. Every tool calls an
existing, already gated path (`listobs`: V8a; `config check` and `run`: W2;
flag backups: W1; `gemclean`: G2-G9) and adds no numerics of its own. Nothing
here changes what E2, E3 or E5 measure.

## 1. What it is

A [Model Context Protocol](https://modelcontextprotocol.io) server, so that an
agent (Claude, Codex or any MCP client) can inspect a Measurement Set, a
configuration, a run directory and its images through typed tools instead of
parsing command-line output. No radio-astronomy MCP server was found
(digest 2026-11-11, section 8).

- Command: `rang-core mcp [--allow-write] [--root DIR ...]`, stdio transport
  only (no network listener).
- Packaging: the optional extra `rang-core[mcp]` = `mcp>=2.3,<3` from public
  PyPI (the official Python SDK; its 2.x API is `MCPServer`). `rang` imports
  `mcp` only inside `rang.mcp_server`, so the package and CLI work without the
  extra; `rang-core mcp` without it says how to install it.
- Layout: `rang.mcp_tools` holds the tool functions with no `mcp` import
  (plain arguments in, JSON-safe dicts out, testable without the extra);
  `rang.mcp_server` registers them on an `MCPServer`.

## 2. Read-only tools (always registered)

| Tool | Calls | Returns |
| --- | --- | --- |
| `listobs` | `rang.listobs.summary` (V8a) | the record CASA's `listobs` returns, plus the text |
| `config_check` | the function behind `rang-core config check` (factored out of `core_cli`, CLI output unchanged) | valid or not, the stages, every error, MS warnings |
| `config_defaults` | `core_config.defaults_yaml` | the default configuration with comments |
| `receipts` | `<run-dir>/receipts/*.rang-receipt.json`, or one receipt file | a list (command, stage, exit code, times, wall) or one receipt |
| `run_status` | `<run-dir>/state.json` read directly, the MS's flag versions, MCP-launched jobs | per stage: status, times, flag backup, error; jobs: alive or exit code |
| `job_log` | the log of a job a write tool started | the last lines (at most 64 kB) |
| `fits_header` | `astropy.io.fits` (a required dependency) | the header cards of one HDU, capped at 2,000 cards |
| `fits_stats` | NumPy on the finite pixels of one HDU, optionally one plane | shape, min, max, mean, std, RMS, median, NaN count, peak position (pixel and world when the WCS reads) |

Read-only means no file is created or changed: `run_status` reads
`state.json` without `RunDir.locked()` (which creates the directory and a
lock file); MSs are opened through rang's read-only reader.

## 3. Write tools (registered only with `--allow-write`)

| Tool | Runs |
| --- | --- |
| `run` | `rang-core run CONFIG MS [--run-dir] [--force STAGE]` (W2) |
| `gemclean` | `gemclean` with an allowlist of options (section 4) |

Confirmation, three layers:

1. **Operator.** Without `--allow-write` the write tools do not exist on the
   server. No `RANG_*` variable turns them on.
2. **Client.** The tools carry the MCP annotations `destructiveHint: true`,
   `readOnlyHint: false`; the read tools `readOnlyHint: true`. Clients that
   ask a human before a destructive call do so.
3. **Two-step call.** A call without `confirm` changes nothing: it runs the
   preflight (`config check` against the MS for `run`; argument checks for
   `gemclean`) and returns the plan (what is written: MS columns, flag
   versions, run directory, image prefix) and a token. The token is a
   SHA-256 over the tool name, the arguments, the configuration file's bytes
   and the MS's `table.dat` size and modification time, and it is single-use
   and expires after 15 minutes. Only a second call with that token runs. A
   changed configuration or MS between the two calls invalidates it. A
   `confirm=true` boolean would be something a model can pass by itself; a
   token forces the plan to be produced, and shown, first.

Write tools run as subprocesses (`python -m rang.core_cli run ...`,
`python -m rang.gemclean ...`), stdin closed, stdout and stderr to a log file:
stdout is the MCP channel, `gemclean` writes to file descriptor 1 from Rust,
resets SIGINT and can exit 101, and the CLI's receipts, thread pinning and
flag backups stay exactly as they are. A real run outlasts any client's tool
timeout, so the call returns at once (or after `wait_seconds`, at most 600)
with the job id, the log path and the run directory; `run_status` reports the
job, and the log is read with `job_log`. Jobs are kept in
`<run-dir>/mcp/jobs/<id>.json` (`run`) or `<prefix>.mcp-job.json`
(`gemclean`); the server keeps no state the files do not.

## 4. The W1 rule: no write to an MS without a flag-version backup

- `run`: the pipeline already saves `rang_original` before the first write
  and `rang_<stage>_<time>` before each stage writes FLAG (W1, W2). The
  MODEL_DATA writes of `image` and `selfcal` save none (E5-43). The MCP `run`
  tool therefore saves `rang_original` (`core_writeback.backup_flags`, which
  does nothing when it exists) before it starts the subprocess, so every MS
  the server writes has a backup, whatever the stages.
- `gemclean`: options are an allowlist; any other option is refused. Of the
  allowed ones, `-predict`, `-update-model-required` and `-model-column`
  write into the MS (MODEL_DATA, G6). With any of them, the tool saves
  `rang_original` if missing and then `rang_mcp_gemclean_<UTC time>` before
  the subprocess starts, and names both in the plan. The simulator options
  that create a new MS are not on the allowlist.
- `--root DIR` (repeatable): when given, every path argument of every tool
  must resolve inside one of the roots.

## 5. Tests

- `tests/test_mcp_server.py`: the tool functions on a synthetic MS (W2's
  `make_ms`): `listobs`, `config_check` valid and refused, `run_status` on an
  empty and a finished run directory (and that it creates nothing), receipts,
  FITS header and statistics on a written FITS file with NaNs, the token
  (missing, wrong, reused, invalidated by a changed config), the `gemclean`
  allowlist, and that a confirmed `run` leaves `rang_original` in
  `<ms>.flagversions`.
- Through the SDK (skipped without the extra): the in-process `Client` lists
  exactly the read tools without `--allow-write` and both write tools with
  it; and one real stdio subprocess (`rang-core mcp`) answers `listobs` and
  `config_check`, which is the only test that catches stray stdout.
- On the public fixture (`RANG_FIXTURE`, skipped when absent, as V8a's
  tests): `listobs` through the server equals `rang.listobs.summary`.
- CI: the `mcp` extra joins the extras of `tests.yml` and of
  `tools/check_all.py`, so the SDK tests run there and do not skip silently.

## 6. Not in this piece

HTTP or SSE transport; MCP resources and prompts; tools for `flag`,
`calibrate`, `apply` or `selfcal` on their own (`run` with `run.stages`
covers them); restoring flag versions through MCP; the agent benchmark
(piece 2 of issue 27, v0.6.0).
