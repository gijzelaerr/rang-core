# Batch 2, the test: sorted and dense residuals agree bit for bit.
root="/home/gijsm/Worktrees/rang/fp-g2-memory/core/src/"
p=root+"gemclean/measure.rs"; s=open(p).read()
old="""    #[test]
    fn f64_path_equals_the_certified_measurement_and_f32_is_close() {"""
assert s.count(old)==1
new='''    /// G2: the residual formed in the gridder's sorted values
    /// ([`Prepared::residual`]) has the bits of the one formed through a
    /// visibility-sized buffer, in both precisions, with single- and
    /// double-precision data, zero weights, the w-term and a shifted centre,
    /// over repeated calls.
    #[test]
    fn sorted_residual_has_the_bits_of_the_dense_one() {
        fn check<T: Real + Send + Sync>(shift: f64) {
            let mut state = 2026u64;
            let mut next = || {
                state ^= state << 13;
                state ^= state >> 7;
                state ^= state << 17;
                (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
            };
            let (nrow, n, cell, eps) = (700, 48usize, 1.5e-4, 1e-6);
            let uvw: Vec<f64> = (0..3 * nrow)
                .map(|i| next() * if i % 3 == 2 { 80.0 } else { 3000.0 })
                .collect();
            let freq = vec![2.7e8, 3.0e8, 3.3e8];
            let cells = nrow * freq.len();
            let single: Vec<Complex<f32>> = (0..cells)
                .map(|_| Complex::new(next() as f32, next() as f32))
                .collect();
            let double: Vec<Complex<f64>> = single
                .iter()
                .map(|v| Complex::new(f64::from(v.re), f64::from(v.im)))
                .collect();
            // About a third of the weights zero, so inactive visibilities are present.
            let wgt: Vec<f64> = (0..cells)
                .map(|_| {
                    let x = next();
                    if x < -0.2 { 0.0 } else { 0.5 + x }
                })
                .collect();
            let opts = Options {
                center_x: shift,
                center_y: -0.5 * shift,
                ..crate::gemclean::sim::imaging_options()
            };
            let make = |v: Vec<Complex<f32>>| {
                GridMeasurement::<T>::from_single(
                    uvw.clone(),
                    freq.clone(),
                    v,
                    wgt.clone(),
                    n,
                    cell,
                    eps,
                    opts,
                )
                .unwrap()
            };
            let sorted = make(single.clone());
            assert!(sorted.sorted_residual);
            let dense = make(single.clone()).with_dense_residual();
            let native = GridMeasurement::<T>::new(
                uvw.clone(),
                freq.clone(),
                double,
                wgt.clone(),
                n,
                cell,
                eps,
                opts,
            )
            .unwrap();
            assert!(native.sorted_residual);
            let mut model = vec![0.0; n * n];
            let bits = |x: &[f64]| x.iter().map(|v| v.to_bits()).collect::<Vec<_>>();
            for round in 0..3 {
                if round > 0 {
                    model[(7 * round) * n + 11 + round] += 0.8;
                    model[30 * n + 40 - round] -= 0.25;
                }
                let (a, qa) = dense.residual(&model).unwrap();
                for m in [&sorted, &native] {
                    let (b, qb) = m.residual(&model).unwrap();
                    assert_eq!(bits(&a), bits(&b), "round {round}");
                    assert_eq!(qa.to_bits(), qb.to_bits(), "round {round}");
                }
            }
            // The other operations still agree after sorted residuals.
            let x: Vec<f64> = (0..n * n).map(|_| next()).collect();
            assert_eq!(
                bits(&dense.gram_apply(&x).unwrap()),
                bits(&sorted.gram_apply(&x).unwrap())
            );
            assert_eq!(
                bits(&dense.psf_image(2 * n).unwrap()),
                bits(&sorted.psf_image(2 * n).unwrap())
            );
        }
        for shift in [0.0, 2e-3] {
            check::<f64>(shift);
            check::<f32>(shift);
        }
    }

'''+old
s=s.replace(old,new)
open(p,"w").write(s)
