import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import {
  BudgetPolicy,
  BudgetPolicyCreate,
  getBudgetPolicies,
  createBudgetPolicy,
  deleteBudgetPolicy,
  getAIModels,
  getAccountAgents,
  AIModel,
  ManagedAgentSummary,
  fetchWithAuth,
} from '../api.js';
import type { User, UserListResponse } from '../types.js';
import '@shoelace-style/shoelace/dist/components/badge/badge.js';

import '@shoelace-style/shoelace/dist/components/button/button.js';
import '@shoelace-style/shoelace/dist/components/select/select.js';
import '@shoelace-style/shoelace/dist/components/option/option.js';
import '@shoelace-style/shoelace/dist/components/input/input.js';
import '@shoelace-style/shoelace/dist/components/checkbox/checkbox.js';
import '@shoelace-style/shoelace/dist/components/icon-button/icon-button.js';
import '@shoelace-style/shoelace/dist/components/alert/alert.js';

@customElement('budget-policy-editor')
export class BudgetPolicyEditor extends LitElement {
  @property({ type: String }) subjectType?: string;
  @property({ type: String }) subjectId?: string;

  @state() private policies: BudgetPolicy[] = [];
  @state() private showAddForm = false;
  @state() private error = '';

  @state() private models: AIModel[] = [];
  @state() private agents: ManagedAgentSummary[] = [];
  @state() private loadingSubjects = false;
  @state() private features: Record<string, boolean> = {};
  @state() private availableUsers: User[] = [];

  // New Policy Form State
  @state() private newSubjectType = 'global';
  @state() private newSubjectId = 'global';
  @state() private newPeriod = 'monthly';
  @state() private newHardLimit = '';
  @state() private newSoftLimit = '';
  @state() private newNotifySoft = false;
  @state() private newNotifyHard = false;
  @state() private newEmails = '';

  static styles = css`
    :host {
      display: block;
      font-family: var(--sl-font-sans);
    }
    .policy-list {
      margin-top: var(--sl-spacing-medium);
      display: flex;
      flex-direction: column;
      gap: var(--sl-spacing-small);
    }
    .policy-item {
      padding: var(--sl-spacing-small) var(--sl-spacing-medium);
      border: 1px solid var(--sl-color-neutral-200);
      border-radius: var(--sl-border-radius-medium);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--sl-panel-background-color);
      color: var(--sl-color-neutral-900);
    }
    .form-container {
      margin-top: var(--sl-spacing-medium);
      padding: var(--sl-spacing-medium);
      border: 1px solid var(--sl-color-neutral-200);
      border-radius: var(--sl-border-radius-medium);
      background: var(--sl-panel-background-color);
      display: flex;
      flex-direction: column;
      gap: var(--sl-spacing-medium);
    }
    .form-row {
      display: flex;
      gap: var(--sl-spacing-medium);
    }
    .form-row > * {
      flex: 1;
    }
    .form-actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--sl-spacing-small);
      margin-top: var(--sl-spacing-small);
    }
    .checkbox-group {
      display: flex;
      gap: var(--sl-spacing-medium);
      align-items: center;
    }
    .meta-text {
      font-size: var(--sl-font-size-small);
      color: var(--sl-color-neutral-500);
      margin-top: var(--sl-spacing-3x-small);
    }
  `;

  async connectedCallback() {
    super.connectedCallback();
    const featuresRes = await fetchWithAuth('/api/v1/features')
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
    this.features = featuresRes?.features || {};
    if (this.features.billing !== true) {
      return;
    }
    await this.loadPolicies();
    this.loadSubjects();
  }

  private getSubjectName(type: string, id: string): string {
    if (type === 'ai_model') {
      const model = this.models.find((m) => m.id === id);
      return model ? model.alias || model.id : id;
    }
    if (type === 'managed_agent') {
      const agent = this.agents.find((a) => a.id === id);
      return agent ? agent.display_name || agent.id : id;
    }
    return id;
  }

