use anyhow::{anyhow, Result};
use log::info;
use std::path::{Path, PathBuf};

const NATIVE_HOST_NAME: &str = "com.example.sign_extension";
const EXTENSION_ID: &str = "lcknfcjhoadggemnifljpplfjnppofdk";
const FIREFOX_EXTENSION_ID: &str = "sign-extension@example.com";

#[cfg(target_os = "windows")]
const SERVICE_NAME: &str = "SignExtensionFido";
#[cfg(target_os = "windows")]
const SERVICE_DISPLAY: &str = "Sign Extension FIDO Service";
#[cfg(target_os = "windows")]
const INSTALL_DIR: &str = r"C:\Program Files\Sign Extension";

fn main() -> Result<()> {
    env_logger::init();

    let args: Vec<String> = std::env::args().collect();
    let command = args.get(1).map(|s| s.as_str()).unwrap_or("help");

    match command {
        "install" => install()?,
        "uninstall" => uninstall()?,
        "status" => status()?,
        "help" | "--help" | "-h" => print_help(),
        _ => {
            eprintln!("Unknown command: {command}");
            print_help();
            std::process::exit(1);
        }
    }

    Ok(())
}

fn print_help() {
    eprintln!("Sign Extension FIDO Bridge Installer");
    eprintln!();
    eprintln!("Usage: sign-extension-installer <command>");
    eprintln!();
    eprintln!("Commands:");
    eprintln!("  install     Install native messaging host (and service on Windows)");
    eprintln!("  uninstall   Remove native messaging host (and service on Windows)");
    eprintln!("  status      Check installation status");
    eprintln!("  help        Show this help");
    if cfg!(target_os = "windows") {
        eprintln!();
        eprintln!("The install and uninstall commands require administrator privileges.");
    }
}

// ---------------------------------------------------------------------------
// Host binary path
// ---------------------------------------------------------------------------

/// On Windows, binaries are copied to INSTALL_DIR.
/// On macOS/Linux, the host binary sits next to the installer.
fn get_host_binary_path() -> Result<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        Ok(PathBuf::from(format!(
            "{INSTALL_DIR}\\sign-extension-host.exe"
        )))
    }
    #[cfg(not(target_os = "windows"))]
    {
        let exe_dir = std::env::current_exe()?
            .parent()
            .ok_or_else(|| anyhow!("Cannot determine exe directory"))?
            .to_path_buf();
        Ok(exe_dir.join("sign-extension-host"))
    }
}

// ---------------------------------------------------------------------------
// Native messaging manifest paths
// ---------------------------------------------------------------------------

struct ManifestTarget {
    browser: &'static str,
    path: PathBuf,
    use_allowed_extensions: bool, // Firefox uses allowed_extensions, Chrome uses allowed_origins
}

