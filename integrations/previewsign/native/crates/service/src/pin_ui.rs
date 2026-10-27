use std::cell::Cell;
use std::sync::atomic::Ordering;
use std::sync::OnceLock;
use log::{info, warn};
use zeroize::Zeroizing;

thread_local! {
    /// Minimum PIN length for the current dialog (set before showing, read by wndproc).
    static MIN_PIN_LENGTH: Cell<usize> = const { Cell::new(4) };
    static DIALOG_FAILURE: Cell<Option<(&'static str, u32)>> = const { Cell::new(None) };
    #[cfg(test)]
    static TEST_CANCEL_HIDDEN: Cell<bool> = const { Cell::new(false) };
    #[cfg(test)]
    static TEST_CREATED: Cell<usize> = const { Cell::new(0) };
}

pub fn take_dialog_failure() -> Option<(&'static str, u32)> {
    DIALOG_FAILURE.with(Cell::take)
}

pub(crate) fn record_dialog_failure(stage: &'static str, code: u32) {
    DIALOG_FAILURE.with(|failure| failure.set(Some((stage, code))));
    warn!("Windows PIN dialog unavailable: stage={stage}, Win32={code}");
}

use windows::core::PCWSTR;
use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, WPARAM};
use windows::Win32::Graphics::Gdi::{
    CreateFontW, UpdateWindow, CLIP_DEFAULT_PRECIS, DEFAULT_CHARSET, DEFAULT_QUALITY,
    FF_SWISS, HFONT, OUT_DEFAULT_PRECIS,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Input::KeyboardAndMouse::{EnableWindow, SetFocus};
use windows::Win32::UI::WindowsAndMessaging::*;
use windows::Win32::System::Threading::GetCurrentThreadId;

use crate::CONSOLE_MODE;

// Control IDs
const ID_LABEL: i32 = 100;
const ID_EDIT: i32 = 101;
const ID_OK: i32 = 1;     // IDOK
const ID_CANCEL: i32 = 2; // IDCANCEL
const ID_ICON: i32 = 103;
const ID_ERROR_LABEL: i32 = 104;

// Multi-field dialog control IDs
const ID_EDIT2: i32 = 111;     // Confirm PIN / New PIN
const ID_EDIT3: i32 = 112;     // Confirm New PIN (change dialog)
const ID_LABEL2: i32 = 121;
const ID_LABEL3: i32 = 122;

// Edit/button control styles (raw values to avoid Win32_UI_Controls feature)
const ES_PASSWORD: u32 = 0x0020;
const ES_AUTOHSCROLL: u32 = 0x0080;
const BS_DEFPUSHBUTTON: u32 = 0x0001;

// Dialog result stored in window's user data
const RESULT_OK: isize = 1;
const RESULT_CANCEL: isize = 2;

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

/// Create a Segoe UI font handle at the given size.
fn create_ui_font(size: i32) -> HFONT {
    let face = to_wide("Segoe UI");
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

/// Set a font on a child control.
fn set_font(hwnd: HWND, font: HFONT) {
    unsafe {
        SendMessageW(hwnd, WM_SETFONT, WPARAM(font.0 as usize), LPARAM(1));
    }
}

/// Compute (x, y) to center a dialog of size (w, h) on the owner window.
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

fn id_to_hmenu(id: i32) -> HMENU {
    HMENU(id as isize as *mut std::ffi::c_void)
}

/// Bring window to foreground using AttachThreadInput technique.
unsafe fn bring_to_foreground(hwnd: HWND, focus_hwnd: Option<HWND>) {
    let _ = ShowWindow(hwnd, SW_SHOW);
    let _ = UpdateWindow(hwnd);

    let fg_hwnd = GetForegroundWindow();
    if fg_hwnd != HWND::default() {
        let fg_thread = GetWindowThreadProcessId(fg_hwnd, None);
        let our_thread = GetCurrentThreadId();
        if fg_thread != 0 && fg_thread != our_thread {
            let _ = windows::Win32::System::Threading::AttachThreadInput(
                our_thread, fg_thread, true,
            );
            let _ = SetForegroundWindow(hwnd);
            if let Some(f) = focus_hwnd {
                let _ = SetFocus(f);
            }
            let _ = windows::Win32::System::Threading::AttachThreadInput(
                our_thread, fg_thread, false,
            );
        } else {
            let _ = SetForegroundWindow(hwnd);
            if let Some(f) = focus_hwnd {
                let _ = SetFocus(f);
            }
        }
    } else {
        let _ = SetForegroundWindow(hwnd);
        if let Some(f) = focus_hwnd {
            let _ = SetFocus(f);
        }
    }
}

/// Run the standard dialog message loop.
unsafe fn run_dialog_loop(hwnd: HWND) -> bool {
    let mut msg = MSG::default();
    loop {
        match GetMessageW(&mut msg, HWND::default(), 0, 0).0 {
            0 => return true,
            -1 => {
                record_dialog_failure("message-loop", std::io::Error::last_os_error().raw_os_error().unwrap_or(0) as u32);
                return false;
            }
            _ => {}
        }
        if !IsDialogMessageW(hwnd, &msg).as_bool() {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
}

/// Read text from an edit control, zero the control, return the text.
unsafe fn read_and_clear_edit(edit_hwnd: HWND) -> Option<Zeroizing<String>> {
    let empty = to_wide("");
    let len = GetWindowTextLengthW(edit_hwnd) as usize;
    if len > 0 {
        let mut buf = vec![0u16; len + 1];
        GetWindowTextW(edit_hwnd, &mut buf);
        // Zero out the edit control before reading
        let _ = SetWindowTextW(edit_hwnd, PCWSTR(empty.as_ptr()));
        let pin_str = String::from_utf16_lossy(&buf[..len]);
        for b in buf.iter_mut() {
            *b = 0;
        }
        Some(Zeroizing::new(pin_str))
    } else {
        None
    }
}

// ============================================================================
// Single-field PIN dialog (existing flow)
// ============================================================================

/// Window procedure for the single-field PIN dialog.
unsafe extern "system" fn pin_wndproc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_CREATE => LRESULT(0),
        WM_COMMAND => {
            let id = (wparam.0 & 0xFFFF) as i32;
            let notification = ((wparam.0 >> 16) & 0xFFFF) as u16;
            if notification == 0 {
                match id {
                    ID_OK => {
                        SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_OK);
                        PostQuitMessage(0);
                    }
                    ID_CANCEL => {
                        SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
                        PostQuitMessage(0);
                    }
                    _ => {}
                }
            }
            LRESULT(0)
        }
        WM_CLOSE => {
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
            PostQuitMessage(0);
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

/// Show a Win32 PIN dialog with screen-capture protection.
fn show_pin_dialog(prompt: &str, _owner_hwnd: Option<usize>) -> Option<Zeroizing<String>> {
    DIALOG_FAILURE.with(|failure| failure.set(None));
    static PIN_CLASS: OnceLock<Result<(), u32>> = OnceLock::new();
    let class_name = to_wide("SignExtPinDialog");
    let window_title = to_wide("Security Key PIN");
    let prompt_wide = to_wide(prompt);
    let ok_text = to_wide("OK");
    let cancel_text = to_wide("Cancel");
    let empty = to_wide("");
    let button_class = to_wide("BUTTON");
    let static_class = to_wide("STATIC");
    let edit_class = to_wide("EDIT");
    let icon_text = to_wide("\u{1F511}"); // key emoji

    unsafe {
        let hmodule = match GetModuleHandleW(PCWSTR::null()) {
            Ok(module) => module,
            Err(_) => {
                record_dialog_failure("module", std::io::Error::last_os_error().raw_os_error().unwrap_or(0) as u32);
                return None;
            }
        };
        let hinstance: HINSTANCE = hmodule.into();

        let wc = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(pin_wndproc),
            hInstance: hinstance,
            hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
            lpszClassName: PCWSTR(class_name.as_ptr()),
            ..Default::default()
        };

        // Register exactly our own class once; never accept an arbitrary
        // ERROR_CLASS_ALREADY_EXISTS collision as a successful registration.
        if let Err(code) = PIN_CLASS.get_or_init(|| {
            if RegisterClassExW(&wc) == 0 {
                Err(std::io::Error::last_os_error().raw_os_error().unwrap_or(0) as u32)
            } else {
                Ok(())
            }
        }) {
            record_dialog_failure("register-class", *code);
            return None;
        }

        // The elevated helper must not attach to or disable an unvalidated,
        // possibly stale foreground HWND captured from a medium browser.
        let owner = HWND::default();
        let ex_style = WS_EX_TOPMOST;

        let (dlg_w, dlg_h) = (440, 200);
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
            Err(_) => {
                record_dialog_failure("create-window", std::io::Error::last_os_error().raw_os_error().unwrap_or(0) as u32);
                return None;
            }
        };

        // Protect against screen capture
        let _ = SetWindowDisplayAffinity(hwnd, WINDOW_DISPLAY_AFFINITY(0x11));
        apply_rounded_corners(hwnd);

        if owner != HWND::default() {
            let _ = EnableWindow(owner, false);
        }

        // Create fonts
        let emoji_font = create_emoji_font(32);
        let text_font = create_ui_font(14);
        let button_font = create_ui_font(14);

        // Emoji icon
        let icon_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(icon_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WINDOW_STYLE(0x0001), // SS_CENTER
            15, 15,
            45, 40,
            hwnd,
            id_to_hmenu(ID_ICON),
            hinstance,
            None,
        ).unwrap_or_default();
        set_font(icon_hwnd, emoji_font);

        // Prompt label
        let label_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(prompt_wide.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 20, 350, 25,
            hwnd,
            id_to_hmenu(ID_LABEL),
            hinstance,
            None,
        ).unwrap_or_default();
        set_font(label_hwnd, text_font);

        // Password edit control
        let edit_hwnd = CreateWindowExW(
            WS_EX_CLIENTEDGE,
            PCWSTR(edit_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(ES_PASSWORD | ES_AUTOHSCROLL),
            70, 55, 340, 28,
            hwnd,
            id_to_hmenu(ID_EDIT),
            hinstance,
            None,
        ).unwrap_or_default();
        set_font(edit_hwnd, text_font);

        // OK button
        let ok_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(ok_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(BS_DEFPUSHBUTTON),
            225, 105, 85, 32,
            hwnd,
            id_to_hmenu(ID_OK),
            hinstance,
            None,
        ).unwrap_or_default();
        set_font(ok_hwnd, button_font);

        // Cancel button
        let cancel_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(cancel_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            325, 105, 85, 32,
            hwnd,
            id_to_hmenu(ID_CANCEL),
            hinstance,
            None,
        ).unwrap_or_default();
        set_font(cancel_hwnd, button_font);

        #[cfg(test)]
        let hidden_cancel = TEST_CANCEL_HIDDEN.with(Cell::get);
        #[cfg(not(test))]
        let hidden_cancel = false;
        if hidden_cancel {
            #[cfg(test)]
            TEST_CREATED.with(|count| count.set(count.get() + 1));
            let _ = PostMessageW(hwnd, WM_COMMAND, WPARAM(ID_CANCEL as usize), LPARAM(0));
        } else {
            // Do not join the input queue of an unrelated foreground process.
            let _ = ShowWindow(hwnd, SW_SHOW);
            let _ = UpdateWindow(hwnd);
            let _ = SetForegroundWindow(hwnd);
            let _ = SetFocus(edit_hwnd);
        }
        let loop_ok = run_dialog_loop(hwnd);

        // Read result
        let result_code = GetWindowLongPtrW(hwnd, GWLP_USERDATA);
        let pin = if loop_ok && result_code == RESULT_OK {
            read_and_clear_edit(edit_hwnd)
        } else {
            None
        };

        // Re-enable owner
        if owner != HWND::default() {
            let _ = EnableWindow(owner, true);
            let _ = SetForegroundWindow(owner);
        }

        if DestroyWindow(hwnd).is_err() {
            record_dialog_failure("destroy-window", std::io::Error::last_os_error().raw_os_error().unwrap_or(0) as u32);
            return None;
        }
        // Class is process-owned; unregistering between ceremonies is unsafe
        // when another worker can still be using the class.
        pin
    }
}

#[cfg(test)]
mod lifecycle_tests {
    use super::*;

    #[test]
    fn repeated_hidden_cancel_ignores_stale_foreground_owner() {
        // No device, no visibility, no PIN input. Keep all dialogs on one worker
        // to exercise class reuse and consumed WM_QUIT messages.
        std::thread::spawn(|| {
            TEST_CANCEL_HIDDEN.with(|flag| flag.set(true));
            for owner in [None, None, Some(usize::MAX)] {
                assert!(show_pin_dialog("Lifecycle test", owner).is_none());
                assert_eq!(take_dialog_failure(), None);
            }
            assert_eq!(TEST_CREATED.with(Cell::get), 3);
            assert_eq!(take_dialog_failure(), None);
        }).join().unwrap();
    }
}

// ============================================================================
// New PIN setup dialog (two fields: New PIN + Confirm)
// ============================================================================

/// Window procedure for the new PIN setup dialog.
/// Validates that both fields match on OK.
unsafe extern "system" fn pin_setup_wndproc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_CREATE => LRESULT(0),
        WM_COMMAND => {
            let id = (wparam.0 & 0xFFFF) as i32;
            let notification = ((wparam.0 >> 16) & 0xFFFF) as u16;
            if notification == 0 {
                match id {
                    ID_OK => {
                        // Validate that both fields match
                        let edit1 = GetDlgItem(hwnd, ID_EDIT).unwrap_or_default();
                        let edit2 = GetDlgItem(hwnd, ID_EDIT2).unwrap_or_default();
                        let error_label = GetDlgItem(hwnd, ID_ERROR_LABEL).unwrap_or_default();

                        let len1 = GetWindowTextLengthW(edit1) as usize;
                        let len2 = GetWindowTextLengthW(edit2) as usize;

                        if len1 == 0 {
                            let msg = to_wide("Please enter a PIN");
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let _ = SetFocus(edit1);
                            return LRESULT(0);
                        }

                        let mut buf1 = vec![0u16; len1 + 1];
                        let mut buf2 = vec![0u16; len2 + 1];
                        GetWindowTextW(edit1, &mut buf1);
                        GetWindowTextW(edit2, &mut buf2);

                        // Check PIN length constraints (UTF-8 byte length)
                        let pin_utf8_len = String::from_utf16_lossy(&buf1[..len1]).len();
                        let min_len = MIN_PIN_LENGTH.with(|c| c.get());
                        if pin_utf8_len < min_len {
                            let msg = to_wide(&format!("PIN must be at least {min_len} characters"));
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let _ = SetFocus(edit1);
                            for b in buf1.iter_mut() { *b = 0; }
                            for b in buf2.iter_mut() { *b = 0; }
                            return LRESULT(0);
                        }
                        if pin_utf8_len > 63 {
                            let msg = to_wide("PIN is too long (max 63 bytes)");
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let _ = SetFocus(edit1);
                            for b in buf1.iter_mut() { *b = 0; }
                            for b in buf2.iter_mut() { *b = 0; }
                            return LRESULT(0);
                        }

                        if buf1[..len1] != buf2[..len2] {
                            let msg = to_wide("PINs do not match");
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            // Clear confirm field and refocus
                            let empty = to_wide("");
                            let _ = SetWindowTextW(edit2, PCWSTR(empty.as_ptr()));
                            let _ = SetFocus(edit2);
                            // Zero buffers
                            for b in buf1.iter_mut() { *b = 0; }
                            for b in buf2.iter_mut() { *b = 0; }
                            return LRESULT(0);
                        }

                        // Zero buffers
                        for b in buf1.iter_mut() { *b = 0; }
                        for b in buf2.iter_mut() { *b = 0; }

                        SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_OK);
                        PostQuitMessage(0);
                    }
                    ID_CANCEL => {
                        SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
                        PostQuitMessage(0);
                    }
                    _ => {}
                }
            }
            LRESULT(0)
        }
        WM_CLOSE => {
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
            PostQuitMessage(0);
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

/// Show a dialog for setting up a new PIN (two fields: New + Confirm).
fn show_new_pin_dialog(prompt: &str, min_pin_length: usize, owner_hwnd: Option<usize>) -> Option<Zeroizing<String>> {
    MIN_PIN_LENGTH.with(|c| c.set(min_pin_length));
    let class_name = to_wide("SignExtPinSetupDialog");
    let window_title = to_wide("Set Up Security Key PIN");
    let prompt_wide = to_wide(prompt);
    let ok_text = to_wide("OK");
    let cancel_text = to_wide("Cancel");
    let empty = to_wide("");
    let button_class = to_wide("BUTTON");
    let static_class = to_wide("STATIC");
    let edit_class = to_wide("EDIT");
    let icon_text = to_wide("\u{1F511}"); // key emoji
    let label_new = to_wide("New PIN:");
    let label_confirm = to_wide("Confirm PIN:");

    unsafe {
        let hmodule = GetModuleHandleW(PCWSTR::null()).ok()?;
        let hinstance: HINSTANCE = hmodule.into();

        let wc = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(pin_setup_wndproc),
            hInstance: hinstance,
            hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
            lpszClassName: PCWSTR(class_name.as_ptr()),
            ..Default::default()
        };

        let atom = RegisterClassExW(&wc);
        if atom == 0 {
            warn!("RegisterClassExW failed: {}", std::io::Error::last_os_error());
            return None;
        }

        let owner = owner_hwnd
            .map(|h| HWND(h as *mut std::ffi::c_void))
            .unwrap_or_default();
        let ex_style = if owner_hwnd.is_some() {
            WINDOW_EX_STYLE::default()
        } else {
            WS_EX_TOPMOST
        };

        let (dlg_w, dlg_h) = (440, 280);
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
                warn!("CreateWindowExW failed: {e}");
                let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
                return None;
            }
        };

        let _ = SetWindowDisplayAffinity(hwnd, WINDOW_DISPLAY_AFFINITY(0x11));
        apply_rounded_corners(hwnd);

        if owner != HWND::default() {
            let _ = EnableWindow(owner, false);
        }

        let emoji_font = create_emoji_font(32);
        let text_font = create_ui_font(14);
        let small_font = create_ui_font(12);
        let button_font = create_ui_font(14);

        // Emoji icon
        let icon_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(icon_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WINDOW_STYLE(0x0001),
            15, 15, 45, 40,
            hwnd, id_to_hmenu(ID_ICON), hinstance, None,
        ).unwrap_or_default();
        set_font(icon_hwnd, emoji_font);

        // Prompt label
        let prompt_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(prompt_wide.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 20, 350, 25,
            hwnd, id_to_hmenu(ID_LABEL), hinstance, None,
        ).unwrap_or_default();
        set_font(prompt_hwnd, text_font);

        // "New PIN:" label
        let label2_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(label_new.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 58, 120, 20,
            hwnd, id_to_hmenu(ID_LABEL2), hinstance, None,
        ).unwrap_or_default();
        set_font(label2_hwnd, small_font);

        // New PIN edit
        let edit1_hwnd = CreateWindowExW(
            WS_EX_CLIENTEDGE,
            PCWSTR(edit_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(ES_PASSWORD | ES_AUTOHSCROLL),
            70, 78, 340, 28,
            hwnd, id_to_hmenu(ID_EDIT), hinstance, None,
        ).unwrap_or_default();
        set_font(edit1_hwnd, text_font);

        // "Confirm PIN:" label
        let label3_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(label_confirm.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 115, 120, 20,
            hwnd, id_to_hmenu(ID_LABEL3), hinstance, None,
        ).unwrap_or_default();
        set_font(label3_hwnd, small_font);

        // Confirm PIN edit
        let edit2_hwnd = CreateWindowExW(
            WS_EX_CLIENTEDGE,
            PCWSTR(edit_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(ES_PASSWORD | ES_AUTOHSCROLL),
            70, 135, 340, 28,
            hwnd, id_to_hmenu(ID_EDIT2), hinstance, None,
        ).unwrap_or_default();
        set_font(edit2_hwnd, text_font);

        // Error label (hidden initially)
        let error_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD, // not visible initially
            70, 168, 240, 20,
            hwnd, id_to_hmenu(ID_ERROR_LABEL), hinstance, None,
        ).unwrap_or_default();
        set_font(error_hwnd, small_font);
        // Note: We can't easily set text color to red without owner-draw.
        // The error message itself makes it clear.

        // OK button
        let ok_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(ok_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(BS_DEFPUSHBUTTON),
            225, 195, 85, 32,
            hwnd, id_to_hmenu(ID_OK), hinstance, None,
        ).unwrap_or_default();
        set_font(ok_hwnd, button_font);

        // Cancel button
        let cancel_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(cancel_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            325, 195, 85, 32,
            hwnd, id_to_hmenu(ID_CANCEL), hinstance, None,
        ).unwrap_or_default();
        set_font(cancel_hwnd, button_font);

        bring_to_foreground(hwnd, Some(edit1_hwnd));
        run_dialog_loop(hwnd);

        let result_code = GetWindowLongPtrW(hwnd, GWLP_USERDATA);
        let pin = if result_code == RESULT_OK {
            read_and_clear_edit(edit1_hwnd)
        } else {
            None
        };

        // Zero the confirm field too
        let _ = SetWindowTextW(edit2_hwnd, PCWSTR(empty.as_ptr()));

        if owner != HWND::default() {
            let _ = EnableWindow(owner, true);
            let _ = SetForegroundWindow(owner);
        }

        let _ = DestroyWindow(hwnd);
        let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
        pin
    }
}

// ============================================================================
// PIN change dialog (three fields: Current + New + Confirm New)
// ============================================================================

/// Window procedure for the PIN change dialog.
/// Validates that New and Confirm match on OK.
unsafe extern "system" fn pin_change_wndproc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_CREATE => LRESULT(0),
        WM_COMMAND => {
            let id = (wparam.0 & 0xFFFF) as i32;
            let notification = ((wparam.0 >> 16) & 0xFFFF) as u16;
            if notification == 0 {
                match id {
                    ID_OK => {
                        let edit_current = GetDlgItem(hwnd, ID_EDIT).unwrap_or_default();
                        let edit_new = GetDlgItem(hwnd, ID_EDIT2).unwrap_or_default();
                        let edit_confirm = GetDlgItem(hwnd, ID_EDIT3).unwrap_or_default();
                        let error_label = GetDlgItem(hwnd, ID_ERROR_LABEL).unwrap_or_default();

                        let len_cur = GetWindowTextLengthW(edit_current) as usize;
                        let len_new = GetWindowTextLengthW(edit_new) as usize;
                        let len_conf = GetWindowTextLengthW(edit_confirm) as usize;

                        if len_cur == 0 {
                            let msg = to_wide("Please enter current PIN");
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let _ = SetFocus(edit_current);
                            return LRESULT(0);
                        }
                        if len_new == 0 {
                            let msg = to_wide("Please enter new PIN");
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let _ = SetFocus(edit_new);
                            return LRESULT(0);
                        }

                        let mut buf_new = vec![0u16; len_new + 1];
                        let mut buf_conf = vec![0u16; len_conf + 1];
                        GetWindowTextW(edit_new, &mut buf_new);
                        GetWindowTextW(edit_confirm, &mut buf_conf);

                        // Check new PIN length constraints (UTF-8 byte length)
                        let pin_utf8_len = String::from_utf16_lossy(&buf_new[..len_new]).len();
                        let min_len = MIN_PIN_LENGTH.with(|c| c.get());
                        if pin_utf8_len < min_len {
                            let msg = to_wide(&format!("PIN must be at least {min_len} characters"));
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let _ = SetFocus(edit_new);
                            for b in buf_new.iter_mut() { *b = 0; }
                            for b in buf_conf.iter_mut() { *b = 0; }
                            return LRESULT(0);
                        }
                        if pin_utf8_len > 63 {
                            let msg = to_wide("PIN is too long (max 63 bytes)");
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let _ = SetFocus(edit_new);
                            for b in buf_new.iter_mut() { *b = 0; }
                            for b in buf_conf.iter_mut() { *b = 0; }
                            return LRESULT(0);
                        }

                        if buf_new[..len_new] != buf_conf[..len_conf] {
                            let msg = to_wide("New PINs do not match");
                            let _ = SetWindowTextW(error_label, PCWSTR(msg.as_ptr()));
                            let _ = ShowWindow(error_label, SW_SHOW);
                            let empty = to_wide("");
                            let _ = SetWindowTextW(edit_confirm, PCWSTR(empty.as_ptr()));
                            let _ = SetFocus(edit_confirm);
                            for b in buf_new.iter_mut() { *b = 0; }
                            for b in buf_conf.iter_mut() { *b = 0; }
                            return LRESULT(0);
                        }

                        for b in buf_new.iter_mut() { *b = 0; }
                        for b in buf_conf.iter_mut() { *b = 0; }

                        SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_OK);
                        PostQuitMessage(0);
                    }
                    ID_CANCEL => {
                        SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
                        PostQuitMessage(0);
                    }
                    _ => {}
                }
            }
            LRESULT(0)
        }
        WM_CLOSE => {
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
            PostQuitMessage(0);
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

/// Show a dialog for changing the PIN (three fields: Current + New + Confirm).
/// Returns `(current_pin, new_pin)` or None if cancelled.
fn show_pin_change_dialog(prompt: &str, min_pin_length: usize, owner_hwnd: Option<usize>) -> Option<(Zeroizing<String>, Zeroizing<String>)> {
    MIN_PIN_LENGTH.with(|c| c.set(min_pin_length));
    let class_name = to_wide("SignExtPinChangeDialog");
    let window_title = to_wide("Change Security Key PIN");
    let prompt_wide = to_wide(prompt);
    let ok_text = to_wide("OK");
    let cancel_text = to_wide("Cancel");
    let empty = to_wide("");
    let button_class = to_wide("BUTTON");
    let static_class = to_wide("STATIC");
    let edit_class = to_wide("EDIT");
    let icon_text = to_wide("\u{1F511}"); // key emoji
    let label_current = to_wide("Current PIN:");
    let label_new = to_wide("New PIN:");

    unsafe {
        let hmodule = GetModuleHandleW(PCWSTR::null()).ok()?;
        let hinstance: HINSTANCE = hmodule.into();

        let wc = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(pin_change_wndproc),
            hInstance: hinstance,
            hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
            lpszClassName: PCWSTR(class_name.as_ptr()),
            ..Default::default()
        };

        let atom = RegisterClassExW(&wc);
        if atom == 0 {
            warn!("RegisterClassExW failed: {}", std::io::Error::last_os_error());
            return None;
        }

        let owner = owner_hwnd
            .map(|h| HWND(h as *mut std::ffi::c_void))
            .unwrap_or_default();
        let ex_style = if owner_hwnd.is_some() {
            WINDOW_EX_STYLE::default()
        } else {
            WS_EX_TOPMOST
        };

        let (dlg_w, dlg_h) = (440, 345);
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
                warn!("CreateWindowExW failed: {e}");
                let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
                return None;
            }
        };

        let _ = SetWindowDisplayAffinity(hwnd, WINDOW_DISPLAY_AFFINITY(0x11));
        apply_rounded_corners(hwnd);

        if owner != HWND::default() {
            let _ = EnableWindow(owner, false);
        }

        let emoji_font = create_emoji_font(32);
        let text_font = create_ui_font(14);
        let small_font = create_ui_font(12);
        let button_font = create_ui_font(14);

        // Emoji icon
        let icon_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(icon_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WINDOW_STYLE(0x0001),
            15, 15, 45, 40,
            hwnd, id_to_hmenu(ID_ICON), hinstance, None,
        ).unwrap_or_default();
        set_font(icon_hwnd, emoji_font);

        // Prompt label
        let prompt_lbl = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(prompt_wide.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 20, 350, 25,
            hwnd, id_to_hmenu(ID_LABEL), hinstance, None,
        ).unwrap_or_default();
        set_font(prompt_lbl, text_font);

        // --- Current PIN ---
        let cur_label_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(label_current.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 58, 150, 20,
            hwnd, id_to_hmenu(ID_LABEL2), hinstance, None,
        ).unwrap_or_default();
        set_font(cur_label_hwnd, small_font);

        let edit_current = CreateWindowExW(
            WS_EX_CLIENTEDGE,
            PCWSTR(edit_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(ES_PASSWORD | ES_AUTOHSCROLL),
            70, 78, 340, 28,
            hwnd, id_to_hmenu(ID_EDIT), hinstance, None,
        ).unwrap_or_default();
        set_font(edit_current, text_font);

        // --- New PIN ---
        let new_label_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(label_new.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 115, 150, 20,
            hwnd, id_to_hmenu(ID_LABEL3), hinstance, None,
        ).unwrap_or_default();
        set_font(new_label_hwnd, small_font);

        let edit_new = CreateWindowExW(
            WS_EX_CLIENTEDGE,
            PCWSTR(edit_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(ES_PASSWORD | ES_AUTOHSCROLL),
            70, 135, 340, 28,
            hwnd, id_to_hmenu(ID_EDIT2), hinstance, None,
        ).unwrap_or_default();
        set_font(edit_new, text_font);

        // --- Confirm New PIN ---
        // Use a raw ID for this extra label
        let conf_label_text = to_wide("Confirm New PIN:");
        let _ = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(conf_label_text.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 172, 150, 20,
            hwnd, id_to_hmenu(130), hinstance, None,
        );
        // (set font via the return value)
        let conf_label = GetDlgItem(hwnd, 130).unwrap_or_default();
        set_font(conf_label, small_font);

        let edit_confirm = CreateWindowExW(
            WS_EX_CLIENTEDGE,
            PCWSTR(edit_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(ES_PASSWORD | ES_AUTOHSCROLL),
            70, 192, 340, 28,
            hwnd, id_to_hmenu(ID_EDIT3), hinstance, None,
        ).unwrap_or_default();
        set_font(edit_confirm, text_font);

        // Error label (hidden)
        let error_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(empty.as_ptr()),
            WS_CHILD,
            70, 225, 240, 20,
            hwnd, id_to_hmenu(ID_ERROR_LABEL), hinstance, None,
        ).unwrap_or_default();
        set_font(error_hwnd, small_font);

        // OK button
        let ok_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(ok_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(BS_DEFPUSHBUTTON),
            225, 258, 85, 32,
            hwnd, id_to_hmenu(ID_OK), hinstance, None,
        ).unwrap_or_default();
        set_font(ok_hwnd, button_font);

        // Cancel button
        let cancel_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(cancel_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            325, 258, 85, 32,
            hwnd, id_to_hmenu(ID_CANCEL), hinstance, None,
        ).unwrap_or_default();
        set_font(cancel_hwnd, button_font);

        bring_to_foreground(hwnd, Some(edit_current));
        run_dialog_loop(hwnd);

        let result_code = GetWindowLongPtrW(hwnd, GWLP_USERDATA);
        let result = if result_code == RESULT_OK {
            let current = read_and_clear_edit(edit_current);
            let new_pin = read_and_clear_edit(edit_new);
            // Zero the confirm field
            let _ = SetWindowTextW(edit_confirm, PCWSTR(empty.as_ptr()));
            match (current, new_pin) {
                (Some(c), Some(n)) => Some((c, n)),
                _ => None,
            }
        } else {
            None
        };

        if owner != HWND::default() {
            let _ = EnableWindow(owner, true);
            let _ = SetForegroundWindow(owner);
        }

        let _ = DestroyWindow(hwnd);
        let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
        result
    }
}

