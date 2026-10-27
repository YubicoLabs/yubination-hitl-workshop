import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import '@shoelace-style/shoelace/dist/components/button/button.js';

@customElement('pagination-controls')
export class PaginationControls extends LitElement {
  @property({ type: Number })
  currentPage = 1;

  @property({ type: Boolean })
  hasMorePages = false;

  @property({ type: Boolean })
  loading = false;

  static styles = css`
    .pagination-controls {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: var(--sl-spacing-medium);
      margin-top: var(--sl-spacing-medium);
    }
    .page-number {
      font-weight: var(--sl-font-weight-semibold);
    }
  `;

  private _onPrevClick() {
    this.dispatchEvent(new CustomEvent('prev-page'));
  }

  private _onNextClick() {
    this.dispatchEvent(new CustomEvent('next-page'));
  }

  render() {
    return html`
      <div class="pagination-controls">
        <sl-button
          @click=${this._onPrevClick}
          ?disabled=${this.currentPage <= 1 || this.loading}
        >
          Previous
        </sl-button>
        <span class="page-number">Page ${this.currentPage}</span>
        <sl-button
          @click=${this._onNextClick}
          ?disabled=${!this.hasMorePages || this.loading}
        >
          Next
        </sl-button>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'pagination-controls': PaginationControls;
  }
}