fn get_manifest_targets() -> Vec<ManifestTarget> {
    let mut targets = Vec::new();
    let home = dirs_home();

    #[cfg(target_os = "macos")]
    {
        // Chrome
        let chrome_dir = home.join("Library/Application Support/Google/Chrome/NativeMessagingHosts");
        targets.push(ManifestTarget {
            browser: "Chrome",
            path: chrome_dir.join(format!("{NATIVE_HOST_NAME}.json")),
            use_allowed_extensions: false,
        });
        // Firefox
        let firefox_dir =
            home.join("Library/Application Support/Mozilla/NativeMessagingHosts");
        targets.push(ManifestTarget {
            browser: "Firefox",
            path: firefox_dir.join(format!("{NATIVE_HOST_NAME}.json")),
            use_allowed_extensions: true,
        });
        // Edge
        let edge_dir =
            home.join("Library/Application Support/Microsoft/Edge/NativeMessagingHosts");
        targets.push(ManifestTarget {
            browser: "Edge",
            path: edge_dir.join(format!("{NATIVE_HOST_NAME}.json")),
            use_allowed_extensions: false,
        });
    }

    #[cfg(target_os = "linux")]
    {
        // Chrome
        targets.push(ManifestTarget {
            browser: "Chrome",
            path: home.join(format!(
                ".config/google-chrome/NativeMessagingHosts/{NATIVE_HOST_NAME}.json"
            )),
            use_allowed_extensions: false,
        });
        // Chromium
        targets.push(ManifestTarget {
            browser: "Chromium",
            path: home.join(format!(
                ".config/chromium/NativeMessagingHosts/{NATIVE_HOST_NAME}.json"
            )),
            use_allowed_extensions: false,
        });
        // Snap Chromium
        targets.push(ManifestTarget {
            browser: "Chromium (snap)",
            path: home.join(format!(
                "snap/chromium/common/chromium/NativeMessagingHosts/{NATIVE_HOST_NAME}.json"
            )),
            use_allowed_extensions: false,
        });
        // Firefox
        targets.push(ManifestTarget {
            browser: "Firefox",
            path: home.join(format!(
                ".mozilla/native-messaging-hosts/{NATIVE_HOST_NAME}.json"
            )),
            use_allowed_extensions: true,
        });
        // Edge
        targets.push(ManifestTarget {
            browser: "Edge",
            path: home.join(format!(
                ".config/microsoft-edge/NativeMessagingHosts/{NATIVE_HOST_NAME}.json"
            )),
            use_allowed_extensions: false,
        });
    }

    #[cfg(target_os = "windows")]
    {
        // Windows uses registry keys; manifests go in a local directory
        let local_app_data = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| {
            format!(
                "C:\\Users\\{}\\AppData\\Local",
                std::env::var("USERNAME").unwrap_or_default()
            )
        });
        targets.push(ManifestTarget {
            browser: "Chrome/Edge",
            path: PathBuf::from(format!(
                "{local_app_data}\\Sign Extension\\{NATIVE_HOST_NAME}.json"
            )),
            use_allowed_extensions: false,
        });
        targets.push(ManifestTarget {
            browser: "Firefox",
            path: PathBuf::from(format!(
                "{local_app_data}\\Sign Extension\\{NATIVE_HOST_NAME}-firefox.json"
            )),
            use_allowed_extensions: true,
        });
    }

    targets
}

fn dirs_home() -> PathBuf {
    std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/"))
}

// ---------------------------------------------------------------------------
// Install
// ---------------------------------------------------------------------------

fn install() -> Result<()> {
    println!("Installing Sign Extension FIDO Bridge...");

    let host_path = get_host_binary_path()?;

    #[cfg(target_os = "windows")]
    {
        // Copy binaries to install directory
        println!("  Creating install directory: {INSTALL_DIR}");
        std::fs::create_dir_all(INSTALL_DIR)?;

        let exe_dir = std::env::current_exe()?
            .parent()
            .ok_or_else(|| anyhow!("Cannot determine exe directory"))?
            .to_path_buf();

        for name in [
            "sign-extension-service.exe",
            "sign-extension-host.exe",
            "sign-extension-installer.exe",
        ] {
            let src = exe_dir.join(name);
            let dst = format!("{INSTALL_DIR}\\{name}");
            if src.exists() {
                println!("  Copying {name} -> {dst}");
                std::fs::copy(&src, &dst)?;
            } else {
                println!("  Warning: {name} not found at {}", src.display());
            }
        }

        // Set up user-session startup (--gui mode).
        // A Windows service (Session 0) cannot access USB HID devices, so we
        // run the FIDO backend in the interactive user session via a Run key.
        println!("  Configuring user-session startup");
        create_startup_entry()?;
    }

    // Verify host binary exists
    if !host_path.exists() {
        return Err(anyhow!(
            "Host binary not found at {}. Build it first with: cargo build -p sign-extension-host --release",
            host_path.display()
        ));
    }

    // Write native messaging manifests
    let targets = get_manifest_targets();
    for target in &targets {
        write_manifest(target, &host_path)?;
    }

    // Windows: register in browser registry
    #[cfg(target_os = "windows")]
    {
        println!("  Registering native messaging host in browser registry");
        register_native_host()?;
    }

    // Linux: install udev rules
    #[cfg(target_os = "linux")]
    install_udev_rules()?;

    println!();
    println!("Installation complete!");
    println!(
        "Host binary: {}",
        host_path.display()
    );
    println!("Load the extension in your browser and it will connect to the native host.");
    Ok(())
}

