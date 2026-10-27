import {
  shortCredentialId,
  workshopAlgorithm,
} from '../../utils/workshop-credential';
import {
  parseWorkshopArtifact,
  type WorkshopArtifact,
  type WorkshopPlatform,
} from '../../utils/workshop-artifact';
import { LitElement, css, html } from 'lit';
import '@shoelace-style/shoelace/dist/components/copy-button/copy-button.js';
import '@shoelace-style/shoelace/dist/components/icon/icon.js';
import '@shoelace-style/shoelace/dist/components/tab-group/tab-group.js';
import '@shoelace-style/shoelace/dist/components/tab/tab.js';
import '@shoelace-style/shoelace/dist/components/tab-panel/tab-panel.js';
import { customElement, property, state } from 'lit/decorators.js';
import '../../components/mcp-setup-dialog';
import '../../components/workshop-receipt-auditor';
import '../../components/security-keys-manager';
import type { SecurityKeysManager } from '../../components/security-keys-manager';
import { fetchWithAuth, acceptWebAuthnSession, getFeatures } from '../../api';
import type { WebAuthnCredential } from '../../api';
import {
  renderWorkshopEvidence,
  workshopEvidenceStyles,
} from './workshop-evidence';
import {
  PREVIEWSIGN_CHROME_EXTENSION_ID,
  PREVIEWSIGN_MACOS_NATIVE_HOST,
  PREVIEWSIGN_WINDOWS_NATIVE_HOST,
} from '../../generated/previewsign-installation';

@customElement('workshop-lab-view')
export class WorkshopLabView extends LitElement {
  @state() private previewSignPlatform: 'mac' | 'windows' | 'source' =
    /^Win/i.test(navigator.platform)
      ? 'windows'
      : /^Mac/i.test(navigator.platform)
        ? 'mac'
        : 'source';

  static styles = [
    workshopEvidenceStyles,
    css`
      :host {
        display: block;
        box-sizing: border-box;
        width: 100%;
        min-width: 0;
        max-width: 52rem;
        margin: auto;
        padding: 1.5rem;
        line-height: 1.6;
        overflow-wrap: anywhere;
      }
      pre {
        max-width: 100%;
        overflow-x: auto;
        overflow-wrap: normal;
      }
      .command-block {
        position: relative;
        min-width: 0;
        padding-top: 2.5rem;
      }
      .command-block sl-copy-button {
        position: absolute;
        top: 0;
        right: 0;
      }
      .command-block pre {
        margin: 0;
        padding: 0.5rem;
      }
      a {
        color: var(--sl-color-primary-700, #005a9c);
      }
      a:focus-visible {
        outline: 3px solid currentColor;
        outline-offset: 3px;
      }
      section {
        margin-block: 2rem;
      }
      .exclusion-comparison {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
        gap: 1rem;
      }
      .exclusion-comparison section {
        min-width: 0;
      }
      .exclusion-comparison code {
        overflow-wrap: anywhere;
      }
      .exclusion-comparison del {
        text-decoration-thickness: 2px;
      }
      .migration-steps {
        list-style: none;
        padding: 0;
        display: grid;
        gap: 1rem;
      }
      .chrome-setup figure,
      figure[data-chrome-step] {
        margin: 1rem 0;
      }
      figure[data-chrome-step] img {
        display: block;
        max-width: 100%;
        height: auto;
        border: 1px solid var(--sl-color-neutral-300);
      }
      figure[data-chrome-step] figcaption {
        font-size: 0.9rem;
      }
      .chrome-setup {
        display: grid;
        gap: 0.75rem;
        padding-inline-start: 1.5rem;
      }
      .chrome-setup li {
        border-inline-start: 3px solid currentColor;
        padding-inline-start: 0.75rem;
      }
      .migration-steps li,
      .existing-passkeys,
      .ceremony-card {
        border: 1px solid var(--sl-color-neutral-200, #dce1e7);
        border-radius: 12px;
        padding: 1.25rem;
        background: var(--sl-color-neutral-0, white);
      }
      .migration-steps h3 {
        margin: 0 0 0.5rem;
        font-size: 1.05rem;
      }
      .migration-steps p {
        margin: 0 0 1rem;
      }
      button,
      select {
        font: inherit;
        min-height: 44px;
        border-radius: 8px;
        box-sizing: border-box;
        max-width: 100%;
      }
      button {
        padding: 0.65rem 1rem;
        border: 1px solid var(--sl-color-primary-600, #0068b5);
        background: var(--sl-color-primary-600, #0068b5);
        color: white;
        cursor: pointer;
      }
      button:disabled {
        background: var(--sl-color-neutral-100, #f1f3f5);
        border-color: var(--sl-color-neutral-300, #dce1e7);
        color: var(--sl-color-neutral-600, #59636e);
        cursor: not-allowed;
      }
      button:focus-visible,
      select:focus-visible,
      summary:focus-visible {
        outline: 3px solid var(--sl-color-primary-500, #0089dd);
        outline-offset: 3px;
      }
      label {
        display: grid;
        gap: 0.4rem;
        margin: 1rem 0;
        font-weight: 600;
      }
      select {
        width: 100%;
        padding: 0.6rem;
        background: var(--sl-color-neutral-0, white);
        color: inherit;
        border: 1px solid var(--sl-color-neutral-400, #aab2bc);
      }
      summary {
        min-height: 44px;
        box-sizing: border-box;
        padding: 0.65rem 0;
        cursor: pointer;
        font-weight: 600;
      }
      pre {
        padding: 1rem;
        border-radius: 8px;
        background: var(--sl-color-neutral-50, #f6f8fa);
        font-size: 0.85rem;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }
      [role='alert'] {
        padding: 1rem;
        border-left: 4px solid var(--sl-color-danger-600, #bd2525);
        background: var(--sl-color-danger-50, #fff2f2);
      }
      @media (max-width: 600px) {
        :host {
          padding: 1rem;
        }
        button {
          width: 100%;
        }
        .migration-steps li {
          padding: 1rem;
        }
      }
    `,
  ];
  @property() lab = 'agent-setup';
  @property({ state: true }) private showClientSetup = false;
  @property({ state: true }) private inventory: WebAuthnCredential[] = [];
  @property({ state: true }) private sourceId = '';
  @property({ state: true }) private pqId = '';
  @property({ state: true }) private busy = false;
  @property({ state: true }) private lifecycleBusy = true;
  @property({ state: true }) private selectedCredentialId = '';
  @property({ state: true }) private outcome = '';
  @property({ state: true }) private ceremonyError = '';
  @property({ state: true }) private migrationAvailable = false;
  @property({ state: true }) private pqOnly = false;
  @property({ state: true }) private availability =
    'Sign in and refresh to check workshop availability.';
  private stage = 'Not started';
  @property({ state: true }) private explorer: {
    action: string;
    kind: 'registration' | 'sign-in' | 'readiness';
    acceptance: 'unconfirmed' | 'accepted';
    replacement: boolean;
    request: string;
    response: string;
    checks: string;
  }[] = [];
  private enrolledPqCredentialId = '';
  private latestRegistration?: {
    begin: any;
    targetAlgorithm: number;
    replacement: boolean;
  };
  private replacementSource?: WebAuthnCredential;
  private targetedSigninId = '';
  private runAbort?: AbortController;
  private focusedStage = 'Not started';

  protected updated(): void {
    const panel = this.shadowRoot?.querySelector<HTMLElement>('#guided-stage');
    if (!panel || this.focusedStage === this.stage) return;
    this.focusedStage = this.stage;
    const selectedRow = this.selectedCredentialId
      ? this.passkeyManager?.shadowRoot?.querySelector<HTMLElement>(
          `[data-credential-id="${CSS.escape(this.selectedCredentialId)}"]`
        )
      : null;
    const target = selectedRow ?? panel;
    target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
    target.scrollIntoView({
      block: selectedRow ? 'start' : 'nearest',
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'auto'
        : 'smooth',
    });
  }

  @state() private sourceRepository = '';
  @state() private sourceLoaded = false;
  @state() private participantArtifact: WorkshopArtifact | null = null;
  @state() private artifactLoaded = false;
  @state() private windowsArtifact: WorkshopArtifact | null = null;

  private async loadParticipantArtifact(
    platform: WorkshopPlatform = 'macos-arm64'
  ) {
    try {
      const response = await fetch(`/previewsign/${platform}/manifest.json`, {
        redirect: 'error',
      });
      if (
        !response.ok ||
        response.headers.get('content-type')?.split(';')[0].trim() !==
          'application/json'
      )
        return;
      const accepted = parseWorkshopArtifact(
        await response.json(),
        platform,
        new URL(location.href)
      );
      if (platform === 'windows-x64') this.windowsArtifact = accepted;
      else this.participantArtifact = accepted;
    } catch {
      return;
    }
  }

  private sourceLink(path: string, label: string) {
    return this.sourceRepository
      ? html`<a href=${`${this.sourceRepository}/${path}`}>${label}</a>`
      : html`<span>${label} (source unavailable)</span>`;
  }

  private get previewSignSourceRef(): string {
    return (
      this.participantArtifact?.sourceRevision ??
      this.windowsArtifact?.sourceRevision ??
      'main'
    );
  }

