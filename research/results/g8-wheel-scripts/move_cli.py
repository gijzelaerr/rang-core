"""move_cli.py: the one-off move of core/src/bin/gemclean.rs into rang_core::gemclean::cli
(task G8, research/g8-wheel.md section 1). Run once from the worktree root."""

from pathlib import Path

src = Path("core/src/bin/gemclean.rs")
s = src.read_text(encoding="utf-8")


def sub(old, new, count=1):
    global s
    assert s.count(old) == count, (old, s.count(old))
    s = s.replace(old, new)


sub(
    "//! `gemclean`: a reference CLEAN imager for Measurement Sets with WSClean-like\n"
    "//! flags (`research/gemclean.md`).\n",
    "//! The command line of `gemclean`, a reference CLEAN imager for Measurement\n"
    "//! Sets with WSClean-like flags (`research/gemclean.md`). One code for both\n"
    "//! front ends (task G8, `research/g8-wheel.md`): the source build's binary\n"
    "//! (`src/bin/gemclean.rs`) and the wheel's console script through the\n"
    "//! extension (`rang._core.gemclean_main`).\n",
)
s = s.replace("use rang_core::", "use crate::")
sub(
    '#[cfg(all(target_os = "linux", target_pointer_width = "64"))]\n'
    "#[global_allocator]\n"
    "static ALLOCATOR: rang_core::gemclean::host::HugePageAlloc =\n"
    "    rang_core::gemclean::host::HugePageAlloc;\n",
    "",
)
sub(
    "fn run() -> Result<(), String> {\n"
    "    let wall = Instant::now();\n"
    "    let raw: Vec<String> = std::env::args().skip(1).collect();\n"
    "    let mut args = parse_args(&raw)?;\n",
    "fn run(raw: &[String]) -> Result<(), String> {\n"
    "    let wall = Instant::now();\n"
    '    if raw.iter().any(|a| a == "-version" || a == "--version") {\n'
    '        println!("gemclean {}", env!("CARGO_PKG_VERSION"));\n'
    "        return Ok(());\n"
    "    }\n"
    "    let mut args = parse_args(raw)?;\n",
)
sub(
    "    if let Some(t) = args.threads {\n"
    "        rayon::ThreadPoolBuilder::new()\n"
    "            .num_threads(t)\n"
    "            .build_global()\n"
    "            .map_err(|e| e.to_string())?;\n"
    "    }\n"
    "    if args.predict {\n",
    "    if let Some(t) = args.threads {\n"
    "        let global = rayon::ThreadPoolBuilder::new().num_threads(t).build_global();\n"
    "        if global.is_err() {\n"
    "            // The global pool exists already (a second run in one process,\n"
    "            // through the extension): this run gets a pool of its own.\n"
    "            let pool = rayon::ThreadPoolBuilder::new()\n"
    "                .num_threads(t)\n"
    "                .build()\n"
    "                .map_err(|e| e.to_string())?;\n"
    "            return pool.install(|| run_parsed(args, raw, wall));\n"
    "        }\n"
    "    }\n"
    "    run_parsed(args, raw, wall)\n"
    "}\n"
    "\n"
    "fn run_parsed(args: Args, raw: &[String], wall: Instant) -> Result<(), String> {\n"
    "    if args.predict {\n",
)
sub("predict_only(&args, &raw, wall)", "predict_only(&args, raw, wall)")
sub("run_polarizations(&args, &raw,", "run_polarizations(&args, raw,")
sub("run_channels(&args, &raw,", "run_channels(&args, raw,")
sub(
    "fn main() {\n"
    "    rang_core::wgridder::set_default_plane_group(rang_core::wgridder::PLANE_GROUP);\n"
    "    if let Err(e) = run() {\n"
    '        eprintln!("gemclean: {e}");\n'
    "        std::process::exit(2);\n"
    "    }\n"
    "}\n",
    "/// Run gemclean with `args` (without the program name); returns the exit\n"
    "/// code: 0, or 2 after `gemclean: <error>` on stderr. A panic unwinds out\n"
    "/// of it (the binary then exits with 101). Rust's stdout is flushed.\n"
    "pub fn main(args: &[String]) -> i32 {\n"
    "    crate::wgridder::set_default_plane_group(crate::wgridder::PLANE_GROUP);\n"
    "    let code = match run(args) {\n"
    "        Ok(()) => 0,\n"
    "        Err(e) => {\n"
    '            eprintln!("gemclean: {e}");\n'
    "            2\n"
    "        }\n"
    "    };\n"
    "    let _ = std::io::Write::flush(&mut std::io::stdout());\n"
    "    code\n"
    "}\n",
)
Path("core/src/gemclean/cli.rs").write_text(s, encoding="utf-8", newline="\n")
src.write_text(
    """//! `gemclean`: a reference CLEAN imager for Measurement Sets with WSClean-like
//! flags (`research/gemclean.md`); the source build's front end of
//! [`rang_core::gemclean::cli`] (task G8, `research/g8-wheel.md`; the wheel's is
//! the console script over `rang._core.gemclean_main`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

#[cfg(all(target_os = "linux", target_pointer_width = "64"))]
#[global_allocator]
static ALLOCATOR: rang_core::gemclean::host::HugePageAlloc =
    rang_core::gemclean::host::HugePageAlloc;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = rang_core::gemclean::cli::main(&args);
    if code != 0 {
        std::process::exit(code);
    }
}
""",
    encoding="utf-8",
    newline="\n",
)
g = Path("core/src/gemclean.rs")
t = g.read_text(encoding="utf-8")
assert "pub mod fits;\n" in t
g.write_text(
    t.replace("pub mod fits;\n", "pub mod cli;\npub mod fits;\n", 1),
    encoding="utf-8",
    newline="\n",
)