fn write_manifest(target: &ManifestTarget, host_path: &Path) -> Result<()> {
    // Only write if the browser's config directory exists (browser is installed)
    let parent = target
        .path
        .parent()
        .ok_or_else(|| anyhow!("Cannot determine manifest directory"))?;

    // For NativeMessagingHosts dirs, check if the grandparent exists (browser config dir)
    // to avoid creating dirs for browsers that aren't installed
    let browser_dir = parent.parent().unwrap_or(parent);
    if !browser_dir.exists() {
        println!(
            "  Skipping {} (not installed: {} not found)",
            target.browser,
            browser_dir.display()
        );
        return Ok(());
    }

    std::fs::create_dir_all(parent)?;

    let host_path_str = host_path.to_string_lossy();
    let manifest = if target.use_allowed_extensions {
        serde_json::json!({
            "name": NATIVE_HOST_NAME,
            "description": "previewSign FIDO Bridge Native Host",
            "path": host_path_str,
            "type": "stdio",
            "allowed_extensions": [FIREFOX_EXTENSION_ID]
        })
    } else {
        serde_json::json!({
            "name": NATIVE_HOST_NAME,
            "description": "previewSign FIDO Bridge Native Host",
            "path": host_path_str,
            "type": "stdio",
            "allowed_origins": [format!("chrome-extension://{EXTENSION_ID}/")]
        })
    };

    std::fs::write(&target.path, serde_json::to_string_pretty(&manifest)?)?;
    println!("  {} manifest: {}", target.browser, target.path.display());
    info!("Manifest written to {}", target.path.display());
    Ok(())
}

// ---------------------------------------------------------------------------
// Uninstall
// ---------------------------------------------------------------------------