// ============================================================================
// Credential selection dialog (listbox)
// ============================================================================

use yubikit::webauthn::types::PublicKeyCredentialUserEntity;

// Listbox control ID
const ID_LISTBOX: i32 = 200;

// Listbox styles
const LBS_NOTIFY: u32 = 0x0001;
const LBS_NOINTEGRALHEIGHT: u32 = 0x0100;
const LB_ADDSTRINGW: u32 = 0x0180;
const LB_SETCURSEL: u32 = 0x0186;
const LB_GETCURSEL: u32 = 0x0188;
const LBN_DBLCLK: u16 = 2;
const LB_ERR: isize = -1;

/// Window procedure for the credential picker dialog.
unsafe extern "system" fn credential_picker_wndproc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_CREATE => LRESULT(0),
        WM_COMMAND => {
            let id = (wparam.0 & 0xFFFF) as i32;
            let notification = ((wparam.0 >> 16) & 0xFFFF) as u16;
            match id {
                ID_OK if notification == 0 => {
                    SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_OK);
                    PostQuitMessage(0);
                }
                ID_CANCEL if notification == 0 => {
                    SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
                    PostQuitMessage(0);
                }
                ID_LISTBOX if notification == LBN_DBLCLK => {
                    // Double-click on a list item acts like OK
                    SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_OK);
                    PostQuitMessage(0);
                }
                _ => {}
            }
            LRESULT(0)
        }
        WM_CLOSE => {
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, RESULT_CANCEL);
            PostQuitMessage(0);
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

