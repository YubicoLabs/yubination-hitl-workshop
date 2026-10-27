import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { Router } from '@vaadin/router';
import { ApiError, getFeatures, post, acceptWebAuthnSession } from '../../api';
import { formStyles } from '../../styles/form-styles';
import { getBrandConfig } from '../../brand-config';
import '@shoelace-style/shoelace/dist/components/input/input.js';
import '@shoelace-style/shoelace/dist/components/button/button.js';
import '@shoelace-style/shoelace/dist/components/icon/icon.js';
import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
import '../../components/logo-component';

const OAUTH_PROVIDER_CONFIG: Record<string, { label: string; icon: string }> = {
  github: { label: 'GitHub', icon: 'github' },
  google: { label: 'Google', icon: 'google' },
  gitlab: { label: 'GitLab', icon: 'gitlab' },
};

const PQ_SIGN_IN_REQUIRED_MESSAGE =
  'Use a post-quantum passkey to sign in. This account requires post-quantum sign-in.';

function loginErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code === 'pq_passkey_required') {
      return PQ_SIGN_IN_REQUIRED_MESSAGE;
    }
    if (error.hasStructuredDetail) return fallback;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

@customElement('login-view')
export class LoginView extends LitElement {
  @state()
  private error = '';

  @state()
  private successMessage = '';

  @state()
  private oauthProviders: string[] = [];

  @state()
  private passkeyAvailable = false;

  @state()
  private passkeyPending = false;

  @state() private pqRequired = false;

  // Set when password auth succeeds but MFA is required; drives the
  // "touch your key" overlay rendered on top of the form.
  @state()
  private mfaState: { sessionId: string; options: Record<string, any> } | null =
    null;

  // AbortController for the background conditional-mediation ceremony so it
  // can be cancelled when the user clicks the explicit "Sign in with passkey"
  // button or triggers the MFA flow via password login.
  private _conditionalAbort: AbortController | null = null;

  static styles = [
    formStyles,
    css`
      .success-message {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
        padding: 0.75rem 1.25rem;
        margin-bottom: 1rem;
        border-radius: 0.25rem;
        text-align: center;
      }

      .oauth-section {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
      }

      .oauth-button {
        width: 100%;
      }

      .oauth-button::part(base) {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
      }

      .divider {
        display: flex;
        align-items: center;
        margin: 1.5rem 0;
        color: var(--sl-color-neutral-500);
        font-size: var(--sl-font-size-small);
      }

      .divider::before,
      .divider::after {
        content: '';
        flex: 1;
        border-bottom: 1px solid var(--sl-color-neutral-300);
      }

      .divider::before {
        margin-right: 0.75rem;
      }

      .divider::after {
        margin-left: 0.75rem;
      }

      .passkey-button {
        width: 100%;
        margin-bottom: 0.75rem;
      }

      .passkey-button::part(base) {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
      }

      .mfa-overlay {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
        padding: 2rem 0;
        text-align: center;
      }

      .mfa-overlay p {
        color: var(--sl-color-neutral-700);
        margin: 0;
      }

      .mfa-overlay .mfa-hint {
        font-size: var(--sl-font-size-small);
        color: var(--sl-color-neutral-500);
      }
    `,
  ];

