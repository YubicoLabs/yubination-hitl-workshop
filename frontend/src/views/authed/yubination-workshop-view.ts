import { css, html } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { AuthedElement } from '../../api';
import {
  checkWorkshopConnection,
  readWorkshopCustomer,
  requestWorkshopChange,
  assignedWorkshopFixture,
  workshopChangeArguments,
  workshopOperation,
  workshopTargetStatus,
  type WorkshopOperation,
  WorkshopPreflightError,
} from './workshop-connection';
import '../../components/mcp-setup-dialog';
import '../../components/workshop-feedback';
import '@shoelace-style/shoelace/dist/components/alert/alert.js';
import '@shoelace-style/shoelace/dist/components/badge/badge.js';
import '@shoelace-style/shoelace/dist/components/button/button.js';
import '@shoelace-style/shoelace/dist/components/card/card.js';
import '@shoelace-style/shoelace/dist/components/details/details.js';
import '@shoelace-style/shoelace/dist/components/input/input.js';
import {
  renderWorkshopEvidence,
  workshopEvidenceStyles,
} from './workshop-evidence';

interface WorkshopApproval {
  id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  status: 'pending' | 'approved' | 'declined' | 'expired' | 'cancelled';
  requested_at: string;
  resolved_at: string | null;
  step_up_required: boolean;
  step_up_verified: boolean;
}

function matchesWorkshopApproval(
  approval: WorkshopApproval,
  operation: WorkshopOperation
): boolean {
  if (!approval.tool_args || typeof approval.tool_args !== 'object')
    return false;
  return (
    approval.tool_name === 'set_customer_status' &&
    Object.keys(approval.tool_args).sort().join(',') ===
      'email,expected_status,status' &&
    approval.tool_args.email === operation.email &&
    approval.tool_args.expected_status === operation.expectedStatus &&
    approval.tool_args.status === operation.targetStatus
  );
}

@customElement('yubination-workshop-view')
export class YubiNationWorkshopView extends AuthedElement {
  @state() private setupStatus: {
    state: string;
    message: string;
    contract_version?: string;
    fixture?: { email: string; status: string };
    tools?: { read: string; write: string };
  } | null = null;
  @state() private showSetupDialog = false;
  @state() private actionBusy = false;
  @state() private actionSubmitted = false;
  @state() private alreadyVipPreflightBlocked = false;
  @state() private actionMessage = '';
  @state() private actionResult: unknown = null;
  private snapshotGeneration = 0;
  private vipObservationGeneration = 0;
  private setupStatusGeneration = 0;
  private attemptUserId?: string;
  private attemptAccountId?: string;
  private recoveryGeneration = 0;
  @state() private recoveryBusy = false;
  @state() private recoveredAttempt = false;
  @state() private activeOperation: WorkshopOperation | null = null;
  @state() private restoringAttempt = false;
  private actionController?: AbortController;
  private connectionController?: AbortController;
  private readbackController?: AbortController;
  @state() private readbackBusy = false;
  @state() private readbackMessage = '';
  @state() private readbackResult: unknown = null;

