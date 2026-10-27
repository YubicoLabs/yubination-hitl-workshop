package cmd

func projectEnrollmentValidation(input map[string]interface{}) map[string]interface{} {
	output := map[string]interface{}{}
	for _, key := range []string{
		"preloop_server_present", "nested_mcp_servers_ok", "preloop_url_ok",
		"only_preloop_mcp_ok", "legacy_mcp_server_present", "config_parse_ok",
		"transport_ok", "authorization_header_ok", "validation_passed",
		"gateway_provider_ok", "gateway_base_url_ok", "gateway_token_ok",
		"gateway_api_ok", "gateway_wire_api_ok", "gateway_present",
		"gateway_model_configured", "model_provider_rewritten",
		"live_validation_supported", "live_validation_attempted", "live_validation_passed",
		"live_validation_request_logged", "control_channel_configured", "control_config_present",
		"control_config_written", "control_plugin_installed", "control_plugin_verified",
		"control_ws_url_ok", "control_bearer_token_ok", "control_adapter_package_ok",
		"control_credential_reference_present", "control_managed_agent_id_present",
		"control_runtime_principal_id_ok", "control_runtime_session_id_present",
	} {
		if value, ok := input[key].(bool); ok {
			output[key] = value
		}
	}
	states := map[string][]string{
		"live_validation_status":        {"pending", "not_run", "unsupported", "passed", "failed", "throttled"},
		"control_plugin_verification":   {"not_attempted", "not_verified_by_cli", "verified", "verified_by_runtime_connection", "unsupported_agent", "installed_config_path_missing", "managed_sidecar_starting", "managed_sidecar_connected", "managed_sidecar_disconnected", "managed_sidecar_stale_status"},
		"control_plugin_install_status": {"plugin_target_not_found", "runtime_plugin_installer_not_found", "install_attempted", "install_failed", "runtime_node_unsupported", "installed_and_verified", "installed_not_verified", "managed_sidecar_started"},
	}
	for key, allowed := range states {
		if value, ok := input[key].(string); ok && containsString(allowed, value) {
			output[key] = value
		}
	}
	return output
}

func enrollmentProtocolValue(value string, allowed []string, fallback string) string {
	if containsString(allowed, value) {
		return value
	}
	return fallback
}

func enrollmentStatus(value string) string {
	return enrollmentProtocolValue(value, []string{"pending", "active", "applied", "validated", "validation_failed", "restored"}, "pending")
}
