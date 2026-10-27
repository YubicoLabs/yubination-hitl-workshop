//! Native macOS UI dialogs using AppKit's NSAlert.
//!
//! All FIDO dialogs (touch, insert, select, biometric, PIN) use NSAlert for a
//! modern native appearance. Each dialog type gets a distinct SF Symbols icon.
//! PIN uses NSSecureTextField so the PIN stays in native memory.
//!
//! AppKit requires all UI to happen on the main thread. The architecture is:
//! - Main thread: runs a minimal NSApplication event loop and processes UI commands
//! - Background thread: runs the stdin/stdout message loop
//! - NativeUI sends commands to the main thread via a channel

#[link(name = "AppKit", kind = "framework")]
extern "C" {}

use log::info;
use objc::runtime::{Object, BOOL, YES, NO};
use objc::{class, msg_send, sel, sel_impl};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::sync::Arc;

#[repr(C)]
#[derive(Copy, Clone)]
struct NSPoint { x: f64, y: f64 }

#[repr(C)]
#[derive(Copy, Clone)]
struct NSSize { width: f64, height: f64 }

#[repr(C)]
#[derive(Copy, Clone)]
struct NSRect { origin: NSPoint, size: NSSize }

const NS_ALERT_FIRST_BUTTON: i64 = 1000;
const NS_FLOATING_WINDOW_LEVEL: i64 = 3;
const NS_NORMAL_WINDOW_LEVEL: i64 = 0;

const NS_ALERT_STYLE_WARNING: i64 = 0;
const NS_ALERT_STYLE_INFORMATIONAL: i64 = 1;
const NS_ALERT_STYLE_CRITICAL: i64 = 2;

// NSImageSymbolScale
const NS_IMAGE_SYMBOL_SCALE_LARGE: i64 = 3;

// NSFontWeight (CGFloat)
const NS_FONT_WEIGHT_MEDIUM: f64 = 0.23;

/// Creates a retained NSString from a Rust &str. Caller must release.
unsafe fn make_nsstring(s: &str) -> *mut Object {
    let obj: *mut Object = msg_send![class!(NSString), alloc];
    msg_send![obj, initWithBytes:s.as_ptr() length:s.len() encoding:4usize]
}

/// Create an SF Symbol image with large scale and medium weight.
/// Returns a retained NSImage, or null if the symbol isn't available.
unsafe fn make_sf_symbol(name: &str, size: f64) -> *mut Object {
    let sym_name = make_nsstring(name);

    // NSImageSymbolConfiguration with point size + weight + scale
    let config: *mut Object = msg_send![
        class!(NSImageSymbolConfiguration),
        configurationWithPointSize: size
        weight: NS_FONT_WEIGHT_MEDIUM
        scale: NS_IMAGE_SYMBOL_SCALE_LARGE
    ];

    let image: *mut Object = msg_send![
        class!(NSImage),
        imageWithSystemSymbolName: sym_name
        accessibilityDescription: std::ptr::null::<Object>()
    ];
    let _: () = msg_send![sym_name, release];

    if image.is_null() {
        return std::ptr::null_mut();
    }

    // Apply the configuration to get the sized/weighted variant
    let configured: *mut Object = msg_send![image, imageWithSymbolConfiguration: config];
    if configured.is_null() {
        return image;
    }
    configured
}

// ---------------------------------------------------------------------------
// UI commands sent from NativeUI (any thread) to the main thread
// ---------------------------------------------------------------------------

pub enum UICommand {
    ShowStatus {
        message: String,
        style: i64,
        icon: &'static str,
        cancelled: Arc<AtomicBool>,
    },
    Dismiss,
    ShowPin {
        message: String,
        result_tx: mpsc::Sender<Option<String>>,
    },
    /// New PIN setup dialog (New PIN + Confirm PIN).
    ShowPinSetup {
        message: String,
        result_tx: mpsc::Sender<Option<String>>,
    },
    /// PIN change dialog (Current PIN + New PIN + Confirm PIN).
    ShowPinChange {
        message: String,
        result_tx: mpsc::Sender<Option<(String, String)>>,
    },
    /// Modal error dialog that blocks until user clicks Close.
    ShowError {
        message: String,
        icon: &'static str,
        done_tx: mpsc::Sender<()>,
    },
    /// Credential picker for multiple resident credentials.
    SelectCredential {
        users: Vec<(Option<String>, Option<String>)>,
        result_tx: mpsc::Sender<Option<usize>>,
    },
    Quit,
}

