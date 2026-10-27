use std::collections::HashMap;

use anyhow::{anyhow, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use log::{debug, error};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use sign_extension_protocol::{
    PipeExtensions, PipeExtensionOutputs, PipeLargeBlobInput, PipePRFInputs,
    PipePRFValues, PipeRequest, PipeResponse, PipeSignExtension,
    PipeSignExtensionOutputs, PipeSignGenerateKey, PipeSignInput,
};

use crate::backend::{FidoBackend, PinRequester};

#[cfg(test)]
mod previewsign_wire_tests;

// ---------------------------------------------------------------------------
// Entry point: handle a JSON message from the browser extension
// ---------------------------------------------------------------------------

pub fn handle_message(backend: &mut dyn FidoBackend, pin_requester: &mut dyn PinRequester, msg: Value) -> Value {
    let request_id = msg
        .get("requestId")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    match handle_message_inner(backend, pin_requester, &msg) {
        Ok(result) => json!({
            "requestId": request_id,
            "result": result,
        }),
        Err(e) => {
            error!("Request failed: {e}");
            json!({
                "requestId": request_id,
                "error": e.to_string(),
            })
        }
    }
}

fn handle_message_inner(backend: &mut dyn FidoBackend, pin_requester: &mut dyn PinRequester, msg: &Value) -> Result<Value> {
    let action = msg
        .get("type")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow!("Missing 'type' field"))?;
    let origin = msg
        .get("origin")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow!("Missing 'origin' field"))?;
    let options = msg
        .get("options")
        .ok_or_else(|| anyhow!("Missing 'options' field"))?;

    match action {
        "create" => handle_create(backend, pin_requester, origin, options),
        "get" => handle_get(backend, pin_requester, origin, options),
        _ => Err(anyhow!("Unknown action: {action}")),
    }
}

// ---------------------------------------------------------------------------
// MakeCredential
// ---------------------------------------------------------------------------

fn handle_create(backend: &mut dyn FidoBackend, pin_requester: &mut dyn PinRequester, origin: &str, options: &Value) -> Result<Value> {
    let rp = options.get("rp").ok_or_else(|| anyhow!("Missing rp"))?;
    let rp_id = rp
        .get("id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow!("Missing rp.id"))?;
    let rp_name = rp.get("name").and_then(|v| v.as_str()).map(String::from);

    crate::validation::validate_rp_id(rp_id, origin)?;

    let challenge = options
        .get("challenge")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow!("Missing challenge"))?;

    let (client_data_json, client_data_hash) =
        make_client_data("webauthn.create", challenge, origin);

    // Parse user
    let user = options.get("user").ok_or_else(|| anyhow!("Missing user"))?;
    let user_id = decode_b64_field(user, "id")?;
    let user_name = user.get("name").and_then(|v| v.as_str()).map(String::from);
    let user_display_name = user
        .get("displayName")
        .and_then(|v| v.as_str())
        .map(String::from);

    // Parse pubKeyCredParams
    let pub_key_params = options
        .get("pubKeyCredParams")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|p| p.get("alg").and_then(|a| a.as_i64()))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    // Parse excludeCredentials
    let exclude_list = parse_credential_list(options.get("excludeCredentials"));

    // Parse authenticatorSelection
    let auth_sel = options.get("authenticatorSelection");
    let resident_key = auth_sel
        .and_then(|s| s.get("residentKey"))
        .and_then(|v| v.as_str())
        .map(|v| v == "required")
        .unwrap_or(false);
    let user_verification = auth_sel
        .and_then(|s| s.get("userVerification"))
        .and_then(|v| v.as_str())
        .unwrap_or("preferred")
        .to_string();

    // Parse extensions
    let extensions = parse_create_extensions(options.get("extensions"))?;

    let timeout_ms = options
        .get("timeout")
        .and_then(|v| v.as_u64())
        .unwrap_or(60_000);

    debug!(
        "MakeCredential: rp_id={rp_id}, has_sign_ext={}",
        extensions.as_ref().and_then(|e| e.sign.as_ref()).is_some()
    );

    // Build pipe request
    let request = PipeRequest::MakeCredential {
        client_data_hash: client_data_hash.to_vec(),
        client_data_json: client_data_json.clone(),
        rp_id: rp_id.to_string(),
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
    };

    let response = backend.execute(&request, pin_requester)?;

    // Convert response to JSON
    match response {
        PipeResponse::Success {
            attestation_object,
            credential_id,
            sign_extension_outputs,
            extension_outputs,
            ..
        } => {
            let cred_id = credential_id.ok_or_else(|| anyhow!("No credential ID in response"))?;
            let att_obj =
                attestation_object.ok_or_else(|| anyhow!("No attestation object in response"))?;

            let cred_id_b64 = to_b64(&cred_id);
            let mut result = json!({
                "id": cred_id_b64,
                "rawId": cred_id_b64,
                "attestationObject": to_b64(&att_obj),
                "clientDataJSON": to_b64(&client_data_json),
                "authenticatorAttachment": "cross-platform",
                "transports": ["usb"],
            });

            let mut ext_results = if let Some(ext_out) = extension_outputs {
                serialize_extension_outputs(&ext_out)
            } else {
                json!({})
            };
            if let Some(sign_out) = sign_extension_outputs {
                ext_results["previewSign"] = serialize_sign_outputs(&sign_out);
            }
            result["clientExtensionResults"] = ext_results;

            Ok(result)
        }
        PipeResponse::Error { code, message } => {
            Err(anyhow!("FIDO error (code {code}): {message}"))
        }
        PipeResponse::StatusUpdate { .. } => {
            Err(anyhow!("Unexpected StatusUpdate as final response"))
        }
    }
}

