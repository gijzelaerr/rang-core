"""Robustness probes of casacure and core_ms on damaged copies
(research/casacure-evaluation.md, code review; reported, not gated).

Usage: python examples/eval_casacure_robustness.py <ms> <fresh-out-dir>

Each probe runs in a child process on its own copy of the MS so a crash
(signal) is recorded instead of ending the run: a data file truncated before
open, a data file truncated after open (another process shrinking a mapped
file), a corrupted `table.dat`, and a missing `table.f0`. For each backend
the outcome is `ok` (values returned), `error` (a Python exception, with its
text) or `crash` (the signal number).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

CHILD = r"""
import os, sys
from pathlib import Path
backend, ms, probe = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
data_file = sorted(ms.glob("table.f*i"), key=lambda p: p.stat().st_size)[-1] if list(ms.glob("table.f*i")) else sorted(ms.glob("table.f*_TSM*"), key=lambda p: p.stat().st_size)[-1]
if probe == "truncate-before-open":
    os.truncate(data_file, data_file.stat().st_size // 2)
elif probe == "corrupt-table-dat":
    raw = bytearray((ms / "table.dat").read_bytes())
    for i in range(40, 200):
        raw[i] ^= 0x5A
    (ms / "table.dat").write_bytes(bytes(raw))
elif probe == "missing-manager-file":
    os.remove(sorted(ms.glob("table.f[0-9]"))[0])
if backend == "casacure":
    import casacure.tables as ct
    t = ct.table(str(ms), ack=False)
    get = lambda: t.getcol("DATA")
else:
    sys.path.insert(0, sys.argv[4])
    from rangtoy import core_ms
    t = core_ms.open_table(ms)
    get = lambda: t.getcol("DATA")
if probe == "truncate-after-open":
    os.truncate(data_file, data_file.stat().st_size // 2)
value = get()
print("shape", value.shape, "sum", complex(value.sum()))
"""

PROBES = (
    "truncate-before-open",
    "truncate-after-open",
    "corrupt-table-dat",
    "missing-manager-file",
)


def main():
    ms, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=False)
    python_dir = Path(__file__).resolve().parents[1] / "python"
    result = {}
    for backend in ("casacure", "core_ms"):
        for probe in PROBES:
            copy = out / f"{backend}-{probe}.ms"
            shutil.copytree(ms, copy)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    CHILD,
                    backend,
                    str(copy),
                    probe,
                    str(python_dir),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=300,
            )
            if proc.returncode < 0:
                outcome = {"outcome": "crash", "signal": -proc.returncode}
            elif proc.returncode == 0:
                outcome = {"outcome": "ok", "stdout": proc.stdout.strip()[-300:]}
            else:
                outcome = {
                    "outcome": "error",
                    "stderr": proc.stderr.strip().splitlines()[-1][-300:]
                    if proc.stderr.strip()
                    else "",
                }
            result[f"{backend}:{probe}"] = outcome
            shutil.rmtree(copy)
            print(backend, probe, outcome)
    (out / "robustness.json").write_text(json.dumps(result, indent=1) + "\n")


if __name__ == "__main__":
    main()
