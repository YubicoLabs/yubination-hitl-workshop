//! Shared Windows-only workshop IPC identity. No permissive development fallback.
use std::fs::{File, OpenOptions};
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
use std::os::windows::io::AsRawHandle;
use std::path::{Path, PathBuf};
use windows::Win32::Storage::FileSystem::{GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION};

use anyhow::{bail, ensure, Result};
use windows::core::PWSTR;
use windows::Win32::Foundation::{CloseHandle, LocalFree, HANDLE, HLOCAL};
use windows::Win32::Security::Authorization::ConvertSidToStringSidW;
use windows::Win32::Security::*;
use windows::Win32::System::Threading::*;

pub struct OwnedHandle(pub HANDLE);
impl OwnedHandle {
    pub fn exited(&self, timeout_ms: u32) -> bool {
        unsafe {
            WaitForSingleObject(self.0, timeout_ms) != windows::Win32::Foundation::WAIT_TIMEOUT
        }
    }
}
impl Drop for OwnedHandle {
    fn drop(&mut self) {
        unsafe {
            let _ = CloseHandle(self.0);
        }
    }
}
// A handle is owned, never used after close, and has no shared mutable state.
unsafe impl Send for OwnedHandle {}
unsafe impl Sync for OwnedHandle {}

#[derive(Debug, PartialEq, Eq)]
pub struct Identity {
    pub user: String,
    pub logon: String,
    pub session: u32,
    pub elevated: bool,
    pub integrity: u32,
    pub app_container: bool,
}

fn token_info(token: HANDLE, class: TOKEN_INFORMATION_CLASS) -> Result<Vec<usize>> {
    let mut size = 0;
    unsafe {
        let _ = GetTokenInformation(token, class, None, 0, &mut size);
    }
    ensure!(size > 0 && size <= 65536, "Invalid token information size");
    let mut data = vec![0usize; (size as usize).div_ceil(std::mem::size_of::<usize>())];
    unsafe {
        GetTokenInformation(
            token,
            class,
            Some(data.as_mut_ptr().cast()),
            size,
            &mut size,
        )?;
    }
    Ok(data)
}

fn sid_string(sid: PSID) -> Result<String> {
    let mut text = PWSTR::null();
    unsafe {
        ConvertSidToStringSidW(sid, &mut text)?;
        let value = text.to_string();
        let _ = LocalFree(HLOCAL(text.0.cast()));
        Ok(value?)
    }
}

pub fn identity(process: HANDLE) -> Result<Identity> {
    let mut token = HANDLE::default();
    unsafe {
        OpenProcessToken(process, TOKEN_QUERY, &mut token)?;
    }
    let token = OwnedHandle(token);
    let user = token_info(token.0, TokenUser)?;
    let groups = token_info(token.0, TokenLogonSid)?;
    let elevation = token_info(token.0, TokenElevation)?;
    let session = token_info(token.0, TokenSessionId)?;
    let integrity = token_info(token.0, TokenIntegrityLevel)?;
    let container = token_info(token.0, TokenIsAppContainer)?;
    unsafe {
        let groups = &*(groups.as_ptr().cast::<TOKEN_GROUPS>());
        ensure!(groups.GroupCount == 1, "Interactive logon SID required");
        Ok(Identity {
            user: sid_string((*(user.as_ptr().cast::<TOKEN_USER>())).User.Sid)?,
            logon: sid_string(groups.Groups[0].Sid)?,
            session: *(session.as_ptr().cast::<u32>()),
            elevated: (*(elevation.as_ptr().cast::<TOKEN_ELEVATION>())).TokenIsElevated != 0,
            integrity: sid_string(
                (*(integrity.as_ptr().cast::<TOKEN_MANDATORY_LABEL>()))
                    .Label
                    .Sid,
            )?
            .rsplit('-')
            .next()
            .ok_or_else(|| anyhow::anyhow!("Missing integrity RID"))?
            .parse()?,
            app_container: *(container.as_ptr().cast::<u32>()) != 0,
        })
    }
}

pub fn current_identity() -> Result<Identity> {
    identity(unsafe { GetCurrentProcess() })
}

pub fn authorize(local: &Identity, peer: &Identity, elevated: bool) -> Result<()> {
    ensure!(
        local.user == peer.user
            && local.logon == peer.logon
            && local.session == peer.session
            && peer.session != 0,
        "IPC peer is outside the workshop user/logon/session"
    );
    ensure!(
        peer.elevated == elevated,
        "IPC peer has the wrong elevation level"
    );
    ensure!(
        !local.app_container && !peer.app_container,
        "AppContainer peers are not allowed"
    );
    ensure!(
        peer.integrity == if elevated { 0x3000 } else { 0x2000 }
            && local.integrity == if local.elevated { 0x3000 } else { 0x2000 },
        "Only medium controller/host and high helper tokens are allowed"
    );
    Ok(())
}

pub fn open_process(pid: u32) -> Result<OwnedHandle> {
    ensure!(pid != 0, "Invalid process ID");
    Ok(OwnedHandle(unsafe {
        OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE,
            false,
            pid,
        )?
    }))
}

pub fn image_path(process: HANDLE) -> Result<PathBuf> {
    let mut text = vec![0u16; 32768];
    let mut size = text.len() as u32;
    unsafe {
        QueryFullProcessImageNameW(
            process,
            PROCESS_NAME_WIN32,
            PWSTR(text.as_mut_ptr()),
            &mut size,
        )?;
    }
    Ok(PathBuf::from(String::from_utf16(&text[..size as usize])?))
}

