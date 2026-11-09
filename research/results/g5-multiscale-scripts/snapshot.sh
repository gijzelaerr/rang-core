#!/usr/bin/env bash
# snapshot.sh DIR : the .code/ snapshot of an output directory: the worktree's HEAD as a tree,
# its uncommitted diff and the commit it was taken at.
set -eu
W=$HOME/Worktrees/rang/fp-g5-multiscale
d=$1/.code
mkdir -p "$d"
git -C "$W" archive HEAD | tar -x -C "$d"
git -C "$W" diff HEAD > "$d/uncommitted.diff"
echo "$(git -C "$W" rev-parse HEAD) $(date -Iseconds)" > "$d/COMMIT"
echo "snapshot $d at $(cat "$d/COMMIT")"
