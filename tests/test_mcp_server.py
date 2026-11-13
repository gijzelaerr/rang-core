"""The MCP server over rang-core (research/mcp-server.md; issue 27, piece 1).

The tool functions (`rang.mcp_tools`) on W2's synthetic MS and on the public
fixture when it is present; the server through the SDK in process and over a
real stdio subprocess (skipped without the `mcp` extra)."""

import asyncio
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms_write, listobs, mcp_tools
from rang.formats import flagversions

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "python"

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


def _w2():
    import test_w2_commands

    return test_w2_commands


@pytest.fixture
def ms(tmp_path):
    return _w2().make_ms(tmp_path / "w2.ms")


@pytest.fixture
def config(tmp_path):
    return _w2().write_config(tmp_path, "run:\n  stages: [flag]\n")


def _sdk():
    return pytest.importorskip("mcp", reason="the mcp extra is not installed")


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PACKAGE), *filter(None, [env.get("PYTHONPATH")])]
    )
    return env


# --- read tools ------------------------------------------------------------------


def test_listobs_equals_the_library(ms):
    out = mcp_tools.Tools().listobs(ms, text=True)
    assert out["record"] == json.loads(json.dumps(listobs.summary(ms)))
    assert "MeasurementSet Name" in out["text"]


def test_listobs_refuses_a_non_ms(tmp_path):
    with pytest.raises(mcp_tools.ToolError, match="not a Measurement Set"):
        mcp_tools.Tools().listobs(tmp_path)


def test_config_check_valid_and_refused(ms, config, tmp_path):
    tools = mcp_tools.Tools()
    good = tools.config_check(config, ms)
    assert good["valid"] and good["stages"] == ["flag"]
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\nimage: {size: 7}\nnope: 1\n", encoding="utf-8")
    out = tools.config_check(bad, stages=["image"])
    assert not out["valid"] and out["errors"] and "nope" in out["report"]
    with pytest.raises(mcp_tools.ToolError, match="unknown stage"):
        tools.config_check(config, stages=["predict"])


def test_config_check_cli_unchanged(ms, config, capsys):
    """The CLI's `config check` goes through the same function, same output."""
    from rang import core_cli

    core_cli.dispatch(["config", "check", str(config), str(ms)])
    assert capsys.readouterr().out == f"{config}: valid for flag\n"


