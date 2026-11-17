#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# W2 end-to-end run into a fresh directory (research/w2-commands.md, criteria 1-4).
# Usage: bash tools/oracles/w2/run.sh /mnt/d/rang/outputs/fp-w2-20261106/run-NN [MS] [STRATEGY]
# Needs the worktree .venv (with casacure) and core/target/release/gemclean.
# CPU-light (a 40 MB MS); not a timing run.
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
code="$root/tools/oracles/w2"
py="$root/.venv/bin/python"
cli=("$py" -m rang.core_cli)
run=$(realpath -m "$1")
src=${2:-/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms}
strategy=${3:-$HOME/Github/rang/outputs/caracal-strategy-inputs-8f7bb363/mk_rfi_flagging_calibrator_fields_firstpass.yaml}
gemclean="$root/core/target/release/gemclean"
if [ -e "$run" ]; then echo "$run exists; choose a fresh run directory" >&2; exit 1; fi
mkdir -p "$run/timing" "$run/logs" "$run/out"
cp "$strategy" "$run/strategy.yaml"

step() {  # a timed step; records the exit status, never stops the run
  local name=$1; shift
  echo "## $name"
  /usr/bin/time -f "%e %M %x" -o "$run/timing/$name.txt" "$@" > "$run/logs/$name.log" 2>&1
  echo "   exit $(tail -1 "$run/timing/$name.txt" | awk '{print $3}')"
}
config() {  # config NAME GEMCLEAN [EXTRA...]
  local name=$1 binary=$2; shift 2
  cat > "$run/$name.yaml" <<EOF
schema: rang-config
version: 1
fields:
  fcal: [J1939-6342]
  target: [SIM-TARGET]
flag:
  strategy: strategy.yaml
calibrate:
  primary:
    terms: [{type: complex, solint: int, freqint: 16}]
image:
  gemclean: $binary
  size: [512, 512]
  scale: 2asec
  niter: 2000
  threads: 2
$(printf '%s\n' "$@")
EOF
}
copy() { cp -r "$src" "$run/$1"; }

config good "$gemclean"
config bad "$run/no-such-gemclean"
config selfcal "$gemclean" "run:" "  stages: [flag, calibrate, image, selfcal]"
config apply "$gemclean" "run:" "  stages: [flag, calibrate, apply, image]"

# Criterion 1 and 2: the commands one by one on a copy; the oracle on a pristine copy.
copy pristine.ms
copy cmd.ms
step hashes-pristine "$py" "$code/oracle.py" hashes "$run/pristine.ms" "$run/out/hashes-pristine.json"
step flag "${cli[@]}" flag "$run/good.yaml" "$run/cmd.ms"
step calibrate "${cli[@]}" calibrate "$run/good.yaml" "$run/cmd.ms"
step image "${cli[@]}" image "$run/good.yaml" "$run/cmd.ms"
step selfcal "${cli[@]}" selfcal "$run/good.yaml" "$run/cmd.ms"
step apply "${cli[@]}" apply "$run/good.yaml" "$run/cmd.ms"
step run-selfcal-refused "${cli[@]}" run "$run/selfcal.yaml" "$run/cmd.ms"
step run-apply-refused "${cli[@]}" run "$run/apply.yaml" "$run/cmd.ms"
step flag-again "${cli[@]}" flag "$run/good.yaml" "$run/cmd.ms"
step hashes-cmd "$py" "$code/oracle.py" hashes "$run/cmd.ms" "$run/out/hashes-cmd.json"
step oracle-flag "$py" "$code/oracle.py" flag "$run/pristine.ms" "$run/strategy.yaml" "$run/out/oracle-flag.npz"
step compare-flag "$py" "$code/compare.py" flag "$run/pristine.ms" "$run/cmd.ms" \
  "$run/out/oracle-flag.npz" "$run/out/hashes-pristine.json" "$run/out/hashes-cmd.json"
# Criterion 3: the complex solve on the flagged copy, against rang's store.
step oracle-calibrate "$py" "$code/oracle.py" calibrate "$run/cmd.ms" J1939-6342 int 16 "$run/out/oracle-complex.qc"
step compare-store "$py" "$code/compare.py" store "$run/cmd.ms.rang-run/calibrate/complex.qc" "$run/out/oracle-complex.qc"

# Criterion 2, seeded input flags.
copy seeded-pristine.ms
step seed "$py" "$code/oracle.py" seed "$run/seeded-pristine.ms" 20261106
cp -r "$run/seeded-pristine.ms" "$run/seeded.ms"
step hashes-seeded-pristine "$py" "$code/oracle.py" hashes "$run/seeded-pristine.ms" "$run/out/hashes-seeded-pristine.json"
step seeded-flag "${cli[@]}" flag "$run/good.yaml" "$run/seeded.ms"
step hashes-seeded "$py" "$code/oracle.py" hashes "$run/seeded.ms" "$run/out/hashes-seeded.json"
step oracle-seeded-flag "$py" "$code/oracle.py" flag "$run/seeded-pristine.ms" "$run/strategy.yaml" "$run/out/oracle-seeded-flag.npz"
step compare-seeded-flag "$py" "$code/compare.py" flag "$run/seeded-pristine.ms" "$run/seeded.ms" \
  "$run/out/oracle-seeded-flag.npz" "$run/out/hashes-seeded-pristine.json" "$run/out/hashes-seeded.json"

# Criterion 4: resume after a forced failure (a gemclean path that does not exist).
copy resume.ms
step run-bad "${cli[@]}" run "$run/bad.yaml" "$run/resume.ms"
cp "$run/resume.ms.rang-run/state.json" "$run/out/state-after-bad.json"
step hashes-resume-bad "$py" "$code/oracle.py" hashes "$run/resume.ms" "$run/out/hashes-resume-bad.json"
cp "$run/resume.ms.flagversions/FLAG_VERSION_LIST" "$run/out/versions-after-bad.txt"
(cd "$run/resume.ms.rang-run/calibrate" && find . -type f | sort | xargs sha256sum) > "$run/out/store-after-bad.txt"
step run-good "${cli[@]}" run "$run/good.yaml" "$run/resume.ms"
cp "$run/resume.ms.rang-run/state.json" "$run/out/state-after-good.json"
step hashes-resume-good "$py" "$code/oracle.py" hashes "$run/resume.ms" "$run/out/hashes-resume-good.json"
cp "$run/resume.ms.flagversions/FLAG_VERSION_LIST" "$run/out/versions-after-good.txt"
(cd "$run/resume.ms.rang-run/calibrate" && find . -type f | sort | xargs sha256sum) > "$run/out/store-after-good.txt"
step run-again "${cli[@]}" run "$run/good.yaml" "$run/resume.ms"
sed 's/niter: 2000/niter: 1000/' "$run/good.yaml" > "$run/changed.yaml"
sed -i 's/freqint: 16/freqint: 8/' "$run/changed.yaml"
step run-changed-refused "${cli[@]}" run "$run/changed.yaml" "$run/resume.ms"
step compare-resume "$py" "$code/compare.py" resume "$run/out"
# Criterion 1: exit statuses (0 ran or skipped, 1 failed, 2 refused).
for f in "$run"/timing/*.txt; do printf '%s %s\n' "$(basename "$f" .txt)" "$(tail -1 "$f")"; done > "$run/out/steps.txt"
echo "done: $run"
