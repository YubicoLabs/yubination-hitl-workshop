#[path = "../src/startup.rs"]
mod startup;

use std::cell::Cell;
use std::io::{self, Cursor, Write};

use serde_json::{json, Value};

#[test]
fn health_exits_without_backend() {
    let request = br#"{"type":"health","requestId":"check-1","protocolVersion":1}"#;
    let mut framed_request = Vec::new();
    framed_request.extend_from_slice(&(request.len() as u32).to_le_bytes());
    framed_request.extend_from_slice(request);
    let mut input = Cursor::new(framed_request);
    let mut output = Vec::new();

    let ordinary = startup::prepare(&mut input, &mut output, || -> anyhow::Result<()> {
        panic!("health must not initialize backend")
    })
    .expect("health must succeed");

    assert!(ordinary.is_none(), "health must exit before ordinary dispatch");
    assert!(output.len() >= 4, "health must produce a framed response");
    let length = u32::from_le_bytes(output[..4].try_into().unwrap()) as usize;
    assert_eq!(output.len(), 4 + length, "exactly one response frame");
    let response: Value = serde_json::from_slice(&output[4..]).unwrap();
    assert_eq!(
        response,
        json!({
            "requestId": "check-1",
            "result": {
                "version": env!("CARGO_PKG_VERSION"),
                "protocolVersion": 1,
                "deviceAccess": false
            }
        })
    );
}

fn frame(payload: &[u8]) -> Vec<u8> {
    let mut framed = (payload.len() as u32).to_le_bytes().to_vec();
    framed.extend_from_slice(payload);
    framed
}

fn decode_single_response(output: &[u8]) -> Value {
    assert!(output.len() >= 4, "expected a framed response");
    let length = u32::from_le_bytes(output[..4].try_into().unwrap()) as usize;
    assert_eq!(output.len(), 4 + length, "exactly one response frame");
    serde_json::from_slice(&output[4..]).unwrap()
}