  async loadSubjects() {
    this.loadingSubjects = true;
    this.error = '';
    try {
      const [models, agentsResponse, userProfile, featuresRes, usersRes] =
        await Promise.all([
          getAIModels(),
          getAccountAgents({ status: 'all', limit: 100 }),
          fetchWithAuth('/api/v1/auth/users/me').then((r) =>
            r.ok ? r.json() : null
          ),
          fetchWithAuth('/api/v1/features').then((r) =>
            r.ok ? r.json() : null
          ),
          fetchWithAuth('/api/v1/users?limit=100').then((r) =>
            r.ok
              ? r.json()
              : ({
                  users: [],
                  total: 0,
                  skip: 0,
                  limit: 100,
                } satisfies UserListResponse)
          ),
        ]);
      this.models = models;
      this.agents = agentsResponse.items || [];
      this.features = featuresRes?.features || {};
      this.availableUsers = (usersRes as UserListResponse).users || [];
      if (userProfile && !this.newEmails) {
        this.newEmails = userProfile.email;
      }
    } catch (e) {
      console.error('Failed to load subjects', e);
      this.error =
        'Failed to load budget policy subjects. Some selectors may be empty.';
      this.models = [];
      this.agents = [];
      this.availableUsers = [];
    } finally {
      this.loadingSubjects = false;
    }
  }

  async loadPolicies() {
    try {
      const result = await getBudgetPolicies(this.subjectType, this.subjectId);
      if (Array.isArray(result)) {
        this.policies = result;
      } else {
        this.error =
          'Failed to load budget policies. Server returned an error.';
        this.policies = [];
        console.error('Non-array response:', result);
      }
    } catch (e: any) {
      this.error = 'Failed to load budget policies.';
      this.policies = [];
      console.error(e);
    }
  }

  private async handleDelete(id: string) {
    try {
      await deleteBudgetPolicy(id);
      await this.loadPolicies();
    } catch (e: any) {
      this.error = 'Failed to delete policy.';
    }
  }

  private async handleCreate() {
    this.error = '';

    // Parse emails from comma separated
    let emails: string[] = [];
    if (this.newEmails.trim()) {
      emails = this.newEmails
        .split(',')
        .map((e) => e.trim())
        .filter((e) => e);
    }

    const payload: BudgetPolicyCreate = {
      subject_type: this.subjectType || this.newSubjectType,
      subject_id: this.subjectType
        ? this.subjectId || 'global'
        : this.newSubjectId,
      model_alias: null, // applies to all models
      period: this.newPeriod,
      hard_limit_usd: this.newHardLimit ? parseFloat(this.newHardLimit) : null,
      soft_limit_usd: this.newSoftLimit ? parseFloat(this.newSoftLimit) : null,
      notify_on_soft: this.newNotifySoft,
      notify_on_hard: this.newNotifyHard,
      notification_emails: emails.length > 0 ? emails : null,
    };

    try {
      await createBudgetPolicy(payload);
      this.showAddForm = false;
      this.resetForm();
      await this.loadPolicies();
    } catch (err: any) {
      this.error = 'Failed to create policy. ' + (err.message || '');
    }
  }

  private resetForm() {
    this.newSubjectType = 'global';
    this.newSubjectId = 'global';
    this.newPeriod = 'monthly';
    this.newHardLimit = '';
    this.newSoftLimit = '';
    this.newNotifySoft = false;
    this.newNotifyHard = false;
    this.newEmails = '';
  }

  private addEmail(email: string) {
    if (!email) return;
    const current = this.newEmails
      .split(',')
      .map((e) => e.trim())
      .filter((e) => e);
    if (!current.includes(email)) {
      current.push(email);
      this.newEmails = current.join(', ');
    }
  }

