import { css } from 'lit';

/**
 * Shared styles for IDE setup tabs component
 * Extracted from landing.css for reusability
 */
export const ideSetupStyles = css`
  .ide-setup-tabs-container {
    display: flex;
    flex-direction: column;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    overflow: hidden;
    background: var(--gradient-brand);
    color: #fff;
    margin-top: 2rem;
  }

  .global-prereq {
    padding: 1rem 1.5rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(0, 0, 0, 0.15);
  }

  .global-prereq-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .global-prereq strong {
    color: #fff;
    font-size: 0.95rem;
  }

  .prereq-link {
    color: #fff;
    text-decoration: underline;
    font-weight: 600;
    font-size: 0.9rem;
    white-space: nowrap;
  }

  .prereq-link:hover {
    color: rgba(255, 255, 255, 0.8);
  }

  .tabs-wrapper {
    display: flex;
    flex: 1;
  }

  .ide-tabs {
    display: flex;
    flex-direction: column;
    border-right: 1px solid rgba(0, 0, 0, 0.2);
  }

  .ide-logo-container {
    padding: 1rem;
    cursor: pointer;
    transition: background-color 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 80px;
  }

  .ide-logo-container.active {
    background-color: rgba(255, 255, 255, 0.1);
    border-left: 3px solid #fff;
  }

  .ide-logo-container img {
    max-width: 100px;
    opacity: 0.8;
    transition: all 0.2s ease;
  }

  .ide-logo-container.active img {
    opacity: 1;
  }

  .tab-content {
    flex: 1;
    padding: 2rem;
    text-align: left;
  }

  .tab-content h4 {
    margin-top: 1rem;
    font-size: 1.5rem;
    margin-bottom: 1rem;
  }

  .tab-content h5 {
    font-size: 1.1rem;
    font-weight: 600;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
  }

  .code-container {
    position: relative;
    border-radius: 6px;
    margin: 1rem 0;
    background-color: rgba(0, 0, 0, 0.2);
  }

  .code-container pre {
    margin: 0;
    padding: 1rem;
    white-space: pre-wrap;
    word-break: break-all;
    font-family: 'Fira Code', monospace;
    font-size: 0.9rem;
    color: #fff;
  }

  .copy-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    color: #fff;
  }

  .copy-btn:hover {
    background-color: rgba(255, 255, 255, 0.1);
  }

  /* Modal Variant - No gradient, neutral colors */
  .ide-setup-tabs-container.modal-variant {
    background: var(--sl-color-neutral-0);
    border: 1px solid var(--sl-color-neutral-200);
    color: var(--sl-color-neutral-900);
  }

  .modal-variant .ide-tabs {
    border-right: 1px solid var(--sl-color-neutral-200);
  }

  .modal-variant .ide-logo-container img {
    opacity: 0.7;
  }

  .modal-variant .ide-logo-container.active {
    background-color: var(--sl-color-primary-50);
    border-left: 3px solid var(--sl-color-primary-600);
  }

  .modal-variant .ide-logo-container.active img {
    opacity: 1;
  }

  .modal-variant .tab-content {
    color: var(--sl-color-neutral-900);
  }

  .modal-variant .code-container {
    background-color: var(--sl-color-neutral-100);
  }

  .modal-variant .code-container pre {
    color: var(--sl-color-neutral-900);
  }

  .modal-variant .copy-btn {
    color: var(--sl-color-neutral-900);
  }

  /* Responsive Styles */
  @media (max-width: 768px) {
    .ide-setup-tabs-container {
      flex-direction: column;
    }

    .tabs-wrapper {
      flex-direction: column;
    }

    .ide-tabs {
      flex-direction: row;
      border-right: none;
      border-bottom: 1px solid rgba(0, 0, 0, 0.2);
      overflow-x: auto;
    }

    .ide-logo-container {
      flex: 1;
      height: 60px;
      min-width: 60px;
      padding: 0.75rem;
    }

    .ide-logo-container img {
      max-width: 80px;
    }

    .ide-logo-container.active {
      border-left: none;
      border-bottom: 3px solid #fff;
    }

    .tab-content {
      padding: 1.5rem;
    }

    .modal-variant .ide-tabs {
      border-bottom: 1px solid var(--sl-color-neutral-200);
    }

    .modal-variant .ide-logo-container.active {
      border-left: none;
      border-bottom: 3px solid var(--sl-color-primary-600);
    }
  }
`;
