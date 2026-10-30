fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match rang_toy::cli(&args) {
        Ok(text) => println!("{text}"),
        Err(error) => {
            eprintln!("rang-toy: {error}");
            std::process::exit(2);
        }
    }
}
