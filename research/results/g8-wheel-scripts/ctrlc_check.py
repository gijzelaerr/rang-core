"""ctrlc_check.py MS OUTDIR CMD...: a real Ctrl-C on Windows (task G8, research/g8-wheel.md section 6).

Run by itself, it starts itself again in a new console; there it starts CMD with the
G8 test's long settings, waits for its first output line, sends CTRL_C_EVENT to every process of
the console (GenerateConsoleCtrlEvent(0, 0); it survives through a handler of its own) and prints CMD's exit status and the seconds from the
event to the exit (0xC000013A is the binary's STATUS_CONTROL_C_EXIT).
"""

import ctypes
import json
import signal
import subprocess
import sys
import time

LONG = [
    "-size", "1024", "1024", "-scale", "1asec", "-weight", "natural",
    "-niter", "100000000", "-gain", "0.01", "-nmiter", "1000", "-abs-threshold", "0",
    "-data-column", "DATA", "-field", "0", "-no-update-model-required", "-j", "2",
]  # fmt: skip


HANDLER = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)(lambda event: 1)


def inner(ms, out, cmd):
    # This process survives the event through a handler of its own; not
    # signal.SIG_IGN, whose "ignore Ctrl-C" flag the child would inherit.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    # Ctrl-C may be disabled for this process tree (a parent started in a new
    # process group); enable it, so the child inherits it enabled.
    ctypes.windll.kernel32.SetConsoleCtrlHandler(None, 0)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(HANDLER, 1)
    p = subprocess.Popen([*cmd, "-name", out + "/c", *LONG, ms], stdout=subprocess.PIPE)
    p.stdout.readline()
    time.sleep(0.5)
    sent = time.perf_counter()
    ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, 0)
    rc = p.wait(timeout=120)
    return {
        "cmd": cmd,
        "rc": rc,
        "rc_hex": hex(rc & 0xFFFFFFFF),
        "seconds": time.perf_counter() - sent,
    }


if __name__ == "__main__":
    if sys.argv[1] == "--inner":
        try:
            res = inner(sys.argv[2], sys.argv[3], sys.argv[5:])
        except BaseException as e:  # noqa: BLE001
            import traceback

            res = {"error": repr(e), "traceback": traceback.format_exc()}
        with open(sys.argv[4], "w") as f:
            json.dump(res, f)
    else:
        ms, out, *cmd = sys.argv[1:]
        result = out + "/ctrlc.json"
        subprocess.run(
            [sys.executable, __file__, "--inner", ms, out, result, *cmd],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            check=False,
        )
        with open(result) as f:
            print(f.read())