/// Show a listbox dialog for selecting among multiple credentials.
/// Returns the selected index, or None if cancelled.
fn show_credential_picker(
    users: &[PublicKeyCredentialUserEntity],
    prompt: &str,
    owner_hwnd: Option<usize>,
) -> Option<usize> {
    let class_name = to_wide("SignExtCredentialPicker");
    let window_title = to_wide("Select Account");
    let prompt_wide = to_wide(prompt);
    let ok_text = to_wide("OK");
    let cancel_text = to_wide("Cancel");
    let button_class = to_wide("BUTTON");
    let static_class = to_wide("STATIC");
    let listbox_class = to_wide("LISTBOX");
    let icon_text = to_wide("\u{1F464}"); // bust silhouette emoji

    unsafe {
        let hmodule = GetModuleHandleW(PCWSTR::null()).ok()?;
        let hinstance: HINSTANCE = hmodule.into();

        let wc = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(credential_picker_wndproc),
            hInstance: hinstance,
            hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
            lpszClassName: PCWSTR(class_name.as_ptr()),
            ..Default::default()
        };

        let atom = RegisterClassExW(&wc);
        if atom == 0 {
            warn!("RegisterClassExW failed: {}", std::io::Error::last_os_error());
            return None;
        }

        let owner = owner_hwnd
            .map(|h| HWND(h as *mut std::ffi::c_void))
            .unwrap_or_default();
        let ex_style = if owner_hwnd.is_some() {
            WINDOW_EX_STYLE::default()
        } else {
            WS_EX_TOPMOST
        };

        // Scale height based on number of items (min 2 visible, max 6 before scroll)
        let visible_items = users.len().clamp(2, 6) as i32;
        let list_height = visible_items * 24 + 4; // ~24px per item + border
        let dlg_h = 90 + list_height + 55; // header + list + buttons
        let dlg_w = 440;
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
                warn!("CreateWindowExW failed: {e}");
                let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
                return None;
            }
        };

        let _ = SetWindowDisplayAffinity(hwnd, WINDOW_DISPLAY_AFFINITY(0x11));
        apply_rounded_corners(hwnd);

        if owner != HWND::default() {
            let _ = EnableWindow(owner, false);
        }

        let emoji_font = create_emoji_font(32);
        let text_font = create_ui_font(14);
        let list_font = create_ui_font(14);
        let button_font = create_ui_font(14);

        // Emoji icon
        let _icon = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(icon_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WINDOW_STYLE(0x0001), // SS_CENTER
            15, 15, 45, 40,
            hwnd, id_to_hmenu(ID_ICON), hinstance, None,
        ).unwrap_or_default();
        set_font(_icon, emoji_font);

        // Prompt label
        let _label = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(static_class.as_ptr()),
            PCWSTR(prompt_wide.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            70, 20, 350, 25,
            hwnd, id_to_hmenu(ID_LABEL), hinstance, None,
        ).unwrap_or_default();
        set_font(_label, text_font);

        // Listbox
        let list_top = 60;
        let listbox = CreateWindowExW(
            WS_EX_CLIENTEDGE,
            PCWSTR(listbox_class.as_ptr()),
            PCWSTR::null(),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL
                | WINDOW_STYLE(LBS_NOTIFY | LBS_NOINTEGRALHEIGHT),
            20, list_top,
            395, list_height,
            hwnd, id_to_hmenu(ID_LISTBOX), hinstance, None,
        ).unwrap_or_default();
        set_font(listbox, list_font);

        // Populate the listbox
        for user in users {
            let display = user
                .display_name
                .as_deref()
                .or(user.name.as_deref())
                .unwrap_or("Unknown user");
            // If both display_name and name exist and differ, show both
            let label = match (&user.display_name, &user.name) {
                (Some(dn), Some(n)) if dn != n => format!("{dn}  ({n})"),
                _ => display.to_string(),
            };
            let wide = to_wide(&label);
            SendMessageW(
                listbox,
                LB_ADDSTRINGW,
                WPARAM(0),
                LPARAM(wide.as_ptr() as isize),
            );
        }
        // Pre-select first item
        SendMessageW(listbox, LB_SETCURSEL, WPARAM(0), LPARAM(0));

        // OK button
        let btn_y = list_top + list_height + 12;
        let ok_hwnd = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(ok_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WINDOW_STYLE(BS_DEFPUSHBUTTON),
            225, btn_y, 85, 32,
            hwnd, id_to_hmenu(ID_OK), hinstance, None,
        ).unwrap_or_default();
        set_font(ok_hwnd, button_font);

        let _cancel = CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            PCWSTR(button_class.as_ptr()),
            PCWSTR(cancel_text.as_ptr()),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            325, btn_y, 85, 32,
            hwnd, id_to_hmenu(ID_CANCEL), hinstance, None,
        ).unwrap_or_default();
        set_font(_cancel, button_font);

        bring_to_foreground(hwnd, Some(listbox));
        run_dialog_loop(hwnd);

        let result_code = GetWindowLongPtrW(hwnd, GWLP_USERDATA);
        let selection = if result_code == RESULT_OK {
            let sel = SendMessageW(listbox, LB_GETCURSEL, WPARAM(0), LPARAM(0));
            if sel.0 != LB_ERR {
                Some(sel.0 as usize)
            } else {
                Some(0) // fallback to first
            }
        } else {
            None
        };

        if owner != HWND::default() {
            let _ = EnableWindow(owner, true);
            let _ = SetForegroundWindow(owner);
        }

        let _ = DestroyWindow(hwnd);
        let _ = UnregisterClassW(PCWSTR(class_name.as_ptr()), hinstance);
        selection
    }
}

