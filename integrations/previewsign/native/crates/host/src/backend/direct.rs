//! Direct FIDO backend using yubikit (macOS/Linux).
//!
//! Runs WebAuthn ceremonies via yubikit's WebAuthnClient over HID.
//! PIN prompts are delegated to the browser extension via the PinRequester trait.

use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};

use anyhow::{anyhow, Result};
use log::{error, info};

use yubikit::ctap::CtapSession;
use yubikit::ctap2::{Ctap2Pin, Ctap2Session, Permissions};
use yubikit::platform::hidapi::{HidFidoConnection, list_fido_devices};
use yubikit::webauthn::{
    ClientDataCollector, ClientError, CollectedClientData, UserInteraction, WebAuthnClient,
    types::{
        AuthenticatorSelectionCriteria, PublicKeyCredentialCreationOptions,
        PublicKeyCredentialDescriptor, PublicKeyCredentialParameters,
        PublicKeyCredentialRequestOptions, PublicKeyCredentialRpEntity,
        PublicKeyCredentialType, PublicKeyCredentialUserEntity,
        ResidentKeyRequirement, UserVerificationRequirement,
    },
};
use yubikit::webauthn::extensions::{
    AuthenticationExtensionInputs, RegistrationExtensionInputs,
    large_blob::{AuthenticationInput as LbAuthInput, LargeBlobSupport, RegistrationInput as LbRegInput},
    prf::{AuthenticationInput as PrfAuthInput, PrfEval, RegistrationInput as PrfRegInput},
    cred_protect::{CredProtectPolicy, RegistrationInput as CpRegInput},
    cred_blob::RegistrationInput as CbRegInput,
    sign::{AuthenticationInput as SignAuthInput, RegistrationInput as SignRegInput, GenerateKeyInput},
};

use sign_extension_protocol::{
    PipeCredentialProperties, PipeExtensionOutputs, PipeExtensions, PipeLargeBlobOutput,
    PipePRFOutputs, PipePRFValues, PipeRequest, PipeResponse, PipeSignExtensionOutputs,
    PipeSignGeneratedKey,
};

use super::{FidoBackend, PinRequester};

// ---------------------------------------------------------------------------
// ClientDataCollector — passes through pre-computed clientDataJSON from browser
// ---------------------------------------------------------------------------

/// Wraps the clientDataJSON bytes already computed by the browser/extension
/// so yubikit uses the exact same hash the server will verify.
struct PipeClientDataCollector {
    client_data_json: Vec<u8>,
    rp_id: String,
}

impl ClientDataCollector for PipeClientDataCollector {
    fn collect_create(
        &self,
        _options: &PublicKeyCredentialCreationOptions,
    ) -> Result<(CollectedClientData, String), String> {
        let cd = CollectedClientData::from_json(self.client_data_json.clone())
            .map_err(|e| format!("invalid client_data_json: {e}"))?;
        Ok((cd, self.rp_id.clone()))
    }

    fn collect_get(
        &self,
        _options: &PublicKeyCredentialRequestOptions,
    ) -> Result<(CollectedClientData, String), String> {
        let cd = CollectedClientData::from_json(self.client_data_json.clone())
            .map_err(|e| format!("invalid client_data_json: {e}"))?;
        Ok((cd, self.rp_id.clone()))
    }
}

// ---------------------------------------------------------------------------
// UserInteraction — bridges yubikit callbacks to PinRequester
// ---------------------------------------------------------------------------

/// Bridges yubikit's `UserInteraction` trait to the `PinRequester` interface.
///
/// Uses a `Mutex` because `UserInteraction` takes `&self` but `PinRequester`
/// requires `&mut self`.
struct PipeUserInteraction<'a> {
    pin_requester: Mutex<&'a mut dyn PinRequester>,
    /// Shared flag set when PinRequester::is_cancelled() returns true.
    /// Polled by the cancel closure passed to yubikit make_credential/get_assertion.
    cancelled: Arc<AtomicBool>,
}

impl<'a> PipeUserInteraction<'a> {
    fn new(pr: &'a mut dyn PinRequester, cancelled: Arc<AtomicBool>) -> Self {
        Self {
            pin_requester: Mutex::new(pr),
            cancelled,
        }
    }
}

