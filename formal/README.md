# Formal proofs (Lean 4 + Mathlib)

Machine-checked statements behind research notes. Started 2026-10-30 with
the CLEAN convergence core of [research/clean-theory.md](../research/clean-theory.md).

| File | Content |
| --- | --- |
| `RangFormal/Clean.lean` | Högbom CLEAN as greedy coordinate descent in a real inner-product space: the one-step misfit identity (Theorem 1), descent for `0 < γ < 2`, square-summability of the picked peaks and their convergence to zero (Theorem 2, for any pick rule, then for `τ`-weak greedy rules at every pixel), the geometric rate under a greedy-ratio bound (Theorem 3), and the coherence condition under which the argmax stays on a sparse support (Theorem 4). |
| `RangFormal/FiniteDim.lean` | The compactness step: a positive greedy constant on the finite-dimensional span of the atoms, and the geometric rate `Q_K ≤ ρ^K Q_0` for data in that span under any `τ`-weak greedy rule. |
| `RangFormal/Projection.lean` | The projection step: the CLEAN sequence ignores the data component orthogonal to the atoms, the misfit floor `Q_∞`, the geometric rate `Q_K − Q_∞ ≤ ρ^K (Q_0 − Q_∞)` for arbitrary data, and convergence of the model. |
| `RangFormal/Audit.lean` | `#print axioms` for every theorem; all thirteen rest on `propext`, `Classical.choice` and `Quot.sound` only. |

## Building

Toolchain `leanprover/lean4:v4.33.1` (`lean-toolchain`), Mathlib tag
`v4.33.1` (`lake-manifest.json`). From this directory:

```bash
lake exe cache get
```

```bash
lake build
```

The first command downloads Mathlib's compiled files (8,690 files; about
4 min 50 s on the Windows workstation, the clone included); the build itself
takes 41-44 s, almost all of it loading Mathlib. `.lake/` is ignored by
Git. The axiom audit prints as `info` lines of the build.
