//! Small dense symmetric linear algebra for the toy's 16 pointing parameters.
//! No external numerical dependency is needed to reproduce this experiment.

pub type Matrix = Vec<Vec<f64>>;

pub fn zeros(n: usize, m: usize) -> Matrix {
    vec![vec![0.0; m]; n]
}

pub fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

pub fn mv(a: &Matrix, v: &[f64]) -> Vec<f64> {
    a.iter().map(|row| dot(row, v)).collect()
}

/// Jacobi eigensolver. Eigenvectors are columns; eigenvalues are descending.
pub fn eigen(a: &Matrix) -> (Vec<f64>, Matrix) {
    let n = a.len();
    let mut a = a.clone();
    let mut v = zeros(n, n);
    for (i, row) in v.iter_mut().enumerate() {
        row[i] = 1.0;
    }
    let scale = a.iter().flatten().fold(0.0_f64, |s, x| s.max(x.abs()));
    for _ in 0..100 * n * n {
        let mut largest = 0.0;
        let (mut p, mut q) = (0, 0);
        for (i, row) in a.iter().enumerate() {
            for (j, value) in row.iter().enumerate().skip(i + 1) {
                if value.abs() > largest {
                    largest = value.abs();
                    (p, q) = (i, j);
                }
            }
        }
        if largest <= 1e-13 * scale.max(1e-30) {
            break;
        }
        let angle = 0.5 * (2.0 * a[p][q]).atan2(a[q][q] - a[p][p]);
        let (s, c) = angle.sin_cos();
        let (app, aqq, apq) = (a[p][p], a[q][q], a[p][q]);
        for k in 0..n {
            if k != p && k != q {
                let (akp, akq) = (a[k][p], a[k][q]);
                a[k][p] = c * akp - s * akq;
                a[p][k] = a[k][p];
                a[k][q] = s * akp + c * akq;
                a[q][k] = a[k][q];
            }
            let (vkp, vkq) = (v[k][p], v[k][q]);
            v[k][p] = c * vkp - s * vkq;
            v[k][q] = s * vkp + c * vkq;
        }
        a[p][p] = c * c * app - 2.0 * c * s * apq + s * s * aqq;
        a[q][q] = s * s * app + 2.0 * c * s * apq + c * c * aqq;
        a[p][q] = 0.0;
        a[q][p] = 0.0;
    }
    let mut indices: Vec<_> = (0..n).collect();
    indices.sort_by(|&i, &j| a[j][j].total_cmp(&a[i][i]));
    let values = indices.iter().map(|&i| a[i][i]).collect();
    let vectors = v
        .iter()
        .map(|row| indices.iter().map(|&i| row[i]).collect())
        .collect();
    (values, vectors)
}

/// Householder tridiagonalisation plus implicit QL (EISPACK `tred2`/`tql2`,
/// in the public-domain JAMA formulation). Same convention as [`eigen`]:
/// eigenvectors are columns and eigenvalues are descending. Deterministic,
/// O(n³). Returns `None` if an eigenvalue needs more than 30 QL iterations.
pub fn eigen_ql(a: &Matrix) -> Option<(Vec<f64>, Matrix)> {
    let n = a.len();
    if n == 0 {
        return Some((Vec::new(), Vec::new()));
    }
    let mut v = a.clone();
    let mut d = vec![0.0; n];
    let mut e = vec![0.0; n];
    tridiagonalize(&mut v, &mut d, &mut e);
    // Rows of `w` are the columns of `v`, so each QL rotation updates two
    // contiguous rows.
    let mut w: Matrix = (0..n).map(|j| (0..n).map(|i| v[i][j]).collect()).collect();
    ql_implicit(&mut d, &mut e, &mut w)?;
    let mut indices: Vec<_> = (0..n).collect();
    indices.sort_by(|&i, &j| d[j].total_cmp(&d[i]));
    let values = indices.iter().map(|&i| d[i]).collect();
    let vectors = (0..n)
        .map(|row| indices.iter().map(|&i| w[i][row]).collect())
        .collect();
    Some((values, vectors))
}