fn uninstall() -> Result<()> {
    println!("Uninstalling Sign Extension FIDO Bridge...");

    #[cfg(target_os = "windows")]
    {
        // Remove startup entry and kill running instance
        println!("  Removing user-session startup entry");
        remove_startup_entry()?;
        // Also clean up legacy Windows service if present
        delete_service()?;

        // Remove registry keys
        println!("  Removing native messaging host registry keys");
        unregister_native_host()?;
    }

    // Remove native messaging manifests
    let targets = get_manifest_targets();
    for target in &targets {
        if target.path.exists() {
            std::fs::remove_file(&target.path)?;
            println!("  Removed {} manifest: {}", target.browser, target.path.display());
        }
    }

    #[cfg(target_os = "windows")]
    {
        // Remove binaries
        println!("  Removing install directory: {INSTALL_DIR}");
        if Path::new(INSTALL_DIR).exists() {
            let _ = std::fs::remove_dir_all(INSTALL_DIR);
        }
    }

    println!();
    println!("Uninstallation complete!");
    Ok(())
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

fn status() -> Result<()> {
    println!("Sign Extension FIDO Bridge Status");
    println!("=================================");

    let host_path = get_host_binary_path()?;
    println!(
        "Host binary:    {} ({})",
        if host_path.exists() { "present" } else { "MISSING" },
        host_path.display()
    );

    #[cfg(target_os = "windows")]
    {
        let service_exe = format!("{INSTALL_DIR}\\sign-extension-service.exe");
        println!(
            "Service binary: {}",
            if Path::new(&service_exe).exists() {
                "present"
            } else {
                "MISSING"
            }
        );
        println!(
            "Startup entry:  {}",
            check_startup_entry().unwrap_or_else(|e| format!("Error: {e}"))
        );
        println!(
            "Service proc:   {}",
            if is_service_running() { "RUNNING" } else { "not running" }
        );
    }

    // Check native messaging manifests
    let targets = get_manifest_targets();
    for target in &targets {
        let status = if target.path.exists() {
            "present"
        } else {
            "not installed"
        };
        println!("  {:15} {}", format!("{}:", target.browser), status);
    }

    #[cfg(target_os = "windows")]
    {
        println!(
            "Chrome NM key:  {}",
            check_registry_key("Google\\Chrome").unwrap_or_else(|_| "not set".into())
        );
        println!(
            "Edge NM key:    {}",
            check_registry_key("Microsoft\\Edge").unwrap_or_else(|_| "not set".into())
        );
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Linux: udev rules
// ---------------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn install_udev_rules() -> Result<()> {
    let rules_path = Path::new("/etc/udev/rules.d/70-sign-extension-fido.rules");
    let rules = r#"# FIDO2 HID devices — allow access for users in plugdev group
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1050", MODE="0660", GROUP="plugdev", TAG+="uaccess"
"#;

    // Check if we can write (need root)
    match std::fs::write(rules_path, rules) {
        Ok(()) => {
            println!("  udev rules: installed to {}", rules_path.display());
            // Reload rules
            let _ = std::process::Command::new("udevadm")
                .args(["control", "--reload-rules"])
                .status();
            let _ = std::process::Command::new("udevadm")
                .args(["trigger"])
                .status();
        }
        Err(e) => {
            if e.kind() == std::io::ErrorKind::PermissionDenied {
                println!("  udev rules: skipped (run with sudo for HID access rules)");
                println!("    To install manually:");
                println!("    sudo tee {} << 'EOF'", rules_path.display());
                println!("    {}", rules.trim());
                println!("    EOF");
                println!("    sudo udevadm control --reload-rules && sudo udevadm trigger");
            } else {
                return Err(e.into());
            }
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Windows service management
// ---------------------------------------------------------------------------

/// Add a Run registry entry so the FIDO service starts in the user's session at logon.
#[cfg(target_os = "windows")]
fn create_startup_entry() -> Result<()> {
    use windows::core::*;
    use windows::Win32::System::Registry::*;

    let service_exe = format!("{INSTALL_DIR}\\sign-extension-service.exe");
    let command = format!("\"{service_exe}\" --gui");

    unsafe {
        let key_name = HSTRING::from("Software\\Microsoft\\Windows\\CurrentVersion\\Run");
        let mut hkey = HKEY::default();
        let result = RegCreateKeyExW(
            HKEY_CURRENT_USER,
            &key_name,
            0,
            None,
            REG_OPTION_NON_VOLATILE,
            KEY_WRITE,
            None,
            &mut hkey,
            None,
        );
        if result.is_err() {
            return Err(anyhow!("Failed to open Run registry key: {result:?}"));
        }

        let value_name = HSTRING::from("SignExtensionFido");
        let value = HSTRING::from(command.as_str());
        let value_bytes = value.as_wide();
        let byte_slice = std::slice::from_raw_parts(
            value_bytes.as_ptr() as *const u8,
            (value_bytes.len() + 1) * 2,
        );

        let _ = RegSetValueExW(hkey, &value_name, 0, REG_SZ, Some(byte_slice));
        let _ = RegCloseKey(hkey);
    }

    println!("    Startup entry: {command}");
    Ok(())
}

#[cfg(target_os = "windows")]
fn remove_startup_entry() -> Result<()> {
    use windows::core::*;
    use windows::Win32::System::Registry::*;

    // Kill any running instance
    let _ = std::process::Command::new("taskkill")
        .args(["/f", "/im", "sign-extension-service.exe"])
        .output();

    unsafe {
        let key_name = HSTRING::from("Software\\Microsoft\\Windows\\CurrentVersion\\Run");
        let mut hkey = HKEY::default();
        let result = RegOpenKeyExW(
            HKEY_CURRENT_USER,
            &key_name,
            0,
            KEY_WRITE,
            &mut hkey,
        );
        if result.is_ok() {
            let value_name = HSTRING::from("SignExtensionFido");
            let _ = RegDeleteValueW(hkey, &value_name);
            let _ = RegCloseKey(hkey);
        }
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn check_startup_entry() -> Result<String> {
    use windows::core::*;
    use windows::Win32::System::Registry::*;

    unsafe {
        let key_name = HSTRING::from("Software\\Microsoft\\Windows\\CurrentVersion\\Run");
        let mut hkey = HKEY::default();
        let result = RegOpenKeyExW(
            HKEY_CURRENT_USER,
            &key_name,
            0,
            KEY_READ,
            &mut hkey,
        );
        if result.is_err() {
            return Ok("not configured".into());
        }

        let value_name = HSTRING::from("SignExtensionFido");
        let mut data_type = REG_VALUE_TYPE::default();
        let mut buf = [0u8; 1024];
        let mut buf_len = buf.len() as u32;
        let result = RegQueryValueExW(
            hkey,
            &value_name,
            None,
            Some(&mut data_type),
            Some(buf.as_mut_ptr()),
            Some(&mut buf_len),
        );
        let _ = RegCloseKey(hkey);

        if result.is_ok() {
            let wide: &[u16] = std::slice::from_raw_parts(
                buf.as_ptr() as *const u16,
                buf_len as usize / 2,
            );
            let s = String::from_utf16_lossy(wide).trim_end_matches('\0').to_string();
            Ok(format!("configured: {s}"))
        } else {
            Ok("not configured".into())
        }
    }
}

#[cfg(target_os = "windows")]
fn is_service_running() -> bool {
    let output = std::process::Command::new("tasklist")
        .args(["/fi", "IMAGENAME eq sign-extension-service.exe", "/nh"])
        .output();
    match output {
        Ok(o) => String::from_utf8_lossy(&o.stdout).contains("sign-extension-service"),
        Err(_) => false,
    }
}

#[cfg(target_os = "windows")]
fn delete_service() -> Result<()> {
    use std::process::Command;

    let _ = Command::new("sc").args(["stop", SERVICE_NAME]).output();
    let output = Command::new("sc")
        .args(["delete", SERVICE_NAME])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        if !stderr.contains("does not exist") {
            println!("    Warning: sc delete: {stderr}");
        }
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn register_native_host() -> Result<()> {
    use windows::core::*;
    use windows::Win32::System::Registry::*;

    let targets = get_manifest_targets();
    let chrome_manifest_path = targets
        .iter()
        .find(|t| t.browser == "Chrome/Edge")
        .map(|t| t.path.to_string_lossy().to_string())
        .unwrap_or_default();
    let firefox_manifest_path = targets
        .iter()
        .find(|t| t.browser == "Firefox")
        .map(|t| t.path.to_string_lossy().to_string())
        .unwrap_or_default();

    let browsers = [
        (
            "Google\\Chrome",
            "Software\\Google\\Chrome\\NativeMessagingHosts",
            &chrome_manifest_path,
        ),
        (
            "Microsoft\\Edge",
            "Software\\Microsoft\\Edge\\NativeMessagingHosts",
            &chrome_manifest_path,
        ),
        (
            "Mozilla",
            "Software\\Mozilla\\NativeMessagingHosts",
            &firefox_manifest_path,
        ),
    ];

    for (name, key_path, manifest) in &browsers {
        let full_path = format!("{key_path}\\{NATIVE_HOST_NAME}");
        println!("    Setting registry: HKCU\\{full_path}");

        unsafe {
            let key_name = HSTRING::from(full_path.as_str());
            let mut hkey = HKEY::default();
            let result = RegCreateKeyExW(
                HKEY_CURRENT_USER,
                &key_name,
                0,
                None,
                REG_OPTION_NON_VOLATILE,
                KEY_WRITE,
                None,
                &mut hkey,
                None,
            );

            if result.is_err() {
                println!("    Warning: Failed to create registry key for {name}: {result:?}");
                continue;
            }

            let value = HSTRING::from(manifest.as_str());
            let value_bytes = value.as_wide();
            let byte_slice = std::slice::from_raw_parts(
                value_bytes.as_ptr() as *const u8,
                (value_bytes.len() + 1) * 2,
            );

            let _ = RegSetValueExW(hkey, None, 0, REG_SZ, Some(byte_slice));

            let _ = RegCloseKey(hkey);
        }
    }

    Ok(())
}

#[cfg(target_os = "windows")]
fn unregister_native_host() -> Result<()> {
    use windows::core::*;
    use windows::Win32::System::Registry::*;

    let keys = [
        format!("Software\\Google\\Chrome\\NativeMessagingHosts\\{NATIVE_HOST_NAME}"),
        format!("Software\\Microsoft\\Edge\\NativeMessagingHosts\\{NATIVE_HOST_NAME}"),
        format!("Software\\Mozilla\\NativeMessagingHosts\\{NATIVE_HOST_NAME}"),
    ];

    for key_path in &keys {
        unsafe {
            let key_name = HSTRING::from(key_path.as_str());
            let _ = RegDeleteKeyW(HKEY_CURRENT_USER, &key_name);
        }
    }

    Ok(())
}

#[cfg(target_os = "windows")]
fn check_registry_key(_browser: &str) -> Result<String> {
    let targets = get_manifest_targets();
    if let Some(target) = targets.first() {
        if target.path.exists() {
            return Ok("configured".into());
        }
    }
    Ok("not configured".into())
}
