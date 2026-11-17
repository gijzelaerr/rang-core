"""An agent runs the whole chain through `rang-core mcp` (roadmap v0.3.0, "Done
when": an agent can run the chain through MCP; issue 27, piece 1;
research/v030-readiness.md).

A scripted client speaks newline-delimited JSON-RPC 2.0 to a real
`rang-core mcp --allow-write --root DIR` over its stdin and stdout, with no
network and without the SDK's client, in the order of
docs/agents/use-the-mcp-server.md: initialize, tools/list, listobs,
config_check, run without `confirm` (the plan), run with the plan's token,
then run_status until every stage is done. The script plays the user's "yes"
to the plan. Data: a copy of the public fixture's scan 9 (J1939-6342, 4
antennas, 4,096 channels; skipped without `RANG_FIXTURE` or the `mcp` extra).
Stages: flag, calibrate, apply, image and selfcal, every one of run.stages.

`RANG_MCP_CHAIN_RECEIPT=PATH` also writes the transcript there (local paths
replaced), as in research/results/v030-mcp/.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import zipfile
from pathlib import Path

import pytest
from rang import core_ms_write

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "python"
STRATEGY = ROOT / "examples" / "ms-to-image" / "strategy.yaml"
STAGES = ["flag", "calibrate", "apply", "image", "selfcal"]
PROTOCOL = "2025-06-18"
DEADLINE_S = 600

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

# Calibrator-only scan, so the fcal field is also the target. refant m002:
# the example strategy flags baselines m000-m001 and m000-m003 entirely on
# this scan, so m000 cannot be the reference; 4 antennas, so minblperant 2.
CONFIG = """\
    version: 1
    fields:
      fcal: [{field}]
      target: [{field}]
    flag:
      strategy: strategy.yaml
    calibrate:
      model: {{source: setjy, standard: Stevens-Reynolds 2016}}
      refant: m002
      minblperant: 2
      primary:
        field: [fcal]
        terms:
          - {{type: K, name: K, solint: inf}}
          - {{type: G, name: G, solint: inf, calmode: ap, preapply: [K], interp: [linear]}}
          - {{type: B, name: B, solint: inf, combine: scan, preapply: [K, G],
             interp: [linear, linear]}}
    apply:
      targets:
        - field: [fcal]
          tables: [K, G, B]
          interp: [linear, linear, linear]
    image:
      fields: [target]
      size: 128
      scale: 30asec
      niter: 200
      auto_threshold: 3.0
      threads: 2
    selfcal:
      rounds: 2
      refant: m002
    run:
      stages: [flag, calibrate, apply, image, selfcal]
    """


@pytest.fixture(scope="module")
def fixture_scan(tmp_path_factory):
    from rang.notebook import data as fixture_data

    source = fixture_data.find_fixture()
    if source is None:
        pytest.skip("public fixture not present (RANG_FIXTURE)")
    if source.is_dir():
        return source
    if fixture_data._sha256(source) != fixture_data.FIXTURE_SHA256:
        pytest.fail(f"{source} is not the pinned public fixture")
    dest = tmp_path_factory.mktemp("fixture")
    with zipfile.ZipFile(source) as zipped:
        for info in fixture_data._safe_members(zipped, fixture_data.FIXTURE_SCAN + "/"):
            zipped.extract(info, dest)
    return dest / fixture_data.FIXTURE_SCAN


class Client:
    """JSON-RPC 2.0 over a subprocess's pipes, one message per line (MCP's
    stdio transport). Records every request and response."""

    def __init__(self, argv, env):
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self.next_id = 0
        self.transcript = []
        self.stderr = []
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self):
        for line in self.proc.stderr:
            self.stderr.append(line.decode("utf-8", "replace"))

    def _send(self, message):
        self.proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def notify(self, method, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.transcript.append({"t": round(time.monotonic(), 3), "send": message})
        self._send(message)

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.transcript.append({"t": round(time.monotonic(), 3), "send": message})
        self._send(message)
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise AssertionError(
                    f"server closed stdout; stderr:\n{''.join(self.stderr)}"
                )
            reply = json.loads(line)  # anything but JSON on stdout fails here
            self.transcript.append({"t": round(time.monotonic(), 3), "recv": reply})
            if reply.get("id") == self.next_id:
                assert "error" not in reply, reply
                return reply["result"]
            # A server notification or request (logging, progress): not ours.

    def call(self, name, arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        assert not result.get("isError"), result["content"]
        return result["structuredContent"]

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


def test_run_state_survives_a_polling_reader(tmp_path):
    """The run's state.json, written by `core_pipeline._write_json` while
    run_status reads it (research/v030-review.md R-01): on Windows the replace
    raised PermissionError and the run failed after a finished stage. Found by
    the chain test below; the job-file form was issue 30."""
    from rang import core_pipeline, mcp_tools

    path = tmp_path / "state.json"
    core_pipeline._write_json(path, {"i": -1})
    errors = []

    def writer():
        try:
            for i in range(200):
                core_pipeline._write_json(path, {"i": i})
        except OSError as exc:
            errors.append(exc)

    t = threading.Thread(target=writer)
    t.start()
    while t.is_alive():
        assert mcp_tools._read_json(path)["i"] >= -1
    t.join()
    assert not errors
    assert mcp_tools._read_json(path) == {"i": 199}


def _trim(value):
    """Long lists of numbers or strings (4,096 channel frequencies) cut to
    their first four items; lists of records (the transcript) kept whole."""
    if isinstance(value, list):
        if len(value) > 16 and not any(isinstance(v, (list, dict)) for v in value):
            return [_trim(v) for v in value[:4]] + [f"... {len(value)} items"]
        return [_trim(v) for v in value]
    if isinstance(value, dict):
        out = {k: _trim(v) for k, v in value.items()}
        if "structuredContent" in out and "content" in out:
            out["content"] = "(structuredContent as text; left out here)"
        return out
    return value


def _scrub(value, replacements):
    text = json.dumps(_trim(value))
    for old, new in replacements:
        forms = {str(old), Path(old).as_posix()}
        for form in sorted(forms, key=len, reverse=True):
            for escaped in (json.dumps(form)[1:-1], form):
                text = text.replace(escaped, new)
    return json.loads(text)


def test_agent_runs_the_chain_over_stdio(fixture_scan, tmp_path):
    pytest.importorskip("mcp", reason="the mcp extra is not installed")
    from rang import __version__, core_ms

    work = tmp_path / "work"
    work.mkdir()
    ms = work / "scan9.ms"
    shutil.copytree(fixture_scan, ms)
    shutil.copyfile(STRATEGY, work / "strategy.yaml")
    with core_ms.open_table(ms / "FIELD") as t:
        field = t.getcol("NAME")[0]
    config = work / "chain.yaml"
    config.write_text(textwrap.dedent(CONFIG.format(field=field)), encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PACKAGE), *filter(None, [env.get("PYTHONPATH")])]
    )
    argv = [sys.executable, "-m", "rang.core_cli", "mcp", "--allow-write"]
    argv += ["--root", str(work)]
    started = time.monotonic()
    client = Client(argv, env)
    try:
        init = client.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "rang-test-script", "version": "1"},
            },
        )
        assert init["serverInfo"]["name"] == "rang-core"
        client.notify("notifications/initialized")
        names = {t["name"] for t in client.request("tools/list")["tools"]}
        assert {"listobs", "config_check", "run", "run_status"} <= names

        # 1. Look before writing anything.
        obs = client.call("listobs", {"ms": str(ms)})
        assert obs["record"]["nfields"] == 1
        assert obs["record"]["field_0"]["name"] == field
        before = client.call("run_status", {"ms": str(ms)})
        assert before["exists"] is False and before["flag_versions"] == []
        check = client.call(
            "config_check", {"config": str(config), "ms": str(ms), "all_stages": True}
        )
        assert check["valid"], check["report"]
        assert check["stages"] == STAGES

        # 2. The plan writes nothing; the script then plays the user's yes.
        plan = client.call("run", {"config": str(config), "ms": str(ms)})
        assert plan["plan"]["stages"] == STAGES and plan["plan"]["writes_ms"]
        assert plan["plan"]["flag_versions_saved_first"][0] == "rang_original"
        assert client.call("run_status", {"ms": str(ms)})["exists"] is False
        job = client.call(
            "run", {"config": str(config), "ms": str(ms), "confirm": plan["confirm"]}
        )
        assert job["job"]["flag_versions_saved"] == ["rang_original"]

        # 3. Follow the job.
        polls = 0
        while True:
            status = client.call("run_status", {"ms": str(ms)})
            polls += 1
            states = [j["state"] for j in status["jobs"]]
            if states and states[-1] in ("done", "failed", "lost"):
                break
            if time.monotonic() - started > DEADLINE_S:
                break
            time.sleep(0.5)
        log = client.call("job_log", {"job": job["job_file"]})
        assert states == ["done"], log["log"]
        assert {s: status["stages"][s]["status"] for s in STAGES} == dict.fromkeys(
            STAGES, "done"
        ), log["log"]
        names = [v["name"] for v in status["flag_versions"]]
        assert names[0] == "rang_original"
        assert status["receipts"] >= 1
        image = Path(status["run_dir"]) / "image"
        fits = sorted(image.rglob("*-image.fits"))
        assert fits, sorted(p.name for p in image.rglob("*"))
        stats = client.call("fits_stats", {"path": str(fits[0])})
        assert stats["finite"] == 128 * 128 and stats["peak"] > 0
        receipts = client.call("receipts", {"path": status["run_dir"]})
        assert receipts["count"] >= 1
        assert all(r["exit"] == 0 for r in receipts["receipts"])
    finally:
        client.close()
    wall = time.monotonic() - started

    out = os.environ.get("RANG_MCP_CHAIN_RECEIPT")
    if out:
        commit = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        replace = [
            (work, "<work>"),
            (Path(fixture_scan), "<fixture>"),
            (tmp_path.parent.parent, "<tmp>"),
            (Path(sys.executable).parent, "<python>"),
            (ROOT, "<checkout>"),
            (Path.home(), "~"),
        ]
        record = {
            "schema": "rang.v030-mcp-chain",
            "test": "tests/test_mcp_chain.py::test_agent_runs_the_chain_over_stdio",
            "commit": commit,
            "rang_core": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "fixture_scan": "outer_scans/1672727931_sdp_l0_scan_9.ms (public fixture)",
            "confirmation": "played by the test script, standing in for the user",
            "wall_seconds": round(wall, 2),
            "polls": polls,
            "stages": {s: status["stages"][s]["status"] for s in STAGES},
            "flag_versions": names,
            "image": {k: stats.get(k) for k in ("peak", "rms", "finite", "nan")},
            "config": textwrap.dedent(CONFIG.format(field=field)),
            "transcript": _scrub(client.transcript, replace),
        }
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