  @state() private connectionBusy = false;
  @state() private connectionMessage = '';
  @state() private connectionPassed = false;
  @state() private approvalId = '';
  @state() private currentApprovalId = '';
  @state() private approval: WorkshopApproval | null = null;
  @state() private loading = false;
  @state() private loadError: string | null = null;
  static styles = [
    workshopEvidenceStyles,
    css`
      :host {
        display: block;
        width: 100%;
        max-width: 70rem;
        color: var(--sl-color-neutral-900);
      }

      * {
        box-sizing: border-box;
      }

      header {
        padding: 2.5rem clamp(1rem, 4vw, 3rem);
        border-radius: 1rem;
        color: white;
        background: linear-gradient(135deg, #14213d, #275dad);
        margin-bottom: 1.5rem;
      }

      header h1 {
        margin: 0.5rem 0;
        font-size: clamp(2rem, 5vw, 3.5rem);
        line-height: 1.05;
      }

      header p {
        max-width: 48rem;
        margin: 0;
        line-height: 1.6;
        color: #e9f2ff;
      }

      .eyebrow {
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.75rem;
        font-weight: 700;
      }

      .evidence-key,
      .actions,
      .snapshot-heading {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.75rem;
      }

      .evidence-key {
        margin: 0 0 1.5rem;
      }

      main {
        display: grid;
        gap: 1rem;
      }

      sl-card::part(base) {
        border-radius: 0.8rem;
      }

      .step {
        display: grid;
        grid-template-columns: 2.5rem minmax(0, 1fr);
        gap: 1rem;
      }

      .step-number {
        width: 2.25rem;
        height: 2.25rem;
        display: grid;
        place-items: center;
        border-radius: 50%;
        background: var(--sl-color-primary-600);
        color: white;
        font-weight: 700;
      }

      h2,
      h3 {
        margin-top: 0;
      }

      p,
      li {
        line-height: 1.6;
      }

      .action-box,
      .snapshot,
      .unavailable {
        padding: 1rem;
        border-radius: 0.6rem;
      }

      .action-box {
        background: var(--sl-color-primary-50);
        border-left: 4px solid var(--sl-color-primary-600);
      }

      .action-box dl,
      .snapshot dl {
        display: grid;
        grid-template-columns: max-content minmax(0, 1fr);
        gap: 0.5rem 1rem;
        margin: 0;
      }

      dt {
        font-weight: 700;
      }

      dd {
        margin: 0;
        overflow-wrap: anywhere;
      }

      code {
        overflow-wrap: anywhere;
      }

      .snapshot {
        background: var(--sl-color-neutral-50);
        border: 1px solid var(--sl-color-neutral-200);
        margin-top: 1rem;
      }

      .unavailable {
        background: var(--sl-color-neutral-100);
        border: 1px dashed var(--sl-color-neutral-400);
        color: var(--sl-color-neutral-700);
      }

      .load-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: end;
        gap: 0.75rem;
      }

      .privacy-note {
        font-size: 0.875rem;
        color: var(--sl-color-neutral-600);
      }

      @media (max-width: 600px) {
        .step {
          grid-template-columns: 1fr;
        }

        .load-row,
        .action-box dl,
        .snapshot dl {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  connectedCallback(): void {
    super.connectedCallback();
    void this.loadSetupStatus();
    void this.restoreAttempt();
    this.approvalId =
      new URLSearchParams(window.location.search).get('approvalId') ?? '';
  }

  private rememberAttempt(
    userId: string,
    approvalId: string | null,
    operation: WorkshopOperation | null = this.activeOperation
  ): void {
    try {
      sessionStorage.setItem(
        'workshop-attempt-v1',
        JSON.stringify({
          version: 2,
          userId,
          accountId: this.attemptAccountId,
          approvalId,
          operation,
          email: operation?.email,
          expectedStatus: operation?.expectedStatus,
          status: operation?.targetStatus,
          attempted: true,
        })
      );
    } catch {
      /* Storage may be unavailable; the active request remains single-shot. */
    }
  }

  private async restoreAttempt(): Promise<void> {
    const generation = ++this.recoveryGeneration;
    let saved;
    try {
      saved = JSON.parse(
        sessionStorage.getItem('workshop-attempt-v1') || 'null'
      );
    } catch {
      return;
    }
    if (!saved || saved.attempted !== true || typeof saved.userId !== 'string')
      return;
    const operation =
      saved.version === 2 &&
      saved.operation &&
      typeof saved.operation.email === 'string' &&
      ['standard', 'vip'].includes(saved.operation.expectedStatus) &&
      ['standard', 'vip'].includes(saved.operation.targetStatus) &&
      saved.operation.expectedStatus !== saved.operation.targetStatus
        ? (saved.operation as WorkshopOperation)
        : null;
    this.activeOperation = operation;
    this.restoringAttempt = true;
    this.actionSubmitted = true;
    try {
      const user = await this.fetchData('/api/v1/auth/users/me');
      if (!this.isConnected || generation !== this.recoveryGeneration) return;
      if (!user?.id) throw new Error('Identity unavailable');
      if (user.id !== saved.userId) {
        this.actionSubmitted = false;
        return;
      }
      this.attemptUserId = user.id;
      this.attemptAccountId =
        typeof saved.accountId === 'string' ? saved.accountId : undefined;
      this.actionSubmitted = true;
      this.actionMessage = operation
        ? `This page was reloaded after an attempt to change ${operation.email} from ${operation.expectedStatus} to ${operation.targetStatus}. The original client call cannot resume, and its execution outcome is unknown. Check the approval, requested direction and database state before another attempt.`
        : 'This page was reloaded after an attempt with an older or incomplete saved direction. The original client call cannot resume, and its execution outcome is unknown. Check the approval, requested direction and database state before another attempt.';
      if (!operation) return;
      if (
        typeof saved.approvalId !== 'string' ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
          saved.approvalId
        )
      )
        return;
      const snapshot = await this.fetchData(
        `/api/v1/approval-requests/${saved.approvalId}`
      );
      if (
        !this.isConnected ||
        generation !== this.recoveryGeneration ||
        snapshot?.id !== saved.approvalId
      )
        return;
      if (!matchesWorkshopApproval(snapshot as WorkshopApproval, operation)) {
        this.actionMessage = `This page was reloaded after an attempt to change ${operation.email} from ${operation.expectedStatus} to ${operation.targetStatus}, but the saved approval no longer matches that exact operation. The original client call cannot resume, and its execution outcome is unknown. Check approval history and database state before another attempt.`;
        return;
      }
      this.currentApprovalId = saved.approvalId;
      this.approvalId = saved.approvalId;
    } catch {
      if (!this.isConnected || generation !== this.recoveryGeneration) return;
      this.actionMessage =
        'The previous attempt could not be revalidated. Its execution outcome is unknown. Check your sign-in, approval history and database state before another attempt.';
    } finally {
      if (generation === this.recoveryGeneration) this.restoringAttempt = false;
    }
  }

  private async recoverAttempt(): Promise<void> {
    if (
      this.actionBusy ||
      this.restoringAttempt ||
      this.recoveryBusy ||
      !this.actionSubmitted ||
      !this.currentApprovalId ||
      !this.activeOperation
    )
      return;
    const id = this.currentApprovalId;
    const operation = this.activeOperation;
    const userId = this.attemptUserId;
    const accountId = this.attemptAccountId;
    const savedRaw = sessionStorage.getItem('workshop-attempt-v1');
    const session = localStorage.getItem('accessToken');
    const generation = ++this.recoveryGeneration;
    const current = () =>
      this.isConnected &&
      generation === this.recoveryGeneration &&
      this.currentApprovalId === id &&
      this.activeOperation === operation &&
      this.attemptUserId === userId &&
      this.attemptAccountId === accountId &&
      sessionStorage.getItem('workshop-attempt-v1') === savedRaw &&
      localStorage.getItem('accessToken') === session;
    this.recoveryBusy = true;
    try {
      const saved = JSON.parse(savedRaw || 'null');
      if (
        !saved ||
        saved.userId !== userId ||
        saved.approvalId !== id ||
        saved.operation?.email !== operation.email ||
        saved.operation?.expectedStatus !== operation.expectedStatus ||
        saved.operation?.targetStatus !== operation.targetStatus ||
        (saved.accountId && saved.accountId !== accountId)
      )
        throw new Error('Attempt changed');
      const user = await this.fetchData('/api/v1/auth/users/me');
      if (!current()) return;
      if (user?.id !== userId) throw new Error('Identity changed');
      const account = await this.fetchData('/api/v1/account/details');
      if (!current()) return;
      if (!account?.id || (accountId && account.id !== accountId))
        throw new Error('Account changed');
      const result = await this.fetchData(`/api/v1/workshop/attempts/${id}`);
      if (!current()) return;
      const args = result?.operation;
      if (
        result?.state !== 'completed' ||
        result.approval_id !== id ||
        result.account_id !== account.id ||
        !args ||
        Object.keys(args).sort().join(',') !== 'email,expected_status,status' ||
        args.email !== operation.email ||
        args.expected_status !== operation.expectedStatus ||
        args.status !== operation.targetStatus ||
        result.fixture?.email !== operation.email ||
        result.fixture?.status !== operation.targetStatus
      ) {
        this.actionMessage =
          'This change is not confirmed yet. Check completion again before requesting another change.';
        return;
      }
      if (!this.setupStatus) throw new Error('Setup unavailable');
      this.setupStatusGeneration++;
      this.vipObservationGeneration++;
      this.setupStatus = { ...this.setupStatus, fixture: result.fixture };
      this.actionSubmitted = false;
      this.alreadyVipPreflightBlocked = false;
      sessionStorage.removeItem('workshop-attempt-v1');
      this.recoveredAttempt = true;
      this.actionMessage = `Customer is now ${result.fixture.status}. You can request another change. This check did not repeat the request.`;
    } catch {
      if (current())
        this.actionMessage =
          'Completion could not be checked safely. Verify your sign-in and original approval, then check completion again before requesting another change.';
    } finally {
      if (generation === this.recoveryGeneration) this.recoveryBusy = false;
    }
  }

  private async loadSetupStatus(): Promise<void> {
    const refreshVipObservationGeneration = this.vipObservationGeneration;
    const generation = ++this.setupStatusGeneration;
    const result = await this.fetchData('/api/v1/workshop/status');
    if (generation !== this.setupStatusGeneration || !this.isConnected) return;
    const nextStatus =
      result &&
      typeof result.state === 'string' &&
      typeof result.message === 'string'
        ? result
        : {
            state: 'error',
            message:
              'Workshop setup status is unavailable. Retry before beginning the exercise.',
          };
    this.setupStatus = nextStatus;
    const fixture = assignedWorkshopFixture(nextStatus);
    if (
      !this.actionSubmitted &&
      this.alreadyVipPreflightBlocked &&
      refreshVipObservationGeneration === this.vipObservationGeneration &&
      fixture &&
      (!this.activeOperation || fixture.email === this.activeOperation.email)
    ) {
      this.alreadyVipPreflightBlocked = false;
      this.actionMessage = '';
    }
  }

  disconnectedCallback(): void {
    this.recoveryGeneration++;
    this.connectionController?.abort();
    this.readbackController?.abort();
    const readKey = this.shadowRoot?.querySelector<HTMLInputElement>(
      '#workshop-readback-key'
    );
    if (readKey) readKey.value = '';

    this.actionController?.abort();
    const actionInput = this.shadowRoot?.querySelector<HTMLInputElement>(
      '#workshop-action-key'
    );
    if (actionInput) actionInput.value = '';
    const input =
      this.shadowRoot?.querySelector<HTMLInputElement>('#workshop-api-key');
    if (input) input.value = '';
    super.disconnectedCallback();
  }

  private async readCustomerStatus(): Promise<void> {
    const fixture = assignedWorkshopFixture(this.setupStatus);
    if (
      this.readbackBusy ||
      this.actionBusy ||
      this.restoringAttempt ||
      !fixture
    )
      return;
    const input = this.shadowRoot?.querySelector<HTMLInputElement>(
      '#workshop-readback-key'
    );
    const key = input?.value.trim() || '';
    if (input) input.value = '';
    this.readbackResult = null;
    this.readbackMessage = '';
    if (!key) {
      this.readbackMessage =
        'Enter your workshop API key to read the current status.';
      return;
    }
    this.readbackBusy = true;
    const controller = new AbortController();
    this.readbackController = controller;
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(20000),
    ]);
    try {
      const user = await this.fetchData('/api/v1/auth/users/me', { signal });
      if (!user?.id) throw new Error('identity');
      const result = await readWorkshopCustomer(
        key,
        user.id,
        fixture.email,
        signal
      );
      if (
        !this.isConnected ||
        controller.signal.aborted ||
        this.readbackController !== controller ||
        assignedWorkshopFixture(this.setupStatus)?.email !== fixture.email
      )
        return;
      this.readbackResult = result.toolResult;
      this.readbackMessage = `Current customer status: ${result.row.status}.`;
    } catch {
      if (this.isConnected && !controller.signal.aborted)
        this.readbackMessage =
          'Could not read the customer status. Check your API key and connection, then try again.';
    } finally {
      if (this.readbackController === controller) this.readbackBusy = false;
    }
  }

  private async testConnection(): Promise<void> {
    if (this.connectionBusy || !assignedWorkshopFixture(this.setupStatus))
      return;
    const input =
      this.shadowRoot?.querySelector<HTMLInputElement>('#workshop-api-key');
    const key = input?.value ?? '';
    if (input) input.value = '';
    this.connectionController = new AbortController();
    this.connectionBusy = true;
    this.connectionPassed = false;
    this.connectionMessage = '';
    try {
      const tools = await checkWorkshopConnection(
        key,
        this.connectionController.signal
      );
      if (!this.isConnected) return;
      this.connectionPassed = true;
      this.connectionMessage = `Connection verified. Tools discovered: ${tools.join(', ')}. Next, connect your chosen client. This check did not run a tool or validate hardware approval.`;
    } catch (error) {
      if (!this.isConnected) return;
      this.connectionMessage =
        error instanceof Error && error.message.startsWith('API key rejected')
          ? error.message
          : error instanceof Error &&
              /^(Hosted access|Enter your|Workshop setup|Workshop tool|Tool discovery|MCP )/.test(
                error.message
              )
            ? error.message
            : 'Connection check failed or timed out. Check workshop setup and try again.';
    } finally {
      this.connectionBusy = false;
    }
  }

  private async requestChange(): Promise<void> {
    const fixture = assignedWorkshopFixture(this.setupStatus);
    if (
      this.actionBusy ||
      this.actionSubmitted ||
      this.alreadyVipPreflightBlocked ||
      this.restoringAttempt ||
      !fixture
    )
      return;
    this.recoveryGeneration++;
    const operation = workshopOperation(fixture);
    const input = this.shadowRoot?.querySelector<HTMLInputElement>(
      '#workshop-action-key'
    );
    const key = input?.value ?? '';
    if (input) input.value = '';
    this.actionBusy = true;
    this.recoveredAttempt = false;
    this.actionResult = null;
    this.snapshotGeneration++;
    this.activeOperation = operation;
    this.currentApprovalId = '';
    this.approvalId = '';
    this.approval = null;
    this.actionMessage =
      'Checking your account, tools, customer status and pending approvals…';
    this.actionController = new AbortController();
    try {
      const user = await this.fetchData('/api/v1/auth/users/me');
      if (!user?.id)
        throw new Error('Workshop signed-in identity could not be verified.');
      this.attemptUserId = user.id;
      this.attemptAccountId = undefined;
      const result = await requestWorkshopChange(
        key,
        user.id,
        operation,
        () => {
          this.actionSubmitted = true;
          this.rememberAttempt(user.id, null, operation);
          this.actionMessage =
            'Waiting for the MCP result. Open approval requests in a new tab and approve the exact customer change with your YubiKey. Keep this page open for the tool result.';
        },
        this.actionController.signal,
        (id) => {
          if (!this.isConnected) return;
          this.rememberAttempt(user.id, id, operation);
          this.currentApprovalId = id;
          this.approvalId = id;
          this.actionMessage =
            'Open this approval in a new tab and review the customer change before using your YubiKey. Keep this page open for the tool result.';
        }
      );
      if (!this.isConnected) return;
      this.actionResult = result.toolResult;
      if (result.verified && result.row) {
        const currentSetup = this.setupStatus;
        if (!currentSetup) return;
        this.setupStatusGeneration++;
        this.setupStatus = {
          ...currentSetup,
          fixture: {
            email: result.row.email,
            status: result.row.status,
          },
        };
        this.actionSubmitted = false;
        this.alreadyVipPreflightBlocked = false;
        sessionStorage.removeItem('workshop-attempt-v1');
        this.actionMessage = `Tool returned ${result.row.email} with status ${result.row.status}. Next, inspect the receipt and independently verify the database change. Approval alone is not execution proof. You can now request the opposite governed change.`;
      } else {
        this.actionMessage =
          'The tool returned a result, but the expected customer change was not confirmed. Inspect the result below and approval history. Do not retry before verifying database state.';
      }
    } catch (error) {
      if (!this.isConnected) return;
      if (
        error instanceof Error &&
        error.message.startsWith('Approval correlation is ambiguous')
      ) {
        this.snapshotGeneration++;
        if (this.attemptUserId)
          this.rememberAttempt(this.attemptUserId, null, this.activeOperation);
        this.loading = false;
        this.currentApprovalId = '';
        this.approvalId = '';
        this.approval = null;
      }
      if (error instanceof WorkshopPreflightError) {
        this.vipObservationGeneration++;
        this.alreadyVipPreflightBlocked = true;
        this.actionMessage = `This customer is ${error.currentStatus}, not the expected before-state. No change was submitted. Refresh setup and verify the database state before repeating this exercise.`;
      } else {
        this.actionMessage = this.actionSubmitted
          ? 'The client stopped waiting without a confirmed result. This does not cancel the server request; execution may still be pending or may have completed. Check approval history and database state before any further attempt. This page will not retry the write.'
          : error instanceof Error &&
              /^(Hosted access|Workshop |API key rejected|Enter your|MCP |Tool discovery)/.test(
                error.message
              )
            ? error.message
            : 'Preflight failed. No write submitted. Check your key and workshop setup.';
      }
    } finally {
      this.actionBusy = false;
    }
  }

  private async loadApproval(explicitId?: string): Promise<void> {
    const id = (explicitId ?? this.approvalId).trim();
    const generation = ++this.snapshotGeneration;
    const uuidPattern =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    this.approval = null;
    this.loadError = null;
    if (!id) {
      this.loadError =
        'Enter the approval request ID returned by your MCP client.';
      return;
    }
    if (!uuidPattern.test(id)) {
      this.loadError =
        'Enter the approval request ID as a UUID (for example, 123e4567-e89b-12d3-a456-426614174000), not a URL.';
      return;
    }

    this.loading = true;
    try {
      const result = await this.fetchData(
        `/api/v1/approval-requests/${encodeURIComponent(id)}`
      );
      if (generation !== this.snapshotGeneration || !this.isConnected) return;
      if (result?.id !== id) {
        this.loadError = 'The approval response did not match this request.';
        return;
      }
      this.approval = result as WorkshopApproval;
    } catch (error: unknown) {
      if (generation !== this.snapshotGeneration || !this.isConnected) return;
      this.loadError =
        error instanceof Error
          ? error.message
          : 'The approval request could not be loaded.';
    } finally {
      if (generation === this.snapshotGeneration) this.loading = false;
    }
  }

  private renderLiveSnapshot() {
    if (!this.approval) return '';
    const fixture = assignedWorkshopFixture(this.setupStatus);
    const operation =
      this.activeOperation ?? (fixture && workshopOperation(fixture));
    const expectedExercise =
      !!operation && matchesWorkshopApproval(this.approval, operation);
    return html`
      ${expectedExercise
        ? ''
        : html`<sl-alert variant="warning" open>
            This request differs from the exact documented exercise. Review the
            customer and status arguments before proceeding; this comparison is
            a guide check, not the policy enforcement point.
          </sl-alert>`}
      <section class="snapshot" aria-live="polite">
        <div class="snapshot-heading">
          <h3>Current API snapshot</h3>
          <p>Approval request: <code>${this.approval.id}</code></p>
          <sl-badge variant="primary" pill>${this.approval.status}</sl-badge>
        </div>
        <dl>
          <dt>Request</dt>
          <dd><code>${this.approval.id}</code></dd>
          <dt>Tool</dt>
          <dd><code>${this.approval.tool_name}</code></dd>
          <dt>Arguments</dt>
          <dd><code>${JSON.stringify(this.approval.tool_args)}</code></dd>
          <dt>Step-up</dt>
          <dd>
            required: ${String(this.approval.step_up_required)}; verified:
            ${String(this.approval.step_up_verified)}
          </dd>
        </dl>
        <p class="privacy-note">
          Read from the existing account-scoped approval API. This snapshot does
          not prove that the upstream tool ran or changed state.
        </p>
        <sl-button
          href=${`/console/approval/${encodeURIComponent(this.approval.id)}`}
          target="_blank"
          rel="noopener noreferrer"
          variant="default"
        >
          Open browser approval and receipt (new tab)
        </sl-button>
      </section>
    `;
  }

  render() {
    const fixture = assignedWorkshopFixture(this.setupStatus);
    const customer = fixture?.email ?? 'Awaiting your account fixture';
    const targetStatus = fixture ? workshopTargetStatus(fixture.status) : 'vip';
    const actionText =
      fixture?.status === 'vip'
        ? 'Reset customer to standard'
        : 'Request standard → vip';
    const supportPurpose =
      targetStatus === 'vip'
        ? 'Upgrade the workshop customer to VIP support.'
        : 'Return your workshop customer to standard so you can repeat the exercise.';
    const writeUnavailable = !fixture || this.alreadyVipPreflightBlocked;
    return html`
      <header>
        <div class="eyebrow">YubiNation participant lab</div>
        <h1>One action. One human decision.</h1>
        <p>
          Connect your AI agent, approve a customer change with your YubiKey,
          and check the result.
        </p>
      </header>

      <p aria-label="Governance foundation">
        Agent requests → Preloop checks policy → You approve → Tool runs → You
        check the result. Preloop is the service that checks tool requests and
        asks for approval when required.
      </p>

      <section class="snapshot" aria-label="Workshop outcomes">
        <h2>What you will accomplish</h2>
        <p>
          Start with the assigned customer at <code>standard</code>, request the
          exact governed change to <code>vip</code>, and verify the result. One
          supplied beta key is enough for this approval exercise; Post-quantum
          sign-in is not required.
        </p>
        <p>
          Browser and curl are simulations, not a native AI client. Whichever
          caller you use, approval alone does not prove execution: inspect the
          tool result and independently read the customer status.
        </p>
      </section>

      ${renderWorkshopEvidence(false)}

      <sl-alert
        open
        variant=${this.setupStatus?.state === 'ready' ? 'success' : 'primary'}
        aria-label="Workshop setup status"
      >
        ${this.setupStatus?.message ?? 'Checking workshop setup…'}
        <sl-button size="small" @click=${this.loadSetupStatus}
          >Refresh setup status</sl-button
        >
      </sl-alert>
      <main>
        <sl-card
          ><section class="step">
            <div class="step-number" aria-hidden="true">1</div>
            <div>
              <h2>Understand the exercise</h2>
              <p>
                Use the invitation’s workshop address and sign in to your own
                account. If hosted signup asks for a code, use the supplied
                code; a local deployment may not require one. Change the
                workshop customer <code>${customer}</code> from
                <code>standard</code> to <code>vip</code>. Learn who requests
                the action, what authority applies, why approval is required,
                and what the signature does and does not prove.
              </p>
              <ul>
                <li>
                  <strong>Official hosted workshop:</strong> use the event’s
                  Preloop URL and your own account.
                </li>
                <li>
                  <strong>Local, self-paced GitHub workshop:</strong> start the
                  documented deployment, then follow this same journey.
                </li>
              </ul>
              <p>
                Create a normal Preloop account and sign in. Stay in that
                account for key registration, client onboarding and approvals.
                Never use a facilitator’s credential.
              </p>
            </div>
          </section></sl-card
        >
        <sl-card
          ><section class="step">
            <div class="step-number" aria-hidden="true">2</div>
            <div>
              <h2>Register your PQC YubiKey in the browser</h2>
              <p>
                Open Security settings and select <strong>Add passkey</strong>.
                Complete the browser prompt with your workshop key, then check
                that its card shows <strong>Post-quantum</strong>. You can name
                it afterward. Registering a key does not enable post-quantum
                account protection; that setting is not required for this
                exercise.
              </p>
              <sl-button href="/console/settings/security"
                >Security settings</sl-button
              >
            </div>
          </section></sl-card
        >
        <sl-card
          ><section class="step">
            <div class="step-number" aria-hidden="true">3</div>
            <div>
              <h2>Connect your agent</h2>
              <p>
                The workshop MCP server and approval policy are already
                configured. Create an API key in this same account and follow
                the selected Codex, Claude Code or curl instructions in client
                setup. Curl demonstrates the protocol without an AI agent.
                Preloop native onboarding is also available as an optional
                setup. Keep your existing model sign-in and settings. In your
                client, inspect the prepared tools and read your sample customer
                before requesting a change.
              </p>
              <sl-button
                id="client-setup"
                @click=${() => {
                  this.showSetupDialog = true;
                }}
                >Set up your client</sl-button
              >
              <ol>
                <li>
                  Open <strong>Set up your client</strong> and choose Codex,
                  Claude Code or curl.
                </li>
                <li>
                  Follow only that method’s instructions. For API-key setup, use
                  a key from this signed-in account. For optional native
                  onboarding, review the proposed changes before applying them.
                  Never paste credentials into an agent conversation or
                  feedback.
                </li>
                <li>
                  Check that your client can see
                  <code>get_customer_status</code> and
                  <code>set_customer_status</code>. Both connection methods then
                  use the same read and approval steps below. A tools list alone
                  does not prove that a request ran.
                </li>
              </ol>
              <details>
                <summary>Connection trouble</summary>
                <p>
                  If either tool is missing, check your account and the
                  displayed endpoint, then ask the facilitator. If native
                  onboarding is unavailable, use the API-key instructions first
                  in setup.
                </p>
              </details>
              <sl-button href="/console/tools"
                >Inspect tools and policy</sl-button
              >
              <section class="snapshot" aria-label="Test MCP connection">
                <h3>API-key connection test</h3>
                <sl-button href="/console/settings/api-keys"
                  >Create an API key</sl-button
                >
                <p>
                  Check your API key and discover the workshop tools before
                  configuring a client. This does not change customer data.
                </p>
                <label for="workshop-api-key">Workshop API key</label>
                <input
                  id="workshop-api-key"
                  type="password"
                  autocomplete="off"
                  spellcheck="false"
                  style="display:block;width:100%;padding:0.75rem;margin:0.5rem 0"
                  ?disabled=${this.connectionBusy}
                />
                <p class="privacy-note">
                  Sent only to this site to check your account and connect to
                  MCP. Not saved; cleared when you start the check.
                </p>
                <sl-button
                  id="test-connection"
                  variant="primary"
                  ?loading=${this.connectionBusy}
                  ?disabled=${this.connectionBusy || !fixture}
                  @click=${this.testConnection}
                  >Test connection</sl-button
                >
                ${this.connectionMessage
                  ? html`<sl-alert
                      open
                      variant=${this.connectionPassed ? 'success' : 'danger'}
                      role="status"
                      >${this.connectionMessage}</sl-alert
                    >`
                  : ''}
              </section>
              <p>
                Confirm <code>get_customer_status</code> and
                <code>set_customer_status</code> are visible. If either is
                missing, resolve setup before requesting a change. Inspect the
                configured allow rule for the bounded read and the approval rule
                and key-verification workflow for the write.
              </p>
              <p>
                A Codex or Claude Code permission prompt permits that client to
                call a tool. It is separate from Preloop’s approval and does not
                replace your PQC YubiKey decision.
              </p>
            </div>
          </section></sl-card
        >
        <sl-card
          ><section class="step">
            <div class="step-number" aria-hidden="true">4</div>
            <div>
              <h2>Request the exact customer change</h2>
              <section aria-label="Native agent request">
                <h3>Request from your connected agent</h3>
                <p>
                  Use the client connection you just checked, whether native or
                  manual. Keep that client running through the read, request,
                  approval and returned result below.
                </p>
                ${fixture
                  ? html`<p>
                      First call <code>get_customer_status</code> with
                      <code>${JSON.stringify({ email: fixture.email })}</code>.
                      This permitted read needs no Preloop approval; your client
                      may still ask for tool permission. Confirm the returned
                      status is <code>${fixture.status}</code> before requesting
                      the change. If it differs from the shown before-state,
                      stop and check the existing approval before another
                      request.
                    </p>`
                  : html`<p>
                      Resolve workshop setup before calling
                      <code>get_customer_status</code>. The ready account
                      provides the assigned customer email; do not call the tool
                      with empty arguments.
                    </p>`}
                <sl-details
                  summary="Why the read is allowed but the write needs approval"
                >
                  <p>
                    The configured allow rule applies only to
                    <code>get_customer_status</code>. The server restricts the
                    read to the fixture assigned to your authenticated account.
                    A customer argument cannot grant access to another account’s
                    fixture.
                  </p>
                  <p>
                    <code>set_customer_status</code> remains subject to its
                    approval workflow. The read rule does not allow arbitrary
                    SQL or infer permission from a SELECT prefix. Inspect both
                    configured rules in Tools; Preloop evaluates them when each
                    request arrives.
                  </p>
                </sl-details>
                <div class="action-box">
                  <p><strong>Tool:</strong> <code>set_customer_status</code></p>
                  <p>
                    <strong>Change:</strong> <code>${customer}</code>:
                    <code>${fixture?.status ?? 'standard'}</code> →
                    <code>${targetStatus}</code>
                  </p>
                </div>
                <p>
                  Ask your client to invoke this governed tool once with the
                  arguments below. The server enforces your account’s assigned
                  customer and the expected before-state. The justification
                  states your purpose; it does not grant authority.
                </p>
                ${fixture
                  ? html`<pre
                      style="white-space: pre-wrap; overflow-wrap: anywhere"
                    ><code id="workshop-write-arguments">${JSON.stringify(
                      workshopChangeArguments(fixture.email, fixture.status),
                      null,
                      2
                    )}</code></pre>`
                  : html`<p>
                      Refresh setup status to obtain your assigned customer. If
                      your account requires migration review, ask the
                      facilitator; do not reuse another participant’s target.
                    </p>`}
                <p>
                  Preloop records the caller-supplied justification separately.
                  The approved action binds the exact customer and status
                  arguments; account isolation is enforced at execution.
                </p>
                <p>
                  Open the approval link if your client provides one. Otherwise,
                  open Preloop approval requests while the client waits; keep
                  the client session running. Check the requester, purpose,
                  matched policy, customer and exact status change. Approve only
                  the intended action, then complete the key prompt.
                </p>
                <sl-button
                  href="/console/approvals"
                  target="_blank"
                  rel="noopener noreferrer"
                  >Open approval requests (new tab)</sl-button
                >
              </section>
              <section
                class="snapshot"
                aria-label="Browser workshop simulation"
              >
                <h3>Browser simulation (alternative)</h3>
                <p>
                  This page can make the same governed MCP call as curl. It
                  simulates the caller. Choose this alternative instead of the
                  native request above; do not submit both for the same change.
                </p>
                <p>
                  <strong>Change:</strong> ${customer}:
                  ${fixture?.status ?? 'standard'} → ${targetStatus}.
                  <strong>Purpose:</strong> ${supportPurpose}
                </p>
                <label for="workshop-action-key">Your workshop API key</label>
                <input
                  id="workshop-action-key"
                  type="password"
                  autocomplete="off"
                  spellcheck="false"
                  style="display:block;width:100%;padding:0.75rem;margin:0.5rem 0"
                  ?disabled=${this.actionBusy ||
                  this.actionSubmitted ||
                  this.restoringAttempt ||
                  writeUnavailable}
                />
                <p class="privacy-note">
                  Not saved. Cleared when you start. This first reads the
                  customer and checks pending approvals, then requests the exact
                  change once. Your YubiKey approval happens separately.
                </p>
                <sl-button
                  id="request-change"
                  variant="primary"
                  ?disabled=${this.actionBusy ||
                  this.actionSubmitted ||
                  this.restoringAttempt ||
                  writeUnavailable}
                  ?loading=${this.actionBusy}
                  @click=${this.requestChange}
                  >${actionText}</sl-button
                >
                <sl-button
                  href="/console/approvals"
                  target="_blank"
                  rel="noopener noreferrer"
                  >Open approval requests in a new tab</sl-button
                >
                ${this.currentApprovalId
                  ? html`<p>
                      <a
                        id="current-approval"
                        href=${`/console/approval/${this.currentApprovalId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        >Open this approval (new tab)</a
                      >
                    </p>`
                  : ''}
                ${this.actionSubmitted &&
                !this.actionBusy &&
                this.currentApprovalId &&
                this.activeOperation
                  ? html`<sl-button
                      id="recover-attempt"
                      ?disabled=${this.restoringAttempt || this.recoveryBusy}
                      ?loading=${this.recoveryBusy}
                      @click=${this.recoverAttempt}
                      >Check completion</sl-button
                    >`
                  : ''}
                ${this.actionSubmitted &&
                !this.actionBusy &&
                this.currentApprovalId &&
                this.activeOperation
                  ? html`<p class="privacy-note">
                      Check completion is read-only. It does not repeat the
                      request.
                    </p>`
                  : ''}
                ${this.recoveredAttempt
                  ? html`<p class="privacy-note">
                      The original client result is unavailable.
                    </p>`
                  : ''}
                ${this.actionMessage
                  ? html`<p role="status">${this.actionMessage}</p>`
                  : ''}
                ${this.actionResult
                  ? html`<sl-details summary="Actual MCP tool result" open>
                      <pre style="white-space:pre-wrap">
${JSON.stringify(this.actionResult, null, 2)}</pre
                      >
                    </sl-details>`
                  : ''}
              </section>
              <p>
                Do not retry a pending or timed-out write blindly. Check the
                approval and execution status first. On this page, only the
                explicit browser request above submits a write. The page never
                approves for you.
              </p>
            </div>
          </section></sl-card
        >
        <sl-card>
          <section class="step">
            <div class="step-number" aria-hidden="true">5</div>
            <div>
              <h2>Verify what happened</h2>
              <ol id="verify-outcome-steps">
                <li>
                  Return to your original client and inspect the exact tool
                  result. For the browser exercise, keep this tab open and read
                  <strong>Actual MCP tool result</strong>. A successful approval
                  alone does not prove execution.
                </li>
                <li>
                  Run <code>get_customer_status</code> again with your assigned
                  email: <code>${JSON.stringify({ email: customer })}</code>.
                  Confirm the returned status is <code>${targetStatus}</code>
                  and compare it with the before-state from step 4.
                </li>
                <li>
                  For the optional cryptographic check, follow
                  <a
                    href="/console/workshop/yubination/receipt-verification"
                    target="_blank"
                    rel="noopener"
                    >Verify an approval receipt (new tab)</a
                  >
                  to inspect and independently verify your receipt.
                </li>
              </ol>

              <section aria-label="Browser status readback">
                <h3>Check in this browser instead</h3>
                <label for="workshop-readback-key">Your workshop API key</label>
                <input
                  id="workshop-readback-key"
                  type="password"
                  autocomplete="off"
                  spellcheck="false"
                  style="display:block;width:100%;padding:0.75rem;margin:0.5rem 0"
                  ?disabled=${this.readbackBusy}
                />
                <sl-button
                  id="read-customer-status"
                  ?loading=${this.readbackBusy}
                  ?disabled=${this.readbackBusy ||
                  this.actionBusy ||
                  this.restoringAttempt ||
                  !fixture}
                  @click=${this.readCustomerStatus}
                  >Check current status</sl-button
                >
                <p>Read only. Your key is cleared when the check starts.</p>
                ${this.readbackMessage
                  ? html`<p role="status">${this.readbackMessage}</p>`
                  : ''}
                ${this.readbackResult
                  ? html`<sl-details summary="Status response">
                      <pre aria-label="Actual status read result">
${JSON.stringify(this.readbackResult, null, 2)}</pre
                      >
                    </sl-details>`
                  : ''}
              </section>
              <p>
                The browser exercise links its own approval below. Other clients
                may show an approval link in their response. If the original
                call was interrupted, check the existing approval and database
                state before another attempt; this page does not reconstruct a
                lost tool result.
              </p>
              ${this.currentApprovalId
                ? html`<p>
                      <a
                        href=${`/console/approval/${this.currentApprovalId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        >Open this approval and receipt (new tab)</a
                      >
                    </p>
                    <sl-button
                      ?loading=${this.loading}
                      @click=${() => this.loadApproval(this.currentApprovalId)}
                      >Refresh approval snapshot</sl-button
                    >`
                : ''}
              ${this.loadError
                ? html`<sl-alert variant="danger" open
                    >${this.loadError}</sl-alert
                  >`
                : ''}
              ${this.renderLiveSnapshot()}
            </div>
          </section>
        </sl-card>

        <sl-card>
          <section class="step">
            <div class="step-number" aria-hidden="true">6</div>
            <div>
              <h2>Share feedback</h2>
              <workshop-feedback></workshop-feedback>
            </div>
          </section>
        </sl-card>
        <sl-card>
          <section aria-labelledby="optional-labs-title">
            <h2 id="optional-labs-title">Optional challenges</h2>
            <p>
              Choose a challenge after completing the main exercise. Feedback is
              optional.
            </p>
            <ul>
              <li>
                <a
                  href="/console/workshop/yubination/python-fido2-ml-dsa"
                  target="_blank"
                  rel="noopener"
                  >Upgrade to a post-quantum passkey (new tab)</a
                >
              </li>
              <li>
                <a
                  href="/console/workshop/yubination/previewsign"
                  target="_blank"
                  rel="noopener"
                  >PreviewSign (new tab)</a
                >
                <sl-badge variant="neutral" pill>Experimental</sl-badge>
              </li>
              <li>
                <a
                  href="/console/workshop/yubination/receipt-verification"
                  target="_blank"
                  rel="noopener"
                  >Verify an approval receipt (new tab)</a
                >
              </li>
              <li>
                <a
                  href="/console/workshop/yubination/pq-authentication"
                  target="_blank"
                  rel="noopener"
                  >Protect your sign-in (new tab)</a
                >
              </li>
              <li>
                <span>Inspect agent access</span>
                <sl-badge variant="neutral" pill>Coming soon</sl-badge>
              </li>
            </ul>
          </section>
        </sl-card>
      </main>
      <mcp-setup-dialog
        .open=${this.showSetupDialog}
        @close=${() => {
          this.showSetupDialog = false;
        }}
      ></mcp-setup-dialog>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'yubination-workshop-view': YubiNationWorkshopView;
  }
}
