//! Shared pipe protocol types for the previewSign FIDO bridge.
//!
//! Both the Windows service (pipe server) and native messaging host (pipe client)
//! use these types for CBOR-encoded communication over `\\.\pipe\sign-extension-fido`.
//!
//! Wire format: `[4 bytes: big-endian u32 length][length bytes: CBOR payload]`

use std::collections::HashMap;
use std::io::{Read, Write};

use serde::{Deserialize, Serialize};

pub const PIPE_NAME: &str = r"\\.\pipe\yubico-previewsign-workshop";
pub const SERVICE_NAME: &str = "YubicoPreviewSignWorkshop";
pub const MAX_FRAME_SIZE: usize = 4 * 1024 * 1024; // 4 MiB

// ---------------------------------------------------------------------------
// Request types (host → service)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum PipeRequest {
    MakeCredential {
        client_data_hash: Vec<u8>,
        /// Raw clientDataJSON bytes for webauthn.dll (which hashes them itself).
        #[serde(default)]
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
    },
    GetAssertion {
        client_data_hash: Vec<u8>,
        #[serde(default)]
        client_data_json: Vec<u8>,
        rp_id: String,
        allow_list: Vec<Vec<u8>>,
        extensions: Option<PipeExtensions>,
        user_verification: String,
        timeout_ms: u64,
    },
    Cancel,
}

// ---------------------------------------------------------------------------
// Extension types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipeExtensions {
    pub sign: Option<PipeSignExtension>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hmac_create_secret: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prf: Option<PipePRFInputs>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cred_props: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub min_pin_length: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cred_protect: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub large_blob: Option<PipeLargeBlobInput>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cred_blob: Option<Vec<u8>>,
    /// For GetAssertion: true means "retrieve the stored blob"
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub get_cred_blob: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipePRFInputs {
    pub eval: Option<PipePRFValues>,
    pub eval_by_credential: Option<HashMap<String, PipePRFValues>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipePRFValues {
    pub first: Vec<u8>,
    pub second: Option<Vec<u8>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipeSignExtension {
    pub generate_key: Option<PipeSignGenerateKey>,
    pub sign_by_credential: Option<HashMap<String, PipeSignInput>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipeSignGenerateKey {
    pub algorithms: Vec<i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipeSignInput {
    pub key_handle: Vec<u8>,
    pub tbs: Vec<u8>,
    pub additional_args: Option<Vec<u8>>,
}

/// Large blob extension inputs.
///
/// For registration (MakeCredential):
///   `support` = "required" | "preferred"
///
/// For authentication (GetAssertion):
///   `read` = true  →  read the blob for the asserted credential
///   `write` = <bytes>  →  write a blob for the asserted credential
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipeLargeBlobInput {
    /// Registration: "required" or "preferred"
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub support: Option<String>,
    /// Authentication: request to read the large blob
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub read: Option<bool>,
    /// Authentication: data to write as the large blob
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub write: Option<Vec<u8>>,
}

/// Large blob extension outputs.
#[derive(Debug, Serialize, Deserialize)]
pub struct PipeLargeBlobOutput {
    /// Registration: whether the authenticator supports large blobs
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub supported: Option<bool>,
    /// Authentication (read): the decrypted blob data
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub blob: Option<Vec<u8>>,
    /// Authentication (write): whether the write succeeded
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub written: Option<bool>,
}

// ---------------------------------------------------------------------------
// Response types (service → host)
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum PipeResponse {
    Success {
        #[serde(skip_serializing_if = "Option::is_none")]
        attestation_object: Option<Vec<u8>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        auth_data: Option<Vec<u8>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        signature: Option<Vec<u8>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        credential_id: Option<Vec<u8>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        user_handle: Option<Vec<u8>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        client_data_json: Option<Vec<u8>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        sign_extension_outputs: Option<PipeSignExtensionOutputs>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        extension_outputs: Option<PipeExtensionOutputs>,
    },
    Error {
        code: u32,
        message: String,
    },
    StatusUpdate {
        status: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        retries: Option<u8>,
    },
}

// ---------------------------------------------------------------------------
// General extension output types
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize)]
pub struct PipeExtensionOutputs {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hmac_create_secret: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cred_props: Option<PipeCredentialProperties>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prf: Option<PipePRFOutputs>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub large_blob: Option<PipeLargeBlobOutput>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cred_blob: Option<Vec<u8>>,
    /// true if credBlob was stored successfully at MakeCredential
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cred_blob_set: Option<bool>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PipeCredentialProperties {
    pub rk: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PipePRFOutputs {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub enabled: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub results: Option<PipePRFValues>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PipeSignExtensionOutputs {
    pub generated_key: Option<PipeSignGeneratedKey>,
    pub signature: Option<Vec<u8>>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PipeSignGeneratedKey {
    pub key_handle: Vec<u8>,
    pub public_key: Vec<u8>,
    pub algorithm: i64,
    pub attestation_object: Vec<u8>,
}

// ---------------------------------------------------------------------------
// Frame I/O
// ---------------------------------------------------------------------------

pub fn read_frame(reader: &mut impl Read) -> anyhow::Result<Vec<u8>> {
    let mut len_buf = [0u8; 4];
    reader.read_exact(&mut len_buf)?;
    let len = u32::from_be_bytes(len_buf) as usize;
    if len > MAX_FRAME_SIZE {
        return Err(anyhow::anyhow!("Frame too large: {len}"));
    }
    let mut buf = vec![0u8; len];
    reader.read_exact(&mut buf)?;
    Ok(buf)
}

pub fn write_frame(writer: &mut impl Write, data: &[u8]) -> anyhow::Result<()> {
    writer.write_all(&(data.len() as u32).to_be_bytes())?;
    writer.write_all(data)?;
    writer.flush()?;
    Ok(())
}

pub fn read_response(reader: &mut impl Read) -> anyhow::Result<PipeResponse> {
    let frame = read_frame(reader)?;
    let response: PipeResponse = serde_cbor::from_slice(&frame)?;
    Ok(response)
}

pub fn write_request(writer: &mut impl Write, request: &PipeRequest) -> anyhow::Result<()> {
    let data = serde_cbor::to_vec(request)?;
    write_frame(writer, &data)
}

pub fn write_response(writer: &mut impl Write, response: &PipeResponse) -> anyhow::Result<()> {
    let data = serde_cbor::to_vec(response)?;
    write_frame(writer, &data)
}

pub fn read_request(reader: &mut impl Read) -> anyhow::Result<PipeRequest> {
    let frame = read_frame(reader)?;
    let request: PipeRequest = serde_cbor::from_slice(&frame)?;
    Ok(request)
}
