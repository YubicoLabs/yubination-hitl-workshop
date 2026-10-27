import { LitElement, html, css, unsafeCSS } from 'lit';
import { customElement } from 'lit/decorators.js';
import './app-header';
import './app-footer';
import landingStyles from '../styles/landing.css?inline';

/**
 * Wrapper component for static SSR content (privacy, terms, etc.)
 * Provides page structure (header, footer) around static HTML content
 */
@customElement('static-view-wrapper')
export class StaticViewWrapper extends LitElement {
  static styles = [
    unsafeCSS(landingStyles),
    css`
      :host {
        display: flex;
        flex-direction: column;
        min-height: 100vh;
        width: 100%;
      }

      main {
        flex: 1;
        padding: 3.5rem 1.5rem 5rem;
        max-width: 760px;
        margin: 0 auto;
        width: 100%;
      }

      @media (max-width: 640px) {
        main {
          padding: 2rem 1.25rem 3.5rem;
        }
      }

      /* Styles for slotted article content live as an inline <style> tag
         emitted alongside the article in the light DOM (see
         loadMarkdownContent in vite-plugin-brand.ts). ::slotted() cannot
         style descendants of slotted elements, so we cannot put them here. */
    `,
  ];

  render() {
    return html`
      <app-header></app-header>
      <main>
        <div class="text-section">
          <slot></slot>
        </div>
      </main>
      <app-footer></app-footer>
    `;
  }
}
