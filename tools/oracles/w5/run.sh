#!/usr/bin/env bash
# W5: the chain recipe under Stimela (arm S) against the four rang-core
# commands by hand (arm H), cases A and O (research/w5-stimela.md).
# Usage: bash tools/oracles/w5/run.sh /mnt/d/rang/outputs/w5-20261106-NN
# Needs .venv313 (Python 3.13, -e .[recipes,casacure,imaging]) and
# core/target/release/gemclean. CPU-light; not a timing run.
set -uo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
venv="$root/.venv313"
export PATH="$venv/bin:$PATH"
run=$(realpath -m "$1")
strategy=${STRATEGY:-$HOME/Github/rang/outputs/caracal-strategy-inputs-8f7bb363/mk_rfi_flagging_calibrator_fields_firstpass.yaml}
src_A=/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms
src_O=$HOME/Github/rang/outputs/o-casa-20261030-01/work.ms
if [ -e "$run" ]; then echo "$run exists; choose a fresh run directory" >&2; exit 1; fi
mkdir -p "$run/timing" "$run/logs" "$run/out" "$run/bin" "$run/.code"
git -C "$root" rev-parse HEAD > "$run/.code/head.txt"
git -C "$root" diff HEAD > "$run/.code/diff.patch"
(cd "$root" && git ls-files --others --exclude-standard | tar czf "$run/.code/untracked.tgz" -T -)
cp "$root/core/target/release/gemclean" "$run/bin/gemclean"
cp "$strategy" "$run/strategy.yaml"
(cd "$run" && sha256sum bin/gemclean strategy.yaml > "$run/out/inputs.sha256")
{ command -v rang-core stimela; python -c "import sys, importlib.metadata as m; print(sys.version.split()[0], 'stimela', m.version('stimela'))"; } > "$run/out/environment.txt"

step() {  # a timed step; records the exit status, never stops the run
  local name=$1; shift
  echo "## $name"
  /usr/bin/time -f "%e %M %x" -o "$run/timing/$name.txt" "$@" > "$run/logs/$name.log" 2>&1
  local code; code=$(tail -1 "$run/timing/$name.txt" | awk '{print $3}')
  echo "   exit $code"
  return "$code"
}

cat > "$run/A.yaml" <<EOF
schema: rang-config
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], target: [SIM-TARGET]}
data: {weights: as_is}
flag: {strategy: strategy.yaml}
calibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: m000
  uvrange: ">150"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}
      - {type: A, name: A}
  secondary:
    terms:
      - {type: G, name: Gsec, solint: 60s, preapply: [K, B], interp: [linear, linear]}
      - {type: A, name: Asec}
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
apply:
  targets:
    - {field: [fcal], tables: [K, G, B]}
    - {field: [gcal, target], tables: [K, F, B],
       gainfield: [J1939-6342, nearest, J1939-6342]}
image:
  gemclean: $run/bin/gemclean
  fields: [target]
  size: [512, 512]
  scale: 2asec
  niter: 2000
  threads: 1
run: {stages: [flag, calibrate, apply, image]}
EOF

cat > "$run/O.yaml" <<EOF
schema: rang-config
version: 1
fields: {fcal: [1]}
flag: {strategy: strategy.yaml}
calibrate:
  model: {source: column}
  refant: m000
  minblperant: 3
  primary:
    terms:
      - {type: K, name: K0, solint: inf}
      - {type: G, name: G0, solint: inf, preapply: [K0], interp: [linear]}
      - {type: B, name: B0, solint: inf, combine: scan, fillgaps: 70, preapply: [K0, G0],
         interp: [linear, linear]}
      - {type: A, name: A0}
      - {type: K, name: K1, solint: int, preapply: [G0, B0], interp: [linear, linear]}
      - {type: G, name: G1, solint: int, preapply: [K1, B0], interp: [linear, linear]}
      - {type: B, name: B1, solint: inf, combine: scan, fillgaps: 70, preapply: [K1, G1],
         interp: [linear, linear]}
apply:
  targets:
    - {field: [1], tables: [K1, G1, B1]}
image:
  gemclean: $run/bin/gemclean
  fields: [fcal]
  size: [256, 256]
  scale: 10asec
  niter: 500
  threads: 1
run: {stages: [flag, calibrate, apply, image]}
EOF

status=0
# Gate 3: stimela doc on every recipe file (it writes its log into the cwd).
mkdir -p "$run/doc"
for f in "$root"/recipes/*.yaml; do
  (cd "$run/doc" && step "doc-$(basename "$f" .yaml)" stimela doc "$f") || status=1
done
for case in A O; do
  src_var=src_$case; src=${!src_var}; name=$(basename "$src")
  mkdir -p "$run/$case/S" "$run/$case/H"
  cp -r "$src" "$run/$case/S/$name"
  cp -r "$src" "$run/$case/H/$name"
  # The configuration must validate with no refusal before anything runs.
  if ! step "$case-config-check" rang-core --no-receipt config check "$run/$case.yaml" "$run/$case/H/$name"; then
    echo "case $case: configuration refused; nothing run" >&2; status=1; continue
  fi
  (cd "$run/$case/S" && step "$case-S-stimela" stimela -s "opts.log.dir=$run/$case/S/logs" \
      run "$root/recipes/rang-chain.yaml" "config=$run/$case.yaml" "ms=$run/$case/S/$name") || status=1
  for verb in flag calibrate apply image; do
    (cd "$run/$case/H" && step "$case-H-$verb" rang-core "$verb" "$run/$case.yaml" "$run/$case/H/$name") || status=1
  done
  step "$case-compare" python "$root/tools/oracles/w5/compare.py" \
    "$run/$case/S/$name" "$run/$case/H/$name" "$run/out/compare-$case.json" || status=1
  cat "$run/logs/$case-compare.log"
done
for f in "$run"/timing/*.txt; do printf '%s %s\n' "$(basename "$f" .txt)" "$(tail -1 "$f")"; done > "$run/out/steps.txt"
echo "done: $run (status $status)"
exit $status
