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
import RangFormal.MajorCycle
import RangFormal.Gemclean
import RangFormal.Gridder
import RangFormal.StopRule

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
#print axioms Clean.misfit_add_batch
#print axioms Clean.half_double_sum
#print axioms Clean.misfit_batch_gap
#print axioms Clean.descent_of_gap
#print axioms Clean.misfit_batch_descent
#print axioms Clean.gapForm_le
#print axioms Clean.misfit_batch_descent_of_bound
#print axioms Clean.predicted_le_first
#print axioms Clean.major_linear_rate
#print axioms Clean.major_linear_rate_of_gap
#print axioms Clean.truncation_error_le_pixel
#print axioms Clean.clark_minor_cycle_descends_pixel
#print axioms Clean.exact_value_identity
#print axioms Clean.exact_value_step
#print axioms Clean.certificate_bound
#print axioms Clean.weak_greedy_of_certificate
#print axioms Clean.degrid_eq_sum
#print axioms Clean.grid_apply
#print axioms Clean.grid_eq_dirty
#print axioms Clean.grid_degrid_eq_gram
#print axioms Clean.grid_degrid_symm
#print axioms Clean.gram_quadratic_nonneg
#print axioms Clean.dirty_update
#print axioms Clean.misfit_add_single_general
#print axioms Clean.misfit_step_general
#print axioms Clean.residual_perturbation
#print axioms Clean.dirty_perturbation
#print axioms Clean.misfit_perturbation
#print axioms Clean.gram_residual_bound
#print axioms Clean.gram_quadratic_bound
#print axioms Clean.working_step_descends
#print axioms Clean.operator_step_descends
#print axioms Clean.gram_eq_node_sum
#print axioms Clean.gram_node_sum_error
#print axioms Clean.sub_cast_injective
#print axioms Clean.exists_embedding
#print axioms Clean.dft_circConv
#print axioms Clean.invDFT_product
#print axioms Clean.embedded_convolution
#print axioms Clean.pick_same_sign
#print axioms Clean.pick_lower
#print axioms Clean.pick_fraction
#print axioms Clean.pick_above_level
#print axioms Clean.pick_level
#print axioms Clean.certified_pick
#print axioms Clean.stale_error_le_envelope
#print axioms Clean.certified_step
#print axioms Clean.certified_cycle_energy
#print axioms Clean.sum_abs_le_energy
#print axioms Clean.certified_cycle_flux
#print axioms Clean.pixel_flux_le
#print axioms Clean.no_flux_of_below
#print axioms Clean.stop_peak_le
#print axioms Clean.peak_contraction
#print axioms Clean.peak_geometric
#print axioms Clean.measured_le_column_sup
#print axioms Clean.stale_of_columns_le
#print axioms Clean.measured_not_a_bound
#print axioms Clean.abs_cos_add_sub_le
#print axioms Clean.phi_lipschitz
#print axioms Clean.phi_moment_bound
#print axioms Clean.certified_stop_rule