// ============================================================================
// Console fallback
// ============================================================================

/// Read PIN from console stdin (fallback).
fn console_prompt_pin(prompt: &str) -> Option<Zeroizing<String>> {
    eprint!("{}", prompt);
    let mut pin = Zeroizing::new(String::new());
    match std::io::stdin().read_line(&mut pin) {
        Ok(_) => {
            let trimmed = pin.trim().to_string();
            if trimmed.is_empty() {
                None
            } else {
                Some(Zeroizing::new(trimmed))
            }
        }
        Err(_) => None,
    }
}

// ============================================================================
// Public API
// ============================================================================

pub fn prompt_pin(retries: Option<u8>, rp_id: Option<&str>, browser_name: Option<&str>, owner_hwnd: Option<usize>) -> Option<Zeroizing<String>> {
    info!("PIN required (retries: {:?}, rp: {:?}, browser: {:?})", retries, rp_id, browser_name);

    let prompt = match (retries, rp_id, browser_name) {
        (Some(r), Some(rp), Some(browser)) if r < 3 => {
            format!("PIN for {rp} ({browser}, {r} retries left): ")
        }
        (Some(r), Some(rp), None) if r < 3 => {
            format!("PIN for {rp} ({r} retries left): ")
        }
        (_, Some(rp), Some(browser)) => format!("PIN for {rp} ({browser}): "),
        (_, Some(rp), None) => format!("PIN for {rp}: "),
        (Some(r), None, _) if r < 3 => format!("Enter YubiKey PIN ({r} retries remaining): "),
        _ => "Enter YubiKey PIN: ".to_string(),
    };

    if CONSOLE_MODE.load(Ordering::Relaxed) {
        return console_prompt_pin(&prompt);
    }

    show_pin_dialog(&prompt, owner_hwnd)
}

