use super::handle_message;
use crate::backend::{FidoBackend, PinRequester};
use anyhow::Result;
use serde_json::{json, Value};
use sign_extension_protocol::{
    PipeRequest, PipeResponse, PipeSignExtensionOutputs, PipeSignGeneratedKey,
};

fn fixture_bytes(fixture: &Value, field: &str) -> Vec<u8> {
    serde_json::from_value(fixture[field].clone()).unwrap()
}

fn fixture_hex(fixture: &Value, field: &str) -> Vec<u8> {
    fixture[field]
        .as_str()
        .unwrap()
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

struct NoPin;

impl PinRequester for NoPin {
    fn request_pin(&mut self, _: &str) -> Option<String> {
        panic!("Synthetic boundary test must not request a PIN")
    }

    fn request_new_pin(&mut self, _: &str) -> Option<String> {
        panic!("Synthetic boundary test must not set a PIN")
    }

    fn request_pin_change(&mut self, _: &str) -> Option<(String, String)> {
        panic!("Synthetic boundary test must not change a PIN")
    }

    fn notify_status(&mut self, _: &str) {
        panic!("Synthetic boundary test must not notify hardware status")
    }
}

struct SyntheticBackend {
    fixture: Value,
    action: &'static str,
    calls: usize,
}

impl FidoBackend for SyntheticBackend {
    fn execute(
        &mut self,
        request: &PipeRequest,
        _: &mut dyn PinRequester,
    ) -> Result<PipeResponse> {
        self.calls += 1;
        let fixture = &self.fixture;
        let generated_key = match request {
            PipeRequest::MakeCredential {
                rp_id,
                user_id,
                pub_key_params,
                exclude_list,
                extensions,
                ..
            } => {
                assert_eq!(self.action, "create");
                assert_eq!(rp_id, "previewsign.test");
                assert_eq!(user_id, &fixture_bytes(fixture, "seedHandleBytes"));
                assert_eq!(pub_key_params, &vec![-7]);
                assert_eq!(exclude_list, &vec![fixture_bytes(fixture, "credentialBytes")]);
                let sign = extensions.as_ref().unwrap().sign.as_ref().unwrap();
                assert_eq!(sign.generate_key.as_ref().unwrap().algorithms, vec![-65539]);
                assert!(sign.sign_by_credential.is_none());
                Some(PipeSignGeneratedKey {
                    key_handle: fixture_bytes(fixture, "seedHandleBytes"),
                    public_key: fixture_bytes(fixture, "dummyPublicKeyBytes"),
                    algorithm: -65539,
                    attestation_object: fixture_bytes(fixture, "dummyAttestationBytes"),
                })
            }
            PipeRequest::GetAssertion {
                rp_id,
                allow_list,
                extensions,
                ..
            } => {
                assert_eq!(self.action, "get");
                assert_eq!(rp_id, "previewsign.test");
                assert_eq!(allow_list, &vec![fixture_bytes(fixture, "credentialBytes")]);
                let sign = extensions.as_ref().unwrap().sign.as_ref().unwrap();
                assert!(sign.generate_key.is_none());
                let inputs = sign.sign_by_credential.as_ref().unwrap();
                assert_eq!(inputs.len(), 1);
                let input = inputs.get("fbff0001").unwrap();
                assert_eq!(input.key_handle, fixture_bytes(fixture, "seedHandleBytes"));
                assert_eq!(input.tbs, fixture_bytes(fixture, "tbsBytes"));
                assert_eq!(
                    input.additional_args,
                    Some(fixture_hex(fixture, "additionalArgsHex"))
                );
                None
            }
            other => panic!("Unexpected synthetic backend request: {other:?}"),
        };
        Ok(PipeResponse::Success {
            attestation_object: Some(fixture_bytes(fixture, "dummyAttestationBytes")),
            auth_data: Some(vec![0]),
            signature: Some(fixture_bytes(fixture, "dummySignatureBytes")),
            credential_id: Some(fixture_bytes(fixture, "credentialBytes")),
            user_handle: None,
            client_data_json: None,
            sign_extension_outputs: Some(PipeSignExtensionOutputs {
                generated_key,
                signature: if self.action == "get" {
                    Some(fixture_bytes(fixture, "dummySignatureBytes"))
                } else {
                    None
                },
            }),
            extension_outputs: None,
        })
    }
}

#[test]
fn previewsign_public_handle_message_synthetic_wire() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../../../scripts/fixtures/previewsign-wire.json"
    ))
    .unwrap();
    for action in ["create", "get"] {
        let options = if action == "create" {
            json!({
                "rp": {"id": "previewsign.test", "name": "Synthetic transport"},
                "user": {"id": fixture["seedHandleBase64url"], "name": "fixture"},
                "challenge": fixture["tbsBase64url"],
                "pubKeyCredParams": [{"type": "public-key", "alg": -7}],
                "excludeCredentials": [{"type": "public-key", "id": fixture["credentialBase64url"]}],
                "extensions": {"previewSign": {"generateKey": {"algorithms": [-65539]}}}
            })
        } else {
            let credential_id = fixture["credentialBase64url"].as_str().unwrap();
            json!({
                "rpId": "previewsign.test",
                "challenge": fixture["seedHandleBase64url"],
                "allowCredentials": [{"type": "public-key", "id": credential_id}],
                "extensions": {"previewSign": {"signByCredential": {
                    (credential_id): {
                        "keyHandle": {"__b64": fixture["seedHandleBase64url"]},
                        "tbs": {"__b64": fixture["tbsBase64url"]},
                        "additionalArgs": {"__b64": fixture["additionalArgsBase64url"]}
                    }
                }}}
            })
        };
        let mut backend = SyntheticBackend {
            fixture: fixture.clone(),
            action,
            calls: 0,
        };
        let output = handle_message(
            &mut backend,
            &mut NoPin,
            json!({
                "type": action,
                "requestId": "ps3-synthetic",
                "origin": "https://previewsign.test",
                "options": options
            }),
        );
        assert_eq!(backend.calls, 1);
        assert_eq!(output["requestId"], "ps3-synthetic");
        assert!(output.get("error").is_none(), "{output}");
        let result = &output["result"];
        assert_eq!(result["id"], fixture["credentialBase64url"]);
        assert_eq!(result["rawId"], fixture["credentialBase64url"]);
        let expected_extension = if action == "create" {
            assert_eq!(result["attestationObject"], fixture["dummyAttestationBase64url"]);
            json!({"generatedKey": {
                "keyHandle": {"__b64": fixture["seedHandleBase64url"]},
                "publicKey": {"__b64": fixture["dummyPublicKeyBase64url"]},
                "algorithm": -65539,
                "attestationObject": {"__b64": fixture["dummyAttestationBase64url"]}
            }})
        } else {
            assert_eq!(result["signature"], fixture["dummySignatureBase64url"]);
            json!({"signature": {"__b64": fixture["dummySignatureBase64url"]}})
        };
        assert_eq!(result["clientExtensionResults"]["previewSign"], expected_extension);
    }
}
