# SPDX-License-Identifier: MIT
"""The UHF gate's smoke, step 8.3 of research/uhf-gate.md (E2-N amendment 3's
rule): uhf-dev.yaml's shape on A1 small (development data), so that D's
one-shot run cannot fail on a code path nobody ran.

    python ug_dryrun.py A1_MS OUT_DIR     OUT_DIR/a1-small.ms (a copy), OUT_DIR/cfg/

The configurations are uhf-dev.yaml and uhf-dev-3c.yaml with only these
edits: the fields mapped to A1 small (gcal SIM-GCAL, xcal 3C286-SIM, target
SIM-TARGET; J1939-6342 is A1's own name), the image 1,024^2 with multiscale
off (A1 small has no short spacings: E2's dry run `a`). The DOI 1934-638
catalogue stays the model. The chain then runs as ug_chain.sh with UG_BLOCK=A1
(ug.py maps SIM-GCAL in for J0408-6545, so H's rows run too). Pass: every
step rc 0 and every stage of run.stages done; the scores mean nothing.
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parent


def sub(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"config edit not unique: {old!r}")
    return text.replace(old, new)


def config(name):
    t = (FROZEN / name).read_text(encoding="utf-8")
    t = sub(t, "  gcal: [J1609+2641]\n", "  gcal: [SIM-GCAL]\n")
    t = sub(t, "  xcal: [J1331+3030]\n", "  xcal: [3C286-SIM]\n")
    t = sub(t, "  target: [ILTJ153010]\n", "  target: [SIM-TARGET]\n")
    t = sub(t, '      gainfield: [J1939-6342, J1609+2641, J1939-6342, "", "", ""]\n',
            '      gainfield: [J1939-6342, SIM-GCAL, J1939-6342, "", "", ""]\n')  # fmt: skip
    t = sub(t, "  size: [6144, 6144]\n", "  size: [1024, 1024]\n")
    t = sub(t, "  multiscale: true\n", "  multiscale: false\n")
    return f"# ug_dryrun.py: {name} on A1 small (development), uhf-gate.md 8.3.\n" + t


def main(a1, out, strategy):
    out = Path(out)
    (out / "cfg").mkdir(parents=True, exist_ok=True)
    ms = out / Path(a1).name
    if not ms.exists():
        shutil.copytree(a1, ms)
    shutil.copy(strategy, out / "cfg" / "firstpass_UHF.yaml")
    (out / "cfg" / "uhf-dev.yaml").write_text(config("uhf-dev.yaml"), encoding="utf-8")
    (out / "cfg" / "uhf-dev-3c.yaml").write_text(
        config("uhf-dev-3c.yaml"), encoding="utf-8"
    )
    sys.path.insert(0, str(HERE.parents[1] / "e2-acceptance-scripts"))
    import json

    import e2_post as P

    h = dict(P.flag_hash(ms), ms=str(ms))  # gate 2a's reference for the smoke copy
    (out / "flaghash-input.json").write_text(
        json.dumps(h, indent=1) + "\n", encoding="utf-8"
    )
    print(ms, h)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
