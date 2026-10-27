import { LitElement, css, html } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import {
  fetchWithAuth,
  getApprovalRequest,
  listApprovalRequests,
} from '../api';

interface Approval {
  id: string;
  status: string;
  step_up_verified: boolean;
  tool_name: string;
  tool_args?: unknown;
  action_class?: string;
  server_recorded_context?: unknown;
}
type Checks = {
  request_id: string;
  intent_intact: boolean;
  challenge_bound: boolean;
  signature_valid: boolean;
};
// These fields may contain sensitive caller data. Render only on explicit inspection,
// never persist or log. Remove credential-bearing names even inside tool arguments.
function displayEvidence(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(displayEvidence);
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value)
        .filter(
          ([name]) =>
            !/token|secret|password|api.?key|authorization/i.test(name)
        )
        .map(([name, entry]) => [name, displayEvidence(entry)])
    );
  return value;
}

@customElement('workshop-receipt-auditor')
export class WorkshopReceiptAuditor extends LitElement {
  static styles = css`
    :host {
      display: block;
      line-height: 1.6;
      overflow-wrap: anywhere;
    }
    section {
      margin-block: 1.5rem;
    }
    h2 {
      font-size: 1.2rem;
    }
    button,
    select {
      font: inherit;
      min-height: 44px;
      max-width: 100%;
      margin: 0.3rem 0;
    }
    select {
      width: 100%;
    }
    pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    details {
      margin: 1rem 0;
    }
    a {
      color: var(--sl-color-primary-700, #005a9c);
    }
    table {
      border-collapse: collapse;
      width: 100%;
    }
    th,
    td {
      text-align: left;
      padding: 0.4rem;
      border-bottom: 1px solid #ccc;
    }
    :focus-visible {
      outline: 3px solid currentColor;
      outline-offset: 2px;
    }
  `;
  @state() private approvals: Approval[] | null = null;
  @state() private selected = '';
  @state() private busy = false;
  @state() private error = '';
  @state() private checks: Checks | null = null;
  @state() private approval: Pick<
    Approval,
    | 'id'
    | 'tool_name'
    | 'tool_args'
    | 'action_class'
    | 'server_recorded_context'
  > | null = null;
  private generation = 0;
  disconnectedCallback() {
    super.disconnectedCallback();
    this.generation++;
  }
  private async load() {
    const generation = ++this.generation;
    this.busy = true;
    this.error = '';
    this.selected = '';
    this.approval = null;
    this.checks = null;
    try {
      const rows = await listApprovalRequests({
        status: 'approved',
        limit: 50,
      });
      if (generation !== this.generation) return;
      if (!Array.isArray(rows)) throw new Error();
      this.approvals = rows.filter(
        (row) =>
          row &&
          typeof row.id === 'string' &&
          row.status === 'approved' &&
          row.step_up_verified === true
      );
    } catch {
      if (generation === this.generation) {
        this.approvals = null;
        this.error =
          'Could not load your approvals. Try again when the connection is available.';
      }
    } finally {
      if (generation === this.generation) this.busy = false;
    }
  }
  private async verify() {
    const id = this.selected;
    if (!id || this.busy) return;
    const generation = ++this.generation;
    this.busy = true;
    this.error = '';
    this.checks = null;
    this.approval = null;
    try {
      const request: Approval = await getApprovalRequest(
        encodeURIComponent(id)
      );
      if (generation !== this.generation) return;
      if (
        request?.id !== id ||
        request.status !== 'approved' ||
        request.step_up_verified !== true
      )
        throw new Error();
      const response = await fetchWithAuth(
        `/api/v1/audit/decisions/${encodeURIComponent(id)}/verify`
      );
      if (!response.ok) throw new Error();
      const checks = await response.json();
      if (generation !== this.generation) return;
      if (
        checks?.request_id !== id ||
        !['intent_intact', 'challenge_bound', 'signature_valid'].every(
          (key) => typeof checks[key] === 'boolean'
        )
      )
        throw new Error();
      this.approval = {
        id,
        tool_name: request.tool_name,
        tool_args: displayEvidence(request.tool_args),
        action_class: request.action_class,
        server_recorded_context: displayEvidence(
          request.server_recorded_context
        ),
      };
      this.checks = checks;
    } catch {
      if (generation === this.generation)
        this.error =
          'This approval could not be verified. Open its approval page to check for missing evidence or a removed credential, then try again. No action was changed.';
    } finally {
      if (generation === this.generation) this.busy = false;
    }
  }
  render() {
    return html`
      <section>
        <h2>What you will learn</h2>
        <ul>
          <li>Identify the approved action.</li>
          <li>Explain its recorded action class.</li>
          <li>Read the three server checks.</li>
          <li>Find separate evidence of execution.</li>
        </ul>
        <a href="/console/workshop/yubination"
          >Complete the main workshop first if needed</a
        >
      </section>
      <section>
        <h2>1. Verify your own approval</h2>
        <section aria-label="Next action">
          <p>
            Select your own approved request: load your approvals below, then
            verify the stored evidence. This read-only check uses the server
            verifier; it does not request another approval or signature.
          </p>
        </section>
        <section aria-label="Expected result">
          <p>
            Your receipt shows the recorded action and verification checks, or a
            missing-evidence message. A missing or failed check is not a pass.
          </p>
        </section>
        <button ?disabled=${this.busy} @click=${this.load}>
          Load my approvals
        </button>
        ${this.approvals?.length
          ? html`<label for="own-approval"
                >Recent approved requests (up to 50)</label
              ><select
                id="own-approval"
                ?disabled=${this.busy}
                .value=${this.selected}
                @change=${(event: Event) => {
                  this.generation++;
                  this.selected = (event.target as HTMLSelectElement).value;
                  this.checks = null;
                  this.approval = null;
                  this.error = '';
                }}
              >
                <option value="">Select an approval</option>
                ${this.approvals.map(
                  (row) =>
                    html`<option value=${row.id}>
                      ${row.tool_name} — ${row.id}
                    </option>`
                )}</select
              ><button
                ?disabled=${this.busy || !this.selected}
                @click=${this.verify}
              >
                Verify my approval
              </button>`
          : this.approvals
            ? html`<p>
                No approved requests with stored step-up were found among the
                most recent requests.
                <a href="/console/approvals">Find an older approval</a> or
                <a href="/console/workshop/yubination"
                  >complete the main workshop</a
                >.
              </p>`
            : ''}
        ${this.busy ? html`<p role="status">Loading evidence…</p>` : ''}
        ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
        ${this.selected
          ? html`<p>
              <a
                href=${`/console/approval/${encodeURIComponent(this.selected)}`}
                >Open this approval and its receipt</a
              >
            </p>`
          : ''}
        ${this.checks
          ? html`<section aria-label="Selected action" data-selected-action>
                <h2>2. Read your result</h2>
                <p>Request: ${this.approval?.id}</p>
                <p>Tool: <strong>${this.approval?.tool_name}</strong></p>
                <p>Arguments shown below omit credential-bearing fields.</p>
                ${this.approval?.tool_args &&
                typeof this.approval.tool_args === 'object'
                  ? html`<dl>
                      ${Object.entries(this.approval.tool_args).map(
                        ([name, value]) => html`
                          <dt>${name}</dt>
                          <dd>
                            ${typeof value === 'string'
                              ? value
                              : JSON.stringify(value)}
                          </dd>
                        `
                      )}
                    </dl>`
                  : html`<p>
                      ${this.approval?.tool_args === undefined
                        ? 'Arguments unavailable.'
                        : JSON.stringify(this.approval.tool_args)}
                    </p>`}
                <p>
                  Recorded action class:
                  <strong
                    >${this.approval?.action_class || 'Not recorded'}</strong
                  >.
                </p>
                <p>
                  An action class describes an effect: read looks up data; write
                  changes it. This approval path defaults to write; the label is
                  not a separately enforced policy.
                </p>
                <p>
                  Open this approval for its recorded policy context. See
                  <a href="/console/tools">Tools</a> for the tool’s current
                  approval policy.
                </p>
              </section>
              <ul>
                ${(
                  [
                    'intent_intact',
                    'challenge_bound',
                    'signature_valid',
                  ] as const
                ).map(
                  (key) =>
                    html`<li data-check=${key}>
                      ${{
                        intent_intact: 'Requested action matches intent hash',
                        challenge_bound: 'Challenge binds that intent',
                        signature_valid: 'Stored WebAuthn signature validates',
                      }[key]}:
                      <strong>${this.checks![key] ? 'Pass' : 'Fail'}</strong>
                      <p>
                        ${{
                          intent_intact:
                            'Checks whether the stored action still matches its recorded hash. A changed argument breaks this match.',
                          challenge_bound:
                            'Checks whether the stored challenge matches the hash derived from this action and its nonce.',
                          signature_valid:
                            'Checks whether the stored assertion signature matches the credential public key.',
                        }[key]}
                      </p>
                    </li>`
                )}
              </ul>
              <p>
                ${Object.values({
                  a: this.checks.intent_intact,
                  b: this.checks.challenge_bound,
                  c: this.checks.signature_valid,
                }).every((value) => value)
                  ? 'All three server checks passed.'
                  : 'At least one check failed. Do not rely on this evidence until the failure is understood.'}
                This is server re-verification, not independent browser
                verification. These checks cover the stored WebAuthn assertion,
                not PreviewSign’s additional signature or database execution.
              </p>
              <p>
                These results do not establish trusted key ownership, origin/RP
                policy, user-verification (UV) policy, freshness or full
                delegation authority.
              </p>
              <details>
                <summary>See the signed inputs and recorded context</summary>
                <p>
                  A Role Delegation Token (RDT) describes scoped delegation: who
                  may do what, under which constraints. Here, the receipt
                  provides partial intent binding, not a fully signed delegation
                  token.
                </p>
                <p>
                  The intent contains
                  <code
                    >v, account_id, approval_request_id, tool_name, tool_args,
                    requested_at</code
                  >. Version 2 also includes
                  <code>intent_risk_tier, intent_flags</code>.
                </p>
                <pre>
intent_hash = SHA256(JCS(intent_envelope))
challenge = SHA256(intent_hash || nonce)
verify(credential_public_key,
       authenticatorData || SHA256(clientDataJSON), signature)
# clientDataJSON contains the challenge</pre
                >
                <p>
                  The RDT display includes
                  <code
                    >version, action_class, operation, context, reasoning,
                    timestamp, approver_id</code
                  >
                  and available credential/assertion fields. The whole RDT JSON
                  is not signed by this intent binding. Server-recorded identity
                  and policy context and the caller's supplied purpose are
                  separate evidence.
                </p>
                <p>
                  The current approval path records <code>write</code> as its
                  default action class. The schema documents read, write,
                  delete, deploy, spend, admin and privacy; those labels do not
                  prove seven independently enforced policies. The configured
                  tool approval policy determines whether this workshop action
                  needs approval.
                </p>
              </details>
              <details data-comparison>
                <summary>Optional: compare a recorded altered action</summary>

                <p>
                  Worked example: changing the action breaks its binding even
                  when the original signature remains valid.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Check</th>
                      <th>Original</th>
                      <th>Changed argument</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Intent hash matches action</td>
                      <td>Pass</td>
                      <td>Fail</td>
                    </tr>
                    <tr>
                      <td>Stored assertion signature</td>
                      <td>Pass</td>
                      <td>Pass</td>
                    </tr>
                    <tr>
                      <td>All verifier checks</td>
                      <td>Pass</td>
                      <td>Fail</td>
                    </tr>
                  </tbody>
                </table>
                <p>
                  The old signature can remain valid for the old bytes while the
                  changed action no longer matches. Never treat one passing
                  check as approval of a different action.
                </p>
                <details>
                  <summary>
                    Inspect the example action and recorded checks
                  </summary>
                  <p>
                    Recorded verifier comparison: the existing offline verifier
                    checked an ES256 software fixture and a copy with
                    <code>tool_args.item</code> changed from
                    <code>example</code> to <code>changed</code>. These are
                    recorded test results, not independent browser cryptography.
                  </p>
                  <pre>
{"tool_name":"offline_fixture","tool_args":{"item":"example"}}</pre
                  >
                  <p>
                    The example uses a software key and
                    <code>https://fixture.invalid</code>. It establishes neither
                    hardware protection nor participant completion.
                  </p>
                </details>
              </details>
              <details data-evidence>
                <summary>
                  Inspect this action and recorded policy context
                </summary>
                <pre>${JSON.stringify(this.approval, null, 2)}</pre>
              </details>`
          : ''}
        <details>
          <summary>What if verification fails?</summary>
          <p>
            Missing key material, unsupported verification or invalid evidence
            can cause failure. This check does not distinguish those causes.
            Preserve the original receipt and inspect its approval page.
          </p>
        </details>
        <p>
          Keep receipts private. This page does not upload receipts or send them
          to feedback.
        </p>
      </section>
      <section>
        <h2>3. Check execution and explain</h2>
        <p>
          Return to
          <a href="/console/workshop/yubination">main workshop step 5</a>. Run
          <code>get_customer_status</code> through your agent or use the browser
          alternative there. Compare this independent readback with the original
          tool result. Approval evidence alone cannot establish execution.
        </p>
        <ul>
          <li>What changed in the customer, and what action was approved?</li>
          <li>What is signed, and which context is only recorded?</li>
          <li>What evidence shows the action executed?</li>
        </ul>
        <p>
          A green check does not complete this challenge. Explain your own
          result; the recorded example is optional practice.
        </p>
      </section>
    `;
  }
}
