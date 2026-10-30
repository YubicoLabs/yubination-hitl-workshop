import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';
import './ide-setup-tabs';
import { getIdeConfigs } from '../utils/ide-configs';

@customElement('mcp-setup-dialog')
export class MCPSetupDialog extends LitElement {
  static styles = css`
    sl-dialog::part(panel) {
      background: var(--sl-panel-background-color, var(--sl-color-neutral-0));
      color: var(--sl-color-neutral-900);
      box-shadow: var(--sl-shadow-x-large);
    }

    sl-dialog::part(body) {
      padding: 0;
    }

    sl-dialog::part(overlay) {
      backdrop-filter: blur(4px);
    }

    .native-controls {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
      gap: 1rem 1.5rem;
      margin-block: 1.5rem;
    }

    label {
      display: grid;
      gap: 0.5rem;
      font-weight: 600;
      align-content: start;
    }

    select,
    input,
    button {
      box-sizing: border-box;
      min-height: 44px;
      min-width: 0;
      padding: 0.625rem 0.875rem;
      font: inherit;
      color: var(--sl-color-neutral-900);
      background: var(--sl-input-background-color, var(--sl-color-neutral-0));
      border: 1px solid var(--sl-color-neutral-400);
      border-radius: var(--sl-border-radius-medium);
    }

    select,
    input {
      width: 100%;
    }

    button {
      cursor: pointer;
      min-width: 44px;
    }

    select:focus-visible,
    input:focus-visible,
    button:focus-visible {
      outline: 2px solid var(--sl-color-primary-600);
      outline-offset: 3px;
    }

    li {
      padding-block: 0.75rem;
    }

    pre {
      padding: 1rem;
      background: var(--sl-color-neutral-100);
      border-radius: var(--sl-border-radius-medium);
    }
  `;

  @property({ type: Boolean })
  open = false;

  @state() private nativeAgent = 'Codex CLI';
  @state() private nativeApiUrl = window.location.origin;
  @state() private copyStatus = '';
  private copyRequest = 0;

  private async copyCommand(command: string, title: string): Promise<void> {
    const request = ++this.copyRequest;
    this.copyStatus = `Copying ${title} command…`;
    try {
      await navigator.clipboard.writeText(command);
      if (request === this.copyRequest) {
        this.copyStatus = `Copied ${title} command.`;
      }
    } catch {
      if (request === this.copyRequest) {
        this.copyStatus = `Could not copy ${title} command. Select and copy the command manually.`;
      }
    }
  }

  private isLoopback(hostname: string): boolean {
    return (
      hostname === 'localhost' ||
      hostname === '[::1]' ||
      /^127(?:\.\d{1,3}){3}$/.test(hostname)
    );
  }

