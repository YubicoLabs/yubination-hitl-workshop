import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('billing-toggle')
export class BillingToggle extends LitElement {
  @property({ type: String, reflect: true })
  interval: 'month' | 'year' = 'month';

  @property({ type: Boolean, reflect: true })
  dark = false;

  private _handleIntervalChange(newInterval: 'month' | 'year') {
    if (this.interval !== newInterval) {
      this.interval = newInterval;
      this.dispatchEvent(
        new CustomEvent('interval-change', {
          detail: { value: this.interval },
          bubbles: true,
          composed: true,
        })
      );
    }
  }

  static styles = css`
    .billing-toggle {
      display: flex;
      justify-content: center;
      margin: 1.5rem 0 2rem 0;
    }

    .billing-toggle.dark sl-button[variant='default']::part(base) {
      background-color: transparent;
      border-color: #58a6ff;
      color: #58a6ff;
    }

    .billing-toggle.dark sl-button[variant='default']::part(base):hover {
      background-color: #58a6ff;
      color: white;
    }

    .billing-toggle.dark sl-button[variant='primary']::part(base) {
      background-color: #58a6ff;
      border-color: #58a6ff;
      color: white;
    }

    sl-button-group {
      position: relative;
      --sl-button-group-spacing: 0;
    }
  `;

  render() {
    return html`
      <div class="billing-toggle ${this.dark ? 'dark' : ''}">
        <sl-button-group>
          <sl-button
            variant=${this.interval === 'month' ? 'primary' : 'default'}
            @click=${() => this._handleIntervalChange('month')}
          >
            Monthly
          </sl-button>
          <sl-button
            variant=${this.interval === 'year' ? 'primary' : 'default'}
            @click=${() => this._handleIntervalChange('year')}
          >
            Yearly
          </sl-button>
        </sl-button-group>
      </div>
    `;
  }
}
