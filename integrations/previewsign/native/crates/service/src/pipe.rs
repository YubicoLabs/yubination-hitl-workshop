use std::io::{self, Read, Write};
use std::sync::mpsc::Receiver;
use std::thread;

use log::{debug, error, info, warn};
use windows::core::{PCWSTR, PWSTR};
use windows::Win32::Foundation::{
    CloseHandle, LocalFree, HANDLE, HLOCAL, HWND, INVALID_HANDLE_VALUE,
};
use windows::Win32::Security::Authorization::ConvertStringSecurityDescriptorToSecurityDescriptorW;
use windows::Win32::Security::{PSECURITY_DESCRIPTOR, SECURITY_ATTRIBUTES};
use windows::Win32::Storage::FileSystem::{
    FlushFileBuffers, ReadFile, WriteFile, PIPE_ACCESS_DUPLEX,
};
use windows::Win32::System::Pipes::{
    ConnectNamedPipe, CreateNamedPipeW, DisconnectNamedPipe, GetNamedPipeClientProcessId,
    PIPE_READMODE_BYTE, PIPE_TYPE_BYTE, PIPE_WAIT,
};
use windows::Win32::System::Threading::{
    OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32,
    PROCESS_QUERY_LIMITED_INFORMATION,
};

pub use sign_extension_protocol::{PipeRequest, PipeResponse};
use sign_extension_protocol::{read_frame, write_frame, PIPE_NAME};

use crate::fido;

/// Context about the connecting client, resolved at connection time.
pub struct ClientContext {
    pub browser_name: Option<String>,
    /// The browser's main window handle (as usize for Send safety).
    /// Used as the owner for modal dialogs.
    pub browser_hwnd: Option<usize>,
}

const PIPE_BUFFER_SIZE: u32 = 64 * 1024;

// ---------------------------------------------------------------------------
// Win32 named pipe handle wrapper with Read/Write
// ---------------------------------------------------------------------------

struct PipeHandle(HANDLE);

// SAFETY: The pipe handle is used from a single thread at a time within
// the client handler. We send it to the spawned thread but do not share
// it across threads concurrently.
unsafe impl Send for PipeHandle {}

impl PipeHandle {
    fn is_valid(&self) -> bool {
        self.0 != INVALID_HANDLE_VALUE
    }
}

impl Read for PipeHandle {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        let mut bytes_read: u32 = 0;
        unsafe {
            ReadFile(self.0, Some(buf), Some(&mut bytes_read), None)
                .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(bytes_read as usize)
    }
}

impl Read for &PipeHandle {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        let mut bytes_read: u32 = 0;
        unsafe {
            ReadFile(self.0, Some(buf), Some(&mut bytes_read), None)
                .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(bytes_read as usize)
    }
}

impl Write for PipeHandle {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        let mut bytes_written: u32 = 0;
        unsafe {
            WriteFile(self.0, Some(buf), Some(&mut bytes_written), None)
                .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(bytes_written as usize)
    }

    fn flush(&mut self) -> io::Result<()> {
        unsafe {
            FlushFileBuffers(self.0)
                .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(())
    }
}

impl Write for &PipeHandle {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        let mut bytes_written: u32 = 0;
        unsafe {
            WriteFile(self.0, Some(buf), Some(&mut bytes_written), None)
                .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(bytes_written as usize)
    }

