# SPDX-License-Identifier: MIT
"""E2-A's post and row steps on nash for research/e2a-kzero.md.

    python kz_nash.py MODULE ARGS...      e.g. kz_nash.py e2_post wsclean0 MS R

A copy of E2-N's shim (branch e2n at 793c645f,
research/results/e2n-scripts/e2n_nash.py; not on main) with two additions:
`e2_rows_a.WPY` (the Windows frozen-wheel python that `flux-run` calls) is
replaced by this interpreter, the worktree venv pinned in the note; and every
container's thread pools (OpenMP, dask, numba, BLAS, WSClean's `-j 8`) are
capped at KZ_THREADS, the slots its step booked.

It imports e2_post (and, through it, every E2 step that calls
`e2_post.docker`) and replaces `docker` with `apptainer exec` of the image's
SIF under ~/rang-data/oracle-images/, with the same bind mounts (host path ->
the container path the scripts and their JSON specs name), a private /tmp and
HOME=/tmp, OMP_NUM_THREADS as asked, under `nice -n 19 ionice -c3`. Then it
runs MODULE's command line as its own `__main__` would. The frozen E2 scripts
are not edited.
"""

import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

# The pinned wheel's rang, imported before any script below puts the
# checkout's python/ (no extension built there) on sys.path; its submodules
# then resolve through the installed package.
import rang

if "site-packages" not in rang.__file__:
    raise SystemExit(f"rang from {rang.__file__}, not the installed wheel")

HERE = Path(__file__).resolve().parent
E2 = HERE.parent / "e2-acceptance-scripts"
sys.path[:0] = [str(HERE), str(E2)]

import e2_post as P

SIF = Path(os.environ.get("E2N_SIF_DIR", Path.home() / "rang-data" / "oracle-images"))

# rang-wsclean-native is built for the Windows host's CPU (-DPORTABLE=OFF) and
# stops with "Illegal instruction" on nash; the KERN WSClean 3.7 in the CASA
# image runs instead (E2-N's build check; a deviation named in the note).
SUBSTITUTE = {"rang-wsclean-native:3.7": "rang-o-casa:6.7.6.14"}


def sif(image):
    image = SUBSTITUTE.get(image, image)
    return SIF / (image.replace(":", "_") + ".sif")


def apptainer(r, image, mounts, script, label, threads=8):
    # research/e2a-kzero.md: every pool capped at the slots booked (KZ_THREADS);
    # WSClean's fixed `-j 8` (gate 2b's -niter 0 images) follows it.
    cap = int(os.environ.get("KZ_THREADS", threads))
    threads = min(int(threads), cap)
    script = script.replace(" -j 8 ", f" -j {threads} ")
    binds = ["--env", f"DASK_NUM_WORKERS={threads}", "--env", f"NUMBA_NUM_THREADS={threads}",
             "--env", f"OPENBLAS_NUM_THREADS={threads}", "--env", f"MKL_NUM_THREADS={threads}"]  # fmt: skip
    for host, inside in mounts:
        host = str(host)
        if host.startswith("$HOME/"):
            host = str(Path.home() / host[len("$HOME/") :])
            Path(host).mkdir(parents=True, exist_ok=True)
        binds += ["--bind", f"{Path(host).resolve()}:{inside}"]
    cmd = ["nice", "-n", "19", "ionice", "-c3", "apptainer", "exec", "--containall",
           "--env", "HOME=/tmp", "--env", f"OMP_NUM_THREADS={threads}", "--pwd", "/tmp",
           *binds, str(sif(image)), "sh", "-c", script]  # fmt: skip
    P.log(r, f"START {label}: {' '.join(cmd)}")
    t0 = time.perf_counter()
    with open(Path(r) / f"{label}.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(
            cmd, stdout=fh, stderr=subprocess.STDOUT, check=False
        ).returncode
    P.log(r, f"END {label} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


P.docker = apptainer
P.wsl = lambda path: str(Path(path).resolve())  # native paths on Linux


if __name__ == "__main__":
    module, *args = sys.argv[1:]
    if module == "e2_post":  # run_path would re-create e2_post's globals unpatched
        sys.exit(P.main(args))
    if module == "e2_rows_a":  # the same, and flux-run's interpreter
        import e2_rows_a as RA

        RA.WPY = sys.executable
        step, ms, r, *rest = args
        P.log(r, f"rows step {step} {ms} {rest}")
        sys.exit(RA.STEPS[step](ms, r, *rest))
    path = next(
        p / f"{module}.py" for p in (HERE, E2) if (p / f"{module}.py").is_file()
    )
    sys.argv = [str(path), *args]
    runpy.run_path(str(path), run_name="__main__")
