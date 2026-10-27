use std::io::{self, Read, Write};
use log::{debug, error, info};
use serde_json::{json, Value};

const MAX_MESSAGE_SIZE: u32 = 1024 * 1024;
const MAX_HEALTH_REQUEST_ID_BYTES: usize = 128;
const INVALID_HEALTH_REQUEST: &str = "Invalid health request";

pub fn read_message(reader: &mut impl Read) -> anyhow::Result<Option<Value>> {
    let mut len_buf = [0u8; 4];
    match reader.read_exact(&mut len_buf) {
        Ok(()) => {}
        Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => return Ok(None),
        Err(e) => return Err(e.into()),
    }
    let len = u32::from_le_bytes(len_buf);
    if len > MAX_MESSAGE_SIZE {
        return Err(anyhow::anyhow!("Message too large: {len} bytes"));
    }
    let mut buf = vec![0u8; len as usize];
    reader.read_exact(&mut buf)?;
    let msg: Value = serde_json::from_slice(&buf)?;
    debug!("Received message: {} bytes", len);
    Ok(Some(msg))
}

pub fn write_message(writer: &mut impl Write, msg: &Value) -> anyhow::Result<()> {
    let data = serde_json::to_vec(msg)?;
    let len = data.len() as u32;
    writer.write_all(&len.to_le_bytes())?;
    writer.write_all(&data)?;
    writer.flush()?;
    debug!("Sent message: {} bytes", len);
    Ok(())
}

pub fn prepare<Backend>(
    reader: &mut impl Read,
    writer: &mut impl Write,
    create_backend: impl FnOnce() -> anyhow::Result<Backend>,
) -> anyhow::Result<Option<(Backend, Value)>> {
    let message = match read_message(reader) {
        Ok(Some(message)) => message,
        Ok(None) => {
            info!("Input stream closed, exiting");
            return Ok(None);
        }
        Err(error) => {
            error!("Failed to read message: {error}");
            return Ok(None);
        }
    };

    if message.get("type").and_then(Value::as_str) == Some("health") {
        let request_id = message
            .get("requestId")
            .and_then(Value::as_str)
            .filter(|request_id| {
                !request_id.is_empty() && request_id.len() <= MAX_HEALTH_REQUEST_ID_BYTES
            });
        let protocol_version = message.get("protocolVersion").and_then(Value::as_u64);
        let response = if request_id.is_none() || protocol_version.is_none() {
            json!({
                "requestId": request_id.unwrap_or(""),
                "error": INVALID_HEALTH_REQUEST
            })
        } else if protocol_version != Some(1) {
            json!({
                "requestId": request_id,
                "error": "Unsupported health protocol version"
            })
        } else {
            json!({
                "requestId": request_id,
                "result": {
                    "version": env!("CARGO_PKG_VERSION"),
                    "protocolVersion": 1,
                    "deviceAccess": false
                }
            })
        };
        if let Err(error) = write_message(writer, &response) {
            error!("Failed to write response: {error}");
        }
        return Ok(None);
    }

    let backend = create_backend()?;
    Ok(Some((backend, message)))
}
