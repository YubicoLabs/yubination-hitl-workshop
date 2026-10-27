use std::io;
use log::{debug, error, info};
use serde_json::{json, Value};

use crate::backend::PinRequester;
pub use crate::startup::{read_message, write_message};

/// PIN requester that uses the native messaging protocol.
///
/// On macOS, status dialogs and PIN entry use native AppKit (NSAlert) dialogs.
/// The extension only receives a "backdrop" command to dim the page.
///
/// On Linux, status and PIN are handled via browser extension overlays using
/// the multi-round needsPin/pinResponse protocol.
struct NativeMessagingPinRequester {
    request_id: String,
    #[cfg(target_os = "macos")]
    native_ui: crate::native_ui::NativeUI,
}

impl NativeMessagingPinRequester {
    fn send_status(&self, status: &str) {
        let msg = json!({
            "requestId": self.request_id,
            "type": "status",
            "status": status,
        });
        let mut stdout = io::stdout().lock();
        let _ = write_message(&mut stdout, &msg);
    }

    #[cfg(not(target_os = "macos"))]
    fn select_credential_extension(&mut self, users: &[(Option<String>, Option<String>)]) -> Option<usize> {
        let user_list: Vec<serde_json::Value> = users.iter().map(|(display_name, name)| {
            json!({
                "displayName": display_name,
                "name": name,
            })
        }).collect();
        let msg = json!({
            "requestId": self.request_id,
            "needsSelect": true,
            "users": user_list,
        });
        info!("Sending needsSelect to extension ({} users)", users.len());
        {
            let mut stdout = io::stdout().lock();
            if write_message(&mut stdout, &msg).is_err() {
                error!("Failed to write needsSelect message");
                return None;
            }
        }

        let response = {
            let mut stdin = io::stdin().lock();
            match read_message(&mut stdin) {
                Ok(Some(msg)) => msg,
                Ok(None) => {
                    error!("stdin closed while waiting for credential selection");
                    return None;
                }
                Err(e) => {
                    error!("Failed to read select response: {e}");
                    return None;
                }
            }
        };

        if response.get("type").and_then(|v| v.as_str()) == Some("selectResponse") {
            response.get("index").and_then(|v| v.as_u64()).map(|i| i as usize)
        } else {
            error!("Expected selectResponse, got: {}", response.get("type").and_then(|v| v.as_str()).unwrap_or("unknown"));
            None
        }
    }

    #[cfg(not(target_os = "macos"))]
    fn request_pin_extension(&mut self, message: &str) -> Option<String> {
        let msg = json!({
            "requestId": self.request_id,
            "needsPin": true,
            "message": message,
        });
        info!("Sending needsPin to extension");
        {
            let mut stdout = io::stdout().lock();
            if write_message(&mut stdout, &msg).is_err() {
                error!("Failed to write needsPin message");
                return None;
            }
        }

        let response = {
            let mut stdin = io::stdin().lock();
            match read_message(&mut stdin) {
                Ok(Some(msg)) => msg,
                Ok(None) => {
                    error!("stdin closed while waiting for PIN");
                    return None;
                }
                Err(e) => {
                    error!("Failed to read PIN response: {e}");
                    return None;
                }
            }
        };

        debug!("Received message while waiting for PIN: type={:?}",
            response.get("type").and_then(|v| v.as_str()));

        if response.get("type").and_then(|v| v.as_str()) == Some("pinResponse") {
            response.get("pin").and_then(|v| v.as_str()).map(String::from)
        } else {
            error!("Expected pinResponse, got: {}", response.get("type").and_then(|v| v.as_str()).unwrap_or("unknown"));
            None
        }
    }

    /// Extract minimum PIN length from message like "Minimum 6 characters."
    #[cfg(not(target_os = "macos"))]
    fn extract_min_pin_length(message: &str) -> u64 {
        // Look for "Minimum N characters" pattern
        if let Some(pos) = message.find("Minimum ") {
            let rest = &message[pos + 8..];
            if let Some(end) = rest.find(' ') {
                if let Ok(n) = rest[..end].parse::<u64>() {
                    return n;
                }
            }
        }
        4 // CTAP2 default
    }