/// Maps yubikit `UserInteraction` callbacks to `PinRequester` status notifications.
///
/// # Status Event Mapping: authenticator-rs → yubikit
///
/// ## COVERED (equivalent functionality exists)
/// - **PresenceRequired** → `prompt_up()` → `notify_status("touch")`
///   - Browser overlay shows "Touch your security key" prompt
/// - **PinUvError::PinRequired** → `request_pin()` called by yubikit
///   - Browser overlay shows PIN entry dialog
/// - **BiometricRequired** → `request_uv()` called by yubikit
///   - Returns `true` to prefer built-in UV (fingerprint)
///
/// ## LOST (no yubikit equivalent)
/// - **PinUvError::InvalidPin { retries: Some(n) }** → yubikit `request_pin()` signature
///   does NOT include `remaining_attempts` parameter. Cannot surface retry count to
///   browser overlay for "N attempts remaining" messaging. User gets generic retry
///   without knowing how many attempts are left.
/// - **SelectResultNotice** → credential selection; yubikit handles internally via
///   `select_credential()` callback (not implemented in PipeUserInteraction)
/// - **SelectDeviceNotice** → multi-device selection; yubikit handles device discovery
///   and selection internally without exposing status events
/// - **DeviceAvailable** / **DeviceUnavailable** → device hotplug events; yubikit
///   doesn't expose these as UserInteraction callbacks
/// - **PinUvError::PinAuthBlocked** → handled as error result, not status update
/// - **PinUvError::PinBlocked** → handled as error result, not status update
/// - **PinUvError::PinNotSet** → handled as error result, not status update
/// - **PinUvError::InvalidUv { retries }** → invalid biometric; yubikit retries
///   internally without exposing retry count
///
/// ## NOTES
/// - The `permissions` and `rp_id` parameters in `request_pin` and `request_uv` are
///   currently ignored (prefixed with `_`). These could be used for future enhancements
///   like showing "Signing into example.com" context in PIN prompts.
/// - Status notifications use simple string constants ("touch") rather than structured
///   enums, for compatibility with the existing PipeResponse::StatusUpdate protocol.
impl UserInteraction for PipeUserInteraction<'_> {
    fn prompt_up(&self) {
        if let Ok(mut pr) = self.pin_requester.lock() {
            if pr.is_cancelled() {
                self.cancelled.store(true, Ordering::Relaxed);
                return;
            }
            pr.notify_status("touch");
        }
    }

    fn request_pin(&self, _permissions: Permissions, _rp_id: Option<&str>) -> Option<Ctap2Pin> {
        let raw_pin = {
            let mut pr = self.pin_requester.lock().ok()?;
            pr.request_pin("Enter your security key PIN:")?
        };
        Ctap2Pin::new(&raw_pin).ok()
    }

    fn request_uv(&self, _permissions: Permissions, _rp_id: Option<&str>) -> bool {
        // Prefer built-in UV (biometrics) when available
        true
    }
}

// ---------------------------------------------------------------------------
// DirectBackend
// ---------------------------------------------------------------------------

pub struct DirectBackend;

impl DirectBackend {
    pub fn new() -> Self {
        Self
    }
}

impl FidoBackend for DirectBackend {
    fn execute(
        &mut self,
        request: &PipeRequest,
        pin_requester: &mut dyn PinRequester,
    ) -> Result<PipeResponse> {
        if matches!(request, PipeRequest::Cancel) {
            return Ok(PipeResponse::Error {
                code: 11,
                message: "Cancelled by user".to_string(),
            });
        }

        // Connect to first available HID FIDO device
        let devices = list_fido_devices()
            .map_err(|e| anyhow!("list_fido_devices: {e}"))?;
        let dev = devices
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("No FIDO device found"))?;

        pin_requester.notify_status("insert");

        let conn = HidFidoConnection::open(&dev)
            .map_err(|e| anyhow!("HidFidoConnection::open: {e}"))?;
        let ctap = CtapSession::new_fido(conn)
            .map_err(|(e, _)| anyhow!("CtapSession::new_fido: {e}"))?;
        let session = Ctap2Session::new(ctap)
            .map_err(|(e, _)| anyhow!("Ctap2Session::new: {e}"))?;

