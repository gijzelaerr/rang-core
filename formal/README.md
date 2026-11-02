# Formal proofs (Lean 4 + Mathlib)

Machine-checked statements behind research notes. Started 2026-10-30 with
the CLEAN convergence core of [research/clean-theory.md](../research/clean-theory.md).

| File | Content |
| --- | --- |
| `RangFormal/Clean.lean` | Högbom CLEAN as greedy coordinate descent in a real inner-product space: the one-step misfit identity (Theorem 1), descent for `0 < γ < 2`, square-summability of the picked peaks and their convergence to zero (Theorem 2, for any pick rule, then for `τ`-weak greedy rules at every pixel), the geometric rate under a greedy-ratio bound (Theorem 3), and the coherence condition under which the argmax stays on a sparse support (Theorem 4). |
| `RangFormal/FiniteDim.lean` | The compactness step: a positive greedy constant on the finite-dimensional span of the atoms, and the geometric rate `Q_K ≤ ρ^K Q_0` for data in that span under any `τ`-weak greedy rule. |
| `RangFormal/Projection.lean` | The projection step: the CLEAN sequence ignores the data component orthogonal to the atoms, the misfit floor `Q_∞`, the geometric rate `Q_K − Q_∞ ≤ ρ^K (Q_0 − Q_∞)` for arbitrary data, and convergence of the model. |
| `RangFormal/Stagewise.lean` | CLEAN as forward stagewise regression ([research/clean-implicit-objective.md](../research/clean-implicit-objective.md)): the exact misfit after any move, ℓ1 steepest descent (`Q(m + d) ≥ Q(m) − max|r| ‖d‖₁`), the signed stagewise step and its misfit change `−ε|r_p| + ε²/2`, optimality of the argmax pick among all single-coordinate steps of the same size, a CLEAN step as a stagewise step of length `|γ||r_p|`, ℓ1 norm bounded by arc length, monotonicity of the ℓ∞ subdifferential, and uniqueness in data space of right-differentiable small-gain limit curves (`flow_residual_unique`). |
| `RangFormal/Separation.lean` | Proposition 4' of `clean-theory.md`: the ℓ1 Neumann-series bound, the off-support column bound for sources at least `d` apart, the exact recovery coefficient below one, invertibility of `B_SS`, and the argmax staying on the support. |
| `RangFormal/Clark.lean` | Theorem 6 of `clean-theory.md`: the descent condition `r_p / r̃_p > γ/2` for a step taken on a working residual, the truncation-error bound `f Σ|c_k|`, and the provable minor-cycle rule end to end. |
| `RangFormal/MajorCycle.lean` | Major cycles as inexact Newton ([research/clean-major-cycles.md](../research/clean-major-cycles.md)): the exact misfit change of a batch, the Gram-gap identity for any beam and pick order, per-cycle descent, the running gap bound and the provable per-cycle rule, the forcing term of a greedy cycle, the outer linear rate over major cycles, and Theorem 6 with a per-component bound. |
| `RangFormal/Gmclean.lean` | The arithmetic of a gmclean minor step ([research/gmclean.md](../research/gmclean.md)): the exact value from the working value through the ignored beam, a step with the exact value is a CLEAN step at any proposed pixel, and the recorded certificate `|r_p| ≥ τ (M + e)` makes the pick `τ`-weak greedy. |
| `RangFormal/Gridder.lean` | What the gridder's arithmetic licenses ([research/gridder-theory.md](../research/gridder-theory.md)): exact adjoints make the beam the Gram matrix of the approximate atoms, with the visibility-free residual law and the one-step law for atoms of any norm; perturbation bounds on the residual image and the misfit from atom or operator error; descent of a step on an approximate residual when `(1 − γ/2) |r̃_p| > η ‖m‖₁`; the finite-sum w-node identity and its error `ε Σ|W_p|`; the Toeplitz embedding on `ZMod (2n)` and the convolution theorem from Mathlib's `ZMod.dft`. |
| `RangFormal/Audit.lean` | `#print axioms` for every theorem; all 73 rest on `propext`, `Classical.choice` and `Quot.sound` only. |

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
takes 41-44 s, almost all of it loading Mathlib (121 s for a clean rebuild of
all seven files on 2026-10-30, after `Stagewise`, `Separation` and `Clark`
were added; `MajorCycle` makes eight). `.lake/` is ignored by
Git. The axiom audit prints as `info` lines of the build.
