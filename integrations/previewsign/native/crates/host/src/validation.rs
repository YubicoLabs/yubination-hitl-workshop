use anyhow::{anyhow, Result};
use log::debug;
use url::Url;

pub fn validate_origin(origin: &str) -> Result<String> {
    let url = Url::parse(origin)?;

    match url.scheme() {
        "https" => {}
        "http" if url.host_str() == Some("localhost") => {}
        scheme => return Err(anyhow!("Invalid origin scheme: {scheme}")),
    }

    let host = url
        .host_str()
        .ok_or_else(|| anyhow!("Origin has no host"))?;

    Ok(host.to_string())
}

pub fn validate_rp_id(rp_id: &str, origin: &str) -> Result<()> {
    let origin_host = validate_origin(origin)?;

    // RP ID must be the origin's effective domain or a registrable domain suffix
    if origin_host == rp_id {
        return Ok(());
    }

    // Check if rp_id is a registrable domain suffix of origin_host
    if origin_host.ends_with(&format!(".{rp_id}")) {
        // Verify rp_id is not a public suffix itself
        let domain = psl::domain(rp_id.as_bytes());
        if domain.is_some() {
            return Ok(());
        }
        return Err(anyhow!("RP ID '{rp_id}' is a public suffix"));
    }

    Err(anyhow!(
        "RP ID '{rp_id}' is not a valid suffix of origin '{origin_host}'"
    ))
}