/// `tred2`: on return `d` is the diagonal, `e[1..]` the subdiagonal and `v`
/// the accumulated orthogonal transformation.
// Index loops follow the EISPACK listing, which keeps the port checkable.
#[allow(clippy::needless_range_loop)]
fn tridiagonalize(v: &mut Matrix, d: &mut [f64], e: &mut [f64]) {
    let n = d.len();
    d.copy_from_slice(&v[n - 1]);
    for i in (1..n).rev() {
        let scale: f64 = d[..i].iter().map(|x| x.abs()).sum();
        let mut h = 0.0;
        if scale == 0.0 {
            e[i] = d[i - 1];
            for j in 0..i {
                d[j] = v[i - 1][j];
                v[i][j] = 0.0;
                v[j][i] = 0.0;
            }
        } else {
            for x in &mut d[..i] {
                *x /= scale;
                h += *x * *x;
            }
            let f = d[i - 1];
            let mut g = h.sqrt();
            if f > 0.0 {
                g = -g;
            }
            e[i] = scale * g;
            h -= f * g;
            d[i - 1] = f - g;
            e[..i].fill(0.0);
            for j in 0..i {
                let f = d[j];
                v[j][i] = f;
                let mut g = e[j] + v[j][j] * f;
                for k in j + 1..i {
                    g += v[k][j] * d[k];
                    e[k] += v[k][j] * f;
                }
                e[j] = g;
            }
            let mut f = 0.0;
            for j in 0..i {
                e[j] /= h;
                f += e[j] * d[j];
            }
            let hh = f / (h + h);
            for j in 0..i {
                e[j] -= hh * d[j];
            }
            for j in 0..i {
                let (f, g) = (d[j], e[j]);
                for k in j..i {
                    v[k][j] -= f * e[k] + g * d[k];
                }
                d[j] = v[i - 1][j];
                v[i][j] = 0.0;
            }
        }
        d[i] = h;
    }
    for i in 0..n - 1 {
        v[n - 1][i] = v[i][i];
        v[i][i] = 1.0;
        let h = d[i + 1];
        if h != 0.0 {
            for k in 0..=i {
                d[k] = v[k][i + 1] / h;
            }
            for j in 0..=i {
                let mut g = 0.0;
                for k in 0..=i {
                    g += v[k][i + 1] * v[k][j];
                }
                for k in 0..=i {
                    v[k][j] -= g * d[k];
                }
            }
        }
        for row in v.iter_mut().take(i + 1) {
            row[i + 1] = 0.0;
        }
    }
    for j in 0..n {
        d[j] = v[n - 1][j];
        v[n - 1][j] = 0.0;
    }
    v[n - 1][n - 1] = 1.0;
    e[0] = 0.0;
}

/// `tql2` on the tridiagonal (`d`, `e`), rotating the rows of `w`.
fn ql_implicit(d: &mut [f64], e: &mut [f64], w: &mut Matrix) -> Option<()> {
    let n = d.len();
    for i in 1..n {
        e[i - 1] = e[i];
    }
    e[n - 1] = 0.0;
    let mut f = 0.0;
    let mut tst1 = 0.0_f64;
    let eps = f64::EPSILON;
    for l in 0..n {
        tst1 = tst1.max(d[l].abs() + e[l].abs());
        let mut m = l;
        while e[m].abs() > eps * tst1 {
            m += 1;
        }
        if m > l {
            let mut iterations = 0;
            loop {
                iterations += 1;
                if iterations > 30 {
                    return None;
                }
                let g = d[l];
                let mut p = (d[l + 1] - g) / (2.0 * e[l]);
                let mut r = p.hypot(1.0);
                if p < 0.0 {
                    r = -r;
                }
                d[l] = e[l] / (p + r);
                d[l + 1] = e[l] * (p + r);
                let dl1 = d[l + 1];
                let h = g - d[l];
                for x in &mut d[l + 2..] {
                    *x -= h;
                }
                f += h;
                p = d[m];
                let (mut c, mut c2, mut c3) = (1.0, 1.0, 1.0);
                let el1 = e[l + 1];
                let (mut s, mut s2) = (0.0, 0.0);
                for i in (l..m).rev() {
                    c3 = c2;
                    c2 = c;
                    s2 = s;
                    let g = c * e[i];
                    let h = c * p;
                    r = p.hypot(e[i]);
                    e[i + 1] = s * r;
                    s = e[i] / r;
                    c = p / r;
                    p = c * d[i] - s * g;
                    d[i + 1] = h + s * (c * g + s * d[i]);
                    let (lower, upper) = w.split_at_mut(i + 1);
                    for (a, b) in lower[i].iter_mut().zip(upper[0].iter_mut()) {
                        let h = *b;
                        *b = s * *a + c * h;
                        *a = c * *a - s * h;
                    }
                }
                p = -s * s2 * c3 * el1 * e[l] / dl1;
                e[l] = s * p;
                d[l] = c * p;
                if e[l].abs() <= eps * tst1 {
                    break;
                }
            }
        }
        d[l] += f;
        e[l] = 0.0;
    }
    Some(())
}

