use std::collections::HashMap;
use std::sync::Arc;

use base64::Engine as _;
use log::{debug, error, info, warn};

use yubikit::ctap::CtapSession;
use yubikit::ctap2::{Ctap2Pin, Ctap2Session, Permissions};
use yubikit::platform::hidapi::{FidoDeviceInfo, HidFidoConnection, list_fido_devices};
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
    cred_blob::{RegistrationInput as CbRegInput},
    sign::{AuthenticationInput as SignAuthInput, RegistrationInput as SignRegInput, GenerateKeyInput, SignInput},
};

use sign_extension_protocol::{
    PipeCredentialProperties, PipeExtensionOutputs, PipeExtensions, PipeLargeBlobOutput,
    PipePRFOutputs, PipePRFValues, PipeRequest, PipeResponse, PipeSignExtensionOutputs,
    PipeSignGeneratedKey,
};

use crate::pipe::ClientContext;
use crate::status_ui::{self, show_status_window, dismiss_status_window};

// ---------------------------------------------------------------------------
// ClientDataCollector — passes through pre-computed clientDataJSON from browser
// ---------------------------------------------------------------------------

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
// UserInteraction — bridges yubikit callbacks to Windows UI
// ---------------------------------------------------------------------------

struct ServiceUserInteraction {
    status_sender: Box<dyn Fn(PipeResponse) + Send>,
    ctx: Arc<ClientContext>,
    rp_id: String,
}

impl UserInteraction for ServiceUserInteraction {
    fn prompt_up(&self) {
        let msg = format_status_msg("Touch your security key", &self.rp_id, &self.ctx.browser_name);
        show_status_window(&msg, self.ctx.browser_hwnd);
        (self.status_sender)(PipeResponse::StatusUpdate {
            status: "presence_required".to_string(),
            retries: None,
        });
    }

    fn request_pin(&self, _permissions: Permissions, _rp_id: Option<&str>) -> Option<Ctap2Pin> {
        dismiss_status_window();
        (self.status_sender)(PipeResponse::StatusUpdate {
            status: "pin_required".to_string(),
            retries: None,
        });

        let raw_pin = crate::pin_ui::prompt_pin(
            None,
            Some(&self.rp_id),
            self.ctx.browser_name.as_deref(),
            self.ctx.browser_hwnd,
        )?;

        Ctap2Pin::new(&raw_pin).ok()
    }

    fn request_uv(&self, _permissions: Permissions, _rp_id: Option<&str>) -> bool {
        let msg = format_status_msg("Scan your fingerprint", &self.rp_id, &self.ctx.browser_name);
        show_status_window(&msg, self.ctx.browser_hwnd);
        (self.status_sender)(PipeResponse::StatusUpdate {
            status: "biometric_required".to_string(),
            retries: None,
        });
        true
    }
}

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

pub fn handle_request(
    request: PipeRequest,
    status_sender: impl Fn(PipeResponse) + Send + 'static,
    ctx: &Arc<ClientContext>,
) -> PipeResponse {
    match request {
        PipeRequest::Cancel => unreachable!("Cancel handled in pipe.rs"),
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
            // Show initial status
            let initial_msg = format_status_msg("Insert your security key", &rp_id, &ctx.browser_name);
            show_status_window(&initial_msg, ctx.browser_hwnd);

            let result = execute_make_credential(
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
                status_sender,
                ctx,
            );

            dismiss_status_window();
            result
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
            // Show initial status
            let initial_msg = format_status_msg("Insert your security key", &rp_id, &ctx.browser_name);
            show_status_window(&initial_msg, ctx.browser_hwnd);

            let result = execute_get_assertion(
                client_data_json,
                rp_id,
                allow_list,
                extensions,
                user_verification,
                timeout_ms,
                status_sender,
                ctx,
            );

            dismiss_status_window();
            result
        }
    }
}

// ---------------------------------------------------------------------------
// Device enumeration with native fallback
// ---------------------------------------------------------------------------

