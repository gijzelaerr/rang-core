"""The host checker of task E6 (research/e6-table-writer-final.md).

    python examples/check_ms_final.py oracle <run> [<label> [<env>=<v>]]
    python examples/check_ms_final.py cases <run> [<label>] [<case> ...]
    python examples/check_ms_final.py determinism <run>
    python examples/check_ms_final.py readback <run>
    python examples/check_ms_final.py refusals <run>
    python examples/check_ms_final.py regress <run>
    python examples/check_ms_final.py serialisation <run>
    python examples/check_ms_final.py crossversion <run>
    python examples/check_ms_final.py summary <run>
    python examples/check_ms_final.py posthoc <run>

`oracle` runs the O-py cases (`examples/oracle_ms_final.py write`, and
`write-mf` once per MultiFile block size with its aipsrc file) in the
pinned python-casacore container and the O-cpp cases
(`tools/oracles/casacore-cpp/oracle.cc`, values from `prepare`) in the
casacore 3.7.1 container into `<run>/oracle[-<label>]`, with environment
variables such as `MALLOC_PERTURB_=85`. `cases` replays every frozen case
(or the named ones) with `rang.core_ms_write` into `<run>/core[-<label>]`
and compares every file with casacore's (criterion 1: `table.lock` from
offset 260; the masks of the protocol, nothing else). The other steps
check criteria 2 to 7; each writes `<run>/<step>.json`; `summary` writes
`<run>/result.json`.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_ms_rest as e5
import oracle_ms_final as oracle
from check_ms_rest import (
    LOCK_REQUESTS,
    MS_IMAGE,
    array_file_order,
    casacure_reads,
    compare_dumps,
    core_vs_dump,
    hashes,
    load_dump,
    same_array,
    tables_of,
    tree,
    write_json,
)
from rang import core, core_ms_write

CPP_IMAGE = "rang-casacore-cpp:3.7.1"
# Records no row references any more, by case: the element size of the
# column whose old value they hold (0: a string array).
ORPHAN_BITS = {
    "IS-arrays": 0,
    "IS-big": 0,
    "F-multi": 64,
    "F-multi-write": 64,
    "F-cont": 64,
    "F-free": 64,
}
MF_BLOCKS = (4096, 512, 1024, 0)


def outputs_root():
    return (HERE.parent / "outputs").resolve()


# ---------------------------------------------------------------------------
# The masks of the protocol.


def gap_mask(table_dir, name, data, orphan_bits, first_put_bodies=False):
    """Mask 1: the alignment gaps of an array file, the walk of the
    protocol (string bodies consumed unaligned); None if the walk does not
    end exactly at the end of the file. `first_put_bodies` (post hoc, not
    the frozen rule): a string record is also followed by the bodies of its
    first put, which a later put of the same record leaves unreferenced."""
    refs = {}
    for file, offset, bits in core.extension().ms_array_records(str(table_dir)):
        if file == name:
            refs[offset] = bits
    order = "big" if array_file_order(data) else "little"
    u32 = lambda at: int.from_bytes(data[at : at + 4], order)
    version = u32(0)
    mask = np.zeros(len(data), bool)
    bodies = set()

    def note_bodies(head, n):
        for k in range(n):
            o = u32(head + 4 * k)
            if o:
                bodies.add(o)

    # String records the rows reference: their bodies are known up front.
    for offset, bits in refs.items():
        if bits == 0 and offset + 8 <= len(data):
            head = offset + (4 if version > 0 else 0)
            ndim = u32(head)
            dims = [u32(head + 4 + 4 * i) for i in range(ndim)]
            note_bodies(head + 4 + 4 * ndim, int(np.prod(dims)) if dims else 1)
    at = 16
    while at < len(data):
        if at in bodies:
            at += 4 + u32(at)
            continue
        nxt = (at + 7) // 8 * 8
        mask[at : min(nxt, len(data))] = True
        at = nxt
        if at >= len(data):
            return None
        bits = refs.get(at, orphan_bits)
        if bits is None:
            return None
        head = at + (4 if version > 0 else 0)
        ndim = u32(head)
        if ndim > 16:
            return None
        dims = [
            int.from_bytes(
                data[head + 4 + 4 * i : head + 8 + 4 * i], order, signed=True
            )
            for i in range(ndim)
        ]
        n = int(np.prod(dims)) if dims else 1
        start = head + 4 + 4 * ndim
        if bits == 0:
            note_bodies(start, n)
            values = 4 * n
        elif bits == 1:
            values = (n + 7) // 8
        else:
            values = n * bits // 8
        at = start + values
        written = bits == 0 and any(u32(start + 4 * k) for k in range(n))
        if written and first_put_bodies and at not in bodies:
            for _ in range(n):
                if at + 4 > len(data):
                    return None
                at += 4 + u32(at)
    return mask if at == len(data) else None


def continuation_lists(data):
    """The two continuation lists and `ncont_used` of a MultiFile header
    (read here, independently of the core): the header is block 0, then the
    continuation blocks chained by their first 8 bytes."""
    be = lambda b, at: int.from_bytes(b[at : at + 8], "big", signed=True)
    u32 = lambda b, at: int.from_bytes(b[at : at + 4], "big")
    length, block, nxt = be(data, 32), be(data, 40), be(data, 8)
    h = bytearray(data[:block])
    while len(h) < length and nxt:
        h += data[nxt * block + 8 : (nxt + 1) * block]
        nxt = be(data, nxt * block)
    h = bytes(h[:length])
    # The AipsIO object `MultiFile` (magic, then the length of the object).
    at = 64 + 4
    obj_end = at + u32(h, at)
    # Inside it, after its own type and version, the `Block` of file infos.
    p = at + 4
    p += 4 + u32(h, p) + 4  # "MultiFile", version
    p += 4  # Block length
    p += 4 + u32(h, p) + 4  # "Block", version
    nfiles = u32(h, p)
    at = obj_end

    def vector(at, size=8):
        n = be(h, at)
        return [
            int.from_bytes(
                h[at + 8 + size * i : at + 8 + size * (i + 1)], "big", signed=True
            )
            for i in range(n)
        ], at + 8 + size * n

    for _ in range(nfiles + 1):  # block lists, the free list
        _, at = vector(at)
    _, at = vector(at, 4)  # CRC
    c0, at = vector(at)
    c1, at = vector(at)
    used = (u32(h, at), u32(h, at + 4))
    if at + 8 != length:
        raise ValueError("MultiFile header does not parse to its length")
    return (c0, c1), used


def multifile_mask(data):
    """Mask 2 (`table.mf`): a. the block-0 tail of a header within one
    block; b. with continuation, the tail of a set's one used block and a
    set's reserved blocks. Also returns the continuation part of the mask
    (reported separately)."""
    mask = np.zeros(len(data), bool)
    cont = np.zeros(len(data), bool)
    if len(data) < 64:
        return mask, cont
    be = lambda at: int.from_bytes(data[at : at + 8], "big", signed=True)
    length, block, first = be(32), be(40), be(8)
    if length <= block:
        mask[length : min(block, len(data))] = True
        if first == 0:
            return mask, cont
    sets, used = continuation_lists(data)
    active = 1 if sets[1] and first == sets[1][0] else 0
    for s in (0, 1):
        blocks = sets[s]
        for i, b in enumerate(blocks):
            lo, hi = b * block, (b + 1) * block
            if i >= used[s]:
                cont[lo + 0 : hi] = True
            elif used[s] == 1:
                c = (length - block) if s == active else 0
                cont[lo + 8 + c : hi] = True
    return mask | cont, cont


def compare_trees(ours, theirs, orphan_bits=None):
    """Every file byte for byte; table.lock from its sync record on; the
    two masks of the protocol."""
    a, b = tree(ours), tree(theirs)
    out = {
        "missing": sorted(set(b) - set(a)),
        "extra": sorted(set(a) - set(b)),
        "differ": [],
        "masked": [],
    }
    for name in sorted(set(a) & set(b)):
        x, y = a[name].read_bytes(), b[name].read_bytes()
        if name.endswith("table.lock"):
            x, y = x[LOCK_REQUESTS:], y[LOCK_REQUESTS:]
        if x == y:
            continue
        n = min(len(x), len(y))
        diff = np.flatnonzero(
            np.frombuffer(x[:n], np.uint8) != np.frombuffer(y[:n], np.uint8)
        )
        entry = {
            "file": name,
            "ours": len(x),
            "theirs": len(y),
            "bytes_differing": int(diff.size) + abs(len(x) - len(y)),
            "first_difference": int(diff[0]) if diff.size else n,
        }
        file = Path(name)
        mask = None
        if len(x) == len(y):
            if file.name.startswith("table.f") and file.name.endswith("i"):
                mask = gap_mask(b[name].parent, file.name, y, orphan_bits)
                kind = "gap_bytes_masked"
            elif file.name == "table.mf":
                mask, cont = multifile_mask(y)
                kind = "multifile_header_bytes_masked"
                entry["continuation_bytes_differing"] = int(cont[diff].sum())
        if mask is not None and not np.any(~mask[diff]):
            entry[kind] = int(diff.size)
            out["masked"].append(entry)
            continue
        if mask is not None:
            entry["outside_mask"] = int((~mask[diff]).sum())
            entry["first_outside_mask"] = [int(d) for d in diff[~mask[diff]][:8]]
        out["differ"].append(entry)
    out["identical"] = not (
        out["missing"] or out["extra"] or out["differ"] or out["masked"]
    )
    out["identical_but_masked"] = not (out["missing"] or out["extra"] or out["differ"])
    return out


# ---------------------------------------------------------------------------
# The oracle runs.


def docker(image, args, mounts, env=None, extra=()):
    return e5.docker(image, args, mounts, env, extra)


def step_oracle(run, label="", *envs):
    started = time.perf_counter()
    run = Path(run).resolve()
    name = "oracle" + (f"-{label}" if label else "")
    out = run / name
    if out.exists():
        shutil.rmtree(out)
    (out / "casacore").mkdir(parents=True)
    env = dict(e.split("=", 1) for e in envs)
    mounts = [(str(run), "/run", "rw"), (str(HERE), "/ex", "ro")]
    walls, logs = {}, []
    wall, log = docker(
        MS_IMAGE, ["/ex/oracle_ms_final.py", "write", f"/run/{name}"], mounts, env
    )
    walls["write"] = wall
    logs.append(log)
    for block in MF_BLOCKS:
        rc = run / f"casarc-{block}"
        text = "table.storage.option: multifile\n"
        if block:
            text += f"table.storage.blocksize: {block}\n"
        rc.write_text(text)
        wall, log = docker(
            MS_IMAGE,
            ["/ex/oracle_ms_final.py", "write-mf", f"/run/{name}", str(block)],
            mounts,
            {**env, "CASARCFILES": f"/run/casarc-{block}"},
        )
        walls[f"write-mf{block}"] = wall
        logs.append(log)
    # The O-cpp cases: values, then casacore 3.7.1.
    subprocess.run(
        [sys.executable, str(HERE / "oracle_ms_final.py"), "prepare", str(out)],
        check=True,
        capture_output=True,
    )
    cpp = []
    for case in ["D-cubes", "D-multiaxis", "D-be", "X-371", "H-mfh5", "D-reopen"]:
        target = out / "casacore" / case
        if case == "D-reopen":
            shutil.copytree(out / "casacore" / "D-cubes", target)
        wall, log = docker(
            CPP_IMAGE,
            [case, f"/run/{name}/casacore/{case}", f"/run/{name}/cpp/{case}"],
            mounts,
            env,
        )
        walls[f"cpp {case}"] = wall
        logs.append(log)
        line = log.strip().splitlines()[-1]
        cpp.append({"name": case, "wall_s": float(line.split(": ")[1].split()[0])})
    (out / "cases-cpp.json").write_text(json.dumps(cpp, indent=1))
    (out / "oracle.log").write_text("".join(logs))
    result = {"containers_s": walls, "env": env, "pass": True}
    print("".join(logs), flush=True)
    return write_json(run, name, result, started)


def load_values(oracle_dir, name):
    with np.load(Path(oracle_dir) / "values" / f"{name}.npz", allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def casacore_walls(oracle_dir):
    out = {}
    for p in Path(oracle_dir).glob("cases*.json"):
        out.update({c["name"]: c["wall_s"] for c in json.loads(p.read_text())})
    return out


# ---------------------------------------------------------------------------
# Criterion 1: the cases.


def replay(oracle_dir, root, only=()):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    sources = {name: Path(oracle_dir) / "casacore" / name for name, _ in oracle.CASES}
    walls = {}
    for name, f in oracle.CASES:
        if only and name not in only:
            continue
        stored = load_values(oracle_dir, name)
        try:
            _, wall = oracle.run_case(core_ms_write, name, f, root, sources, stored)
            walls[name] = (wall, None)
        except Exception as e:  # noqa: BLE001 - recorded per case
            walls[name] = (None, f"{type(e).__name__}: {e}")
    return walls


def step_cases(run, label="", *only):
    started = time.perf_counter()
    run = Path(run)
    oracle_dir = run / "oracle"
    root = run / ("core" + (f"-{label}" if label else ""))
    walls = replay(oracle_dir, root, only)
    cwalls = casacore_walls(oracle_dir)
    report = []
    for name, f in oracle.CASES:
        if name not in walls:
            continue
        wall, error = walls[name]
        entry = {
            "name": name,
            "oracle": "casacore 3.7.1"
            if name in oracle.CPP_CASES
            else "casacore 3.8.1",
            "core_s": wall,
            "casacore_s": cwalls.get(name),
            "error": error,
        }
        if error is None:
            entry.update(
                compare_trees(
                    root / name, oracle_dir / "casacore" / name, ORPHAN_BITS.get(name)
                )
            )
            files = tree(root / name)
            entry["files"] = len(files)
            entry["bytes"] = sum(p.stat().st_size for p in files.values())
        else:
            entry["identical"] = entry["identical_but_masked"] = False
        report.append(entry)
        state = (
            "identical"
            if entry["identical"]
            else ("masked only" if entry["identical_but_masked"] else "DIFFERS")
        )
        detail = entry.get("differ", error)
        print(
            f"{name}: {state} {detail if detail else ''} {entry.get('masked', '') or ''}",
            flush=True,
        )
    result = {"cases": report, "pass": all(r["identical_but_masked"] for r in report)}
    return write_json(run, "cases" + (f"-{label}" if label else ""), result, started)


def step_determinism(run):
    """Criterion 3: two core runs and one under MALLOC_PERTURB_=85 give the
    same bytes (no mask); casacore's twin and perturbed runs equal its first
    except in masked bytes (H-mfh5 recorded apart)."""
    started = time.perf_counter()
    run = Path(run)
    for label, env in (("twin", {}), ("perturb", {"MALLOC_PERTURB_": "85"})):
        cmd = [sys.executable, str(Path(__file__)), "cases", str(run), label]
        subprocess.run(cmd, check=True, env={**os.environ, **env}, capture_output=True)
    core_ok = {}
    for name, _ in oracle.CASES:
        first = hashes(run / "core" / name)
        core_ok[name] = all(
            hashes(run / f"core-{k}" / name) == first for k in ("twin", "perturb")
        )
    casacore, mfh5 = {}, {}
    for label in ("oracle-twin", "oracle-perturb"):
        other = run / label
        if not other.exists():
            continue
        per = {}
        for name, _ in oracle.CASES:
            d = compare_trees(
                other / "casacore" / name,
                run / "oracle" / "casacore" / name,
                ORPHAN_BITS.get(name),
            )
            per[name] = {
                "identical": d["identical"],
                "identical_but_masked": d["identical_but_masked"],
                "masked": [
                    (
                        m["file"],
                        m.get(
                            "gap_bytes_masked", m.get("multifile_header_bytes_masked")
                        ),
                    )
                    for m in d["masked"]
                ],
                "differ": d["differ"],
            }
        casacore[label] = per
        a = run / "oracle" / "casacore" / "H-mfh5" / "table.mfh5"
        b = other / "casacore" / "H-mfh5" / "table.mfh5"
        if a.exists() and b.exists():
            x, y = a.read_bytes(), b.read_bytes()
            n = min(len(x), len(y))
            diff = np.flatnonzero(
                np.frombuffer(x[:n], np.uint8) != np.frombuffer(y[:n], np.uint8)
            )
            mfh5[label] = {
                "lengths": [len(x), len(y)],
                "differing": [int(d) for d in diff[:20]],
            }
    result = {
        "core_identical_between_runs": core_ok,
        "casacore": casacore,
        "h_mfh5_runs": mfh5,
        "pass": all(core_ok.values())
        and all(
            v["identical_but_masked"] for per in casacore.values() for v in per.values()
        ),
    }
    print(json.dumps({"core": core_ok}, indent=0), flush=True)
    return write_json(run, "determinism", result, started)


# ---------------------------------------------------------------------------
# Criterion 2: read-back.


def step_readback(run):
    started = time.perf_counter()
    run = Path(run).resolve()
    dumps = run / "dumps"
    mounts = [(str(run), "/run", "rw"), (str(HERE), "/ex", "ro")]
    pairs = []
    for name, _ in oracle.CASES:
        pairs += [
            f"core.{name}={e5.guest(run, run / 'core' / name)}",
            f"cc.{name}={e5.guest(run, run / 'oracle' / 'casacore' / name)}",
        ]
    wall, _ = docker(
        MS_IMAGE,
        ["/ex/oracle_ms_final.py", "readback", e5.guest(run, dumps), *pairs],
        mounts,
    )
    report = {}
    for name, _ in oracle.CASES:
        path = run / "oracle" / "casacore" / name
        for suffix, table in tables_of(path):
            a = load_dump(dumps, f"core.{name}{suffix}")
            b = load_dump(dumps, f"cc.{name}{suffix}")
            problems = compare_dumps(a, b)
            core_problems = core_vs_dump(table, b)
            cc_ours, cc_err = casacure_reads(run / "core" / name / suffix.lstrip("."))
            cc_theirs, _ = casacure_reads(table)
            if cc_ours is None or cc_theirs is None:
                casacure = {"reads": False, "reason": cc_err}
            else:
                same = set(cc_ours) == set(cc_theirs) and all(
                    same_array(cc_ours[k], cc_theirs[k]) for k in cc_ours
                )
                kw = casacure_keywords(run / "core" / name / suffix.lstrip(".")) == (
                    casacure_keywords(table)
                )
                casacure = {"reads": True, "same": same and kw, "keywords_same": kw}
            report[f"{name}{suffix}"] = {
                "python_casacore_same": not problems,
                "core_reads_same": not core_problems,
                "casacure": casacure,
                "problems": problems[:10],
                "core_problems": core_problems[:10],
                "cells": len(b[0]),
            }
    bad = {
        k: v
        for k, v in report.items()
        if not (v["python_casacore_same"] and v["core_reads_same"])
        or (v["casacure"].get("reads") and not v["casacure"].get("same"))
    }
    for k, v in bad.items():
        print(k, v["problems"][:3], v["core_problems"][:3], v["casacure"], flush=True)
    result = {
        "tables": len(report),
        "cells": sum(v["cells"] for v in report.values()),
        "casacure_unreadable": sorted(
            k for k, v in report.items() if not v["casacure"]["reads"]
        ),
        "casacure_reasons": sorted(
            {
                v["casacure"].get("reason", "")[:120]
                for v in report.values()
                if not v["casacure"]["reads"]
            }
        ),
        "failures": bad,
        "container_s": wall,
        "pass": not bad,
    }
    return write_json(run, "readback", result, started)


# ---------------------------------------------------------------------------
# Criterion 6: refusals.


def step_refusals(run):
    started = time.perf_counter()
    run = Path(run)
    scratch = run / "refusals"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    pt = core_ms_write
    report = {}

    def attempt(label, f, path, table_expected=None):
        before = hashes(path) if path.exists() else None
        try:
            r = f(path)
            if r is not None:
                r.close()
            entry = {"refused": False}
        except Exception as e:  # noqa: BLE001 - the refusal is the result
            entry = {
                "refused": True,
                "message": str(e),
                "names_e6": "E6" in str(e),
                "not_supported": "not supported" in str(e),
            }
        after = hashes(path) if path.exists() else None
        entry["unchanged"] = before == after if table_expected else after is None
        report[label] = entry

    # R-tcsm-remove: on a copy of casacore's C-var.
    src = run / "oracle" / "casacore" / "C-var"
    target = scratch / "R-tcsm-remove"
    shutil.copytree(src, target)

    def remove(p):
        t = pt.table(str(p), readonly=False)
        try:
            t.removerows([1])
        finally:
            t.close()

    attempt("R-tcsm-remove", remove, target, table_expected=True)
    report["R-tcsm-remove"]["casacore_refuses"] = casacore_refuses_remove(run, target)
    # R-mfh5: create, and open for writing and reading.
    arr = pt.makearrcoldesc("A", 0.0, shape=[4], valuetype="float")
    attempt(
        "R-mfh5 create",
        lambda p: pt.create_table(p, [arr], 3, multifile="multihdf5"),
        scratch / "R-mfh5-create",
    )
    h = scratch / "R-mfh5-open"
    shutil.copytree(run / "oracle" / "casacore" / "H-mfh5", h)
    attempt("R-mfh5 open write", lambda p: pt.table(str(p), readonly=False), h, True)
    attempt("R-mfh5 open read", lambda p: pt.read_cells(str(p), "I", 0, 1), h, True)
    # R-other: a data manager the core does not write.
    other = {"*1": {"TYPE": "Adios2StMan", "NAME": "X", "SPEC": {}, "COLUMNS": ["A"]}}
    attempt(
        "R-other", lambda p: pt.create_table(p, [arr], 3, other), scratch / "R-other"
    )
    # No message of the writer names E6.
    sources = {}
    for root in (HERE.parent / "core" / "src", HERE.parent / "python" / "rang"):
        for p in sorted(root.rglob("*")):
            if p.suffix in (".rs", ".py"):
                text = p.read_text(errors="replace")
                hits = [
                    i + 1 for i, line in enumerate(text.splitlines()) if "E6" in line
                ]
                if hits:
                    sources[str(p.relative_to(HERE.parent))] = hits
    result = {
        "attempts": report,
        "sources_naming_e6": sources,
        "pass": all(
            v["refused"] and not v["names_e6"] and v["unchanged"]
            for v in report.values()
        )
        and report["R-tcsm-remove"]["casacore_refuses"]
        and all(
            report[k]["not_supported"]
            for k in report
            if k.startswith(("R-mfh5", "R-other"))
        )
        and not sources,
    }
    print(json.dumps(result, indent=1), flush=True)
    return write_json(run, "refusals", result, started)


def casacore_refuses_remove(run, target):
    """python-casacore refuses `removerows([1])` on a copy of C-var."""
    probe = Path(run) / "refusals" / "casacore-remove"
    shutil.copytree(target, probe)
    script = Path(run) / "refusals" / "remove.py"
    script.write_text(
        "import sys\nimport casacore.tables as pt\n"
        "t = pt.table(sys.argv[1], readonly=False, ack=False)\n"
        "try:\n    t.removerows([1])\n    print('removed')\n"
        "except Exception as e:\n    print('refused', e)\n"
        "t.close()\n"
    )
    _, log = docker(
        MS_IMAGE,
        [e5.guest(run, script), e5.guest(run, probe)],
        [(str(Path(run).resolve()), "/run", "rw")],
    )
    return log.strip().startswith("refused")


# ---------------------------------------------------------------------------
# Criterion 4: E3, E4 and E5 unchanged; 5: serialisation; 7: cross-version.


def step_regress(run):
    started = time.perf_counter()
    run = Path(run)
    sub = run / "e5"
    sub.mkdir(parents=True, exist_ok=True)
    r34 = e5.step_regress(sub)
    e5_oracle = outputs_root() / "e5-20261031-01"
    e5_run = run / "e5-cases"
    if e5_run.exists():
        shutil.rmtree(e5_run)
    e5_run.mkdir(parents=True)
    os.symlink(e5_oracle / "oracle", e5_run / "oracle")
    r5 = e5.step_cases(e5_run)
    frozen = json.loads((e5_oracle / "cases.json").read_text())["cases"]
    frozen = {c["name"]: c for c in frozen}
    verdicts = {}
    for c in r5["cases"]:
        f = frozen[c["name"]]
        same_verdict = c["identical_but_masked"] == f["identical_but_masked"]
        same_bytes = [(d["file"], d["bytes_differing"]) for d in c["differ"]] == [
            (d["file"], d["bytes_differing"]) for d in f["differ"]
        ]
        verdicts[c["name"]] = {
            "same_verdict": same_verdict,
            "same_differing_bytes": same_bytes,
            "identical_but_masked": c["identical_but_masked"],
        }
    result = {
        "e3_e4": {k: v for k, v in r34.items() if k != "details"},
        "e5_cases": verdicts,
        "e5_identical_or_masked": sum(
            v["identical_but_masked"] for v in verdicts.values()
        ),
        "pass": bool(r34["pass"])
        and all(
            v["same_verdict"] and v["same_differing_bytes"] for v in verdicts.values()
        ),
    }
    print(json.dumps({k: v for k, v in result.items() if k != "e5_cases"}), flush=True)
    return write_json(run, "regress", result, started)


def step_serialisation(run):
    started = time.perf_counter()
    run = Path(run)
    report, totals, multifile = {}, [0, 0, 0, 0], 0
    for name, _ in oracle.CASES:
        t = run / "oracle" / "casacore" / name
        failures = []
        if (t / "table.mf").exists():
            failures += core.extension().ms_multifile_check(str(t))
            multifile += 1
        n_tables, ssm, tiled, ism, more = core.extension().ms_serialisation_check_e5(
            str(t)
        )
        totals = [
            totals[0] + n_tables,
            totals[1] + ssm,
            totals[2] + tiled,
            totals[3] + ism,
        ]
        report[name] = failures + more
    e5_oracle = outputs_root() / "e5-20261031-01" / "oracle" / "casacore"
    e5_fail = {}
    for t in sorted(p for p in e5_oracle.iterdir() if (p / "table.dat").exists()):
        more = core.extension().ms_serialisation_check_e5(str(t))[4]
        if (t / "table.mf").exists():
            more += core.extension().ms_multifile_check(str(t))
        if more:
            e5_fail[t.name] = more
    result = {
        "tables": totals[0],
        "ssm_files": totals[1],
        "tiled_headers": totals[2],
        "ism_files": totals[3],
        "multifile_headers": multifile,
        "failures": {k: v for k, v in report.items() if v},
        "e5_failures": e5_fail,
    }
    result["pass"] = not result["failures"] and not e5_fail
    print(json.dumps(result), flush=True)
    return write_json(run, "serialisation", result, started)


def step_crossversion(run):
    """Criterion 7: X-371 (casacore 3.7.1) equals C-var (3.8.1)."""
    started = time.perf_counter()
    run = Path(run)
    base = run / "oracle" / "casacore"
    d = compare_trees(base / "X-371", base / "C-var")
    result = {"compare": d, "pass": d["identical_but_masked"]}
    print(json.dumps(result), flush=True)
    return write_json(run, "crossversion", result, started)


def casacure_keywords(path):
    """casacure's table and column keywords of a table, as plain values."""
    try:
        from casacure import tables as cc
    except ImportError:
        return None
    try:
        t = cc.table(str(path), ack=False)
    except Exception:  # noqa: BLE001 - read elsewhere
        return None
    try:
        out = {"": oracle.oracle_ms_create.plain(t.getkeywords())}
        for c in t.colnames():
            out[c] = oracle.oracle_ms_create.plain(t.getcolkeywords(c))
        return json.dumps(out, sort_keys=True, default=str)
    finally:
        t.close()


