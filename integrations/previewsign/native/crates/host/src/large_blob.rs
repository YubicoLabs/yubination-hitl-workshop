//! Large-blob array crypto: AES-256-GCM encryption/decryption and DEFLATE
//! compression for per-credential large-blob entries.
//!
//! Wire format (per CTAP2.1 §11.4.2):
//!   - Serialized large-blob array = CBOR array of large-blob maps + LEFT(SHA-256, 16)
//!   - Each large-blob map = { 1: ciphertext, 2: nonce (12 bytes), 3: origSize }
//!   - Encryption: AES-256-GCM(key = largeBlobKey, nonce, AD = "blob" || LE64(origSize),
//!                              plaintext = DEFLATE(data))
//!   - Trial decryption: iterate entries, try decrypting with the credential's largeBlobKey

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use flate2::read::DeflateDecoder;
use flate2::write::DeflateEncoder;
use flate2::Compression;
use log::{debug, warn};
use rand::RngCore;
use serde_cbor::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::io::{Read, Write};

/// The initial (empty) serialized large-blob array.
/// = CBOR empty array (0x80) + LEFT(SHA-256(0x80), 16)
pub const INITIAL_LARGE_BLOB_ARRAY: [u8; 17] = [
    0x80, // empty CBOR array
    0x76, 0xbe, 0x8b, 0x52, 0x8d, 0x00, 0x75, 0xf7, 0xaa, 0xe9, 0x8d, 0x6f, 0xa5, 0x7a, 0x6d,
    0x3c, // LEFT(SHA-256(h'80'), 16)
];

/// A single entry in the large-blob array.
#[derive(Debug, Clone)]
pub struct LargeBlobEntry {
    pub ciphertext: Vec<u8>, // CBOR key 1
    pub nonce: Vec<u8>,      // CBOR key 2 (12 bytes)
    pub orig_size: u64,      // CBOR key 3
}

/// Parse the serialized large-blob array into individual entries.
///
/// Validates the trailing 16-byte SHA-256 hash, then decodes the CBOR array.
/// Returns the entries and the raw CBOR portion (without hash) for later re-serialization.
pub fn parse_large_blob_array(serialized: &[u8]) -> Result<Vec<LargeBlobEntry>, String> {
    if serialized.len() < 17 {
        return Err("Serialized large-blob array too short".into());
    }

    let (cbor_part, hash_part) = serialized.split_at(serialized.len() - 16);

    // Verify hash
    let computed = Sha256::digest(cbor_part);
    if &computed[..16] != hash_part {
        return Err("Large-blob array hash mismatch".into());
    }

    // Decode CBOR array
    let value: Value = serde_cbor::from_slice(cbor_part)
        .map_err(|e| format!("CBOR decode error: {e}"))?;

    let array = match value {
        Value::Array(arr) => arr,
        _ => return Err("Large-blob array is not a CBOR array".into()),
    };

    let mut entries = Vec::new();
    for item in array {
        if let Value::Map(map) = item {
            let mut ciphertext = None;
            let mut nonce = None;
            let mut orig_size = None;

            for (k, v) in map {
                match k {
                    Value::Integer(1) => {
                        if let Value::Bytes(b) = v {
                            ciphertext = Some(b);
                        }
                    }
                    Value::Integer(2) => {
                        if let Value::Bytes(b) = v {
                            nonce = Some(b);
                        }
                    }
                    Value::Integer(3) => {
                        if let Value::Integer(n) = v {
                            orig_size = Some(n as u64);
                        }
                    }
                    _ => {} // ignore unknown keys
                }
            }

            if let (Some(ct), Some(n), Some(os)) = (ciphertext, nonce, orig_size) {
                entries.push(LargeBlobEntry {
                    ciphertext: ct,
                    nonce: n,
                    orig_size: os,
                });
            } else {
                warn!("Skipping malformed large-blob entry");
            }
        }
    }

    Ok(entries)
}

/// Serialize entries back into a serialized large-blob array.
///
/// Returns CBOR array + 16-byte truncated SHA-256 hash.
pub fn serialize_large_blob_array(entries: &[LargeBlobEntry]) -> Vec<u8> {
    let array: Vec<Value> = entries
        .iter()
        .map(|e| {
            let mut map = BTreeMap::new();
            map.insert(Value::Integer(1), Value::Bytes(e.ciphertext.clone()));
            map.insert(Value::Integer(2), Value::Bytes(e.nonce.clone()));
            map.insert(Value::Integer(3), Value::Integer(e.orig_size as i128));
            Value::Map(map)
        })
        .collect();

    let cbor = serde_cbor::to_vec(&Value::Array(array))
        .expect("CBOR serialization should not fail");

    let hash = Sha256::digest(&cbor);
    let mut result = cbor;
    result.extend_from_slice(&hash[..16]);
    result
}

