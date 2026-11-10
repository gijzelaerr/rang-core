#!/usr/bin/env bash
# build_linux.sh COMMIT TAR : the Linux builds of research/g8-wheel.md (section 2), in WSL, under
# tools/heavy_lock.py. TAR is `git archive COMMIT` made on Windows (a Windows worktree's .git does
# not resolve from WSL); it is unpacked into ~/Build/tmp/20261110-g8-src and committed there, so
# tools/wheel/build.sh (which asks git) runs on it unchanged.
#   SBL: cargo +1.93 build --profile gemclean --bin gemclean (x86-64-v3 from .cargo/config.toml),
#        target dir ~/Build/tmp/20261110-g8-target, copied to $OUT/bin/gemclean-sbl-COMMIT.
#   WHL: tools/wheel/build.sh (manylinux_2_28 container, pinned image, rustc 1.93.1, maturin 1.16.0,
#        target-cpu=x86-64), out dir ~/Build/tmp/20261110-g8-whl, wheel copied to $OUT/wheels/WHL;
#        then a fresh uv venv (Python 3.14) with it at ~/Build/tmp/20261110-g8-venv-whl.
# Build walls (inside the lock) in $OUT/wheels/WHL/linux-builds.tsv.
set -euo pipefail
commit=$1
tar=$2
OUT=/mnt/d/rang/outputs/g8-20261110-01
S=$HOME/Build/tmp/20261110-g8-src
T=$HOME/Build/tmp/20261110-g8-target
WO=$HOME/Build/tmp/20261110-g8-whl
V=$HOME/Build/tmp/20261110-g8-venv-whl
rm -rf "$S" "$WO" "$V"
mkdir -p "$S" "$T" "$OUT/bin" "$OUT/wheels/WHL"
tar -x -C "$S" -f "$tar"
(cd "$S" && git init -q && git add -A && git -c user.name=g8 -c user.email=g8@localhost commit -qm "archive of $commit")
source "$HOME/.cargo/env"
log=$OUT/wheels/WHL/linux-builds.tsv
s=$(date +%s.%N)
(cd "$S/core" && CARGO_TARGET_DIR=$T cargo +1.93 build --profile gemclean --bin gemclean)
e=$(date +%s.%N)
printf 'SBL\t%.1f\n' "$(python3 -c "print($e - $s)")" >> "$log"
cp "$T/gemclean/gemclean" "$OUT/bin/gemclean-sbl-$commit"
echo "$commit $(sha256sum "$OUT/bin/gemclean-sbl-$commit")" | tee "$OUT/bin/gemclean-sbl-$commit.provenance"
s=$(date +%s.%N)
(cd "$S" && bash tools/wheel/build.sh "$WO" x86_64)
e=$(date +%s.%N)
printf 'WHL\t%.1f\n' "$(python3 -c "print($e - $s)")" >> "$log"
cp "$WO"/dist/*.whl "$WO/timings.tsv" "$WO/sha256.txt" "$WO/auditwheel-show.txt" "$OUT/wheels/WHL/"
cp "$WO"/repaired/*.whl "$OUT/wheels/WHL/" 2>/dev/null || true
whl=$(ls "$WO"/dist/*.whl | head -1)
uv venv -q -p 3.14 "$V"
uv pip install -q --python "$V/bin/python" "$whl"
echo "$commit $(sha256sum "$whl")" | tee "$OUT/wheels/WHL/provenance.txt"
"$V/bin/gemclean" -version
