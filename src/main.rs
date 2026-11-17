// SPDX-License-Identifier: GPL-3.0-or-later
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match rang_sim::cli(&args) {
        Ok(text) => println!("{text}"),
        Err(error) => {
            eprintln!("rang-sim: {error}");
            std::process::exit(2);
        }
    }
}