pub fn solve(a: &Matrix, b: &[f64]) -> Vec<f64> {
    let (values, vectors) = eigen(a);
    let cutoff = values.first().copied().unwrap_or(0.0).max(1e-30) * 1e-12;
    let mut x = vec![0.0; b.len()];
    for (k, &value) in values.iter().enumerate() {
        if value > cutoff {
            let projection: f64 = b.iter().enumerate().map(|(i, b)| vectors[i][k] * b).sum();
            for (i, xi) in x.iter_mut().enumerate() {
                *xi += vectors[i][k] * projection / value;
            }
        }
    }
    x
}

#[cfg(test)]
#[allow(clippy::needless_range_loop)]
mod tests {
    use super::*;

    #[test]
    fn eigen_reconstructs_symmetric_matrix() {
        let a = vec![
            vec![4.0, 1.0, -0.5],
            vec![1.0, 2.0, 0.3],
            vec![-0.5, 0.3, 1.0],
        ];
        let (d, v) = eigen(&a);
        for i in 0..3 {
            for j in 0..3 {
                let recovered: f64 = (0..3).map(|k| v[i][k] * d[k] * v[j][k]).sum();
                assert!((recovered - a[i][j]).abs() < 1e-11);
            }
        }
        let b = vec![1.0, 2.0, 3.0];
        let x = solve(&a, &b);
        assert!(mv(&a, &x).iter().zip(b).all(|(x, y)| (x - y).abs() < 1e-10));
    }

    /// Fixed-seed LCG in [-1, 1); no external crate.
    pub(crate) struct Lcg(pub u64);

    impl Lcg {
        pub(crate) fn next(&mut self) -> f64 {
            self.0 = self
                .0
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((self.0 >> 11) as f64 / (1u64 << 53) as f64) * 2.0 - 1.0
        }
    }

    fn random_symmetric(n: usize, rng: &mut Lcg) -> Matrix {
        let mut a = zeros(n, n);
        for i in 0..n {
            for j in 0..=i {
                let x = rng.next();
                a[i][j] = x;
                a[j][i] = x;
            }
        }
        a
    }

    fn random_orthogonal(n: usize, rng: &mut Lcg) -> Matrix {
        let mut q: Matrix = Vec::new();
        while q.len() < n {
            let mut c: Vec<f64> = (0..n).map(|_| rng.next()).collect();
            for _ in 0..2 {
                for p in &q {
                    let s = dot(&c, p);
                    c.iter_mut().zip(p).for_each(|(x, y)| *x -= s * y);
                }
            }
            let norm = dot(&c, &c).sqrt();
            c.iter_mut().for_each(|x| *x /= norm);
            q.push(c);
        }
        q
    }

    /// Q diag(spectrum) Q^T with the rows of `q` as the eigenvectors.
    fn with_spectrum(spectrum: &[f64], rng: &mut Lcg) -> Matrix {
        let n = spectrum.len();
        let q = random_orthogonal(n, rng);
        let mut a = zeros(n, n);
        for i in 0..n {
            for j in 0..n {
                a[i][j] = (0..n).map(|k| q[k][i] * spectrum[k] * q[k][j]).sum();
            }
        }
        for i in 0..n {
            for j in 0..i {
                let m = 0.5 * (a[i][j] + a[j][i]);
                a[i][j] = m;
                a[j][i] = m;
            }
        }
        a
    }

    fn scale_of(a: &Matrix) -> f64 {
        a.iter().flatten().fold(0.0_f64, |s, x| s.max(x.abs()))
    }

