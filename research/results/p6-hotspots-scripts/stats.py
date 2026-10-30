import pstats, sys
names = ("generate_candidates", "cond", "inv", "train_signal_guard", "train_signal_guard_p6",
         "corrected_intensity", "inverse_tangent", "_evaluate", "run", "_run", "anchored_response",
         "training_normals", "_per_run", "core_solve", "balanced_rank", "svd", "_correct")
for path in sys.argv[1:]:
    st = pstats.Stats(path)
    print(f"## {path}: total {st.total_tt:.2f} s")
    rows = []
    for (f, line, name), (cc, nc, tt, ct, _) in st.stats.items():
        if name in names or "nonzero" in name or "sha256" in name:
            rows.append((ct, nc, tt, f"{f.split('/')[-1]}:{line}:{name}"))
    for ct, nc, tt, key in sorted(rows, reverse=True)[:22]:
        print(f"{key}\tcalls={nc}\ttottime={tt:.2f}\tcumtime={ct:.2f}")
