mod api;
mod cli;
mod drivers;
mod scoring;
mod storage;

fn main() {
    if let Err(e) = cli::run() {
        eprintln!("Error: {e:#}");
        std::process::exit(1);
    }
}
