import { approvalDeadline } from '../utils/approval-time';
import { formatRelativeTime } from '../utils/date';
import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import '@shoelace-style/shoelace/dist/components/dropdown/dropdown.js';
import '@shoelace-style/shoelace/dist/components/menu/menu.js';
import '@shoelace-style/shoelace/dist/components/menu-item/menu-item.js';
import '@shoelace-style/shoelace/dist/components/icon-button/icon-button.js';
import '@shoelace-style/shoelace/dist/components/divider/divider.js';
import '@shoelace-style/shoelace/dist/components/icon/icon.js';
import '@shoelace-style/shoelace/dist/components/badge/badge.js';
import '@shoelace-style/shoelace/dist/components/button/button.js';
import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
import './theme-switcher.ts';
import * as api from '../api';
import { Router } from '@vaadin/router';
import { unifiedWebSocketManager } from '../services/unified-websocket-manager';

interface UserDetails {
  username: string;
  email: string;
  full_name: string;
}

interface FlowExecution {
  id: string;
  flow_id: string;
  flow_name?: string;
  status: string;
  start_time: string;
  end_time: string | null;
}

interface ApprovalRequest {
  id: string;
  tool_name: string;
  tool_args?: Record<string, unknown>;
  status: 'pending' | 'approved' | 'declined' | 'expired' | 'cancelled';
  requested_at: string;
  expires_at?: string;
  execution_id?: string;
  agent_reasoning?: string;
  step_up_required?: boolean;
  step_up_verified?: boolean;
  step_up_protocol?: string | null;
  approval_token?: string | null;
}

interface UserNotification {
  id: string;
  type:
    | 'team_added'
    | 'team_removed'
    | 'policy_added'
    | 'policy_removed'
    | 'role_changed'
    | 'system';
  title: string;
  message: string;
  created_at: string;
  read: boolean;
  metadata?: Record<string, unknown>;
}

// Bundle the essential header icon so it works without a remote icon CDN.
const NOTIFICATION_ICON =
  'data:image/svg+xml,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></svg>'
  );

const PROFILE_ICON =
  'data:image/svg+xml,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor"><path d="M11 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0"/><path fill-rule="evenodd" d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8m8-7a7 7 0 0 0-5.468 11.37C3.242 11.226 4.805 10 8 10s4.757 1.225 5.468 2.37A7 7 0 0 0 8 1"/></svg>'
  );

@customElement('console-header')
export class ConsoleHeader extends LitElement {
  @state()
  private _user: UserDetails | null = null;

  @state()
  private _runningExecutions: FlowExecution[] = [];

  @state()
  private _pendingApprovals: ApprovalRequest[] = [];

  @state()
  private _userNotifications: UserNotification[] = [];

  @state()
  private _processingApproval: string | null = null;

  @state()
  private _passkeyNudge: 'none' | 'setup' | 'backup' = 'none';

  private static readonly _NUDGE_SETUP_KEY = 'passkey-nudge-setup-dismissed';
  private static readonly _NUDGE_BACKUP_KEY = 'passkey-nudge-backup-dismissed';

  private unsubscribeFlow?: () => void;
  private unsubscribeApprovals?: () => void;
  private unsubscribeNotifications?: () => void;

  // Track notification IDs to prevent duplicates
  private shownExecutionNotifications: Set<string> = new Set();
  private shownApprovalNotifications: Set<string> = new Set();

