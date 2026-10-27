//! Windows pipe backend — connects to the elevated service over a named pipe.

use anyhow::Result;
use log::debug;
use std::io::{Read, Write};

use sign_extension_protocol::{
    PipeRequest, PipeResponse, read_frame, write_frame, PIPE_NAME,
};

use super::FidoBackend;

pub struct PipeBackend {
    #[cfg(target_os = "windows")]
    handle: windows::Win32::Foundation::HANDLE,
    #[cfg(target_os = "windows")]
    _server: crate::workshop_identity::OwnedHandle,
    #[cfg(target_os = "windows")]
    _server_pin: crate::workshop_identity::PinnedBinary,
}

#[cfg(target_os = "windows")]
fn verify_server_identity(handle: windows::Win32::Foundation::HANDLE,
    pin: &crate::workshop_identity::PinnedBinary) -> Result<crate::workshop_identity::OwnedHandle> {
    let mut pid = 0;
    unsafe { windows::Win32::System::Pipes::GetNamedPipeServerProcessId(handle, &mut pid)?; }
    let peer = crate::workshop_identity::open_process(pid)?;
    pin.verify(peer.0)?;
    crate::workshop_identity::authorize(&crate::workshop_identity::current_identity()?,
        &crate::workshop_identity::identity(peer.0)?, true)?;
    Ok(peer)
}

// SAFETY: HANDLE is a thin wrapper around *mut c_void. The pipe handle is
// exclusively owned by PipeBackend and only accessed from a single thread.
#[cfg(target_os = "windows")]
unsafe impl Send for PipeBackend {}

impl PipeBackend {
    pub fn connect() -> Result<Self> {
        #[cfg(target_os = "windows")]
        {
            Self::connect_windows()
        }
        #[cfg(not(target_os = "windows"))]
        {
            Err(anyhow::anyhow!("Named pipe client only supported on Windows"))
        }
    }

    #[cfg(target_os = "windows")]
    fn connect_windows() -> Result<Self> {
        use anyhow::anyhow;
        use log::info;
        use windows::Win32::Foundation::*;
        use windows::Win32::Storage::FileSystem::*;
        use windows::core::*;

        let pipe_name = HSTRING::from(PIPE_NAME);

        for attempt in 0..5u64 {
            unsafe {
                let handle = CreateFileW(
                    &pipe_name,
                    (GENERIC_READ | GENERIC_WRITE).0,
                    FILE_SHARE_NONE,
                    None,
                    OPEN_EXISTING,
                    SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION,
                    HANDLE::default(),
                );

                match handle {
                    Ok(h) => {
                        // Verify the elevated peer before sending a request or
                        // accepting a PIN/status response from this pipe name.
                        let checked = (|| -> anyhow::Result<_> {
                            let pin = crate::workshop_identity::PinnedBinary::sibling("sign-extension-service.exe")?;
                            let peer = verify_server_identity(h, &pin)?;
                            Ok((peer, pin))
                        })();
                        let (peer, pin) = match checked {
                            Ok(pair) => pair,
                            Err(error) => { let _ = CloseHandle(h); return Err(error); }
                        };
                        debug!("Connected to pipe");
                        return Ok(Self { handle: h, _server: peer, _server_pin: pin });
                    }
                    Err(e) => {
                        if attempt == 0 {
                            info!("Workshop pipe unavailable; start the explicit UAC helper launcher");
                            // Explicit workshop launch only. Never start an SCM service.
                        }
                        debug!("Connection attempt {attempt} failed: {e}");
                        std::thread::sleep(std::time::Duration::from_millis(
                            500 * (attempt + 1),
                        ));
                    }
                }
            }
        }

        Err(anyhow!("Failed to connect to service pipe after retries"))
    }
}

#[cfg(all(test, target_os = "windows"))]
mod peer_tests {
    use super::*;
    use windows::Win32::Foundation::*;
    use windows::Win32::Storage::FileSystem::*;
    use windows::Win32::System::Pipes::*;
    use windows::core::HSTRING;