/// Dismiss any current alert, releasing it.
unsafe fn dismiss_alert(current_alert: &mut Option<*mut Object>) {
    if let Some(alert) = current_alert.take() {
        let window: *mut Object = msg_send![alert, window];
        let _: () = msg_send![window, close];
        let _: () = msg_send![alert, release];
    }
}

/// Set an SF Symbol icon on an NSAlert.
unsafe fn set_alert_icon(alert: *mut Object, symbol_name: &str) {
    let icon = make_sf_symbol(symbol_name, 48.0);
    if !icon.is_null() {
        let _: () = msg_send![alert, setIcon: icon];
    }
}

/// Check if a bundle ID belongs to a known browser.
fn is_browser_bundle_id(bundle_id: &str) -> bool {
    // Match common browser bundle IDs (case-insensitive substring)
    let lower = bundle_id.to_lowercase();
    lower.contains("chrome") || lower.contains("firefox")
        || lower.contains("safari") || lower.contains("chromium")
        || lower.contains("brave") || lower.contains("vivaldi")
        || lower.contains("opera") || lower.contains("edgemac")
        || lower.contains("arc")
}

/// Determine the appropriate window level based on the currently active app.
/// Returns `.floating` if a browser or our own process is active, `.normal` otherwise.
unsafe fn desired_window_level() -> i64 {
    let workspace: *mut Object = msg_send![class!(NSWorkspace), sharedWorkspace];
    let front_app: *mut Object = msg_send![workspace, frontmostApplication];
    if front_app.is_null() { return NS_FLOATING_WINDOW_LEVEL; }

    // Check if frontmost app is us
    let current_app: *mut Object = msg_send![class!(NSRunningApplication), currentApplication];
    if !current_app.is_null() {
        let is_same: BOOL = msg_send![front_app, isEqual: current_app];
        if is_same == YES {
            return NS_FLOATING_WINDOW_LEVEL;
        }
    }

    // Check if frontmost app is a browser
    let bundle_id: *mut Object = msg_send![front_app, bundleIdentifier];
    if !bundle_id.is_null() {
        let cstr: *const i8 = msg_send![bundle_id, UTF8String];
        if !cstr.is_null() {
            let s = std::ffi::CStr::from_ptr(cstr).to_string_lossy();
            if is_browser_bundle_id(&s) {
                return NS_FLOATING_WINDOW_LEVEL;
            }
        }
    }

    NS_NORMAL_WINDOW_LEVEL
}

/// Apply the given window level to all visible windows.
unsafe fn apply_window_level(app: *mut Object, level: i64) {
    let windows: *mut Object = msg_send![app, windows];
    let count: usize = msg_send![windows, count];
    for i in 0..count {
        let window: *mut Object = msg_send![windows, objectAtIndex: i];
        let visible: BOOL = msg_send![window, isVisible];
        if visible == YES {
            let _: () = msg_send![window, setLevel: level];
        }
    }
}

/// Start a GCD dispatch timer that adjusts window levels based on which app
/// is active. Fires every 250ms, including during `runModal()`.
unsafe fn start_window_level_timer(app: *mut Object) {
    // Store app pointer in a global so the timer callback can access it.
    // Safe because the main thread is the only user.
    TIMER_APP.store(app as *mut std::ffi::c_void, Ordering::Relaxed);
    TIMER_LAST_LEVEL.store(NS_FLOATING_WINDOW_LEVEL, Ordering::Relaxed);

    // Use dispatch source timer on main queue — fires during modal sessions.
    let queue = dispatch_get_main_queue();
    let source = dispatch_source_create(
        &_dispatch_source_type_timer as *const _ as *mut _,
        0, 0, queue,
    );
    // 100ms interval, 20ms leeway
    dispatch_source_set_timer(source, dispatch_time(0, 0), 100_000_000, 20_000_000);
    dispatch_source_set_event_handler_f(source, window_level_timer_handler);
    dispatch_resume(source);
}

static TIMER_APP: std::sync::atomic::AtomicPtr<std::ffi::c_void> =
    std::sync::atomic::AtomicPtr::new(std::ptr::null_mut());
static TIMER_LAST_LEVEL: std::sync::atomic::AtomicI64 =
    std::sync::atomic::AtomicI64::new(NS_FLOATING_WINDOW_LEVEL);

extern "C" fn window_level_timer_handler(_context: *mut std::ffi::c_void) {
    unsafe {
        let app = TIMER_APP.load(Ordering::Relaxed) as *mut Object;
        if app.is_null() { return; }
        let level = desired_window_level();
        let last = TIMER_LAST_LEVEL.load(Ordering::Relaxed);
        if level != last {
            apply_window_level(app, level);
            TIMER_LAST_LEVEL.store(level, Ordering::Relaxed);
        }
    }
}