/// Try to decrypt a large-blob entry using the given largeBlobKey.
///
/// Returns the decompressed plaintext on success, or None if decryption fails
/// (meaning this entry doesn't belong to this credential — trial decryption).
pub fn decrypt_entry(entry: &LargeBlobEntry, large_blob_key: &[u8]) -> Option<Vec<u8>> {
    if large_blob_key.len() != 32 {
        warn!("largeBlobKey must be 32 bytes, got {}", large_blob_key.len());
        return None;
    }
    if entry.nonce.len() != 12 {
        warn!("nonce must be 12 bytes, got {}", entry.nonce.len());
        return None;
    }

    let cipher = Aes256Gcm::new_from_slice(large_blob_key).ok()?;
    let nonce = Nonce::from_slice(&entry.nonce);

    // AD = "blob" || LE64(origSize)
    let mut ad = b"blob".to_vec();
    ad.extend_from_slice(&entry.orig_size.to_le_bytes());

    let payload = Payload {
        msg: &entry.ciphertext,
        aad: &ad,
    };

    let compressed = match cipher.decrypt(nonce, payload) {
        Ok(data) => data,
        Err(_) => return None, // trial decryption failed — not our entry
    };

    // DEFLATE decompress
    let mut decoder = DeflateDecoder::new(&compressed[..]);
    let mut plaintext = Vec::with_capacity(entry.orig_size as usize);
    match decoder.read_to_end(&mut plaintext) {
        Ok(_) => {
            debug!(
                "Decrypted large-blob entry: {} bytes compressed → {} bytes",
                compressed.len(),
                plaintext.len()
            );
            Some(plaintext)
        }
        Err(e) => {
            warn!("DEFLATE decompression failed: {e}");
            None
        }
    }
}

/// Encrypt data into a large-blob entry for the given largeBlobKey.
///
/// Compresses with DEFLATE, encrypts with AES-256-GCM, returns the entry
/// ready to be inserted into the large-blob array.
pub fn encrypt_entry(data: &[u8], large_blob_key: &[u8]) -> Result<LargeBlobEntry, String> {
    if large_blob_key.len() != 32 {
        return Err(format!("largeBlobKey must be 32 bytes, got {}", large_blob_key.len()));
    }

    // DEFLATE compress
    let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default());
    encoder
        .write_all(data)
        .map_err(|e| format!("DEFLATE compression failed: {e}"))?;
    let compressed = encoder
        .finish()
        .map_err(|e| format!("DEFLATE finish failed: {e}"))?;

    let orig_size = data.len() as u64;

    // Random 12-byte nonce
    let mut nonce_bytes = [0u8; 12];
    rand::thread_rng().fill_bytes(&mut nonce_bytes);

    let cipher = Aes256Gcm::new_from_slice(large_blob_key)
        .map_err(|e| format!("AES-GCM init failed: {e}"))?;
    let nonce = Nonce::from_slice(&nonce_bytes);

    // AD = "blob" || LE64(origSize)
    let mut ad = b"blob".to_vec();
    ad.extend_from_slice(&orig_size.to_le_bytes());

    let payload = Payload {
        msg: &compressed,
        aad: &ad,
    };

    let ciphertext = cipher
        .encrypt(nonce, payload)
        .map_err(|e| format!("AES-GCM encrypt failed: {e}"))?;

    Ok(LargeBlobEntry {
        ciphertext,
        nonce: nonce_bytes.to_vec(),
        orig_size,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initial_array() {
        let entries = parse_large_blob_array(&INITIAL_LARGE_BLOB_ARRAY).unwrap();
        assert_eq!(entries.len(), 0);
    }

    #[test]
    fn test_roundtrip_serialize() {
        let entries = vec![];
        let serialized = serialize_large_blob_array(&entries);
        assert_eq!(serialized, INITIAL_LARGE_BLOB_ARRAY);
    }

    #[test]
    fn test_encrypt_decrypt_roundtrip() {
        let key = [0x42u8; 32]; // test key
        let data = b"hello, large blob!";

        let entry = encrypt_entry(data, &key).unwrap();
        assert_eq!(entry.orig_size, data.len() as u64);
        assert_eq!(entry.nonce.len(), 12);

        let decrypted = decrypt_entry(&entry, &key).unwrap();
        assert_eq!(decrypted, data);
    }

    #[test]
    fn test_trial_decrypt_wrong_key() {
        let key1 = [0x42u8; 32];
        let key2 = [0x43u8; 32];
        let data = b"secret data";

        let entry = encrypt_entry(data, &key1).unwrap();
        assert!(decrypt_entry(&entry, &key2).is_none());
    }

    #[test]
    fn test_full_array_roundtrip() {
        let key = [0x42u8; 32];
        let data = b"test blob content";

        let entry = encrypt_entry(data, &key).unwrap();
        let serialized = serialize_large_blob_array(&[entry.clone()]);

        let parsed = parse_large_blob_array(&serialized).unwrap();
        assert_eq!(parsed.len(), 1);

        let decrypted = decrypt_entry(&parsed[0], &key).unwrap();
        assert_eq!(decrypted, data);
    }
}
