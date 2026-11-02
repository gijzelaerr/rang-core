//! Wall time, process CPU time and whole-machine load of a timed interval,
//! so a timing can be judged afterwards on a shared host.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Linux reads `/proc/self/stat` and `/proc/stat` (clock ticks taken as 100
//! per second, the Linux ABI value); Windows calls `GetProcessTimes` and
//! `GetSystemTimes` (which also see a WSL guest's work, as the hardware is
//! shared). Elsewhere the CPU fields are absent.

use std::time::Instant;

/// Seconds of CPU since some origin.
#[derive(Clone, Copy, Debug)]
struct Cpu {
    process: f64,
    system_busy: f64,
    system_total: f64,
}

#[cfg(target_os = "linux")]
fn cpu_now() -> Option<Cpu> {
    const TICK: f64 = 0.01;
    let stat = std::fs::read_to_string("/proc/self/stat").ok()?;
    let fields: Vec<&str> = stat[stat.rfind(')')? + 1..].split_whitespace().collect();
    // After the command come state (field 3) .. utime (14), stime (15).
    let utime: f64 = fields.get(11)?.parse().ok()?;
    let stime: f64 = fields.get(12)?.parse().ok()?;
    let all = std::fs::read_to_string("/proc/stat").ok()?;
    let line = all.lines().next()?;
    let v: Vec<f64> = line
        .split_whitespace()
        .skip(1)
        .take(8)
        .filter_map(|x| x.parse().ok())
        .collect();
    let total: f64 = v.iter().sum();
    let idle = v.get(3)? + v.get(4)?;
    Some(Cpu {
        process: (utime + stime) * TICK,
        system_busy: (total - idle) * TICK,
        system_total: total * TICK,
    })
}

#[cfg(windows)]
fn cpu_now() -> Option<Cpu> {
    use std::ffi::c_void;
    #[repr(C)]
    #[derive(Clone, Copy, Default)]
    struct FileTime {
        low: u32,
        high: u32,
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetCurrentProcess() -> *mut c_void;
        fn GetProcessTimes(
            process: *mut c_void,
            creation: *mut FileTime,
            exit: *mut FileTime,
            kernel: *mut FileTime,
            user: *mut FileTime,
        ) -> i32;
        fn GetSystemTimes(idle: *mut FileTime, kernel: *mut FileTime, user: *mut FileTime) -> i32;
    }
    let seconds = |t: FileTime| ((u64::from(t.high) << 32) | u64::from(t.low)) as f64 * 1e-7;
    let (mut a, mut b, mut k, mut u) = (
        FileTime::default(),
        FileTime::default(),
        FileTime::default(),
        FileTime::default(),
    );
    let (mut si, mut sk, mut su) = (
        FileTime::default(),
        FileTime::default(),
        FileTime::default(),
    );
    // SAFETY: every pointer is to a live local `FileTime`, the layout of
    // Windows' FILETIME; the pseudo-handle needs no closing.
    let ok = unsafe {
        GetProcessTimes(GetCurrentProcess(), &mut a, &mut b, &mut k, &mut u) != 0
            && GetSystemTimes(&mut si, &mut sk, &mut su) != 0
    };
    // The system kernel time includes the idle time.
    ok.then(|| Cpu {
        process: seconds(k) + seconds(u),
        system_busy: seconds(sk) + seconds(su) - seconds(si),
        system_total: seconds(sk) + seconds(su),
    })
}

#[cfg(not(any(target_os = "linux", windows)))]
fn cpu_now() -> Option<Cpu> {
    None
}

/// One timed interval.
#[derive(Clone, Copy, Debug)]
pub struct Measured {
    pub wall: f64,
    /// CPU seconds of this process, all threads.
    pub cpu: Option<f64>,
    /// Busy logical CPUs of the whole machine, this process included.
    pub load: Option<f64>,
}

/// A running measurement: `Probe::start()`, then [`Probe::stop`].
pub struct Probe {
    wall: Instant,
    cpu: Option<Cpu>,
}

impl Probe {
    pub fn start() -> Probe {
        Probe {
            wall: Instant::now(),
            cpu: cpu_now(),
        }
    }

    pub fn stop(&self) -> Measured {
        let wall = self.wall.elapsed().as_secs_f64();
        let cores = std::thread::available_parallelism().map_or(1, |n| n.get()) as f64;
        let (cpu, load) = match (self.cpu, cpu_now()) {
            (Some(a), Some(b)) => {
                let total = b.system_total - a.system_total;
                let load = (total > 0.0).then(|| cores * (b.system_busy - a.system_busy) / total);
                (Some(b.process - a.process), load)
            }
            _ => (None, None),
        };
        Measured { wall, cpu, load }
    }
}

/// `(min, median)` of a sample; the median of an even count is the mean of
/// the middle two. `None` for an empty sample.
pub fn min_median(sample: &[f64]) -> Option<(f64, f64)> {
    if sample.is_empty() {
        return None;
    }
    let mut s = sample.to_vec();
    s.sort_by(f64::total_cmp);
    let mid = s.len() / 2;
    let median = if s.len() % 2 == 1 {
        s[mid]
    } else {
        0.5 * (s[mid - 1] + s[mid])
    };
    Some((s[0], median))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn probe_and_statistics() {
        let p = Probe::start();
        let mut x = 0.0_f64;
        for i in 0..2_000_000 {
            x += (i as f64).sqrt();
        }
        std::hint::black_box(x);
        let m = p.stop();
        assert!(m.wall > 0.0);
        if let Some(c) = m.cpu {
            assert!(c >= 0.0);
        }
        assert_eq!(min_median(&[3.0, 1.0, 2.0]), Some((1.0, 2.0)));
        assert_eq!(min_median(&[4.0, 1.0, 2.0, 3.0]), Some((1.0, 2.5)));
        assert_eq!(min_median(&[]), None);
    }
}