  protected firstUpdated(): void {
    if (this.lab === 'previewsign') {
      void Promise.all([
        this.loadParticipantArtifact(),
        this.loadParticipantArtifact('windows-x64'),
      ]).finally(() => {
        this.artifactLoaded = true;
      });
    }
    void Promise.all([
      getFeatures().catch(() => null),
      fetch('/workshop/source.json', { redirect: 'error' })
        .then(async (response) =>
          response.ok &&
          response.headers.get('content-type')?.split(';')[0].trim() ===
            'application/json'
            ? response.json()
            : null
        )
        .catch(() => null),
    ])
      .then(([result, publicConfig]) => {
        const value =
          publicConfig?.source_repository_url ??
          result?.workshop?.source_repository_url ??
          '';
        if (
          /^https:\/\/github\.com\/[A-Za-z0-9_-]+\/[A-Za-z0-9_.-]+$/.test(
            value
          ) &&
          !['.', '..'].includes(value.split('/').pop()!)
        ) {
          this.sourceRepository = value;
        }
      })
      .catch(() => {
        this.sourceRepository = '';
      })
      .finally(() => {
        this.sourceLoaded = true;
      });
    if (
      this.lab === 'python-fido2-ml-dsa' &&
      localStorage.getItem('accessToken')
    ) {
      this.sourceId =
        new URLSearchParams(window.location.search).get('source') ?? '';
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.runAbort?.abort();
    this.explorer = [];
  }

  private async refreshInventory(): Promise<void> {
    if (this.busy || this.lifecycleBusy || this.passkeyManager?.lifecycleBusy)
      return;
    await this.passkeyManager?.refresh();
  }

  private get passkeyManager(): SecurityKeysManager | null {
    return (
      this.shadowRoot?.querySelector<SecurityKeysManager>(
        'security-keys-manager'
      ) ?? null
    );
  }

  private inventoryChanged(event: CustomEvent): void {
    if (event.composedPath()[0] !== this.passkeyManager) return;
    this.inventory = event.detail.credentials.map(
      (credential: WebAuthnCredential) => ({ ...credential })
    );
    this.migrationAvailable = event.detail.available === true;
    this.pqOnly = event.detail.pqOnly === true;
    this.availability = this.migrationAvailable
      ? 'Workshop migration is available. Use the supplied beta key.'
      : 'Workshop migration is unavailable: deployment, PQ-only protection or inventory/policy loading prevents this exercise. Review Account security; no policy has been changed.';
    if (!this.inventory.some((credential) => credential.id === this.sourceId))
      this.sourceId = '';
    if (this.sourceId && !this.selectedCredentialId)
      this.selectedCredentialId = this.sourceId;
    if (!this.inventory.some((credential) => credential.id === this.pqId))
      this.pqId = '';
    if (
      this.selectedCredentialId &&
      !this.inventory.some(
        (credential) => credential.id === this.selectedCredentialId
      )
    ) {
      this.selectedCredentialId = '';
      this.explorer = [];
      this.outcome = '';
      this.ceremonyError = '';
      this.enrolledPqCredentialId = '';
    }
  }

  private rowAction(event: CustomEvent): void {
    if (
      event.composedPath()[0] !== this.passkeyManager ||
      this.busy ||
      this.lifecycleBusy ||
      this.passkeyManager?.lifecycleBusy ||
      !this.migrationAvailable
    )
      return;
    const { credentialId, action } = event.detail;
    const credential = this.inventory.find((item) => item.id === credentialId);
    if (!credential || ![-7, -48].includes(credential.cose_algorithm ?? 0))
      return;
    if (action === 'identify' && credential.discoverable == null) {
      void this.identifyExistingPasskey();
      return;
    }
    if (!['replace', 'signin'].includes(action)) return;
    if (action === 'signin' && credentialId !== this.targetedSigninId) return;
    if (this.selectedCredentialId !== credentialId) this.explorer = [];
    this.selectedCredentialId = credentialId;
    if (action === 'replace') {
      this.sourceId = credentialId;
      this.replacementSource = undefined;
      this.targetedSigninId = '';
      this.latestRegistration = undefined;
      this.outcome = '';
      this.ceremonyError = '';
      this.stage = 'Preparing replacement';
      this.requestUpdate();
      void this.runMigration(
        credential.cose_algorithm === -48 ? 'downgrade' : 'upgrade'
      );
      return;
    }
    void this.runMigration(
      credential.cose_algorithm === -7 ? 'classical' : 'pq'
    );
  }

  private async ceremonyPost(path: string, body: unknown): Promise<any> {
    const stages: Record<string, string> = {
      'register/begin': 'Preparing registration',
      'register/complete': 'Saving the new passkey',
      'migration/signin/begin': 'Preparing sign-in',
      'login/complete': 'Verifying sign-in',
    };
    this.stage = stages[path] ?? 'Contacting the site';
    const response = await fetchWithAuth(`/api/v1/webauthn/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: this.runAbort?.signal,
    });
    if (!response.ok) {
      const error = new Error('RP rejected this ceremony');
      error.name = path.endsWith('/complete')
        ? 'ServerVerificationError'
        : 'ServerRequestError';
      throw error;
    }
    return response.json();
  }

  private decode(value: string): Uint8Array<ArrayBuffer> {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(
      atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')),
      (character) => character.charCodeAt(0)
    );
  }

  private encode(value: ArrayBuffer): string {
    return btoa(String.fromCharCode(...new Uint8Array(value)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
  }

  private async browserCeremony(
    begin: any,
    kind: 'registration' | 'sign-in' | 'readiness',
    action: string,
    replacement = false
  ): Promise<Record<string, unknown>> {
    const creation = kind === 'registration';
    this.stage = `Browser ${action}`;
    const options = begin.options;
    const entry: (typeof this.explorer)[number] = {
      action,
      kind,
      acceptance: 'unconfirmed',
      replacement,
      request: JSON.stringify(
        {
          rp: options.rp ?? { id: options.rpId },
          user: options.user
            ? { id: `${options.user.id.slice(0, 8)}…` }
            : undefined,
          pubKeyCredParams: options.pubKeyCredParams,
          authenticatorSelection: options.authenticatorSelection,
          extensions:
            options.extensions?.credProps === true
              ? { credProps: true }
              : undefined,
          excludeCredentials: options.excludeCredentials?.map((item: any) => ({
            type: item.type,
            id: `${item.id.slice(0, 8)}…`,
          })),
          allowCredentials: options.allowCredentials?.map((item: any) => ({
            type: item.type,
            id: `${item.id.slice(0, 8)}…`,
          })),
          userVerification:
            options.userVerification ??
            options.authenticatorSelection?.userVerification,
          challenge: 'Fresh server challenge (not retained)',
        },
        null,
        2
      ),
      response: 'No browser response yet',
      checks: 'Server acceptance not confirmed',
    };
    this.explorer = [...this.explorer, entry];
    const publicKey = {
      ...options,
      timeout: options.timeout ?? 60000,
      challenge: this.decode(options.challenge),
    };
    if (creation) {
      publicKey.user = { ...options.user, id: this.decode(options.user.id) };
      publicKey.excludeCredentials = options.excludeCredentials.map(
        (item: any) => ({ ...item, id: this.decode(item.id) })
      );
    } else {
      publicKey.allowCredentials = options.allowCredentials?.map(
        (item: any) => ({ ...item, id: this.decode(item.id) })
      );
    }
    const credential = (
      creation
        ? await navigator.credentials.create({
            publicKey,
            signal: this.runAbort?.signal,
          })
        : await navigator.credentials.get({
            publicKey,
            signal: this.runAbort?.signal,
          })
    ) as PublicKeyCredential | null;
    if (!credential) throw new Error('No browser response');
    const response = credential.response;
    const serialized: Record<string, unknown> = {
      clientDataJSON: this.encode(response.clientDataJSON),
    };
    if (creation) {
      serialized.attestationObject = this.encode(
        (response as AuthenticatorAttestationResponse).attestationObject
      );
    } else {
      const assertion = response as AuthenticatorAssertionResponse;
      serialized.authenticatorData = this.encode(assertion.authenticatorData);
      serialized.signature = this.encode(assertion.signature);
      serialized.userHandle = assertion.userHandle
        ? this.encode(assertion.userHandle)
        : null;
    }
    const clientData = JSON.parse(
      new TextDecoder().decode(response.clientDataJSON)
    );
    const shortText = (value: unknown): string | undefined =>
      typeof value === 'string' ? value.slice(0, 160) : undefined;
    const binarySummary = (value: ArrayBuffer) => ({
      byteLength: value.byteLength,
      base64urlPrefix: `${this.encode(value.slice(0, 9))}…`,
    });
    const extensionResults = credential.getClientExtensionResults();
    const attestation = response as AuthenticatorAttestationResponse;
    const assertion = response as AuthenticatorAssertionResponse;
    const authData = creation
      ? attestation.getAuthenticatorData?.()
      : assertion.authenticatorData;
    entry.response = JSON.stringify(
      {
        type: credential.type,
        credential: `${credential.id.slice(0, 8)}…`,
        clientData: {
          type: shortText(clientData.type),
          origin: shortText(clientData.origin),
          crossOrigin:
            typeof clientData.crossOrigin === 'boolean'
              ? clientData.crossOrigin
              : 'absent',
          challenge:
            typeof clientData.challenge === 'string'
              ? `${clientData.challenge.slice(0, 8)}…`
              : 'absent',
        },
        attestationObject: creation
          ? binarySummary(attestation.attestationObject)
          : undefined,
        authenticatorData: authData
          ? binarySummary(authData)
          : 'Browser did not expose decoded authenticator data',
        signature: creation ? undefined : binarySummary(assertion.signature),
        extensions: {
          credProps:
            typeof extensionResults.credProps?.rk === 'boolean'
              ? { rk: extensionResults.credProps.rk }
              : undefined,
          appid:
            typeof extensionResults.appid === 'boolean'
              ? extensionResults.appid
              : undefined,
          otherValues:
            'Omitted for privacy; extension outputs are not proof of RP acceptance',
        },
        browserResponse: 'Received; not yet RP verified',
      },
      null,
      2
    );
    this.explorer = [...this.explorer];
    return {
      id: credential.id,
      rawId: this.encode(credential.rawId),
      type: credential.type,
      response: serialized,
      clientExtensionResults: extensionResults,
    };
  }

  private verified(message: string): void {
    this.explorer[this.explorer.length - 1].acceptance = 'accepted';
    this.explorer[this.explorer.length - 1].checks = message;
    this.explorer = [...this.explorer];
  }

  private async identifyExistingPasskey(): Promise<void> {
    if (this.busy || this.lifecycleBusy || !this.migrationAvailable) return;
    this.busy = true;
    if (this.passkeyManager) this.passkeyManager.externalBusy = true;
    this.ceremonyError = '';
    this.runAbort = new AbortController();
    try {
      const begin = await this.ceremonyPost('migration/identify/begin', {});
      const response = await this.browserCeremony(
        begin,
        'readiness',
        'Identify an existing passkey'
      );
      const result = await this.ceremonyPost('migration/identify/complete', {
        session_id: begin.session_id,
        response,
      });
      if (
        result.discoverable !== true ||
        typeof result.credential_record_id !== 'string'
      )
        throw new Error('Incomplete readiness result');
      this.verified(
        'The RP verified the assertion and recorded browser-observed discoverability for the returned credential. No sign-in session or account policy changed.'
      );
      await this.passkeyManager?.refresh();
      await this.passkeyManager?.updateComplete;
      const returned = this.inventory.find(
        (item) =>
          item.id === result.credential_record_id && item.discoverable === true
      );
      if (!returned) throw new Error('Inventory did not confirm readiness');
      this.selectedCredentialId = returned.id;
      this.sourceId = returned.id;
      this.outcome = `Discoverability observed for credential ${returned.credential_id ?? result.credential_id}. Choose its upgrade or preparation action.`;
      this.stage = 'Ready to choose an action';
    } catch {
      this.ceremonyError =
        'Identification not completed. No upgrade eligibility was confirmed. Try again with a passkey registered to this account.';
    } finally {
      this.busy = false;
      if (this.passkeyManager) this.passkeyManager.externalBusy = false;
    }
  }

  private async runMigration(
    action: 'create' | 'classical' | 'upgrade' | 'downgrade' | 'pq'
  ): Promise<void> {
    if (
      !this.migrationAvailable ||
      this.busy ||
      this.lifecycleBusy ||
      this.passkeyManager?.lifecycleBusy
    )
      return;
    const credentialId = this.selectedCredentialId;
    this.busy = true;
    if (this.passkeyManager) this.passkeyManager.externalBusy = true;
    if (action !== 'classical' && action !== 'pq') {
      this.outcome = '';
      this.targetedSigninId = '';
      this.replacementSource = undefined;
      this.latestRegistration = undefined;
    }
    this.ceremonyError = '';
    this.runAbort = new AbortController();
    let creationAttempted = false;
    try {
      if (
        action === 'create' ||
        action === 'upgrade' ||
        action === 'downgrade'
      ) {
        this.enrolledPqCredentialId = '';
        const targetAlgorithm = action === 'upgrade' ? -48 : -7;
        const begin = await this.ceremonyPost('register/begin', {
          algorithm: targetAlgorithm === -7 ? 'es256' : 'mldsa44',
          replacement_source_id:
            action === 'upgrade' || action === 'downgrade'
              ? credentialId
              : undefined,
        });
        this.latestRegistration = {
          begin,
          targetAlgorithm,
          replacement: action !== 'create',
        };
        await this.completeRegistration(this.latestRegistration, () => {
          creationAttempted = true;
        });
      } else {
        const begin = await this.ceremonyPost('migration/signin/begin', {
          credential_id: credentialId,
        });
        const response = await this.browserCeremony(
          begin,
          'sign-in',
          action === 'classical'
            ? 'Sign in with classical passkey'
            : 'Sign in with post-quantum passkey'
        );
        const tokens = await this.ceremonyPost('login/complete', {
          session_id: begin.session_id,
          response,
        });
        acceptWebAuthnSession(tokens);
        this.verified(
          'RP verified the selected credential signature, RP/origin, user verification, owner and current key binding. Real sign-in succeeded.'
        );
        this.outcome = 'Sign-in verified';
        this.stage = 'Sign-in verified';
      }
    } catch (error) {
      const name =
        error instanceof Error || error instanceof DOMException
          ? error.name
          : '';
      const reason =
        name === 'NotAllowedError'
          ? 'Browser cancellation or timeout; the browser does not distinguish the cause.'
          : name === 'NotSupportedError'
            ? 'The browser or authenticator does not support this ceremony.'
            : name === 'ServerVerificationError'
              ? creationAttempted
                ? 'Registration outcome could not be confirmed; server verification failed.'
                : 'Server verification failed; no verified success.'
              : name === 'ServerRequestError'
                ? 'The server did not authorize this request.'
                : name === 'RegistrationContextError'
                  ? 'The RP did not return a complete migration context; registration was not opened.'
                  : 'The ceremony was interrupted or its response could not be processed; no verified success.';
      this.ceremonyError = `Incomplete — ${this.stage}: ${reason} ${
        creationAttempted
          ? 'The authenticator may already have replaced the source even without a saved server response. Refresh inventory, retry, and use your independent recovery path on this account. Recreate this disposable lab account only if access is actually lost.'
          : 'Refresh inventory to check the result before retrying on this account; use your independent recovery path if needed.'
      }`;
      if (action === 'classical' || action === 'pq') {
        this.ceremonyError = `Optional sign-in not verified. ${reason} Registration remains accepted; retry or proceed without sign-in.`;
        this.outcome = this.replacementSource
          ? 'Replacement registered'
          : 'Passkey registered';
        this.stage = this.replacementSource
          ? 'Replacement registered'
          : 'Passkey registered';
      }
    } finally {
      this.busy = false;
      if (this.passkeyManager) this.passkeyManager.externalBusy = false;
    }
  }

  private async completeRegistration(
    registration: NonNullable<WorkshopLabView['latestRegistration']>,
    markCreationAttempted: () => void
  ): Promise<void> {
    const pending = registration;
    const context = pending.begin.migration_context;
    const options = pending.begin.options;
    if (
      (this.sourceId &&
        (!context ||
          typeof context.source_record_id !== 'string' ||
          typeof context.source_credential_id !== 'string' ||
          !Array.isArray(context.exclude_credentials_before))) ||
      !Array.isArray(options?.excludeCredentials) ||
      !Array.isArray(options?.pubKeyCredParams)
    ) {
      this.ceremonyError =
        'Incomplete — the RP did not return a complete migration context. Registration was not opened; refresh and retry.';
      const error = new Error(this.ceremonyError);
      error.name = 'RegistrationContextError';
      throw error;
    }
    markCreationAttempted();
    const response = await this.browserCeremony(
      pending.begin,
      'registration',
      pending.targetAlgorithm === -7
        ? 'Prepare a classical passkey'
        : 'Upgrade to post-quantum',
      pending.replacement
    );
    const record = (await this.ceremonyPost('register/complete', {
      session_id: pending.begin.session_id,
      response,
      name:
        pending.targetAlgorithm === -7
          ? 'Workshop classical'
          : 'Workshop post-quantum',
    })) as WebAuthnCredential;
    this.verified(
      `RP accepted the ${pending.replacement ? 'replacement' : 'initial registration'} with algorithm ${record.cose_algorithm}; targeted sign-in is optional and separately verified.`
    );
    this.replacementSource = this.inventory.find(
      (item) => item.id === record.replaced_credential_id
    );
    this.selectedCredentialId = record.id;
    this.sourceId = record.id;
    this.targetedSigninId = record.id;
    if (record.cose_algorithm === -48) {
      this.pqId = record.id;
      this.enrolledPqCredentialId = record.id;
    }
    this.outcome = this.replacementSource
      ? 'Replacement registered'
      : 'Passkey registered';
    await this.passkeyManager?.refresh();
    await this.passkeyManager?.updateComplete;
    await this.updateComplete;
    this.stage = this.replacementSource
      ? 'Replacement registered'
      : 'Passkey registered';
    this.requestUpdate();
  }

  private chromeScreenshot(step: string, alt: string, caption: string) {
    const src = `/workshop/previewsign/chrome-${step}.png`;
    return html`<figure data-chrome-step=${step}>
      <a
        href=${src}
        target="_blank"
        rel="noopener"
        aria-label=${`Open full-size image: ${alt}`}
        ><img src=${src} alt=${alt} loading="lazy"
      /></a>
      <figcaption>${caption}</figcaption>
    </figure>`;
  }

  private renderCommand(command: string) {
    return html`<div class="command-block">
      <sl-copy-button
        .value=${command}
        copy-label="Copy command"
        success-label="Copied"
        error-label="Could not copy. Select and copy the command manually."
      >
        <sl-icon
          slot="copy-icon"
          library="system"
          name="copy"
          label="Copy command"
        ></sl-icon>
        <sl-icon
          slot="success-icon"
          library="system"
          name="check"
          label="Copied"
        ></sl-icon>
        <sl-icon
          slot="error-icon"
          library="system"
          name="x-lg"
          label="Could not copy"
        ></sl-icon>
      </sl-copy-button>
      <pre><code>${command}</code></pre>
    </div>`;
  }

  private renderCredentialIdentity(credential: WebAuthnCredential) {
    return html`<span
      >${workshopAlgorithm(credential.cose_algorithm)} · Credential ID:
      <code>${shortCredentialId(credential.credential_id)}</code>
      ${credential.credential_id
        ? html`<sl-copy-button
              .value=${credential.credential_id}
              copy-label="Copy credential ID"
              ><sl-icon
                slot="copy-icon"
                library="system"
                name="copy"
                label="Copy credential ID"
              ></sl-icon
            ></sl-copy-button>
            <details>
              <summary>Full credential ID</summary>
              <code>${credential.credential_id}</code>
            </details>`
        : ''}
    </span>`;
  }

  private renderMigration() {
    const selectedSource = this.inventory.find(
      (credential) => credential.id === this.sourceId
    );
    const source = selectedSource;
    const context = this.latestRegistration?.begin.migration_context;
    const options = this.latestRegistration?.begin.options;
    const beforeIds: string[] =
      context?.exclude_credentials_before?.map((item: any) => item.id) ?? [];
    const afterIds: string[] =
      options?.excludeCredentials?.map((item: any) => item.id) ?? [];
    const retainedIds = beforeIds.filter((id) => afterIds.includes(id));
    const guidedStage = html`<section
      id="guided-stage"
      class="ceremony-card"
      tabindex="-1"
      aria-live="polite"
    >
      <h3>Current step: ${this.stage}</h3>
      ${selectedSource
        ? html`<p>
            Selected passkey: ${this.renderCredentialIdentity(selectedSource)}
          </p>`
        : ''}
      ${!source
        ? html`<p>
              Choose an eligible discoverable credential below. Classical
              credentials can upgrade; post-quantum credentials can prepare the
              classical starting point.
            </p>
            ${this.inventory.length === 0
              ? html`<button
                  ?disabled=${!this.migrationAvailable ||
                  this.busy ||
                  this.lifecycleBusy}
                  @click=${() => this.runMigration('create')}
                >
                  Add a classical passkey
                </button>`
              : ''}`
        : this.targetedSigninId
          ? html`<p>
                <strong
                  >${this.replacementSource
                    ? 'Replacement registered.'
                    : 'Passkey registered.'}</strong
                >
                The RP accepted ${source.name || 'the new passkey'}
                (${source.cose_algorithm === -7
                  ? 'classical ES256'
                  : 'post-quantum ML-DSA-44'})
                ${this.replacementSource
                  ? html`and retired
                    ${this.replacementSource.name || 'the selected source'}
                    (${this.replacementSource.cose_algorithm === -7
                      ? 'classical ES256'
                      : 'post-quantum ML-DSA-44'}).`
                  : ''}
                Sign-in is optional and verifies this exact new passkey
                separately.
              </p>
              ${source.cose_algorithm === -48 &&
              this.replacementSource?.cose_algorithm === -7
                ? html`<section aria-label="Explain your upgrade">
                    <h4>Explain the change you just made</h4>
                    <p>
                      Use Registration details and the old and new credential
                      IDs below to inspect:
                    </p>
                    <ul>
                      <li>
                        The changed <code>pubKeyCredParams</code> and selected
                        source omitted from <code>excludeCredentials</code>.
                      </li>
                      <li>
                        The accepted credential and retired account record.
                      </li>
                      <li>
                        The risk of the key changing before the site saves the
                        result, and the recovery access you kept.
                      </li>
                    </ul>
                    <p>
                      What did the RP change, and what recovery risk remains?
                    </p>
                    <p>
                      Registration and optional sign-in are separate results.
                      The accepted replacement and these explanations complete
                      the browser exercise; they do not establish compatibility
                      for other authenticators.
                    </p>
                  </section>`
                : ''}
              ${this.outcome === 'Sign-in verified'
                ? html`<p role="status">
                    Sign-in verified: ${this.renderCredentialIdentity(source)}
                  </p>`
                : ''}
              ${source.credential_id
                ? html`<div aria-label="Credential replacement">
                    ${this.replacementSource?.credential_id
                      ? html`<p>
                          Retired RP source:
                          ${this.renderCredentialIdentity(
                            this.replacementSource
                          )}
                        </p>`
                      : ''}
                    <p>
                      ${this.replacementSource
                        ? 'Active replacement:'
                        : 'Registered credential:'}
                      ${this.renderCredentialIdentity(source)}
                    </p>
                  </div>`
                : ''}
              <button
                ?disabled=${this.busy ||
                this.lifecycleBusy ||
                !this.migrationAvailable}
                @click=${() =>
                  this.passkeyManager?.dispatchEvent(
                    new CustomEvent('workshop-passkey-action', {
                      detail: {
                        credentialId: this.targetedSigninId,
                        action: 'signin',
                      },
                    })
                  )}
              >
                Try sign-in
              </button>
              ${this.ceremonyError
                ? html`<p role="alert">${this.ceremonyError}</p>`
                : ''}
              ${source.cose_algorithm === -7 && source.discoverable === true
                ? html`<p>
                    Classical preparation is complete. Continue from this
                    credential's card above; it shows an upgrade action when
                    this credential is eligible.
                  </p>`
                : html`<p>
                    Registration accepted. You may return to the workshop using
                    the final link below.
                  </p>`}`
          : html`<p>
              Selected ${source.name || 'passkey'} uses
              ${source.cose_algorithm === -48
                ? 'post-quantum ML-DSA-44 (-48)'
                : 'classical ES256 (-7)'}.
              Register its
              ${source.cose_algorithm === -48
                ? 'classical ES256 (-7)'
                : 'post-quantum ML-DSA-44 (-48)'}
              replacement. This workshop session authorizes the operation; it
              does not prove control of the source credential.
            </p>`}
      ${this.latestRegistration && options
        ? html`<details>
            <summary>Registration details</summary>
            <div role="region" aria-label="RP registration options">
              <p>
                The RP returned these actual registration options for
                ${context
                  ? `${workshopAlgorithm(context.source_algorithm)} → `
                  : ''}${workshopAlgorithm(options.pubKeyCredParams?.[0]?.alg)}.
              </p>
              <p>
                <strong
                  ><code>pubKeyCredParams</code>: algorithms accepted by the
                  RP</strong
                >
              </p>
              <p>
                ${context
                  ? html`Source: ${workshopAlgorithm(context.source_algorithm)}
                    → `
                  : ''}Requested:
                <code
                  >${options.pubKeyCredParams
                    ?.map(
                      (item: any) =>
                        `${workshopAlgorithm(item.alg)} (${item.alg})`
                    )
                    .join(', ')}</code
                >
              </p>
              <h4><code>excludeCredentials</code>: what changed</h4>
              <div class="exclusion-comparison">
                <section aria-label="Before exclusion list">
                  <h5>Before — ordinary duplicate protection</h5>
                  ${context?.exclude_credentials_before?.length
                    ? html`<ul>
                        ${context.exclude_credentials_before.map(
                          (item: any) =>
                            html`<li>
                              ${item.id === context.source_credential_id
                                ? html`<del
                                      ><code
                                        >${shortCredentialId(item.id)}</code
                                      ></del
                                    >
                                    <strong
                                      >Selected source: removed for this
                                      registration</strong
                                    >`
                                : html`<code
                                      >${shortCredentialId(item.id)}</code
                                    >
                                    — retained`}
                            </li>`
                        )}
                      </ul>`
                    : html`<p>No existing credential exclusions.</p>`}
                </section>
                <section aria-label="After exclusion list">
                  <h5>After — this authorized registration</h5>
                  ${options.excludeCredentials?.length
                    ? html`<ul>
                        ${options.excludeCredentials.map(
                          (item: any) =>
                            html`<li>
                              <code>${shortCredentialId(item.id)}</code> —
                              retained
                            </li>`
                        )}
                      </ul>`
                    : html`<p>No credential exclusions remain.</p>`}
                </section>
              </div>
              <p>
                These are WebAuthn credential IDs used by the authenticator, not
                the database record IDs.
              </p>
              <details>
                <summary>
                  Registration options and internal record details
                </summary>
                <pre>
${JSON.stringify(
                    {
                      source_record_id: context?.source_record_id,
                      pubKeyCredParams: options.pubKeyCredParams,
                      authenticatorSelection: options.authenticatorSelection,
                      extensions:
                        options.extensions?.credProps === true
                          ? { credProps: true }
                          : undefined,
                      excludeCredentialsBefore:
                        context?.exclude_credentials_before,
                      excludeCredentialsAfter: options.excludeCredentials,
                    },
                    null,
                    2
                  )}</pre
                >
              </details>
            </div>
          </details>`
        : ''}
      ${this.outcome && !this.targetedSigninId
        ? html`<p role="status">${this.outcome}</p>`
        : ''}
    </section>`;
    return html`<section aria-label="Migration lab outcomes">
      <h2>Start your upgrade</h2>
      <p>
        <strong>Keep another way to access your account.</strong> Your key may
        replace its old passkey before the site saves the new one. A real
        service must establish recovery before offering this replacement.
      </p>
      <details>
        <summary>Prerequisites, replacement and recovery</summary>
        <p>
          A known classical-only authenticator cannot complete the post-quantum
          target. Use a compatible beta key. If another credential on the same
          key is excluded, stop: do not delete it to force registration. Keep
          account access and choose another eligible credential if available.
        </p>
        <p>
          This replacement exercise is only for discoverable credentials. A
          discoverable credential on the same authenticator for the same relying
          party and user handle can be replaced when a new credential is
          registered. Replacement is not atomic: the key may change before the
          site saves the result. The RP omits only the selected source from
          excludeCredentials, then retires its account record after accepting
          the replacement. Keeping the old database record does not restore
          access to a replaced credential.
        </p>
        <p>
          Non-discoverable credentials can use additive enrollment instead;
          inspect the actual storage result because a non-discoverable request
          can fall back to discoverable storage. This beta exercise does not
          establish MDS-certified compatibility.
        </p>
      </details>
      ${!this.migrationAvailable ? html`<p>${this.availability}</p>` : ''}
      ${this.pqOnly
        ? html`<p>
            Turn off post-quantum-only sign-in in
            <a href="/console/settings/security">Account security</a> before
            starting this exercise. This exercise never changes that policy
            automatically.
          </p>`
        : ''}
      <section aria-label="Next action">
        <p>
          Inspect your existing passkeys: refresh the list, then select a
          credential to check its eligibility.
        </p>
        <button
          @click=${this.refreshInventory}
          ?disabled=${this.busy || this.lifecycleBusy}
        >
          Refresh existing passkeys
        </button>
      </section>
      <section aria-label="Expected result">
        <p>
          The list shows each credential's algorithm and eligibility. Select a
          supported credential for the guided upgrade or preparation action;
          follow the displayed blocker guidance. Do not delete an excluded
          credential.
        </p>
      </section>
      <security-keys-manager
        .workshopLab=${true}
        .externalBusy=${this.busy}
        .selectedCredentialId=${this.selectedCredentialId}
        .targetedSigninCredentialId=${this.targetedSigninId}
        .workshopProgress=${''}
        @workshop-passkey-action=${this.rowAction}
        @workshop-passkey-inventory=${this.inventoryChanged}
        @workshop-passkey-busy=${(event: CustomEvent) => {
          if (event.composedPath()[0] === this.passkeyManager)
            this.lifecycleBusy = event.detail.busy === true;
        }}
      >
        ${this.selectedCredentialId
          ? html`<div slot="workshop-evidence">
              ${guidedStage}${this.renderExplorer()}
            </div>`
          : ''}
      </security-keys-manager>
      ${!this.selectedCredentialId &&
      (this.inventory.length === 0 || this.busy || this.explorer.length > 0)
        ? guidedStage
        : ''}
      ${this.ceremonyError && !this.targetedSigninId
        ? html`<p role="alert">${this.ceremonyError}</p>`
        : ''}
      ${!this.selectedCredentialId ? this.renderExplorer() : ''}
      <h3>Explore further</h3>
      <details>
        <summary>Compare: identifier-first sign-in</summary>
        <p>
          After a username identifies the account, the RP supplies eligible
          credential IDs in allowCredentials. It verifies the returned
          credential and enforces its algorithm policy. Identifier-first can use
          either discoverable or non-discoverable credentials.
        </p>
        <p>
          For non-discoverable credentials, additive enrollment can retain the
          classical credential. The RP must inspect the actual storage result;
          requesting non-discoverable storage does not guarantee it. This
          hands-on comparison is not available yet while its isolation and
          recovery requirements are being validated.
        </p>
      </details>
    </section>`;
  }

  private illustrativeLogic(entry: (typeof this.explorer)[number]): string {
    switch (entry.kind) {
      case 'readiness':
        return `require_existing_owner_session()
state = consume_readiness_challenge()
credential = require_active_owned_returned_credential()
fido2_server.authenticate_complete(state, [credential.public_key], response)
require_uv_origin_rp_challenge_and_expected_user_handle()
record_browser_discovery_observation_if_unknown()
# No login tokens, policy changes or replacement authorization`;

      case 'registration':
        return `state = consume_and_check_registration_owner_and_policy()
${entry.replacement ? 'require_human_access_session()\nsource = validate_binding(db, current_user, state.binding)\nrequire(requested_algorithm == state.binding.target)\n' : ''}auth_data = fido2_server.register_complete(state, response)
validate_ceremony_context(client_data, auth_data)
actual_algorithm = auth_data.credential_data.public_key[3]
require(actual_algorithm in offered_algorithms)
require_requested_algorithm_policy(actual_algorithm)
${entry.replacement ? 'require(actual_algorithm == state.binding.target)\nreplace_credential(source, new_credential)  # atomic RP transaction' : 'create_credential(new_credential)  # no source retirement'}`;
      case 'sign-in':
        return `session = consume_and_check_targeted_login_session()
credential = require_targeted_credential(response, session.binding)
fido2_server.authenticate_complete(session.state, [credential_public_key], response)
validate_ceremony_context(client_data, authenticator_data)
require_user_verification_and_matching_user_handle()
validate_binding(db, user, session.binding, require_transition=False)
recheck_current_owner_key_and_signin_policy()
record_authentication_and_issue_session()`;
    }
  }

  private highlightedLogic(entry: (typeof this.explorer)[number]) {
    return this.illustrativeLogic(entry)
      .split(
        /(fido2_server\.(?:register_complete|authenticate_complete)|validate_binding|actual_algorithm|offered_algorithms|state\.binding\.target|replace_credential|require_targeted_credential)/g
      )
      .map((part, index) =>
        index % 2 ? html`<strong>${part}</strong>` : part
      );
  }

  private renderExplorer() {
    return this.explorer.map(
      (entry) =>
        html`<section class="ceremony-card">
          <h3>${entry.action}</h3>
          <details>
            <summary>Request</summary>
            <h4>1. What the RP requests</h4>
            <p>
              ${entry.kind === 'registration'
                ? html`The site chooses acceptable algorithms and credentials
                    that block registration. Compare
                    <code>pubKeyCredParams</code> and
                    <code>excludeCredentials</code>. Algorithm -7 is classical
                    ES256; -48 is post-quantum ML-DSA-44.`
                : entry.kind === 'sign-in'
                  ? html`The site requests a fresh assertion for the selected
                    credential. Inspect the challenge, relying-party ID, allowed
                    credential and user-verification requirement.`
                  : html`The site checks whether the browser can identify an
                    existing credential without a credential list. This records
                    discoverability; it does not register a replacement or sign
                    you in.`}
            </p>
            <pre>${entry.request}</pre>
          </details>
          <details>
            <summary>Response</summary>
            <h4>2. What the browser and key return</h4>
            <p>
              These fields came from this browser ceremony. Long binary values
              are abbreviated. The server must still verify them. Client data
              binds the operation, origin and challenge. Authenticator data
              includes verification flags; a sign-in signature proves possession
              only after server verification. These details clear when you
              leave.
            </p>
            <pre>${entry.response}</pre>
          </details>
          <details>
            <summary>What the RP verified</summary>
            <h4>3. What the RP verifies</h4>
            <p>
              ${entry.kind === 'registration'
                ? html`Inspect the accepted credential’s Saved registration
                  details for the issued options, response and checks. Saved
                  attestation does not establish certificate-chain trust.`
                : entry.kind === 'sign-in'
                  ? html`Check that the RP accepted the assertion for the
                    selected credential and issued the sign-in result.
                    Registration alone does not prove this sign-in succeeded.`
                  : html`Check the observed credential and discoverability
                    result. A successful readiness check does not complete
                    registration, replacement or sign-in.`}
            </p>
            <p>
              ${entry.acceptance === 'accepted'
                ? entry.checks
                : 'Server acceptance not confirmed'}
            </p>
            <h4>Illustrative server logic — not an execution trace</h4>
            <p>
              The Fido2Server completion checks the challenge, RP, origin and
              required user verification. The helpers below summarize additional
              application checks; browser output alone is not server acceptance.
            </p>
            <pre><code>${this.highlightedLogic(entry)}</code></pre>
            ${entry.kind === 'registration'
              ? html`<p>
                  ${entry.replacement
                    ? 'Authorized replacement stores the new credential and retires the old RP record in one atomic RP transaction.'
                    : 'Initial registration stores a new credential; no replacement or retirement is authorized.'}
                  Registration does not establish trusted attestation or
                  hardware protection.
                </p>`
              : ''}
          </details>
        </section>`
    );
  }
  private renderPqAuthentication() {
    return html`
      <nav aria-label="Workshop">
        <a href="/console/workshop/yubination">Return to workshop</a>
      </nav>
      <p>Optional challenge · Sign-in protection</p>
      <section aria-label="Challenge outcome">
        <h1>Protect your sign-in with post-quantum passkeys</h1>
        <p>
          This changes authentication, not action authorization. Require a
          post-quantum passkey for new sign-ins; tool approval policies and
          existing signed-in sessions stay unchanged.
        </p>
      </section>
      <section aria-label="Prepare sign-in protection">
        <h2>1. Keep access, then enable</h2>
        <section aria-label="Prerequisites">
          <p>
            You need at least two eligible post-quantum credentials on this
            account.
          </p>
        </section>
        <p>
          <strong
            >There is no account recovery if you lose all usable post-quantum
            passkeys.</strong
          >
          Keep this workshop session open.
        </p>
        <details>
          <summary>Credentials and backup keys</summary>
          <p>
            This does not require two physical keys. Two credentials on one key
            do not protect you from losing that key. Replacing a passkey can
            remove an earlier credential; check what remains.
          </p>
        </details>
        <section aria-label="Next action">
          <p>
            Check your eligible credentials below, then select
            <strong>Enable post-quantum sign-in</strong> and confirm with any
            eligible post-quantum passkey. If you need another credential,
            select Add passkey in Account security first.
          </p>
        </section>
        <section aria-label="Expected result">
          <p>
            The saved setting shows protection enabled after reloading.
            Cancellation leaves it unchanged.
          </p>
        </section>
        <security-keys-manager></security-keys-manager>
      </section>
      <section aria-label="Test fresh sign-in">
        <h2>2. Check what new sign-ins allow</h2>
        <p>
          Keep this session signed in. Open
          <a href="/login" target="_blank" rel="noopener">Sign in</a> in a
          separate private browser session using your browser’s link menu. A
          normal new tab shares this session. Use your own account and
          credentials.
        </p>
        <ol>
          <li>
            Sign in with an eligible post-quantum passkey: your account should
            open.
          </li>
          <li>
            In a fresh private session, try a registered classical passkey:
            expect a readable request to use a post-quantum passkey, without a
            signed-in account.
          </li>
          <li>
            Try the account password in a fresh private session: a password
            alone cannot bypass post-quantum protection.
          </li>
        </ol>
        <p>
          If you lack a classical credential, record that comparison as not
          tested. Keep your working passkeys and policy unchanged.
        </p>
      </section>
      <details>
        <summary>How Preloop enforces this at sign-in</summary>
        <p>
          The relying party verifies the assertion, checks the registered
          credential's actual algorithm and this user's policy, then decides
          whether to issue its normal session. Password-only sign-in is rejected
          while protection is enabled.
        </p>
        <pre>
verify WebAuthn assertion
load credential algorithm and per-user sign-in policy
if protection is enabled and credential is not post-quantum: deny sign-in
otherwise: issue the existing session</pre
        >
        <p>
          A successful assertion and successful sign-in are distinct: a
          classical signature can verify while policy still denies access. This
          setting does not authorize tool calls or change action approval.
        </p>
      </details>
      <section aria-label="Explain sign-in protection">
        <h2>3. Explain the result and recovery</h2>
        <p>
          Record which sign-in paths succeeded or were denied and check the
          saved setting. Why does protected sign-in not approve an agent action?
        </p>
        <details>
          <summary>
            Explore further: recovery and turning protection off
          </summary>
          <p>
            Two credentials do not guarantee two recovery devices. Existing
            sessions stay open; keep usable credentials and access.
          </p>
          <p>
            Optional: use <strong>Disable post-quantum sign-in</strong> above
            and confirm with a post-quantum passkey while you still have access.
            Reload to verify the saved setting.
          </p>
        </details>
      </section>
      <a href="/console/workshop/yubination">Return to workshop</a>
    `;
  }
  render() {
    if (this.lab === 'pq-authentication') return this.renderPqAuthentication();
    if (this.lab !== 'agent-setup') return this.renderPreview();
    return html`
      <nav aria-label="Workshop">
        <a href="/console/workshop/yubination">Workshop overview</a>
      </nav>
      <p>Optional challenges · Agent access</p>
      <section aria-label="Challenge outcome">
        <h1>Inspect agent access</h1>
        <p>
          Inspect your already-connected workshop agent's access: discover the
          governed tools, read your customer and explain where approval is
          enforced.
        </p>
      </section>
      <p>
        If your workshop action is pending, keep its original tab open and
        switch back to it to continue. This page does not resume an interrupted
        tool call.
      </p>
      <section aria-label="Prerequisites">
        <h2>Before you begin</h2>
        <ul>
          <li>
            Use the same account, assigned customer and already-connected J1
            client.
          </li>
          <li>
            Keep the original workshop tab and working client configuration.
          </li>
        </ul>
      </section>
      <details>
        <summary>Connection recovery: canonical client setup</summary>
        <p>
          Back up existing client configuration before adding a missing workshop
          connection.
        </p>
        <p>
          If native onboarding is unavailable, open
          <strong>Open client setup</strong>
          and choose manual setup. Use an API key from this same account with
          the displayed MCP endpoint.
        </p>
        <section>
          <h2>Recover a missing connection</h2>
          <p>
            Use this deployment's governed endpoint:
            <code>${window.location.origin}/mcp</code>.
          </p>
          <button
            id="lab-client-setup"
            @click=${() => {
              this.showClientSetup = true;
            }}
          >
            Open client setup
          </button>
          <ol>
            <li>
              Open <strong>Open client setup</strong>, then select
              <strong>Codex CLI</strong> or <strong>Claude Code</strong> in
              native onboarding. Follow login, discovery, preview, apply and
              status in order.
            </li>
            <li>
              Use the configuration and managed credential emitted by onboarding
              for that client and this deployment. For manual alternatives only,
              merge the workshop server into existing settings without replacing
              your whole configuration, and do not share the API key in chat.
            </li>
            <li>
              In Codex or Claude Code, use <code>/mcp</code> to inspect the
              connection and discover <code>get_customer_status</code> and
              <code>set_customer_status</code>. For curl, follow the
              initialization and tool-discovery recipe. Do not request the write
              yet.
            </li>
          </ol>
          <p>
            Native setup uses the CLI built from this workshop checkout and
            requires Go/make and an installed, authenticated client. Use the
            configuration and credential emitted by onboarding. Review the
            preview, preserve provider settings and stop on unintended routing.
            Manual client and curl alternatives remain in the dialog; they do
            not establish canonical onboarding completion.
          </p>
          <p>
            <a
              href="https://docs.preloop.ai/getting-started/connect-mcp-client/"
              target="_blank"
              rel="noopener"
              >Read Preloop's client connection documentation</a
            >. Use this deployment's generated instructions when a public
            example targets preloop.ai.
          </p>
        </section>
      </details>
      <section aria-label="Next action">
        <h2>Inspect the governed tools</h2>
        <ol>
          <li>
            <a href="/console/tools" target="_blank" rel="noopener"
              >Open Tools in a new tab</a
            >
            and find the workshop database server.
          </li>
          <li>
            Inspect the input schemas and Approval Workflow settings for
            <code>get_customer_status</code> and
            <code>set_customer_status</code>. Do not change the policy.
          </li>
          <li>
            In your connected client, request:
            <code
              >Call get_customer_status once using the exact read arguments
              displayed on the main workshop page, including my assigned
              customer email, and report its exact result. Do not call any other
              tool.</code
            >
            Compare the returned customer with the main workshop. A returned row
            proves the read completed; tool discovery alone does not. Then
            inspect why the write requires approval without running it again.
          </li>
        </ol>
        <section aria-label="Expected result">
          <p>
            The tool result identifies your assigned customer; discovery alone
            is not execution. Your client calling a tool, Preloop authorizing
            the action, and the database executing it are separate events.
            Identify the control permitting the bounded read and the policy
            requiring approval for writes.
          </p>
        </section>
      </section>
      <section>
        <h2>Troubleshoot and finish</h2>
        <p>Whose credential grants access, and where is approval enforced?</p>
        <p>
          If tools are missing, confirm the account, API key, endpoint and
          hosted access setup before adding a duplicate server. A client
          permission prompt does not replace your YubiKey approval. After the
          workshop, remove only the connection you added or restore the relevant
          configuration from your backup.
        </p>
        <p>
          If this exercise added no temporary connection, leave your working J1
          configuration alone.
        </p>
      </section>
      <details>
        <summary>Explore further: connection reference</summary>
        <p>
          Use canonical setup above only if your J1 connection needs recovery;
          connecting twice is not the challenge.
        </p>
      </details>
      <mcp-setup-dialog
        .open=${this.showClientSetup}
        @close=${() => {
          this.showClientSetup = false;
        }}
      ></mcp-setup-dialog>
    `;
  }

  private renderPreview() {
    const content = {
      'receipt-verification': {
        title: 'Audit an approval',
        objective:
          'Audit your own approval: identify the action, read its checks and find separate evidence of execution.',
        prerequisites:
          'Use an approved request from the main workshop in this account.',
        check:
          'Distinguish signed action bindings, recorded policy context and independent execution evidence.',
        readiness: '',
      },
      previewsign: {
        title: 'Sign an action with PreviewSign',
        objective:
          'Explore an additional signature in the same governed approval journey. Compare the signed inputs, algorithms and verification evidence.',
        prerequisites:
          'Use Google Chrome desktop with permission to load an unpacked extension, a YubiKey with firmware 5.8 or later and PreviewSign support, and the matching native helper built with experimental Yubikit Rust. Windows installation and hardware testing are pending. A PQC-capable YubiKey alone does not establish PreviewSign support.',
        check:
          'Finish only when both WebAuthn and PreviewSign verification pass, the original tool returns the expected change, and an independent read shows VIP. The extra P-256 signature is not post-quantum.',
        readiness:
          'Experimental • macOS Apple silicon. Windows testing is pending. Check existing credential readiness before touch; ready credentials need no new registration. A customer reset cannot add missing PreviewSign metadata.',
      },
      'python-fido2-ml-dsa': {
        title: 'Upgrade to a post-quantum passkey',
        objective:
          'Upgrade a classical passkey to post-quantum, then inspect what changed.',
        prerequisites:
          'Use your existing workshop account and a registered passkey. If it is already post-quantum, prepare the classical starting point on that account. No new account is required.',
        check:
          'Complete browser registration, inspect the actual algorithm, and optionally try sign-in with the replacement. Follow the RP algorithm and exclusion choices for a discoverable credential upgrade. Explain replacement and recovery, and compare additive enrollment for non-discoverable credentials.',
      },
    }[this.lab];
    if (!content)
      return html`<h1>Challenge not found</h1>
        <a href="/console/workshop/yubination">Return to the workshop</a>`;
    return html`
      <nav aria-label="Workshop">
        <a href="/console/workshop/yubination">Return to the workshop</a>
      </nav>
      ${this.lab !== 'python-fido2-ml-dsa'
        ? html`<p>Optional challenge</p>`
        : ''}
      ${this.lab !== 'previewsign'
        ? html`<section aria-label="Challenge outcome">
            <h1>${content.title}</h1>
            <p>${content.objective}</p>
          </section>`
        : html`<h1>${content.title}</h1>
            <sl-badge variant="neutral" pill>Experimental</sl-badge>`}
      ${this.lab !== 'python-fido2-ml-dsa' &&
      this.lab !== 'receipt-verification'
        ? html`<p
            role="status"
            data-source-state=${!this.sourceLoaded ||
            (this.lab === 'previewsign' && !this.artifactLoaded)
              ? 'loading'
              : this.lab === 'receipt-verification' ||
                  this.sourceRepository ||
                  this.participantArtifact ||
                  this.windowsArtifact
                ? 'available'
                : 'unavailable'}
          >
            ${!this.sourceLoaded ||
            (this.lab === 'previewsign' && !this.artifactLoaded)
              ? 'Checking workshop source availability…'
              : !this.sourceRepository &&
                  !this.participantArtifact &&
                  !this.windowsArtifact &&
                  this.lab === 'previewsign'
                ? 'No Mac download is available on this deployment. Windows testing is pending. Use the source-build instructions if available.'
                : content.readiness}
          </p>`
        : ''}
      ${this.lab === 'python-fido2-ml-dsa'
        ? html`<section aria-label="Prerequisites">
              <h2>Before you begin</h2>
              <p>
                ${content.prerequisites} Use a compatible beta key and keep
                another way into your account; follow the eligibility and
                recovery checks below.
              </p>
            </section>
            ${renderWorkshopEvidence(false)} ${this.renderMigration()} `
        : ''}
      ${this.lab !== 'python-fido2-ml-dsa' && this.lab !== 'previewsign'
        ? html`<section aria-label="Prerequisites">
            <h2>Before you begin</h2>
            <p>${content.prerequisites}</p>
          </section>`
        : ''}
      ${this.lab === 'receipt-verification' ? this.renderReceiptExercise() : ''}
      ${this.lab === 'previewsign' ? this.renderPreviewSignExercise() : ''}
      ${this.lab !== 'python-fido2-ml-dsa' && this.lab !== 'previewsign'
        ? html`<section>
            <h2>Continue the workshop</h2>
            <p>
              If an action is pending in your original workshop tab, switch back
              to that tab. The return link does not resume an interrupted tool
              call.
            </p>
          </section>`
        : ''}
      <section>
        <a href="/console/workshop/yubination">Return to workshop</a>
      </section>
    `;
  }
  private renderPreviewSignExercise() {
    const requiredSteps = html`
      <section data-previewsign-step>
        <section aria-label="Challenge outcome">
          <h2>1. What you will learn</h2>
          <p>
            PreviewSign adds a signature to the same governed approval ceremony.
            Compare the two signed inputs, their verification results and the
            actual customer change.
          </p>
        </section>
        <p role="img" aria-label="PreviewSign component diagram">
          Page → Chrome extension → Native helper → YubiKey → RP verifier
        </p>
        <details>
          <summary>Why the extension and helper are needed</summary>
          <p>
            Chrome does not natively support the proposed PreviewSign WebAuthn
            extension. The workshop browser extension bridges the page to a
            native helper that talks to the YubiKey 5.8 with PreviewSign
            support. It is distinct from the authenticator's PreviewSign
            extension; the relying party (RP) verifier checks the returned
            proofs.
          </p>
        </details>
      </section>
      <section data-previewsign-step>
        <h2>2. Before you begin</h2>
        <section aria-label="Prerequisites">
          <p>
            Use Chrome desktop, one YubiKey with firmware 5.8 or later and
            PreviewSign support, your existing workshop account and the matching
            extension/native helper.
          </p>
        </section>
        <section aria-label="Next action">
          <p>
            Use the same account you used in the main workshop. Open
            <a href="/console/settings/security">Account security</a> and look
            for the PreviewSign ready badge on the passkey you plan to use. If
            it is there, continue below. If it is missing, read “Missing
            PreviewSign metadata” below. The browser extension supports one
            YubiKey at a time. Unplug other YubiKeys.
          </p>
        </section>
        <section aria-label="Expected result">
          <p>
            The badge means registration metadata is saved. It does not prove
            hardware support or valid signatures.
          </p>
        </section>
        <details>
          <summary>Missing PreviewSign metadata</summary>
          <p>
            Installing the extension does not update an existing credential.
            This application cannot add missing PreviewSign metadata to it in
            place. Ordinary WebAuthn can still work, but that does not complete
            this challenge.
          </p>
          <p>
            If you have another compatible YubiKey that is not registered to
            this account, install the matching extension and helper, enable
            interception, then open
            <a href="/console/settings/security">Account security</a> and select
            <strong>Add passkey</strong>. Check for the PreviewSign ready badge
            afterward.
          </p>
          <p>
            If your only compatible key is already registered without metadata,
            this challenge currently has no supported preparation path for that
            key. Keep your account and credentials. Do not delete or replace
            credentials or bypass <code>excludeCredentials</code>. A
            post-quantum algorithm or model name alone does not establish
            PreviewSign readiness.
          </p>
        </details>
      </section>
      <section data-previewsign-step>
        <h2>3. Install for your computer</h2>
        <sl-tab-group
          data-platform-tabs
          aria-label="Installation platform"
          @sl-tab-show=${(event: CustomEvent<{ name: string }>) => {
            if (
              event.detail.name === 'mac' ||
              event.detail.name === 'windows' ||
              event.detail.name === 'source'
            )
              this.previewSignPlatform = event.detail.name;
          }}
        >
          <sl-tab
            slot="nav"
            panel="mac"
            ?active=${this.previewSignPlatform === 'mac'}
            >macOS Apple silicon</sl-tab
          >
          <sl-tab
            slot="nav"
            panel="windows"
            ?active=${this.previewSignPlatform === 'windows'}
            >Windows</sl-tab
          >
          <sl-tab
            slot="nav"
            panel="source"
            ?active=${this.previewSignPlatform === 'source'}
            >Build from source</sl-tab
          >
          <sl-tab-panel
            name="mac"
            ?active=${this.previewSignPlatform === 'mac'}
          >
            ${this.participantArtifact
              ? html`
                  <p>
                    PreviewSign package for macOS Apple silicon. This package is
                    not signed or notarized. The manual setup below needs only
                    Chrome and tools included with macOS.
                  </p>
                  <p>
                    <a
                      href="/previewsign/macos-arm64/previewsign-macos-arm64.tar.gz"
                      download="previewsign-macos-arm64.tar.gz"
                      >${this.participantArtifact.distribution ===
                      'local-evaluation'
                        ? 'Experimental Mac test download'
                        : 'Download Mac evaluation package'}</a
                    >
                  </p>
                  <details>
                    <summary>Package checksum and matching source</summary>
                    <p>
                      Expected SHA-256:
                      <code>${this.participantArtifact.sha256}</code>
                    </p>
                    <p>
                      Source revision:
                      <code
                        >${this.participantArtifact.sourceRevision ??
                        'local test package: see its manifest for the source revision'}</code
                      >. Use this revision for matching source, not a current
                      main link.
                    </p>
                  </details>
                `
              : this.sourceRepository
                ? html`<p>
                    On macOS Apple silicon, follow the
                    ${this.sourceLink(
                      `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/DEVELOPER-QUICKSTART.md`,
                      'Mac source-build and installation guide'
                    )}.
                    Build, assemble and install into its dedicated Chrome
                    profile, then use Developer mode → Load unpacked with the
                    guide’s exact folder. Check helper connectivity before
                    requesting an action; this deployment has no participant
                    package.
                  </p>`
                : html`<p>
                    No Mac participant download is available on this deployment.
                    The source-build guide is unavailable until this deployment
                    provides its source repository. You cannot install from this
                    page yet. Do not download an unrelated helper or start
                    registration without the matching extension.
                  </p>`}
            <p>
              Only use the commands below after obtaining the matching package
              and its expected SHA-256. If no download is available, ask the
              release owner; screenshots are guidance, not evidence of package
              availability.
            </p>
            ${this.renderCommand(`cd "$HOME/Downloads"
shasum -a 256 previewsign-macos-arm64.tar.gz`)}
            <p>
              Compare the entire checksum with Expected SHA-256 in the package
              details. Stop on mismatch. Only after a match, extract and
              install:
            </p>
            <p>
              These commands unpack the files and register the packaged native
              helper with Chrome, allowing only the workshop extension to call
              it. They create a new folder at
              <code>$HOME/PreviewSign-evaluation</code>. If it already exists,
              the commands stop before changing it. Do not delete an existing
              setup to retry.
            </p>
            ${this.renderCommand(`(
set -eu
base="$HOME/PreviewSign-evaluation"
mkdir "$base"
mkdir "$base/install" "$base/chrome"
tar -xzf "$HOME/Downloads/previewsign-macos-arm64.tar.gz" -C "$base/install"
test -x "$base/install/bin/sign-extension-host"
facts="$base/install/installation.json"
if test -e "$facts"; then
  native_host="$(plutil -extract nativeHosts.macos raw -o - "$facts")"
  extension_id="$(plutil -extract chromeExtensionId raw -o - "$facts")"
else
  native_host="${PREVIEWSIGN_MACOS_NATIVE_HOST}"
  extension_id="${PREVIEWSIGN_CHROME_EXTENSION_ID}"
fi
printf '%s\\n' "$native_host" | grep -Eq '^[a-z0-9_]+(\\.[a-z0-9_]+)+$'
printf '%s\\n' "$extension_id" | grep -Eq '^[a-p]{32}$'
mkdir "$base/chrome/NativeMessagingHosts"
manifest="$base/chrome/NativeMessagingHosts/$native_host.json"
printf '{}\\n' > "$manifest"
plutil -convert xml1 "$manifest"
plutil -insert name -string "$native_host" "$manifest"
plutil -insert description -string "PreviewSign workshop helper" "$manifest"
plutil -insert path -string "$base/install/bin/sign-extension-host" "$manifest"
plutil -insert type -string stdio "$manifest"
plutil -insert allowed_origins -json "[\\"chrome-extension://$extension_id/\\"]" "$manifest"
plutil -convert json "$manifest"
)`)}
            <details>
              <summary>Optional Python installer</summary>
              <p>
                Requires Python 3 installed separately. Use this only instead of
                the manual setup, with a new destination. Follow the matching
                Python cleanup below.
              </p>
              ${this.renderCommand(`cd "$HOME/Downloads"
mkdir previewsign-evaluation
tar -xzf previewsign-macos-arm64.tar.gz -C previewsign-evaluation
cd previewsign-evaluation
python3 -I -S install.py install --package "$PWD" --destination "$HOME/PreviewSign-evaluation/install" --chrome-user-data-dir "$HOME/PreviewSign-evaluation/chrome"`)}
            </details>
            <p>
              Keep these dedicated paths; installation refuses collisions.
              Connect only the intended YubiKey for the later action. Open the
              dedicated browser:
            </p>
            ${this.renderCommand(
              `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --user-data-dir="$HOME/PreviewSign-evaluation/chrome"`
            )}
          </sl-tab-panel>
          <sl-tab-panel
            name="windows"
            ?active=${this.previewSignPlatform === 'windows'}
          >
            ${this.windowsArtifact
              ? html`
                  <p>
                    Windows x64 package. Requires Windows PowerShell 5.1 or
                    later and Google Chrome installed under Program Files. No
                    compilation or Python is needed.
                  </p>
                  <p>
                    <a
                      data-windows-download
                      href="/previewsign/windows-x64/previewsign-windows-x64.zip"
                      download="previewsign-windows-x64.zip"
                      >${this.windowsArtifact.distribution ===
                      'local-evaluation'
                        ? 'Experimental Windows test download'
                        : 'Download Windows evaluation package'}</a
                    >
                  </p>
                  <details>
                    <summary>Package checksum and matching source</summary>
                    <p>
                      Expected SHA-256:
                      <code>${this.windowsArtifact.sha256}</code>
                    </p>
                    <p>
                      Source revision:
                      <code
                        >${this.windowsArtifact.sourceRevision ??
                        'See the package manifest'}</code
                      >
                    </p>
                  </details>
                  ${this.renderCommand(
                    `Get-FileHash -Algorithm SHA256 "$env:USERPROFILE\\Downloads\\previewsign-windows-x64.zip"`
                  )}
                  <p>
                    Compare the entire checksum with the value above. After a
                    match, extract into a new stable folder and register the
                    helper. If the folder or a Chrome native-host registration
                    already exists, stop and keep that setup.
                  </p>
                  ${this
                    .renderCommand(`$base = Join-Path $env:USERPROFILE 'PreviewSign-evaluation'
if (Test-Path -LiteralPath $base) { throw 'PreviewSign-evaluation already exists' }
New-Item -ItemType Directory -Path $base -ErrorAction Stop
Expand-Archive -LiteralPath "$env:USERPROFILE\\Downloads\\previewsign-windows-x64.zip" -DestinationPath "$base\\install"
Set-Location "$base\\install"
.\\install.ps1 -Command Install -ChromeUserDataDir "$base\\chrome"
.\\install.ps1 -Command Preflight -ChromeUserDataDir "$base\\chrome"
& "$env:ProgramFiles\\Google\\Chrome\\Application\\chrome.exe" --user-data-dir="$base\\chrome"`)}
                  <p>
                    Load the installed <code>extension</code> folder using the
                    Chrome steps below. PowerShell, Windows and Chrome policy
                    may block installation; follow your organization's policy.
                  </p>
                  <p>
                    After helper health passes, start the interactive signing
                    process in a separate PowerShell terminal before
                    registration or approval. Keep Chrome and the terminal
                    unelevated; explicitly consent to UAC for only the temporary
                    signing helper. No persistent service is installed. Keep
                    that terminal open:
                  </p>
                  ${this
                    .renderCommand(`Set-Location "$env:USERPROFILE\\PreviewSign-evaluation\\install"
.\\install.ps1 -Command RunHumanService -ChromeUserDataDir "$env:USERPROFILE\\PreviewSign-evaluation\\chrome"`)}
                `
              : html`
                  <p>
                    <strong>Windows download:</strong>
                    <span data-windows-download
                      >Unavailable on this deployment</span
                    >
                  </p>
                  <p>
                    Windows installation and hardware testing are pending.
                    Developers can use the
                    ${this.sourceLink(
                      `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/WINDOWS-SOURCE-REHEARSAL.md`,
                      'Windows source rehearsal guide'
                    )}
                    to build from source, install and check helper connectivity.
                    This is not a Windows participant release.
                  </p>
                `}
          </sl-tab-panel>
          <sl-tab-panel
            name="source"
            ?active=${this.previewSignPlatform === 'source'}
            data-previewsign-source-build
          >
            <h3>Build from source (optional)</h3>
            <p>
              Build the browser extension and matching native helper for your
              computer:
            </p>
            <ul>
              <li>
                ${this.sourceLink(
                  `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/DEVELOPER-QUICKSTART.md`,
                  'macOS Apple silicon build instructions'
                )}
              </li>
              <li>
                ${this.sourceLink(
                  `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/WINDOWS-SOURCE-REHEARSAL.md`,
                  'Windows build and test instructions'
                )}
              </li>
            </ul>
            <p>
              If you downloaded a package, use its source revision. Otherwise
              follow the source-build guide’s revision selection. If the source
              or matching helper is unavailable, this path is not available yet.
            </p>
          </sl-tab-panel>
        </sl-tab-group>
        <p>
          In the dedicated Chrome profile, open chrome://extensions and record
          whether Developer mode is on or off before changing it.
        </p>
        <ol class="chrome-setup" aria-label="Chrome extension setup">
          <li>
            <strong>Enable Developer mode if it was off.</strong> Open
            <code>chrome://extensions</code> in the dedicated profile. The Load
            unpacked button appears.
            ${this.chromeScreenshot(
              'developer-mode',
              'Chrome Extensions page showing the Developer mode toggle',
              'Developer mode exposes extension loading controls.'
            )}
          </li>
          <li>
            <strong>Select Load unpacked.</strong> Chrome opens a folder picker.
            ${this.chromeScreenshot(
              'load-unpacked',
              'Load unpacked button on Chrome Extensions page',
              'Select Load unpacked to choose the extension folder.'
            )}
          </li>
          <li>
            <strong>Select the installed extension folder.</strong>
            <div data-platform-folder>
              ${this.previewSignPlatform === 'mac'
                ? html`<p>
                      For the Mac archive, run this in Terminal and copy its
                      output:
                    </p>
                    ${this.renderCommand(
                      `printf '%s\\n' "$HOME/PreviewSign-evaluation/install/extension"`
                    )}
                    <p>
                      Press Command-Shift-G in the picker, paste that absolute
                      path, then select the folder. Do not paste
                      <code>$HOME</code> literally. Mac source builds use the
                      absolute folder printed by their guide.
                    </p>`
                : this.previewSignPlatform === 'source'
                  ? html`<p>
                      Select the installed extension folder printed by your
                      platform’s source-build guide.
                    </p>`
                  : this.windowsArtifact
                    ? html`<p>
                          Copy the expanded absolute path from PowerShell into
                          the folder picker:
                        </p>
                        ${this.renderCommand(
                          `Join-Path $env:USERPROFILE 'PreviewSign-evaluation\\install\\extension'`
                        )}
                        <p>
                          Select the extension folder, not the package or bin
                          folder.
                        </p>`
                    : html`<p>
                        Windows source builds: select the installed
                        <code>extension</code> folder printed by the Windows
                        guide. The Windows download is not available yet.
                      </p>`}
            </div>
            ${this.previewSignPlatform === 'mac'
              ? this.chromeScreenshot(
                  'select-folder',
                  'Chrome folder picker selecting the installed extension folder',
                  'Choose the extension folder, not the package or bin folder.'
                )
              : ''}
          </li>
          <li>
            <strong>Check that the extension card appears.</strong> Its enabled
            toggle should be on and its service worker link available.
            ${this.chromeScreenshot(
              'installed',
              'Installed PreviewSign extension card with its service worker link',
              'The installed extension is ready for the connection check below.'
            )}
          </li>
        </ol>
        <section data-capture-check>
          <h3>Check capture, then reload the workshop</h3>
          <p>
            Open Chrome’s Extensions menu and select the PreviewSign extension.
            In this workshop package,
            <strong>Capture all WebAuthn calls</strong> is unchecked and
            disabled. Leave it that way: the extension automatically handles
            PreviewSign requests from this workshop.
          </p>
          <figure>
            <a
              href="/workshop/previewsign/chrome-workshop-popup.png"
              target="_blank"
              rel="noopener"
              ><img
                src="/workshop/previewsign/chrome-workshop-popup.png"
                alt="Actual workshop extension popup with Capture all WebAuthn calls unchecked and disabled"
                style="max-width:100%;height:auto"
            /></a>
            <figcaption>
              The workshop package captures PreviewSign requests automatically.
              This disabled checkbox is expected.
            </figcaption>
          </figure>
          <p>
            Reload the workshop tab after installing the extension, then check
            the helper below before requesting approval. Installing the
            extension does not add missing PreviewSign data to an existing
            passkey.
          </p>
        </section>
        <section data-helper-health>
          <h3>Check the helper connection</h3>
          <p>
            Return to chrome://extensions. On the PreviewSign card shown above,
            select the service worker link. In the new DevTools window, confirm
            its title identifies background.js and a chrome-extension:// URL,
            then select Console. Do not use the workshop webpage’s or Google’s
            console. Run this check there; it does not access a key. If Chrome
            prevents pasting, do not bypass the warning—type the command or stop
            at this check.
          </p>
          ${this.renderCommand(
            `typeof chrome === 'undefined' || typeof chrome.runtime?.sendNativeMessage !== 'function' ? console.log('Wrong console: open the PreviewSign extension service worker from chrome://extensions.') : chrome.runtime.sendNativeMessage('${this.previewSignPlatform === 'windows' || (this.previewSignPlatform === 'source' && /^Win/i.test(navigator.platform)) ? PREVIEWSIGN_WINDOWS_NATIVE_HOST : PREVIEWSIGN_MACOS_NATIVE_HOST}', {type:'health', protocolVersion:1, requestId:'participant-health'}, response => console.log(chrome.runtime.lastError?.message ?? response))`
          )}
          <p>
            Expect <code>requestId: participant-health</code>,
            <code>version: 0.1.0</code>, <code>protocolVersion: 1</code> and
            <code>deviceAccess: false</code>. This confirms the connection, not
            either signature.
          </p>
          <details>
            <summary>Helper connection troubleshooting</summary>
            <p>
              If Chrome reports an error, check the dedicated profile and
              matching helper installation. Do not bypass browser or
              operating-system policy. Continue only after the check succeeds,
              then return to this workshop in that browser.
            </p>
          </details>
        </section>
      </section>
      <section data-previewsign-step>
        <h2>4. Use your ready credential, request and approve</h2>
        <p>
          Use the ready credential checked in step 2 after the helper check
          passes. If PreviewSign metadata is missing, stop and use the
          preparation guidance there; do not delete/replace a credential or
          bypass exclusion. A badge or a PQC credential alone is insufficient.
        </p>
        <p>
          Open the <a href="/console/workshop/yubination">main workshop</a>.
          Confirm your account-owned customer is Standard, then request Standard
          → VIP once through the same governed tool. The browser extension
          supports one YubiKey at a time. Unplug other YubiKeys. This is one
          step-up assertion with both proofs. Review the exact customer, change
          and justification, then approve with PIN/touch when prompted.
        </p>
        <details>
          <summary>Already VIP, PIN trouble or interrupted approval</summary>
          <p>
            Already VIP? Open the
            <a href="/console/workshop/yubination">main workshop</a>, choose
            <strong>Reset customer to standard</strong>, and approve that
            separate request. Confirm its actual result and Standard readback
            before starting this challenge. PIN failure or cancellation? Open
            the approval page and check its status. Expired request? Confirm its
            terminal state before arranging a fresh request. Do not retry a
            pending transaction or blindly repeat a write.
          </p>
        </details>
      </section>
      <section data-previewsign-step>
        <h2>5. Check both signatures, then check the customer status</h2>
        <p>
          Open Receipt verification details and check the server-reported
          results for both signatures. Inspect
          <strong>Actual MCP tool result</strong>, then return to the main
          workshop and select <strong>Check current status</strong> for
          independent customer readback of your account-owned customer. Missing
          PreviewSign evidence leaves the exercise incomplete even if the action
          ran.
        </p>
        <details>
          <summary>Optional developer verification (requires Python 3)</summary>
          <p>
            Expand <strong>Receipt verification details</strong>, then select
            <strong>Verify stored evidence</strong> for the stored WebAuthn
            checks. Separately inspect the receipt's recorded PreviewSign
            verification and additional proof; the auditor button does not
            re-verify that additional signature. Select
            <strong>Copy WebAuthn proof bundle</strong>. To verify both
            signatures independently, follow the developer instructions below.
            This also requires the matching captured begin response and
            externally expected run inputs; the copied bundle alone is not
            sufficient. Require both independent results to be true.
          </p>
          <p>
            From the matching checkout root, use
            <code
              >integrations/previewsign/scripts/verify_participant_receipt.py</code
            >. The capture contains receipt, begin and external expected origin,
            RP ID, account, request, action and exact arguments; do not learn
            expected values from the receipt. Use the
            ${this.sourceLink(
              `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/DEVELOPER-QUICKSTART.md`,
              'developer verification instructions'
            )}.
          </p>
          ${this.renderCommand(
            `python3 -I -B integrations/previewsign/scripts/verify_participant_receipt.py < /private/capture.json`
          )}
          <p>
            With the existing fido2/cryptography/jcs dependencies, success is
            exit 0, independent_webauthn_valid true,
            independent_previewsign_valid true and errors empty. Otherwise stop
            with incomplete evidence; do not repeat the write. These are
            mathematical checks, distinct from server reports, hardware key
            provenance and actual execution. Keep proof captures private.
          </p>
        </details>
        <details>
          <summary>Developer evidence: two signed inputs</summary>
          <p>
            WebAuthn signs authenticator data and the client-data hash, whose
            challenge binds the intent hash plus nonce. Inspect the credential's
            actual negotiated algorithm; do not assume it is post-quantum.
            PreviewSign adds a P-256 signature over the intent digest, not every
            field of the complete transaction. This extra proof is not
            post-quantum and uses a separate signing key.
          </p>
          <p>
            Inspect the actual registration request's <code>generateKey</code>
            and stored extension metadata, then the approval request's
            <code>previewSign</code> and <code>additionalArgs</code>, returned
            signature, algorithm, key and each verifier result. These are fields
            to inspect in your evidence, not sample success results.
          </p>
        </details>
        <details>
          <summary>Missing proof and what verification establishes</summary>
          <p>
            Repeat the helper connectivity check and check for saved PreviewSign
            metadata in Account security. Ordinary WebAuthn fallback alone is
            incomplete. Signature validity is separate from trusted key
            provenance, human review and database execution. PIN/touch alone
            does not prove a person read the intent.
          </p>
        </details>
      </section>
    `;
    const exploreFurther = html`
      <section>
        <h2>Explore further</h2>
        <p>
          Optional: start with the
          <a
            href="https://github.com/YubicoLabs/build-with-us/blob/main/quickstart/dotnet/preview-sign/README.md"
            >public .NET guide: a separate RP example</a
          >. For this workshop's browser/helper build, use the source paths
          below when the checkout is available.
        </p>
        <details>
          <summary>Workshop source and experimental migration</summary>
          ${this.sourceRepository
            ? html`<p>
                Use the
                ${this.sourceLink(
                  `tree/${this.previewSignSourceRef}/integrations/previewsign`,
                  'workshop extension and native-helper source'
                )}
                and its
                ${this.sourceLink(
                  `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/DEVELOPER-QUICKSTART.md`,
                  'developer guide'
                )}.
              </p>`
            : html`<p>
                Workshop source links are unavailable until this deployment
                configures its source repository. The source checkout is not
                available from this deployment yet.
              </p>`}
          <p>
            Use the package manifest’s source revision; source browsing without
            a package defaults to main, not a release pin. The public .NET
            example is a separate integration.
          </p>
          <ul>
            <li>
              <a
                href="https://github.com/YubicoLabs/build-with-us/tree/main/quickstart/dotnet/preview-sign"
                >RP example source and verification code</a
              >
              — follow the guide's source map and pinned dependencies.
            </li>
            <li>
              <a
                href="https://github.com/w3c/webauthn/blob/main/explainers/raw-signing-extension.md"
                >W3C raw-signing explainer</a
              >
              and
              <a href="https://github.com/w3c/webauthn/pull/2078"
                >draft proposal</a
              >.
            </li>
            <li>
              <a href="https://yubicolabs.github.io/webauthn-sign-extension/4/"
                >Versioned experimental prototype</a
              >.
            </li>
          </ul>
          <p>
            Detect capability and define an explicit fallback policy. Pin
            dependency versions and protocol revisions; test enrollment,
            approval, verification and removal against future revisions while
            preserving old receipts. This workshop uses
            <code>previewSign</code>/<code>additionalArgs</code>; the newer
            explainer uses
            <code>previewSign5</code>/<code>additionalArguments</code>.
            Provisional signing identifiers are not ML-DSA credential
            identifiers: do not replace constants or assume existing key
            material can migrate. Proposal approval guarantees neither browser
            support nor automatic migration.
          </p>
        </details>
      </section>
    `;
    return html`
      ${requiredSteps}
      <section data-previewsign-step>
        <h2>6. Explain your result</h2>
        <p>
          Record the server-reported verification of both signatures, the exact
          MCP result and customer readback. These server results are not
          independent verification. Missing either proof or readback leaves the
          exercise incomplete.
        </p>
        <p>What do the two signatures prove that customer readback does not?</p>
      </section>
      <section data-previewsign-step>
        <h2>7. Cleanup</h2>
        <p>
          Remove only this workshop's extension and owned helper using the
          matching path below.
        </p>
        <p>
          First open <code>chrome://extensions</code> in the dedicated profile.
          Select <strong>Remove</strong> on this workshop’s extension card and
          confirm. Its card disappears. Restore Developer mode to its previous
          setting; turn it off only if you enabled it for this exercise.
        </p>
        ${this.chromeScreenshot(
          'remove',
          'Remove button on the workshop extension card',
          'Remove only the workshop extension, then close the dedicated Chrome window.'
        )}
        ${this.previewSignPlatform === 'mac'
          ? html`<div data-platform-cleanup="mac">
              <h3>Mac archive cleanup</h3>
              <p>
                Close the dedicated Chrome window. In Finder, choose Go → Go to
                Folder and open <code>~/PreviewSign-evaluation</code>. If you
                used the manual setup, move only
                <code
                  >chrome/NativeMessagingHosts/${PREVIEWSIGN_MACOS_NATIVE_HOST}.json</code
                >
                and the <code>install</code> folder created by these steps to
                Trash. Keep the Chrome profile and any other files. If you are
                unsure which files you created, stop without deleting them.
              </p>
              <details>
                <summary>Optional Python installer cleanup</summary>
                <p>
                  Only if you used the Python installer; requires Python 3. From
                  the extracted download, run:
                </p>
                ${this
                  .renderCommand(`cd "$HOME/Downloads/previewsign-evaluation"
python3 -I -S install.py remove --destination "$HOME/PreviewSign-evaluation/install" --chrome-user-data-dir "$HOME/PreviewSign-evaluation/chrome"`)}
              </details>
              <p>
                Installed from Mac source instead? Use the matching owned
                removal command in the
                ${this.sourceLink(
                  `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/DEVELOPER-QUICKSTART.md`,
                  'Mac source-build and cleanup guide'
                )},
                not the archive command.
              </p>
            </div>`
          : this.previewSignPlatform === 'source'
            ? html`<div data-platform-cleanup="source">
                <h3>Source-build cleanup</h3>
                <p>
                  Close the dedicated Chrome window and follow the owned removal
                  instructions for the source build you installed:
                </p>
                <ul>
                  <li>
                    ${this.sourceLink(
                      `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/DEVELOPER-QUICKSTART.md`,
                      'Mac source cleanup'
                    )}
                  </li>
                  <li>
                    ${this.sourceLink(
                      `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/WINDOWS-SOURCE-REHEARSAL.md#5-stop-and-remove-only-owned-installation`,
                      'Windows source cleanup'
                    )}
                  </li>
                </ul>
                <p>Keep unrelated files and your existing Chrome profiles.</p>
              </div>`
            : html`<div data-platform-cleanup="windows">
                ${this.windowsArtifact
                  ? html`
                      <h3>Windows package cleanup</h3>
                      <p>
                        Stop the signing process with Ctrl+C in its terminal.
                        Remove only the workshop extension, restore the previous
                        Developer mode setting and close the dedicated Chrome
                        window. From the installed package folder:
                      </p>
                      ${this
                        .renderCommand(`Set-Location "$env:USERPROFILE\\PreviewSign-evaluation\\install"
.\\install.ps1 -Command Remove -ChromeUserDataDir "$env:USERPROFILE\\PreviewSign-evaluation\\chrome"`)}
                      <p>
                        The owned helper files and user-level registration are
                        removed; your Chrome profile and unrelated files are
                        preserved.
                      </p>
                    `
                  : html`
                      <h3>Windows source cleanup</h3>
                      <p>
                        Stop the owned service with Ctrl+C in its launching
                        terminal and close the dedicated Chrome window. From the
                        matching source checkout, use the owned cleanup in the
                        ${this.sourceLink(
                          `blob/${this.previewSignSourceRef}/integrations/previewsign/docs/WINDOWS-SOURCE-REHEARSAL.md#5-stop-and-remove-only-owned-installation`,
                          'Windows source cleanup guide'
                        )}:
                      </p>
                      ${this
                        .renderCommand(`Set-Location C:\\Work\\previewsign-source
py -3 integrations/previewsign/scripts/install_windows.py remove --destination C:\\Temp\\previewsign-install --chrome-user-data-dir C:\\Temp\\previewsign-chrome`)}
                    `}
              </div>`}
        <p>
          Preserve preexisting extensions, profiles, accounts and credentials.
          Then verify ordinary WebAuthn in your account. Return to the
          workshop's final feedback step using
          <a href="/console/workshop/yubination">Return to workshop</a>.
        </p>
        <details>
          <summary>Removal and returning to the workshop</summary>
          <p>
            If removal reports changed or ambiguous owned files, stop without
            deleting unrelated configuration. If an action is pending, switch to
            its original tab; the return link does not resume an interrupted
            tool call.
          </p>
        </details>
      </section>
      ${exploreFurther}
    `;
  }
  private renderReceiptExercise() {
    return html`
      <workshop-receipt-auditor></workshop-receipt-auditor>
      ${this.sourceRepository
        ? html`<details>
            <summary>
              Explore further: independently verify a private receipt offline
            </summary>
            <p>
              The browser check above uses the server. For separate offline
              verification, use the published source and pinned Python
              dependencies in the
              ${this.sourceLink(
                'blob/main/docs/receipt-lab.md',
                'receipt verification guide'
              )}.
              The supplied public key does not establish key ownership or
              trusted enrollment. The verifier does not enforce origin/RP,
              ceremony type or user-verification (UV) policy, or prove
              execution.
            </p>
            ${this.renderCommand(`python3.13 -m venv .venv-receipt
.venv-receipt/bin/python -m pip install --only-binary=:all: --no-deps -r scripts/workshop/requirements-receipt.txt
.venv-receipt/bin/python -m pip check
.venv-receipt/bin/python scripts/workshop/verify_receipt.py "$HOME/Downloads/workshop-receipt.json" --explain`)}
            <p>
              Keep your downloaded receipt outside source control. Unsupported
              algorithms or missing evidence are not successful verification.
            </p>
          </details>`
        : html`<p>
            Optional offline source not published. The browser challenge above
            remains available.
          </p>`}
    `;
  }
}