// GCD FFI declarations
type DispatchObject = std::ffi::c_void;
extern "C" {
    // dispatch_get_main_queue() is a macro; the actual symbol is _dispatch_main_q
    static _dispatch_main_q: DispatchObject;
    fn dispatch_source_create(
        type_: *const DispatchObject, handle: usize, mask: usize,
        queue: *mut DispatchObject,
    ) -> *mut DispatchObject;
    fn dispatch_source_set_timer(
        source: *mut DispatchObject, start: u64, interval: u64, leeway: u64,
    );
    fn dispatch_source_set_event_handler_f(
        source: *mut DispatchObject, handler: extern "C" fn(*mut std::ffi::c_void),
    );
    fn dispatch_resume(source: *mut DispatchObject);
    fn dispatch_time(when: u64, delta: i64) -> u64;
    static _dispatch_source_type_timer: DispatchObject;
}

/// Get the main dispatch queue (equivalent to dispatch_get_main_queue() macro).
unsafe fn dispatch_get_main_queue() -> *mut DispatchObject {
    &_dispatch_main_q as *const _ as *mut _
}

/// Runs the AppKit event loop on the main thread.
/// Processes UI commands from the channel.
///
/// Call this from `main()` — it blocks the main thread.
pub fn run_main_loop(cmd_rx: mpsc::Receiver<UICommand>) {
    unsafe {
        let app: *mut Object = msg_send![class!(NSApplication), sharedApplication];
        // Accessory = no Dock icon, but can show windows.
        let _: () = msg_send![app, setActivationPolicy: 1i64];
        let _: () = msg_send![app, finishLaunching];

        // Start GCD timer for dynamic window level management.
        // Fires every 250ms even during runModal(), adjusting window levels
        // based on whether the browser or another app is frontmost.
        start_window_level_timer(app);

        // Pre-create the run loop mode string (reused each iteration).
        let run_loop_mode = make_nsstring("kCFRunLoopDefaultMode");

        let mut current_alert: Option<*mut Object> = None;
        let mut current_cancelled: Option<Arc<AtomicBool>> = None;

        loop {
            // Drain any pending AppKit events (non-blocking).
            loop {
                let event: *mut Object = msg_send![app,
                    nextEventMatchingMask: u64::MAX
                    untilDate: std::ptr::null::<Object>()
                    inMode: run_loop_mode
                    dequeue: YES
                ];
                if event.is_null() {
                    break;
                }
                let _: () = msg_send![app, sendEvent: event];
            }

            // Check for UI commands (non-blocking).
            match cmd_rx.try_recv() {
                Ok(UICommand::ShowStatus { message, style, icon, cancelled }) => {
                    dismiss_alert(&mut current_alert);

                    let alert: *mut Object = msg_send![class!(NSAlert), new];
                    let title = make_nsstring("Security Key");
                    let _: () = msg_send![alert, setMessageText: title];
                    let _: () = msg_send![title, release];
                    let msg = make_nsstring(&message);
                    let _: () = msg_send![alert, setInformativeText: msg];
                    let _: () = msg_send![msg, release];
                    let _: () = msg_send![alert, setAlertStyle: style];

                    set_alert_icon(alert, icon);

                    let cancel_btn = make_nsstring("Cancel");
                    let _: () = msg_send![alert, addButtonWithTitle: cancel_btn];
                    let _: () = msg_send![cancel_btn, release];

                    // Wire the Cancel button to close the window when clicked.
                    // NSAlert buttons only fire via runModal; since we show
                    // non-modally, we set the button's target/action directly.
                    let buttons: *mut Object = msg_send![alert, buttons];
                    let button: *mut Object = msg_send![buttons, objectAtIndex: 0usize];
                    let _: () = msg_send![alert, layout];
                    let window: *mut Object = msg_send![alert, window];
                    let _: () = msg_send![button, setTarget: window];
                    let _: () = msg_send![button, setAction: sel!(orderOut:)];
                    // Escape key should also close
                    let esc = make_nsstring("\u{1b}");
                    let _: () = msg_send![button, setKeyEquivalent: esc];
                    let _: () = msg_send![esc, release];
                    let level = desired_window_level();
                    let _: () = msg_send![window, setLevel: level];
                    let _: () = msg_send![window, center];
                    let _: () = msg_send![window, makeKeyAndOrderFront: std::ptr::null::<Object>()];
                    let _: () = msg_send![app, activateIgnoringOtherApps: YES];

                    current_alert = Some(alert);
                    current_cancelled = Some(cancelled);
                }
                Ok(UICommand::Dismiss) => {
                    dismiss_alert(&mut current_alert);
                    current_cancelled = None;
                }
                Ok(UICommand::ShowPin { message, result_tx }) => {
                    dismiss_alert(&mut current_alert);
                    current_cancelled = None;

                    let alert: *mut Object = msg_send![class!(NSAlert), new];
                    let title = make_nsstring("Security Key PIN");
                    let _: () = msg_send![alert, setMessageText: title];
                    let _: () = msg_send![title, release];
                    let text = make_nsstring(&message);
                    let _: () = msg_send![alert, setInformativeText: text];
                    let _: () = msg_send![text, release];
                    let _: () = msg_send![alert, setAlertStyle: NS_ALERT_STYLE_INFORMATIONAL];

                    set_alert_icon(alert, "lock.shield");

                    let ok = make_nsstring("OK");
                    let _: () = msg_send![alert, addButtonWithTitle: ok];
                    let _: () = msg_send![ok, release];
                    let cancel_label = make_nsstring("Cancel");
                    let _: () = msg_send![alert, addButtonWithTitle: cancel_label];
                    let _: () = msg_send![cancel_label, release];

                    let rect = NSRect {
                        origin: NSPoint { x: 0.0, y: 0.0 },
                        size: NSSize { width: 200.0, height: 24.0 },
                    };
                    let field: *mut Object = msg_send![class!(NSSecureTextField), alloc];
                    let field: *mut Object = msg_send![field, initWithFrame: rect];
                    let _: () = msg_send![alert, setAccessoryView: field];

                    let window: *mut Object = msg_send![alert, window];
                    let _: () = msg_send![window, setLevel: desired_window_level()];
                    let _: () = msg_send![window, setInitialFirstResponder: field];

                    let _: () = msg_send![app, activateIgnoringOtherApps: YES];

                    // runModal blocks the main thread until user responds.
                    let response: i64 = msg_send![alert, runModal];

                    let result = if response == NS_ALERT_FIRST_BUTTON {
                        let value: *mut Object = msg_send![field, stringValue];
                        let len: usize = msg_send![value, length];
                        if len > 0 {
                            let cstr: *const i8 = msg_send![value, UTF8String];
                            let s = std::ffi::CStr::from_ptr(cstr)
                                .to_string_lossy()
                                .to_string();
                            Some(s)
                        } else {
                            None
                        }
                    } else {
                        None
                    };

                    let _: () = msg_send![field, release];
                    let _: () = msg_send![alert, release];
                    let _ = result_tx.send(result);
                }
                Ok(UICommand::ShowPinSetup { message, result_tx }) => {
                    dismiss_alert(&mut current_alert);
                    current_cancelled = None;

                    let result = run_pin_setup_dialog(app, &message);
                    let _ = result_tx.send(result);
                }
                Ok(UICommand::ShowPinChange { message, result_tx }) => {
                    dismiss_alert(&mut current_alert);
                    current_cancelled = None;

                    let result = run_pin_change_dialog(app, &message);
                    let _ = result_tx.send(result);
                }
                Ok(UICommand::ShowError { message, icon, done_tx }) => {
                    dismiss_alert(&mut current_alert);
                    current_cancelled = None;

                    let alert: *mut Object = msg_send![class!(NSAlert), new];
                    let title = make_nsstring("Security Key");
                    let _: () = msg_send![alert, setMessageText: title];
                    let _: () = msg_send![title, release];
                    let text = make_nsstring(&message);
                    let _: () = msg_send![alert, setInformativeText: text];
                    let _: () = msg_send![text, release];
                    let _: () = msg_send![alert, setAlertStyle: NS_ALERT_STYLE_CRITICAL];

                    set_alert_icon(alert, icon);

                    let close_label = make_nsstring("Close");
                    let _: () = msg_send![alert, addButtonWithTitle: close_label];
                    let _: () = msg_send![close_label, release];

                    let window: *mut Object = msg_send![alert, window];
                    let _: () = msg_send![window, setLevel: desired_window_level()];
                    let _: () = msg_send![app, activateIgnoringOtherApps: YES];

                    // runModal blocks until user clicks Close.
                    let _: i64 = msg_send![alert, runModal];
                    let _: () = msg_send![alert, release];
                    let _ = done_tx.send(());
                }
                Ok(UICommand::SelectCredential { users, result_tx }) => {
                    dismiss_alert(&mut current_alert);
                    current_cancelled = None;

                    let result = run_credential_picker(app, &users);
                    let _ = result_tx.send(result);
                }
                Ok(UICommand::Quit) => {
                    dismiss_alert(&mut current_alert);
                    break;
                }
                Err(mpsc::TryRecvError::Empty) => {}
                Err(mpsc::TryRecvError::Disconnected) => break,
            }

            // Check if the status alert window was closed (user clicked Cancel).
            if let Some(alert) = current_alert {
                let window: *mut Object = msg_send![alert, window];
                let visible: BOOL = msg_send![window, isVisible];
                if visible == NO {
                    info!("User cancelled from native status dialog");
                    if let Some(ref flag) = current_cancelled {
                        flag.store(true, Ordering::Relaxed);
                    }
                    let _: () = msg_send![alert, release];
                    current_alert = None;
                    current_cancelled = None;
                }
            }

            // Sleep briefly to avoid busy-waiting.
            std::thread::sleep(std::time::Duration::from_millis(20));
        }

        // Clean up the run loop mode string.
        let _: () = msg_send![run_loop_mode, release];
    }
}

