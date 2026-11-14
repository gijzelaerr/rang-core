# SPDX-License-Identifier: GPL-3.0-or-later
"""The tools of `rang-core mcp` without the MCP SDK (research/mcp-server.md).

    from rang.mcp_tools import Tools
    tools = Tools(roots=["/data"], allow_write=False)
    tools.listobs("/data/my.ms")
    tools.config_check("config.yaml", "/data/my.ms")

Every tool takes plain arguments and returns a JSON-safe dict; `rang.mcp_server`
registers them on an MCP server. Read tools create and change no file. The
write tools (`run`, `gemclean`) exist only with `allow_write`, take two calls
(the first returns a plan and a single-use token, the second passes it as
`confirm`), save a flag version of the MS before anything writes to it (the
W1 rule), and run the command line as a detached subprocess whose output
goes to a log, never to this process's stdout (the MCP channel).

`python -m rang.mcp_tools --job JOBFILE` is the job runner the write tools
start: it runs the job's argv, then records its exit code in JOBFILE.
"""

import hashlib
import json
import math
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

JOB_SCHEMA = "rang.mcp-job"
TOKEN_SECONDS = 15 * 60
MAX_WAIT = 600
MAX_CARDS = 2000
MAX_LOG = 64 * 1024
MAX_RECEIPTS = 200
STAGES = ("flag", "calibrate", "apply", "image", "selfcal")

# gemclean options the MCP tool passes on, with the number of values each
# takes (-weight briggs takes two, handled below). Anything else is refused:
# the prototype and audit options, and every option not in gemclean's usage.
GEMCLEAN_OPTIONS = {
    **dict.fromkeys(
        (
            "-minor-to-threshold",
            "-unit-weights",
            "-no-wgridding",
            "-single",
            "-double",
            "-no-plan-reuse",
            "-beam-no-w",
            "-beam-band",
            "-eager-tiles",
            "-no-restore",
            "-memory-report",
            "-update-model-required",
            "-no-update-model-required",
            "-predict",
            "-join-channels",
            "-mf-weighting",
            "-no-mf-weighting",
            "-join-polarizations",
            "-multiscale",
        ),
        0,
    ),
    **dict.fromkeys(
        (
            "-scale",
            "-niter",
            "-gain",
            "-mgain",
            "-mgain-misfit",
            "-stale-rule",
            "-stale-floor",
            "-stop-rule",
            "-stop-rule-kappa",
            "-stop-rule-samples",
            "-stop-rule-bound",
            "-nmiter",
            "-threshold",
            "-abs-threshold",
            "-auto-threshold",
            "-patch",
            "-theta",
            "-drift",
            "-tau-min",
            "-resync-every",
            "-data-column",
            "-field",
            "-scans",
            "-j",
            "-wgridder-accuracy",
            "-bitpix",
            "-tile",
            "-model-column",
            "-channels-out",
            "-fit-spectral-pol",
            "-average-channels",
            "-pol",
            "-multiscale-scales",
            "-multiscale-max-scales",
            "-multiscale-scale-bias",
            "-multiscale-shape",
            "-multiscale-gain",
            "-taper-gaussian",
            "-taper-tukey",
            "-taper-inner-tukey",
            "-taper-edge",
            "-taper-edge-tukey",
            "-minuv-l",
            "-maxuv-l",
            "-minuvw-m",
            "-maxuvw-m",
            "-fits-mask",
            "-auto-mask",
            "-abs-auto-mask",
            "-auto-mask-nmiter",
            "-major-iteration-mode",
        ),
        1,
    ),
    "-size": 2,
    "-channel-range": 2,
    "-weight": 1,
}
GEMCLEAN_PATH_OPTIONS = ("-fits-mask",)


class ToolError(ValueError):
    """A refused tool call: the message is the whole answer to the client."""


def _now():
    return datetime.now(timezone.utc)


def _stamp(t=None):
    return (t or _now()).strftime("%Y%m%dT%H%M%SZ")


