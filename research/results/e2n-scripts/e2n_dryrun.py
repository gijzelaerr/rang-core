"""E2-N's smoke (research/e2n-native.md amendment 3): e2n.yaml's shape on A1
small (development data), so that the one-shot run on E2-N cannot fail on a
code path nobody ran.

    python e2n_dryrun.py A1_MS OUT_DIR       writes OUT_DIR/a1-small.ms (a copy) and
                                             OUT_DIR/config.yaml

The configuration is e2n.yaml with only these edits: the fields mapped to
A1 small (fcal J1939-6342, gcal SIM-GCAL, xcal 3C286-SIM, target
SIM-TARGET); the apply entry's bare field J0408-6545 removed (A1 has no such
field; the bare-name case is covered by `config check e2n.yaml e2n.ms`); the
image 1,024² with multiscale off (A1 small has no short spacings: E2's dry
run `a`, e2-acceptance.md 6.4). The chain then runs as
`e2n_nash_chain.sh` with MS, R, CONFIG and INPUT pointing here, and the
E2N_* field variables set to A1's names. Pass: every step rc 0 and every
stage of run.stages done; the scores mean nothing.
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sub(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"config edit not unique: {old!r}")
    return text.replace(old, new)


def config():
    t = (HERE / "e2n.yaml").read_text(encoding="utf-8")
    t = sub(t, "  gcal: [J1744-5144]\n", "  gcal: [SIM-GCAL]\n")
    t = sub(t, "  xcal: [J1331+3030]\n", "  xcal: [3C286-SIM]\n")
    t = sub(t, "  target: [ASKAPJ1745]\n", "  target: [SIM-TARGET]\n")
    t = sub(
        t, "    - field: [gcal, target, J0408-6545]\n", "    - field: [gcal, target]\n"
    )
    t = sub(t, '      gainfield: [J1939-6342, J1744-5144, J1939-6342, "", "", ""]\n',
            '      gainfield: [J1939-6342, SIM-GCAL, J1939-6342, "", "", ""]\n')  # fmt: skip
    t = sub(t, "  size: [4096, 4096]\n", "  size: [1024, 1024]\n")
    t = sub(t, "  multiscale: true\n", "  multiscale: false\n")
    return "# e2n_dryrun.py: e2n.yaml on A1 small (development), amendment 3.\n" + t


def main(a1, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ms = out / Path(a1).name
    if not ms.exists():
        shutil.copytree(a1, ms)
    shutil.copy(HERE / "mk_rfi_flagging_calibrator_fields_firstpass.yaml", out)
    (out / "config.yaml").write_text(config(), encoding="utf-8")
    print(ms)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
