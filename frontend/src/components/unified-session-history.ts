import { LitElement, css, html } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { RuntimeSessionSummary } from '../types';
import './preloop-session-observer';

@customElement('unified-session-history')
export class UnifiedSessionHistory extends LitElement {
  @property({ type: Array })
  sessions: Array<RuntimeSessionSummary | Record<string, unknown>> = [];

  @property({ type: Boolean })
  hideSidebar = false;

  static styles = css`
    :host {
      display: block;
    }
  `;

  render() {
    return html`
      <preloop-session-observer
        .sessions=${this.sessions}
        .hideSidebar=${this.hideSidebar}
        layout="embedded"
      ></preloop-session-observer>
    `;
  }
}