  static styles = css`
    :host {
      display: block;
    }
    .header-container {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      padding: 0.4rem;
      border-bottom: 1px solid var(--sl-color-neutral-200);
    }
    .nav-toggle {
      display: flex;
      align-items: center;
      margin-right: auto;
    }
    .nav-toggle sl-icon-button {
      font-size: 1.5rem;
    }
    .user-menu {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .user-menu sl-icon-button {
      font-size: 1.8rem;
    }
    .theme-switcher-container {
      padding: 0.5rem 1rem;
    }
    .user-info {
      padding: 0.5rem 1rem;
      line-height: 1.4;
    }
    .user-name {
      font-weight: bold;
    }
    .user-email {
      color: var(--sl-color-neutral-500);
    }
    .notification-button {
      position: relative;
    }
    .notification-badge {
      position: absolute;
      top: -4px;
      right: -4px;
      min-width: 18px;
      height: 18px;
      padding: 0 4px;
      font-size: 0.7rem;
      font-weight: 600;
      line-height: 18px;
      text-align: center;
      color: white;
      background-color: var(--sl-color-danger-500);
      border-radius: 9px;
    }
    .notification-dropdown {
      min-width: 380px;
      max-width: 420px;
      max-height: 500px;
      overflow-y: auto;
      background: var(--sl-color-neutral-0);
      border: 1px solid var(--sl-color-neutral-200);
      border-radius: var(--sl-border-radius-medium);
      box-shadow: var(--sl-shadow-large);
    }
    .notification-section {
      border-bottom: 1px solid var(--sl-color-neutral-100);
    }
    .notification-section:last-child {
      border-bottom: none;
    }
    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem 1rem;
      background-color: var(--sl-color-neutral-50);
      border-bottom: 1px solid var(--sl-color-neutral-100);
    }
    .section-title {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-weight: 600;
      font-size: 0.875rem;
      color: var(--sl-color-neutral-700);
    }
    .section-count {
      font-size: 0.75rem;
      color: var(--sl-color-neutral-500);
    }
    .section-link {
      font-size: 0.75rem;
      color: var(--sl-color-primary-600);
      text-decoration: none;
      cursor: pointer;
    }
    .section-link:hover {
      text-decoration: underline;
    }
    .execution-list,
    .approval-list,
    .notification-list {
      max-height: 200px;
      overflow-y: auto;
    }
    .execution-item,
    .approval-item,
    .notification-item {
      padding: 0.75rem 1rem;
      cursor: pointer;
      border-bottom: 1px solid var(--sl-color-neutral-50);
    }
    .execution-item:last-child,
    .approval-item:last-child,
    .notification-item:last-child {
      border-bottom: none;
    }
    .execution-item:hover,
    .approval-item:hover,
    .notification-item:hover {
      background-color: var(--sl-color-neutral-50);
    }
    .execution-name,
    .approval-name,
    .notification-title {
      font-weight: 500;
      margin-bottom: 0.25rem;
      font-size: 0.875rem;
    }
    .execution-time,
    .approval-time,
    .notification-time {
      font-size: 0.75rem;
      color: var(--sl-color-neutral-500);
    }
    .approval-actions {
      display: flex;
      gap: 0.5rem;
      margin-top: 0.5rem;
    }
    .approval-actions sl-button {
      font-size: 0.75rem;
    }
    .notification-item.unread {
      background-color: var(--sl-color-primary-50);
    }
    .notification-item.unread::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 3px;
      background-color: var(--sl-color-primary-500);
    }
    .notification-item {
      position: relative;
    }
    .no-items {
      padding: 1rem;
      text-align: center;
      color: var(--sl-color-neutral-500);
      font-size: 0.875rem;
    }
    .empty-state {
      padding: 2rem 1rem;
      text-align: center;
      color: var(--sl-color-neutral-500);
    }
    .empty-state sl-icon {
      font-size: 2rem;
      margin-bottom: 0.5rem;
      opacity: 0.5;
    }
    .theme-switcher-container {
      text-align: center;
    }
    .passkey-nudge {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.5rem 1rem;
      background: var(--sl-color-primary-50);
      border-bottom: 1px solid var(--sl-color-primary-200);
      font-size: var(--sl-font-size-small);
      color: var(--sl-color-primary-900);
    }
    .passkey-nudge span {
      flex: 1;
    }
    .passkey-nudge a {
      color: var(--sl-color-primary-700);
      font-weight: 600;
      text-decoration: none;
      white-space: nowrap;
    }
    .passkey-nudge a:hover {
      text-decoration: underline;
    }
  `;

  private timingInterval?: ReturnType<typeof setInterval>;

  async connectedCallback() {
    super.connectedCallback();
    this.timingInterval = setInterval(() => this.requestUpdate(), 1000);
    this.fetchUserDetails();
    this.connectToFlowUpdates();
    this.connectToApprovalUpdates();
    this.connectToNotificationUpdates();
    this.loadRunningExecutions();
    this.loadPendingApprovals();
    this.loadUserNotifications();
    this._checkPasskeyNudge();
    // Request desktop notification permission when console loads.
    // Browsers may require a user gesture; if so, user can click the bell icon.
    this.requestNotificationPermission();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearInterval(this.timingInterval);
    this.unsubscribeFlow?.();
    this.unsubscribeApprovals?.();
    this.unsubscribeNotifications?.();
  }