    /// Reconstruction, orthogonality, eigenvalues against Jacobi and the
    /// projector onto every cluster of equal eigenvalues (relative gap
    /// `cluster`), which is basis-free where eigenvectors are not unique.
    fn assert_matches_jacobi(a: &Matrix, cluster: f64) {
        let n = a.len();
        let (dq, vq) = eigen_ql(a).expect("QL converges");
        let (dj, vj) = eigen(a);
        let scale = scale_of(a).max(1e-300);
        let top = dj.iter().fold(0.0_f64, |s, x| s.max(x.abs())).max(1e-300);
        for k in 0..n {
            assert!((dq[k] - dj[k]).abs() <= 1e-12 * top, "eigenvalue {k}");
        }
        assert!(dq.windows(2).all(|w| w[0] >= w[1]));
        for i in 0..n {
            for j in 0..n {
                let recovered: f64 = (0..n).map(|k| vq[i][k] * dq[k] * vq[j][k]).sum();
                assert!((recovered - a[i][j]).abs() <= 1e-12 * scale);
                let gram: f64 = (0..n).map(|k| vq[k][i] * vq[k][j]).sum();
                let identity = if i == j { 1.0 } else { 0.0 };
                assert!((gram - identity).abs() <= 1e-12);
            }
        }
        let mut start = 0;
        while start < n {
            let mut end = start + 1;
            while end < n && (dj[end - 1] - dj[end]).abs() <= cluster * top {
                end += 1;
            }
            for i in 0..n {
                for j in 0..n {
                    let pq: f64 = (start..end).map(|k| vq[i][k] * vq[j][k]).sum();
                    let pj: f64 = (start..end).map(|k| vj[i][k] * vj[j][k]).sum();
                    assert!((pq - pj).abs() <= 1e-9, "cluster {start}..{end}");
                }
            }
            start = end;
        }
    }

    #[test]
    fn ql_matches_jacobi_on_random_symmetric_matrices() {
        let mut rng = Lcg(20261030);
        for n in 1..=32 {
            for _ in 0..3 {
                assert_matches_jacobi(&random_symmetric(n, &mut rng), 1e-9);
            }
        }
    }

    #[test]
    fn ql_matches_jacobi_on_degenerate_spectra() {
        let mut rng = Lcg(7);
        // Exactly four zero eigenvalues (the projected gauge directions).
        let mut gauge: Vec<f64> = (0..28).map(|k| 1.0 + k as f64 * 0.37).collect();
        gauge.extend([0.0; 4]);
        assert_matches_jacobi(&with_spectrum(&gauge, &mut rng), 1e-9);
        // Repeated eigenvalues in blocks, and a 1e-12 cluster.
        let repeated: Vec<f64> = (0..32).map(|k| [5.0, 2.0, -1.0, 0.5][k % 4]).collect();
        assert_matches_jacobi(&with_spectrum(&repeated, &mut rng), 1e-9);
        let tiny: Vec<f64> = (0..32)
            .map(|k| {
                if k < 24 {
                    1.0 + k as f64
                } else {
                    1e-12 * (1.0 + k as f64)
                }
            })
            .collect();
        assert_matches_jacobi(&with_spectrum(&tiny, &mut rng), 1e-9);
        // Diagonal, already tridiagonal, identity and zero matrices.
        let mut diagonal = zeros(32, 32);
        let mut tridiagonal = zeros(32, 32);
        for i in 0..32 {
            diagonal[i][i] = ((i * 7) % 11) as f64 - 3.0;
            tridiagonal[i][i] = 2.0;
            if i > 0 {
                tridiagonal[i][i - 1] = -1.0;
                tridiagonal[i - 1][i] = -1.0;
            }
        }
        assert_matches_jacobi(&diagonal, 1e-9);
        assert_matches_jacobi(&tridiagonal, 1e-9);
        let mut identity = zeros(32, 32);
        identity
            .iter_mut()
            .enumerate()
            .for_each(|(i, r)| r[i] = 1.0);
        assert_matches_jacobi(&identity, 1e-9);
        let (d, v) = eigen_ql(&zeros(32, 32)).unwrap();
        assert!(d.iter().all(|x| *x == 0.0));
        assert!((0..32).all(|i| v[i][i].abs() == 1.0));
        assert!(eigen_ql(&Vec::new()).unwrap().0.is_empty());
    }

    #[test]
    fn ql_is_deterministic() {
        let a = random_symmetric(32, &mut Lcg(3));
        let first = eigen_ql(&a).unwrap();
        let second = eigen_ql(&a).unwrap();
        assert!(
            first
                .0
                .iter()
                .zip(&second.0)
                .all(|(x, y)| x.to_bits() == y.to_bits())
        );
        assert!(
            first
                .1
                .iter()
                .flatten()
                .zip(second.1.iter().flatten())
                .all(|(x, y)| x.to_bits() == y.to_bits())
        );
    }
}
