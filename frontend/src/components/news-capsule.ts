import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

interface NewsItem {
  text: string;
  link: string;
  label: string;
}

@customElement('news-capsule')
export class NewsCapsule extends LitElement {
  @property({ type: Object }) newsItem: NewsItem = {
    label: 'New',
    text: 'Compliance Suggestions and Improved Reasoning',
    link: '/features/compliance',
  };

  static styles = css`
    :host {
      display: block;
      text-align: center;
      margin-top: -4rem;
      margin-bottom: 4rem;
    }
    .capsule {
      display: inline-flex;
      align-items: center;
      gap: 0.75rem;
      background-color: rgba(255, 255, 255, 0.05);
      color: var(--sl-color-neutral-800);
      padding: 0.75rem 1.25rem;
      border-radius: 9999px;
      font-size: var(--sl-font-size-medium);
      text-decoration: none;
      transition: all 0.3s ease;
      border: 1px solid rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(10px);
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }
    .capsule:hover {
      background-color: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.2);
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
    }
    .label {
      font-weight: 600;
      background-color: var(--sl-color-primary-500);
      color: white;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      font-size: var(--sl-font-size-x-small);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .text {
      font-weight: 400;
    }
    .arrow {
      color: var(--sl-color-neutral-600);
      transition: transform 0.3s ease;
    }
    .capsule:hover .arrow {
      transform: translateX(3px);
      color: var(--sl-color-neutral-800);
    }
  `;

  render() {
    return html`
      <a href="${this.newsItem.link}" class="capsule">
        <span class="label">${this.newsItem.label}</span>
        <span class="text">${this.newsItem.text}</span>
        <sl-icon name="arrow-right" class="arrow"></sl-icon>
      </a>
    `;
  }
}