fn health_response(request: Value) -> Value {
    let mut frames = frame(&serde_json::to_vec(&request).unwrap());
    let first_frame_length = frames.len() as u64;
    frames.extend(frame(br#"{"type":"ordinary","requestId":"must-not-dispatch"}"#));
    let mut input = Cursor::new(frames);
    let mut output = Vec::new();
    let ordinary = startup::prepare(&mut input, &mut output, || -> anyhow::Result<()> {
        panic!("health success or error must not initialize backend")
    })
    .unwrap();
    assert!(ordinary.is_none());
    assert_eq!(input.position(), first_frame_length, "health is one-shot");
    assert!(output.len() <= 1024, "health response must remain bounded");
    decode_single_response(&output)
}

#[test]
fn malformed_health_ids_are_not_echoed() {
    let mut requests = vec![json!({"type": "health", "protocolVersion": 1})];
    for request_id in [
        Value::Null,
        json!(42),
        json!(false),
        json!([]),
        json!({}),
        json!(""),
        json!("a".repeat(129)),
        json!("é".repeat(65)),
    ] {
        requests.push(json!({
            "type": "health", "requestId": request_id, "protocolVersion": 1
        }));
    }
    requests.push(json!({"type": "health", "requestId": "", "protocolVersion": 2}));
    for request in requests {
        assert_eq!(
            health_response(request),
            json!({"requestId": "", "error": "Invalid health request"})
        );
    }
}

#[test]
fn malformed_health_protocol_preserves_only_a_valid_id() {
    let mut requests = vec![json!({"type": "health", "requestId": "check-1"})];
    for protocol_version in [
        Value::Null,
        json!("1"),
        json!(true),
        json!(-1),
        json!(1.0),
        json!(1.5),
        json!([]),
        json!({}),
    ] {
        requests.push(json!({
            "type": "health", "requestId": "check-1", "protocolVersion": protocol_version
        }));
    }
    for request in requests {
        assert_eq!(
            health_response(request),
            json!({"requestId": "check-1", "error": "Invalid health request"})
        );
    }
}

#[test]
fn health_accepts_id_byte_boundaries_and_exits_with_a_queued_message() {
    for request_id in ["a".to_string(), "a".repeat(128), "é".repeat(64), "\0".repeat(128)] {
        assert_eq!(
            health_response(json!({
                "type": "health", "requestId": request_id, "protocolVersion": 1
            })),
            json!({
                "requestId": request_id,
                "result": {
                    "version": env!("CARGO_PKG_VERSION"),
                    "protocolVersion": 1,
                    "deviceAccess": false
                }
            })
        );
    }
}

#[test]
fn unsupported_health_protocol_exits_without_backend() {
    for protocol_version in [0, 2, u64::MAX] {
        assert_eq!(
            health_response(json!({
                "type": "health", "requestId": "check-1", "protocolVersion": protocol_version
            })),
            json!({
                "requestId": "check-1", "error": "Unsupported health protocol version"
            })
        );
    }
}

#[test]
fn eof_exits_silently_without_backend() {
    let mut input = Cursor::new(Vec::<u8>::new());
    let mut output = Vec::new();
    assert!(startup::prepare(&mut input, &mut output, || -> anyhow::Result<()> {
        panic!("EOF must not initialize backend")
    })
    .unwrap()
    .is_none());
    assert!(output.is_empty());
}

#[test]
fn invalid_first_frame_exits_silently_without_backend() {
    let mut truncated_body = frame(br#"{"type":"health"}"#);
    truncated_body.pop();
    for bytes in [
        frame(br#"{"type":"health","requestId":"do-not-reflect","protocolVersion":1"#),
        frame(&[0xff]),
        frame(b""),
        truncated_body,
        (1024_u32 * 1024 + 1).to_le_bytes().to_vec(),
    ] {
        let mut input = Cursor::new(bytes);
        let mut output = Vec::new();
        assert!(startup::prepare(&mut input, &mut output, || -> anyhow::Result<()> {
            panic!("invalid framing or JSON must not initialize backend")
        })
        .unwrap()
        .is_none());
        assert!(output.is_empty());
    }
}

#[test]
fn ordinary_first_message_is_preserved_and_second_remains_for_the_loop() {
    let first = json!({
        "type": "create", "requestId": "first", "origin": "https://example.test",
        "options": {"challenge": [1, 2, 3]}
    });
    let second = json!({
        "type": "get", "requestId": "second", "origin": "https://example.test",
        "options": {"challenge": [4, 5, 6]}
    });
    let first_frame = frame(&serde_json::to_vec(&first).unwrap());
    let second_frame = frame(&serde_json::to_vec(&second).unwrap());
    let mut frames = first_frame.clone();
    frames.extend_from_slice(&second_frame);
    let mut input = Cursor::new(frames);
    let mut output = Vec::new();
    let factory_calls = Cell::new(0);

    let (backend, first_message) = startup::prepare(&mut input, &mut output, || {
        factory_calls.set(factory_calls.get() + 1);
        Ok("synthetic backend")
    })
    .unwrap()
    .expect("ordinary input must reach the existing message loop");

    assert_eq!(backend, "synthetic backend");
    assert_eq!(first_message, first);
    assert!(output.is_empty(), "startup must not answer ordinary requests");
    assert_eq!(input.position(), first_frame.len() as u64);
    assert_eq!(
        &input.get_ref()[input.position() as usize..],
        second_frame.as_slice()
    );
    assert_eq!(startup::read_message(&mut input).unwrap(), Some(second));
    assert!(startup::read_message(&mut input).unwrap().is_none());
    assert_eq!(factory_calls.get(), 1);
}

#[test]
fn non_health_messages_keep_their_existing_dispatch_shape() {
    for request in [
        json!({"type": "Health", "requestId": "", "protocolVersion": 999}),
        json!({"type": null}),
        json!({"type": 1}),
        json!({}),
        Value::Null,
        json!([]),
    ] {
        let mut input = Cursor::new(frame(&serde_json::to_vec(&request).unwrap()));
        let mut output = Vec::new();
        let factory_calls = Cell::new(0);
        let (_, message) = startup::prepare(&mut input, &mut output, || {
            factory_calls.set(factory_calls.get() + 1);
            Ok(())
        })
        .unwrap()
        .expect("only the exact health type bypasses existing dispatch");
        assert_eq!(message, request);
        assert_eq!(factory_calls.get(), 1);
        assert!(output.is_empty());
    }
}

struct FailingWriter;

impl Write for FailingWriter {
    fn write(&mut self, _buffer: &[u8]) -> io::Result<usize> {
        Err(io::Error::new(io::ErrorKind::BrokenPipe, "synthetic write failure"))
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn terminal_response_write_failure_never_falls_through_to_backend() {
    for bytes in [
        frame(br#"{"type":"health","requestId":"check-1","protocolVersion":1}"#),
        frame(br#"{"type":"health"}"#),
        frame(b"invalid json"),
    ] {
        assert!(startup::prepare(
            &mut Cursor::new(bytes),
            &mut FailingWriter,
            || -> anyhow::Result<()> { panic!("write failure must not initialize backend") },
        )
        .unwrap()
        .is_none());
    }
}
