use std::ffi::OsString;
use std::sync::atomic::AtomicBool;
use std::sync::mpsc;
use std::time::Duration;
use log::{info, error, warn};
use windows::Win32::Foundation::{CloseHandle, HANDLE, HWND};
use windows::Win32::UI::WindowsAndMessaging::{ShowWindow, SW_HIDE};
use windows_service::{
    define_windows_service,
    service::{
        ServiceControl, ServiceControlAccept, ServiceExitCode, ServiceState, ServiceStatus,
        ServiceType,
    },
    service_control_handler::{self, ServiceControlHandlerResult},
    service_dispatcher,
};

mod pipe;
mod fido;
#[cfg(windows)]
mod hid_windows;
mod pin_ui;
mod status_ui;
#[path = "../../../workshop_identity.rs"]
mod workshop_identity;

const SERVICE_NAME: &str = sign_extension_protocol::SERVICE_NAME;
const SERVICE_TYPE: ServiceType = ServiceType::OWN_PROCESS;

/// When true, use console stdin for PIN entry instead of Win32 dialog.
pub static CONSOLE_MODE: AtomicBool = AtomicBool::new(false);

define_windows_service!(ffi_service_main, service_main);

/// Acquire a system-wide named mutex to prevent multiple service instances.
/// Returns the mutex handle on success, or None if another instance is running.
fn acquire_singleton_mutex() -> Option<HANDLE> {
    use windows::Win32::System::Threading::CreateMutexW;
    use windows::core::PCWSTR;

    let name: Vec<u16> = "Local\\YubicoPreviewSignWorkshop"
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();
    unsafe {
        match CreateMutexW(None, true, PCWSTR(name.as_ptr())) {
            Ok(handle) => {
                // ERROR_ALREADY_EXISTS = 183
                if std::io::Error::last_os_error().raw_os_error() == Some(183) {
                    warn!("Another instance is already running — exiting");
                    let _ = CloseHandle(handle);
                    return None;
                }
                Some(handle)
            }
            Err(e) => {
                warn!("CreateMutexW failed: {e}");
                None
            }
        }
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    unsafe {
        windows::Win32::System::LibraryLoader::SetDefaultDllDirectories(
            windows::Win32::System::LibraryLoader::LOAD_LIBRARY_SEARCH_SYSTEM32)?;
    }
    // Workshop mode is interactive and explicitly consented; never silently
    // start a privileged SCM service or inherit a development log configuration.
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) != Some("--gui") || args.len() != 4
        || args[2] != "--controller-pid" {
        return Err("Use the workshop launcher: --gui --controller-pid <PID>".into());
    }
    let local = workshop_identity::current_identity()?;
    if !local.elevated || local.session == 0 {
        return Err("Windows FIDO access requires explicit UAC consent in the interactive session".into());
    }
    let controller = workshop_identity::open_process(args[3].parse()?)?;
    workshop_identity::authorize(&local, &workshop_identity::identity(controller.0)?, false)?;
    std::thread::spawn(move || {
        let started = std::time::Instant::now();
        loop {
            if lifetime_finished(controller.exited(500), started.elapsed()) {
                std::process::exit(0);
            }
        }
    });
    // Enable DPI awareness for crisp Win32 dialogs on high-DPI displays
    unsafe {
        use windows::Win32::UI::HiDpi::SetProcessDpiAwarenessContext;
        use windows::Win32::UI::HiDpi::DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2;
        let _ = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    }

    let args: Vec<String> = std::env::args().collect();
    let mode = args.get(1).map(|s| s.as_str()).unwrap_or("");

    match mode {
        "--console" => {
            CONSOLE_MODE.store(true, std::sync::atomic::Ordering::Relaxed);
            env_logger::init();

            let _mutex = match acquire_singleton_mutex() {
                Some(h) => h,
                None => {
                    eprintln!("Another instance is already running.");
                    return Err("Another workshop signing process is already running".into());
                }
            };

            info!("Running in console mode");
            run_service_logic()
        }
        "--gui" => {
            // GUI mode: runs pipe server in the user's session with Win32 PIN dialog
            // and tray notifications (no console I/O).
            init_file_logger();

            let _mutex = match acquire_singleton_mutex() {
                Some(h) => h,
                None => {
                    info!("Another instance is already running — exiting");
                    return Err("Another workshop signing process is already running".into());
                }
            };

            info!("Running in GUI mode");
            // Hide the console window if one was allocated
            hide_console_window();
            run_service_logic()
        }
        _ => {
            // Started by the Service Control Manager
            service_dispatcher::start(SERVICE_NAME, ffi_service_main)
                .map_err(|e| format!("Failed to start service dispatcher: {e}"))?;
            Ok(())
        }
    }
}

fn lifetime_finished(controller_exited: bool, elapsed: Duration) -> bool {
    controller_exited || elapsed >= Duration::from_secs(600)
}

#[cfg(test)]
mod lifetime_tests {
    use super::*;
    #[test]
    fn controller_exit_and_whole_process_deadline_are_terminal() {
        assert!(!lifetime_finished(false, Duration::from_secs(599)));
        assert!(lifetime_finished(false, Duration::from_secs(600)));
        assert!(lifetime_finished(true, Duration::ZERO));
    }
}

fn hide_console_window() {
    unsafe {
        let hwnd = windows::Win32::System::Console::GetConsoleWindow();
        if hwnd != HWND::default() {
            let _ = ShowWindow(hwnd, SW_HIDE);
        }
    }
}

fn service_main(args: Vec<OsString>) {
    if let Err(e) = run_service(args) {
        error!("Service failed: {e}");
    }
}

fn run_service(_args: Vec<OsString>) -> Result<(), Box<dyn std::error::Error>> {
    init_file_logger();

    let (shutdown_tx, shutdown_rx) = mpsc::channel();

    let event_handler = move |control_event| -> ServiceControlHandlerResult {
        match control_event {
            ServiceControl::Stop => {
                let _ = shutdown_tx.send(());
                ServiceControlHandlerResult::NoError
            }
            ServiceControl::Interrogate => ServiceControlHandlerResult::NoError,
            _ => ServiceControlHandlerResult::NotImplemented,
        }
    };

    let status_handle = service_control_handler::register(SERVICE_NAME, event_handler)?;

    status_handle.set_service_status(ServiceStatus {
        service_type: SERVICE_TYPE,
        current_state: ServiceState::Running,
        controls_accepted: ServiceControlAccept::STOP,
        exit_code: ServiceExitCode::Win32(0),
        checkpoint: 0,
        wait_hint: Duration::default(),
        process_id: None,
    })?;

    info!("Service started");

    // Run the pipe server
    let result = pipe::run_pipe_server(shutdown_rx);

    if let Err(ref e) = result {
        error!("Pipe server error: {e}");
    }

    status_handle.set_service_status(ServiceStatus {
        service_type: SERVICE_TYPE,
        current_state: ServiceState::Stopped,
        controls_accepted: ServiceControlAccept::empty(),
        exit_code: ServiceExitCode::Win32(0),
        checkpoint: 0,
        wait_hint: Duration::default(),
        process_id: None,
    })?;

    info!("Service stopped");
    Ok(())
}

fn init_file_logger() {
    // Never open a user-controlled TEMP path with an elevated token. Do not
    // inherit RUST_LOG=debug: request bodies and PIN-related data stay private.
    env_logger::Builder::new().filter_level(log::LevelFilter::Warn).init();
}

fn run_service_logic() -> Result<(), Box<dyn std::error::Error>> {
    let (_shutdown_tx, shutdown_rx) = mpsc::channel();
    pipe::run_pipe_server(shutdown_rx)
}
