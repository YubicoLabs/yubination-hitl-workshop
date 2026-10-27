import { css } from 'lit';

export const formStyles = css`
  /* Shared Form Styles */

  .logo {
    text-align: center;
    padding: 2rem;
  }

  .logo img {
    max-width: 150px;
  }

  .error-message {
    color: var(--sl-color-danger-700);
    margin-bottom: 1rem;
    text-align: center;
  }

  .form-container {
    max-width: 400px;
    margin: 2rem auto;
    padding: 2rem;
  }

  .form-container h2 {
    text-align: center;
    margin-bottom: 1.5rem;
    color: var(--sl-color-neutral-800);
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-actions {
    margin-top: 2rem;
    text-align: center;
  }

  .form-actions sl-button {
    width: 100%;
  }

  .form-links {
    margin-top: 2rem;
    text-align: center;
    color: var(--sl-color-primary-600);
  }

  .form-links a {
    color: var(--sl-color-primary-600);
    text-decoration: none;
  }

  .form-links a:hover {
    text-decoration: underline;
  }

  sl-alert {
    margin-bottom: 1rem;
  }
`;
