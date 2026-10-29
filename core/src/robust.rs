//! Per-baseline robust log-amplitude scores, matching
//! `rangtoy.flagging.residual_features`.

/// NumPy-compatible median: the mean of the two middle values for even counts.
pub fn median(values: &mut [f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let n = values.len();
    Some(if n % 2 == 1 {
        values[n / 2]
    } else {
        0.5 * (values[n / 2 - 1] + values[n / 2])
    })
}

/// Scores for one baseline's eligible log amplitudes, in input order.
/// Location is the median; scale is max(1.4826 MAD, 0.05); scores are clipped
/// at zero, so only positive outliers count.
pub fn scores(log_amplitude: &[f64]) -> Vec<f64> {
    let mut buffer = log_amplitude.to_vec();
    let Some(location) = median(&mut buffer) else {
        return Vec::new();
    };
    let mut deviations: Vec<f64> = log_amplitude.iter().map(|x| (x - location).abs()).collect();
    let mad = median(&mut deviations).unwrap_or(0.);
    let scale = (1.4826 * mad).max(0.05);
    log_amplitude
        .iter()
        .map(|x| ((x - location) / scale).max(0.))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn median_matches_numpy_conventions() {
        assert_eq!(median(&mut [3., 1., 2.]), Some(2.));
        assert_eq!(median(&mut [4., 1., 3., 2.]), Some(2.5));
        assert_eq!(median(&mut []), None);
    }

    #[test]
    fn scale_floor_applies() {
        let z = scores(&[0., 0., 0., 1.]);
        assert_eq!(z, vec![0., 0., 0., 20.]);
    }
}
