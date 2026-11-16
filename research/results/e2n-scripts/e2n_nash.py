"""E2's oracle steps on nash (research/e2n-native.md amendment 2): the same
pinned container images, run by apptainer instead of docker-in-WSL.

    python e2n_nash.py MODULE ARGS...      e.g. e2n_nash.py e2_post wsclean0 MS R

Imports e2_post (and, through it, every E2 step that calls `e2_post.docker`)
and replaces `docker` with `apptainer exec` of the image's SIF under
~/rang-data/oracle-images/, with the same bind mounts (host path -> the
container path the scripts and their JSON specs name), a private /tmp and
HOME=/tmp, OMP_NUM_THREADS as asked, and the owner's rule for nash:
`nice -n 19 ionice -c3`. Then runs MODULE's command line as its own
`__main__` would. Nothing else in the steps changes.
"""

import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
E2 = HERE.parent / "e2-acceptance-scripts"
sys.path[:0] = [str(HERE), str(E2)]

import e2_post as P

SIF = Path(os.environ.get("E2N_SIF_DIR", Path.home() / "rang-data" / "oracle-images"))


def sif(image):
    return SIF / (image.replace(":", "_") + ".sif")


def apptainer(r, image, mounts, script, label, threads=8):
    binds = []
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
    path = next(
        p / f"{module}.py" for p in (HERE, E2) if (p / f"{module}.py").is_file()
    )
    sys.argv = [str(path), *args]
    runpy.run_path(str(path), run_name="__main__")
