# SPDX-License-Identifier: GPL-3.0-or-later
"""Chunk tasks and their executor (multi-node stage 1, research/chunk-task-api.md).

W3's and W3b's chunk loops (research/w3-chunking.md, w3b-chainchunks.md) as
explicit tasks:

- `ChunkSpec`: one task, serialisable (`to_json`, `from_json`): what to read
  and what to compute, never a live object;
- `plan_*`: the specs of one stage step, in the order their partials are
  reduced (`index`);
- `run(spec, source=None)`: reads the cell columns the task needs and runs
  the kernel; it never writes the MS. Without a `source` it opens its own
  reader, as a worker process does;
- the reduce is the caller's: it consumes the partials in plan order and
  writes them through the stage's one `WriteBack` session (the single
  writer), so results do not depend on scheduling;
- `executor(config)`: `data.executor: local` with `data.processes` processes
  (default 1: the tasks run inline, in this process, on the stage's own
  source; above 1, a spawn process pool with `data.threads` rayon threads
  shared out among the workers).

Splitting changes no arithmetic: every stage gives the bit-identical result
at any process count (the gate of research/chunk-task-api.md, section 3).
"""

import base64
import collections
import contextlib
import functools
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

EXECUTORS = ("local",)


class ExecutorError(ValueError):
    """An executor setting that cannot run."""


# -- the task ----------------------------------------------------------------------


