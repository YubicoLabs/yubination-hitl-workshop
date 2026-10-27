use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::thread::JoinHandle;
use log::{info, warn};

/// Set when the user closes a status window (X button / Alt+F4 / Cancel).
/// NOT set on programmatic dismiss (operation completed).
static USER_CANCELLED: AtomicBool = AtomicBool::new(false);

/// Generation counter to prevent stale dismiss calls from closing a newer window.
static GENERATION: AtomicU64 = AtomicU64::new(0);

/// Check if the user dismissed the status window.
pub fn was_user_cancelled() -> bool {
    USER_CANCELLED.load(Ordering::Relaxed)
}

/// Reset the cancel flag (call before starting a new FIDO operation).
pub fn reset_user_cancelled() {
    USER_CANCELLED.store(false, Ordering::Relaxed);
}

use windows::core::PCWSTR;
use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, WPARAM};
use windows::Win32::Graphics::Gdi::{
    CreateFontW, UpdateWindow, CLIP_DEFAULT_PRECIS, DEFAULT_CHARSET, DEFAULT_QUALITY,
    FF_SWISS, HFONT, OUT_DEFAULT_PRECIS,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Threading::GetCurrentThreadId;
use windows::Win32::UI::Input::KeyboardAndMouse::EnableWindow;
use windows::Win32::UI::WindowsAndMessaging::*;

pub enum StatusNotification {
    PinInvalid { retries: Option<u8> },
}

// Custom message to dismiss the status window from another thread.
const WM_STATUS_DISMISS: u32 = 0x0401;

// Cancel button control ID (matches IDCANCEL = 2 so Escape works with IsDialogMessageW)
const ID_CANCEL: i32 = 2;
// Control IDs for child windows
const ID_ICON_LABEL: i32 = 100;
const ID_MESSAGE_LABEL: i32 = 101;

static STATUS_WINDOW: Mutex<Option<StatusWindowState>> = Mutex::new(None);

struct StatusWindowState {
    hwnd: HWND,
    label_hwnd: HWND,
    icon_hwnd: HWND,
    thread: Option<JoinHandle<()>>,
    generation: u64,
}

// HWND contains a raw pointer, but we only access it while holding the Mutex.
unsafe impl Send for StatusWindowState {}

fn to_wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Request rounded window corners on Windows 11+. Silently no-ops on Win10.
fn apply_rounded_corners(hwnd: HWND) {
    use windows::Win32::Graphics::Dwm::{DwmSetWindowAttribute, DWMWA_WINDOW_CORNER_PREFERENCE};
    let preference: u32 = 2; // DWMWCP_ROUND
    unsafe {
        let _ = DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            &preference as *const _ as *const std::ffi::c_void,
            std::mem::size_of::<u32>() as u32,
        );
    }
}

/// Create a Segoe UI font handle at the given size (in logical pixels).
fn create_ui_font(size: i32) -> HFONT {
    let face = to_wide("Segoe UI");
    unsafe {
        CreateFontW(
            size,              // height
            0,                 // width (auto)
            0,                 // escapement
            0,                 // orientation
            400,               // weight (FW_NORMAL = 400)
            0,                 // italic
            0,                 // underline
            0,                 // strikeout
            DEFAULT_CHARSET.0 as u32,
            OUT_DEFAULT_PRECIS.0 as u32,
            CLIP_DEFAULT_PRECIS.0 as u32,
            DEFAULT_QUALITY.0 as u32,
            FF_SWISS.0 as u32,
            PCWSTR(face.as_ptr()),
        )
    }
}

/// Create a large emoji font for the icon area.
fn create_emoji_font(size: i32) -> HFONT {
    let face = to_wide("Segoe UI Emoji");
    unsafe {
        CreateFontW(
            size, 0, 0, 0, 400, 0, 0, 0,
            DEFAULT_CHARSET.0 as u32,
            OUT_DEFAULT_PRECIS.0 as u32,
            CLIP_DEFAULT_PRECIS.0 as u32,
            DEFAULT_QUALITY.0 as u32,
            FF_SWISS.0 as u32,
            PCWSTR(face.as_ptr()),
        )
    }
}

/// Set a font on a child control via WM_SETFONT.
fn set_font(hwnd: HWND, font: HFONT) {
    unsafe {
        SendMessageW(hwnd, WM_SETFONT, WPARAM(font.0 as usize), LPARAM(1));
    }
}

fn id_to_hmenu(id: i32) -> HMENU {
    HMENU(id as isize as *mut std::ffi::c_void)
}

/// Compute (x, y) to center a dialog of size (w, h) on the owner window.
/// Falls back to CW_USEDEFAULT if there's no owner or GetWindowRect fails.
fn center_on_owner(owner: HWND, w: i32, h: i32) -> (i32, i32) {
    if owner == HWND::default() {
        return (CW_USEDEFAULT, CW_USEDEFAULT);
    }
    let mut rect = RECT::default();
    if unsafe { GetWindowRect(owner, &mut rect) }.is_err() {
        return (CW_USEDEFAULT, CW_USEDEFAULT);
    }
    let cx = (rect.left + rect.right) / 2;
    let cy = (rect.top + rect.bottom) / 2;
    (cx - w / 2, cy - h / 2)
}

