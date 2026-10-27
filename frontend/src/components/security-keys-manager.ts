import { shortCredentialId } from '../utils/workshop-credential';
import { LitElement, html, css, unsafeCSS } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { repeat } from 'lit/directives/repeat.js';
import {
  listWebAuthnCredentials,
  deleteWebAuthnCredential,
  renameWebAuthnCredential,
  webauthnRegisterBegin,
  webauthnRegisterComplete,
  getWebAuthnMdsInfo,
  getRegistrationEvidence,
  getPqPolicy,
  confirmPqAction,
  fetchWithAuth,
} from '../api';
import type {
  WebAuthnCredential,
  MdsInfo,
  PqPolicy,
  RegistrationEvidenceResult,
} from '../api';
import '@shoelace-style/shoelace/dist/components/alert/alert.js';
import '@shoelace-style/shoelace/dist/components/button/button.js';
import '@shoelace-style/shoelace/dist/components/dialog/dialog.js';
import '@shoelace-style/shoelace/dist/components/icon/icon.js';
import '@shoelace-style/shoelace/dist/components/icon-button/icon-button.js';
import '@shoelace-style/shoelace/dist/components/input/input.js';
import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
import '@shoelace-style/shoelace/dist/components/badge/badge.js';
import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';
import '@shoelace-style/shoelace/dist/components/copy-button/copy-button.js';
import type SlDialog from '@shoelace-style/shoelace/dist/components/dialog/dialog.js';
import type SlInput from '@shoelace-style/shoelace/dist/components/input/input.js';
import consoleStyles from '../styles/console-styles.css?inline';