/// Find a FIDO device, falling back to native Windows enumeration if hidapi
/// returns empty (hidapi opens devices with zero access rights during
/// enumeration, which can cause HidD_GetPreparsedData to fail on Windows,
/// leaving usage_page=0 and filtering out the device).
fn find_fido_device() -> Result<FidoDeviceInfo, PipeResponse> {
    match list_fido_devices() {
        Ok(devices) if !devices.is_empty() => {
            let dev = devices.into_iter().next().unwrap();
            debug!("Found FIDO device via hidapi: path={}", dev.path);
            return Ok(dev);
        }
        Ok(_) => {
            warn!("hidapi returned no FIDO devices — trying native Windows enumeration");
        }
        Err(e) => {
            warn!("list_fido_devices failed ({e}) — trying native Windows enumeration");
        }
    }

    #[cfg(windows)]
    {
        let devices = crate::hid_windows::list_fido_devices_native();
        if let Some(dev) = devices.into_iter().next() {
            info!("Found FIDO device via native enumeration: path={}", dev.path);
            return Ok(dev);
        }
    }

    Err(error_response(10, "No FIDO device found"))
}

// ---------------------------------------------------------------------------
// MakeCredential
// ---------------------------------------------------------------------------

#[allow(clippy::too_many_arguments)]
fn execute_make_credential(
    client_data_json: Vec<u8>,
    rp_id: String,
    rp_name: Option<String>,
    user_id: Vec<u8>,
    user_name: Option<String>,
    user_display_name: Option<String>,
    pub_key_params: Vec<i64>,
    exclude_list: Vec<Vec<u8>>,
    extensions: Option<PipeExtensions>,
    resident_key: bool,
    user_verification: String,
    timeout_ms: u64,
    status_sender: impl Fn(PipeResponse) + Send + 'static,
    ctx: &Arc<ClientContext>,
) -> PipeResponse {
    // Connect to device
    let dev = match find_fido_device() {
        Ok(d) => d,
        Err(resp) => return resp,
    };

    let conn = match HidFidoConnection::open(&dev) {
        Ok(c) => c,
        Err(e) => return error_response(2, &format!("HidFidoConnection::open: {e}")),
    };
    let ctap = match CtapSession::new_fido(conn) {
        Ok(s) => s,
        Err((e, _)) => return error_response(3, &format!("CtapSession: {e}")),
    };
    let session = match Ctap2Session::new(ctap) {
        Ok(s) => s,
        Err((e, _)) => return error_response(3, &format!("Ctap2Session: {e}")),
    };

    let collector = PipeClientDataCollector {
        client_data_json,
        rp_id: rp_id.clone(),
    };
    let ui = ServiceUserInteraction {
        status_sender: Box::new(status_sender),
        ctx: ctx.clone(),
        rp_id: rp_id.clone(),
    };
    let mut client = WebAuthnClient::new(session, ui, collector);

    let options = build_creation_options(
        &rp_id,
        rp_name.as_deref(),
        &user_id,
        user_name.as_deref(),
        user_display_name.as_deref(),
        &pub_key_params,
        &exclude_list,
        extensions.as_ref(),
        resident_key,
        &user_verification,
        timeout_ms,
    );

    match client.make_credential(&options, None) {
        Ok(reg) => match pipe_response_from_registration(reg) {
            Ok(resp) => resp,
            Err(e) => error_response(99, &e.to_string()),
        },
        Err(e) => yubikit_error_to_pipe(e),
    }
}

// ---------------------------------------------------------------------------
// GetAssertion
// ---------------------------------------------------------------------------

fn execute_get_assertion(
    client_data_json: Vec<u8>,
    rp_id: String,
    allow_list: Vec<Vec<u8>>,
    extensions: Option<PipeExtensions>,
    user_verification: String,
    timeout_ms: u64,
    status_sender: impl Fn(PipeResponse) + Send + 'static,
    ctx: &Arc<ClientContext>,
) -> PipeResponse {
    // Connect to device
    let dev = match find_fido_device() {
        Ok(d) => d,
        Err(resp) => return resp,
    };

    let conn = match HidFidoConnection::open(&dev) {
        Ok(c) => c,
        Err(e) => return error_response(2, &format!("HidFidoConnection::open: {e}")),
    };
    let ctap = match CtapSession::new_fido(conn) {
        Ok(s) => s,
        Err((e, _)) => return error_response(3, &format!("CtapSession: {e}")),
    };
    let session = match Ctap2Session::new(ctap) {
        Ok(s) => s,
        Err((e, _)) => return error_response(3, &format!("Ctap2Session: {e}")),
    };

    let collector = PipeClientDataCollector {
        client_data_json,
        rp_id: rp_id.clone(),
    };
    let ui = ServiceUserInteraction {
        status_sender: Box::new(status_sender),
        ctx: ctx.clone(),
        rp_id: rp_id.clone(),
    };
    let mut client = WebAuthnClient::new(session, ui, collector);

    let options = build_request_options(
        &rp_id,
        &allow_list,
        extensions.as_ref(),
        &user_verification,
        timeout_ms,
    );

    match client.get_assertion(&options, None) {
        Ok(auths) => {
            if auths.is_empty() {
                return error_response(99, "No credentials found");
            }
            let auth = if auths.len() == 1 {
                auths.into_iter().next().unwrap()
            } else {
                let users: Vec<PublicKeyCredentialUserEntity> = auths.iter().map(|a| {
                    PublicKeyCredentialUserEntity {
                        id: a.response.user_handle.clone().unwrap_or_default(),
                        name: None,
                        display_name: None,
                    }
                }).collect();

                dismiss_status_window();
                match crate::pin_ui::prompt_credential_selection(
                    &users,
                    Some(&rp_id),
                    ctx.browser_name.as_deref(),
                    ctx.browser_hwnd,
                ) {
                    Some(idx) => auths.into_iter().nth(idx).unwrap(),
                    None => return PipeResponse::Error {
                        code: 11,
                        message: "Credential selection cancelled".to_string(),
                    },
                }
            };
            match pipe_response_from_authentication(auth) {
                Ok(resp) => resp,
                Err(e) => error_response(99, &e.to_string()),
            }
        }
        Err(e) => yubikit_error_to_pipe(e),
    }
}

