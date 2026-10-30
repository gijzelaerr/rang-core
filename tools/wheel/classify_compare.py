"""Classify the differences in a compare_core_backends.py receipt.

    python tools/wheel/classify_compare.py COMPARE.json OUT.json

The wheel's archive suite is compared with task J's extension run
(tools/wheel/test.sh), which ran in another worktree with checkout-absolute
archive paths, so the raw comparator always fails on path strings. This
splits its failures into classes (research/wheel.md):

- "path string": both sides name a file under outputs/ or /home/;
- "version string": both sides are version numbers (numpy_version);
- "cost": the section 6 checker's cost criterion and its all_passed, which
  depend on host load and page cache;
- "number": float leaves, with the relative difference of each, reported
  (they follow the NumPy release; see research/wheel.md);
- "worst label": the name of a comparator class's worst leaf, which moves
  with the numbers;
- "missing": files on one side only;
- "other": anything else.

Exit status 1 when any "missing" or "other" difference remains; numbers are
reported, not gated.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

NUM = re.compile(r"^(.*): (-?[0-9.e+-]+|nan|inf) != (-?[0-9.e+-]+|nan|inf)$")
STR = re.compile(r"^(.*): '(.*)' != '(.*)'$")
COST = re.compile(r"^(.*/)?(all_passed|8_cost): (True|False) != (True|False)$")
# The name of the leaf with the worst difference in a comparator class: it
# moves when the numbers move.
WORST = re.compile(r"^(.*/)?worst_path/[0-9]+: '.*' != '.*'$")
VERSION = re.compile(r"[0-9]+(\.[0-9]+)+")


def is_path(text):
    return "outputs/" in text or text.startswith("/home/")


def classify(text):
    if "only in reference" in text or "only in candidate" in text:
        return "missing", None
    if COST.match(text):
        return "cost", None
    if WORST.match(text):
        return "worst label", None
    if m := NUM.match(text):
        a, b = float(m.group(2)), float(m.group(3))
        return "number", abs(a - b) / max(abs(a), abs(b), 1e-300)
    if m := STR.match(text):
        a, b = m.group(2), m.group(3)
        if is_path(a) and is_path(b):
            return "path string", None
        if VERSION.fullmatch(a) and VERSION.fullmatch(b):
            return "version string", None
    return "other", None


def main(source, target):
    data = json.loads(Path(source).read_text())
    classes = Counter()
    numbers = []
    examples = {}
    for failure in data["failures"]:
        kind, rel = classify(failure)
        classes[kind] += 1
        examples.setdefault(kind, failure[:200])
        if rel is not None:
            numbers.append((rel, failure[:200]))
    numbers.sort(reverse=True)
    summary = {
        "receipt": str(source),
        "files": data["files"],
        "json_leaves": data["json_leaves"],
        "arrays": data["arrays"],
        "fits_hdus": data["fits_hdus"],
        "failures": len(data["failures"]),
        "classes": dict(classes),
        "numbers_above_1e-9": sum(rel > 1e-9 for rel, _ in numbers),
        "largest_numbers": [{"rel": rel, "leaf": leaf} for rel, leaf in numbers[:12]],
        "examples": examples,
        "pass": classes["missing"] == 0 and classes["other"] == 0,
    }
    Path(target).write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: summary[k] for k in ("failures", "classes", "pass")}))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
