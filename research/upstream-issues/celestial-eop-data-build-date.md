Target: https://github.com/gaker/celestial-eop-data/issues
Status: ready to post
Reproduced on: celestial-eop-data 0.1.12 (crates.io, the version casacure 3.8.41 locks), built natively on Windows 11 with Rust 1.93.1 MSVC on 2026-10-30; build.rs read at b7678d9 (main, v0.1.33) on 2026-11-12, unchanged
Duplicates checked: gaker/celestial-eop-data has no issues or PRs; gaker/celestial issues searched for "date"; none
Title: build.rs runs `date -u`: the build panics on Windows without a POSIX `date`, and data_timestamp() is the build date

---

`build.rs` gets its timestamp from an external `date` command (`build.rs:36-41` at b7678d9):

```rust
fn chrono_free_utc_date() -> String {
    let output = std::process::Command::new("date")
        .args(["-u", "+%Y-%m-%d"])
        .output()
        .expect("failed to run `date`");
    ...
}
```

1. **Windows.** With no POSIX `date` on `PATH` (a plain MSVC toolchain), the build script panics with ``failed to run `date` ``, so every crate that depends on this one fails to build. We hit this building casacure 3.8.x natively on Windows (Rust 1.93.1 MSVC, celestial-eop-data 0.1.12). With Git for Windows' `usr\bin` on `PATH` it builds in 13 s.
2. **Reproducibility.** The value is the day of the build, written to `eop_timestamp.txt` and returned by `data_timestamp()` (`src/lib.rs:30-32`). Two builds of the same source on different days differ, and the "data timestamp" says when the crate was compiled, not how recent the bundled IERS series is.

Suggested fix: derive the timestamp from the data (the last MJD in `finals2000A.all` or `eopc04.1962-now`, which `build.rs` already parses), or honour `SOURCE_DATE_EPOCH`. Either removes the external command.

crates.io has 0.1.12 (2026-05-15) as the newest release, while the repository tags go up to v0.1.33. Is publishing to crates.io paused?