// ---------------------------------------------------------------------------
// GetAssertion
// ---------------------------------------------------------------------------

fn handle_get(backend: &mut dyn FidoBackend, pin_requester: &mut dyn PinRequester, origin: &str, options: &Value) -> Result<Value> {
    let rp_id = options
        .get("rpId")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow!("Missing rpId"))?;

    crate::validation::validate_rp_id(rp_id, origin)?;

    let challenge = options
        .get("challenge")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow!("Missing challenge"))?;

    let (client_data_json, client_data_hash) =
        make_client_data("webauthn.get", challenge, origin);

    // Parse allowCredentials
    let allow_list = parse_credential_list(options.get("allowCredentials"));

    let user_verification = options
        .get("userVerification")
        .and_then(|v| v.as_str())
        .unwrap_or("preferred")
        .to_string();

    // Parse extensions
    let extensions = parse_get_extensions(options.get("extensions"))?;

    let timeout_ms = options
        .get("timeout")
        .and_then(|v| v.as_u64())
        .unwrap_or(60_000);

    debug!(
        "GetAssertion: rp_id={rp_id}, has_sign_ext={}",
        extensions.as_ref().and_then(|e| e.sign.as_ref()).is_some()
    );

    // Build pipe request
    let request = PipeRequest::GetAssertion {
        client_data_hash: client_data_hash.to_vec(),
        client_data_json: client_data_json.clone(),
        rp_id: rp_id.to_string(),
        allow_list,
        extensions,
        user_verification,
        timeout_ms,
    };

    let response = backend.execute(&request, pin_requester)?;

    // Convert response to JSON
    match response {
        PipeResponse::Success {
            auth_data,
            signature,
            credential_id,
            user_handle,
            sign_extension_outputs,
            extension_outputs,
            ..
        } => {
            let cred_id = credential_id.ok_or_else(|| anyhow!("No credential ID in response"))?;
            let auth_data_bytes =
                auth_data.ok_or_else(|| anyhow!("No authenticator data in response"))?;
            let sig = signature.ok_or_else(|| anyhow!("No signature in response"))?;

            let cred_id_b64 = to_b64(&cred_id);
            let mut result = json!({
                "id": cred_id_b64,
                "rawId": cred_id_b64,
                "authenticatorData": to_b64(&auth_data_bytes),
                "clientDataJSON": to_b64(&client_data_json),
                "signature": to_b64(&sig),
                "authenticatorAttachment": "cross-platform",
            });

            if let Some(uh) = user_handle {
                result["userHandle"] = json!(to_b64(&uh));
            }

            let mut ext_results = if let Some(ext_out) = extension_outputs {
                serialize_extension_outputs(&ext_out)
            } else {
                json!({})
            };
            if let Some(sign_out) = sign_extension_outputs {
                ext_results["previewSign"] = serialize_sign_outputs(&sign_out);
            }
            result["clientExtensionResults"] = ext_results;

            Ok(result)
        }
        PipeResponse::Error { code, message } => {
            Err(anyhow!("FIDO error (code {code}): {message}"))
        }
        PipeResponse::StatusUpdate { .. } => {
            Err(anyhow!("Unexpected StatusUpdate as final response"))
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn make_client_data(type_: &str, challenge: &str, origin: &str) -> (Vec<u8>, [u8; 32]) {
    let json = json!({
        "type": type_,
        "challenge": challenge,
        "origin": origin,
        "crossOrigin": false,
    });
    let bytes = serde_json::to_vec(&json).unwrap();
    let hash: [u8; 32] = Sha256::digest(&bytes).into();
    (bytes, hash)
}

fn to_b64(data: &[u8]) -> String {
    URL_SAFE_NO_PAD.encode(data)
}

/// Decode a base64url value from a JSON field.
/// Handles both plain strings and `{"__b64": "..."}` objects (from page.js serialization).
fn decode_b64(val: &Value) -> Result<Vec<u8>> {
    if let Some(obj) = val.as_object() {
        if let Some(b64) = obj.get("__b64").and_then(|v| v.as_str()) {
            return URL_SAFE_NO_PAD
                .decode(b64)
                .map_err(|e| anyhow!("base64 decode: {e}"));
        }
    }
    if let Some(s) = val.as_str() {
        return URL_SAFE_NO_PAD
            .decode(s)
            .map_err(|e| anyhow!("base64 decode: {e}"));
    }
    Err(anyhow!("Expected base64url string or {{__b64: ...}} object"))
}

fn decode_b64_field(obj: &Value, field: &str) -> Result<Vec<u8>> {
    let val = obj
        .get(field)
        .ok_or_else(|| anyhow!("Missing field '{field}'"))?;
    decode_b64(val)
}

/// Parse credential descriptor list from `excludeCredentials` or `allowCredentials`.
fn parse_credential_list(list: Option<&Value>) -> Vec<Vec<u8>> {
    list.and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|c| c.get("id").and_then(|id| decode_b64(id).ok()))
                .collect()
        })
        .unwrap_or_default()
}

