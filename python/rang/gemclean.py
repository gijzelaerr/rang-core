# SPDX-License-Identifier: GPL-3.0-or-later
"""The `gemclean` command of the wheel (task G8, research/g8-wheel.md).

    gemclean [options] <ms>         the console script
    python -m rang.gemclean ...     the same

GeMClean's command line (`rang_core::gemclean::cli`, the code of the source
build's `gemclean` binary) runs inside the extension `rang._core`: the same
options, output, files and exit codes (0, 2 on an error, 101 on a panic).
SIGINT (and SIGBREAK on Windows) take their default action first, so Ctrl-C
ends the run at once, as it ends the binary; Python would otherwise hold the
signal until the imager returns.
"""

import signal
import sys


def main(argv=None):
    """Run gemclean with `argv` (default `sys.argv[1:]`); returns its exit code."""
    for name in ("SIGINT", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), signal.SIG_DFL)
    from rang import _core

    args = sys.argv[1:] if argv is None else [str(a) for a in argv]
    sys.stdout.flush()
    sys.stderr.flush()
    return _core.gemclean_main(args)


if __name__ == "__main__":
    sys.exit(main())