  private async loadRunningExecutions() {
    try {
      this._runningExecutions = await api.getFlowExecutions({
        limit: 10,
        status: ['PENDING', 'INITIALIZING', 'STARTING', 'RUNNING'],
      });
    } catch (error) {
      console.error('Failed to load running executions:', error);
    }
  }

  private async loadPendingApprovals() {
    try {
      const approvals = await api.listApprovalRequests({ status: 'pending' });
      this._pendingApprovals = approvals.map((approval: any) => ({
        id: approval.id,
        tool_name: approval.tool_name,
        tool_args: approval.tool_args || {},
        status: approval.status,
        requested_at: approval.requested_at,
        expires_at: approval.expires_at,
        execution_id: approval.execution_id,
        agent_reasoning: approval.agent_reasoning,
        step_up_required: approval.step_up_required,
        step_up_verified: approval.step_up_verified,
        step_up_protocol: approval.step_up_protocol,
        approval_token: approval.approval_token,
      }));
    } catch (error) {
      console.error('Failed to load pending approvals:', error);
    }
  }

  private async loadUserNotifications() {
    // TODO: Implement when backend API is available
    // For now, notifications will only come through WebSocket
    try {
      // const notifications = await api.getUserNotifications();
      // this._userNotifications = notifications;
    } catch (error) {
      console.error('Failed to load user notifications:', error);
    }
  }

  private async _checkPasskeyNudge(): Promise<void> {
    try {
      const features = await api.getFeatures();
      if (features.features['webauthn_login'] !== true) return;

      const setupDismissed = localStorage.getItem(
        ConsoleHeader._NUDGE_SETUP_KEY
      );
      const backupDismissed = localStorage.getItem(
        ConsoleHeader._NUDGE_BACKUP_KEY
      );

      const resp = await api.fetchWithAuth('/api/v1/webauthn/credentials');
      if (!resp.ok) return;
      const creds: unknown[] = await resp.json();

      if (creds.length === 0 && !setupDismissed) {
        this._passkeyNudge = 'setup';
      } else if (creds.length === 1 && !backupDismissed) {
        this._passkeyNudge = 'backup';
      }
    } catch {
      // Best-effort — never break the header
    }
  }

  private _dismissNudge(): void {
    const key =
      this._passkeyNudge === 'setup'
        ? ConsoleHeader._NUDGE_SETUP_KEY
        : ConsoleHeader._NUDGE_BACKUP_KEY;
    localStorage.setItem(key, '1');
    this._passkeyNudge = 'none';
  }

  private _renderNudge() {
    if (this._passkeyNudge === 'none') return '';
    const message =
      this._passkeyNudge === 'setup'
        ? 'Secure your account with a passkey.'
        : 'Add a backup passkey in case you lose access to your primary one.';
    return html`
      <div class="passkey-nudge">
        <sl-icon name="key"></sl-icon>
        <span>${message}</span>
        <a
          href="/console/settings/security"
          @click=${(e: Event) => {
            e.preventDefault();
            Router.go('/console/settings/security');
          }}
          >Set up now →</a
        >
        <sl-icon-button
          name="x-lg"
          label="Dismiss"
          @click=${this._dismissNudge}
        ></sl-icon-button>
      </div>
    `;
  }

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