#[cfg(target_os = "windows")]
pub fn validate_caller() -> Result<()> {
    use log::{info, warn};
    use windows::core::PWSTR;
    use windows::Win32::Foundation::{CloseHandle, HANDLE};
    use windows::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };
    use windows::Win32::System::Threading::{
        GetCurrentProcessId, OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32,
        PROCESS_QUERY_LIMITED_INFORMATION,
    };

    // Development mode: set to false when binaries are deployed
    const ALLOW_NON_BROWSER: bool = false;

    const KNOWN_BROWSERS: &[&str] = &["chrome.exe", "msedge.exe", "firefox.exe"];
    const ALLOWED_PREFIXES: &[&str] = &[
        r"C:\Program Files\",
        r"C:\Program Files (x86)\",
    ];

    struct HandleGuard(HANDLE);
    impl Drop for HandleGuard {
        fn drop(&mut self) {
            if !self.0.is_invalid() {
                unsafe { let _ = CloseHandle(self.0); }
            }
        }
    }

    let my_pid = unsafe { GetCurrentProcessId() };
    debug!("Current PID: {my_pid}");

    // Take a snapshot of all processes
    let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)? };
    let snapshot = HandleGuard(snapshot);

    // Find our entry to get parent PID
    let mut entry = PROCESSENTRY32W {
        dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
        ..Default::default()
    };

    let mut parent_pid: Option<u32> = None;
    unsafe {
        if Process32FirstW(snapshot.0, &mut entry).is_ok() {
            loop {
                if entry.th32ProcessID == my_pid {
                    parent_pid = Some(entry.th32ParentProcessID);
                    break;
                }
                if Process32NextW(snapshot.0, &mut entry).is_err() {
                    break;
                }
            }
        }
    }

    let parent_pid = match parent_pid {
        Some(pid) => {
            info!("Parent PID: {pid}");
            pid
        }
        None => {
            return Err(anyhow!("Could not find parent process"));
        }
    };

    // Open parent process and query its executable path
    let proc_handle = match unsafe {
        OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, parent_pid)
    } {
        Ok(h) => HandleGuard(h),
        Err(e) => {
            if ALLOW_NON_BROWSER {
                warn!("Cannot open parent process (PID {parent_pid}): {e} -- allowing (ALLOW_NON_BROWSER=true)");
                return Ok(());
            }
            return Err(anyhow!("Cannot open parent process: {e}"));
        }
    };

    let mut path_buf = [0u16; 1024];
    let mut path_len = path_buf.len() as u32;
    if let Err(e) = unsafe {
        QueryFullProcessImageNameW(proc_handle.0, PROCESS_NAME_WIN32, PWSTR(path_buf.as_mut_ptr()), &mut path_len)
    } {
        if ALLOW_NON_BROWSER {
            warn!("Cannot query parent exe path: {e} -- allowing (ALLOW_NON_BROWSER=true)");
            return Ok(());
        }
        return Err(anyhow!("Cannot query parent exe path: {e}"));
    }

    let mut exe_path = String::from_utf16_lossy(&path_buf[..path_len as usize]);
    info!("Parent executable: {exe_path}");

    // Chrome's default Windows native-messaging launch uses exactly one system
    // cmd.exe wrapper. Do not treat cmd.exe itself or arbitrary ancestors as a
    // browser: require its immediate parent to satisfy the existing browser rule.
    let mut system = vec![0u16; 32768];
    let length = unsafe { windows::Win32::System::SystemInformation::GetSystemDirectoryW(Some(&mut system)) } as usize;
    if length == 0 || length >= system.len() { return Err(anyhow!("System directory unavailable")); }
    let system_cmd = std::path::PathBuf::from(String::from_utf16(&system[..length])?).join("cmd.exe");
    let parent_path = std::path::Path::new(&exe_path).canonicalize()?;
    let mut _held_wrapper_chain = None;
    if parent_path.as_os_str().to_string_lossy().eq_ignore_ascii_case(&system_cmd.canonicalize()?.as_os_str().to_string_lossy()) {
        let wrapper = crate::workshop_identity::open_process(parent_pid)?;
        crate::workshop_identity::authorize(&crate::workshop_identity::current_identity()?,
            &crate::workshop_identity::identity(wrapper.0)?, false)?;
        if wrapper.exited(0) { return Err(anyhow!("System wrapper exited")); }
        let mut wrapper_parent = None;
        entry.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
        unsafe {
            if Process32FirstW(snapshot.0, &mut entry).is_ok() {
                loop {
                    if entry.th32ProcessID == parent_pid { wrapper_parent = Some(entry.th32ParentProcessID); break; }
                    if Process32NextW(snapshot.0, &mut entry).is_err() { break; }
                }
            }
        }
        let browser_pid = wrapper_parent.ok_or_else(|| anyhow!("System wrapper parent unavailable"))?;
        let browser = crate::workshop_identity::open_process(browser_pid)?;
        let browser_identity = crate::workshop_identity::identity(browser.0)?;
        crate::workshop_identity::authorize(&crate::workshop_identity::current_identity()?, &browser_identity, false)?;
        if browser.exited(0) { return Err(anyhow!("Browser parent exited")); }
        exe_path = crate::workshop_identity::image_path(browser.0)?.to_string_lossy().into_owned();
        _held_wrapper_chain = Some((wrapper, browser));
        info!("System wrapper browser parent: {exe_path}");
    }

    // Check filename
    let filename = exe_path
        .rsplit('\\')
        .next()
        .unwrap_or("")
        .to_lowercase();

    let is_browser = KNOWN_BROWSERS.iter().any(|b| filename == *b);
    let is_program_files = ALLOWED_PREFIXES.iter().any(|p| {
        exe_path.len() >= p.len()
            && exe_path[..p.len()].eq_ignore_ascii_case(p)
    });

    // TODO: Authenticode-verify the parent browser executable.
    // The exe name + Program Files path check prevents casual spoofing, but a
    // binary named chrome.exe placed in Program Files by an admin would pass.
    // Add WinVerifyTrust on exe_path (same as service/pipe.rs verify_authenticode_signature)
    // and optionally check signer matches Google/Mozilla/Microsoft.

    if is_browser && is_program_files {
        info!("Parent is a known browser in Program Files");
        Ok(())
    } else if ALLOW_NON_BROWSER {
        warn!(
            "Parent is not a known browser ({filename} at {exe_path}) -- allowing (ALLOW_NON_BROWSER=true)"
        );
        Ok(())
    } else {
        Err(anyhow!(
            "Parent process is not a known browser: {exe_path}"
        ))
    }
}

#[cfg(not(target_os = "windows"))]
pub fn validate_caller() -> Result<()> {
    debug!("Caller validation skipped on non-Windows");
    Ok(())
}
