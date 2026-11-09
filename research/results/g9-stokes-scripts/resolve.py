"""resolve.py FILE MODE... : resolve FILE's conflict hunks in order, each by MODE: both (ours then
theirs), ours, theirs or none (merge helper for the G9 merge of main 3defaae)."""

import sys

path, modes = sys.argv[1], sys.argv[2:]
out, ours, theirs, state, k = [], [], [], None, 0
for line in open(path).read().splitlines(keepends=True):
    if line.startswith("<<<<<<< "):
        state, ours, theirs = "ours", [], []
    elif line.startswith("=======") and state == "ours":
        state = "theirs"
    elif line.startswith(">>>>>>> ") and state == "theirs":
        mode = modes[k]
        k += 1
        out += {"both": ours + theirs, "ours": ours, "theirs": theirs, "none": []}[mode]
        state = None
    elif state == "ours":
        ours.append(line)
    elif state == "theirs":
        theirs.append(line)
    else:
        out.append(line)
assert k == len(modes), (k, modes)
open(path, "w").write("".join(out))
