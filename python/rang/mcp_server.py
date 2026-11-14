# SPDX-License-Identifier: GPL-3.0-or-later
"""`rang-core mcp`: an MCP server over rang-core, stdio only
(research/mcp-server.md; issue 27, piece 1).

    pip install 'rang-core[mcp]'
    rang-core mcp                      # read-only tools
    rang-core mcp --allow-write        # also run and gemclean, each confirmed
    rang-core mcp --root /data/ms      # every path argument inside /data/ms

The tools are `rang.mcp_tools.Tools`; this module only registers them on the
SDK's `MCPServer` (mcp 2.x) and is the one module that imports `mcp`.
Nothing here prints to stdout, which is the protocol channel.
"""

import argparse
import functools
import sys
from typing import Any

from .mcp_tools import STAGES, ToolError, Tools

INSTALL = "the MCP server needs the extra: pip install 'rang-core[mcp]'"

INSTRUCTIONS = """\
rang-core: MeerKAT flagging, calibration and imaging (a research demonstrator,
not an operational calibrator). Read tools change nothing. Write tools, when the
server allows them, take two calls: the first returns a plan and a `confirm`
token and writes nothing; show the plan to the user, and only after they agree
call again with confirm=<token>. Every MS write is preceded by a flag-version
backup (rang_original). Long runs return a job at once: poll run_status and
job_log."""


def _sdk():
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError as SdkToolError
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise SystemExit(f"rang-core mcp: {INSTALL} ({exc})") from None
    return MCPServer, SdkToolError, ToolAnnotations


def build(roots=(), allow_write=False, tools=None):
    """The `MCPServer` with rang's tools (the write tools only with
    `allow_write`)."""
    from . import __version__

    MCPServer, SdkToolError, ToolAnnotations = _sdk()
    tools = tools or Tools(roots=roots, allow_write=allow_write)
    server = MCPServer(name="rang-core", version=__version__, instructions=INSTRUCTIONS)
    read = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, openWorldHint=False
    )
    write = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    )

    def register(fn, annotations):
        @functools.wraps(fn)
        def call(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (ToolError, OSError, ValueError, KeyError) as exc:
                raise SdkToolError(str(exc)) from exc

        server.add_tool(call, name=fn.__name__, annotations=annotations)

    def listobs(ms: str, text: bool = False) -> dict[str, Any]:
        """Summarise a Measurement Set as CASA's listobs does (rang.listobs,
        checked against CASA 6.7.6 with 0 differences): observation, scans,
        fields, spectral windows, sources, antennas. text=True adds the
        listobs-style report."""
        return tools.listobs(ms, text)

    def config_defaults() -> dict[str, Any]:
        """Every rang-core configuration key with its default and comment (YAML)."""
        return tools.config_defaults()

    def config_check(
        config: str,
        ms: str | None = None,
        stages: list[str] | None = None,
        all_stages: bool = False,
    ) -> dict[str, Any]:
        """Validate a rang-core configuration (rang-core config check): every
        schema error and refusal at once. With ms, also resolve its fields
        against that MS and run the preflight. stages: any of flag, calibrate,
        apply, image, selfcal (default run.stages)."""
        return tools.config_check(config, ms, stages, all_stages)

    def run_status(run_dir: str | None = None, ms: str | None = None) -> dict[str, Any]:
        """The state of a rang-core run directory (default <ms>.rang-run):
        each stage's status, times, flag backup and error; the MS's flag
        versions; the receipts; and the jobs started through this server."""
        return tools.run_status(run_dir, ms)

    def receipts(path: str, full: bool = False) -> dict[str, Any]:
        """The rang receipts of a run directory (command, stage, exit code,
        wall time, commit), or one receipt file in full."""
        return tools.receipts(path, full)

    def job_log(job: str, lines: int = 200) -> dict[str, Any]:
        """The last lines of the log of a job a write tool started (job is the
        job_file it returned) and its state."""
        return tools.job_log(job, lines)

    def fits_header(path: str, hdu: int = 0) -> dict[str, Any]:
        """The header cards of one HDU of a FITS image."""
        return tools.fits_header(path, hdu)

    def fits_stats(path: str, hdu: int = 0, plane: int | None = None) -> dict[str, Any]:
        """Statistics of the finite pixels of a FITS image (or one plane):
        min, max, mean, std, RMS, median, NaN count, the peak and its pixel
        and sky position."""
        return tools.fits_stats(path, hdu, plane)

    for fn in (
        listobs,
        config_defaults,
        config_check,
        run_status,
        receipts,
        job_log,
        fits_header,
        fits_stats,
    ):
        register(fn, read)
    if not tools.allow_write:
        return server

    def run(
        config: str,
        ms: str,
        run_dir: str | None = None,
        force: list[str] | None = None,
        confirm: str | None = None,
        wait_seconds: float = 0,
    ) -> dict[str, Any]:
        """rang-core run CONFIG MS: the stages of run.stages, written into the
        MS. Without confirm, writes nothing and returns the plan and a
        single-use token (15 min); show the plan to the user and, once they
        agree, call again with confirm=<token>. Saves the flag version
        rang_original first. Returns a job (poll run_status, job_log)."""
        return tools.run(config, ms, run_dir, force, confirm, wait_seconds)

    def gemclean(
        ms: str,
        name: str,
        options: list[str] | None = None,
        confirm: str | None = None,
        wait_seconds: float = 0,
    ) -> dict[str, Any]:
        """gemclean [options] -name NAME MS (rang's imager, WSClean's options;
        an allowlist). Writes NAME-*.fits and, unless
        -no-update-model-required, MODEL_DATA into the MS (after saving a flag
        version). Without confirm, writes nothing and returns the plan and a
        token; call again with confirm=<token> once the user agrees."""
        return tools.gemclean(ms, name, options, confirm, wait_seconds)

    register(run, write)
    register(gemclean, write)
    return server


def main(argv=None):
    """`rang-core mcp [--allow-write] [--root DIR ...]`: serve over stdio."""
    parser = argparse.ArgumentParser(
        prog="rang-core mcp",
        description="Serve rang-core's tools to an agent over the Model Context "
        "Protocol (stdio; research/mcp-server.md). Read-only tools by default. "
        f"Needs the extra: pip install 'rang-core[mcp]'. Stages: {', '.join(STAGES)}.",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="also offer run and gemclean, each confirmed by a token from a "
        "first call that writes nothing; every MS write saves a flag version first",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="DIR",
        help="accept only path arguments inside DIR (repeatable; default: any path)",
    )
    args = parser.parse_args(argv)
    server = build(args.root, args.allow_write)
    print(
        f"rang-core mcp: serving on stdio ({'read and write' if args.allow_write else 'read-only'})",
        file=sys.stderr,
        flush=True,
    )
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
