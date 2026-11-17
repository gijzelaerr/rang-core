"""Appendix A of the E2 protocol: A0's gates copied verbatim by line range
from research/a0-acceptance.md at commit a373a4c (A0 amendment 1, its last
change), checked byte for byte against that commit.
    python e2_appendix_a.py research/results/e2-acceptance/appendix-a.md"""

import subprocess
import sys

COMMIT = "a373a4c"
RANGES = [  # (first, last) 1-based inclusive, with what they hold
    (249, 294, "section 5, common rules"),
    (297, 305, "6.1, gates 1 to 3c"),
    (309, 340, "6.2, stage tolerances"),
    (355, 398, "6.3, E2-A and E2-B"),
    (498, 560, "6.5 and 6.6, failure rules and amendment 1"),
]


def main(out):
    text = subprocess.run(
        ["git", "show", f"{COMMIT}:research/a0-acceptance.md"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8")
    lines = text.splitlines(keepends=True)
    with open("research/a0-acceptance.md", encoding="utf-8", newline="") as fh:
        assert fh.read() == text, "a0-acceptance.md changed since " + COMMIT
    parts = [
        "## Appendix A. A0's gates, verbatim\n\n",
        (
            "Copied by `research/results/e2-acceptance-scripts/e2_appendix_a.py` from\n"
            f"[a0-acceptance.md](../../a0-acceptance.md) at `{COMMIT}`, lines as given; nothing\n"
            "edited. Section and table references inside are A0's.\n\n"
        ),
    ]
    for a, b, what in RANGES:
        parts.append(f"<!-- A0 lines {a}-{b}: {what} -->\n\n")
        block = "".join(lines[a - 1 : b])
        parts.append(block if block.endswith("\n") else block + "\n")
        parts.append("\n")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(parts).rstrip("\n") + "\n")
    for a, b, _ in RANGES:  # the check: every copied block is in the output unchanged
        assert "".join(lines[a - 1 : b]) in "".join(parts)
    print(out, sum(b - a + 1 for a, b, _ in RANGES), "lines")


if __name__ == "__main__":
    main(sys.argv[1])