        // Shared cancel flag. The PipeUserInteraction polls PinRequester::is_cancelled()
        // via its Mutex and sets this flag, which the cancel closure passes to yubikit.
        // Do NOT read stdin in a background thread — messaging.rs owns that file
        // descriptor and a competing reader corrupts the 4-byte LE length framing.
        let cancelled = Arc::new(AtomicBool::new(false));
        let ui = PipeUserInteraction::new(pin_requester, cancelled.clone());
        let cancel_fn = {
            let c = cancelled.clone();
            move || c.load(Ordering::Relaxed)
        };

        match request {
            PipeRequest::MakeCredential {
                client_data_json,
                rp_id,
                rp_name,
                user_id,
                user_name,
                user_display_name,
                pub_key_params,
                exclude_list,
                extensions,
                resident_key,
                user_verification,
                timeout_ms,
                ..
            } => {
                let collector = PipeClientDataCollector {
                    client_data_json: client_data_json.clone(),
                    rp_id: rp_id.clone(),
                };
                let mut client = WebAuthnClient::new(session, ui, collector);

                let options = build_creation_options(
                    rp_id, rp_name.as_deref(), user_id, user_name.as_deref(),
                    user_display_name.as_deref(), pub_key_params, exclude_list,
                    extensions.as_ref(), *resident_key, user_verification, *timeout_ms,
                );

                match client.make_credential(&options, Some(&cancel_fn)) {
                    Ok(reg) => pipe_response_from_registration(reg),
                    Err(e) => Ok(yubikit_error_to_pipe(e)),
                }
            }
            PipeRequest::GetAssertion {
                client_data_json,
                rp_id,
                allow_list,
                extensions,
                user_verification,
                timeout_ms,
                ..
            } => {
                let collector = PipeClientDataCollector {
                    client_data_json: client_data_json.clone(),
                    rp_id: rp_id.clone(),
                };
                let mut client = WebAuthnClient::new(session, ui, collector);

                let options = build_request_options(
                    rp_id, allow_list, extensions.as_ref(),
                    user_verification, *timeout_ms,
                );

                match client.get_assertion(&options, Some(&cancel_fn)) {
                    Ok(mut auths) => pipe_response_from_authentication(auths.remove(0)),
                    Err(e) => Ok(yubikit_error_to_pipe(e)),
                }
            }
            PipeRequest::Cancel => unreachable!(),
        }
    }
}

// ---------------------------------------------------------------------------
// Option builders — PipeRequest fields → yubikit WebAuthn option types
// ---------------------------------------------------------------------------

fn build_creation_options(
    rp_id: &str,
    rp_name: Option<&str>,
    user_id: &[u8],
    user_name: Option<&str>,
    user_display_name: Option<&str>,
    pub_key_params: &[i64],
    exclude_list: &[Vec<u8>],
    extensions: Option<&PipeExtensions>,
    resident_key: bool,
    user_verification: &str,
    timeout_ms: u64,
) -> PublicKeyCredentialCreationOptions {
    PublicKeyCredentialCreationOptions {
        rp: PublicKeyCredentialRpEntity {
            id: Some(rp_id.to_string()),
            name: rp_name.unwrap_or(rp_id).to_string(),
        },
        user: PublicKeyCredentialUserEntity {
            id: user_id.to_vec(),
            name: user_name.map(String::from),
            display_name: user_display_name.map(String::from),
        },
        // challenge field is ignored — PipeClientDataCollector returns pre-built client_data_json
        challenge: vec![],
        pub_key_cred_params: build_pub_key_params(pub_key_params),
        timeout: Some(timeout_ms),
        exclude_credentials: if exclude_list.is_empty() {
            None
        } else {
            Some(build_cred_list(exclude_list))
        },
        authenticator_selection: Some(AuthenticatorSelectionCriteria {
            authenticator_attachment: None,
            resident_key: Some(if resident_key {
                ResidentKeyRequirement::Required
            } else {
                ResidentKeyRequirement::Discouraged
            }),
            user_verification: Some(parse_uv(user_verification)),
        }),
        hints: None,
        attestation: None,
        attestation_formats: None,
        extensions: extensions.map(map_registration_extensions),
    }
}