/// Prompt the user to set up a new PIN (two fields: New + Confirm).
/// `min_pin_length` is the device-specific minimum PIN length (CTAP2 default: 4).
/// Returns the new PIN, or None if cancelled.
pub fn prompt_new_pin(rp_id: Option<&str>, browser_name: Option<&str>, min_pin_length: usize, owner_hwnd: Option<usize>) -> Option<Zeroizing<String>> {
    info!("New PIN setup required (rp: {:?}, browser: {:?}, min_len: {})", rp_id, browser_name, min_pin_length);

    let prompt = match (rp_id, browser_name) {
        (Some(rp), Some(browser)) => format!("Set up PIN for {rp} ({browser}). Minimum {min_pin_length} characters."),
        (Some(rp), None) => format!("Set up PIN for {rp}. Minimum {min_pin_length} characters."),
        _ => format!("Set up a new YubiKey PIN. Minimum {min_pin_length} characters."),
    };

    if CONSOLE_MODE.load(Ordering::Relaxed) {
        return console_prompt_pin("Enter new PIN: ");
    }

    show_new_pin_dialog(&prompt, min_pin_length, owner_hwnd)
}

/// Prompt the user to change their PIN (three fields: Current + New + Confirm).
/// `min_pin_length` is the device-specific minimum PIN length (CTAP2 default: 4).
/// Returns `(current_pin, new_pin)`, or None if cancelled.
pub fn prompt_pin_change(rp_id: Option<&str>, browser_name: Option<&str>, min_pin_length: usize, owner_hwnd: Option<usize>) -> Option<(Zeroizing<String>, Zeroizing<String>)> {
    info!("PIN change required (rp: {:?}, browser: {:?}, min_len: {})", rp_id, browser_name, min_pin_length);

    let prompt = match (rp_id, browser_name) {
        (Some(rp), Some(browser)) => format!("Change PIN for {rp} ({browser}). Minimum {min_pin_length} characters."),
        (Some(rp), None) => format!("Change PIN for {rp}. Minimum {min_pin_length} characters."),
        _ => format!("Change your YubiKey PIN. Minimum {min_pin_length} characters."),
    };

    if CONSOLE_MODE.load(Ordering::Relaxed) {
        let current = console_prompt_pin("Enter current PIN: ")?;
        let new_pin = console_prompt_pin("Enter new PIN: ")?;
        return Some((current, new_pin));
    }

    show_pin_change_dialog(&prompt, min_pin_length, owner_hwnd)
}