// ---------------------------------------------------------------------------
// Option builders — PipeRequest fields → yubikit WebAuthn option types
// ---------------------------------------------------------------------------

#[allow(clippy::too_many_arguments)]
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

fn format_status_msg(action: &str, rp_id: &str, browser_name: &Option<String>) -> String {
    match browser_name {
        Some(browser) => format!("{action}\n{browser}  \u{2192}  {rp_id}"),
        None => format!("{action}\n{rp_id}"),
    }
}

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
// Extension mapping: PipeExtensions → yubikit extension inputs
// ---------------------------------------------------------------------------

fn map_registration_extensions(ext: &PipeExtensions) -> RegistrationExtensionInputs {
    RegistrationExtensionInputs {
        prf: ext.prf.as_ref().map(|p| PrfRegInput {
            eval: p.eval.as_ref().map(|v| PrfEval {
                first: v.first.clone(),
                second: v.second.clone(),
            }),
        }),
        cred_protect: ext.cred_protect.as_ref().and_then(|s| {
            let policy = match s.as_str() {
                "userVerificationOptional" => Some(CredProtectPolicy::UserVerificationOptional),
                "userVerificationOptionalWithCredentialIDList" =>
                    Some(CredProtectPolicy::UserVerificationOptionalWithCredentialIDList),
                "userVerificationRequired" => Some(CredProtectPolicy::UserVerificationRequired),
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

fn map_authentication_extensions(ext: &PipeExtensions) -> AuthenticationExtensionInputs {
    AuthenticationExtensionInputs {
        prf: ext.prf.as_ref().map(|p| PrfAuthInput {
            eval: p.eval.as_ref().map(|v| PrfEval {
                first: v.first.clone(),
                second: v.second.clone(),
            }),
            eval_by_credential: p.eval_by_credential.as_ref().map(|ebc| {
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
            }).unwrap_or_default(),
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
            s.sign_by_credential.as_ref().map(|sbc| {
                let map: HashMap<String, SignInput> = sbc
                    .iter()
                    .filter_map(|(cred_id_hex, input)| {
                        let cred_id_bytes = hex_decode(cred_id_hex)?;
                        let cred_id_b64 = base64::engine::general_purpose::URL_SAFE_NO_PAD
                            .encode(&cred_id_bytes);
                        Some((
                            cred_id_b64,
                            SignInput {
                                key_handle: input.key_handle.clone(),
                                tbs: input.tbs.clone(),
                                additional_args: input.additional_args.clone(),
                            },
                        ))
                    })
                    .collect();
                SignAuthInput {
                    sign_by_credential: map,
                }
            })
        }),
    }
}

// ---------------------------------------------------------------------------
// Response mapping: yubikit responses → PipeResponse
// ---------------------------------------------------------------------------

fn pipe_response_from_registration(
    reg: yubikit::webauthn::RegistrationResponse,
) -> Result<PipeResponse, anyhow::Error> {
    let ext_out = reg.client_extension_results.as_ref();

    let extension_outputs = ext_out.and_then(|e| {
        let has_any = e.prf.is_some()
            || e.cred_props.is_some()
            || e.cred_blob.is_some()
            || e.large_blob.is_some()
            || e.min_pin_length.is_some();
        if !has_any {
            return None;
        }
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
            cred_blob: e
                .cred_blob
                .as_ref()
                .map(|cb| cb.stored.then_some(true))
                .flatten()
                .map(|_| vec![]),
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
) -> Result<PipeResponse, anyhow::Error> {
    let ext_out = auth.client_extension_results.as_ref();

    let extension_outputs = ext_out.and_then(|e| {
        let has_any = e.prf.is_some() || e.cred_blob.is_some() || e.large_blob.is_some();
        if !has_any {
            return None;
        }
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

fn yubikit_error_to_pipe<E: std::error::Error + Send + Sync + 'static>(
    e: ClientError<E>,
) -> PipeResponse {
    let (code, message) = match &e {
        ClientError::PinRequired => match crate::pin_ui::take_dialog_failure() {
            Some((stage, code)) => (15, format!("Windows PIN prompt unavailable: {stage}, Win32 {code}")),
            None => (13, "PIN required".to_string()),
        },
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

fn error_response(code: u32, message: &str) -> PipeResponse {
    error!("FIDO error (code={code}): {message}");
    PipeResponse::Error {
        code,
        message: message.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_uv() {
        use yubikit::webauthn::types::UserVerificationRequirement;

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
    }

    #[test]
    fn test_build_pub_key_params() {
        use yubikit::webauthn::types::PublicKeyCredentialType;

        let algs = vec![-7, -257];
        let params = build_pub_key_params(&algs);

        assert_eq!(params.len(), 2);
        assert_eq!(params[0].type_, PublicKeyCredentialType::PublicKey);
        assert_eq!(params[0].alg, -7);
    }

    #[test]
    fn test_build_cred_list() {
        use yubikit::webauthn::types::PublicKeyCredentialType;

        let raw = vec![vec![1, 2, 3], vec![4, 5, 6]];
        let list = build_cred_list(&raw);

        assert_eq!(list.len(), 2);
        assert_eq!(list[0].type_, PublicKeyCredentialType::PublicKey);
        assert_eq!(list[0].id, vec![1, 2, 3]);
    }

    #[test]
    fn test_hex_decode() {
        assert_eq!(hex_decode("48656c6c6f"), Some(b"Hello".to_vec()));
        assert_eq!(hex_decode("486"), None); // Odd length
        assert_eq!(hex_decode("GG"), None); // Invalid hex
    }

    #[test]
    fn test_error_response() {
        let response = error_response(10, "Test error");
        match response {
            PipeResponse::Error { code, message } => {
                assert_eq!(code, 10);
                assert_eq!(message, "Test error");
            }
            _ => panic!("Expected Error response"),
        }
    }

    #[test]
    fn test_yubikit_error_to_pipe() {
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
    fn pin_ui_failure_is_distinct_from_cancellation_and_consumed() {
        crate::pin_ui::record_dialog_failure("create-window", 1400);
        let failure: ClientError<std::io::Error> = ClientError::PinRequired;
        match yubikit_error_to_pipe(failure) {
            PipeResponse::Error { code, message } => {
                assert_eq!(code, 15);
                assert_eq!(message, "Windows PIN prompt unavailable: create-window, Win32 1400");
            }
            _ => panic!("Expected UI failure"),
        }
        let cancel: ClientError<std::io::Error> = ClientError::PinRequired;
        assert!(matches!(yubikit_error_to_pipe(cancel), PipeResponse::Error { code: 13, .. }));
    }

    #[test]
    fn test_map_registration_extensions() {
        let pipe_ext = sign_extension_protocol::PipeExtensions {
            prf: Some(sign_extension_protocol::PipePRFInputs {
                eval: Some(sign_extension_protocol::PipePRFValues {
                    first: vec![1; 32],
                    second: None,
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
    }

    #[test]
    fn test_build_creation_options() {
        use yubikit::webauthn::types::ResidentKeyRequirement;

        let options = build_creation_options(
            "example.com",
            Some("Example"),
            b"user123",
            Some("user@example.com"),
            None,
            &[-7],
            &[],
            None,
            true,
            "required",
            30000,
        );

        assert_eq!(options.rp.id, Some("example.com".to_string()));
        assert!(options.authenticator_selection.is_some());
        let sel = options.authenticator_selection.unwrap();
        assert_eq!(sel.resident_key, Some(ResidentKeyRequirement::Required));
    }
}