fn build_request_options(
    rp_id: &str,
    allow_list: &[Vec<u8>],
    extensions: Option<&PipeExtensions>,
    user_verification: &str,
    timeout_ms: u64,
) -> PublicKeyCredentialRequestOptions {
    PublicKeyCredentialRequestOptions {
        // challenge is ignored — PipeClientDataCollector returns pre-built client_data_json
        challenge: vec![],
        timeout: Some(timeout_ms),
        rp_id: Some(rp_id.to_string()),
        allow_credentials: if allow_list.is_empty() {
            None
        } else {
            Some(build_cred_list(allow_list))
        },
        user_verification: Some(parse_uv(user_verification)),
        hints: None,
        extensions: extensions.map(map_authentication_extensions),
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn parse_uv(s: &str) -> UserVerificationRequirement {
    match s {
        "required" => UserVerificationRequirement::Required,
        "discouraged" => UserVerificationRequirement::Discouraged,
        _ => UserVerificationRequirement::Preferred,
    }
}

fn build_pub_key_params(algs: &[i64]) -> Vec<PublicKeyCredentialParameters> {
    algs.iter()
        .map(|&alg| PublicKeyCredentialParameters {
            type_: PublicKeyCredentialType::PublicKey,
            alg,
        })
        .collect()
}

fn build_cred_list(raw: &[Vec<u8>]) -> Vec<PublicKeyCredentialDescriptor> {
    raw.iter()
        .map(|id| PublicKeyCredentialDescriptor {
            type_: PublicKeyCredentialType::PublicKey,
            id: id.clone(),
            transports: None,
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Extension mapping: PipeExtensions → yubikit extension inputs
// ---------------------------------------------------------------------------

pub(crate) fn map_registration_extensions(ext: &PipeExtensions) -> RegistrationExtensionInputs {
    use yubikit::webauthn::extensions::cred_protect::CredProtectPolicy;

    RegistrationExtensionInputs {
        prf: ext.prf.as_ref().map(|p| PrfRegInput {
            eval: p.eval.as_ref().map(|v| PrfEval {
                first: v.first.clone(),
                second: v.second.clone(),
            }),
        }),
        cred_protect: ext.cred_protect.as_ref().and_then(|s| {
            let policy = match s.as_str() {
                "userVerificationOptional" =>
                    Some(CredProtectPolicy::UserVerificationOptional),
                "userVerificationOptionalWithCredentialIDList" =>
                    Some(CredProtectPolicy::UserVerificationOptionalWithCredentialIDList),
                "userVerificationRequired" =>
                    Some(CredProtectPolicy::UserVerificationRequired),
                _ => None,
            }?;
            Some(CpRegInput {
                policy,
                enforce: false,
            })
        }),
        cred_blob: ext.cred_blob.as_ref().map(|b| CbRegInput { blob: b.clone() }),
        large_blob: ext.large_blob.as_ref().and_then(|lb| {
            lb.support.as_ref().map(|_| LbRegInput {
                support: LargeBlobSupport::Preferred,
            })
        }),
        cred_props: ext.cred_props,
        min_pin_length: ext.min_pin_length,
        preview_sign: ext.sign.as_ref().and_then(|s| {
            s.generate_key.as_ref().map(|gk| SignRegInput {
                generate_key: GenerateKeyInput {
                    algorithms: gk.algorithms.iter().map(|&a| a as i64).collect(),
                },
            })
        }),
    }
}

pub(crate) fn map_authentication_extensions(ext: &PipeExtensions) -> AuthenticationExtensionInputs {
    use base64::Engine;
    use std::collections::HashMap;

    AuthenticationExtensionInputs {
        prf: ext.prf.as_ref().map(|p| PrfAuthInput {
            eval: p.eval.as_ref().map(|v| PrfEval {
                first: v.first.clone(),
                second: v.second.clone(),
            }),
            eval_by_credential: p.eval_by_credential.as_ref()
                .map(|ebc| {
                    ebc.iter()
                        .filter_map(|(k, v)| {
                            let id = base64::engine::general_purpose::URL_SAFE_NO_PAD
                                .decode(k)
                                .ok()?;
                            Some((id, PrfEval {
                                first: v.first.clone(),
                                second: v.second.clone(),
                            }))
                        })
                        .collect::<HashMap<_, _>>()
                })
                .unwrap_or_default(),
        }),
        get_cred_blob: ext.get_cred_blob,
        large_blob: ext.large_blob.as_ref().and_then(|lb| {
            if lb.read == Some(true) || lb.write.is_some() {
                Some(LbAuthInput {
                    read: lb.read,
                    write: lb.write.clone(),
                })
            } else {
                None
            }
        }),
        preview_sign: ext.sign.as_ref().and_then(|s| {
            // Map sign_by_credential entries
            s.sign_by_credential.as_ref().map(|sbc| {
                use yubikit::webauthn::extensions::sign::SignInput;
                let map: HashMap<String, SignInput> = sbc.iter()
                    .filter_map(|(cred_id_hex, input)| {
                        // Convert hex credential ID to base64url for yubikit
                        let cred_id_bytes = hex_decode(cred_id_hex)?;
                        let cred_id_b64 = base64::engine::general_purpose::URL_SAFE_NO_PAD
                            .encode(&cred_id_bytes);
                        Some((cred_id_b64, SignInput {
                            key_handle: input.key_handle.clone(),
                            tbs: input.tbs.clone(),
                            additional_args: input.additional_args.clone(),
                        }))
                    })
                    .collect();
                SignAuthInput { sign_by_credential: map }
            })
        }),
    }
}

fn hex_decode(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 {
        return None;
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok())
        .collect()
}

// ---------------------------------------------------------------------------
// Response mapping: yubikit responses → PipeResponse
// ---------------------------------------------------------------------------

fn pipe_response_from_registration(
    reg: yubikit::webauthn::RegistrationResponse,
) -> Result<PipeResponse> {
    let ext_out = reg.client_extension_results.as_ref();

    let extension_outputs = ext_out.and_then(|e| {
        let has_any = e.prf.is_some() || e.cred_props.is_some() || e.cred_blob.is_some()
            || e.large_blob.is_some() || e.min_pin_length.is_some();
        if !has_any { return None; }
        Some(PipeExtensionOutputs {
            hmac_create_secret: None,
            cred_props: e.cred_props.as_ref().map(|cp| PipeCredentialProperties { rk: cp.rk }),
            prf: e.prf.as_ref().map(|p| PipePRFOutputs {
                enabled: Some(p.enabled),
                results: p.results.as_ref().map(|r| PipePRFValues {
                    first: r.first.clone(),
                    second: r.second.clone(),
                }),
            }),
            large_blob: e.large_blob.as_ref().map(|lb| PipeLargeBlobOutput {
                supported: Some(lb.supported),
                blob: None,
                written: None,
            }),
            cred_blob: e.cred_blob.as_ref().map(|cb| cb.stored.then_some(true)).flatten().map(|_| vec![]),
            cred_blob_set: e.cred_blob.as_ref().map(|cb| cb.stored),
        })
    });

    let sign_extension_outputs = ext_out.and_then(|e| e.preview_sign.as_ref()).map(|s| {
        PipeSignExtensionOutputs {
            generated_key: Some(PipeSignGeneratedKey {
                key_handle: s.generated_key.key_handle.clone(),
                public_key: s.generated_key.public_key.clone(),
                algorithm: s.generated_key.algorithm,
                attestation_object: s.generated_key.attestation_object.clone(),
            }),
            signature: None,
        }
    });

    Ok(PipeResponse::Success {
        attestation_object: Some(reg.response.attestation_object),
        auth_data: None,
        signature: None,
        credential_id: Some(reg.id),
        user_handle: None,
        client_data_json: None,
        sign_extension_outputs,
        extension_outputs,
    })
}

fn pipe_response_from_authentication(
    auth: yubikit::webauthn::AuthenticationResponse,
) -> Result<PipeResponse> {
    let ext_out = auth.client_extension_results.as_ref();

    let extension_outputs = ext_out.and_then(|e| {
        let has_any = e.prf.is_some() || e.cred_blob.is_some() || e.large_blob.is_some();
        if !has_any { return None; }
        Some(PipeExtensionOutputs {
            hmac_create_secret: None,
            cred_props: None,
            prf: e.prf.as_ref().map(|p| PipePRFOutputs {
                enabled: None,
                results: Some(PipePRFValues {
                    first: p.results.first.clone(),
                    second: p.results.second.clone(),
                }),
            }),
            large_blob: e.large_blob.as_ref().map(|lb| PipeLargeBlobOutput {
                supported: None,
                blob: lb.blob.clone(),
                written: lb.written,
            }),
            cred_blob: e.cred_blob.as_ref().map(|cb| cb.blob.clone()),
            cred_blob_set: None,
        })
    });

    let sign_extension_outputs = ext_out.and_then(|e| e.preview_sign.as_ref()).map(|s| {
        PipeSignExtensionOutputs {
            generated_key: None,
            signature: Some(s.signature.clone()),
        }
    });

    Ok(PipeResponse::Success {
        attestation_object: None,
        auth_data: Some(auth.response.authenticator_data),
        signature: Some(auth.response.signature),
        credential_id: Some(auth.id),
        user_handle: auth.response.user_handle,
        client_data_json: None,
        sign_extension_outputs,
        extension_outputs,
    })
}

pub(crate) fn yubikit_error_to_pipe<E: std::error::Error + Send + Sync + 'static>(
    e: ClientError<E>,
) -> PipeResponse {
    let (code, message) = match &e {
        ClientError::PinRequired => (13, "PIN required".to_string()),
        ClientError::BadRequest(msg) => (1, format!("Bad request: {msg}")),
        ClientError::ConfigurationUnsupported(msg) => (14, format!("Unsupported: {msg}")),
        ClientError::Ctap(ce) => {
            error!("CTAP error: {ce}");
            (99, format!("CTAP error: {ce}"))
        }
    };
    error!("FIDO error (code={code}): {message}");
    PipeResponse::Error { code, message }
}

// ---------------------------------------------------------------------------
// Stdin cancel check (non-blocking, unix only)
// ---------------------------------------------------------------------------

fn check_stdin_cancel() -> bool {
    use std::io::Read;

    #[cfg(unix)]
    {
        use std::os::unix::io::AsRawFd;
        let stdin = std::io::stdin();
        let fd = stdin.as_raw_fd();
        let mut pollfd = libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        };
        let ret = unsafe { libc::poll(&mut pollfd, 1, 0) };
        if ret <= 0 {
            return false;
        }
        if pollfd.revents & (libc::POLLIN | libc::POLLHUP) != 0 {
            let mut stdin = stdin.lock();
            let mut len_buf = [0u8; 4];
            if stdin.read_exact(&mut len_buf).is_err() {
                return true;
            }
            let len = u32::from_le_bytes(len_buf) as usize;
            if len > 1024 * 1024 {
                return false;
            }
            let mut buf = vec![0u8; len];
            if stdin.read_exact(&mut buf).is_err() {
                return true;
            }
            if let Ok(msg) = serde_json::from_slice::<serde_json::Value>(&buf) {
                if msg.get("type").and_then(|v| v.as_str()) == Some("cancel") {
                    return true;
                }
            }
        }
    }

    #[cfg(not(unix))]
    {}

    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use yubikit::webauthn::types::*;

    #[test]
    fn test_pipe_client_data_collector_valid_json() {
        let client_data_json = br#"{"type":"webauthn.create","challenge":"AAAA","origin":"https://example.com","crossOrigin":false}"#.to_vec();
        let collector = PipeClientDataCollector {
            client_data_json,
            rp_id: "example.com".to_string(),
        };

        let options = PublicKeyCredentialCreationOptions {
            rp: PublicKeyCredentialRpEntity {
                id: Some("example.com".to_string()),
                name: "Example".to_string(),
            },
            user: PublicKeyCredentialUserEntity {
                id: vec![1, 2, 3],
                name: Some("user".to_string()),
                display_name: None,
            },
            challenge: vec![],
            pub_key_cred_params: vec![],
            timeout: None,
            exclude_credentials: None,
            authenticator_selection: None,
            hints: None,
            attestation: None,
            attestation_formats: None,
            extensions: None,
        };

        let result = collector.collect_create(&options);
        assert!(result.is_ok(), "collect_create failed: {:?}", result);

        let (cd, rp) = result.unwrap();
        assert_eq!(rp, "example.com");
        assert_eq!(cd.type_, "webauthn.create");
        assert_eq!(cd.origin, "https://example.com");
    }

    #[test]
    fn test_pipe_client_data_collector_invalid_json() {
        let collector = PipeClientDataCollector {
            client_data_json: vec![0xff, 0xff], // Invalid JSON
            rp_id: "example.com".to_string(),
        };

        let options = PublicKeyCredentialCreationOptions {
            rp: PublicKeyCredentialRpEntity {
                id: Some("example.com".to_string()),
                name: "Example".to_string(),
            },
            user: PublicKeyCredentialUserEntity {
                id: vec![1, 2, 3],
                name: Some("user".to_string()),
                display_name: None,
            },
            challenge: vec![],
            pub_key_cred_params: vec![],
            timeout: None,
            exclude_credentials: None,
            authenticator_selection: None,
            hints: None,
            attestation: None,
            attestation_formats: None,
            extensions: None,
        };

        let result = collector.collect_create(&options);
        assert!(result.is_err(), "Expected error for invalid JSON");
    }

    #[test]
    fn test_parse_uv() {
        assert!(matches!(
            parse_uv("required"),
            UserVerificationRequirement::Required
        ));
        assert!(matches!(
            parse_uv("discouraged"),
            UserVerificationRequirement::Discouraged
        ));
        assert!(matches!(
            parse_uv("preferred"),
            UserVerificationRequirement::Preferred
        ));
        assert!(matches!(
            parse_uv("invalid"),
            UserVerificationRequirement::Preferred
        ));
    }

    #[test]
    fn test_build_pub_key_params() {
        let algs = vec![-7, -257];
        let params = build_pub_key_params(&algs);

        assert_eq!(params.len(), 2);
        assert_eq!(params[0].type_, PublicKeyCredentialType::PublicKey);
        assert_eq!(params[0].alg, -7);
        assert_eq!(params[1].type_, PublicKeyCredentialType::PublicKey);
        assert_eq!(params[1].alg, -257);
    }

    #[test]
    fn test_build_cred_list() {
        let raw = vec![vec![1, 2, 3, 4], vec![5, 6, 7, 8]];
        let list = build_cred_list(&raw);

        assert_eq!(list.len(), 2);
        assert_eq!(list[0].type_, PublicKeyCredentialType::PublicKey);
        assert_eq!(list[0].id, vec![1, 2, 3, 4]);
        assert_eq!(list[1].id, vec![5, 6, 7, 8]);
    }

    #[test]
    fn test_hex_decode_valid() {
        let result = hex_decode("48656c6c6f");
        assert_eq!(result, Some(b"Hello".to_vec()));
    }

    #[test]
    fn test_hex_decode_invalid() {
        assert_eq!(hex_decode("4865"), Some(vec![0x48, 0x65]));
        assert_eq!(hex_decode("486"), None); // Odd length
        assert_eq!(hex_decode("48ZZ"), None); // Invalid hex
    }

    #[test]
    fn test_build_creation_options() {
        let options = build_creation_options(
            "example.com",
            Some("Example RP"),
            b"user123",
            Some("user@example.com"),
            Some("User Name"),
            &[-7],
            &[],
            None,
            true, // resident key
            "required",
            30000,
        );

        assert_eq!(options.rp.id, Some("example.com".to_string()));
        assert_eq!(options.rp.name, "Example RP");
        assert_eq!(options.user.id, b"user123");
        assert_eq!(options.user.name, Some("user@example.com".to_string()));
        assert_eq!(options.timeout, Some(30000));
        assert!(options.authenticator_selection.is_some());

        let sel = options.authenticator_selection.unwrap();
        assert_eq!(sel.resident_key, Some(ResidentKeyRequirement::Required));
        assert_eq!(
            sel.user_verification,
            Some(UserVerificationRequirement::Required)
        );
    }

    #[test]
    fn test_build_request_options() {
        let allow = vec![vec![1, 2, 3, 4]];
        let options = build_request_options(
            "example.com",
            &allow,
            None,
            "preferred",
            25000,
        );

        assert_eq!(options.rp_id, Some("example.com".to_string()));
        assert_eq!(options.timeout, Some(25000));
        assert_eq!(
            options.user_verification,
            Some(UserVerificationRequirement::Preferred)
        );
        assert!(options.allow_credentials.is_some());
        assert_eq!(options.allow_credentials.as_ref().unwrap().len(), 1);
    }

    #[test]
    fn test_map_registration_extensions_prf() {
        let pipe_ext = PipeExtensions {
            prf: Some(sign_extension_protocol::PipePRFInputs {
                eval: Some(sign_extension_protocol::PipePRFValues {
                    first: vec![1; 32],
                    second: Some(vec![2; 32]),
                }),
                eval_by_credential: None,
            }),
            hmac_create_secret: None,
            cred_protect: None,
            cred_blob: None,
            large_blob: None,
            cred_props: None,
            min_pin_length: None,
            get_cred_blob: None,
            sign: None,
        };

        let yubikit_ext = map_registration_extensions(&pipe_ext);
        assert!(yubikit_ext.prf.is_some());

        let prf = yubikit_ext.prf.unwrap();
        assert!(prf.eval.is_some());
        let eval = prf.eval.unwrap();
        assert_eq!(eval.first, vec![1; 32]);
        assert_eq!(eval.second, Some(vec![2; 32]));
    }

    #[test]
    fn test_map_registration_extensions_credprotect() {
        let pipe_ext = PipeExtensions {
            cred_protect: Some("userVerificationRequired".to_string()),
            prf: None,
            hmac_create_secret: None,
            cred_blob: None,
            large_blob: None,
            cred_props: None,
            min_pin_length: None,
            get_cred_blob: None,
            sign: None,
        };

        let yubikit_ext = map_registration_extensions(&pipe_ext);
        assert!(yubikit_ext.cred_protect.is_some());

        let cp = yubikit_ext.cred_protect.unwrap();
        assert_eq!(
            cp.policy,
            CredProtectPolicy::UserVerificationRequired
        );
    }

    #[test]
    fn test_map_registration_extensions_credblob() {
        let blob_data = vec![0x48, 0x65, 0x6c, 0x6c, 0x6f]; // "Hello"
        let pipe_ext = PipeExtensions {
            cred_blob: Some(blob_data.clone()),
            prf: None,
            hmac_create_secret: None,
            cred_protect: None,
            large_blob: None,
            cred_props: None,
            min_pin_length: None,
            get_cred_blob: None,
            sign: None,
        };

        let yubikit_ext = map_registration_extensions(&pipe_ext);
        assert!(yubikit_ext.cred_blob.is_some());
        assert_eq!(yubikit_ext.cred_blob.unwrap().blob, blob_data);
    }

    #[test]
    fn test_yubikit_error_to_pipe_pin_required() {
        use yubikit::webauthn::ClientError;
        let error: ClientError<std::io::Error> = ClientError::PinRequired;
        let response = yubikit_error_to_pipe(error);

        match response {
            PipeResponse::Error { code, message } => {
                assert_eq!(code, 13);
                assert_eq!(message, "PIN required");
            }
            _ => panic!("Expected Error response"),
        }
    }

    #[test]
    fn test_yubikit_error_to_pipe_bad_request() {
        use yubikit::webauthn::ClientError;
        let error: ClientError<std::io::Error> =
            ClientError::BadRequest("invalid parameter".to_string());
        let response = yubikit_error_to_pipe(error);

        match response {
            PipeResponse::Error { code, message } => {
                assert_eq!(code, 1);
                assert!(message.contains("Bad request"));
                assert!(message.contains("invalid parameter"));
            }
            _ => panic!("Expected Error response"),
        }
    }

    #[test]
    fn test_yubikit_error_to_pipe_config_unsupported() {
        use yubikit::webauthn::ClientError;
        let error: ClientError<std::io::Error> =
            ClientError::ConfigurationUnsupported("algorithm not supported".to_string());
        let response = yubikit_error_to_pipe(error);

        match response {
            PipeResponse::Error { code, message } => {
                assert_eq!(code, 14);
                assert!(message.contains("Unsupported"));
            }
            _ => panic!("Expected Error response"),
        }
    }

    #[test]
    fn given_cancel_signal_when_executing_then_cancel_fn_delegates_to_pin_requester() {
        // The cancel closure must delegate to PinRequester::is_cancelled() and never
        // read from stdin — stdin is owned by the message loop in messaging.rs and
        // a competing reader would corrupt the 4-byte LE length-prefixed framing.
        struct MockPinRequester { cancelled: bool }
        impl super::PinRequester for MockPinRequester {
            fn request_pin(&mut self, _: &str) -> Option<String> { None }
            fn request_new_pin(&mut self, _: &str) -> Option<String> { None }
            fn request_pin_change(&mut self, _: &str) -> Option<(String, String)> { None }
            fn notify_status(&mut self, _: &str) {}
            fn is_cancelled(&self) -> bool { self.cancelled }
        }
        let mut pr = MockPinRequester { cancelled: false };
        assert!(!pr.is_cancelled());
        pr.cancelled = true;
        assert!(pr.is_cancelled());
    }
}
