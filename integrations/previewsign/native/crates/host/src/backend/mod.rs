use anyhow::Result;
use sign_extension_protocol::{PipeRequest, PipeResponse};

/// Callback for requesting a PIN from the user (via browser extension).
pub trait PinRequester {
    fn request_pin(&mut self, message: &str) -> Option<String>;
    /// Request a new PIN (setup). UI shows New PIN + Confirm PIN fields.
    fn request_new_pin(&mut self, message: &str) -> Option<String>;
    /// Request a PIN change. UI shows Current PIN + New PIN + Confirm PIN fields.
    /// Returns (current_pin, new_pin).
    fn request_pin_change(&mut self, message: &str) -> Option<(String, String)>;
    fn notify_status(&mut self, status: &str);
    /// Show a credential picker when multiple resident credentials match.
    /// `users` contains (display_name, name) pairs. Returns selected index or None if cancelled.
    fn select_credential(&mut self, users: &[(Option<String>, Option<String>)]) -> Option<usize> {
        if users.is_empty() { None } else { Some(0) }
    }
    /// Check if the user cancelled via a native UI dialog (macOS).
    fn is_cancelled(&self) -> bool { false }
}

/// Trait abstracting the FIDO backend.
///
/// On macOS/Linux the host talks to authenticator-rs directly.
/// On Windows the host sends requests over a named pipe to an elevated helper
/// that calls webauthn.dll.
pub trait FidoBackend {
    fn execute(&mut self, request: &PipeRequest, pin_requester: &mut dyn PinRequester) -> Result<PipeResponse>;
}

#[cfg(not(target_os = "windows"))]
pub mod direct;

#[cfg(target_os = "windows")]
pub mod pipe;

/// Create the platform-appropriate backend.
pub fn create_backend() -> Result<Box<dyn FidoBackend + Send>> {
    #[cfg(not(target_os = "windows"))]
    {
        Ok(Box::new(direct::DirectBackend::new()))
    }
    #[cfg(target_os = "windows")]
    {
        Ok(Box::new(pipe::PipeBackend::connect()?))
    }
}
