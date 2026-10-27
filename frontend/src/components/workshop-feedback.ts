import { LitElement, html, css } from 'lit';
import { fetchWithAuth } from '../api';

type Feedback = {
  recommendation: number;
  worked_well: string | null;
  could_improve: string | null;
};

export class WorkshopFeedback extends LitElement {
  static properties = {
    recommendation: { state: true },
    workedWell: { state: true },
    couldImprove: { state: true },
    pending: { state: true },
    loadFailed: { state: true },
    message: { state: true },
  };

  private recommendation = '';
  private workedWell = '';
  private couldImprove = '';
  private pending = true;
  private loadFailed = false;
  private message = '';

  static styles = css`
    :host {
      display: block;
    }
    label {
      display: block;
      margin: 1rem 0;
    }
    textarea,
    select {
      display: block;
      font: inherit;
      max-width: 100%;
    }
    textarea {
      width: 100%;
      box-sizing: border-box;
      min-height: 5rem;
    }
    fieldset {
      border: 0;
      padding: 0;
      margin: 0;
      min-width: 0;
    }
  `;

  connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  private async load(): Promise<void> {
    this.pending = true;
    this.loadFailed = false;
    this.message = 'Loading feedback…';
    try {
      const response = await fetchWithAuth('/api/v1/workshop/feedback');
      if (!response.ok) throw new Error('load');
      const existing: Feedback | null = await response.json();
      if (existing) {
        this.recommendation = String(existing.recommendation);
        this.workedWell = existing.worked_well ?? '';
        this.couldImprove = existing.could_improve ?? '';
      }
      this.message = '';
    } catch {
      this.loadFailed = true;
      this.message = 'Could not load your feedback. Retry before editing.';
    } finally {
      this.pending = false;
    }
  }

  private async submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (this.pending || this.loadFailed || !this.recommendation) return;
    this.pending = true;
    this.message = 'Saving feedback…';
    try {
      const response = await fetchWithAuth('/api/v1/workshop/feedback', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recommendation: Number(this.recommendation),
          worked_well: this.workedWell,
          could_improve: this.couldImprove,
        }),
      });
      if (!response.ok) throw new Error('save');
      this.message = 'Feedback saved. You can update it here.';
    } catch {
      this.message =
        'Could not save your feedback. Your answers are still here; try again.';
    } finally {
      this.pending = false;
    }
  }

  render() {
    return html`
      <h3>Workshop feedback (optional)</h3>
      <p>
        Feedback is optional and visible to workshop organizers. Do not include
        sensitive information.
      </p>
      <form @submit=${this.submit}>
        <fieldset ?disabled=${this.pending || this.loadFailed}>
          <label for="recommendation"
            >How likely are you to recommend this workshop?</label
          >
          <select
            id="recommendation"
            required
            .value=${this.recommendation}
            @change=${(event: Event) => {
              this.recommendation = (event.target as HTMLSelectElement).value;
            }}
          >
            <option value="">Choose a rating</option>
            ${Array.from({ length: 10 }, (_, index) => index + 1).map(
              (rating) =>
                html`<option value=${rating}>
                  ${rating === 1
                    ? '1 — Not likely'
                    : rating === 10
                      ? '10 — Very likely'
                      : rating}
                </option>`
            )}
          </select>
          <label for="worked-well">What worked well? (optional)</label>
          <textarea
            id="worked-well"
            maxlength="2000"
            .value=${this.workedWell}
            @input=${(event: Event) => {
              this.workedWell = (event.target as HTMLTextAreaElement).value;
            }}
          ></textarea>
          <label for="could-improve">What could improve? (optional)</label>
          <textarea
            id="could-improve"
            maxlength="2000"
            .value=${this.couldImprove}
            @input=${(event: Event) => {
              this.couldImprove = (event.target as HTMLTextAreaElement).value;
            }}
          ></textarea>
          <button type="submit" ?disabled=${this.pending || this.loadFailed}>
            Send feedback
          </button>
        </fieldset>
      </form>
      ${this.loadFailed
        ? html`<button type="button" @click=${this.load}>Retry loading</button>`
        : ''}
      <p role="status" aria-live="polite">${this.message}</p>
    `;
  }
}

customElements.define('workshop-feedback', WorkshopFeedback);