// ---------------------------------------------------------------------------
// Multi-field PIN dialogs
// ---------------------------------------------------------------------------

/// Helper to read a string from an NSSecureTextField.
unsafe fn read_secure_field(field: *mut Object) -> String {
    let value: *mut Object = msg_send![field, stringValue];
    let cstr: *const i8 = msg_send![value, UTF8String];
    std::ffi::CStr::from_ptr(cstr)
        .to_string_lossy()
        .to_string()
}

const FIELD_WIDTH: f64 = 220.0;
const FIELD_HEIGHT: f64 = 24.0;
const FIELD_SPACING: f64 = 8.0;

/// Create an NSSecureTextField with a placeholder string, positioned at y offset.
unsafe fn make_secure_field(placeholder: &str, y: f64) -> *mut Object {
    let field_rect = NSRect {
        origin: NSPoint { x: 0.0, y },
        size: NSSize { width: FIELD_WIDTH, height: FIELD_HEIGHT },
    };
    let field: *mut Object = msg_send![class!(NSSecureTextField), alloc];
    let field: *mut Object = msg_send![field, initWithFrame: field_rect];
    let ph = make_nsstring(placeholder);
    let _: () = msg_send![field, setPlaceholderString: ph];
    let _: () = msg_send![ph, release];
    field
}

