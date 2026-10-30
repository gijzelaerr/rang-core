/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clean

/-! Axiom audit: every theorem of `RangFormal.Clean` should rest on the three
standard axioms only (`propext`, `Classical.choice`, `Quot.sound`); `lake build`
prints the list. -/

#print axioms Clean.misfit_step
#print axioms Clean.misfit_step_le
#print axioms Clean.sum_peak_sq_le
#print axioms Clean.peak_tendsto_zero
#print axioms Clean.dirty_tendsto_zero
#print axioms Clean.misfit_geometric
#print axioms Clean.greedy_pick_in_support
