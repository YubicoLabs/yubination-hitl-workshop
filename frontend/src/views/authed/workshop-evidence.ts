import { css, html, type TemplateResult } from 'lit';

export const workshopEvidenceStyles = css`
  .workshop-evidence {
    min-width: 0;
    padding: clamp(1rem, 3vw, 1.5rem);
    border: 1px solid var(--sl-color-neutral-300, #d4d4d8);
    border-radius: 0.8rem;
    background: var(--sl-color-neutral-50, #fafafa);
  }

  .workshop-evidence details {
    max-width: 100%;
    overflow-wrap: anywhere;
  }

  .workshop-evidence summary {
    cursor: pointer;
    font-weight: 700;
  }

  .workshop-evidence summary:focus-visible {
    outline: 3px solid currentColor;
    outline-offset: 3px;
  }
`;

export function renderWorkshopEvidence(includeClient = true): TemplateResult {
  return html`
    <section class="workshop-evidence" aria-label="What you need">
      <h2>What you need</h2>
      <ul>
        <li>Your Preloop workshop account.</li>
        <li>The provided beta YubiKey.</li>
        <li>Tested browser: Google Chrome 154 on macOS 27 (Apple silicon).</li>
      </ul>
      ${includeClient
        ? html`<details>
            <summary>Client version example</summary>
            <p>
              Codex 0.155.0-alpha.2.6 passed a recorded workshop run. This is a
              tested example, not a minimum version requirement.
            </p>
          </details>`
        : ''}
    </section>
  `;
}