def test_run_status_creates_nothing(ms, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    out = mcp_tools.Tools().run_status(ms=ms)
    assert out["exists"] is False and out["stages"] == {} and out["jobs"] == []
    assert out["flag_versions"] == []
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_status_and_receipts_after_a_cli_run(ms, config):
    from rang import core_cli

    core_cli.dispatch(["run", str(config), str(ms)])
    tools = mcp_tools.Tools()
    status = tools.run_status(ms=ms)
    assert status["stages"]["flag"]["status"] == "done"
    assert "rang_original" in [v["name"] for v in status["flag_versions"]]
    assert status["receipts"] == 1
    listed = tools.receipts(status["run_dir"])
    assert listed["count"] == 1 and listed["receipts"][0]["exit"] == 0
    one = tools.receipts(listed["receipts"][0]["path"])
    assert one["receipt"]["schema"] == "rang.receipt"


def test_fits_header_and_stats(tmp_path):
    from astropy.io import fits

    data = np.zeros((1, 1, 32, 32), np.float32)
    data[0, 0, 10, 20] = 5.0
    data[0, 0, 0, :4] = np.nan
    header = fits.Header()
    for k, v in {
        "CTYPE1": "RA---SIN",
        "CTYPE2": "DEC--SIN",
        "CRVAL1": 201.0,
        "CRVAL2": -43.0,
        "CRPIX1": 17,
        "CRPIX2": 17,
        "CDELT1": -1e-3,
        "CDELT2": 1e-3,
        "BUNIT": "JY/BEAM",
    }.items():
        header[k] = v
    path = tmp_path / "img.fits"
    fits.PrimaryHDU(data, header).writeto(path)
    tools = mcp_tools.Tools()
    head = tools.fits_header(path)
    assert {"key": "BUNIT", "value": "JY/BEAM", "comment": ""} in head["cards"]
    stats = tools.fits_stats(path)
    assert stats["nan"] == 4 and stats["finite"] == 32 * 32 - 4
    assert stats["peak"] == 5.0 and stats["peak_pixel"] == [10, 20]
    assert stats["bunit"] == "JY/BEAM" and stats["peak_world"]["dec_deg"] < -42
    json.dumps(stats, allow_nan=False)
    with pytest.raises(mcp_tools.ToolError, match="plane 3"):
        tools.fits_stats(path, plane=3)


def test_roots_refuse_paths_outside(ms, tmp_path):
    tools = mcp_tools.Tools(roots=[tmp_path / "elsewhere"])
    with pytest.raises(mcp_tools.ToolError, match="outside the server's roots"):
        tools.listobs(ms)


# --- write tools: confirmation and the W1 rule ------------------------------------


def test_write_tools_need_allow_write(ms, config):
    with pytest.raises(mcp_tools.ToolError, match="--allow-write"):
        mcp_tools.Tools().run(config, ms)


def test_token_is_single_use_and_bound(ms, config):
    tools = mcp_tools.Tools(allow_write=True)
    first = tools.run(config, ms)
    assert first["plan"]["stages"] == ["flag"] and first["plan"]["writes_ms"]
    assert first["plan"]["flag_versions_saved_first"][0] == "rang_original"
    # The plan wrote nothing.
    assert flagversions.versions(ms) == []
    assert not (Path(str(ms) + ".rang-run")).exists()
    with pytest.raises(mcp_tools.ToolError, match="unknown or used"):
        tools.run(config, ms, confirm="0" * 32)
    with pytest.raises(mcp_tools.ToolError, match="confirms run, not gemclean"):
        tools.gemclean(ms, ms.parent / "img", confirm=first["confirm"])
    # A changed configuration invalidates the token, which is then used up.
    second = tools.run(config, ms)
    config.write_text(config.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(mcp_tools.ToolError, match="changed since the plan"):
        tools.run(config, ms, confirm=second["confirm"])
    with pytest.raises(mcp_tools.ToolError, match="unknown or used"):
        tools.run(config, ms, confirm=second["confirm"])
    # Another server's token is not this one's.
    other = mcp_tools.Tools(allow_write=True).run(config, ms)["confirm"]
    with pytest.raises(mcp_tools.ToolError, match="unknown or used"):
        tools.run(config, ms, confirm=other)


def test_refused_config_gives_no_token(ms, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\nnope: 1\n", encoding="utf-8")
    out = mcp_tools.Tools(allow_write=True).run(bad, ms)
    assert out["plan"] is None and "confirm" not in out


def test_confirmed_run_backs_up_then_runs(ms, config):
    tools = mcp_tools.Tools(allow_write=True)
    token = tools.run(config, ms)["confirm"]
    out = tools.run(config, ms, confirm=token, wait_seconds=300)
    job = out["job"]
    log = tools.job_log(out["job_file"])["log"]
    assert job["state"] == "done", log
    assert job["flag_versions_saved"] == ["rang_original"]
    status = tools.run_status(ms=ms)
    assert status["stages"]["flag"]["status"] == "done"
    assert [j["state"] for j in status["jobs"]] == ["done"]
    names = [v["name"] for v in status["flag_versions"]]
    assert names[0] == "rang_original" and any(
        n.startswith("rang_flag_") for n in names
    )
    assert status["receipts"] == 1


def test_gemclean_allowlist(ms, tmp_path):
    tools = mcp_tools.Tools(allow_write=True)
    for options, match in (
        (["-gram-operator", "3,0.1"], "not allowed"),
        (["-audit"], "not allowed"),
        (["-name", "x"], "as `name`"),
        (["-size", "64"], "takes 2"),
    ):
        with pytest.raises(mcp_tools.ToolError, match=match):
            tools.gemclean(ms, tmp_path / "img", options)
    plan = tools.gemclean(ms, tmp_path / "img", ["-weight", "briggs", "-0.5"])["plan"]
    assert plan["command"][1:4] == ["-weight", "briggs", "-0.5"]
    assert plan["writes_ms"] and plan["ms_columns"] == ["MODEL_DATA"]
    assert plan["flag_versions_saved_first"][0] == "rang_original"
    plan = tools.gemclean(ms, tmp_path / "img", ["-no-update-model-required"])["plan"]
    assert not plan["writes_ms"] and plan["flag_versions_saved_first"] == []
    assert flagversions.versions(ms) == []


@pytest.mark.parametrize("writes", [False, True])
def test_confirmed_gemclean(ms, tmp_path, writes):
    tools = mcp_tools.Tools(allow_write=True)
    options = ["-size", "64", "64", "-scale", "20asec", "-niter", "10", "-j", "1"]
    if not writes:
        options.append("-no-update-model-required")
    prefix = tmp_path / "img"
    token = tools.gemclean(ms, prefix, options)["confirm"]
    out = tools.gemclean(ms, prefix, options, confirm=token, wait_seconds=300)
    log = tools.job_log(out["job_file"])["log"]
    assert out["job"]["state"] == "done", log
    assert Path(str(prefix) + "-image.fits").is_file()
    names = [n for n, _ in flagversions.versions(ms)]
    if writes:
        assert names[0] == "rang_original" and names[1].startswith("rang_mcp_gemclean_")
        assert out["job"]["flag_versions_saved"] == names
    else:
        assert names == [] and out["job"]["flag_versions_saved"] == []
    stats = tools.fits_stats(Path(str(prefix) + "-image.fits"))
    assert stats["finite"] == 64 * 64


# --- the public fixture -----------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_ms(tmp_path_factory):
    from rang.notebook import data as fixture_data

    source = fixture_data.find_fixture()
    if source is None:
        pytest.skip("fixture MS not present (RANG_FIXTURE)")
    if source.is_dir():
        return source
    if fixture_data._sha256(source) != fixture_data.FIXTURE_SHA256:
        pytest.fail(f"{source} is not the pinned public fixture")
    dest = tmp_path_factory.mktemp("fixture")
    with zipfile.ZipFile(source) as zipped:
        for info in fixture_data._safe_members(zipped, fixture_data.FIXTURE_SCAN + "/"):
            zipped.extract(info, dest)
    return dest / fixture_data.FIXTURE_SCAN


def test_fixture_listobs_and_status(fixture_ms):
    tools = mcp_tools.Tools(roots=[fixture_ms.parent])
    out = tools.listobs(fixture_ms)
    assert out["record"] == json.loads(json.dumps(listobs.summary(fixture_ms)))
    assert out["record"]["nfields"] == 1 and out["record"]["numrecords"] > 0
    status = tools.run_status(ms=fixture_ms)
    assert status["exists"] is False and status["flag_versions"] == []


def test_fixture_through_the_server(fixture_ms):
    _sdk()
    from mcp import Client
    from rang import mcp_server

    async def go():
        async with Client(mcp_server.build([fixture_ms.parent])) as client:
            return await client.call_tool("listobs", {"ms": str(fixture_ms)})

    result = asyncio.run(go())
    assert not result.is_error
    assert result.structured_content["record"] == json.loads(
        json.dumps(listobs.summary(fixture_ms))
    )


# --- through the SDK ----------------------------------------------------------------

READ = {
    "listobs",
    "config_defaults",
    "config_check",
    "run_status",
    "receipts",
    "job_log",
    "fits_header",
    "fits_stats",
}


@pytest.mark.parametrize("allow_write", [False, True])
def test_server_lists_the_tools(allow_write):
    _sdk()
    from mcp import Client
    from rang import mcp_server

    async def go():
        async with Client(mcp_server.build(allow_write=allow_write)) as client:
            return (await client.list_tools()).tools

    tools = {t.name: t for t in asyncio.run(go())}
    assert set(tools) == READ | ({"run", "gemclean"} if allow_write else set())
    for name, tool in tools.items():
        read_only = name in READ
        assert tool.annotations.read_only_hint is read_only, name
        assert tool.annotations.destructive_hint is (not read_only), name


def test_server_reports_refusals_as_tool_errors(tmp_path):
    _sdk()
    from mcp import Client
    from rang import mcp_server

    async def go():
        async with Client(mcp_server.build()) as client:
            return await client.call_tool("listobs", {"ms": str(tmp_path)})

    result = asyncio.run(go())
    assert result.is_error and "not a Measurement Set" in result.content[0].text


def test_stdio_subprocess(ms, config):
    """A real `rang-core mcp` over stdio: the only test that catches output
    on stdout, which would corrupt the protocol."""
    _sdk()
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "rang.core_cli", "mcp", "--root", str(ms.parent)],
        env=_env(),
    )

    async def go():
        async with Client(params) as client:
            a = await client.call_tool("listobs", {"ms": str(ms)})
            b = await client.call_tool(
                "config_check", {"config": str(config), "ms": str(ms)}
            )
            c = await client.call_tool("listobs", {"ms": str(ROOT)})
            return a, b, c

    a, b, c = asyncio.run(go())
    assert not a.is_error and a.structured_content["record"]["numrecords"] == 240
    assert not b.is_error and b.structured_content["valid"] is True
    assert c.is_error and "outside the server's roots" in c.content[0].text


def test_mcp_help_without_the_sdk():
    """`rang-core mcp -h` works without the extra (docs/cli.md is built from it)."""
    done = subprocess.run(
        [sys.executable, "-m", "rang.core_cli", "mcp", "-h"],
        capture_output=True,
        text=True,
        env=_env(),
        check=True,
    )
    assert "--allow-write" in done.stdout