    #[cfg(not(target_os = "macos"))]
    fn request_pin_setup_extension(&mut self, message: &str) -> Option<String> {
        let min_length = Self::extract_min_pin_length(message);
        let msg = json!({
            "requestId": self.request_id,
            "needsPinSetup": true,
            "message": message,
            "minLength": min_length,
        });
        info!("Sending needsPinSetup to extension");
        {
            let mut stdout = io::stdout().lock();
            if write_message(&mut stdout, &msg).is_err() {
                error!("Failed to write needsPinSetup message");
                return None;
            }
        }

        let response = {
            let mut stdin = io::stdin().lock();
            match read_message(&mut stdin) {
                Ok(Some(msg)) => msg,
                Ok(None) => {
                    error!("stdin closed while waiting for PIN setup");
                    return None;
                }
                Err(e) => {
                    error!("Failed to read PIN setup response: {e}");
                    return None;
                }
            }
        };

        if response.get("type").and_then(|v| v.as_str()) == Some("pinSetupResponse") {
            response.get("pin").and_then(|v| v.as_str()).map(String::from)
        } else {
            error!("Expected pinSetupResponse, got: {}", response.get("type").and_then(|v| v.as_str()).unwrap_or("unknown"));
            None
        }
    }

    #[cfg(not(target_os = "macos"))]
    fn request_pin_change_extension(&mut self, message: &str) -> Option<(String, String)> {
        let min_length = Self::extract_min_pin_length(message);
        let msg = json!({
            "requestId": self.request_id,
            "needsPinChange": true,
            "message": message,
            "minLength": min_length,
        });
        info!("Sending needsPinChange to extension");
        {
            let mut stdout = io::stdout().lock();
            if write_message(&mut stdout, &msg).is_err() {
                error!("Failed to write needsPinChange message");
                return None;
            }
        }

        let response = {
            let mut stdin = io::stdin().lock();
            match read_message(&mut stdin) {
                Ok(Some(msg)) => msg,
                Ok(None) => {
                    error!("stdin closed while waiting for PIN change");
                    return None;
                }
                Err(e) => {
                    error!("Failed to read PIN change response: {e}");
                    return None;
                }
            }
        };

        if response.get("type").and_then(|v| v.as_str()) == Some("pinChangeResponse") {
            let current = response.get("currentPin").and_then(|v| v.as_str()).map(String::from);
            let new_pin = response.get("newPin").and_then(|v| v.as_str()).map(String::from);
            match (current, new_pin) {
                (Some(c), Some(n)) => Some((c, n)),
                _ => None,
            }
        } else {
            error!("Expected pinChangeResponse, got: {}", response.get("type").and_then(|v| v.as_str()).unwrap_or("unknown"));
            None
        }
    }
}

impl PinRequester for NativeMessagingPinRequester {
    fn notify_status(&mut self, status: &str) {
        #[cfg(target_os = "macos")]
        {
            match status {
                "touch" => {
                    self.native_ui.show_touch();
                    self.send_status("native_prompt");
                }
                "insert" => {
                    self.native_ui.show_insert();
                    self.send_status("native_prompt");
                }
                "select" => {
                    self.native_ui.show_select();
                    self.send_status("native_prompt");
                }
                "biometric" => {
                    self.native_ui.show_biometric();
                    self.send_status("native_prompt");
                }
                s if s.starts_with("biometric_retry:") => {
                    let retries = s
                        .strip_prefix("biometric_retry:")
                        .and_then(|r| r.parse::<u8>().ok());
                    self.native_ui.show_uv_retry(retries);
                    self.send_status("native_prompt");
                }
                "uv_blocked" => {
                    self.native_ui
                        .show_status_msg("Too many failed attempts. Falling back to PIN.");
                    self.send_status("native_prompt");
                }
                "pin_blocked" => {
                    self.send_status("native_prompt");
                    self.native_ui
                        .show_error("Your security key PIN is permanently locked.\n\nThe key must be factory reset before it can be used again.", "xmark.octagon.fill");
                }
                "pin_auth_blocked" => {
                    self.send_status("native_prompt");
                    self.native_ui
                        .show_error("Too many incorrect PIN attempts.\n\nRemove and re-insert your security key to try again.", "exclamationmark.triangle.fill");
                }
                "pin_not_set" => {
                    self.send_status("native_prompt");
                    self.native_ui
                        .show_error("Your security key requires a PIN, but none is set.\n\nUse your key manufacturer's app to set a PIN.", "exclamationmark.triangle.fill");
                }
                "bio_not_enrolled" => {
                    self.send_status("native_prompt");
                    self.native_ui
                        .show_bio_nudge();
                }
                "done" => {
                    self.native_ui.dismiss();
                    self.send_status("done");
                }
                other => {
                    self.send_status(other);
                }
            }
            return;
        }
        #[cfg(not(target_os = "macos"))]
        {
            self.send_status(status);
        }
    }