def step_posthoc(run):
    """Post hoc (after the frozen summary; not a criterion): the cases
    whose array files differ outside the frozen gap mask, walked again with
    the bodies of a string record's first put consumed after it."""
    started = time.perf_counter()
    run = Path(run)
    cases = json.loads((run / "cases.json").read_text())["cases"]
    report = {}
    for c in cases:
        if c["identical_but_masked"] or c.get("error"):
            continue
        entry = {}
        for d in c["differ"]:
            file = d["file"]
            theirs = run / "oracle" / "casacore" / c["name"] / file
            ours = run / "core" / c["name"] / file
            x, y = ours.read_bytes(), theirs.read_bytes()
            if len(x) != len(y) or not Path(file).name.endswith("i"):
                entry[file] = {"not_an_array_file_or_lengths_differ": True}
                continue
            diff = np.flatnonzero(
                np.frombuffer(x, np.uint8) != np.frombuffer(y, np.uint8)
            )
            mask = gap_mask(
                theirs.parent, Path(file).name, y, ORPHAN_BITS.get(c["name"]), True
            )
            entry[file] = {
                "bytes_differing": int(diff.size),
                "walk_ends": mask is not None,
                "outside_extended_mask": None
                if mask is None
                else int((~mask[diff]).sum()),
            }
        report[c["name"]] = entry
    result = {
        "label": "post hoc",
        "cases": report,
        "all_gaps": all(
            v.get("outside_extended_mask") == 0
            for e in report.values()
            for v in e.values()
        ),
    }
    print(json.dumps(result, indent=1), flush=True)
    return write_json(run, "posthoc", result, started)


def step_summary(run):
    run = Path(run)
    names = {
        "1 byte identity": "cases",
        "2 read-back": "readback",
        "3 determinism": "determinism",
        "4 E3, E4 and E5 unchanged": "regress",
        "5 serialisation identity": "serialisation",
        "6 refusals": "refusals",
        "7 cross-version identity": "crossversion",
    }
    result = {}
    for label, step in names.items():
        f = run / f"{step}.json"
        result[label] = json.loads(f.read_text()).get("pass") if f.exists() else None
    result["all_pass"] = all(v is True for v in result.values())
    (run / "result.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return result


def main(argv):
    steps = {
        "oracle": step_oracle,
        "cases": step_cases,
        "determinism": step_determinism,
        "readback": step_readback,
        "refusals": step_refusals,
        "regress": step_regress,
        "serialisation": step_serialisation,
        "crossversion": step_crossversion,
        "summary": step_summary,
        "posthoc": step_posthoc,
    }
    if len(argv) < 2 or argv[1] not in steps:
        print(__doc__)
        return 2
    steps[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