/// Parse extensions for MakeCredential.
fn parse_create_extensions(ext: Option<&Value>) -> Result<Option<PipeExtensions>> {
    let ext = match ext {
        Some(e) => e,
        None => return Ok(None),
    };

    let sign = ext.get("previewSign").map(|preview_sign| {
        let generate_key = preview_sign.get("generateKey").map(|gk| {
            let algorithms = gk
                .get("algorithms")
                .and_then(|a| a.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_i64().map(|n| n as i32))
                        .collect()
                })
                .unwrap_or_default();
            PipeSignGenerateKey { algorithms }
        });
        PipeSignExtension {
            generate_key,
            sign_by_credential: None,
        }
    });

    let hmac_create_secret = ext.get("hmacCreateSecret").and_then(|v| v.as_bool());
    let cred_props = ext.get("credProps").and_then(|v| v.as_bool());
    let min_pin_length = ext.get("minPinLength").and_then(|v| v.as_bool());
    let cred_protect = ext.get("credentialProtectionPolicy").and_then(|v| v.as_str()).map(String::from);
    let prf = parse_prf_inputs(ext.get("prf"));
    let large_blob = parse_large_blob_input(ext.get("largeBlob"));
    let cred_blob = ext.get("credBlob").map(|v| decode_b64(v)).transpose()?;

    if sign.is_none() && hmac_create_secret.is_none() && cred_props.is_none()
        && min_pin_length.is_none() && cred_protect.is_none() && prf.is_none()
        && large_blob.is_none() && cred_blob.is_none()
    {
        return Ok(None);
    }

    Ok(Some(PipeExtensions {
        sign,
        hmac_create_secret,
        prf,
        cred_props,
        min_pin_length,
        cred_protect,
        large_blob,
        cred_blob,
        get_cred_blob: None,
    }))
}

/// Parse extensions for GetAssertion.
fn parse_get_extensions(ext: Option<&Value>) -> Result<Option<PipeExtensions>> {
    let ext = match ext {
        Some(e) => e,
        None => return Ok(None),
    };

    let sign = ext.get("previewSign").map(|preview_sign| {
        let sign_by_credential = preview_sign
            .get("signByCredential")
            .and_then(|sbc| sbc.as_object())
            .map(|obj| {
                let mut map = HashMap::new();
                for (cred_id_b64, vals) in obj {
                    let key_handle = vals
                        .get("keyHandle")
                        .and_then(|v| decode_b64(v).ok())
                        .unwrap_or_default();
                    let tbs = vals
                        .get("tbs")
                        .and_then(|v| decode_b64(v).ok())
                        .unwrap_or_default();
                    let additional_args = vals
                        .get("additionalArgs")
                        .and_then(|v| decode_b64(v).ok());

                    let cred_id_bytes = URL_SAFE_NO_PAD.decode(cred_id_b64).unwrap_or_default();
                    let cred_id_hex = hex_encode(&cred_id_bytes);

                    map.insert(
                        cred_id_hex,
                        PipeSignInput {
                            key_handle,
                            tbs,
                            additional_args,
                        },
                    );
                }
                map
            });
        PipeSignExtension {
            generate_key: None,
            sign_by_credential,
        }
    });

    let prf = parse_prf_inputs(ext.get("prf"));
    let large_blob = parse_large_blob_input(ext.get("largeBlob"));
    let get_cred_blob = ext.get("getCredBlob").and_then(|v| v.as_bool())
        .or_else(|| ext.get("credBlob").and_then(|v| v.as_bool()));

    if sign.is_none() && prf.is_none() && large_blob.is_none() && get_cred_blob.is_none() {
        return Ok(None);
    }

    Ok(Some(PipeExtensions {
        sign,
        hmac_create_secret: None,
        prf,
        cred_props: None,
        min_pin_length: None,
        cred_protect: None,
        large_blob,
        cred_blob: None,
        get_cred_blob,
    }))
}