  render() {
    if (this.features.billing !== true) {
      return nothing;
    }

    return html`
      <div role="region" aria-labelledby="budget-policy-editor-title">
        <div
          style="display: flex; justify-content: space-between; align-items: center;"
        >
          <h4
            id="budget-policy-editor-title"
            style="margin: 0; font-size: var(--sl-font-size-large); font-weight: var(--sl-font-weight-semibold); color: var(--sl-color-neutral-900);"
          >
            Budget Policies
          </h4>
          ${!this.showAddForm
            ? html`
                <sl-button
                  size="small"
                  variant="primary"
                  @click=${() => (this.showAddForm = true)}
                >
                  <sl-icon slot="prefix" name="plus"></sl-icon>
                  Add Policy
                </sl-button>
              `
            : ''}
        </div>

        ${this.error
          ? html`
              <sl-alert
                variant="danger"
                open
                role="alert"
                aria-live="assertive"
                style="margin-top: var(--sl-spacing-medium);"
              >
                <sl-icon slot="icon" name="exclamation-octagon"></sl-icon>
                ${this.error}
              </sl-alert>
            `
          : ''}

        <div class="policy-list">
          ${this.policies.length === 0 && !this.showAddForm
            ? html`<div
                style="color: var(--sl-color-neutral-500); font-size: var(--sl-font-size-small);"
              >
                No budget policies configured.
              </div>`
            : this.policies.map(
                (p) => html`
                  <div class="policy-item">
                    <div>
                      <strong style="color: var(--sl-color-neutral-900);"
                        >${p.period.charAt(0).toUpperCase() +
                        p.period.slice(1)}</strong
                      >
                      ${!this.subjectType
                        ? html`
                            <sl-badge
                              variant="neutral"
                              style="margin-left: 8px;"
                            >
                              ${p.subject_type === 'global'
                                ? 'Global'
                                : p.subject_type === 'ai_model'
                                  ? 'Model'
                                  : p.subject_type === 'managed_agent'
                                    ? 'Agent'
                                    : p.subject_type}
                            </sl-badge>
                            <span
                              style="font-size: var(--sl-font-size-small); color: var(--sl-color-neutral-600); margin-left: 4px;"
                            >
                              ${p.subject_type !== 'global' && p.subject_id
                                ? this.getSubjectName(
                                    p.subject_type,
                                    p.subject_id
                                  )
                                : ''}
                            </span>
                          `
                        : ''}
                      <br />
                      <span
                        style="font-size: var(--sl-font-size-small); color: var(--sl-color-neutral-700);"
                        >Limit:</span
                      >
                      ${p.hard_limit_usd
                        ? html`<span
                            style="font-size: var(--sl-font-size-small);"
                            >Hard: $${p.hard_limit_usd.toFixed(2)}</span
                          >`
                        : html`<span
                            style="font-size: var(--sl-font-size-small);"
                            >No Hard Limit</span
                          >`}
                      ${p.soft_limit_usd
                        ? html`<span
                            style="font-size: var(--sl-font-size-small);"
                            >| Soft: $${p.soft_limit_usd.toFixed(2)}</span
                          >`
                        : ''}
                      ${this.features?.['billing']
                        ? html`
                            <div class="meta-text">
                              Notifications to:
                              ${p.notification_emails?.join(', ') || 'None'}
                            </div>
                          `
                        : ''}
                    </div>
                    <sl-icon-button
                      name="trash"
                      style="color: var(--sl-color-danger-600);"
                      @click=${() => this.handleDelete(p.id)}
                    ></sl-icon-button>
                  </div>
                `
              )}
        </div>

        ${this.showAddForm
          ? html`
              <div class="form-container">
                ${!this.subjectType
                  ? html`
                      <div class="form-row">
                        <sl-select
                          label="Target Scope"
                          value=${this.newSubjectType}
                          @sl-change=${(e: any) => {
                            this.newSubjectType = e.target.value;
                            this.newSubjectId =
                              this.newSubjectType === 'global' ? 'global' : '';
                          }}
                        >
                          <sl-option value="global"
                            >Global (Account-wide)</sl-option
                          >
                          <sl-option value="ai_model">AI Model</sl-option>
                          <sl-option value="managed_agent">Agent</sl-option>
                        </sl-select>

                        ${this.newSubjectType === 'ai_model'
                          ? html`
                              <sl-select
                                label="Select Model"
                                value=${this.newSubjectId}
                                @sl-change=${(e: any) =>
                                  (this.newSubjectId = e.target.value)}
                                ?disabled=${this.loadingSubjects}
                              >
                                ${this.models.map(
                                  (m) =>
                                    html`<sl-option value=${m.id}
                                      >${m.alias || m.id}</sl-option
                                    >`
                                )}
                              </sl-select>
                            `
                          : this.newSubjectType === 'managed_agent'
                            ? html`
                                <sl-select
                                  label="Select Agent"
                                  value=${this.newSubjectId}
                                  @sl-change=${(e: any) =>
                                    (this.newSubjectId = e.target.value)}
                                  ?disabled=${this.loadingSubjects}
                                >
                                  ${this.agents.map(
                                    (a) =>
                                      html`<sl-option value=${a.id}
                                        >${a.display_name || a.id}</sl-option
                                      >`
                                  )}
                                </sl-select>
                              `
                            : html`<div style="flex: 1"></div>`}
                      </div>
                    `
                  : ''}

                <sl-select
                  label="Period"
                  value=${this.newPeriod}
                  @sl-change=${(e: any) => (this.newPeriod = e.target.value)}
                >
                  <sl-option value="hourly">Hourly</sl-option>
                  <sl-option value="daily">Daily</sl-option>
                  <sl-option value="weekly">Weekly</sl-option>
                  <sl-option value="monthly">Monthly</sl-option>
                  <sl-option value="yearly">Yearly</sl-option>
                  <sl-option value="all_time">All Time</sl-option>
                </sl-select>

                <div class="form-row">
                  <sl-input
                    label="Hard Limit (USD)"
                    type="number"
                    step="0.0001"
                    .value=${this.newHardLimit}
                    @sl-input=${(e: any) =>
                      (this.newHardLimit = e.target.value)}
                  ></sl-input>
                  <sl-input
                    label="Soft Limit (USD)"
                    type="number"
                    step="0.0001"
                    .value=${this.newSoftLimit}
                    @sl-input=${(e: any) =>
                      (this.newSoftLimit = e.target.value)}
                  ></sl-input>
                </div>

                ${this.features?.['billing']
                  ? html`
                      <sl-input
                        label="Notification Emails"
                        help-text="Comma separated list of emails"
                        placeholder="admin@example.com"
                        .value=${this.newEmails}
                        @sl-input=${(e: any) =>
                          (this.newEmails = e.target.value)}
                      ></sl-input>

                      ${this.availableUsers.length > 0
                        ? html`
                            <div
                              style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: -8px; margin-bottom: 8px;"
                            >
                              ${this.availableUsers.map(
                                (u) => html`
                                  <sl-badge
                                    variant="neutral"
                                    style="cursor: pointer"
                                    @click=${() => this.addEmail(u.email)}
                                  >
                                    + ${u.email}
                                  </sl-badge>
                                `
                              )}
                            </div>
                          `
                        : ''}

                      <div class="checkbox-group">
                        <sl-checkbox
                          ?checked=${this.newNotifySoft}
                          @sl-change=${(e: any) =>
                            (this.newNotifySoft = e.target.checked)}
                        >
                          Send email on Soft Limit
                        </sl-checkbox>
                        <sl-checkbox
                          ?checked=${this.newNotifyHard}
                          @sl-change=${(e: any) =>
                            (this.newNotifyHard = e.target.checked)}
                        >
                          Send email on Hard Limit
                        </sl-checkbox>
                      </div>
                    `
                  : ''}

                <div class="form-actions">
                  <sl-button @click=${() => (this.showAddForm = false)}
                    >Cancel</sl-button
                  >
                  <sl-button variant="primary" @click=${this.handleCreate}
                    >Save Policy</sl-button
                  >
                </div>
              </div>
            `
          : ''}
      </div>
    `;
  }
}
