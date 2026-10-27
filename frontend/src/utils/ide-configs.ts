import type { IdeConfig } from '../components/ide-setup-tabs';

export function getIdeConfigs(): IdeConfig[] {
  const mcpUrl = `${window.location.origin}/mcp`;
  const envVarName = 'PRELOOP_API_KEY';
  const apiKeyPrerequisite =
    'Preloop API key (create a normal API key in <a href="/console/settings/api-keys">Settings → API Keys</a>)';

  return [
    {
      ide: 'claude-code',
      ide_name: 'Claude Code',
      logo_path: '/images/logos/claude.svg',
      logo_width: '40',
      prerequisites: [apiKeyPrerequisite],
      setup_instructions: `Export <code>${envVarName}</code> in the shell that launches Claude Code, then add the HTTP server. The single quotes preserve Claude Code's documented <code>\${${envVarName}}</code> environment-variable reference instead of writing a credential into its configuration.`,
      code: `export ${envVarName}="YOUR_API_KEY_HERE"

claude mcp add --transport http preloop ${mcpUrl} --header 'Authorization: Bearer \${${envVarName}}'`,
    },
    {
      ide: 'gemini-cli',
      ide_name: 'Gemini CLI',
      logo_path: '/images/logos/gemini-cli.png',
      logo_width: '40',
      prerequisites: [apiKeyPrerequisite],
      setup_instructions:
        'Install the MCP server using the Gemini CLI. Replace <code>YOUR_API_KEY_HERE</code> with your actual Preloop API key.',
      code: `export ${envVarName}="YOUR_API_KEY_HERE"

gemini mcp add preloop ${mcpUrl} --header "Authorization: Bearer $${envVarName}"`,
    },
    {
      ide: 'codex-cli',
      ide_name: 'Codex CLI',
      logo_path: '/images/logos/openai.svg',
      logo_width: '40',
      prerequisites: [apiKeyPrerequisite],
      setup_instructions: `First run <code>export ${envVarName}=&quot;YOUR_API_KEY_HERE&quot;</code> in the shell that launches Codex. Separately, add the TOML below to <code>~/.codex/config.toml</code>. Codex reads the bearer token from the named environment variable; the secret does not belong in TOML. Run <code>codex</code> and use <code>/mcp</code> to check the connection. Keep the session running while you review the Preloop approval in your browser. The 900-second tool timeout allows time for that decision; Codex tool permission is separate from Preloop approval.`,
      code: `[mcp_servers.preloop]
url = "${mcpUrl}"
bearer_token_env_var = "${envVarName}"
tool_timeout_sec = 900`,
    },
    {
      ide: 'curl',
      ide_name: 'curl (MCP protocol)',
      logo_path: '/assets/preloop-badge.svg',
      logo_width: '40',
      prerequisites: [apiKeyPrerequisite, 'Bash, curl, awk, and jq'],
      setup_instructions:
        'Run this protocol recipe in Bash. It initializes MCP, validates JSON or Server-Sent Events responses, reuses the negotiated session and protocol version, lists tools, and calls one governed Preloop tool. Replace the placeholder key, tool name, and arguments.',
      code: `set -euo pipefail

export ${envVarName}="YOUR_API_KEY_HERE"
MCP_URL="${mcpUrl}"
HEADERS_FILE="$(mktemp)"
trap 'rm -f "$HEADERS_FILE"' EXIT

parse_mcp_response() {
  local response="$1"
  local label="$2"
  local parsed

  if parsed="$(printf '%s' "$response" | jq -ce 'select(type == "object")' 2>/dev/null)"; then
    :
  else
    parsed="$(printf '%s\\n' "$response" | awk '/^data:[[:space:]]*/ { sub(/^data:[[:space:]]*/, ""); print }' | jq -sce 'map(select(type == "object")) | last')" || {
      printf '%s: response was neither JSON nor valid MCP SSE\\n' "$label" >&2
      exit 1
    }
  fi

  if printf '%s' "$parsed" | jq -e '.error != null' >/dev/null; then
    printf '%s: JSON-RPC error: %s\\n' "$label" "$(printf '%s' "$parsed" | jq -c '.error')" >&2
    exit 1
  fi

  printf '%s\\n' "$parsed"
}

INITIALIZE_RESPONSE="$(curl --fail-with-body --silent --show-error \\
  --dump-header "$HEADERS_FILE" \\
  --request POST "$MCP_URL" \\
  --header "Authorization: Bearer $${envVarName}" \\
  --header 'Content-Type: application/json' \\
  --header 'Accept: application/json, text/event-stream' \\
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"preloop-curl","version":"1.0"}}}')"
INITIALIZE_JSON="$(parse_mcp_response "$INITIALIZE_RESPONSE" initialize)"
printf '%s\\n' "$INITIALIZE_JSON"

SESSION_ID="$(awk 'tolower($1) == "mcp-session-id:" { gsub("\\r", "", $2); print $2 }' "$HEADERS_FILE" | tail -n 1)"
PROTOCOL_VERSION="$(printf '%s' "$INITIALIZE_JSON" | jq -er '.result.protocolVersion | select(type == "string" and length > 0)')" || {
  printf 'initialize: missing negotiated protocol version\\n' >&2
  exit 1
}
SESSION_ARGS=(--header "MCP-Protocol-Version: $PROTOCOL_VERSION")
if [ -n "$SESSION_ID" ]; then
  SESSION_ARGS+=(--header "Mcp-Session-Id: $SESSION_ID")
fi

curl --fail-with-body --silent --show-error \\
  --request POST "$MCP_URL" \\
  --header "Authorization: Bearer $${envVarName}" \\
  --header 'Content-Type: application/json' \\
  --header 'Accept: application/json, text/event-stream' \\
  "\${SESSION_ARGS[@]}" \\
  --data '{"jsonrpc":"2.0","method":"notifications/initialized"}'

TOOLS_RESPONSE="$(curl --fail-with-body --silent --show-error \\
  --request POST "$MCP_URL" \\
  --header "Authorization: Bearer $${envVarName}" \\
  --header 'Content-Type: application/json' \\
  --header 'Accept: application/json, text/event-stream' \\
  "\${SESSION_ARGS[@]}" \\
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')"
parse_mcp_response "$TOOLS_RESPONSE" tools/list

TOOL_NAME="REPLACE_WITH_TOOL_NAME"
TOOL_ARGUMENTS='{}'
CALL_RESPONSE="$(jq -cn --arg name "$TOOL_NAME" --argjson arguments "$TOOL_ARGUMENTS" \\
  '{jsonrpc:"2.0",id:3,method:"tools/call",params:{name:$name,arguments:$arguments}}' | \\
curl --fail-with-body --silent --show-error \\
  --request POST "$MCP_URL" \\
  --header "Authorization: Bearer $${envVarName}" \\
  --header 'Content-Type: application/json' \\
  --header 'Accept: application/json, text/event-stream' \\
  "\${SESSION_ARGS[@]}" \\
  --data-binary @-)"
parse_mcp_response "$CALL_RESPONSE" tools/call`,
    },
    {
      ide: 'ide-json',
      ide_name: 'VSCode / Cursor / Windsurf',
      logo_path: '/images/logos/vscode.svg',
      logo_width: '40',
      prerequisites: [
        apiKeyPrerequisite,
        'Works with Cursor, Windsurf, VSCode, and Antigravity',
      ],
      setup_instructions:
        'Add this to your MCP settings. Replace <code>YOUR_API_KEY_HERE</code> with your actual Preloop API key.',
      code: `{
  "mcpServers": {
    "preloop": {
      "url": "${mcpUrl}",
      "transport": "http-streaming",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY_HERE"
      }
    }
  }
}`,
    },
  ];
}