function fromBase64Url(b64url: string): Uint8Array<ArrayBuffer> {
  const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/');
  const padded = b64.padEnd(b64.length + ((4 - (b64.length % 4)) % 4), '=');
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

function aaguidToUuid(b64url: string): string {
  const bytes = fromBase64Url(b64url);
  const h = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
}

function toBase64Url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

function serializeCredential(
  cred: PublicKeyCredential
): Record<string, unknown> {
  const att = cred.response as AuthenticatorAttestationResponse;
  return {
    id: cred.id,
    rawId: toBase64Url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: toBase64Url(att.clientDataJSON),
      attestationObject: toBase64Url(att.attestationObject),
    },
  };
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

const WEBAUTHN_SUPPORTED =
  typeof window !== 'undefined' &&
  typeof window.PublicKeyCredential !== 'undefined' &&
  typeof navigator.credentials?.create === 'function';

@customElement('security-keys-manager')
export class SecurityKeysManager extends LitElement {
  @property({ type: Boolean }) workshopLab = false;
  @property({ type: Boolean }) externalBusy = false;
  @property() selectedCredentialId = '';
  @property() targetedSigninCredentialId = '';
  @property() workshopProgress = '';
  private workshopActionPending = false;

  get lifecycleBusy(): boolean {
    return (
      this.isLoading ||
      this.renamingId !== null ||
      this.isRenaming ||
      this.isDeleteDialogOpen ||
      this.isDeleting ||
      this.isRegistering ||
      this.pqBusy
    );
  }

  private notifyLifecycle(): void {
    if (!this.workshopLab) return;
    this.dispatchEvent(
      new CustomEvent('workshop-passkey-busy', {
        detail: { busy: this.lifecycleBusy },
        bubbles: true,
        composed: true,
      })
    );
  }

  private publishInventory(): void {
    if (!this.workshopLab) return;
    this.dispatchEvent(
      new CustomEvent('workshop-passkey-inventory', {
        detail: {
          credentials: this.loadError
            ? []
            : this.credentials.map((credential) => ({ ...credential })),
          pqOnly: this.pqPolicy?.enabled,
          available:
            !this.loadError &&
            this.pqPolicy?.enabled === false &&
            this.workshopMigration,
        },
        bubbles: true,
        composed: true,
      })
    );
  }

  private get workshopBlocked(): boolean {
    return (
      this.workshopLab &&
      (this.externalBusy ||
        this.workshopActionPending ||
        this.lifecycleBusy ||
        !!this.loadError ||
        typeof this.pqPolicy?.enabled !== 'boolean')
    );
  }

  async refresh(): Promise<void> {
    await this.loadCredentials();
  }

  private workshopAction(
    credentialId: string,
    action: 'replace' | 'signin' | 'identify'
  ): void {
    if (
      !this.workshopLab ||
      this.workshopBlocked ||
      !this.workshopMigration ||
      this.pqPolicy?.enabled !== false
    )
      return;
    const credential = this.credentials.find(
      (item) => item.id === credentialId
    );
    if (
      !credential ||
      (action === 'replace' && credential.discoverable !== true) ||
      ![-7, -48].includes(credential.cose_algorithm ?? 0)
    )
      return;
    if (action !== 'signin' && this.pqUpgradeUnavailable(credential)) return;
    if (action === 'identify' && credential.discoverable != null) return;
    if (action === 'signin' && credentialId !== this.targetedSigninCredentialId)
      return;
    this.workshopActionPending = true;
    this.dispatchEvent(
      new CustomEvent('workshop-passkey-action', {
        detail: { credentialId, action },
        bubbles: true,
        composed: true,
      })
    );
    queueMicrotask(() => {
      this.workshopActionPending = false;
    });
  }
  @state() private workshopMigration = false;
  @state() private credentials: WebAuthnCredential[] = [];
  @state() private isLoading = true;
  @state() private loadError: string | null = null;

  // MDS metadata keyed by UUID-format AAGUID
  @state() private mdsData: Record<string, MdsInfo> = {};
  @state() private mdsLoading: Set<string> = new Set();

  @state() private pqPolicy: PqPolicy | null = null;
  @state() private pqBusy = false;
  @state() private pqError = '';
  @state() private pqSetupPrompt = '';
  @state() private emergencyRemoval = false;

  // Add flow
  @state() private isRegistering = false;
  @state() private addError: string | null = null;
  @state() private enrollmentAuthorization: string | undefined;
  @state() private registrationPhase:
    | 'idle'
    | 'confirming'
    | 'ready'
    | 'registering' = 'idle';

  // Rename flow
  @state() private renamingId: string | null = null;
  @state() private renameValue = '';
  @state() private isRenaming = false;
  @state() private renameError = '';

  // Delete flow
  @state() private deletingId: string | null = null;
  @state() private isDeleting = false;
  @state() private isDeleteDialogOpen = false;

  connectedCallback() {
    super.connectedCallback();
    this.loadCredentials();
    if (!this.workshopLab)
      void fetchWithAuth('/api/v1/webauthn/migration/status')
        .then(async (response) => {
          const status = response.ok ? await response.json() : null;
          this.workshopMigration =
            status?.enabled === true && status?.pq_only === false;
        })
        .catch(() => {
          this.workshopMigration = false;
        });
  }

  private async loadCredentials() {
    this.isLoading = true;
    this.notifyLifecycle();
    this.loadError = null;
    try {
      this.credentials = await listWebAuthnCredentials();
      this.pqError = '';
      try {
        this.pqPolicy = await getPqPolicy();
      } catch (error) {
        this.pqPolicy = null;
        this.pqError =
          error instanceof Error
            ? error.message
            : 'Could not load sign-in settings.';
      }
      if (this.workshopLab) {
        this.workshopMigration = false;
        try {
          const response = await fetchWithAuth(
            '/api/v1/webauthn/migration/status'
          );
          const status = response.ok ? await response.json() : null;
          this.workshopMigration =
            status?.enabled === true && status?.pq_only === false;
        } catch {
          this.workshopMigration = false;
        }
      }
      // Fetch MDS info for each unique AAGUID (fire-and-forget, updates reactively)
      const seen = new Set<string>();
      for (const cred of this.credentials) {
        const uuid = aaguidToUuid(cred.aaguid);
        if (!seen.has(uuid) && !this.mdsData[uuid]) {
          seen.add(uuid);
          this.fetchMdsInfo(uuid);
        }
      }
    } catch (e) {
      this.loadError =
        e instanceof Error ? e.message : 'Failed to load passkeys';
    } finally {
      this.isLoading = false;
      this.publishInventory();
      this.notifyLifecycle();
    }
  }

  private async fetchMdsInfo(uuid: string): Promise<void> {
    if (this.mdsData[uuid] !== undefined) return;
    this.mdsLoading = new Set([...this.mdsLoading, uuid]);
    try {
      const info = await getWebAuthnMdsInfo(uuid);
      this.mdsData = { ...this.mdsData, [uuid]: info };
    } catch {
      // Leave absent — renderKeyRow shows AAGUID-only fallback
    } finally {
      const next = new Set(this.mdsLoading);
      next.delete(uuid);
      this.mdsLoading = next;
    }
  }

  // --- Add flow ---

  private resetAddFlow() {
    this.enrollmentAuthorization = undefined;
    this.registrationPhase = 'idle';
    this.addError = null;
  }

  private async handleAddKey() {
    if (this.isRegistering || this.workshopLab || this.externalBusy) return;
    const name = ''; // Optional name can be edited after the native ceremony.
    this.addError = null;
    this.isRegistering = true;
    try {
      if (this.pqPolicy?.enabled && !this.enrollmentAuthorization) {
        this.registrationPhase = 'confirming';
        await this.updateComplete;
        const confirmation = await confirmPqAction({
          action: 'enroll',
          version: this.pqPolicy.version,
        });
        this.enrollmentAuthorization = confirmation.authorization_id;
        if (!this.enrollmentAuthorization)
          throw new Error(
            'Replacement authorization was not returned. Try again.'
          );
        this.registrationPhase = 'ready';
        return;
      }
      this.registrationPhase = 'registering';
      const { session_id, options } = await webauthnRegisterBegin(
        name,
        undefined,
        this.enrollmentAuthorization
      );
      // Registration begin consumes the one-use grant, even if creation is cancelled.
      this.enrollmentAuthorization = undefined;

      const opts = options as Record<string, unknown>;
      const pkOptions: PublicKeyCredentialCreationOptions = {
        rp: opts['rp'] as PublicKeyCredentialRpEntity,
        user: {
          ...(opts['user'] as { name: string; displayName: string }),
          id: fromBase64Url((opts['user'] as Record<string, string>)['id']),
        },
        challenge: fromBase64Url(opts['challenge'] as string),
        excludeCredentials: (
          (opts['excludeCredentials'] || []) as {
            type: 'public-key';
            id: string;
          }[]
        ).map((credential) => ({
          ...credential,
          id: fromBase64Url(credential.id),
        })),
        pubKeyCredParams: opts[
          'pubKeyCredParams'
        ] as PublicKeyCredentialParameters[],
        timeout: opts['timeout'] as number | undefined,
        authenticatorSelection: opts['authenticatorSelection'] as
          | AuthenticatorSelectionCriteria
          | undefined,
        attestation: opts['attestation'] as
          | AttestationConveyancePreference
          | undefined,
        extensions: opts['extensions'] as
          | AuthenticationExtensionsClientInputs
          | undefined,
      };

      const credential = (await navigator.credentials.create({
        publicKey: pkOptions,
      })) as PublicKeyCredential | null;

      if (!credential) {
        throw new Error('No credential returned by authenticator.');
      }

      // Extract previewSign ARKG output. With the generateKey request format,
      // the Yubico Authenticator returns generatedKey.{keyHandle, publicKey}
      // when running on a YubiKey 5.8+. All other authenticators return nothing.
      const extResults = credential.getClientExtensionResults() as Record<
        string,
        unknown
      >;
      const psOutput = extResults?.previewSign as
        | {
            generatedKey?: {
              keyHandle?: ArrayBuffer;
              publicKey?: ArrayBuffer;
              algorithm?: number;
            };
          }
        | undefined;
      const gk = psOutput?.generatedKey;
      const arkgSeedPubB64 = gk?.publicKey
        ? toBase64Url(gk.publicKey)
        : undefined;
      const arkgSeedKhB64 = gk?.keyHandle
        ? toBase64Url(gk.keyHandle)
        : undefined;

      const newCred = await webauthnRegisterComplete(
        session_id,
        name,
        serializeCredential(credential),
        arkgSeedPubB64,
        arkgSeedKhB64
      );

      this.credentials = [...this.credentials, newCred];
      this.resetAddFlow();
      await this.loadCredentials();
    } catch (e) {
      this.enrollmentAuthorization = undefined;
      this.registrationPhase = 'idle';
      if (e instanceof Error && e.name === 'NotAllowedError') {
        this.addError = 'Passkey operation was cancelled or timed out.';
      } else if (e instanceof Error && e.name === 'InvalidStateError') {
        this.addError =
          'This passkey is already registered. Try a different one.';
      } else if (e instanceof Error && e.name === 'NotSupportedError') {
        this.addError =
          'This browser or authenticator does not support the offered passkey algorithms. Try another authenticator.';
      } else {
        this.addError =
          e instanceof Error
            ? e.message
            : 'Registration failed. Please try again.';
      }
    } finally {
      this.isRegistering = false;
    }
  }

  // --- Rename flow ---

  private startRename(cred: WebAuthnCredential) {
    if (this.externalBusy || this.workshopBlocked) return;
    this.renamingId = cred.id;
    this.notifyLifecycle();
    this.renameValue = cred.name || '';
    this.renameError = '';
    this.updateComplete.then(() => {
      const input = this.shadowRoot?.querySelector<SlInput>(
        `#rename-input-${cred.id}`
      );
      input?.focus();
      input?.select();
    });
  }

  private cancelRename() {
    if (this.isRenaming || this.externalBusy) return;
    this.renamingId = null;
    this.renameValue = '';
    this.notifyLifecycle();
  }

  private async commitRename(credId: string) {
    if (
      this.renamingId !== credId ||
      this.isRenaming ||
      this.externalBusy ||
      this.isDeleting
    )
      return;
    const name = this.renameValue.trim();
    if (
      name ===
      (this.credentials.find((credential) => credential.id === credId)?.name ||
        '')
    ) {
      this.cancelRename();
      return;
    }
    this.isRenaming = true;
    this.notifyLifecycle();
    this.renameError = '';
    try {
      const updated = await renameWebAuthnCredential(credId, name);
      this.credentials = this.credentials.map((credential) =>
        credential.id === credId ? updated : credential
      );
      this.renamingId = null;
    } catch {
      this.renameError = 'Could not save the passkey name. Please try again.';
      if (this.workshopLab) this.renamingId = null;
    } finally {
      this.isRenaming = false;
      this.publishInventory();
      this.notifyLifecycle();
    }
  }

  // --- Delete flow ---

  private openDeleteDialog(credId: string) {
    if (this.externalBusy || this.workshopBlocked) return;
    this.deletingId = credId;
    this.emergencyRemoval = false;
    this.isDeleteDialogOpen = true;
    this.notifyLifecycle();
    this.updateComplete.then(() => {
      const dialog = this.shadowRoot?.querySelector<SlDialog>('#delete-dialog');
      dialog?.show();
    });
  }

  private closeDeleteDialog() {
    if (this.externalBusy) return;
    const dialog = this.shadowRoot?.querySelector<SlDialog>('#delete-dialog');
    dialog?.hide();
    this.isDeleteDialogOpen = false;
    this.deletingId = null;
    this.notifyLifecycle();
  }

  private async confirmDelete() {
    if (
      !this.deletingId ||
      this.isDeleting ||
      this.externalBusy ||
      (this.workshopLab &&
        (typeof this.pqPolicy?.enabled !== 'boolean' ||
          this.isLoading ||
          this.loadError))
    )
      return;
    const credentialId = this.deletingId;
    this.isDeleting = true;
    this.notifyLifecycle();
    try {
      if (this.pqPolicy?.enabled) {
        await confirmPqAction({
          action: 'remove',
          version: this.pqPolicy.version,
          credential_id: credentialId,
          emergency: this.emergencyRemoval,
        });
      } else {
        await deleteWebAuthnCredential(credentialId);
      }
      this.credentials = this.credentials.filter((c) => c.id !== credentialId);
      this.publishInventory();
      this.closeDeleteDialog();
      await this.loadCredentials();
    } catch (e) {
      this.closeDeleteDialog();
      this.pqError =
        e instanceof Error
          ? e.message
          : 'Could not remove passkey. Nothing changed.';
    } finally {
      this.isDeleting = false;
      this.notifyLifecycle();
    }
  }

  // --- Render helpers ---

  private renderMdsBadges(info: MdsInfo | undefined) {
    if (
      !info?.found ||
      info.metadata_status !== 'current' ||
      info.metadata_authenticated !== true
    )
      return '';
    const protection = info.key_protection || [];
    const label = protection.includes('secure_element')
      ? 'Model: Hardware-backed · Secure element'
      : protection.some((value) => ['hardware', 'tee'].includes(value))
        ? 'Model: Hardware-backed'
        : '';
    return label
      ? html`<sl-tooltip
          content="Authenticated FIDO metadata describes this model's key protection. It does not verify this particular credential's hardware."
          ><sl-badge class="model-protection" variant="neutral" pill
            >${label}</sl-badge
          ></sl-tooltip
        >`
      : '';
  }

  private async runPqAction(
    action: 'enable' | 'disable',
    credentialId?: string
  ) {
    if (!this.pqPolicy) return;
    this.pqBusy = true;
    this.pqError = '';
    try {
      this.pqPolicy = await confirmPqAction({
        action,
        version: this.pqPolicy.version,
        credential_id: credentialId,
        ...(action === 'enable' ? { consent: true } : {}),
      });
      this.pqSetupPrompt = '';
      await this.loadCredentials();
    } catch (error) {
      this.pqSetupPrompt = '';
      this.pqError =
        error instanceof Error && error.name === 'NotAllowedError'
          ? 'Passkey confirmation was cancelled or timed out. Sign-in protection is unchanged.'
          : error instanceof Error
            ? error.message
            : 'Passkey confirmation failed. Nothing changed.';
    } finally {
      this.pqBusy = false;
    }
  }

  private async changePqProtection() {
    const policy = this.pqPolicy;
    if (!policy || this.pqBusy) return;
    if (!policy.enabled && policy.eligible_count < 2) return;
    this.pqSetupPrompt = policy.enabled
      ? 'Confirm with a post-quantum passkey to disable post-quantum sign-in.'
      : 'Confirm with a post-quantum passkey to enable post-quantum sign-in.';
    await this.updateComplete;
    await this.runPqAction(policy.enabled ? 'disable' : 'enable');
  }

  private renderPqPolicy() {
    const policy = this.pqPolicy;
    return html`<section aria-label="Post-quantum sign-in" class="pq-policy">
      <div class="protection-heading">
        <div>
          <p class="eyebrow">Account security</p>
          <h3>Post-quantum sign-in</h3>
        </div>
        ${policy
          ? html`<sl-badge
              variant=${policy.enabled ? 'primary' : 'neutral'}
              title="Existing sessions stay signed in."
              pill
              >${policy.enabled ? 'Post-quantum enabled' : 'Standard'}</sl-badge
            >`
          : ''}
      </div>
      ${policy
        ? html`
            <p class="protection-summary">
              Use a post-quantum passkey to sign in. You need at least two
              registered post-quantum passkeys to enable this setting. Action
              approval policies are unchanged. There is no account recovery if
              you lose all your post-quantum passkeys.
            </p>
            ${policy.warning
              ? html`<sl-alert variant="warning" open
                  >${policy.warning}</sl-alert
                >`
              : ''}
            ${!policy.enabled && policy.eligible_count < 2
              ? html`<p class="supporting-text">
                  Add ${2 - policy.eligible_count} more post-quantum
                  ${policy.eligible_count === 1 ? 'passkey' : 'passkeys'} to
                  enable.
                </p>`
              : ''}
            ${this.pqSetupPrompt
              ? html`<p class="setup-prompt" role="status">
                  ${this.pqSetupPrompt}
                </p>`
              : ''}
            <sl-button
              id="pq-policy-toggle"
              variant=${policy.enabled ? 'default' : 'primary'}
              ?loading=${this.pqBusy}
              ?disabled=${this.pqBusy ||
              (!policy.enabled && policy.eligible_count < 2)}
              @click=${this.changePqProtection}
            >
              ${policy.enabled
                ? 'Disable post-quantum sign-in'
                : 'Enable post-quantum sign-in'}
            </sl-button>
          `
        : html`<p class="supporting-text">
            ${this.isLoading
              ? 'Loading sign-in protection…'
              : 'Protection status unavailable.'}
          </p>`}
      ${this.pqError
        ? html`<sl-alert variant="danger" open
            >${this.pqError}<sl-button @click=${this.loadCredentials}
              >Refresh settings</sl-button
            ></sl-alert
          >`
        : ''}
    </section>`;
  }

  private credentialAlgorithm(algorithm: number | null | undefined): string {
    return this.knownCredentialAlgorithm(algorithm) ?? 'Algorithm unavailable';
  }

  private knownCredentialAlgorithm(
    algorithm: number | null | undefined
  ): string | undefined {
    const labels: Record<number, string> = {
      [-48]: 'Post-quantum · ML-DSA-44',
      [-49]: 'Post-quantum · ML-DSA-65',
      [-50]: 'Post-quantum · ML-DSA-87',
      [-7]: 'Classical · ES256',
      [-35]: 'Classical · ES384',
      [-36]: 'Classical · ES512',
      [-8]: 'Classical · EdDSA',
      [-257]: 'Classical · RS256',
      [-37]: 'Classical · PS256',
    };
    return algorithm == null ? undefined : labels[algorithm];
  }

  private credentialName(cred: WebAuthnCredential | undefined): string {
    if (!cred) return '';
    if (cred.name) return cred.name;
    const metadata = this.mdsData[aaguidToUuid(cred.aaguid)];
    return metadata?.found &&
      metadata.metadata_status === 'current' &&
      metadata.metadata_authenticated === true
      ? metadata.description || ''
      : '';
  }

  @state() private registrationDetails: Record<
    string,
    RegistrationEvidenceResult | 'loading' | 'error'
  > = {};

  private async loadRegistrationDetails(
    id: string,
    event: Event
  ): Promise<void> {
    if (
      !(event.target as HTMLDetailsElement).open ||
      (this.registrationDetails[id] && this.registrationDetails[id] !== 'error')
    )
      return;
    this.registrationDetails = { ...this.registrationDetails, [id]: 'loading' };
    try {
      const result = await getRegistrationEvidence(id);
      this.registrationDetails = { ...this.registrationDetails, [id]: result };
    } catch {
      this.registrationDetails = { ...this.registrationDetails, [id]: 'error' };
    }
  }

  private renderRegistrationDetails(id: string) {
    const result = this.registrationDetails[id];
    return html`<details
      @toggle=${(event: Event) => this.loadRegistrationDetails(id, event)}
    >
      <summary>Saved registration details</summary>
      ${result === 'loading'
        ? html`<p role="status">Loading saved details…</p>`
        : result === 'error'
          ? html`<p role="alert">
              Registration details could not be loaded. Refresh the page to
              retry.
            </p>`
          : result && (!result.available || !result.evidence)
            ? html`<p>
                Registration details were not saved for this credential. If its
                discovery information is missing, use Identify an existing
                passkey below. That check observes the returned credential; it
                does not reconstruct registration history.
              </p>`
            : result && result.evidence
              ? html`<p>
                    Saved when this credential was registered. Retaining these
                    data does not establish attestation trust.
                  </p>
                  <h4>Saved request</h4>
                  <pre style="white-space:pre-wrap;overflow-wrap:anywhere">
${JSON.stringify(result.evidence.request, null, 2)}</pre
                  >
                  <h4>Saved response</h4>
                  <pre style="white-space:pre-wrap;overflow-wrap:anywhere">
${JSON.stringify(result.evidence.response, null, 2)}</pre
                  >
                  <h4>RP verification</h4>
                  <pre style="white-space:pre-wrap;overflow-wrap:anywhere">
${JSON.stringify(result.evidence.verification, null, 2)}</pre
                  >`
              : ''}
    </details>`;
  }

  private pqUpgradeUnavailable(credential: WebAuthnCredential): boolean {
    return (
      credential.cose_algorithm === -7 &&
      this.mdsData[aaguidToUuid(credential.aaguid)]?.pq_upgrade_supported ===
        false
    );
  }

  private renderKeyRow(cred: WebAuthnCredential) {
    const algorithmLabel = this.knownCredentialAlgorithm(cred.cose_algorithm);
    const isRenaming = this.renamingId === cred.id;
    const displayName = this.credentialName(cred);
    const uuid = aaguidToUuid(cred.aaguid);
    const mdsInfo = this.mdsData[uuid];
    const upgradeUnavailable = this.pqUpgradeUnavailable(cred);

    return html`
      <div
        class=${this.workshopLab ? 'key-row workshop-key-row' : 'key-row'}
        data-credential-id=${cred.id}
        role="group"
        aria-label=${`Passkey ${displayName || 'Unnamed passkey'}`}
      >
        ${mdsInfo?.metadata_authenticated &&
        mdsInfo.metadata_status === 'current' &&
        mdsInfo.found &&
        mdsInfo.icon
          ? html`<img
              src="${mdsInfo.icon}"
              class="key-icon-img"
              alt="${mdsInfo.description ?? 'Authenticator'}"
            />`
          : html`<sl-icon name="key" class="key-icon"></sl-icon>`}
        <div class="key-info">
          ${isRenaming
            ? html`<sl-input
                id="rename-input-${cred.id}"
                size="small"
                label="Passkey name (optional)"
                .value="${this.renameValue}"
                @sl-input="${(e: Event) =>
                  (this.renameValue = (e.target as HTMLInputElement).value)}"
                @keydown="${(e: KeyboardEvent) => {
                  if (e.key === 'Enter') this.commitRename(cred.id);
                  if (e.key === 'Escape') this.cancelRename();
                }}"
                @sl-blur="${() => this.commitRename(cred.id)}"
                ?disabled="${this.isRenaming || this.externalBusy}"
              ></sl-input>`
            : html`<button
                class="key-name"
                ?disabled=${this.externalBusy || this.workshopBlocked}
                aria-label=${displayName
                  ? `Rename ${displayName}`
                  : 'Add name for this passkey'}
                @click=${() => this.startRename(cred)}
              >
                ${displayName || 'Add name'}
              </button>`}
          <span class="key-meta">
            Added
            ${formatDate(cred.created_at)}${cred.last_used_at
              ? ` · Last used ${formatDate(cred.last_used_at)}`
              : ''}
            ${mdsInfo?.found &&
            mdsInfo.metadata_authenticated === true &&
            mdsInfo.metadata_status === 'current' &&
            mdsInfo.previewsign_supported === true
              ? html`<sl-tooltip
                  content="Authenticated FIDO metadata lists PreviewSign support for this model. This does not attest this particular device or mean this passkey is ready."
                  ><sl-badge variant="neutral" pill
                    >Supports PreviewSign</sl-badge
                  ></sl-tooltip
                >`
              : mdsInfo?.previewsign_vendor_catalog_supported === true
                ? html`<sl-tooltip
                    content="Yubico’s model documentation lists PreviewSign for this AAGUID’s 5 Series firmware 5.8 model. This is not verification of this device, MDS certification or saved passkey readiness."
                    ><sl-badge variant="neutral" pill
                      >Supports PreviewSign</sl-badge
                    ></sl-tooltip
                  >`
                : mdsInfo?.previewsign_workshop_assumption === true
                  ? html`<sl-tooltip
                      content="Workshop assumption for this preview-key AAGUID: PreviewSign support on firmware 5.8+. Not verified manufacturer, MDS or attestation evidence; saved setup may still be missing."
                      ><sl-badge variant="neutral" pill
                        >Supports PreviewSign</sl-badge
                      ></sl-tooltip
                    >`
                  : ''}
            ${cred.arkg_capable
              ? html`<sl-tooltip
                  content="PreviewSign registration metadata is complete. Verify both proofs during approval."
                >
                  <sl-badge
                    variant="neutral"
                    pill
                    style="margin-left:0.4rem;font-size:0.7rem"
                    >PreviewSign ready</sl-badge
                  >
                </sl-tooltip>`
              : ''}
          </span>
          ${this.workshopLab &&
          !upgradeUnavailable &&
          cred.discoverable !== true
            ? html`<p class="workshop-readiness">
                ${cred.discoverable === false
                  ? 'No replacement needed. Use additive enrollment rather than the replacement exercise for this non-discoverable credential.'
                  : 'Discoverability not recorded. Check eligibility before preparing this credential.'}
              </p>`
            : ''}
          ${this.workshopLab &&
          cred.discoverable == null &&
          !upgradeUnavailable &&
          [-7, -48].includes(cred.cose_algorithm ?? 0)
            ? html`<p>
                  Check eligibility with your key. The browser chooses a
                  registered passkey, which may differ from this card. Only that
                  verified credential becomes eligible; this does not replace
                  it.
                </p>
                <button
                  ?disabled=${this.workshopBlocked ||
                  !this.workshopMigration ||
                  this.pqPolicy?.enabled}
                  @click=${() => this.workshopAction(cred.id, 'identify')}
                >
                  Check upgrade eligibility
                </button>`
            : ''}
          ${this.workshopLab && upgradeUnavailable
            ? html`<p>
                This authenticator's metadata lists only classical algorithms.
                Use the supplied beta key for this exercise.
              </p>`
            : ''}
          ${this.workshopLab ? this.renderRegistrationDetails(cred.id) : ''}
          <div class="key-badges">
            ${this.workshopLab
              ? html`<span>
                  Credential ID:
                  <code>${shortCredentialId(cred.credential_id)}</code>
                  ${cred.credential_id
                    ? html`<sl-copy-button
                          .value=${cred.credential_id}
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
                          <code style="overflow-wrap:anywhere"
                            >${cred.credential_id}</code
                          >
                        </details>`
                    : ''}
                </span>`
              : ''}
            ${algorithmLabel
              ? html`<sl-badge
                  class="credential-algorithm"
                  variant="neutral"
                  pill
                  >${algorithmLabel}</sl-badge
                >`
              : ''}
            ${typeof cred.backup_eligible === 'boolean'
              ? html`<sl-tooltip
                  content="${cred.backup_eligible
                    ? 'This passkey supports backup through its passkey provider. This does not confirm it is currently backed up.'
                    : 'This passkey cannot be backed up to another device. This does not establish hardware protection.'}"
                  ><sl-badge class="credential-type" variant="neutral" pill
                    >${cred.backup_eligible
                      ? 'Synced passkey'
                      : 'Device-bound passkey'}</sl-badge
                  ></sl-tooltip
                >`
              : ''}
            ${this.renderMdsBadges(mdsInfo)}
          </div>
          ${this.workshopLab &&
          !upgradeUnavailable &&
          cred.discoverable === true &&
          [-7, -48].includes(cred.cose_algorithm ?? 0)
            ? html`<p class="workshop-replacement-explanation">
                Register a
                ${cred.cose_algorithm === -7
                  ? 'post-quantum ML-DSA-44'
                  : 'classical ES256'}
                replacement${cred.cose_algorithm === -48
                  ? ' to practice the upgrade exercise'
                  : ''}.
              </p>`
            : ''}
        </div>
        <div class="key-actions">
          ${this.workshopLab &&
          !upgradeUnavailable &&
          cred.discoverable === true &&
          [-7, -48].includes(cred.cose_algorithm ?? 0)
            ? html`<button
                ?disabled=${this.workshopBlocked ||
                !this.workshopMigration ||
                this.pqPolicy?.enabled}
                @click=${() => this.workshopAction(cred.id, 'replace')}
              >
                ${cred.cose_algorithm === -7
                  ? 'Upgrade to post-quantum'
                  : 'Prepare classical credential'}
              </button> `
            : ''}
          ${!this.workshopLab &&
          this.workshopMigration &&
          !this.pqPolicy?.enabled &&
          cred.cose_algorithm === -7 &&
          !upgradeUnavailable &&
          cred.discoverable === true
            ? html`<a
                href=${`/console/workshop/yubination/python-fido2-ml-dsa?source=${encodeURIComponent(cred.id)}`}
                >Upgrade to post-quantum</a
              >`
            : ''}
          <sl-icon-button
            name="trash"
            label=${`Remove ${displayName || 'passkey'}`}
            @click=${() => this.openDeleteDialog(cred.id)}
            ?disabled=${this.isDeleting ||
            this.externalBusy ||
            this.workshopBlocked}
          ></sl-icon-button>
        </div>
        ${this.workshopLab && this.selectedCredentialId === cred.id
          ? html`<div class="workshop-row-evidence">
              ${this.workshopProgress
                ? html`<p role="status">${this.workshopProgress}</p>`
                : ''}
              <slot name="workshop-evidence"></slot>
            </div>`
          : ''}
      </div>
    `;
  }

  private renderEmptyState() {
    return html`
      <div class="empty-state">
        <sl-icon name="shield-lock" class="empty-icon"></sl-icon>
        <p>No passkeys registered yet.</p>
        <p class="empty-hint">
          Add a passkey — hardware security keys, Touch ID, Windows Hello, and
          more — to sign in and approve actions.
        </p>
      </div>
    `;
  }

  private renderAddButton() {
    if (!WEBAUTHN_SUPPORTED) {
      return html`
        <sl-tooltip
          content="Your browser does not support passkeys. Try Chrome, Firefox, or Safari."
        >
          <sl-button variant="primary" disabled>Add passkey</sl-button>
        </sl-tooltip>
      `;
    }
    return html`
      <sl-button
        variant="primary"
        @click="${this.handleAddKey}"
        ?disabled="${this.isRegistering}"
        ?loading=${this.isRegistering}
        >${this.enrollmentAuthorization
          ? 'Create new passkey'
          : 'Add passkey'}</sl-button
      >
    `;
  }

  render() {
    const removalTarget = this.credentials.find(
      (credential) => credential.id === this.deletingId
    );
    const remainingPq =
      this.pqPolicy && removalTarget
        ? Math.max(
            0,
            this.pqPolicy.eligible_count -
              (removalTarget.pq_eligible === true ? 1 : 0)
          )
        : null;
    return html`
      ${this.workshopLab ? '' : this.renderPqPolicy()}
      <section class="passkey-inventory" aria-label="Your passkeys">
        <div class="section-header">
          <div>
            <h3>Passkeys</h3>
            <p class="section-desc">
              ${this.workshopLab
                ? 'Choose a passkey for this exercise.'
                : 'Sign in and approve actions with a passkey.'}
            </p>
          </div>
          ${this.workshopLab ? '' : this.renderAddButton()}
        </div>

        ${this.registrationPhase !== 'idle'
          ? html`<p role="status" class="registration-status">
              ${this.registrationPhase === 'confirming'
                ? 'Confirm with an existing post-quantum passkey before adding another.'
                : this.registrationPhase === 'ready'
                  ? 'Existing post-quantum passkey confirmed. Switch to your new authenticator, then choose Create new passkey.'
                  : 'Choose a passkey provider in the browser prompt.'}
            </p>`
          : ''}
        ${this.registrationPhase === 'ready'
          ? html`<sl-button size="small" @click=${this.resetAddFlow}
              >Cancel adding passkey</sl-button
            >`
          : ''}
        ${this.addError
          ? html`<sl-alert variant="danger" open>${this.addError}</sl-alert>`
          : ''}
        ${this.renameError
          ? html`<sl-alert variant="danger" open>${this.renameError}</sl-alert>`
          : ''}
        ${this.loadError
          ? html`<sl-alert variant="danger" open
              >${this.loadError}
              <sl-button
                slot="footer"
                size="small"
                @click=${() => {
                  if (!this.externalBusy && !this.lifecycleBusy)
                    void this.refresh();
                }}
                >Retry</sl-button
              ></sl-alert
            >`
          : this.isLoading
            ? html`<div class="loading"><sl-spinner></sl-spinner></div>`
            : this.credentials.length === 0
              ? this.renderEmptyState()
              : html`<div class="key-list">
                  ${repeat(
                    this.credentials,
                    (c) => c.id,
                    (c) => this.renderKeyRow(c)
                  )}
                </div>`}
      </section>

      <!-- Delete confirmation dialog -->
      <sl-dialog
        id="delete-dialog"
        label="Remove Passkey"
        @sl-hide="${() => {
          if (!this.isDeleting) this.closeDeleteDialog();
        }}"
      >
        <p>
          Remove
          <strong
            >${this.credentialName(removalTarget) || 'this passkey'}</strong
          >?
        </p>
        <p>${this.credentialAlgorithm(removalTarget?.cose_algorithm)}</p>
        <p>You will need to re-register it to use it again.</p>
        ${remainingPq !== null
          ? html`<p>
              ${remainingPq} eligible post-quantum
              ${remainingPq === 1 ? 'passkey will' : 'passkeys will'} remain.
            </p>`
          : ''}
        ${this.pqPolicy?.enabled && remainingPq !== null && remainingPq < 2
          ? html`<sl-alert variant="warning" open>
              ${remainingPq === 0
                ? 'No eligible post-quantum passkey will remain. Fresh sign-in will be unavailable, and this demo account has no recovery option.'
                : 'If you lose access to the remaining key, this demo account has no recovery option.'}
              Post-quantum sign-in stays on. Add and test a replacement.
              Emergency revocation does not enable classical sign-in.
            </sl-alert>`
          : ''}
        ${this.pqPolicy?.enabled
          ? html`<p>Confirm removal with a post-quantum passkey.</p>
              <label
                ><input
                  type="checkbox"
                  ?disabled=${this.externalBusy || this.isDeleting}
                  .checked=${this.emergencyRemoval}
                  @change=${(event: Event) => {
                    this.emergencyRemoval = (
                      event.target as HTMLInputElement
                    ).checked;
                  }}
                />
                This key is compromised. Revoke it even if fewer than two
                post-quantum passkeys remain.</label
              >`
          : ''}
        <div slot="footer" class="dialog-footer">
          <sl-button
            variant="default"
            @click="${this.closeDeleteDialog}"
            ?disabled="${this.isDeleting || this.externalBusy}"
            >Cancel</sl-button
          >
          <sl-button
            variant="danger"
            @click="${this.confirmDelete}"
            ?disabled=${this.isDeleting || this.externalBusy}
            ?loading="${this.isDeleting}"
            >Remove Key</sl-button
          >
        </div>
      </sl-dialog>
    `;
  }

  static styles = [
    unsafeCSS(consoleStyles),
    css`
      .workshop-row-evidence {
        grid-column: 1 / -1;
        min-width: 0;
      }
      .workshop-key-row .key-actions {
        width: min(18rem, 100%);
        gap: 0.5rem;
      }
      .workshop-key-row .key-actions button {
        box-sizing: border-box;
        min-height: 44px;
        min-width: 100px;
        padding: 0.65rem 0.9rem;
        font: inherit;
        line-height: 1.35;
        white-space: normal;
        word-break: normal;
        color: var(--sl-color-primary-700);
        background: var(--sl-color-neutral-0);
        border: 1px solid var(--sl-color-neutral-400);
        border-radius: 0.5rem;
        cursor: pointer;
      }
      .workshop-key-row .key-actions button:hover:not(:disabled) {
        background: var(--sl-color-primary-50);
        border-color: var(--sl-color-primary-500);
      }
      .workshop-key-row .key-actions button:focus-visible {
        outline: 3px solid var(--sl-color-primary-500);
        outline-offset: 2px;
      }
      .workshop-key-row .key-actions button:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }
      :host([hidden]) {
        display: none;
      }
      .section-desc {
        margin: 0;
        font-size: 0.875rem;
        color: var(--sl-color-neutral-600);
      }

      .loading {
        display: flex;
        justify-content: center;
        padding: 2rem;
      }

      .key-list {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
      }

      .key-icon {
        font-size: 1.25rem;
        color: var(--sl-color-neutral-500);
        flex-shrink: 0;
        margin-top: 0.1rem;
      }

      .key-icon-img {
        width: 1.5rem;
        height: 1.5rem;
        object-fit: contain;
        flex-shrink: 0;
        margin-top: 0.05rem;
      }

      .key-name:hover {
        text-decoration: underline;
      }

      .empty-state {
        text-align: center;
        padding: 2rem 1rem;
        color: var(--sl-color-neutral-500);
      }

      .empty-icon {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
        display: block;
      }

      .empty-hint {
        font-size: 0.875rem;
        max-width: 30rem;
        margin: 0 auto;
      }

      .dialog-footer {
        display: flex;
        gap: 0.5rem;
        justify-content: flex-end;
      }

      :host {
        display: block;
        min-width: 0;
      }

      .pq-policy {
        padding: 1.25rem;
        border: 1px solid var(--sl-color-neutral-200);
        border-radius: 0.75rem;
        margin-bottom: 1.75rem;
        background: var(--sl-color-neutral-0);
      }

      .protection-heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
      }
      .eyebrow {
        margin: 0 0 0.35rem;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        color: var(--sl-color-neutral-600);
        text-transform: uppercase;
      }
      .protection-heading h3 {
        margin: 0;
        font-size: 1.25rem;
      }
      .protection-summary {
        margin: 0.75rem 0;
        line-height: 1.5;
        max-width: 65ch;
      }
      .supporting-text {
        font-size: 0.875rem;
        color: var(--sl-color-neutral-600);
        line-height: 1.5;
      }
      .section-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.35rem;
      }
      .section-header h3 {
        margin: 0 0 0.25rem 0;
        font-size: 1.15rem;
      }
      .key-row {
        display: grid;
        align-items: flex-start;
        gap: 1rem;
        padding: 1rem;
        border: 1px solid var(--sl-color-neutral-200);
        border-radius: 0.65rem;
        background: var(--sl-color-neutral-0);
        grid-template-columns: 1.5rem minmax(0, 1fr) auto;
      }
      .key-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
      }
      .key-name {
        font: inherit;
        font-weight: 600;
        color: inherit;
        background: transparent;
        padding: 0;
        border: 0;
        min-height: 44px;
        overflow-wrap: anywhere;
        text-align: left;
        cursor: pointer;
      }
      .key-name:focus-visible {
        outline: 3px solid var(--sl-color-primary-500);
        outline-offset: 3px;
      }
      .key-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        align-items: center;
      }
      .key-actions sl-icon-button::part(base) {
        width: 44px;
        height: 44px;
        color: var(--sl-color-neutral-600);
      }
      .registration-status {
        line-height: 1.5;
        color: var(--sl-color-neutral-700);
      }
      .key-meta {
        font-size: 0.8125rem;
        color: var(--sl-color-neutral-600);
        line-height: 1.4;
      }
      .credential-algorithm {
        align-self: flex-start;
      }
      .key-actions {
        display: flex;
        gap: 0.3rem;
        flex-shrink: 0;
        flex-direction: column;
        align-items: stretch;
        min-width: 0;
      }
      .key-actions a {
        overflow-wrap: anywhere;
        max-width: 100%;
      }
      .key-actions sl-icon-button::part(base),
      #pq-policy-toggle::part(base) {
        min-height: 44px;
        white-space: normal;
      }
      .setup-prompt {
        padding: 0.75rem;
        border-left: 3px solid var(--sl-color-primary-500);
        line-height: 1.5;
      }
      sl-alert {
        margin: 0.75rem 0;
      }
      @media (max-width: 600px) {
        .pq-policy {
          padding: 1rem;
          margin-bottom: 1.5rem;
        }
        .protection-heading {
          align-items: flex-start;
          flex-wrap: wrap;
          gap: 0.65rem;
        }
        .section-header {
          align-items: flex-start;
          gap: 0.75rem;
          flex-wrap: wrap;
        }
        .key-row {
          grid-template-columns: 1.25rem minmax(0, 1fr) 44px;
          padding: 0.85rem;
          gap: 0.6rem;
        }
        .workshop-key-row {
          grid-template-columns: 1.25rem minmax(0, 1fr);
        }
        .workshop-key-row .key-actions {
          grid-column: 1 / -1;
          width: 100%;
        }
        .workshop-key-row .key-actions button {
          width: 100%;
        }
        .workshop-key-row .key-actions sl-icon-button {
          align-self: flex-end;
        }
        .dialog-footer {
          flex-wrap: wrap;
        }
        .dialog-footer sl-button {
          flex: 1 1 140px;
        }
      }
    `,
  ];
}
