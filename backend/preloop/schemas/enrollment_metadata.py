"""Finite enrollment metadata shared by ingress, persistence and legacy reads."""

from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

_ENROLLMENT_TIMESTAMP = TypeAdapter(datetime | None)

VALIDATION_BOOLEANS = frozenset(
    {
        "preloop_server_present",
        "nested_mcp_servers_ok",
        "preloop_url_ok",
        "only_preloop_mcp_ok",
        "legacy_mcp_server_present",
        "config_parse_ok",
        "transport_ok",
        "authorization_header_ok",
        "validation_passed",
        "gateway_provider_ok",
        "gateway_base_url_ok",
        "gateway_token_ok",
        "gateway_api_ok",
        "gateway_wire_api_ok",
        "gateway_present",
        "gateway_model_configured",
        "model_provider_rewritten",
        "live_validation_supported",
        "live_validation_attempted",
        "live_validation_passed",
        "live_validation_request_logged",
        "control_channel_configured",
        "control_config_present",
        "control_config_written",
        "control_plugin_installed",
        "control_plugin_verified",
        "control_ws_url_ok",
        "control_bearer_token_ok",
        "control_adapter_package_ok",
        "control_credential_reference_present",
        "control_managed_agent_id_present",
        "control_runtime_principal_id_ok",
        "control_runtime_session_id_present",
    }
)
VALIDATION_STATES = {
    "live_validation_status": frozenset(
        {"pending", "not_run", "unsupported", "passed", "failed", "throttled"}
    ),
    "control_plugin_verification": frozenset(
        {
            "not_attempted",
            "not_verified_by_cli",
            "verified",
            "verified_by_runtime_connection",
            "unsupported_agent",
            "installed_config_path_missing",
            "managed_sidecar_starting",
            "managed_sidecar_connected",
            "managed_sidecar_disconnected",
            "managed_sidecar_stale_status",
        }
    ),
    "control_plugin_install_status": frozenset(
        {
            "plugin_target_not_found",
            "runtime_plugin_installer_not_found",
            "install_attempted",
            "install_failed",
            "runtime_node_unsupported",
            "installed_and_verified",
            "installed_not_verified",
            "managed_sidecar_started",
        }
    ),
}
ENROLLMENT_TYPES = frozenset(
    {
        "cli_managed_config",
        "cli_managed_config_restore",
        "runtime_plugin_control",
        "runtime_session_bootstrap",
    }
)
ADAPTER_KEYS = frozenset(
    {
        "claude_code",
        "claude_desktop",
        "codex",
        "openclaw",
        "gemini_cli",
        "opencode",
        "hermes",
        "desktop_agent",
    }
)
ENROLLMENT_STATUSES = frozenset(
    {"pending", "active", "applied", "validated", "validation_failed", "restored"}
)
GATEWAY_FLAGS = (
    "gateway_provider_ok",
    "gateway_base_url_ok",
    "gateway_token_ok",
    "model_provider_rewritten",
    "gateway_model_configured",
)


def protocol_value(value: Any, allowed: frozenset[str], fallback: Any) -> Any:
    """Drop unknown protocol strings without echoing rejected input."""
    return value if isinstance(value, str) and value in allowed else fallback


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested(value: Any, *path: str) -> dict[str, Any]:
    for key in path:
        value = _object(value).get(key)
    return _object(value)


def project_validation(value: Any, managed_config: Any = None) -> dict[str, bool | str]:
    """Keep strict assertions and infer only legacy configuration shapes."""
    source = _object(value)
    result: dict[str, bool | str] = {
        key: entry
        for key, entry in source.items()
        if key in VALIDATION_BOOLEANS and type(entry) is bool
    }
    for key, allowed in VALIDATION_STATES.items():
        entry = source.get(key)
        if isinstance(entry, str) and entry in allowed:
            result[key] = entry

    config = _object(managed_config)
    if "preloop_server_present" not in result and any(
        "preloop" in container
        for container in (
            _nested(config, "servers"),
            _nested(config, "mcpServers"),
            _nested(config, "mcp_servers"),
            _nested(config, "mcp", "servers"),
            _nested(config, "mcp"),
        )
    ):
        result["preloop_server_present"] = (
            result.get("nested_mcp_servers_ok") is not False
        )

    model = _nested(config, "model")
    env = _nested(config, "env")
    legacy_gateway = (
        "preloop" in _nested(config, "models", "providers")
        or (
            config.get("model_provider") == "preloop"
            and "preloop" in _nested(config, "model_providers")
        )
        or (
            "preloop" in _nested(config, "provider")
            and isinstance(config.get("model"), str)
            and config["model"].startswith("preloop/")
        )
        or (
            model.get("provider") == "custom"
            and isinstance(model.get("base_url"), str)
            and "/openai/v1" in model["base_url"]
            and any(isinstance(model.get(key), str) for key in ("api_key", "apiKey"))
            and any(isinstance(model.get(key), str) for key in ("default", "model"))
        )
        or (
            isinstance(env.get("ANTHROPIC_BASE_URL"), str)
            and isinstance(env.get("ANTHROPIC_MODEL"), str)
        )
        or (
            isinstance(config.get("baseUrl"), str)
            and isinstance(config.get("apiKey"), str)
            and (
                isinstance(model.get("name"), str)
                or isinstance(config.get("model"), str)
            )
        )
    )
    if "gateway_model_configured" not in result and legacy_gateway:
        result["gateway_model_configured"] = not any(
            result.get(key) is False for key in GATEWAY_FLAGS
        )

    control = _nested(config, "preloop", "control")
    if not control:
        for plugin in ("openclaw-plugin", "@preloop/openclaw-plugin"):
            control = _nested(config, "plugins", "entries", plugin, "config")
            if control:
                break
    if "control_config_present" not in result and control:
        result["control_config_present"] = bool(
            control.get("enabled") is True
            and isinstance(control.get("control_ws_url"), str)
            and control["control_ws_url"].strip()
            and result.get("control_config_written") is not False
            and result.get("control_ws_url_ok") is not False
        )
    return result


def control_validation_ready(validation: dict[str, bool | str]) -> bool:
    """Read finite control assertions, respecting explicit negative evidence."""
    keys = ("control_plugin_verified", "control_ws_url_ok", "control_bearer_token_ok")
    if any(
        validation.get(key) is False for key in ("control_channel_configured", *keys)
    ):
        return False
    return validation.get("control_channel_configured") is True or all(
        validation.get(key) is True for key in keys
    )


def project_enrollment_request(value: Any) -> dict[str, Any]:
    """Project legacy request shapes before field validation can echo metadata."""
    source = _object(value)
    result: dict[str, Any] = {}
    for key in ("last_applied_at", "last_validated_at", "last_restored_at"):
        if key in source:
            try:
                result[key] = _ENROLLMENT_TIMESTAMP.validate_python(source[key])
            except ValidationError:
                result[key] = ""
    result["validation_result"] = project_validation(
        source.get("validation_result"), source.get("managed_config")
    )
    for key in ("discovered_config", "managed_config", "backup_metadata"):
        result[key] = {}
    result["target_config_path"] = None
    for key, allowed, fallback in (
        ("enrollment_type", ENROLLMENT_TYPES, "cli_managed_config"),
        ("adapter_key", ADAPTER_KEYS, None),
        ("status", ENROLLMENT_STATUSES, "pending"),
    ):
        if key in source:
            result[key] = protocol_value(source[key], allowed, fallback)
    if "restore_available" in source:
        result["restore_available"] = source["restore_available"] is True
    return result