/// Choose an emoji for the status message based on its content.
fn status_emoji(message: &str) -> &'static str {
    let lower = message.to_lowercase();
    if lower.contains("touch") || lower.contains("tap") || lower.contains("multiple") {
        "\u{261D}\u{FE0F}" // index finger pointing up (touch gesture)
    } else if lower.contains("insert") || lower.contains("plug") {
        "\u{1F511}" // key
    } else if lower.contains("fingerprint") || lower.contains("biometric") {
        "\u{1F300}" // cyclone — swirl pattern resembles a fingerprint
    } else {
        "\u{1F510}" // lock with key
    }
}

/// Window procedure for the status window.
unsafe extern "system" fn status_wndproc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_CREATE => LRESULT(0),
        WM_CLOSE => {
            // User clicked X or pressed Alt+F4 — signal cancellation
            USER_CANCELLED.store(true, Ordering::Relaxed);
            PostQuitMessage(0);
            LRESULT(0)
        }
        WM_COMMAND => {
            let id = (wparam.0 & 0xFFFF) as i32;
            let notification = ((wparam.0 >> 16) & 0xFFFF) as u16;
            // BN_CLICKED = 0, or IDCANCEL from Escape via IsDialogMessageW
            if notification == 0 && id == ID_CANCEL {
                USER_CANCELLED.store(true, Ordering::Relaxed);
                PostQuitMessage(0);
            }
            LRESULT(0)
        }
        _ if msg == WM_STATUS_DISMISS => {
            PostQuitMessage(0);
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

/// Show the status window with the given message, or update it if already showing.
/// If `owner_hwnd` is provided, the window is created as owned by (modal to) that window.
pub fn show_status_window(message: &str, owner_hwnd: Option<usize>) {
    let current_gen = GENERATION.fetch_add(1, Ordering::SeqCst) + 1;

    let mut state = match STATUS_WINDOW.lock() {
        Ok(s) => s,
        Err(_) => return,
    };

    if let Some(ref s) = *state {
        // Window already exists — update the label text and icon
        let wide = to_wide(message);
        let icon_text = to_wide(status_emoji(message));
        unsafe {
            let _ = SetWindowTextW(s.label_hwnd, PCWSTR(wide.as_ptr()));
            let _ = SetWindowTextW(s.icon_hwnd, PCWSTR(icon_text.as_ptr()));
        }
        // Update the generation so a stale dismiss won't close this window
        // (we need mutable access — take the state and put it back)
        if let Some(mut s) = state.take() {
            s.generation = current_gen;
            *state = Some(s);
        }
        return;
    }

    // Spawn a new thread to own the status window and its message loop.
    let msg_text = message.to_string();
    let (tx, rx) = std::sync::mpsc::channel::<Option<(usize, usize, usize)>>();

    let thread = std::thread::spawn(move || {
        let class_name = to_wide("SignExtStatusWindow");
        let window_title = to_wide("Security Key");
        let msg_wide = to_wide(&msg_text);
        let static_class = to_wide("STATIC");
        let button_class = to_wide("BUTTON");
        let cancel_text = to_wide("Cancel");
        let icon_text = to_wide(status_emoji(&msg_text));

        unsafe {
            let hmodule = match GetModuleHandleW(PCWSTR::null()).ok() {
                Some(h) => h,
                None => {
                    let _ = tx.send(None);
                    return;
                }
            };
            let hinstance: HINSTANCE = hmodule.into();

            let wc = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                style: CS_HREDRAW | CS_VREDRAW,
                lpfnWndProc: Some(status_wndproc),
                hInstance: hinstance,
                hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                lpszClassName: PCWSTR(class_name.as_ptr()),
                ..Default::default()
            };

            RegisterClassExW(&wc);

            let owner = owner_hwnd
                .map(|h| HWND(h as *mut std::ffi::c_void))
                .unwrap_or_default();
            let ex_style = if owner_hwnd.is_some() {
                WINDOW_EX_STYLE::default()
            } else {
                WS_EX_TOPMOST
            };

            // Dialog dimensions
            let (dlg_w, dlg_h) = (440, 170);
            let (x, y) = center_on_owner(owner, dlg_w, dlg_h);

            let hwnd = match CreateWindowExW(
                ex_style,
                PCWSTR(class_name.as_ptr()),
                PCWSTR(window_title.as_ptr()),
                WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
                x, y,
                dlg_w, dlg_h,
                owner,
                HMENU::default(),
                hinstance,
                None,
            ) {
                Ok(h) => h,
                Err(e) => {
                    warn!("CreateWindowExW for status window failed: {e}");
                    let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
                    let _ = tx.send(None);
                    return;
                }
            };

            // Protect against screen capture (WDA_EXCLUDEFROMCAPTURE = 0x11)
            let _ = SetWindowDisplayAffinity(hwnd, WINDOW_DISPLAY_AFFINITY(0x11));

            // Rounded corners on Windows 11+
            apply_rounded_corners(hwnd);

            // Disable the owner window to make our dialog modal
            if owner != HWND::default() {
                let _ = EnableWindow(owner, false);
            }

            // Create fonts
            let emoji_font = create_emoji_font(36);
            let text_font = create_ui_font(16);
            let button_font = create_ui_font(14);

            // Emoji icon on the left
            let icon_hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                PCWSTR(static_class.as_ptr()),
                PCWSTR(icon_text.as_ptr()),
                WS_CHILD | WS_VISIBLE | WINDOW_STYLE(0x0001), // SS_CENTER
                15, 15,
                50, 50,
                hwnd,
                id_to_hmenu(ID_ICON_LABEL),
                hinstance,
                None,
            ).unwrap_or_default();
            set_font(icon_hwnd, emoji_font);

            // Message text to the right of the icon
            let label_hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                PCWSTR(static_class.as_ptr()),
                PCWSTR(msg_wide.as_ptr()),
                WS_CHILD | WS_VISIBLE,
                75, 20,
                340, 50,
                hwnd,
                id_to_hmenu(ID_MESSAGE_LABEL),
                hinstance,
                None,
            ).unwrap_or_default();
            set_font(label_hwnd, text_font);

            // Cancel button centered at bottom
            let cancel_hwnd = CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                PCWSTR(button_class.as_ptr()),
                PCWSTR(cancel_text.as_ptr()),
                WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                175, 90,
                90, 30,
                hwnd,
                id_to_hmenu(ID_CANCEL),
                hinstance,
                None,
            ).unwrap_or_default();
            set_font(cancel_hwnd, button_font);

            let _ = ShowWindow(hwnd, SW_SHOW);
            let _ = UpdateWindow(hwnd);

            // Bring to foreground using AttachThreadInput
            let fg_hwnd = GetForegroundWindow();
            if fg_hwnd != HWND::default() {
                let fg_thread = GetWindowThreadProcessId(fg_hwnd, None);
                let our_thread = GetCurrentThreadId();
                if fg_thread != 0 && fg_thread != our_thread {
                    let _ = windows::Win32::System::Threading::AttachThreadInput(
                        our_thread, fg_thread, true,
                    );
                    let _ = SetForegroundWindow(hwnd);
                    let _ = windows::Win32::System::Threading::AttachThreadInput(
                        our_thread, fg_thread, false,
                    );
                } else {
                    let _ = SetForegroundWindow(hwnd);
                }
            } else {
                let _ = SetForegroundWindow(hwnd);
            }

            // Send HWNDs back to the caller (as usize for Send)
            let _ = tx.send(Some((hwnd.0 as usize, label_hwnd.0 as usize, icon_hwnd.0 as usize)));

            // Message loop — runs until WM_CLOSE, Cancel, Escape, or WM_STATUS_DISMISS
            let mut msg = MSG::default();
            while GetMessageW(&mut msg, HWND::default(), 0, 0).as_bool() {
                // IsDialogMessageW converts Escape to WM_COMMAND(IDCANCEL)
                if !IsDialogMessageW(hwnd, &msg).as_bool() {
                    let _ = TranslateMessage(&msg);
                    DispatchMessageW(&msg);
                }
            }

            // Re-enable the owner window before destroying our window
            if owner != HWND::default() {
                let _ = EnableWindow(owner, true);
                let _ = SetForegroundWindow(owner);
            }

            let _ = DestroyWindow(hwnd);
            let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
        }
    });

    // Wait for the window thread to create the window and send us the HWNDs
    match rx.recv() {
        Ok(Some((hwnd_raw, label_raw, icon_raw))) => {
            *state = Some(StatusWindowState {
                hwnd: HWND(hwnd_raw as *mut std::ffi::c_void),
                label_hwnd: HWND(label_raw as *mut std::ffi::c_void),
                icon_hwnd: HWND(icon_raw as *mut std::ffi::c_void),
                thread: Some(thread),
                generation: current_gen,
            });
        }
        _ => {
            warn!("Failed to create status window");
        }
    }
}

/// Dismiss the status window if it's showing.
pub fn dismiss_status_window() {
    let current_gen = GENERATION.load(Ordering::SeqCst);
    let thread = {
        let mut state = match STATUS_WINDOW.lock() {
            Ok(s) => s,
            Err(_) => return,
        };

        if let Some(ref s) = *state {
            // Only dismiss if this is the same generation (not a newer window)
            if s.generation != current_gen {
                return;
            }
        }

        if let Some(mut s) = state.take() {
            unsafe {
                let _ = PostMessageW(s.hwnd, WM_STATUS_DISMISS, WPARAM(0), LPARAM(0));
            }
            s.thread.take()
        } else {
            None
        }
    };

    if let Some(t) = thread {
        let _ = t.join();
    }
}

pub fn show_notification(notification: StatusNotification) {
    match notification {
        StatusNotification::PinInvalid { retries } => {
            let msg = match retries {
                Some(r) => format!("PIN invalid ({r} retries remaining)"),
                None => "PIN invalid".to_string(),
            };
            info!("{msg}");
            // PIN dialog handles this — no status window needed
        }
    }
}

pub fn dismiss_notification() {
    info!("Notification dismissed");
    dismiss_status_window();
}