/// Create a container NSView with secure text fields stacked vertically.
/// Fields are ordered top-to-bottom matching the placeholders slice.
/// Returns (container, Vec<fields>).
unsafe fn make_pin_fields(placeholders: &[&str]) -> (*mut Object, Vec<*mut Object>) {
    let n = placeholders.len();
    let total_height = n as f64 * FIELD_HEIGHT + (n as f64 - 1.0) * FIELD_SPACING;
    let container_rect = NSRect {
        origin: NSPoint { x: 0.0, y: 0.0 },
        size: NSSize { width: FIELD_WIDTH, height: total_height },
    };
    let container: *mut Object = msg_send![class!(NSView), alloc];
    let container: *mut Object = msg_send![container, initWithFrame: container_rect];

    let mut fields = Vec::with_capacity(n);
    for (i, &ph) in placeholders.iter().enumerate() {
        // Top-to-bottom: first placeholder gets highest y
        let y = total_height - (i as f64 + 1.0) * FIELD_HEIGHT - i as f64 * FIELD_SPACING;
        let field = make_secure_field(ph, y);
        let _: () = msg_send![container, addSubview: field];
        fields.push(field);
    }
    (container, fields)
}

/// Extract the minimum PIN length from a message like "Minimum 6 characters."
/// Falls back to the CTAP2 default of 4 if the pattern isn't found.
fn extract_min_pin_length(message: &str) -> usize {
    if let Some(pos) = message.find("Minimum ") {
        let rest = &message[pos + 8..];
        if let Some(end) = rest.find(' ') {
            if let Ok(n) = rest[..end].parse::<usize>() {
                return n;
            }
        }
    }
    4
}

/// Maximum PIN length in bytes per CTAP2 spec.
const MAX_PIN_LENGTH_BYTES: usize = 63;

/// Show a "Try Again" / "Cancel" error dialog. Returns true if user clicked "Try Again".
unsafe fn show_pin_error_dialog(app: *mut Object, title: &str, body: &str) -> bool {
    let err_alert: *mut Object = msg_send![class!(NSAlert), new];
    let err_title = make_nsstring(title);
    let _: () = msg_send![err_alert, setMessageText: err_title];
    let _: () = msg_send![err_title, release];
    let err_msg = make_nsstring(body);
    let _: () = msg_send![err_alert, setInformativeText: err_msg];
    let _: () = msg_send![err_msg, release];
    let _: () = msg_send![err_alert, setAlertStyle: NS_ALERT_STYLE_WARNING];
    set_alert_icon(err_alert, "exclamationmark.triangle.fill");
    let err_ok = make_nsstring("Try Again");
    let _: () = msg_send![err_alert, addButtonWithTitle: err_ok];
    let _: () = msg_send![err_ok, release];
    let err_cancel = make_nsstring("Cancel");
    let _: () = msg_send![err_alert, addButtonWithTitle: err_cancel];
    let _: () = msg_send![err_cancel, release];
    let err_window: *mut Object = msg_send![err_alert, window];
    let _: () = msg_send![err_window, setLevel: desired_window_level()];
    let _: () = msg_send![app, activateIgnoringOtherApps: YES];
    let err_resp: i64 = msg_send![err_alert, runModal];
    let _: () = msg_send![err_alert, release];
    err_resp == NS_ALERT_FIRST_BUTTON
}

