/-
Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
License, version 3 or (at your option) any later version; see `LICENSE`.
-/
import RangFormal.Clean
import RangFormal.FiniteDim
import RangFormal.Projection
import RangFormal.Stagewise
import RangFormal.Separation
import RangFormal.Clark

/-! Axiom audit: every theorem of `RangFormal` should rest on the three
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
#print axioms Clean.misfit_add_eq
#print axioms Clean.misfit_add_ge
#print axioms Clean.misfit_add_single
#print axioms Clean.misfit_stagewise_step
#print axioms Clean.l1_stagewise_step
#print axioms Clean.stagewise_pick_optimal
#print axioms Clean.step_eq_stagewise
#print axioms Clean.l1_step_sub
#print axioms Clean.l1_iterate_le_arc
#print axioms Clean.subgradient_monotone
#print axioms Clean.flow_residual_unique
#print axioms Clean.l1_le_of_offdiag_le
#print axioms Clean.colsum_le_of_separated
#print axioms Clean.erc_lt_one_of_separated
#print axioms Clean.exists_erc_solution
#print axioms Clean.pick_in_support_of_erc
#print axioms Clean.clark_descends_iff
#print axioms Clean.truncation_error_le
#print axioms Clean.dirty_add
#print axioms Clean.clark_rule_descends
#print axioms Clean.clark_minor_cycle_descends