fn parse_prf_inputs(prf: Option<&Value>) -> Option<PipePRFInputs> {
    let prf = prf?;
    let eval = prf.get("eval").and_then(|e| {
        let first = e.get("first").and_then(|v| decode_b64(v).ok())?;
        let second = e.get("second").and_then(|v| decode_b64(v).ok());
        Some(PipePRFValues { first, second })
    });
    let eval_by_credential = prf.get("evalByCredential").and_then(|ebc| {
        let obj = ebc.as_object()?;
        let mut map = HashMap::new();
        for (cred_id_b64, vals) in obj {
            let first = match vals.get("first").and_then(|v| decode_b64(v).ok()) {
                Some(f) => f,
                None => continue,
            };
            let second = vals.get("second").and_then(|v| decode_b64(v).ok());
            map.insert(cred_id_b64.clone(), PipePRFValues { first, second });
        }
        Some(map)
    });
    // Return Some even if eval/eval_by_credential are both None —
    // prf: {} means "query PRF support" during MakeCredential.
    Some(PipePRFInputs { eval, eval_by_credential })
}

/// Parse largeBlob extension input.
///
/// Registration: `{ support: "required"|"preferred" }`
/// Authentication: `{ read: true }` or `{ write: <base64url bytes> }`
fn parse_large_blob_input(lb: Option<&Value>) -> Option<PipeLargeBlobInput> {
    let lb = lb?;
    let support = lb.get("support").and_then(|v| v.as_str()).map(String::from);
    let read = lb.get("read").and_then(|v| v.as_bool());
    let write = lb.get("write").and_then(|v| decode_b64(v).ok());

    if support.is_none() && read.is_none() && write.is_none() {
        return None;
    }
    Some(PipeLargeBlobInput { support, read, write })
}

fn hex_encode(data: &[u8]) -> String {
    data.iter().map(|b| format!("{b:02x}")).collect()
}

fn serialize_sign_outputs(out: &PipeSignExtensionOutputs) -> Value {
    let mut result = json!({});

    if let Some(gk) = &out.generated_key {
        result["generatedKey"] = json!({
            "keyHandle": { "__b64": to_b64(&gk.key_handle) },
            "publicKey": { "__b64": to_b64(&gk.public_key) },
            "algorithm": gk.algorithm,
            "attestationObject": { "__b64": to_b64(&gk.attestation_object) },
        });
    }

    if let Some(sig) = &out.signature {
        result["signature"] = json!({ "__b64": to_b64(sig) });
    }

    result
}

fn serialize_extension_outputs(ext_out: &PipeExtensionOutputs) -> Value {
    let mut result = json!({});

    if let Some(hmac) = ext_out.hmac_create_secret {
        result["hmacCreateSecret"] = json!(hmac);
    }

    if let Some(cp) = &ext_out.cred_props {
        result["credProps"] = json!({ "rk": cp.rk });
    }

    if let Some(prf) = &ext_out.prf {
        let mut prf_out = json!({});
        if let Some(enabled) = prf.enabled {
            prf_out["enabled"] = json!(enabled);
        }
        if let Some(results) = &prf.results {
            let mut res = json!({
                "first": { "__b64": to_b64(&results.first) },
            });
            if let Some(second) = &results.second {
                res["second"] = json!({ "__b64": to_b64(second) });
            }
            prf_out["results"] = res;
        }
        result["prf"] = prf_out;
    }

    if let Some(lb) = &ext_out.large_blob {
        let mut lb_out = json!({});
        if let Some(supported) = lb.supported {
            lb_out["supported"] = json!(supported);
        }
        if let Some(ref blob) = lb.blob {
            lb_out["blob"] = json!({ "__b64": to_b64(blob) });
        }
        if let Some(written) = lb.written {
            lb_out["written"] = json!(written);
        }
        result["largeBlob"] = lb_out;
    }

    if let Some(true) = ext_out.cred_blob_set {
        result["credBlob"] = json!(true);
    } else if let Some(ref blob) = ext_out.cred_blob {
        result["credBlob"] = json!({ "__b64": to_b64(blob) });
    }

    result
}