/// PIN setup dialog: New PIN + Confirm PIN. Loops on mismatch/empty.
unsafe fn run_pin_setup_dialog(app: *mut Object, message: &str) -> Option<String> {
    let min_len = extract_min_pin_length(message);
    loop {
        let alert: *mut Object = msg_send![class!(NSAlert), new];
        let title = make_nsstring("Set Security Key PIN");
        let _: () = msg_send![alert, setMessageText: title];
        let _: () = msg_send![title, release];
        let text = make_nsstring(message);
        let _: () = msg_send![alert, setInformativeText: text];
        let _: () = msg_send![text, release];
        let _: () = msg_send![alert, setAlertStyle: NS_ALERT_STYLE_INFORMATIONAL];

        set_alert_icon(alert, "lock.shield");

        let ok = make_nsstring("Set PIN");
        let _: () = msg_send![alert, addButtonWithTitle: ok];
        let _: () = msg_send![ok, release];
        let cancel_label = make_nsstring("Cancel");
        let _: () = msg_send![alert, addButtonWithTitle: cancel_label];
        let _: () = msg_send![cancel_label, release];

        // Build accessory view with two fields
        let (container, fields) = make_pin_fields(&["New PIN", "Confirm PIN"]);
        let field1 = fields[0];
        let field2 = fields[1];
        let _: () = msg_send![alert, setAccessoryView: container];

        let window: *mut Object = msg_send![alert, window];
        let _: () = msg_send![window, setLevel: desired_window_level()];
        let _: () = msg_send![window, setInitialFirstResponder: field1];
        let _: () = msg_send![app, activateIgnoringOtherApps: YES];

        let response: i64 = msg_send![alert, runModal];

        let result = if response == NS_ALERT_FIRST_BUTTON {
            let pin1 = read_secure_field(field1);
            let pin2 = read_secure_field(field2);
            if pin1.is_empty() {
                // Empty — re-show
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                continue;
            }
            if pin1.as_bytes().len() < min_len {
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                let err_body = format!("PIN must be at least {} characters.", min_len);
                if !show_pin_error_dialog(app, "PIN Too Short", &err_body) {
                    return None;
                }
                continue;
            }
            if pin1.as_bytes().len() > MAX_PIN_LENGTH_BYTES {
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                if !show_pin_error_dialog(app, "PIN Too Long", "PIN is too long (maximum 63 bytes).") {
                    return None;
                }
                continue;
            }
            if pin1 != pin2 {
                // Mismatch — re-show with error
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                if !show_pin_error_dialog(app, "PINs Don't Match", "The PINs you entered don't match. Please try again.") {
                    return None;
                }
                continue;
            }
            Some(pin1)
        } else {
            None
        };

        let _: () = msg_send![container, release];
        let _: () = msg_send![alert, release];
        return result;
    }
}

