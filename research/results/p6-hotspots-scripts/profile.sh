#!/bin/bash
# usage: profile.sh <outdir> <label>  (env RANG_P6 passed through; trend uses
# core_trend.run when label starts with "new")
set -u
export PATH=$HOME/.cargo/bin:$PATH RUSTUP_TOOLCHAIN=1.93
cd ~/Worktrees/rang/p6-hotspots
out=$1; label=$2
mkdir -p "$out"
py=.venv/bin/python
if [[ $label == new* ]]; then trendmod=core_trend; else trendmod=flagging_trend; fi
$py -m cProfile -o "$out/$label-trend.prof" -c "import sys; from rangtoy.$trendmod import run; run(sys.argv[1], sys.argv[2])" "$out/$label-trend" outputs/core-trend-mirror-20261029-01 > "$out/$label-trend.log" 2>&1
echo "trend rc=$?" >> "$out/profile-$label.txt"
$py -m cProfile -o "$out/$label-signal.prof" -m rangtoy.core_cli signal "$out/$label-signal" outputs/tv-next-wsl-20261029-01/inputs outputs/core-phase3c-b-uvw-20261029-01 > "$out/$label-signal.log" 2>&1
echo "signal rc=$?" >> "$out/profile-$label.txt"
$py - "$out" "$label" >> "$out/profile-$label.txt" 2>&1 <<'EOF'
import pstats, sys
out, label = sys.argv[1:3]
names = ("generate_candidates", "cond", "inv", "train_signal_guard", "train_signal_guard_p6",
         "corrected_intensity", "inverse_tangent", "_evaluate", "run", "_run", "anchored_response",
         "training_normals", "_per_run", "core_solve", "balanced_rank", "sha256", "nonzero")
for stage in ("trend", "signal"):
    st = pstats.Stats(f"{out}/{label}-{stage}.prof")
    print(f"## {stage}: total {st.total_tt:.2f} s")
    rows = []
    for (path, line, name), (cc, nc, tt, ct, _) in st.stats.items():
        if name in names or "nonzero" in name or "sha256" in name:
            rows.append((ct, nc, tt, f"{path.split('/')[-1]}:{line}:{name}"))
    for ct, nc, tt, key in sorted(rows, reverse=True)[:25]:
        print(f"{key}\tcalls={nc}\ttottime={tt:.2f}\tcumtime={ct:.2f}")
EOF