  private validApiUrl(): boolean {
    try {
      const address = new URL(this.nativeApiUrl);
      return (
        !address.username &&
        !address.password &&
        !address.search &&
        !address.hash &&
        !/[\s'"\\`<>]/.test(this.nativeApiUrl) &&
        (address.protocol === 'https:' ||
          (address.protocol === 'http:' && this.isLoopback(address.hostname)))
      );
    } catch {
      return false;
    }
  }

  render() {
    const shellQuote = (value: string): string =>
      `'${value.replace(/'/g, `'"'"'`)}'`;
    const cli = `./cli/build/preloop --url ${shellQuote(this.nativeApiUrl)}`;
    const agent = `"${this.nativeAgent}"`;
    const steps = [
      [
        'login',
        'Sign in to Preloop',
        `${cli} login --frontend-url ${shellQuote(window.location.origin)}`,
      ],
      [
        'discover',
        'Find your installed clients',
        `${cli} agents discover --no-onboard-prompt`,
      ],
      [
        'preview',
        'Review the proposed changes',
        `${cli} agents onboard ${agent} --dry-run --skip-live-validate`,
      ],
      [
        'apply',
        'Connect your selected client',
        `${cli} agents onboard ${agent} --skip-live-validate`,
      ],
      ['status', 'Check enrollment status', `${cli} agents status ${agent}`],
    ];
    const governedClientConfigs = getIdeConfigs().filter((config) =>
      ['codex-cli', 'claude-code', 'curl'].includes(config.ide)
    );

    return html`
      <sl-dialog
        label="Connect your client"
        ?open=${this.open}
        @sl-hide=${() => this._handleClose()}
        style="--width: 65rem;"
      >
        <h2 style="padding: 0 1.5rem;">Connect with an API key</h2>
        <p style="padding: 0 1.5rem;">
          The workshop MCP server and approval policy are already configured.
          Create an API key in this same Preloop account and follow the selected
          client’s instructions below. Curl demonstrates the protocol without an
          AI agent.
        </p>
        <ide-setup-tabs
          .configs=${governedClientConfigs}
          defaultTab="codex-cli"
          variant="modal"
        ></ide-setup-tabs>
        <section
          aria-label="Preloop native onboarding (optional)"
          style="padding: 1.5rem; background: var(--sl-color-neutral-0);"
        >
          <h2>Preloop native onboarding (optional)</h2>
          <p>
            Native onboarding discovers existing MCP connections and connects
            them through the Preloop proxy. It also works with the preconfigured
            workshop server.
          </p>
          <p>
            This optional path additionally requires Go 1.24+ and make. Use the
            workshop checkout supplied by your facilitator and sign in to Codex
            or Claude Code. From the checkout folder, run
            <code>make -C cli build</code>. The output is
            <code>cli/build/preloop</code>. Use this workshop build; another
            installed Preloop version may not include these commands.
          </p>
          <div class="native-controls">
            <label
              >Which client will you use?
              <select
                data-native-agent
                @change=${(event: Event) => {
                  const selected = (event.target as HTMLSelectElement).value;
                  if (['Codex CLI', 'Claude Code'].includes(selected)) {
                    this.nativeAgent = selected;
                  }
                }}
              >
                <option value="Codex CLI">Codex CLI</option>
                <option value="Claude Code">Claude Code</option>
              </select>
            </label>
            ${this.isLoopback(window.location.hostname)
              ? html`
                  <label
                    >Preloop API address
                    <input
                      data-native-api-url
                      type="url"
                      .value=${this.nativeApiUrl}
                      @input=${(event: Event) => {
                        this.nativeApiUrl = (
                          event.target as HTMLInputElement
                        ).value;
                      }}
                    />
                  </label>
                  <p>
                    Use the address supplied by your facilitator. For a local
                    setup it may differ from this page’s address. Only HTTP
                    loopback or HTTPS addresses are accepted.
                  </p>
                `
              : html`<p>Commands use this workshop site's address.</p>`}
          </div>
          <p>
            Back up your client settings. Review the preview before applying it.
            Keep your current model sign-in and settings; stop if unrelated
            connections would change. Connect only the selected client; do not
            select automatic yes or all clients. These steps do not test a model
            request. Check the connection in your client next.
          </p>
          ${this.validApiUrl()
            ? html`<ol>
                ${steps.map(
                  ([step, title, command]) => html`
                    <li>
                      <p>${title}</p>
                      <pre
                        style="white-space: pre-wrap; overflow-wrap: anywhere;"
                      ><code data-native-step=${step}>${command}</code></pre>
                      <button
                        type="button"
                        data-native-copy=${step}
                        aria-label=${`Copy ${title} command`}
                        @click=${() => this.copyCommand(command, title)}
                      >
                        Copy
                      </button>
                    </li>
                  `
                )}
              </ol>`
            : html`<p role="alert">
                Enter a valid API URL: HTTP loopback or HTTPS, without
                credentials, query, fragment, whitespace or shell characters.
                Commands are withheld until the address is safe.
              </p>`}
          <p role="status" aria-live="polite" aria-atomic="true">
            ${this.copyStatus}
          </p>
          <p>
            If you used native onboarding, keep the configuration and credential
            it created. In your actual client, use <code>/mcp</code> to inspect
            connected tools before requesting any customer change.
          </p>
        </section>
      </sl-dialog>
    `;
  }

  private _handleClose() {
    this.dispatchEvent(new CustomEvent('close'));
  }
}