    fn flush(&mut self) -> io::Result<()> {
        unsafe {
            FlushFileBuffers(self.0)
                .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(())
    }
}

impl Drop for PipeHandle {
    fn drop(&mut self) {
        if self.is_valid() {
            unsafe {
                let _ = CloseHandle(self.0);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Development mode: set to false when binaries are Authenticode-signed
// ---------------------------------------------------------------------------

const ALLOW_UNSIGNED: bool = false;

// ---------------------------------------------------------------------------
// RAII wrapper for process handles
// ---------------------------------------------------------------------------

struct ProcessHandle(HANDLE);

impl Drop for ProcessHandle {
    fn drop(&mut self) {
        if !self.0.is_invalid() {
            unsafe { let _ = CloseHandle(self.0); }
        }
    }
}

// ---------------------------------------------------------------------------
// Authenticode verification via WinVerifyTrust
// ---------------------------------------------------------------------------

/// Verify that the executable at `exe_path` has a valid Authenticode signature.
/// Returns Ok(true) if valid, Ok(false) if unsigned/invalid, Err on API failure.
fn verify_authenticode_signature(exe_path: &[u16]) -> anyhow::Result<bool> {
    use windows::Win32::Security::WinTrust::*;

    let mut file_info = WINTRUST_FILE_INFO {
        cbStruct: std::mem::size_of::<WINTRUST_FILE_INFO>() as u32,
        pcwszFilePath: PCWSTR(exe_path.as_ptr()),
        hFile: HANDLE::default(),
        pgKnownSubject: std::ptr::null_mut(),
    };

    let mut action = WINTRUST_ACTION_GENERIC_VERIFY_V2;

    let mut trust_data = WINTRUST_DATA {
        cbStruct: std::mem::size_of::<WINTRUST_DATA>() as u32,
        dwUIChoice: WTD_UI_NONE,
        fdwRevocationChecks: WTD_REVOKE_NONE,
        dwUnionChoice: WTD_CHOICE_FILE,
        Anonymous: WINTRUST_DATA_0 {
            pFile: &mut file_info,
        },
        dwStateAction: WTD_STATEACTION_VERIFY,
        dwProvFlags: WTD_SAFER_FLAG,
        ..Default::default()
    };

    let status = unsafe {
        WinVerifyTrust(
            HWND::default(), // no UI parent
            &mut action,
            &mut trust_data as *mut _ as *mut _,
        )
    };

    // Clean up state
    trust_data.dwStateAction = WTD_STATEACTION_CLOSE;
    unsafe {
        WinVerifyTrust(
            HWND::default(),
            &mut action,
            &mut trust_data as *mut _ as *mut _,
        );
    }

    if status == 0 {
        Ok(true)
    } else {
        // 0x800B0100 = TRUST_E_NOSIGNATURE
        let code = status as u32;
        info!("WinVerifyTrust returned 0x{code:08X}");
        Ok(false)
    }
}

/// Get the client's process ID from the pipe handle.
fn get_client_pid(pipe: &PipeHandle) -> Option<u32> {
    let mut pid: u32 = 0;
    match unsafe { GetNamedPipeClientProcessId(pipe.0, &mut pid) } {
        Ok(()) => Some(pid),
        Err(e) => {
            warn!("GetNamedPipeClientProcessId failed: {e}");
            None
        }
    }
}

/// Verify the connecting client's Authenticode signature.
fn verify_client_authenticode(pipe: &PipeHandle) -> bool {
    // Get the client's process ID
    let mut client_pid: u32 = 0;
    if let Err(e) = unsafe { GetNamedPipeClientProcessId(pipe.0, &mut client_pid) } {
        error!("GetNamedPipeClientProcessId failed: {e}");
        if ALLOW_UNSIGNED {
            warn!("Allowing connection despite PID lookup failure (ALLOW_UNSIGNED=true)");
            return true;
        }
        return false;
    }
    info!("Client PID: {client_pid}");

    // Open the client process
    let proc_handle = match unsafe {
        OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, client_pid)
    } {
        Ok(h) => ProcessHandle(h),
        Err(e) => {
            error!("OpenProcess failed for PID {client_pid}: {e}");
            if ALLOW_UNSIGNED {
                warn!("Allowing connection despite OpenProcess failure (ALLOW_UNSIGNED=true)");
                return true;
            }
            return false;
        }
    };

    // Query the executable path
    let mut path_buf = [0u16; 1024];
    let mut path_len = path_buf.len() as u32;
    if let Err(e) = unsafe {
        QueryFullProcessImageNameW(proc_handle.0, PROCESS_NAME_WIN32, PWSTR(path_buf.as_mut_ptr()), &mut path_len)
    } {
        error!("QueryFullProcessImageNameW failed: {e}");
        if ALLOW_UNSIGNED {
            warn!("Allowing connection despite path query failure (ALLOW_UNSIGNED=true)");
            return true;
        }
        return false;
    }

    let exe_path = String::from_utf16_lossy(&path_buf[..path_len as usize]);
    info!("Client executable: {exe_path}");

    // Null-terminate for WinVerifyTrust
    let path_with_null: Vec<u16> = path_buf[..path_len as usize]
        .iter()
        .copied()
        .chain(std::iter::once(0))
        .collect();

    match verify_authenticode_signature(&path_with_null) {
        Ok(true) => {
            info!("Client Authenticode signature valid");
            true
        }
        Ok(false) => {
            if ALLOW_UNSIGNED {
                warn!("Client binary unsigned/invalid signature -- allowing (ALLOW_UNSIGNED=true)");
                true
            } else {
                error!("Client binary unsigned/invalid signature -- rejecting");
                false
            }
        }
        Err(e) => {
            error!("Authenticode verification error: {e}");
            if ALLOW_UNSIGNED {
                warn!("Allowing connection despite verification error (ALLOW_UNSIGNED=true)");
                true
            } else {
                false
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Browser name resolution from client's parent process
// ---------------------------------------------------------------------------

struct BrowserInfo {
    name: String,
}

/// Given the pipe client's PID, walk the process tree upward to find a
/// known browser ancestor and return its info.
fn resolve_browser(client_pid: u32) -> Option<BrowserInfo> {
    use std::collections::HashMap;
    use windows::Win32::System::Diagnostics::ToolHelp::*;

    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0).ok()?;
        let _snap_guard = scopeguard(snap);

        // Build a PID → parent-PID map from the snapshot
        let mut parent_map: HashMap<u32, u32> = HashMap::new();
        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };
        if Process32FirstW(snap, &mut entry).is_ok() {
            loop {
                parent_map.insert(entry.th32ProcessID, entry.th32ParentProcessID);
                entry.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
                if Process32NextW(snap, &mut entry).is_err() {
                    break;
                }
            }
        }

        // Walk up the tree from client_pid, checking each ancestor
        let mut current = client_pid;
        for _ in 0..10 {
            let ppid = match parent_map.get(&current) {
                Some(&p) if p != current && p != 0 => p,
                _ => break,
            };

            let proc_handle = match OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, ppid) {
                Ok(h) => ProcessHandle(h),
                Err(_) => break,
            };

            let mut path_buf = [0u16; 1024];
            let mut path_len = path_buf.len() as u32;
            if QueryFullProcessImageNameW(
                proc_handle.0,
                PROCESS_NAME_WIN32,
                PWSTR(path_buf.as_mut_ptr()),
                &mut path_len,
            ).is_err() {
                break;
            }

            let exe_path = String::from_utf16_lossy(&path_buf[..path_len as usize]);
            let exe_name = exe_path
                .rsplit('\\')
                .next()
                .unwrap_or("")
                .to_lowercase();

            info!("Ancestor process (PID {ppid}): {exe_path}");

            let browser_name = match exe_name.as_str() {
                "chrome.exe" => Some("Google Chrome"),
                "msedge.exe" => Some("Microsoft Edge"),
                "firefox.exe" => Some("Mozilla Firefox"),
                _ => None,
            };

            if let Some(name) = browser_name {
                return Some(BrowserInfo {
                    name: name.to_string(),
                });
            }

            current = ppid;
        }

        // No known browser found — return the direct parent info for logging
        let ppid = *parent_map.get(&client_pid)?;
        let proc_handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, ppid).ok()?;
        let proc_guard = ProcessHandle(proc_handle);
        let mut path_buf = [0u16; 1024];
        let mut path_len = path_buf.len() as u32;
        QueryFullProcessImageNameW(
            proc_guard.0,
            PROCESS_NAME_WIN32,
            PWSTR(path_buf.as_mut_ptr()),
            &mut path_len,
        ).ok()?;
        let exe_path = String::from_utf16_lossy(&path_buf[..path_len as usize]);
        let exe_name = exe_path.rsplit('\\').next().unwrap_or("").to_lowercase();
        info!("No known browser ancestor found; direct parent (PID {ppid}): {exe_path}");
        Some(BrowserInfo { name: exe_name })
    }
}

/// RAII guard for snapshot handles.
fn scopeguard(handle: HANDLE) -> impl Drop {
    struct Guard(HANDLE);
    impl Drop for Guard {
        fn drop(&mut self) {
            unsafe { let _ = CloseHandle(self.0); }
        }
    }
    Guard(handle)
}

// ---------------------------------------------------------------------------
// Named pipe creation with explicit DACL
// ---------------------------------------------------------------------------

fn create_named_pipe(logon_sid: &str) -> anyhow::Result<PipeHandle> {
    let pipe_name: Vec<u16> = PIPE_NAME.encode_utf16().chain(std::iter::once(0)).collect();

    // SDDL security descriptor:
    //   D:           — DACL
    //   (A;;GA;;;LS) — Allow GENERIC_ALL to LocalService (S-1-5-19)
    //   (A;;GRGW;;;IU) — Allow GENERIC_READ|GENERIC_WRITE to Interactive Users (S-1-5-4)
    // In dev mode, also allow Network Users (NU) for SSH-based testing.
    let sddl_str = format!("D:P(A;;GA;;;{logon_sid})S:(ML;;NW;;;ME)");
    let sddl: Vec<u16> = sddl_str
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();

    let mut sd_ptr = PSECURITY_DESCRIPTOR::default();
    unsafe {
        ConvertStringSecurityDescriptorToSecurityDescriptorW(
            PCWSTR(sddl.as_ptr()),
            1, // SDDL_REVISION_1
            &mut sd_ptr,
            None,
        )?;
    }

    let sa = SECURITY_ATTRIBUTES {
        nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
        lpSecurityDescriptor: sd_ptr.0,
        bInheritHandle: false.into(),
    };

    let handle = unsafe {
        CreateNamedPipeW(
            PCWSTR(pipe_name.as_ptr()),
            PIPE_ACCESS_DUPLEX | windows::Win32::Storage::FileSystem::FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | windows::Win32::System::Pipes::PIPE_REJECT_REMOTE_CLIENTS,
            1,                // reserve one instance for the helper's lifetime
            PIPE_BUFFER_SIZE, // nOutBufferSize
            PIPE_BUFFER_SIZE, // nInBufferSize
            0,                // nDefaultTimeOut
            Some(&sa),
        )
    };

    // Free the API-allocated security descriptor
    unsafe { let _ = LocalFree(HLOCAL(sd_ptr.0)); }

    if handle == INVALID_HANDLE_VALUE {
        let err = std::io::Error::last_os_error();
        return Err(anyhow::anyhow!("CreateNamedPipeW failed: {err}"));
    }

    info!("Pipe instance created with explicit DACL");
    Ok(PipeHandle(handle))
}

// ---------------------------------------------------------------------------
// Client handler
// ---------------------------------------------------------------------------

fn handle_client(mut pipe: &mut PipeHandle, pin: &crate::workshop_identity::PinnedBinary) {
    let client_pid = get_client_pid(&pipe);
    let verified = (|| -> anyhow::Result<crate::workshop_identity::OwnedHandle> {
        let peer = crate::workshop_identity::open_process(client_pid.ok_or_else(|| anyhow::anyhow!("Client PID unavailable"))?)?;
        pin.verify_new_client(&peer)?;
        crate::workshop_identity::authorize(
            &crate::workshop_identity::current_identity()?,
            &crate::workshop_identity::identity(peer.0)?, false)?;
        Ok(peer)
    })();
    let _peer = match verified {
        Ok(peer) => peer,
        Err(_) => { error!("Workshop client identity rejected");
            unsafe { let _ = DisconnectNamedPipe(pipe.0); }
            return;
        }
    };

    let browser_info = client_pid.and_then(resolve_browser);
    let browser_name = browser_info.as_ref().map(|b| b.name.clone());
    // An arbitrary foreground HWND is not authenticated browser identity and
    // may be stale by the next ceremony. All elevated workshop UI is ownerless.
    let browser_hwnd = None;
    info!("Browser: {:?}, HWND: {:?}", browser_name, browser_hwnd);

    let ctx = std::sync::Arc::new(ClientContext { browser_name, browser_hwnd });

    loop {
        // Read a request frame
        let frame = match read_frame(&mut pipe) {
            Ok(f) => f,
            Err(e) => {
                debug!("Client disconnected or read error: {e}");
                break;
            }
        };

        // Decode CBOR request
        let request: PipeRequest = match serde_cbor::from_slice(&frame) {
            Ok(r) => r,
            Err(e) => {
                error!("Failed to decode request: {e}");
                let err_resp = PipeResponse::Error {
                    code: 1,
                    message: format!("Invalid request: {e}"),
                };
                if let Ok(data) = serde_cbor::to_vec(&err_resp) {
                    let _ = write_frame(&mut pipe, &data);
                }
                break;
            }
        };

        // Never log the request body (credentials, client data and PIN inputs).

        // Handle Cancel specially
        if matches!(request, PipeRequest::Cancel) {
            info!("Cancel received");
            let resp = PipeResponse::Error {
                code: 11,
                message: "Cancelled by user".to_string(),
            };
            if let Ok(data) = serde_cbor::to_vec(&resp) {
                let _ = write_frame(&mut pipe, &data);
            }
            break;
        }

        // Create a status sender that writes StatusUpdate frames to the pipe.
        // We use a channel so the fido module can send status updates from
        // its own thread while the response is being assembled.
        let (status_tx, status_rx) = std::sync::mpsc::channel::<PipeResponse>();

        // Spawn a thread that forwards status updates to the pipe.
        // HANDLE contains *mut c_void which isn't Send, so pass as usize.
        let pipe_handle_usize = pipe.0 .0 as usize;
        let status_writer = thread::spawn(move || {
            // We write status updates using the raw handle. This is safe
            // because the main thread is blocked waiting for the fido call
            // to complete, and only status updates are written here.
            let mut writer = PipeHandle(HANDLE(pipe_handle_usize as *mut _));
            for status in status_rx {
                if let Ok(data) = serde_cbor::to_vec(&status) {
                    if let Err(e) = write_frame(&mut writer, &data) {
                        error!("Failed to write status update: {e}");
                        break;
                    }
                }
            }
            // Prevent Drop from closing the handle -- the main PipeHandle owns it
            std::mem::forget(writer);
        });

        let status_sender = move |resp: PipeResponse| {
            let _ = status_tx.send(resp);
        };

        // Process the FIDO request
        let response = fido::handle_request(request, status_sender, &ctx);

        // Wait for the status writer to drain (the sender was moved into
        // handle_request's closure, so it is dropped when handle_request returns).
        let _ = status_writer.join();

        // Send the final response
        match serde_cbor::to_vec(&response) {
            Ok(data) => {
                if let Err(e) = write_frame(&mut pipe, &data) {
                    error!("Failed to write response: {e}");
                    break;
                }
            }
            Err(e) => {
                error!("Failed to encode response: {e}");
                break;
            }
        }
    }

    unsafe {
        let _ = DisconnectNamedPipe(pipe.0);
    }
    info!("Client disconnected");
}

// ---------------------------------------------------------------------------
// Pipe server main loop
// ---------------------------------------------------------------------------

pub fn run_pipe_server(shutdown_rx: Receiver<()>) -> Result<(), Box<dyn std::error::Error>> {
    info!("Starting pipe server on {PIPE_NAME}");
    let identity = crate::workshop_identity::current_identity()?;
    let pin = crate::workshop_identity::PinnedBinary::sibling("sign-extension-host.exe")?;
    // Keep the first instance open across disconnects, preventing pipe squatting.
    let mut pipe = create_named_pipe(&identity.logon)?;

    loop {
        // Check for shutdown signal (non-blocking)
        if shutdown_rx.try_recv().is_ok() {
            info!("Shutdown signal received");
            break;
        }

        // Create a new pipe instance for the next client
        info!("Waiting for client connection...");

        // ConnectNamedPipe blocks until a client connects
        let connected = unsafe { ConnectNamedPipe(pipe.0, None) };

        match connected {
            Ok(()) => {
                info!("Client connected");
            }
            Err(ref e) => {
                // ERROR_PIPE_CONNECTED (535) means the client connected between
                // CreateNamedPipe and ConnectNamedPipe -- that is fine.
                let code = e.code().0 as u32;
                if code == 0x80070217 /* HRESULT for ERROR_PIPE_CONNECTED */ {
                    info!("Client already connected");
                } else {
                    error!("ConnectNamedPipe failed: {e}");
                    continue;
                }
            }
        }

        // Sequential clients reuse the reserved first pipe instance. A separate
        // controller watchdog bounds lifetime even while this handler blocks.
        handle_client(&mut pipe, &pin);
    }

    info!("Pipe server stopped");
    Ok(())
}