    fn request_pin(&mut self, message: &str) -> Option<String> {
        #[cfg(target_os = "macos")]
        {
            self.send_status("native_prompt");
            info!("Showing native PIN dialog");
            let pin = self.native_ui.show_pin_dialog(message);
            self.send_status("done");
            return pin;
        }
        #[cfg(not(target_os = "macos"))]
        {
            self.request_pin_extension(message)
        }
    }

    fn request_new_pin(&mut self, message: &str) -> Option<String> {
        #[cfg(target_os = "macos")]
        {
            self.send_status("native_prompt");
            info!("Showing native PIN setup dialog");
            let pin = self.native_ui.show_pin_setup_dialog(message);
            self.send_status("done");
            return pin;
        }
        #[cfg(not(target_os = "macos"))]
        {
            self.request_pin_setup_extension(message)
        }
    }

    fn request_pin_change(&mut self, message: &str) -> Option<(String, String)> {
        #[cfg(target_os = "macos")]
        {
            self.send_status("native_prompt");
            info!("Showing native PIN change dialog");
            let pins = self.native_ui.show_pin_change_dialog(message);
            self.send_status("done");
            return pins;
        }
        #[cfg(not(target_os = "macos"))]
        {
            self.request_pin_change_extension(message)
        }
    }

    fn select_credential(&mut self, users: &[(Option<String>, Option<String>)]) -> Option<usize> {
        #[cfg(target_os = "macos")]
        {
            self.send_status("native_prompt");
            info!("Showing native credential picker ({} users)", users.len());
            let result = self.native_ui.show_credential_picker(users);
            self.send_status("done");
            return result;
        }
        #[cfg(not(target_os = "macos"))]
        {
            self.select_credential_extension(users)
        }
    }

    fn is_cancelled(&self) -> bool {
        #[cfg(target_os = "macos")]
        {
            return self.native_ui.is_cancelled();
        }
        #[cfg(not(target_os = "macos"))]
        {
            false
        }
    }
}

/// Message loop using a multi-round PIN protocol.
#[cfg(target_os = "macos")]
pub fn message_loop(
    backend: &mut dyn crate::backend::FidoBackend,
    first_message: Value,
    ui_tx: std::sync::mpsc::Sender<crate::native_ui::UICommand>,
) {
    message_loop_inner(backend, first_message, ui_tx);
}

#[cfg(not(target_os = "macos"))]
pub fn message_loop(backend: &mut dyn crate::backend::FidoBackend, first_message: Value) {
    message_loop_inner(backend, first_message);
}

fn message_loop_inner(
    backend: &mut dyn crate::backend::FidoBackend,
    first_message: Value,
    #[cfg(target_os = "macos")] ui_tx: std::sync::mpsc::Sender<crate::native_ui::UICommand>,
) {
    let mut first_message = Some(first_message);
    loop {
        let msg = if let Some(message) = first_message.take() {
            message
        } else {
            let mut stdin = io::stdin().lock();
            match read_message(&mut stdin) {
                Ok(Some(msg)) => msg,
                Ok(None) => {
                    info!("Input stream closed, exiting");
                    break;
                }
                Err(e) => {
                    error!("Failed to read message: {e}");
                    break;
                }
            }
        };

        debug!("Processing message");
        let request_id = msg
            .get("requestId")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let mut pin_requester = NativeMessagingPinRequester {
            request_id: request_id.clone(),
            #[cfg(target_os = "macos")]
            native_ui: crate::native_ui::NativeUI::new(ui_tx.clone()),
        };
        let response = crate::webauthn::handle_message(backend, &mut pin_requester, msg);

        let mut stdout = io::stdout().lock();
        if let Err(e) = write_message(&mut stdout, &response) {
            error!("Failed to write response: {e}");
            break;
        }
    }
}