@dataclass
class ChunkSpec:
    """One task of a stage: `kind` names its `run` function, `index` its
    place in the plan (the reduction order), `key` its identity, `params`
    JSON-able settings and `arrays` NumPy inputs (rows, per-row metadata,
    solution slices)."""

    stage: str
    kind: str
    index: int
    ms: str
    key: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    arrays: dict = field(default_factory=dict)

    def to_json(self):
        arrays = {
            name: {
                "dtype": np.asarray(a).dtype.str,
                "shape": list(np.shape(a)),
                "data": base64.b64encode(np.ascontiguousarray(a).tobytes()).decode(
                    "ascii"
                ),
            }
            for name, a in self.arrays.items()
        }
        return json.dumps(
            {
                "stage": self.stage,
                "kind": self.kind,
                "index": self.index,
                "ms": self.ms,
                "key": self.key,
                "params": self.params,
                "arrays": arrays,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, text):
        raw = json.loads(text)
        arrays = {
            name: np.frombuffer(base64.b64decode(a["data"]), np.dtype(a["dtype"]))
            .reshape(a["shape"])
            .copy()
            for name, a in raw["arrays"].items()
        }
        return cls(
            raw["stage"],
            raw["kind"],
            int(raw["index"]),
            raw["ms"],
            raw["key"],
            raw["params"],
            arrays,
        )


def same_spec(a, b):
    """True when two specs are equal, arrays bit for bit."""
    if (a.stage, a.kind, a.index, a.ms, a.key, a.params) != (
        b.stage,
        b.kind,
        b.index,
        b.ms,
        b.key,
        b.params,
    ):
        return False
    if a.arrays.keys() != b.arrays.keys():
        return False
    return all(
        a.arrays[k].dtype == b.arrays[k].dtype
        and a.arrays[k].shape == b.arrays[k].shape
        and a.arrays[k].tobytes() == b.arrays[k].tobytes()
        for k in a.arrays
    )


# -- run -----------------------------------------------------------------------------


def run(spec, source=None):
    """The partial of `spec`, read from `source` (the stage's reader or
    `WriteBack` session) or, when None, from a reader of `spec.ms` opened
    for this task."""
    fn = RUNNERS[spec.kind]
    if source is not None:
        return fn(spec, source)
    from . import core_ms

    with core_ms.open_table(spec.ms) as reader:
        return fn(spec, reader)


@functools.lru_cache(maxsize=8)
def _strategies(text):
    from . import core_flag

    return core_flag.parse_strategy(text)


def _run_flag(spec, source):
    """One flag block: the Tricolour port on its rows, on the group's whole
    time grid (research/w3-chunking.md 1.2)."""
    from . import core_chunks, core_flag

    a, p = spec.arrays, spec.params
    block = a["rows"]
    data = core_chunks.read_rows(source, p["column"], block)
    flag = core_chunks.read_rows(source, "FLAG", block)
    masks = [a[f"mask{i}"] for i in range(int(p["masks"]))]
    result = core_flag.flag_rows(
        data,
        flag,
        a["antenna1"],
        a["antenna2"],
        a["time"],
        a["antenna_position"],
        a["chan_freq"],
        a["chan_width"],
        a["corr_type"],
        _strategies(p["strategy"]),
        masks=masks,
        want_intensity=False,
        want_stages=False,
        time_grid=a["time_grid"],
    )
    del data
    out = result["flags"]
    new = out if p["write"] == "replace" else (flag | out)
    return {
        "rows": block,
        "flag": new,
        "before": int(flag.sum()),
        "after": int(new.sum()),
        "seconds": result["seconds"],
    }


def _run_solve(spec, source):
    """One `complex` solve on the rows and channels of `spec`: a whole
    partition (`pass` 0), or a chunk of whole solution intervals in pass 1
    (stop test off, trace: returns the per-iteration counts) or pass 2 (to
    the replayed stop; research/w3-chunking.md 1.3)."""
    from . import core_chunks
    from . import core_pipeline as pipe

    a, p = spec.arrays, spec.params
    info = {"cell": tuple(p["cell"]), "weight_spectrum": p["weight_spectrum"]}
    chans = slice(*p["chans"])
    inputs = pipe._solve_inputs(
        source,
        a["rows"],
        chans,
        info,
        p["weights_mode"],
        p["model_source"],
        p["model_column"],
    )
    args = (
        inputs,
        a["antenna1"],
        a["antenna2"],
        int(p["nant"]),
        a["time_bin"],
        a["freq_bin"],
        int(p["ntime"]),
        int(p["nfreq"]),
        p["term"],
    )
    which = int(p["pass"])
    if which == 0:
        return pipe._complex_rows(*args)
    if which == 1:
        with tempfile.TemporaryDirectory(prefix="rang-w3-trace-") as tmp:
            trace = Path(tmp) / "trace.json"
            pipe._complex_rows(*args, stop_fraction=pipe.NO_STOP, trace=str(trace))
            return np.array(core_chunks.trace_counts(trace), np.int64)
    sol = pipe._complex_rows(
        *args,
        stop_fraction=pipe.NO_STOP,
        max_iterations=int(p["max_iterations"]),
        trace="",
    )
    return {"gains": sol.gains, "flags": sol.flags}


def _run_apply(spec, source):
    """One row chunk of `applycal.apply_complex`: the gains of each
    partition its rows belong to, on their own bins (research/c4b-apply-ms.md),
    from the time-bin slices the spec carries."""
    from . import cal_apply
    from .core_chunks import _getter

    a, p = spec.arrays, spec.params
    get = _getter(source)
    start, n = int(p["start"]), int(p["n"])
    part = a["row_part"]
    data = get(p["input_column"], start, n)
    flag = get("FLAG", start, n)
    out = get(p["column"], start, n)
    new_flag = flag.copy()
    a1 = get("ANTENNA1", start, n)
    a2 = get("ANTENNA2", start, n)
    before = after = 0
    for k, lo in zip(p["parts"], p["lo"]):
        idx = np.flatnonzero(part == k)
        got, gflag = cal_apply.apply_jones(
            data[idx],
            flag[idx],
            a1[idx],
            a2[idx],
            a[f"gains{k}"],
            a[f"valid{k}"],
            a["row_bin"][idx] - int(lo),
            a[f"freq_bin{k}"],
            threads=int(p["threads"]),
        )
        out[idx] = got
        new_flag[idx] = gflag
        before += int(flag[idx].sum())
        after += int(gflag.sum())
    return {
        "start": start,
        "out": out,
        "flag": new_flag,
        "before": before,
        "after": after,
    }


RUNNERS = {"flag-block": _run_flag, "solve": _run_solve, "apply-rows": _run_apply}


# -- plans ---------------------------------------------------------------------------


def plan_flag(ms, info, groups, max_rows, column, write, strategy_text, masks):
    """The flag stage's specs: per (field, ddid, scan) group (`groups`, an
    ordered {key: row indices}) one block, or blocks of consecutive
    baselines in Tricolour's order when the group has more than `max_rows`
    rows, each on the group's whole time grid. Returns (specs, blocks per
    group)."""
    from . import core_chunks, core_flag

    rows_meta = info["rows"]
    shared = {
        "antenna_position": np.asarray(info["antenna_position"]),
        "chan_freq": np.asarray(info["chan_freq"]),
        "chan_width": np.asarray(info["chan_width"]),
        "corr_type": np.asarray(info["corr_type"]),
    }
    for i, m in enumerate(masks):
        shared[f"mask{i}"] = np.asarray(m)
    specs, nblocks = [], []
    for g, ((field_id, ddid, scan), idx) in enumerate(groups.items()):
        time_grid = np.unique(rows_meta["TIME"][idx])
        ubl = core_flag.unique_baselines(
            rows_meta["ANTENNA1"][idx], rows_meta["ANTENNA2"][idx]
        )
        if len(idx) <= max_rows:
            parts = [idx]
        else:
            lookup = {(int(a), int(b)): k for k, (a, b) in enumerate(ubl)}
            bl = np.array(
                [
                    lookup[(int(a), int(b))]
                    for a, b in zip(
                        rows_meta["ANTENNA1"][idx], rows_meta["ANTENNA2"][idx]
                    )
                ],
                np.int64,
            )
            parts = [
                idx[np.isin(bl, chosen)]
                for chosen in core_chunks.baseline_blocks(bl, len(ubl), max_rows)
            ]
        nblocks.append(len(parts))
        for b, block in enumerate(parts):
            specs.append(
                ChunkSpec(
                    "flag",
                    "flag-block",
                    len(specs),
                    str(ms),
                    {
                        "group": g,
                        "field_id": int(field_id),
                        "ddid": int(ddid),
                        "scan": int(scan),
                        "block": b,
                        "blocks": len(parts),
                    },
                    {
                        "column": column,
                        "write": write,
                        "strategy": strategy_text,
                        "masks": len(masks),
                    },
                    {
                        "rows": np.asarray(block, np.int64),
                        "antenna1": rows_meta["ANTENNA1"][block],
                        "antenna2": rows_meta["ANTENNA2"][block],
                        "time": rows_meta["TIME"][block],
                        "time_grid": time_grid,
                        **shared,
                    },
                )
            )
    return specs, nblocks


def solve_spec(ms, index, key, info, rows, chans, time_bin, freq_bin, ntime, nfreq,
               term, read, which, max_iterations=None):  # fmt: skip
    """A `solve` spec (`which`: 0 whole partition, 1 or 2 the pass of a
    chunk)."""
    weights_mode, model_source, model_column = read
    a = info["rows"]
    return ChunkSpec(
        "calibrate",
        "solve",
        index,
        str(ms),
        dict(key),
        {
            "pass": int(which),
            "chans": [int(chans.start), int(chans.stop)],
            "cell": [int(c) for c in info["cell"]],
            "weight_spectrum": bool(info.get("weight_spectrum")),
            "weights_mode": weights_mode,
            "model_source": model_source,
            "model_column": model_column,
            "nant": len(info["antennas"]),
            "ntime": int(ntime),
            "nfreq": int(nfreq),
            "term": _jsonable(term),
            "max_iterations": None if max_iterations is None else int(max_iterations),
        },
        {
            "rows": np.asarray(rows, np.int64),
            "antenna1": a["ANTENNA1"][rows],
            "antenna2": a["ANTENNA2"][rows],
            "time_bin": np.asarray(time_bin),
            "freq_bin": np.asarray(freq_bin),
        },
    )


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def plan_apply(ms, chunks, row_part, row_bin, grids, input_column, column, threads):
    """`applycal.apply_complex`'s specs: one per row chunk `(start, n)` that
    holds rows of a solved partition, with the time-bin slice of each of
    its partitions' gains (`grids[k]`: gains, valid, freq_bin)."""
    specs = []
    for start, n in chunks:
        part = row_part[start : start + n]
        if not (part >= 0).any():
            continue
        bins = row_bin[start : start + n]
        arrays = {"row_part": part, "row_bin": bins}
        parts, los = [], []
        for k in np.unique(part[part >= 0]):
            k = int(k)
            mine = bins[part == k]
            lo, hi = int(mine.min()), int(mine.max()) + 1
            gains, valid, fb = grids[k]
            arrays[f"gains{k}"] = gains[lo:hi]
            arrays[f"valid{k}"] = valid[lo:hi]
            arrays[f"freq_bin{k}"] = fb
            parts.append(k)
            los.append(lo)
        specs.append(
            ChunkSpec(
                "apply",
                "apply-rows",
                len(specs),
                str(ms),
                {"start": int(start), "n": int(n)},
                {
                    "start": int(start),
                    "n": int(n),
                    "parts": parts,
                    "lo": los,
                    "input_column": input_column,
                    "column": column,
                    "threads": int(threads),
                },
                arrays,
            )
        )
    return specs


# -- the executor ----------------------------------------------------------------------


def settings(config):
    """(executor, processes, threads) of `config['data']`."""
    data = config.get("data", {}) if config else {}
    kind = data.get("executor") or "local"
    processes = int(data.get("processes") or 1)
    threads = data.get("threads")
    return kind, processes, None if threads is None else int(threads)


def total_threads(threads=None):
    """The thread budget the workers share: `data.threads`, else the
    process's RAYON_NUM_THREADS, else the CPU count."""
    if threads:
        return int(threads)
    env = os.environ.get("RAYON_NUM_THREADS")
    if env and env.strip().isdigit() and int(env) > 0:
        return int(env)
    return os.cpu_count() or 1


def _init_worker(threads):
    # Before any kernel runs: the core's rayon pool is built at first use.
    os.environ["RAYON_NUM_THREADS"] = str(int(threads))


class Executor:
    """`map(specs, source)`: the partials of `specs` in plan order. One
    process runs them inline on `source`; more run them in a spawn process
    pool, each worker reading through its own reader, with at most
    2 x processes tasks in flight."""

    def __init__(self, processes=1, threads=None, kind="local"):
        if kind not in EXECUTORS:
            raise ExecutorError(f"data.executor {kind!r}: one of {list(EXECUTORS)}")
        if int(processes) < 1:
            raise ExecutorError("data.processes must be at least 1")
        self.kind = kind
        self.processes = int(processes)
        self.threads = threads
        self._pool = None

    @property
    def threads_per_process(self):
        if self.processes == 1:
            return None
        return max(1, total_threads(self.threads) // self.processes)

    def describe(self):
        return {
            "executor": self.kind,
            "processes": self.processes,
            "threads_per_process": self.threads_per_process,
        }

    def _start(self):
        if self._pool is None:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor

            self._pool = ProcessPoolExecutor(
                max_workers=self.processes,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_init_worker,
                initargs=(self.threads_per_process,),
            )
        return self._pool

    def map(self, specs, source=None):
        if self.processes == 1:
            for spec in specs:
                yield run(spec, source)
            return
        pool = self._start()
        pending = collections.deque()
        window = 2 * self.processes
        try:
            for spec in specs:
                pending.append(pool.submit(run, spec))
                if len(pending) >= window:
                    yield pending.popleft().result()
            while pending:
                yield pending.popleft().result()
        finally:
            for f in pending:
                f.cancel()

    def close(self):
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None


INLINE = Executor()


@contextlib.contextmanager
def executor(config):
    """The executor `config['data']` asks for, closed on exit."""
    kind, processes, threads = settings(config)
    ex = Executor(processes, threads, kind)
    try:
        yield ex
    finally:
        ex.close()


def problems(config):
    """[str]: executor settings that cannot run (preflight)."""
    kind, processes, _ = settings(config)
    out = []
    if kind not in EXECUTORS:
        out.append(f"data.executor {kind!r}: one of {list(EXECUTORS)}")
    if processes > 1 and os.environ.get("RANG_SOLVE_TRACE"):
        out.append(
            "RANG_SOLVE_TRACE writes one trace file per solve; it needs "
            "data.processes: 1 (research/chunk-task-api.md 1.1)"
        )
    return out


__all__ = [
    "EXECUTORS",
    "INLINE",
    "ChunkSpec",
    "Executor",
    "ExecutorError",
    "executor",
    "plan_apply",
    "plan_flag",
    "problems",
    "run",
    "same_spec",
    "settings",
    "solve_spec",
    "total_threads",
]