  private async _runArkgCeremony(
    approvalId: string,
    token: string
  ): Promise<void> {
    const beginResp = await fetch(
      `/approval/${approvalId}/step-up/arkg/begin?token=${encodeURIComponent(token)}`,
      { method: 'POST' }
    );
    if (!beginResp.ok) {
      const err = await beginResp.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to start ARKG verification');
    }
    const {
      credential_id_b64,
      seed_kh_b64,
      additional_args_b64,
      tbs_b64,
      rp_id,
    } = await beginResp.json();

    const publicKey: PublicKeyCredentialRequestOptions = {
      challenge: this._fromBase64Url(tbs_b64),
      rpId: rp_id,
      allowCredentials: [
        { type: 'public-key', id: this._fromBase64Url(credential_id_b64) },
      ],
      timeout: 60000,
      extensions: {
        previewSign: {
          signByCredential: {
            [credential_id_b64]: {
              keyHandle: this._fromBase64Url(seed_kh_b64),
              tbs: this._fromBase64Url(tbs_b64),
              additionalArgs: this._fromBase64Url(additional_args_b64),
            },
          },
        },
      } as AuthenticationExtensionsClientInputs,
    };

    const credential = (await navigator.credentials.get({
      publicKey,
    })) as PublicKeyCredential;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ext = (credential as any).getClientExtensionResults() as Record<
      string,
      unknown
    >;
    const previewResult = ext['previewSign'] as
      | Record<string, unknown>
      | undefined;
    if (!previewResult?.['signature']) {
      throw new Error(
        'previewSign extension did not return a signature — YubiKey 5.8+ required'
      );
    }
    const signatureB64 = this._toBase64Url(
      previewResult['signature'] as ArrayBuffer
    );

    const completeResp = await fetch(
      `/approval/${approvalId}/step-up/arkg/complete?token=${encodeURIComponent(token)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signature_b64: signatureB64 }),
      }
    );
    if (!completeResp.ok) {
      const err = await completeResp.json().catch(() => ({}));
      throw new Error(err.detail || 'ARKG signature verification failed');
    }
  }

  private async handleApprove(approvalId: string, event: Event) {
    event.stopPropagation();
    const approval = this._pendingApprovals.find((a) => a.id === approvalId);
    if (approval?.step_up_required && !approval.step_up_verified) {
      // Any unverified step-up requires the full ceremony UI on the detail page
      window.location.href = `/console/approval/${approvalId}`;
      return;
    }
    this._processingApproval = approvalId;
    try {
      await api.approveRequest(approvalId);
      this._pendingApprovals = this._pendingApprovals.filter(
        (a) => a.id !== approvalId
      );
    } catch (error) {
      console.error('Failed to approve request:', error);
    } finally {
      this._processingApproval = null;
    }
  }

  private async handleDecline(approvalId: string, event: Event) {
    event.stopPropagation();
    this._processingApproval = approvalId;
    try {
      await api.declineRequest(approvalId);
      this._pendingApprovals = this._pendingApprovals.filter(
        (a) => a.id !== approvalId
      );
    } catch (error) {
      console.error('Failed to decline request:', error);
    } finally {
      this._processingApproval = null;
    }
  }

  private markNotificationAsRead(notificationId: string) {
    this._userNotifications = this._userNotifications.map((n) =>
      n.id === notificationId ? { ...n, read: true } : n
    );
    // TODO: Call API to mark as read when backend supports it
    // api.markNotificationRead(notificationId);
  }

  private get totalNotificationCount(): number {
    const unreadNotifications = this._userNotifications.filter(
      (n) => !n.read
    ).length;
    return (
      this._runningExecutions.length +
      this._pendingApprovals.length +
      unreadNotifications
    );
  }

  private connectToFlowUpdates() {
    this.unsubscribeFlow = unifiedWebSocketManager.subscribe(
      'flow_executions',
      (message) => {
        console.log('Console header received flow update:', message);

        // Handle new execution
        if (message.type === 'execution_started') {
          const newExecution: FlowExecution = {
            id: message.execution_id,
            flow_id: message.flow_id,
            status: message.payload?.status || 'PENDING',
            start_time: message.timestamp,
            end_time: null,
            flow_name: message.payload?.flow_name,
          };

          // Add to running executions if not already there
          const exists = this._runningExecutions.some(
            (exec) => exec.id === newExecution.id
          );
          if (!exists) {
            this._runningExecutions = [
              newExecution,
              ...this._runningExecutions,
            ];
            // Show desktop notification for new execution
            this.showExecutionNotification(newExecution);
          }
        }

        // Handle status updates
        if (message.type === 'status_update' && message.execution_id) {
          const status = message.payload?.status;
          const executionIndex = this._runningExecutions.findIndex(
            (exec) => exec.id === message.execution_id
          );

          if (executionIndex !== -1) {
            // If status is no longer running/pending, remove from list
            if (
              status !== 'RUNNING' &&
              status !== 'PENDING' &&
              status !== 'STARTING' &&
              status !== 'INITIALIZING'
            ) {
              const finishedExecution = this._runningExecutions[executionIndex];
              this._runningExecutions = [
                ...this._runningExecutions.slice(0, executionIndex),
                ...this._runningExecutions.slice(executionIndex + 1),
              ];
              // Show desktop notification for finished execution
              this.showExecutionFinishedNotification(finishedExecution, status);
            } else {
              // Update the execution
              const updatedExecution = {
                ...this._runningExecutions[executionIndex],
                status: status,
                end_time: message.payload?.end_time || null,
              };
              this._runningExecutions = [
                ...this._runningExecutions.slice(0, executionIndex),
                updatedExecution,
                ...this._runningExecutions.slice(executionIndex + 1),
              ];
            }
          }
        }
      }
    );

    // Track connection state
    unifiedWebSocketManager.onStateChange((state) => {
      console.log(`Console header WebSocket state: ${state}`);
    });
  }

  private connectToApprovalUpdates() {
    this.unsubscribeApprovals = unifiedWebSocketManager.subscribe(
      'approvals',
      (message) => {
        console.log('Console header received approval update:', message);

        // Handle new approval request
        if (message.type === 'approval_created') {
          const newApproval: ApprovalRequest = {
            id: message.approval_request_id,
            tool_name: message.tool_name,
            tool_args: message.tool_args || {},
            status: 'pending',
            requested_at: message.requested_at || new Date().toISOString(),
            expires_at: message.expires_at,
            execution_id: message.execution_id,
            agent_reasoning: message.agent_reasoning,
          };

          // Add to pending approvals if not already there
          const exists = this._pendingApprovals.some(
            (approval) => approval.id === newApproval.id
          );
          if (!exists) {
            this._pendingApprovals = [newApproval, ...this._pendingApprovals];
            // Show desktop notification for new approval request
            this.showApprovalNotification(newApproval);
          }
        }

        // Handle approval resolution (approved, declined, expired, cancelled)
        if (
          message.type === 'approval_approved' ||
          message.type === 'approval_declined' ||
          message.type === 'approval_expired' ||
          message.type === 'approval_cancelled'
        ) {
          // Show desktop notification for resolution
          this.showApprovalResolvedNotification(
            message.approval_request_id,
            message.tool_name || 'Tool',
            message.type
          );
          // Remove from pending approvals
          this._pendingApprovals = this._pendingApprovals.filter(
            (approval) => approval.id !== message.approval_request_id
          );
        }
      }
    );
  }

  private connectToNotificationUpdates() {
    // TODO: Subscribe to 'notifications' WebSocket channel when backend supports it
    this.unsubscribeNotifications = unifiedWebSocketManager.subscribe(
      'system',
      (message) => {
        console.log('Console header received system message:', message);

        // Handle notification-type messages
        if (
          message.type === 'team_member_added' ||
          message.type === 'policy_assigned' ||
          message.type === 'role_changed'
        ) {
          const notification: UserNotification = {
            id: message.id || crypto.randomUUID(),
            type: this.mapMessageTypeToNotificationType(message.type),
            title: message.title || this.getNotificationTitle(message.type),
            message: message.message || '',
            created_at: message.timestamp || new Date().toISOString(),
            read: false,
            metadata: message.payload,
          };
          this._userNotifications = [notification, ...this._userNotifications];
        }
      }
    );
  }

  private mapMessageTypeToNotificationType(
    messageType: string
  ): UserNotification['type'] {
    const typeMap: Record<string, UserNotification['type']> = {
      team_member_added: 'team_added',
      team_member_removed: 'team_removed',
      policy_assigned: 'policy_added',
      policy_unassigned: 'policy_removed',
      role_changed: 'role_changed',
    };
    return typeMap[messageType] || 'system';
  }

  private getNotificationTitle(messageType: string): string {
    const titleMap: Record<string, string> = {
      team_member_added: 'Added to Team',
      team_member_removed: 'Removed from Team',
      policy_assigned: 'Policy Assigned',
      policy_unassigned: 'Policy Removed',
      role_changed: 'Role Updated',
    };
    return titleMap[messageType] || 'System Notification';
  }

  // ============================================
  // Desktop Notification Methods
  // ============================================

  /**
   * Request notification permission from the browser if not already granted.
   */
  private async requestNotificationPermission(): Promise<void> {
    if (!('Notification' in window)) {
      console.log('Desktop notifications not supported in this browser');
      return;
    }

    if (Notification.permission === 'default') {
      try {
        const permission = await Notification.requestPermission();
        console.log(`Notification permission: ${permission}`);
      } catch (error) {
        console.error('Failed to request notification permission:', error);
      }
    }
  }

  /**
   * Show desktop notification when a flow execution starts.
   */
  private showExecutionNotification(execution: FlowExecution): void {
    if (!('Notification' in window)) {
      console.log('[Notification] Browser does not support Notification API');
      return;
    }

    if (Notification.permission !== 'granted') {
      console.log(
        `[Notification] Permission not granted (current: ${Notification.permission}), requesting...`
      );
      // Proactively request if still default
      if (Notification.permission === 'default') {
        Notification.requestPermission();
      }
      return;
    }

    // Prevent duplicate notifications for the same execution
    if (this.shownExecutionNotifications.has(execution.id)) {
      console.log(`[Notification] Already shown for execution ${execution.id}`);
      return;
    }
    this.shownExecutionNotifications.add(execution.id);
    console.log(
      `[Notification] Showing start notification for ${execution.flow_name || 'Flow'} (${execution.id})`
    );

    try {
      const notification = new Notification('Flow Execution Started', {
        body: `${execution.flow_name || 'Flow'} is now running`,
        icon: '/images/logos/preloop_logo_dark.svg',
        tag: `execution-${execution.id}`,
      });

      notification.onclick = () => {
        window.focus();
        Router.go(`/console/flows/executions/${execution.id}`);
        notification.close();
      };

      // Auto-close after 10 seconds
      setTimeout(() => notification.close(), 10000);
    } catch (error) {
      console.error('Failed to show execution notification:', error);
    }
  }

  /**
   * Show desktop notification when a flow execution finishes.
   */
  private showExecutionFinishedNotification(
    execution: FlowExecution,
    status: string
  ): void {
    if (!('Notification' in window) || Notification.permission !== 'granted') {
      console.log(
        `[Notification] Cannot show finished notification (permission: ${'Notification' in window ? Notification.permission : 'unsupported'})`
      );
      return;
    }

    console.log(
      `[Notification] Showing finished notification for ${execution.flow_name || 'Flow'} (${execution.id}) — status: ${status}`
    );

    // Build notification based on final status
    const succeeded = status === 'SUCCEEDED';
    const title = succeeded
      ? 'Flow Execution Succeeded'
      : 'Flow Execution Failed';
    const body = `${execution.flow_name || 'Flow'} ${succeeded ? 'completed successfully' : `finished with status: ${status}`}`;

    try {
      const notification = new Notification(title, {
        body,
        icon: '/images/logos/preloop_logo_dark.svg',
        tag: `execution-done-${execution.id}`,
      });

      notification.onclick = () => {
        window.focus();
        Router.go(`/console/flows/executions/${execution.id}`);
        notification.close();
      };

      // Auto-close after 10 seconds
      setTimeout(() => notification.close(), 10000);
    } catch (error) {
      console.error('Failed to show execution finished notification:', error);
    }
  }

  /**
   * Show desktop notification when an approval is requested.
   */
  private showApprovalNotification(approval: ApprovalRequest): void {
    if (!('Notification' in window) || Notification.permission !== 'granted') {
      return;
    }

    // Prevent duplicate notifications for the same approval
    if (this.shownApprovalNotifications.has(approval.id)) {
      return;
    }
    this.shownApprovalNotifications.add(approval.id);

    try {
      const body = approval.agent_reasoning
        ? `${approval.tool_name}: ${approval.agent_reasoning.substring(0, 100)}${approval.agent_reasoning.length > 100 ? '...' : ''}`
        : `${approval.tool_name} requires your approval`;

      const notification = new Notification('Approval Required', {
        body,
        icon: '/images/logos/preloop_logo_dark.svg',
        tag: `approval-${approval.id}`,
        requireInteraction: true, // Stay until dismissed
      });

      notification.onclick = () => {
        window.focus();
        Router.go(`/console/approval/${approval.id}`);
        notification.close();
      };
    } catch (error) {
      console.error('Failed to show approval notification:', error);
    }
  }

  /**
   * Show desktop notification when an approval is resolved.
   */
  private showApprovalResolvedNotification(
    approvalId: string,
    toolName: string,
    eventType: string
  ): void {
    if (!('Notification' in window) || Notification.permission !== 'granted') {
      return;
    }

    const statusMap: Record<string, { title: string; emoji: string }> = {
      approval_approved: { title: 'Approved', emoji: '✅' },
      approval_declined: { title: 'Declined', emoji: '❌' },
      approval_expired: { title: 'Expired', emoji: '⏰' },
      approval_cancelled: { title: 'Cancelled', emoji: '🚫' },
    };

    const status = statusMap[eventType] || { title: 'Resolved', emoji: '📋' };

    try {
      const notification = new Notification(
        `${status.emoji} Approval ${status.title}`,
        {
          body: `${toolName} was ${status.title.toLowerCase()}`,
          icon: '/images/logos/preloop_logo_dark.svg',
          tag: `approval-resolved-${approvalId}`,
        }
      );

      notification.onclick = () => {
        window.focus();
        notification.close();
      };

      // Auto-close after 8 seconds
      setTimeout(() => notification.close(), 8000);
    } catch (error) {
      console.error('Failed to show approval resolved notification:', error);
    }
  }

  async fetchUserDetails() {
    try {
      this._user = await api.getUserProfile();
    } catch (error) {
      console.error('Failed to fetch user details', error);
    }
  }

  async signOut() {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    window.dispatchEvent(
      new CustomEvent('auth-change', { bubbles: true, composed: true })
    );
    window.location.href = '/';
    fetch('/logout', { method: 'GET' }).catch((error) => {
      console.error('Logout request to server failed:', error);
    });
  }

  private formatRelativeTime(dateString: string): string {
    return formatRelativeTime(dateString);
  }

  private navigateToExecution(executionId: string) {
    Router.go(`/console/flows/executions/${executionId}`);
  }

  private renderExecutionsSection() {
    if (this._runningExecutions.length === 0) return '';

    return html`
      <div class="notification-section">
        <div class="section-header">
          <div class="section-title">
            <sl-icon name="activity"></sl-icon>
            Active Executions
            <span class="section-count"
              >(${this._runningExecutions.length})</span
            >
          </div>
          <a
            class="section-link"
            @click=${() => Router.go('/console/flow-executions')}
            >View all</a
          >
        </div>
        <div class="execution-list">
          ${this._runningExecutions.slice(0, 5).map(
            (exec) => html`
              <div
                class="execution-item"
                @click=${() => this.navigateToExecution(exec.id)}
              >
                <div class="execution-name">
                  ${exec.flow_name || 'Flow Execution'}
                </div>
                <div class="execution-time">
                  <sl-badge variant="warning">${exec.status}</sl-badge>
                  • ${this.formatRelativeTime(exec.start_time)}
                </div>
              </div>
            `
          )}
        </div>
      </div>
    `;
  }

  private renderApprovalsSection() {
    if (this._pendingApprovals.length === 0) return '';

    return html`
      <div class="notification-section">
        <div class="section-header">
          <div class="section-title">
            <sl-icon name="shield-check"></sl-icon>
            Pending Approvals
            <span class="section-count"
              >(${this._pendingApprovals.length})</span
            >
          </div>
          <a
            class="section-link"
            @click=${() => Router.go('/console/approvals')}
            >View all</a
          >
        </div>
        <div class="approval-list">
          ${this._pendingApprovals.slice(0, 5).map(
            (approval) => html`
              <div
                class="approval-item"
                @click=${() => Router.go(`/console/approval/${approval.id}`)}
              >
                <div class="approval-name">${approval.tool_name}</div>
                <div class="approval-time">
                  ${this.formatRelativeTime(approval.requested_at)}
                  ${approval.expires_at
                    ? html` •
                      ${approvalDeadline(approval.expires_at, 'pending')}`
                    : ''}
                </div>
                <div class="approval-actions">
                  <sl-button
                    size="small"
                    variant="success"
                    ?loading=${this._processingApproval === approval.id}
                    ?disabled=${this._processingApproval !== null}
                    @click=${(e: Event) => this.handleApprove(approval.id, e)}
                  >
                    <sl-icon slot="prefix" name="check-lg"></sl-icon>
                    Approve
                  </sl-button>
                  <sl-button
                    size="small"
                    variant="danger"
                    ?loading=${this._processingApproval === approval.id}
                    ?disabled=${this._processingApproval !== null}
                    @click=${(e: Event) => this.handleDecline(approval.id, e)}
                  >
                    <sl-icon slot="prefix" name="x-lg"></sl-icon>
                    Decline
                  </sl-button>
                </div>
              </div>
            `
          )}
        </div>
      </div>
    `;
  }

  private renderNotificationsSection() {
    const unreadNotifications = this._userNotifications.filter((n) => !n.read);
    if (this._userNotifications.length === 0) return '';

    return html`
      <div class="notification-section">
        <div class="section-header">
          <div class="section-title">
            <sl-icon name="bell"></sl-icon>
            Notifications
            ${unreadNotifications.length > 0
              ? html`<span class="section-count"
                  >(${unreadNotifications.length} unread)</span
                >`
              : ''}
          </div>
        </div>
        <div class="notification-list">
          ${this._userNotifications.slice(0, 5).map(
            (notification) => html`
              <div
                class="notification-item ${notification.read ? '' : 'unread'}"
                @click=${() => this.markNotificationAsRead(notification.id)}
              >
                <div class="notification-title">
                  <sl-icon
                    name=${this.getNotificationIcon(notification.type)}
                  ></sl-icon>
                  ${notification.title}
                </div>
                <div class="notification-time">
                  ${notification.message} ${notification.message ? ' • ' : ''}
                  ${this.formatRelativeTime(notification.created_at)}
                </div>
              </div>
            `
          )}
        </div>
      </div>
    `;
  }

  private getNotificationIcon(type: UserNotification['type']): string {
    const iconMap: Record<UserNotification['type'], string> = {
      team_added: 'people',
      team_removed: 'people',
      policy_added: 'file-earmark-text',
      policy_removed: 'file-earmark-text',
      role_changed: 'person-badge',
      system: 'info-circle',
    };
    return iconMap[type] || 'bell';
  }

  private renderEmptyState() {
    return html`
      <div class="empty-state">
        <sl-icon name="bell-slash"></sl-icon>
        <div>No notifications</div>
      </div>
    `;
  }

  render() {
    const hasContent =
      this._runningExecutions.length > 0 ||
      this._pendingApprovals.length > 0 ||
      this._userNotifications.length > 0;

    return html`
      ${this._renderNudge()}
      <div class="header-container">
        <div class="nav-toggle">
          <slot name="nav-toggle"></slot>
        </div>
        <div class="user-menu">
          <!-- Notification Center -->
          <sl-dropdown distance="8" placement="bottom-end">
            <div
              slot="trigger"
              class="notification-button"
              @click=${() => this.requestNotificationPermission()}
            >
              <sl-icon-button
                .src=${NOTIFICATION_ICON}
                label="Notifications"
              ></sl-icon-button>
              ${this.totalNotificationCount > 0
                ? html`<span class="notification-badge"
                    >${this.totalNotificationCount > 99
                      ? '99+'
                      : this.totalNotificationCount}</span
                  >`
                : ''}
            </div>
            <div class="notification-dropdown">
              ${hasContent
                ? html`
                    ${this.renderExecutionsSection()}
                    ${this.renderApprovalsSection()}
                    ${this.renderNotificationsSection()}
                  `
                : this.renderEmptyState()}
            </div>
          </sl-dropdown>

          <!-- User Menu -->
          <sl-dropdown distance="8">
            <sl-icon-button
              .src=${PROFILE_ICON}
              slot="trigger"
              label="User Menu"
            ></sl-icon-button>
            <sl-menu>
              <div class="theme-switcher-container">
                <theme-switcher></theme-switcher>
              </div>
              <sl-divider></sl-divider>

              <div class="user-info">
                <div class="user-name">
                  ${this._user?.full_name || this._user?.username}
                </div>
                <div class="user-email">${this._user?.email}</div>
              </div>
              <sl-divider></sl-divider>
              <sl-menu-item
                @click=${() => Router.go('/console/settings/profile')}
              >
                <sl-icon .src=${PROFILE_ICON} slot="prefix"></sl-icon>
                Profile
              </sl-menu-item>
              <sl-menu-item
                @click=${() => Router.go('/console/settings/security')}
              >
                <sl-icon name="lock" slot="prefix"></sl-icon>
                Security
              </sl-menu-item>
              <sl-menu-item
                @click=${() =>
                  Router.go('/console/settings/notification-preferences')}
              >
                <sl-icon name="bell" slot="prefix"></sl-icon>
                Notification Preferences
              </sl-menu-item>
              <sl-divider></sl-divider>
              <sl-menu-item @click=${this.signOut}>
                <sl-icon name="box-arrow-right" slot="prefix"></sl-icon>
                Sign Out
              </sl-menu-item>
            </sl-menu>
          </sl-dropdown>
        </div>
      </div>
    `;
  }
}
