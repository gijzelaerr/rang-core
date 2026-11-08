"""resolve_tail.py FILE : bin/gemclean.rs's last three conflict hunks interleave two functions (G9's
run_polarizations and G6's write_model/predict_only) around shared report lines; write each
function whole, ours first (merge helper for main 3defaae)."""

import sys

path = sys.argv[1]
lines = open(path).read().splitlines(keepends=True)
starts = [i for i, l in enumerate(lines) if l.startswith("<<<<<<< ")]
mids = [i for i, l in enumerate(lines) if l.startswith("=======")]
ends = [i for i, l in enumerate(lines) if l.startswith(">>>>>>> ")]
assert len(starts) == len(mids) == len(ends)
h = list(zip(starts, mids, ends))[-3:]
# The function tail after the last hunk: up to and including the closing brace.
close = h[2][2] + 1
while lines[close].rstrip("\n") != "}":
    close += 1
tail = lines[h[2][2] + 1 : close + 1]
common1 = lines[h[0][2] + 1 : h[1][0]]
common2 = lines[h[1][2] + 1 : h[2][0]]


def side(k):
    parts = []
    for i, (s, m, e) in enumerate(h):
        parts += lines[s + 1 : m] if k == "ours" else lines[m + 1 : e]
        parts += [common1, common2, tail][i]
    return parts


ours = side("ours")
theirs = side("theirs")
new = lines[: h[0][0]] + ours + ["\n"] + theirs + lines[close + 1 :]
open(path, "w").write("".join(new))
