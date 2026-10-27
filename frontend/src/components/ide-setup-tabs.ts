import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { ideSetupStyles } from '../styles/ide-setup-styles';

export interface IdeConfig {
  ide: string;
  ide_name: string;
  logo_path: string;
  logo_width: string;
  prerequisites: string[];
  setup_instructions: string;
  code: string;
}

@customElement('ide-setup-tabs')
export class IdeSetupTabs extends LitElement {
  static styles = [
    css`
      :host {
        --gradient-brand: linear-gradient(225deg, #d35400, #6c3483, #1f618d);
      }
    `,
    ideSetupStyles,
    css`
      .ide-logo-container {
        background: transparent;
        border: 0;
        width: 100%;
        cursor: pointer;
        flex-direction: column;
        gap: 0.4rem;
        font: inherit;
        color: inherit;
        min-width: 7.5rem;
      }
      .client-label {
        font-size: 0.875rem;
        font-weight: 600;
      }
      .ide-logo-container img {
        max-height: 2rem;
        object-fit: contain;
      }
      .ide-logo-container:focus-visible {
        outline: 3px solid var(--sl-color-primary-600, #1668cc);
        outline-offset: -3px;
      }
    `,
  ];

  @property({ type: Array })
  configs: IdeConfig[] = [];

  @property({ type: String })
  defaultTab = 'claude-code';

  @property({ type: String })
  variant: 'default' | 'modal' = 'default';

  @property({ type: String })
  globalPrerequisite = '';

  @property({ type: String })
  globalPrerequisiteLink = '';

  @property({ type: String })
  globalPrerequisiteLinkText = '';

  @property({ type: String })
  helpText = '';

  @state()
  private _activeTab = '';

  connectedCallback() {
    super.connectedCallback();
    this._activeTab = this.defaultTab;
  }

  private _handleTabClick(ide: string) {
    this._activeTab = ide;
  }

  private async _handleTabKey(e: KeyboardEvent, index: number) {
    let next: number;
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        next = (index + 1) % this.configs.length;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        next = (index + this.configs.length - 1) % this.configs.length;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = this.configs.length - 1;
        break;
      default:
        return;
    }
    e.preventDefault();
    this._activeTab = this.configs[next].ide;
    await this.updateComplete;
    this.renderRoot
      .querySelectorAll<HTMLElement>('[role="tab"]')
      [next]?.focus();
  }

  private _copyCode(e: Event) {
    const button = e.currentTarget as HTMLElement;
    const pre = button.previousElementSibling;
    if (pre && pre.tagName === 'PRE') {
      const code = pre.querySelector('code');
      if (code) {
        navigator.clipboard.writeText(code.innerText).then(() => {
          const originalHTML = button.innerHTML;
          button.innerHTML =
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-check" viewBox="0 0 16 16"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/></svg>';
          setTimeout(() => {
            button.innerHTML = originalHTML;
          }, 2000);
        });
      }
    }
  }

  render() {
    if (this.configs.length === 0) {
      return html`<div>No IDE configurations available.</div>`;
    }

    const activeConfig = this.configs.find((c) => c.ide === this._activeTab);

    return html`
      <div
        class="ide-setup-tabs-container ${this.variant === 'modal'
          ? 'modal-variant'
          : ''}"
      >
        ${this.globalPrerequisite
          ? html`
              <div class="global-prereq">
                <div class="global-prereq-content">
                  <strong>${this.globalPrerequisite}</strong>
                  ${this.globalPrerequisiteLink
                    ? html`
                        <a
                          href="${this.globalPrerequisiteLink}"
                          class="prereq-link"
                          >${this.globalPrerequisiteLinkText}</a
                        >
                      `
                    : ''}
                </div>
              </div>
            `
          : ''}
        <div class="tabs-wrapper">
          <div class="ide-tabs" role="tablist" aria-label="Choose your client">
            ${this.configs.map(
              (config, index) => html`
                <button
                  type="button"
                  id=${`client-tab-${config.ide}`}
                  aria-controls="client-setup-panel"
                  class="ide-logo-container ${this._activeTab === config.ide
                    ? 'active'
                    : ''}"
                  role="tab"
                  tabindex=${this._activeTab === config.ide ? 0 : -1}
                  aria-selected="${this._activeTab === config.ide}"
                  @click=${() => this._handleTabClick(config.ide)}
                  @keydown=${(e: KeyboardEvent) => this._handleTabKey(e, index)}
                >
                  <img
                    src="${config.logo_path}"
                    alt=""
                    aria-hidden="true"
                    width="${config.logo_width}"
                  />
                  <span class="client-label">${config.ide_name}</span>
                </button>
              `
            )}
          </div>

          <div
            class="tab-content"
            role="tabpanel"
            id="client-setup-panel"
            aria-labelledby=${`client-tab-${this._activeTab}`}
            tabindex="0"
          >
            ${activeConfig
              ? html`
                  <div>
                    <h4 style="margin-top: 0; margin-bottom: 1.5rem;">
                      ${activeConfig.ide_name} Setup
                    </h4>
                    ${activeConfig.prerequisites.length > 0
                      ? html` <h5>Prerequisites</h5>
                          <ul>
                            ${activeConfig.prerequisites.map(
                              (prereq) => html`<li>${unsafeHTML(prereq)}</li>`
                            )}
                          </ul>`
                      : ``}
                    <h5>Setup</h5>
                    <p>${unsafeHTML(activeConfig.setup_instructions)}</p>
                    <div class="code-container">
                      <pre><code>${activeConfig.code.trimStart()}</code></pre>
                      <button
                        class="copy-btn"
                        @click=${this._copyCode}
                        aria-label="Copy code to clipboard"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="16"
                          height="16"
                          fill="currentColor"
                          class="bi bi-clipboard"
                          viewBox="0 0 16 16"
                        >
                          <path
                            d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z"
                          />
                          <path
                            d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z"
                          />
                        </svg>
                      </button>
                    </div>
                    ${this.helpText
                      ? html`<p
                          style="margin-top: 1.5rem; font-size: 0.875rem; opacity: 0.9; line-height: 1.5;"
                        >
                          ${this.helpText}
                        </p>`
                      : ''}
                  </div>
                `
              : html`<div>Please select an IDE from the tabs.</div>`}
          </div>
        </div>
      </div>
    `;
  }
}
