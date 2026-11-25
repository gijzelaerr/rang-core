"""`rang-core spool submit | status | stop` (research/multinode-2.md, section
3): the worker scripts of each scheduler as text; a dry run submits nothing;
a stale stop file is refused; local workers started by the launcher run the
stages identical to one process; and, where a Slurm cluster answers (the CI
runner's single node, the container cluster on nash), workers from a real
`sbatch --array` do the same. The multi-node arms on the container cluster
are `tools/oracles/multinode/run.py`."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from rang import core_launch, core_spool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import test_spool as ts

SPOOL = "/shared/run/spool"
PY = "/shared/venv/bin/python"
LOG = "/shared/run/spool/launch/L"


def test_the_slurm_script():
    text = core_launch.script(
        "slurm", SPOOL, 4, threads=2, mem_gb=6, walltime="02:00:00",
        idle_exit=300, python=PY, logdir=LOG, extra=["--account=b42"],
    )  # fmt: skip
    assert text == (
        "#!/bin/bash\n"
        "#SBATCH --array=0-3\n"
        "#SBATCH --job-name=rang-spool\n"
        "#SBATCH --nodes=1\n"
        "#SBATCH --ntasks=1\n"
        "#SBATCH --cpus-per-task=2\n"
        f"#SBATCH --output={LOG}/%A_%a.out\n"
        "#SBATCH --no-requeue\n"
        "#SBATCH --mem=6G\n"
        "#SBATCH --time=02:00:00\n"
        "#SBATCH --account=b42\n"
        "# rang-core spool submit: 4 spool worker(s) of 2 thread(s)\n"
        "# (research/multinode-2.md). Recovery is the spool's lease, so the\n"
        "# scheduler does not requeue a task.\n"
        "set -e\n"
        "export RAYON_NUM_THREADS=2\n"
        "export OMP_NUM_THREADS=2\n"
        "export OPENBLAS_NUM_THREADS=2\n"
        f"exec {PY} -m rang.core_spool worker {SPOOL} --threads 2 --idle-exit 300\n"
    )


def test_the_pbs_script():
    text = core_launch.script(
        "pbs", SPOOL, 3, threads=4, mem_gb=1.5, walltime="1:00:00",
        python=PY, logdir=LOG, extra=["-q normal", "-P ASTR1234"],
    )  # fmt: skip
    head = text.split("# rang-core")[0]
    assert head == (
        "#!/bin/bash\n"
        "#PBS -J 0-2\n"
        "#PBS -N rang-spool\n"
        "#PBS -l select=1:ncpus=4:mem=1536mb\n"
        "#PBS -j oe\n"
        f"#PBS -o {LOG}/\n"
        "#PBS -l walltime=1:00:00\n"
        "#PBS -q normal\n"
        "#PBS -P ASTR1234\n"
    )
    assert text.endswith("--threads 4 --idle-exit 600\n")


def test_a_one_worker_array_is_a_plain_job():
    # PBS Professional refuses `-J 0-0`; Slurm and Torque need no array either.
    for scheduler, flag in (
        ("slurm", "#SBATCH --array"),
        ("pbs", "#PBS -J"),
        ("torque", "#PBS -t"),
    ):
        text = core_launch.script(scheduler, SPOOL, 1, python=PY, logdir=LOG)
        assert flag not in text, scheduler


def test_the_torque_script():
    text = core_launch.script(
        "torque", SPOOL, 2, threads=8, mem_gb=32, python=PY, logdir=LOG
    )
    head = text.split("# rang-core")[0]
    assert head == (
        "#!/bin/bash\n"
        "#PBS -t 0-1\n"
        "#PBS -N rang-spool\n"
        "#PBS -l nodes=1:ppn=8,mem=32gb\n"
        "#PBS -j oe\n"
        f"#PBS -o {LOG}/\n"
        "#PBS -r n\n"
    )


def test_bad_settings_are_refused(tmp_path):
    spool = tmp_path / "spool"
    bad = [
        {"scheduler": "lsf", "workers": 2},
        {"scheduler": "slurm", "workers": 0},
        {"scheduler": "slurm", "workers": 2, "threads": 0},
        {"scheduler": "slurm", "workers": 2, "walltime": "two hours"},
        {"scheduler": "slurm", "workers": 2, "name": "1bad name"},
        {"scheduler": "slurm", "workers": 2, "mem_gb": -1},
    ]
    for kw in bad:
        with pytest.raises(core_launch.LaunchError):
            core_launch.submit(spool, dry_run=True, **kw)
    with pytest.raises(core_launch.LaunchError, match="absolute"):
        core_launch.submit("relative/spool", "slurm", 2, dry_run=True)


class FakeRunner:
    def __init__(self, stdout="", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "boom")


def test_a_dry_run_writes_the_script_and_submits_nothing(tmp_path):
    spool = tmp_path / "spool"
    runner = FakeRunner("1234\n")
    rec = core_launch.submit(spool, "slurm", 2, threads=2, dry_run=True, runner=runner)
    assert runner.calls == []
    assert rec["dry_run"] and "job_id" not in rec
    script = Path(rec["script"])
    assert script.read_text(encoding="utf-8").startswith(
        "#!/bin/bash\n#SBATCH --array=0-1\n"
    )
    assert rec["command"] == ["sbatch", "--parsable", str(script)]
    saved = json.loads((spool / "launch" / f"{rec['id']}.json").read_text())
    assert saved["build"] == core_spool.build()
    assert saved["python"] == str(Path(sys.executable).absolute())


def test_submit_records_the_job_and_stop_cancels_it(tmp_path, monkeypatch):
    spool = tmp_path / "spool"
    monkeypatch.setattr(core_launch.shutil, "which", lambda name: f"/usr/bin/{name}")
    rec = core_launch.submit(spool, "slurm", 2, runner=FakeRunner("1234;cl\n"))
    assert rec["job_id"] == "1234"
    rec = core_launch.submit(spool, "pbs", 2, runner=FakeRunner("77[].pbs\n"))
    assert rec["job_id"] == "77[].pbs"
    with pytest.raises(core_launch.LaunchError, match="failed"):
        core_launch.submit(spool, "slurm", 2, runner=FakeRunner("", returncode=1))
    runner = FakeRunner()
    ran = core_launch.stop(spool, cancel=True, runner=runner)
    assert ran == [["scancel", "1234"], ["qdel", "-W", "force", "77[].pbs"]]
    assert (spool / "stop").exists()


def test_a_stale_stop_file_is_refused(tmp_path):
    spool = core_spool.prepare(tmp_path / "spool")
    core_spool.stop(spool)
    with pytest.raises(core_launch.LaunchError, match="stop"):
        core_launch.submit(spool, "slurm", 2, dry_run=True)
    core_launch.submit(spool, "slurm", 2, dry_run=True, clear_stop=True)
    assert not (spool / "stop").exists()


def test_the_command_line(tmp_path, capsys):
    from rang import core_cli

    spool = tmp_path / "spool"
    core_cli.main(
        ["spool", "submit", str(spool), "--scheduler", "pbs", "--workers", "2",
         "--dry-run", "--json", "--directive", "-q normal"]
    )  # fmt: skip
    rec = json.loads(capsys.readouterr().out)
    assert "#PBS -q normal\n" in Path(rec["script"]).read_text()
    assert core_cli.main(["spool", "status", str(spool), "--json"]) in (0, None)
    st = json.loads(capsys.readouterr().out)
    assert st["tasks"] == {"queued": 0, "claimed": 0, "done": 0, "failed": 0}
    assert [r["scheduler"] for r in st["launches"]] == ["pbs"]
    with pytest.raises(SystemExit):
        core_cli.main(["spool", "submit", str(spool), "--scheduler", "lsf",
                       "--workers", "2"])  # fmt: skip


def _wait_workers(spool, n, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = core_launch.status(spool)
        if sum(w["live"] for w in st["workers"]) >= n:
            return st
        time.sleep(0.5)
    raise AssertionError(f"fewer than {n} live workers after {timeout} s")


def _stages_against_one_process(tmp_path, launch):
    """flag, calibrate and apply with workers that `launch(spool)` starts,
    against one process (test_spool's stage test, launcher-started)."""
    out = {}
    for arm in ("one", "spool"):
        work = tmp_path / arm
        work.mkdir()
        ms = ts.w2.make_ms(work / "x.ms")
        spool = tmp_path / "spooldir"
        data = ts._spool_data(spool, 2, ", chunk_rows: 7") if arm == "spool" else ""
        config = ts.w3._config(work, ts.w3.CONFIG, data)
        args = (
            work,
            ms,
            config,
            ("flag", "calibrate", "apply"),
            ("FLAG", "MODEL_DATA", "CORRECTED_DATA"),
        )
        if arm == "spool":
            core_spool.prepare(spool)
            launch(spool)
            st = _wait_workers(spool, 2)
            try:
                out[arm] = ts._run(*args)
            finally:
                core_launch.stop(spool, cancel=True)
            out["status"] = st
        else:
            out[arm] = ts._run(*args)
    ts._equal(out["one"], out["spool"])
    chunking = out["spool"]["chunking"]
    assert all(chunking[s]["executor"] == "spool" for s in chunking)
    return out


@ts.needs_writer
def test_local_workers_from_the_launcher_equal_one_process(tmp_path):
    rec = {}

    def launch(spool):
        rec.update(core_launch.submit(spool, "local", 2, idle_exit=120))

    _stages_against_one_process(tmp_path, launch)
    assert len(rec["pids"]) == 2


def _slurm_idle():
    if not (shutil.which("sbatch") and shutil.which("sinfo")):
        return False
    try:
        out = subprocess.run(
            ["sinfo", "-h", "-o", "%T"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(s.strip().startswith(("idle", "mix")) for s in out.splitlines())


@ts.needs_writer
@pytest.mark.skipif(
    os.name != "posix" or not _slurm_idle(), reason="no Slurm cluster answers here"
)
def test_slurm_array_workers_equal_one_process(tmp_path):
    rec = {}

    def launch(spool):
        rec.update(
            core_launch.submit(
                spool,
                "slurm",
                2,
                threads=1,
                mem_gb=1,
                idle_exit=120,
                walltime="00:20:00",
            )
        )

    out = _stages_against_one_process(tmp_path, launch)
    assert rec["job_id"]
    jobs = {
        w["scheduler_job"].get("SLURM_ARRAY_JOB_ID") for w in out["status"]["workers"]
    }
    assert jobs == {rec["job_id"]}
