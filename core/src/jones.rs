//! Complex 2x2 Jones algebra, row-major XX, XY, YX, YY as in the MS.

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct C64 {
    pub re: f64,
    pub im: f64,
}

impl C64 {
    pub const ZERO: Self = Self { re: 0., im: 0. };

    pub fn new(re: f64, im: f64) -> Self {
        Self { re, im }
    }
    pub fn conj(self) -> Self {
        Self::new(self.re, -self.im)
    }
    pub fn scale(self, s: f64) -> Self {
        Self::new(self.re * s, self.im * s)
    }
    pub fn norm2(self) -> f64 {
        self.re * self.re + self.im * self.im
    }
    pub fn is_finite(self) -> bool {
        self.re.is_finite() && self.im.is_finite()
    }
}

impl std::ops::Add for C64 {
    type Output = Self;
    fn add(self, o: Self) -> Self {
        Self::new(self.re + o.re, self.im + o.im)
    }
}

impl std::ops::Sub for C64 {
    type Output = Self;
    fn sub(self, o: Self) -> Self {
        Self::new(self.re - o.re, self.im - o.im)
    }
}

impl std::ops::Mul for C64 {
    type Output = Self;
    fn mul(self, o: Self) -> Self {
        Self::new(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
}

pub type Jones = [C64; 4];

pub fn from_f64(x: &[f64]) -> Jones {
    std::array::from_fn(|i| C64::new(x[2 * i], x[2 * i + 1]))
}

pub fn from_f32(x: &[f32]) -> Jones {
    std::array::from_fn(|i| C64::new(f64::from(x[2 * i]), f64::from(x[2 * i + 1])))
}

pub fn scalar(s: f64) -> Jones {
    [C64::new(s, 0.), C64::ZERO, C64::ZERO, C64::new(s, 0.)]
}

/// Matrix product a b.
pub fn mul(a: &Jones, b: &Jones) -> Jones {
    std::array::from_fn(|e| {
        let (r, c) = (e / 2, e % 2);
        a[2 * r] * b[c] + a[2 * r + 1] * b[2 + c]
    })
}

/// Conjugate transpose.
pub fn adjoint(a: &Jones) -> Jones {
    std::array::from_fn(|e| a[2 * (e % 2) + e / 2].conj())
}

pub fn is_finite(a: &Jones) -> bool {
    a.iter().all(|x| x.is_finite())
}