def _json_safe(value):
    """NaN and infinities become None; NumPy scalars and arrays plain Python."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        return _json_safe(value.tolist())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, Path):
        return str(value)
    return value


def _pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _fingerprint(path):
    """Size and modification time of every file at the top of a table (or of
    one file): cheap, and it changes when the MS or configuration does."""
    path = Path(path)
    if not path.exists():
        return None
    if path.is_file():
        st = path.stat()
        return [path.name, st.st_size, st.st_mtime_ns]
    return sorted(
        [p.name, p.stat().st_size, p.stat().st_mtime_ns]
        for p in path.iterdir()
        if p.is_file() and p.name != "table.lock"
    )


def job_status(job):
    """A job record with `state`: starting, running, done, failed or lost
    (the runner died without recording an exit code)."""
    job = dict(job)
    if "exit" in job:
        job["state"] = "done" if job["exit"] == 0 else "failed"
    elif _pid_alive(job.get("pid")) or _pid_alive(job.get("runner_pid")):
        job["state"] = "running"
    elif "pid" not in job and _age_seconds(job.get("started_utc")) < 60:
        job["state"] = "starting"
    else:
        job["state"] = "lost"
    return job


def _age_seconds(iso):
    try:
        return (_now() - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return math.inf


class Tools:
    """The MCP tools of one server process.

    `roots`: when given, every path argument must resolve inside one of them.
    `allow_write`: register (and allow) the write tools. Tokens live in this
    object, so a confirmation never outlives the server that issued it."""

    def __init__(self, roots=(), allow_write=False, python=None):
        self.roots = [Path(r).resolve() for r in roots]
        self.allow_write = bool(allow_write)
        self.python = python or sys.executable
        self._secret = secrets.token_bytes(32)
        self._tokens = {}
        self._runners = []

    # -- paths -------------------------------------------------------------

    def _path(self, value, what, must_exist=True):
        if value is None or str(value) == "":
            raise ToolError(f"{what}: no path given")
        path = Path(os.path.expanduser(str(value))).resolve()
        if self.roots and not any(path.is_relative_to(r) for r in self.roots):
            raise ToolError(
                f"{what} {path} is outside the server's roots "
                f"({', '.join(map(str, self.roots))})"
            )
        if must_exist and not path.exists():
            raise ToolError(f"{what} {path} does not exist")
        return path

    def _ms(self, value):
        ms = self._path(value, "MS")
        if not (ms / "table.dat").is_file():
            raise ToolError(f"{ms} is not a Measurement Set (no table.dat)")
        return ms

    # -- read tools --------------------------------------------------------

    def listobs(self, ms, text=False):
        """CASA listobs's record of an MS (rang.listobs, V8a), and its text."""
        from . import listobs

        ms = self._ms(ms)
        try:
            record = listobs.summary(ms)
        except (listobs.ListobsError, OSError) as exc:
            raise ToolError(str(exc)) from None
        out = {"ms": str(ms), "record": _json_safe(record)}
        if text:
            out["text"] = listobs.text(record, ms)
        return out

    def config_defaults(self):
        """Every configuration key with its default and comment, as YAML."""
        from . import core_config

        return {"yaml": core_config.defaults_yaml()}

    def config_check(self, config, ms=None, stages=None, all_stages=False):
        """`rang-core config check CONFIG [MS] [--stage ...] [--all]`."""
        from . import core_config, core_pipeline

        config = self._path(config, "configuration")
        ms = self._ms(ms) if ms else None
        bad = [s for s in stages or () if s not in STAGES]
        if bad:
            raise ToolError(f"unknown stage {bad[0]!r}; stages are {', '.join(STAGES)}")
        try:
            resolved, checked, warnings = core_pipeline.check_config(
                config, ms, stages, all_stages=all_stages
            )
        except core_config.ConfigError as exc:
            return {
                "valid": False,
                "config": str(config),
                "ms": str(ms) if ms else None,
                "errors": [{"key": k, "text": t} for k, t in exc.errors],
                "refusals": [str(r) for r in exc.refusals],
                "report": exc.report(),
            }
        except (core_pipeline.Refused, OSError) as exc:
            return {
                "valid": False,
                "config": str(config),
                "ms": str(ms) if ms else None,
                "errors": [],
                "refusals": [str(exc)],
                "report": str(exc),
            }
        return {
            "valid": True,
            "config": str(config),
            "ms": str(ms) if ms else None,
            "stages": checked,
            "warnings": warnings,
            "run_stages": list(resolved["run"]["stages"]),
        }

    def _run_dir(self, run_dir=None, ms=None):
        from . import core_pipeline

        if run_dir:
            return self._path(run_dir, "run directory", must_exist=False)
        if ms:
            return self._path(
                core_pipeline.default_run_dir(self._ms(ms)),
                "run directory",
                must_exist=False,
            )
        raise ToolError("give run_dir or ms")

    def run_status(self, run_dir=None, ms=None):
        """A run directory's state.json, the MS's flag versions and the jobs
        this server (or an earlier one) started there. Creates nothing."""
        from .formats import flagversions

        path = self._run_dir(run_dir, ms)
        out = {"run_dir": str(path), "exists": path.is_dir(), "stages": {}}
        state_path = path / "state.json"
        if state_path.is_file():
            state = _read_json(state_path)
            out["ms"] = state.get("ms")
            out["created"] = state.get("created")
            out["updated"] = state.get("updated")
            out["stages"] = _json_safe(state.get("stages", {}))
        ms_path = Path(out.get("ms") or ms) if (out.get("ms") or ms) else None
        if ms_path is not None:
            out["flag_versions"] = [
                {"name": n, "comment": c} for n, c in flagversions.versions(ms_path)
            ]
        receipts = path / "receipts"
        out["receipts"] = (
            len(list(receipts.glob("*.rang-receipt.json"))) if receipts.is_dir() else 0
        )
        jobs = path / "mcp" / "jobs"
        out["jobs"] = (
            [job_status(_read_json(p)) for p in sorted(jobs.glob("*.json"))]
            if jobs.is_dir()
            else []
        )
        return out

    def receipts(self, path, full=False):
        """The receipts of a run directory (newest last), or one receipt file
        in full."""
        path = self._path(path, "receipt path")
        if path.is_file():
            return {"path": str(path), "receipt": _read_json(path)}
        folder = path / "receipts" if (path / "receipts").is_dir() else path
        files = sorted(folder.glob("*.rang-receipt.json"))
        out = []
        for p in files[-MAX_RECEIPTS:]:
            try:
                r = _read_json(p)
            except (OSError, ValueError) as exc:
                out.append({"path": str(p), "error": str(exc)})
                continue
            if full:
                out.append({"path": str(p), "receipt": r})
                continue
            out.append(
                {
                    "path": str(p),
                    "command": r.get("command"),
                    "stage": r.get("stage"),
                    "started_utc": r.get("started_utc"),
                    "exit": r.get("exit"),
                    "wall_seconds": (r.get("timings") or {}).get("wall_seconds"),
                    "commit": r.get("commit"),
                    "outputs": len(r.get("outputs") or ()),
                }
            )
        return {"folder": str(folder), "count": len(files), "receipts": out}

    def job_log(self, job, lines=200):
        """The last `lines` lines (at most 64 kB) of a job's log."""
        record = self._job(job)
        log = Path(record["log"])
        if not log.is_file():
            return {"job": job_status(record), "log": ""}
        with log.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - MAX_LOG))
            text = stream.read().decode("utf-8", "replace")
        tail = text.splitlines()[-max(1, int(lines)) :]
        return {"job": job_status(record), "log": "\n".join(tail), "bytes": size}

    def _job(self, job):
        path = self._path(job, "job file")
        if path.suffix != ".json":
            raise ToolError(f"{path} is not a job file")
        record = _read_json(path)
        if record.get("schema") != JOB_SCHEMA:
            raise ToolError(f"{path} is not a {JOB_SCHEMA} file")
        return record

    def fits_header(self, path, hdu=0):
        """The header cards of one HDU of a FITS file."""
        from astropy.io import fits

        path = self._path(path, "FITS file")
        with fits.open(path, memmap=True, lazy_load_hdus=True) as hdul:
            header = hdul[int(hdu)].header
            cards = [
                {"key": c.keyword, "value": _json_safe(c.value), "comment": c.comment}
                for c in header.cards[:MAX_CARDS]
            ]
            return {
                "path": str(path),
                "hdu": int(hdu),
                "hdus": len(hdul),
                "cards": cards,
                "truncated": len(header.cards) > MAX_CARDS,
            }

    def fits_stats(self, path, hdu=0, plane=None):
        """Statistics of the finite pixels of one HDU (or one plane of it:
        the index into the axes before the last two, flattened)."""
        import numpy as np
        from astropy.io import fits

        path = self._path(path, "FITS file")
        with fits.open(path, memmap=True) as hdul:
            item = hdul[int(hdu)]
            if item.data is None:
                raise ToolError(f"HDU {hdu} of {path} has no data")
            data = np.asarray(item.data)
            shape = list(data.shape)
            if plane is not None:
                planes = data.reshape((-1,) + data.shape[-2:])
                if not 0 <= int(plane) < planes.shape[0]:
                    raise ToolError(f"plane {plane}: the HDU has {planes.shape[0]}")
                data = planes[int(plane)]
            elif data.ndim > 2 and int(np.prod(data.shape[:-2])) == 1:
                data = data.reshape(data.shape[-2:])
            finite = np.isfinite(data)
            values = data[finite].astype(np.float64)
            out = {
                "path": str(path),
                "hdu": int(hdu),
                "shape": shape,
                "plane": plane,
                "bunit": item.header.get("BUNIT"),
                "pixels": int(data.size),
                "finite": int(values.size),
                "nan": int(np.isnan(data).sum()),
            }
            if values.size:
                at = np.unravel_index(
                    int(np.argmax(np.where(finite, np.abs(data), -np.inf))), data.shape
                )
                out.update(
                    min=float(values.min()),
                    max=float(values.max()),
                    mean=float(values.mean()),
                    std=float(values.std()),
                    rms=float(np.sqrt(np.mean(values**2))),
                    median=float(np.median(values)),
                    peak=float(data[at]),
                    peak_pixel=[int(i) for i in at],
                )
                if data.ndim == 2:
                    out["peak_world"] = self._world(item.header, at)
            return _json_safe(out)

    @staticmethod
    def _world(header, at):
        try:
            from astropy.wcs import WCS

            wcs = WCS(header).celestial
            ra, dec = wcs.wcs_pix2world([[at[1], at[0]]], 0)[0]
            return {"ra_deg": float(ra), "dec_deg": float(dec)}
        except Exception:  # noqa: BLE001 (a header without a celestial WCS)
            return None

    # -- confirmation --------------------------------------------------------

    def _issue(self, tool, payload):
        digest = hashlib.sha256(
            self._secret + json.dumps([tool, payload], sort_keys=True).encode()
        ).hexdigest()
        token = digest[:32]
        self._tokens[token] = (tool, digest, time.monotonic() + TOKEN_SECONDS)
        return token

    def _redeem(self, tool, payload, token):
        entry = self._tokens.get(token)
        if entry is None:
            raise ToolError(
                "unknown or used confirmation token: call again without confirm "
                "for a new plan"
            )
        name, digest, expires = entry
        if name != tool:
            raise ToolError(f"this token confirms {name}, not {tool}")
        if time.monotonic() > expires:
            del self._tokens[token]
            raise ToolError("the confirmation token expired; ask for a new plan")
        now = hashlib.sha256(
            self._secret + json.dumps([tool, payload], sort_keys=True).encode()
        ).hexdigest()
        del self._tokens[token]
        if now != digest:
            raise ToolError(
                "the arguments, configuration or MS changed since the plan; "
                "call again without confirm for a new plan"
            )

    def _require_write(self):
        if not self.allow_write:
            raise ToolError("write tools are off: start the server with --allow-write")

    # -- write tools -------------------------------------------------------

    def run(self, config, ms, run_dir=None, force=(), confirm=None, wait_seconds=0):
        """`rang-core run CONFIG MS`, in two calls: a plan and a token, then
        the run (a detached job) with that token."""
        from . import core_pipeline
        from .formats import flagversions

        self._require_write()
        config = self._path(config, "configuration")
        ms = self._ms(ms)
        rdir = self._run_dir(run_dir, ms)
        force = list(force or ())
        bad = [s for s in force if s not in (*STAGES, "all")]
        if bad:
            raise ToolError(f"--force {bad[0]}: not a stage")
        payload = {
            "config": str(config),
            "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
            "ms": str(ms),
            "ms_fingerprint": _fingerprint(ms),
            "run_dir": str(rdir),
            "force": force,
        }
        if confirm is None:
            check = self.config_check(config, ms)
            if not check["valid"]:
                return {"plan": None, "refused": check}
            stages = check["stages"]
            writes = sorted(core_pipeline.WRITES_FLAGS.intersection(stages))
            backups = []
            if not flagversions.exists(ms, core_pipeline.ORIGINAL):
                backups.append(core_pipeline.ORIGINAL)
            if writes:
                backups.append(f"rang_<stage>_<UTC time> before each of {writes}")
            plan = {
                "command": [
                    "rang-core",
                    "run",
                    str(config),
                    str(ms),
                    "--run-dir",
                    str(rdir),
                ]
                + [a for s in force for a in ("--force", s)],
                "stages": stages,
                "writes_ms": True,
                "writes_flags_in": writes,
                "flag_versions_saved_first": backups,
                "run_dir": str(rdir),
                "warnings": check["warnings"],
                "state": self.run_status(rdir)["stages"],
            }
            return {
                "plan": plan,
                "confirm": self._issue("run", payload),
                "expires_seconds": TOKEN_SECONDS,
                "note": "nothing was written; call run again with confirm=<token>",
            }
        self._redeem("run", payload, confirm)
        saved = self._backup(ms)
        argv = [self.python, "-m", "rang.core_cli", "run", str(config), str(ms)]
        argv += ["--run-dir", str(rdir)]
        argv += [a for s in force for a in ("--force", s)]
        jobs = rdir / "mcp" / "jobs"
        job = self._start("run", argv, jobs, cwd=config.parent, saved=saved)
        return self._waited(job, wait_seconds)

    def gemclean(self, ms, name, options=(), confirm=None, wait_seconds=0):
        """`gemclean [options] -name NAME MS`, options from an allowlist, in
        two calls like `run`."""
        from . import core_writeback

        self._require_write()
        ms = self._ms(ms)
        prefix = self._path(name, "image prefix", must_exist=False)
        if not prefix.parent.is_dir():
            raise ToolError(f"{prefix.parent} does not exist")
        options = [str(o) for o in options or ()]
        checked = self._gemclean_options(options)
        writes = self._gemclean_writes(options)
        payload = {
            "ms": str(ms),
            "ms_fingerprint": _fingerprint(ms),
            "name": str(prefix),
            "options": options,
        }
        argv = [
            self.python,
            "-m",
            "rang.gemclean",
            *checked,
            "-name",
            str(prefix),
            str(ms),
        ]
        if confirm is None:
            from .formats import flagversions

            backups = []
            if writes:
                if not flagversions.exists(ms, core_writeback.DEFAULT_BACKUP):
                    backups.append(core_writeback.DEFAULT_BACKUP)
                backups.append("rang_mcp_gemclean_<UTC time>")
            plan = {
                "command": ["gemclean", *checked, "-name", str(prefix), str(ms)],
                "writes_ms": writes,
                "ms_columns": [self._model_column(options)] if writes else [],
                "flag_versions_saved_first": backups,
                "outputs": f"{prefix}-*.fits, {prefix}-report.json",
            }
            return {
                "plan": plan,
                "confirm": self._issue("gemclean", payload),
                "expires_seconds": TOKEN_SECONDS,
                "note": "nothing was written; call gemclean again with confirm=<token>",
            }
        self._redeem("gemclean", payload, confirm)
        saved = []
        if writes:
            saved = self._backup(ms, f"rang_mcp_gemclean_{_stamp()}")
        folder = Path(str(prefix) + ".mcp-jobs")
        job = self._start("gemclean", argv, folder, cwd=prefix.parent, saved=saved)
        return self._waited(job, wait_seconds)

    def _gemclean_options(self, options):
        out, i = [], 0
        while i < len(options):
            opt = options[i]
            if opt in ("-name",):
                raise ToolError("give the prefix as `name`, not -name")
            if opt not in GEMCLEAN_OPTIONS:
                raise ToolError(
                    f"gemclean option {opt!r} is not allowed through MCP "
                    "(research/mcp-server.md, section 4)"
                )
            n = GEMCLEAN_OPTIONS[opt]
            if opt == "-weight" and i + 1 < len(options) and options[i + 1] == "briggs":
                n = 2
            values = options[i + 1 : i + 1 + n]
            if len(values) < n or any(
                v.startswith("-") and not _number(v) for v in values
            ):
                raise ToolError(f"gemclean option {opt} takes {n} value(s)")
            if opt in GEMCLEAN_PATH_OPTIONS:
                values = [str(self._path(values[0], f"{opt} file"))]
            out += [opt, *values]
            i += 1 + n
        return out

    @staticmethod
    def _gemclean_writes(options):
        """True when gemclean will write the MS: -predict, or the model update
        after imaging, which is gemclean's default."""
        if "-predict" in options:
            return True
        update = True
        for opt in options:
            if opt == "-update-model-required":
                update = True
            elif opt == "-no-update-model-required":
                update = False
        return update

    @staticmethod
    def _model_column(options):
        if "-model-column" in options:
            return options[options.index("-model-column") + 1]
        return "MODEL_DATA"

    def _backup(self, ms, extra=None):
        """Save `rang_original` (if missing) and `extra`: the W1 rule."""
        from . import core_writeback

        saved = []
        if core_writeback.backup_flags(ms, core_writeback.DEFAULT_BACKUP):
            saved.append(core_writeback.DEFAULT_BACKUP)
        if extra and core_writeback.backup_flags(
            ms, extra, comment="before MCP gemclean"
        ):
            saved.append(extra)
        return saved

    def _start(self, tool, argv, folder, cwd, saved):
        folder.mkdir(parents=True, exist_ok=True)
        ident = f"{tool}-{_stamp()}-{secrets.token_hex(3)}"
        job_path = folder / f"{ident}.json"
        log = folder / f"{ident}.log"
        record = {
            "schema": JOB_SCHEMA,
            "version": 1,
            "id": ident,
            "tool": tool,
            "argv": argv,
            "cwd": str(cwd),
            "log": str(log),
            "started_utc": _now().isoformat(timespec="seconds"),
            "flag_versions_saved": saved,
        }
        _write_json(job_path, record)
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            kwargs["start_new_session"] = True
        env = dict(os.environ)
        package_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = os.pathsep.join(
            [package_root, *filter(None, [env.get("PYTHONPATH")])]
        )
        self._runners.append(
            subprocess.Popen(
                [self.python, "-m", "rang.mcp_tools", "--job", str(job_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=cwd,
                env=env,
                **kwargs,
            )
        )
        return job_path

    def _waited(self, job_path, wait_seconds):
        deadline = time.monotonic() + min(max(0.0, float(wait_seconds or 0)), MAX_WAIT)
        while True:
            for runner in self._runners:
                runner.poll()  # reap finished runners
            record = job_status(_read_json(job_path))
            if record["state"] in ("done", "failed", "lost"):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.25)
        return {"job_file": str(job_path), "job": record}


def _number(text):
    try:
        float(text)
    except ValueError:
        return False
    return True


def run_job(job_path):
    """Run one job file's argv with output to its log; record pid and exit."""
    job_path = Path(job_path)
    record = _read_json(job_path)
    with open(record["log"], "ab") as log:
        try:
            proc = subprocess.Popen(
                record["argv"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=record["cwd"],
            )
        except OSError as exc:
            log.write(f"rang.mcp_tools: cannot start: {exc}\n".encode())
            code = 127
        else:
            record["pid"] = proc.pid
            record["runner_pid"] = os.getpid()
            _write_json(job_path, record)
            code = proc.wait()
    record = _read_json(job_path)
    record["exit"] = code
    record["finished_utc"] = _now().isoformat(timespec="seconds")
    _write_json(job_path, record)
    return code


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--job":
        sys.exit(0 if run_job(sys.argv[2]) == 0 else 1)
    print("usage: python -m rang.mcp_tools --job JOBFILE", file=sys.stderr)
    sys.exit(2)