    #[test]
    fn medium_fake_pipe_is_rejected_without_request_bytes() {
        // A distinct test-only pipe, never the user's workshop registration.
        if crate::workshop_identity::current_identity().unwrap().elevated { return; }
        let name = HSTRING::from(format!(r"\\.\pipe\workshop-negative-{}", std::process::id()));
        unsafe {
            let server = CreateNamedPipeW(&name, PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
                PIPE_TYPE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS, 1, 1024, 1024, 0, None);
            assert_ne!(server, INVALID_HANDLE_VALUE);
            let raw = server.0 as usize;
            let thread = std::thread::spawn(move || {
                let handle = HANDLE(raw as *mut _);
                let _ = ConnectNamedPipe(handle, None);
                let mut bytes = [0u8; 1]; let mut count = 0;
                let _ = ReadFile(handle, Some(&mut bytes), Some(&mut count), None);
                let _ = CloseHandle(handle);
                count
            });
            let client = CreateFileW(&name, (GENERIC_READ | GENERIC_WRITE).0, FILE_SHARE_NONE,
                None, OPEN_EXISTING, SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, HANDLE::default()).unwrap();
            let pin = crate::workshop_identity::PinnedBinary::open(&std::env::current_exe().unwrap()).unwrap();
            assert!(verify_server_identity(client, &pin).is_err());
            let _ = CloseHandle(client);
            assert_eq!(thread.join().unwrap(), 0, "No request/PIN/CTAP bytes sent to rogue pipe");
        }
    }
}

impl FidoBackend for PipeBackend {
    fn execute(&mut self, request: &PipeRequest, pin_requester: &mut dyn super::PinRequester) -> Result<PipeResponse> {
        let data = serde_cbor::to_vec(request)?;
        write_frame(self, &data)?;

        loop {
            let frame = read_frame(self)?;
            let response: PipeResponse = serde_cbor::from_slice(&frame)?;
            match &response {
                PipeResponse::StatusUpdate { status, retries: _ } => {
                    debug!("Status update from service: {status}");
                    // On Windows, the service shows its own Win32 modal dialog for
                    // touch/insert status — don't duplicate it in the extension overlay.
                    let ext_status = match status.as_str() {
                        "presence_required" | "device_needed" => {
                            continue;
                        }
                        _ => status.as_str(),
                    };
                    pin_requester.notify_status(ext_status);
                    continue;
                }
                PipeResponse::Success { .. } | PipeResponse::Error { .. } => {
                    pin_requester.notify_status("done");
                    return Ok(response);
                }
            }
        }
    }
}

#[cfg(target_os = "windows")]
impl Read for PipeBackend {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        use windows::Win32::Storage::FileSystem::ReadFile;
        let mut bytes_read = 0u32;
        unsafe {
            ReadFile(self.handle, Some(buf), Some(&mut bytes_read), None)
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(bytes_read as usize)
    }
}

#[cfg(target_os = "windows")]
impl Write for PipeBackend {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        use windows::Win32::Storage::FileSystem::WriteFile;
        let mut bytes_written = 0u32;
        unsafe {
            WriteFile(self.handle, Some(buf), Some(&mut bytes_written), None)
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(bytes_written as usize)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        use windows::Win32::Storage::FileSystem::FlushFileBuffers;
        unsafe {
            FlushFileBuffers(self.handle)
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))?;
        }
        Ok(())
    }
}

#[cfg(not(target_os = "windows"))]
impl Read for PipeBackend {
    fn read(&mut self, _buf: &mut [u8]) -> std::io::Result<usize> {
        Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "Named pipe not supported on this platform",
        ))
    }
}

#[cfg(not(target_os = "windows"))]
impl Write for PipeBackend {
    fn write(&mut self, _buf: &[u8]) -> std::io::Result<usize> {
        Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "Named pipe not supported on this platform",
        ))
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "Named pipe not supported on this platform",
        ))
    }
}

#[cfg(target_os = "windows")]
impl Drop for PipeBackend {
    fn drop(&mut self) {
        unsafe {
            let _ = windows::Win32::Foundation::CloseHandle(self.handle);
        }
    }
}