pub struct PinnedBinary {
    path: PathBuf,
    file: File,
    _parents: Vec<File>,
    pinned_at: u64,
}
fn windows_ticks() -> u64 {
    (std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos()
        / 100) as u64
        + 116444736000000000
}
fn file_id(file: &File) -> Result<(u32, u32, u32)> {
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    unsafe {
        GetFileInformationByHandle(HANDLE(file.as_raw_handle()), &mut info)?;
    }
    Ok((
        info.dwVolumeSerialNumber,
        info.nFileIndexHigh,
        info.nFileIndexLow,
    ))
}
impl PinnedBinary {
    pub fn sibling(name: &str) -> Result<Self> {
        let executable = std::env::current_exe()?;
        Self::open(
            &executable
                .parent()
                .ok_or_else(|| anyhow::anyhow!("Missing executable directory"))?
                .join(name),
        )
    }
    pub fn open(path: &Path) -> Result<Self> {
        ensure!(path.is_absolute(), "Absolute executable path required");
        let mut parents = Vec::new();
        // Lock from the root downward before inspecting descendants: neither
        // directory replacement nor in-place reparse writes may race the pin.
        let ancestors: Vec<_> = path.ancestors().skip(1).collect();
        for part in ancestors.into_iter().rev() {
            parents.push(
                OpenOptions::new()
                    .read(true)
                    .share_mode(1)
                    .custom_flags(0x02000000 | 0x00200000)
                    .open(part)?,
            );
            if std::fs::symlink_metadata(part)?.file_attributes() & 0x400 != 0 {
                bail!("Reparse executable paths are not allowed");
            }
        }
        let file = OpenOptions::new()
            .read(true)
            .share_mode(1)
            .custom_flags(0x00200000)
            .open(path)?;
        ensure!(
            file.metadata()?.file_attributes() & 0x400 == 0,
            "Reparse executable rejected"
        );
        ensure!(
            file.metadata()?.is_file(),
            "Pinned executable must be a file"
        );
        Ok(Self {
            path: path.canonicalize()?,
            file,
            _parents: parents,
            pinned_at: windows_ticks(),
        })
    }
    pub fn verify(&self, process: HANDLE) -> Result<()> {
        let actual = image_path(process)?.canonicalize()?;
        ensure!(
            self.path
                .as_os_str()
                .to_string_lossy()
                .eq_ignore_ascii_case(&actual.as_os_str().to_string_lossy()),
            "IPC peer is not the pinned sibling executable"
        );
        let peer_file = OpenOptions::new().read(true).share_mode(1).open(actual)?;
        ensure!(
            file_id(&self.file)? == file_id(&peer_file)?,
            "IPC executable file identity changed"
        );
        Ok(())
    }
    pub fn verify_new_client(&self, process: &OwnedHandle) -> Result<()> {
        self.verify(process.0)?;
        let mut created = windows::Win32::Foundation::FILETIME::default();
        let mut exited = created;
        let mut kernel = created;
        let mut user = created;
        unsafe {
            GetProcessTimes(process.0, &mut created, &mut exited, &mut kernel, &mut user)?;
        }
        let ticks = ((created.dwHighDateTime as u64) << 32) | created.dwLowDateTime as u64;
        ensure!(
            ticks > self.pinned_at && !process.exited(0),
            "Client must be launched after helper pinning"
        );
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sample(elevated: bool) -> Identity {
        Identity {
            user: "user".into(),
            logon: "logon".into(),
            session: 1,
            elevated,
            integrity: if elevated { 0x3000 } else { 0x2000 },
            app_container: false,
        }
    }
    #[test]
    fn exact_same_logon_and_expected_role_only() {
        let local = sample(true);
        assert!(authorize(&local, &sample(false), false).is_ok());
        assert!(authorize(&local, &sample(true), false).is_err());
        let mut low = sample(false);
        low.integrity = 0x1000;
        assert!(authorize(&local, &low, false).is_err());
        low = sample(false);
        low.app_container = true;
        assert!(authorize(&local, &low, false).is_err());
        let mut other = sample(false);
        other.user = "other".into();
        assert!(authorize(&local, &other, false).is_err());
        other = sample(false);
        other.logon = "other".into();
        assert!(authorize(&local, &other, false).is_err());
        other = sample(false);
        other.session = 2;
        assert!(authorize(&local, &other, false).is_err());
        other.session = 0;
        assert!(authorize(&local, &other, false).is_err());
    }
    #[test]
    fn current_process_identity_and_image_are_consistent() {
        let process = open_process(std::process::id()).unwrap();
        assert_eq!(current_identity().unwrap(), identity(process.0).unwrap());
        let pin = PinnedBinary::open(&std::env::current_exe().unwrap()).unwrap();
        pin.verify(process.0).unwrap();
        assert!(pin.verify_new_client(&process).is_err());
        assert!(OpenOptions::new()
            .write(true)
            .open(std::env::current_exe().unwrap())
            .is_err());
        assert!(open_process(0).is_err());
    }
    #[test]
    fn pinned_fixture_rejects_write_delete_rename_and_wrong_image() {
        let directory = std::env::temp_dir().join(format!(
            "workshop-pin-{}-{}",
            std::process::id(),
            windows_ticks()
        ));
        std::fs::create_dir(&directory).unwrap();
        let executable = directory.join("fixture.exe");
        std::fs::write(&executable, b"MZ synthetic nonexecutable fixture").unwrap();
        let pin = PinnedBinary::open(&executable).unwrap();
        assert!(OpenOptions::new().write(true).open(&executable).is_err());
        assert!(std::fs::remove_file(&executable).is_err());
        assert!(std::fs::rename(&directory, directory.with_extension("moved")).is_err());
        assert!(pin
            .verify(open_process(std::process::id()).unwrap().0)
            .is_err());
        drop(pin);
        std::fs::remove_file(&executable).unwrap();
        std::fs::remove_dir(&directory).unwrap();
    }
}