/// Prompt the user to select from multiple credentials on a single key.
/// Returns the selected index, or None if cancelled.
pub fn prompt_credential_selection(
    users: &[PublicKeyCredentialUserEntity],
    rp_id: Option<&str>,
    browser_name: Option<&str>,
    owner_hwnd: Option<usize>,
) -> Option<usize> {
    info!(
        "Credential selection required ({} users, rp: {:?}, browser: {:?})",
        users.len(),
        rp_id,
        browser_name
    );

    let prompt = match (rp_id, browser_name) {
        (Some(rp), Some(browser)) => format!("Choose an account for {rp} ({browser})"),
        (Some(rp), None) => format!("Choose an account for {rp}"),
        _ => "Choose an account".to_string(),
    };

    if CONSOLE_MODE.load(Ordering::Relaxed) {
        eprintln!("{prompt}");
        for (i, user) in users.iter().enumerate() {
            let name = user.display_name.as_deref()
                .or(user.name.as_deref())
                .unwrap_or("Unknown user");
            eprintln!("  {}: {name}", i + 1);
        }
        eprint!("Selection (1-{}): ", users.len());
        let mut input = String::new();
        if std::io::stdin().read_line(&mut input).is_ok() {
            if let Ok(n) = input.trim().parse::<usize>() {
                if n >= 1 && n <= users.len() {
                    return Some(n - 1);
                }
            }
        }
        return Some(0); // default to first
    }

    show_credential_picker(users, &prompt, owner_hwnd)
}