/// PIN change dialog: Current PIN + New PIN + Confirm PIN. Loops on mismatch/empty.
unsafe fn run_pin_change_dialog(app: *mut Object, message: &str) -> Option<(String, String)> {
    let min_len = extract_min_pin_length(message);
    loop {
        let alert: *mut Object = msg_send![class!(NSAlert), new];
        let title = make_nsstring("Change Security Key PIN");
        let _: () = msg_send![alert, setMessageText: title];
        let _: () = msg_send![title, release];
        let text = make_nsstring(message);
        let _: () = msg_send![alert, setInformativeText: text];
        let _: () = msg_send![text, release];
        let _: () = msg_send![alert, setAlertStyle: NS_ALERT_STYLE_INFORMATIONAL];

        set_alert_icon(alert, "lock.rotation");

        let ok = make_nsstring("Change PIN");
        let _: () = msg_send![alert, addButtonWithTitle: ok];
        let _: () = msg_send![ok, release];
        let cancel_label = make_nsstring("Cancel");
        let _: () = msg_send![alert, addButtonWithTitle: cancel_label];
        let _: () = msg_send![cancel_label, release];

        let (container, fields) = make_pin_fields(&["Current PIN", "New PIN", "Confirm new PIN"]);
        let field1 = fields[0];
        let field2 = fields[1];
        let field3 = fields[2];
        let _: () = msg_send![alert, setAccessoryView: container];

        let window: *mut Object = msg_send![alert, window];
        let _: () = msg_send![window, setLevel: desired_window_level()];
        let _: () = msg_send![window, setInitialFirstResponder: field1];
        let _: () = msg_send![app, activateIgnoringOtherApps: YES];

        let response: i64 = msg_send![alert, runModal];

        let result = if response == NS_ALERT_FIRST_BUTTON {
            let current = read_secure_field(field1);
            let new_pin = read_secure_field(field2);
            let confirm = read_secure_field(field3);
            if current.is_empty() || new_pin.is_empty() {
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                continue;
            }
            if new_pin.as_bytes().len() < min_len {
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                let err_body = format!("PIN must be at least {} characters.", min_len);
                if !show_pin_error_dialog(app, "PIN Too Short", &err_body) {
                    return None;
                }
                continue;
            }
            if new_pin.as_bytes().len() > MAX_PIN_LENGTH_BYTES {
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                if !show_pin_error_dialog(app, "PIN Too Long", "PIN is too long (maximum 63 bytes).") {
                    return None;
                }
                continue;
            }
            if new_pin != confirm {
                let _: () = msg_send![container, release];
                let _: () = msg_send![alert, release];
                if !show_pin_error_dialog(app, "PINs Don't Match", "The new PINs you entered don't match. Please try again.") {
                    return None;
                }
                continue;
            }
            Some((current, new_pin))
        } else {
            None
        };

        let _: () = msg_send![container, release];
        let _: () = msg_send![alert, release];
        return result;
    }
}

// ---------------------------------------------------------------------------
// Credential picker dialog
// ---------------------------------------------------------------------------

/// Show a modal credential picker. Each credential is a button — one click to select.
/// Returns selected index or None if cancelled.
unsafe fn run_credential_picker(
    app: *mut Object,
    users: &[(Option<String>, Option<String>)],
) -> Option<usize> {
    let alert: *mut Object = msg_send![class!(NSAlert), new];
    let title = make_nsstring("Choose an Account");
    let _: () = msg_send![alert, setMessageText: title];
    let _: () = msg_send![title, release];
    let text = make_nsstring("Select which account to use:");
    let _: () = msg_send![alert, setInformativeText: text];
    let _: () = msg_send![text, release];
    let _: () = msg_send![alert, setAlertStyle: NS_ALERT_STYLE_INFORMATIONAL];

    set_alert_icon(alert, "person.2.fill");

    // Add one button per credential — return codes are 1000, 1001, 1002, ...
    for (display_name, name) in users {
        let label = display_name.as_deref()
            .or(name.as_deref())
            .unwrap_or("Unknown account");
        let ns_label = make_nsstring(label);
        let _: () = msg_send![alert, addButtonWithTitle: ns_label];
        let _: () = msg_send![ns_label, release];
    }

    // Cancel button last — Escape key dismisses
    let cancel_label = make_nsstring("Cancel");
    let _: () = msg_send![alert, addButtonWithTitle: cancel_label];
    let _: () = msg_send![cancel_label, release];
    let buttons: *mut Object = msg_send![alert, buttons];
    let cancel_idx = users.len();
    let cancel_btn: *mut Object = msg_send![buttons, objectAtIndex: cancel_idx];
    let esc = make_nsstring("\u{1b}");
    let _: () = msg_send![cancel_btn, setKeyEquivalent: esc];
    let _: () = msg_send![esc, release];

    let window: *mut Object = msg_send![alert, window];
    let _: () = msg_send![window, setLevel: desired_window_level()];
    let _: () = msg_send![app, activateIgnoringOtherApps: YES];

    let response: i64 = msg_send![alert, runModal];

    let idx = (response - NS_ALERT_FIRST_BUTTON) as usize;
    let _: () = msg_send![alert, release];

    if idx < users.len() { Some(idx) } else { None }
}

// ---------------------------------------------------------------------------
// NativeUI — Send-safe handle used from the messaging/FIDO threads
// ---------------------------------------------------------------------------

/// Handle for sending UI commands to the main thread.
/// Can be cloned and used from any thread.
pub struct NativeUI {
    cmd_tx: mpsc::Sender<UICommand>,
    user_cancelled: Arc<AtomicBool>,
}

