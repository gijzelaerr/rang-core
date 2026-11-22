# SPDX-License-Identifier: MIT
"""Issue #56: gemclean writes one progress line per major cycle as the cycle
ends (cycle, peak, threshold, components so far, wall seconds), before the
end-of-run report, and `rang-core watch` shows the last one."""

import importlib.util
import re
import subprocess
from pathlib import Path

from rang import core_pipeline, watch

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("g8", HERE / "test_g8_gemclean.py")
g8 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g8)

LINE = re.compile(
    r"^gemclean cycle (\d+): peak (\S+), threshold (\S+), (\d+) components so far, ([\d.]+) s$"
)


def test_one_line_per_major_cycle_before_the_report(tmp_path):
    ms = g8.tiny_ms(tmp_path / "tiny.ms")
    log = tmp_path / "gemclean.log"
    with log.open("w", encoding="utf-8") as fh:
        done = subprocess.run(
            [str(a) for a in (g8.script(), "-name", tmp_path / "img", *g8.SMALL, ms)],
            stdout=fh,
            stderr=subprocess.STDOUT,
            check=False,
        )
    text = log.read_text(encoding="utf-8", errors="replace").splitlines()
    assert done.returncode == 0, text[-5:]
    # The end-of-run summary the pipeline parses; no progress line matches it.
    stop = [(i, core_pipeline._GEMCLEAN_STOP.search(t)) for i, t in enumerate(text)]
    summary, m = next((i, m) for i, m in stop if m)
    cycles = int(m.group(2))
    assert sum(1 for _, m in stop if m) == 1
    found = [
        (i, LINE.match(t))
        for i, t in enumerate(text)
        if t.startswith("gemclean cycle ")
    ]
    assert len(found) == cycles >= 1
    assert all(m for _, m in found), [text[i] for i, m in found if not m]
    numbers = [int(m.group(1)) for _, m in found]
    assert numbers == list(range(1, cycles + 1))
    comps = [int(m.group(4)) for _, m in found]
    assert comps == sorted(comps)
    # Written as each cycle ends: every progress line comes before the summary.
    assert max(i for i, _ in found) < summary
    # rang-core watch shows the last one.
    assert watch.last_cycle_line(log) == text[found[-1][0]]
