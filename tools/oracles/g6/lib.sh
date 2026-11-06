# Shared helpers of the G6 runs (research/g6-predict.md); source with O and GEM set.
# O: the run directory under /mnt/d/rang/outputs; GEM: the gemclean binary.
HERE=${HERE:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")}
WT=${WT:-$HOME/Worktrees/rang/fp-g6-predict}
D=/mnt/d/rang/outputs
UIDS="$(id -u):$(id -g)"

# python-casacore 3.8.1 (the read-back oracle) on files under $O and $D.
casa_py() {
  docker run --rm --user "$UIDS" --network none -e HOME=/tmp -v "$O:$O" -v "$D:$D:ro" \
    -v "$HERE:/g6:ro" --entrypoint python3 rang-ms-reader:local "$@"
}

# rang's venv.
rang_py() { nice -n 10 "$WT/.venv/bin/python" "$@"; }

# WSClean 3.7 with the paths as on the host ($O writable, $D read-only).
wsc() {
  docker run --rm --user "$UIDS" --network none -e HOME=/tmp -e OMP_NUM_THREADS=${THREADS:-16} \
    -v "$O:$O" -v "$D:$D:ro" -w "$O" rang-wsclean-native:3.7 \
    /usr/bin/time -v -o "$O/time-wsclean-$1.txt" wsclean "${@:2}"
}

# gemclean, with GNU time; $1 a label.
gem() {
  local label=$1; shift
  /usr/bin/time -v -o "$O/time-gemclean-$label.txt" "$GEM" "$@"
}

# Snapshot of the code into $O/.code.
snapshot() {
  mkdir -p "$O/.code"
  cp -r "$HERE" "$O/.code/g6"
  git -C "$WT" rev-parse HEAD > "$O/.code/commit.txt"
  git -C "$WT" status --porcelain > "$O/.code/status.txt"
  git -C "$WT" diff > "$O/.code/diff.patch"
  sha256sum "$GEM" > "$O/.code/gemclean.sha256"
}
