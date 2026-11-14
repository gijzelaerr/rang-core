# The MCP server

`rang-core mcp` serves rang-core's tools to an agent (Claude, Codex or any
[Model Context Protocol](https://modelcontextprotocol.io) client) over stdio.
The agent calls typed tools and gets JSON back instead of parsing the command
line's output. Scope and design: {gh}`research/mcp-server.md`. The server adds
no numerics of its own: every tool calls a path the command line already uses
and that is already gated (`listobs` against CASA, `run` and the flag backups
by W1 and W2, `gemclean` by G2-G9).

## Install and start

```sh
pip install 'rang-core[mcp]'      # the official MCP Python SDK, 2.x, from PyPI
rang-core mcp                     # read-only tools
rang-core mcp --allow-write       # also run and gemclean, each confirmed
rang-core mcp --root /data/ms     # refuse any path argument outside /data/ms
```

A client starts the server itself. For Claude Code, from the directory with the
data:

```sh
claude mcp add rang -- rang-core mcp --root .
```

Any client's configuration takes the same command, for example:

```json
{"mcpServers": {"rang": {"command": "rang-core", "args": ["mcp", "--root", "/data/ms"]}}}
```

The server writes nothing to stdout except the protocol; its own messages go to
stderr. There is no network transport.

## Tools

Read tools change no file. They are always present and carry the MCP
annotation `readOnlyHint`.

| Tool | Arguments | Returns |
| --- | --- | --- |
| `listobs` | `ms`, `text` | CASA `listobs`'s record from rang's reader (0 differences against CASA 6.7.6, {gh}`research/v8a-listobs.md`); `text` adds the report |
| `config_defaults` | | every configuration key with its default, as YAML |
| `config_check` | `config`, `ms`, `stages`, `all_stages` | `rang-core config check`: valid or not, every error and refusal, warnings for data outside the tested scope |
| `run_status` | `run_dir` or `ms` | `state.json` per stage (status, times, flag backup, error), the MS's flag versions, the receipt count, the jobs started through the server |
| `receipts` | `path`, `full` | the receipts of a run directory (command, stage, exit, wall time, commit), or one receipt |
| `job_log` | `job`, `lines` | the end of a job's log and its state |
| `fits_header` | `path`, `hdu` | the header cards (at most 2,000) |
| `fits_stats` | `path`, `hdu`, `plane` | shape, min, max, mean, std, RMS, median, NaN count, the peak, its pixel and sky position |

Write tools exist only with `--allow-write` and carry `destructiveHint`:

| Tool | Arguments | Runs |
| --- | --- | --- |
| `run` | `config`, `ms`, `run_dir`, `force`, `confirm`, `wait_seconds` | `rang-core run CONFIG MS` |
| `gemclean` | `ms`, `name`, `options`, `confirm`, `wait_seconds` | `gemclean OPTIONS -name NAME MS`; options from an allowlist of gemclean's own |

## Confirmation

A write tool called without `confirm` writes nothing. It runs the preflight
(for `run`, `config check` against the MS) and returns the plan: the command,
the stages, whether and what it writes into the MS, the flag versions it will
save first, and a token. The agent shows the plan to the user; once they
agree, it calls the tool again with `confirm=<token>`.

The token is single-use, expires after 15 minutes and is bound to the
arguments, the configuration file's content and the MS's files: an edit to
either between the two calls refuses it. Tokens die with the server process.

## Flag backups

No tool writes an MS without a flag-version backup. Before `run` starts, the
server saves `rang_original` (if the MS has none), and the pipeline saves
`rang_<stage>_<UTC time>` before each stage writes FLAG, as the command does.
`gemclean` writes MODEL_DATA after imaging by default (or with `-predict`);
then the server saves `rang_original` and `rang_mcp_gemclean_<UTC time>`
first. With `-no-update-model-required` gemclean leaves the MS alone and no
version is saved. Visibility columns are not backed up: work on a copy of the
MS unless you mean to change it. Restore flags with
`rang.formats.flagversions.restore` or CASA's `flagmanager` ({doc}`howto/flag`).

## Jobs

A run can take hours, longer than a client waits for one call. A confirmed
write returns at once (or after `wait_seconds`, at most 600) with a job file:
`<run-dir>/mcp/jobs/<id>.json` for `run`, `<name>.mcp-jobs/<id>.json` for
`gemclean`, with the log beside it. The job runs detached from the server, so
it finishes even if the client disconnects. `run_status` lists the run
directory's jobs (`starting`, `running`, `done`, `failed`, or `lost` when the
runner died without an exit code); `job_log` reads the log. The command line's
receipts are written as usual.

## Limits

- stdio only; no HTTP transport, resources or prompts.
- `--root` checks the path arguments; a configuration can still name a
  strategy or mask file outside the roots.
- No tools for `flag`, `calibrate`, `apply` or `selfcal` alone: `run` with
  `run.stages` covers them.
- rang-core is a tested research demonstrator, not an operational calibrator
  ({doc}`limits`).

With an agent: {doc}`agents/use-the-mcp-server`.
