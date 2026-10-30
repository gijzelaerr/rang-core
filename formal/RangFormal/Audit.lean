/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clean
import RangFormal.FiniteDim
import RangFormal.Projection

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
#print axioms Clean.exists_energy_bound
#print axioms Clean.exists_pixel_bound
#print axioms Clean.misfit_geometric_of_mem_visible
#print axioms Clean.misfit_tendsto_zero_of_mem_visible
#print axioms Clean.misfit_geometric_general
#print axioms Clean.iterate_tendsto