impl NativeUI {
    pub fn new(cmd_tx: mpsc::Sender<UICommand>) -> Self {
        Self {
            cmd_tx,
            user_cancelled: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn is_cancelled(&self) -> bool {
        self.user_cancelled.load(Ordering::Relaxed)
    }

    pub fn dismiss(&mut self) {
        let _ = self.cmd_tx.send(UICommand::Dismiss);
    }

    fn show_status(&mut self, message: &str, style: i64, icon: &'static str) {
        let _ = self.cmd_tx.send(UICommand::ShowStatus {
            message: message.to_string(),
            style,
            icon,
            cancelled: self.user_cancelled.clone(),
        });
    }

    pub fn show_touch(&mut self) {
        self.show_status(
            "Touch your security key to continue.",
            NS_ALERT_STYLE_INFORMATIONAL,
            "hand.tap",
        );
    }

    pub fn show_insert(&mut self) {
        self.show_status(
            "Insert your security key to continue.",
            NS_ALERT_STYLE_INFORMATIONAL,
            "cable.connector.horizontal",
        );
    }

    pub fn show_select(&mut self) {
        self.show_status(
            "Touch the security key you want to use.",
            NS_ALERT_STYLE_INFORMATIONAL,
            "checklist",
        );
    }

    pub fn show_biometric(&mut self) {
        self.show_status(
            "Scan your fingerprint on the security key.",
            NS_ALERT_STYLE_INFORMATIONAL,
            "touchid",
        );
    }

    pub fn show_uv_retry(&mut self, retries: Option<u8>) {
        let msg = match retries {
            Some(r) => format!(
                "Fingerprint not recognized. Try again.\n{r} {} remaining.",
                if r == 1 { "attempt" } else { "attempts" }
            ),
            None => "Fingerprint not recognized. Try again.".to_string(),
        };
        self.show_status(&msg, NS_ALERT_STYLE_WARNING, "exclamationmark.triangle.fill");
    }

    pub fn show_status_msg(&mut self, message: &str) {
        self.show_status(message, NS_ALERT_STYLE_WARNING, "exclamationmark.triangle.fill");
    }

    /// Show a modal error dialog. Blocks until the user clicks OK.
    pub fn show_error(&mut self, message: &str, icon: &'static str) {
        let (done_tx, done_rx) = mpsc::channel();
        let _ = self.cmd_tx.send(UICommand::ShowError {
            message: message.to_string(),
            icon,
            done_tx,
        });
        // Block until the user acknowledges the error.
        let _ = done_rx.recv();
    }

    /// Show a modal nudge about fingerprint enrollment. Blocks until OK.
    pub fn show_bio_nudge(&mut self) {
        self.show_error(
            "Your security key supports fingerprint login, but no fingerprints are enrolled.\n\nUse your key manufacturer's app to set up fingerprints for faster, more secure sign-in.",
            "touchid",
        );
    }

    /// Show a PIN setup dialog (new + confirm). Blocks until submitted or cancelled.
    pub fn show_pin_setup_dialog(&mut self, message: &str) -> Option<String> {
        let (result_tx, result_rx) = mpsc::channel();
        let _ = self.cmd_tx.send(UICommand::ShowPinSetup {
            message: message.to_string(),
            result_tx,
        });
        result_rx.recv().ok().flatten()
    }

    /// Show a PIN change dialog (current + new + confirm). Blocks until submitted or cancelled.
    pub fn show_pin_change_dialog(&mut self, message: &str) -> Option<(String, String)> {
        let (result_tx, result_rx) = mpsc::channel();
        let _ = self.cmd_tx.send(UICommand::ShowPinChange {
            message: message.to_string(),
            result_tx,
        });
        result_rx.recv().ok().flatten()
    }

    /// Show a credential picker dialog. Blocks until the user selects or cancels.
    pub fn show_credential_picker(&mut self, users: &[(Option<String>, Option<String>)]) -> Option<usize> {
        let (result_tx, result_rx) = mpsc::channel();
        let _ = self.cmd_tx.send(UICommand::SelectCredential {
            users: users.to_vec(),
            result_tx,
        });
        result_rx.recv().ok().flatten()
    }

    /// Show a PIN entry dialog. Blocks until the user submits or cancels.
    pub fn show_pin_dialog(&mut self, message: &str) -> Option<String> {
        let (result_tx, result_rx) = mpsc::channel();
        let _ = self.cmd_tx.send(UICommand::ShowPin {
            message: message.to_string(),
            result_tx,
        });
        // Block until the main thread finishes the PIN dialog.
        result_rx.recv().ok().flatten()
    }
}

impl Drop for NativeUI {
    fn drop(&mut self) {
        let _ = self.cmd_tx.send(UICommand::Quit);
    }
}
