mod backend;
#[cfg(not(target_os = "windows"))]
mod large_blob;
mod messaging;
mod startup;
#[cfg(target_os = "macos")]
mod native_ui;
mod validation;
mod webauthn;

use log::info;

fn main() {
    // Log to file since stdout is the messaging channel.
    // On Linux, snap confinement remaps /tmp; use SNAP_USER_COMMON or XDG_RUNTIME_DIR.
    let log_path = if cfg!(target_os = "linux") {
        if let Ok(snap_common) = std::env::var("SNAP_USER_COMMON") {
            std::path::PathBuf::from(snap_common).join("sign-extension-host.log")
        } else {
            std::env::temp_dir().join("sign-extension-host.log")
        }
    } else {
        std::env::temp_dir().join("sign-extension-host.log")
    };
    let log_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .ok();

    // Redirect stderr to the log file so eprintln! output is captured
    #[cfg(unix)]
    {
        use std::os::unix::io::AsRawFd;
        if let Ok(stderr_file) = std::fs::OpenOptions::new().create(true).append(true).open(&log_path) {
            unsafe {
                extern "C" { fn dup2(oldfd: i32, newfd: i32) -> i32; }
                dup2(stderr_file.as_raw_fd(), 2);
            }
        }
    }

    if let Some(file) = log_file {
        env_logger::Builder::new()
            .target(env_logger::Target::Pipe(Box::new(file)))
            .filter_level(log::LevelFilter::Debug)
            .init();
    } else {
        // Fallback to stderr if log file can't be opened
        env_logger::Builder::new()
            .target(env_logger::Target::Stderr)
            .filter_level(log::LevelFilter::Debug)
            .init();
    }

    info!("Native messaging host starting");

    // Validate caller
    if let Err(e) = validation::validate_caller() {
        log::error!("Caller validation failed: {e}");
        let error_response = serde_json::json!({
            "error": format!("Caller validation failed: {e}")
        });
        if let Err(e) = messaging::write_message(&mut std::io::stdout().lock(), &error_response) {
            log::error!("Failed to write error response: {e}");
        }
        std::process::exit(1);
    }

    info!("Caller validated, creating backend");

    let (mut backend, first_message) = match startup::prepare(
        &mut std::io::stdin().lock(),
        &mut std::io::stdout().lock(),
        backend::create_backend,
    ) {
        Ok(Some(prepared)) => prepared,
        Ok(None) => return,
        Err(e) => {
            log::error!("Failed to create FIDO backend: {e}");
            let error_response = serde_json::json!({
                "error": format!("Failed to create FIDO backend: {e}")
            });
            if let Err(e) = messaging::write_message(&mut std::io::stdout().lock(), &error_response) {
                log::error!("Failed to write error response: {e}");
            }
            std::process::exit(1);
        }
    };

    info!("Backend created, entering message loop");

    #[cfg(target_os = "macos")]
    {
        // AppKit requires all UI on the main thread. Run the message loop
        // on a background thread and the AppKit event loop here.
        let (ui_tx, ui_rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            messaging::message_loop(backend.as_mut(), first_message, ui_tx);
            // When the message loop exits, the process should exit.
            std::process::exit(0);
        });
        native_ui::run_main_loop(ui_rx);
    }

    #[cfg(not(target_os = "macos"))]
    {
        messaging::message_loop(backend.as_mut(), first_message);
    }
}
#[cfg(target_os = "windows")]
#[path = "../../../workshop_identity.rs"]
mod workshop_identity;