  connectedCallback() {
    super.connectedCallback();
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('registered')) {
      this.successMessage =
        'Your account has been created successfully. Please sign in.';
      const url = new URL(window.location.href);
      url.searchParams.delete('registered');
      window.history.replaceState({}, document.title, url.pathname);
    }
    this._checkFeatures();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._conditionalAbort?.abort();
  }

  // ---------------------------------------------------------------------------
  // Base64url helpers (same as approval-view)
  // ---------------------------------------------------------------------------

  private _fromBase64Url(b64url: string): Uint8Array {
    const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/');
    const pad = '='.repeat((4 - (b64.length % 4)) % 4);
    return Uint8Array.from(atob(b64 + pad), (c) => c.charCodeAt(0));
  }

  private _toBase64Url(buf: ArrayBuffer): string {
    return btoa(String.fromCharCode(...new Uint8Array(buf)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
  }

  // ---------------------------------------------------------------------------
  // WebAuthn helpers
  // ---------------------------------------------------------------------------

  private _buildPublicKeyOptions(
    options: Record<string, any>
  ): PublicKeyCredentialRequestOptions {
    const pkOpts: PublicKeyCredentialRequestOptions = {
      challenge: this._fromBase64Url(
        options.challenge
      ) as unknown as BufferSource,
      rpId: options.rpId,
      userVerification: (options.userVerification ||
        'required') as UserVerificationRequirement,
      timeout: options.timeout || 60000,
    };
    if (options.allowCredentials?.length) {
      pkOpts.allowCredentials = options.allowCredentials.map((c: any) => ({
        type: 'public-key' as PublicKeyCredentialType,
        id: this._fromBase64Url(c.id),
      }));
    }
    return pkOpts;
  }

  private async _completeWebAuthnLogin(
    sessionId: string,
    credential: PublicKeyCredential
  ): Promise<void> {
    const authResp = credential.response as AuthenticatorAssertionResponse;
    const body = {
      session_id: sessionId,
      response: {
        id: this._toBase64Url(credential.rawId),
        rawId: this._toBase64Url(credential.rawId),
        type: credential.type,
        response: {
          clientDataJSON: this._toBase64Url(authResp.clientDataJSON),
          authenticatorData: this._toBase64Url(authResp.authenticatorData),
          signature: this._toBase64Url(authResp.signature),
          userHandle: authResp.userHandle
            ? this._toBase64Url(authResp.userHandle)
            : null,
        },
      },
    };

    const data = await post('/api/v1/webauthn/login/complete', body);
    acceptWebAuthnSession(data);
    this.error = '';
    this.mfaState = null;
    const redirectPath = localStorage.getItem('loginRedirect');
    if (redirectPath) {
      localStorage.removeItem('loginRedirect');
      Router.go(redirectPath);
    } else {
      Router.go('/console');
    }
  }

  // Background conditional-mediation ceremony: browser autofill passkey picker.
  // Resolves silently; never shows an error to the user on abort/cancel.
  private async _startConditionalFlow(): Promise<void> {
    this._conditionalAbort?.abort();
    this._conditionalAbort = new AbortController();
    try {
      const beginData = await post('/api/v1/webauthn/login/begin', {});
      const { session_id, options } = beginData;
      const pkOpts = this._buildPublicKeyOptions(options);

      const credential = (await navigator.credentials.get({
        mediation: 'conditional' as CredentialMediationRequirement,
        publicKey: pkOpts,
        signal: this._conditionalAbort.signal,
      } as CredentialRequestOptions)) as PublicKeyCredential | null;

      if (!credential) return;
      await this._completeWebAuthnLogin(session_id, credential);
    } catch (error) {
      if (
        error instanceof Error &&
        !['AbortError', 'NotAllowedError'].includes(error.name)
      )
        this.error = loginErrorMessage(
          error,
          'Passkey sign-in failed. Try again.'
        );
    }
  }

  // MFA flow: triggered when password login returns HTTP 202.
  private async _doMfaCeremony(
    sessionId: string,
    options: Record<string, any>,
    pqRequired = false
  ): Promise<void> {
    this._conditionalAbort?.abort();
    this.pqRequired = pqRequired;
    this.mfaState = { sessionId, options };
    this.passkeyPending = true;
    try {
      const pkOpts = this._buildPublicKeyOptions(options);
      const credential = (await navigator.credentials.get({
        publicKey: pkOpts,
        mediation: 'required' as CredentialMediationRequirement,
      } as CredentialRequestOptions)) as PublicKeyCredential;

      await this._completeWebAuthnLogin(sessionId, credential);
    } catch (err) {
      this.mfaState = null;
      if (err instanceof Error) {
        this.error =
          err.name === 'NotAllowedError'
            ? 'Security key verification was cancelled.'
            : loginErrorMessage(err, 'Passkey verification failed. Try again.');
      }
    } finally {
      this.passkeyPending = false;
    }
  }

  // Explicit "Sign in with passkey" button handler.
  private async _signInWithPasskey(): Promise<void> {
    this._conditionalAbort?.abort();
    this.passkeyPending = true;
    this.error = '';
    try {
      const usernameInput = this.shadowRoot?.querySelector(
        'sl-input[name="username"]'
      ) as any;
      const username: string = usernameInput?.value?.trim() ?? '';

      const beginData = await post(
        '/api/v1/webauthn/login/begin',
        username ? { username } : {}
      );
      const { session_id, options } = beginData;
      const pkOpts = this._buildPublicKeyOptions(options);

      const credential = (await navigator.credentials.get({
        publicKey: pkOpts,
        mediation: 'required' as CredentialMediationRequirement,
      } as CredentialRequestOptions)) as PublicKeyCredential;

      await this._completeWebAuthnLogin(session_id, credential);
    } catch (err) {
      if (err instanceof Error) {
        this.error =
          err.name === 'NotAllowedError'
            ? 'Sign in with passkey was cancelled.'
            : loginErrorMessage(err, 'Passkey sign-in failed. Try again.');
      }
    } finally {
      this.passkeyPending = false;
    }
  }

  private async _checkFeatures() {
    try {
      const features = await getFeatures();
      const providers = features.features['oauth_providers'];
      this.oauthProviders = Array.isArray(providers) ? providers : [];

      const webauthnLoginEnabled = features.features['webauthn_login'] === true;
      if (
        webauthnLoginEnabled &&
        window.isSecureContext &&
        typeof window.PublicKeyCredential !== 'undefined'
      ) {
        this.passkeyAvailable = true;
        // Start conditional mediation (browser autofill passkey picker) if supported.
        const conditionalAvailable = await (PublicKeyCredential as any)
          .isConditionalMediationAvailable?.()
          .catch(() => false);
        if (conditionalAvailable) {
          this._startConditionalFlow().catch(() => {});
        }
      }
    } catch {
      this.oauthProviders = [];
    }
  }

  private async handleLogin(event: SubmitEvent) {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const formData = new FormData(form);
    const username = formData.get('username') as string;
    const password = formData.get('password') as string;

    try {
      const data = await post('/api/v1/auth/token/json', {
        username,
        password,
      });

      // HTTP 202: user has WebAuthn credentials, MFA step-up required
      if (data.mfa_required && data.webauthn_session_id) {
        await this._doMfaCeremony(
          data.webauthn_session_id,
          data.options,
          data.pq_required === true
        );
        return;
      }

      localStorage.setItem('accessToken', data.access_token);
      if (data.refresh_token) {
        localStorage.setItem('refreshToken', data.refresh_token);
      }
      this.error = '';
      this.successMessage = '';
      window.dispatchEvent(
        new CustomEvent('auth-change', { bubbles: true, composed: true })
      );
      const redirectPath = localStorage.getItem('loginRedirect');
      if (redirectPath) {
        localStorage.removeItem('loginRedirect');
        Router.go(redirectPath);
      } else {
        Router.go('/console');
      }
    } catch (error) {
      this.error = loginErrorMessage(error, 'Sign in failed. Try again.');
      console.error('Sign in failed', error);
    }
  }

  private _renderOAuthButtons() {
    if (this.oauthProviders.length === 0) return nothing;

    return html`
      <div class="oauth-section">
        ${this.oauthProviders.map((provider) => {
          const config = OAUTH_PROVIDER_CONFIG[provider];
          if (!config) return nothing;
          return html`
            <sl-button
              class="oauth-button"
              variant="default"
              size="large"
              @click=${() => {
                window.location.href = `/api/v1/auth/oauth/${provider}/authorize`;
              }}
            >
              <sl-icon name="${config.icon}" slot="prefix"></sl-icon>
              Sign in with ${config.label}
            </sl-button>
          `;
        })}
      </div>
      <div class="divider">or sign in with email</div>
    `;
  }

  private _renderPasskeyButton() {
    if (!this.passkeyAvailable) return nothing;
    return html`
      <sl-button
        class="passkey-button"
        variant="default"
        size="large"
        ?disabled=${this.passkeyPending}
        @click=${this._signInWithPasskey}
      >
        ${this.passkeyPending
          ? html`<sl-spinner slot="prefix"></sl-spinner>`
          : html`<sl-icon name="key" slot="prefix"></sl-icon>`}
        Sign in with passkey
      </sl-button>
      <div class="divider">or sign in with password</div>
    `;
  }

  private _renderMfaOverlay() {
    if (!this.mfaState) return nothing;
    return html`
      <div class="mfa-overlay">
        <sl-spinner style="font-size: 2rem;"></sl-spinner>
        <p>
          ${this.pqRequired
            ? 'Use a post-quantum passkey to complete sign-in'
            : 'Use your passkey to complete sign-in'}
        </p>
        <p class="mfa-hint">
          Follow your browser’s prompt. For a security key, insert it and touch
          it when it flashes.
        </p>
      </div>
    `;
  }

  render() {
    return html`
      <div class="container">
        <div class="logo">
          <a href="/">
            <logo-component></logo-component>
          </a>
        </div>
        <div class="form-container">
          <h2>
            ${getBrandConfig().workshop
              ? 'Sign into workshop'
              : `Sign in to ${getBrandConfig().name}`}
          </h2>
          ${this.successMessage
            ? html`<div class="success-message">${this.successMessage}</div>`
            : ''}
          ${this.error
            ? html`<div class="error-message">${this.error}</div>`
            : ''}
          ${this._renderOAuthButtons()} ${this._renderPasskeyButton()}
          ${this.mfaState
            ? this._renderMfaOverlay()
            : html`
                <form @submit=${this.handleLogin}>
                  <div class="form-group">
                    <sl-input
                      label="Username"
                      id="username"
                      name="username"
                      autocomplete="username webauthn"
                      required
                    ></sl-input>
                  </div>
                  <div class="form-group">
                    <sl-input
                      type="password"
                      label="Password"
                      id="password"
                      name="password"
                      required
                      password-toggle
                    ></sl-input>
                  </div>
                  <div class="form-actions">
                    <sl-button
                      type="submit"
                      variant="primary"
                      style="width: 100%;"
                      >Sign in</sl-button
                    >
                  </div>
                  <div class="form-links">
                    <a href="/forgot-password">Forgot Password?</a> &middot;
                    <a href="/register">Create Account</a>
                  </div>
                </form>
              `}
        </div>
      </div>
    `;
  }
}
