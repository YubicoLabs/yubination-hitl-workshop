import type { IdeConfig } from '../components/ide-setup-tabs';

export function getIdeConfigs(): IdeConfig[] {
  const mcpUrl = `${window.location.origin}/mcp`;
  const envVarName = 'PRELOOP_API_KEY';

  return [
    {
      ide: 'claude-code',
      ide_name: 'Claude Code',
      logo_path: '/images/logos/claude.svg',
      logo_width: '40',
      prerequisites: [
        'Preloop API key (create in <a href="/console/settings/api-keys">Settings → API Keys</a>)',
      ],
      setup_instructions:
        'Export your API key as an environment variable, then add the MCP server. Replace <code>YOUR_API_KEY_HERE</code> with your actual Preloop API key.',
      code: `export ${envVarName}="YOUR_API_KEY_HERE"

claude mcp add --transport http preloop ${mcpUrl} --header "Authorization: Bearer $${envVarName}"`,
    },
    {
      ide: 'gemini-cli',
      ide_name: 'Gemini CLI',
      logo_path: '/images/logos/gemini-cli.png',
      logo_width: '40',
      prerequisites: [
        'Preloop API key (create in <a href="/console/settings/api-keys">Settings → API Keys</a>)',
      ],
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
      prerequisites: [
        'Preloop API key (create in <a href="/console/settings/api-keys">Settings → API Keys</a>)',
      ],
      setup_instructions: `Codex supports Streamable HTTP MCP servers via <code>url</code>. Use <code>bearer_token_env_var</code> so you don't have to store secrets in the file.<br><br>Add this to your Codex config, then export the API key. Run <code>codex</code> and use <code>/mcp</code> in the TUI to verify the server is connected.`,
      code: `[mcp_servers.preloop]
url = "${mcpUrl}"
bearer_token_env_var = "${envVarName}"

# Then export your API key:
export ${envVarName}="YOUR_API_KEY_HERE"`,
    },
    {
      ide: 'ide-json',
      ide_name: 'VSCode / Cursor / Windsurf',
      logo_path: '/images/logos/vscode.svg',
      logo_width: '40',
      prerequisites: [
        'Preloop API key (create in <a href="/console/settings/api-keys">Settings → API Keys</a>)',
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
