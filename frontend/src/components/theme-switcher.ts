import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import '@shoelace-style/shoelace/dist/components/button-group/button-group.js';
import '@shoelace-style/shoelace/dist/components/icon-button/icon-button.js';
import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';
import { Theme, DEFAULT_THEME } from '../theme';

@customElement('theme-switcher')
export class ThemeSwitcher extends LitElement {
  @state()
  private selectedTheme: Theme = DEFAULT_THEME;

  static styles = css``;

  connectedCallback() {
    super.connectedCallback();
    const storedTheme = localStorage.getItem('theme') as Theme | null;
    this.selectedTheme = storedTheme || DEFAULT_THEME;
  }

  private handleThemeChange(newTheme: Theme) {
    this.selectedTheme = newTheme;
    localStorage.setItem('theme', newTheme);
    window.dispatchEvent(
      new CustomEvent('theme-change', { detail: { theme: newTheme } })
    );
  }

  render() {
    return html`
      <sl-button-group label="Theme">
        <sl-button
          size="small"
          variant="${this.selectedTheme === 'light' ? 'primary' : 'default'}"
          @click=${() => this.handleThemeChange('light')}
        >
          <sl-icon name="sun" label="Light theme"></sl-icon>
        </sl-button>
        <sl-button
          size="small"
          variant="${this.selectedTheme === 'dark' ? 'primary' : 'default'}"
          @click=${() => this.handleThemeChange('dark')}
        >
          <sl-icon name="moon" label="Dark theme"></sl-icon>
        </sl-button>
        <sl-button
          size="small"
          variant="${this.selectedTheme === 'system' ? 'primary' : 'default'}"
          @click=${() => this.handleThemeChange('system')}
        >
          <sl-icon name="display" label="System theme"></sl-icon>
        </sl-button>
      </sl-button-group>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'theme-switcher': ThemeSwitcher;
  }
}
