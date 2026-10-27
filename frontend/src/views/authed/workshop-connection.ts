export interface WorkshopFixture {
  email: string;
  status: 'standard' | 'vip';
}

export interface WorkshopOperation {
  email: string;
  expectedStatus: WorkshopFixture['status'];
  targetStatus: WorkshopFixture['status'];
}

interface WorkshopCustomerRow {
  email: string;
  status: string;
}

export class WorkshopPreflightError extends Error {
  code: 'unexpected_status';
  email: string;
  currentStatus: string;

  constructor(email: string, currentStatus: string, expectedStatus: string) {
    super(
      `Workshop customer ${email} is ${currentStatus}, not ${expectedStatus}; no write was submitted.`
    );
    this.name = 'WorkshopPreflightError';
    this.code = 'unexpected_status';
    this.email = email;
    this.currentStatus = currentStatus;
  }
}

/** Only an authenticated v2 setup response can identify the current exercise. */
export function assignedWorkshopFixture(setup: any): WorkshopFixture | null {
  if (
    setup?.state !== 'ready' ||
    setup?.contract_version !== 'yubination-v2' ||
    setup?.tools?.read !== 'get_customer_status' ||
    setup?.tools?.write !== 'set_customer_status' ||
    typeof setup?.fixture?.email !== 'string' ||
    !setup.fixture.email.trim() ||
    !['standard', 'vip'].includes(setup.fixture.status)
  )
    return null;
  return { email: setup.fixture.email, status: setup.fixture.status };
}

export function workshopTargetStatus(status: WorkshopFixture['status']) {
  return status === 'standard' ? 'vip' : 'standard';
}

export function workshopOperation(fixture: WorkshopFixture): WorkshopOperation {
  return {
    email: fixture.email,
    expectedStatus: fixture.status,
    targetStatus: workshopTargetStatus(fixture.status),
  };
}

export function workshopChangeArguments(
  email: string,
  expectedStatus: WorkshopFixture['status'] = 'standard'
) {
  const status = workshopTargetStatus(expectedStatus);
  const action = status === 'vip' ? 'Upgrade' : 'Reset';
  const support = status === 'vip' ? 'VIP' : 'standard';
  return {
    email,
    expected_status: expectedStatus,
    status,
    justification: `${action} workshop customer ${email} to ${support} support.`,
  };
}

/** Reject zero rows, tool errors, and unrelated records. */
function workshopRows(result: any): WorkshopCustomerRow[] {
  if (result?.isError || result?.is_error)
    throw new Error('Workshop tool reported a failure.');
  const unpack = (value: any, depth = 0): any[] => {
    if (depth > 12) throw new Error('Workshop result nesting exceeded.');
    if (typeof value === 'string') return unpack(JSON.parse(value), depth + 1);
    if (Array.isArray(value))
      return value.flatMap((item) => unpack(item, depth + 1));
    if (!value || typeof value !== 'object' || value.isError || value.is_error)
      throw new Error('Workshop result invalid.');
    if (Object.keys(value).sort().join(',') === 'email,status') return [value];
    if (value.type === 'text' && typeof value.text === 'string')
      return unpack(value.text, depth + 1);
    throw new Error('Workshop result invalid.');
  };
  return unpack(result?.content);
}

export function workshopRow(
  result: any,
  status: string,
  email: string
): WorkshopCustomerRow {
  const rows = workshopRows(result);
  if (rows.length !== 1 || rows[0].email !== email || rows[0].status !== status)
    throw new Error(
      `Workshop customer must be exactly ${email} with status ${status}. Ask the facilitator to review the fixture; do not retry a write.`
    );
  return rows[0];
}

function workshopPreflightRow(
  result: any,
  email: string,
  expectedStatus: WorkshopFixture['status']
): WorkshopCustomerRow {
  const rows = workshopRows(result);
  if (
    rows.length !== 1 ||
    rows[0].email !== email ||
    rows[0].status !== expectedStatus
  ) {
    if (rows.length === 1 && rows[0].email === email)
      throw new WorkshopPreflightError(email, rows[0].status, expectedStatus);
    throw new Error(
      `Workshop customer must be exactly ${email} with status ${expectedStatus}. Ask the facilitator to review the fixture; do not retry a write.`
    );
  }
  return rows[0];
}

/** Distinguish the hosted access gate from application credentials; never echo bodies. */
async function checkAuthentication(response: Response): Promise<void> {
  if (response.status !== 401 && response.status !== 403) return;
  const body = await response.text();
  if (
    /^Invalid IAP credentials:/i.test(body.trim()) ||
    response.headers.has('x-goog-iap-generated-response')
  )
    throw new Error(
      'Hosted access was rejected by Google IAP. Reload this page and sign in to the hosted workshop, then try again.'
    );
  throw new Error(
    'API key rejected. Check its expiry and permissions, then try again.'
  );
}

interface BrowserAction {
  userId: string;
  operation: WorkshopOperation;
  onSubmitting: () => void;
  onApproval?: (requestId: string) => void;
}

/** One session; no retry, no credential persistence, no alternate execution route. */
async function workshopSession(
  key: string,
  cancellation?: AbortSignal,
  action?: BrowserAction,
  readback?: { userId: string; email: string }
): Promise<any> {
  if (!key.trim()) throw new Error('Enter your workshop API key.');
  const signal = AbortSignal.any([
    AbortSignal.timeout(action ? 900000 : 20000),
    ...(cancellation ? [cancellation] : []),
  ]);
  const headers: Record<string, string> = {
    Authorization: `Bearer ${key.trim()}`,
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
  };
  const send = async (body: unknown) => {
    signal.throwIfAborted();
    const response = await fetch('/mcp', {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
    });
    await checkAuthentication(response);
    if (!response.ok)
      throw new Error(
        'MCP connection failed. Check workshop setup and try again.'
      );
    return response;
  };
  const progressToken = crypto.randomUUID();
  let linkedId: string | undefined;
  const acceptProgress = (message: any) => {
    if (
      message?.method !== 'notifications/progress' ||
      message.params?.progressToken !== progressToken
    )
      return;
    let correlation;
    try {
      correlation = JSON.parse(message.params.message);
    } catch {
      return;
    }
    if (
      correlation?.type !== 'preloop.approval_required' ||
      typeof correlation.request_id !== 'string' ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        correlation.request_id
      )
    )
      return;
    if (linkedId && linkedId !== correlation.request_id)
      throw new Error(
        'Approval correlation is ambiguous. Do not retry the action.'
      );
    if (!linkedId) {
      linkedId = correlation.request_id;
      action?.onApproval?.(linkedId);
    }
  };
  const result = async (response: Response, id: number) => {
    if (
      id === 101 &&
      response.headers.get('Content-Type')?.includes('text/event-stream') &&
      response.body
    ) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const matches: any[] = [];
      const event = (text: string) => {
        const data = text
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n');
        if (!data) return;
        const message = JSON.parse(data);
        acceptProgress(message);
        if (message?.id === id) matches.push(message);
      };
      try {
        while (true) {
          const { done, value } = await reader.read();
          buffer += decoder.decode(value, { stream: !done });
          // Normalize CRLF only once both bytes have arrived.
          buffer = buffer.replace(/\r\n/g, '\n');
          let end;
          while ((end = buffer.indexOf('\n\n')) >= 0) {
            event(buffer.slice(0, end));
            buffer = buffer.slice(end + 2);
          }
          if (done) {
            if (buffer.trim()) event(buffer);
            break;
          }
        }
      } finally {
        reader.releaseLock();
      }
      if (matches.length !== 1 || matches[0].error || !matches[0].result)
        throw new Error(
          'MCP returned no unambiguous action result. Do not retry the action.'
        );
      return matches[0].result;
    }
    const text = await response.text();
    let messages;
    try {
      messages = [JSON.parse(text)];
    } catch {
      messages = text
        .replace(/\r\n/g, '\n')
        .split('\n\n')
        .map((event) =>
          event
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n')
        )
        .filter(Boolean)
        .map((data) => JSON.parse(data));
    }
    const matches = messages.filter((message) => message?.id === id);
    if (matches.length !== 1 || matches[0].error || !matches[0].result)
      throw new Error('MCP returned an invalid discovery response.');
    return matches[0].result;
  };
  try {
    const accountRead = async (path: string) => {
      signal.throwIfAborted();
      const response = await fetch(path, {
        headers: { Authorization: headers.Authorization },
        signal,
        credentials: 'same-origin',
        redirect: 'error',
        cache: 'no-store',
      });
      await checkAuthentication(response);
      if (!response.ok)
        throw new Error(
          'Workshop account preflight failed. Check workshop setup.'
        );
      return response.json();
    };
    if (action || readback) {
      const identity = await accountRead('/api/v1/auth/users/me');
      if (
        !(action?.userId || readback?.userId) ||
        identity.id !== (action?.userId || readback?.userId)
      )
        throw new Error(
          'Workshop API key must belong to the signed-in participant.'
        );
    }
    const setup = await accountRead('/api/v1/workshop/status');
    const fixture = assignedWorkshopFixture(setup);
    if (!fixture) {
      if (setup?.state === 'review')
        throw new Error(
          'Workshop setup needs updating. Ask the facilitator to migrate this account before testing the connection.'
        );
      const detail =
        typeof setup?.message === 'string'
          ? setup.message
          : 'Ask the facilitator to review the account fixture.';
      throw new Error(`Workshop setup is not ready. ${detail}`);
    }
    if (
      action &&
      (fixture.email !== action.operation.email ||
        fixture.status !== action.operation.expectedStatus ||
        workshopTargetStatus(fixture.status) !== action.operation.targetStatus)
    )
      throw new WorkshopPreflightError(
        action.operation.email,
        fixture.status,
        action.operation.expectedStatus
      );
    if (readback && fixture.email !== readback.email)
      throw new Error(
        'Workshop read must use the signed-in participant’s assigned customer.'
      );
    const initialized = await send({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2025-03-26',
        capabilities: {},
        clientInfo: { name: 'workshop-connection-check', version: '1.0' },
      },
    });
    const initialization = await result(initialized, 1);
    if (
      !['2024-11-05', '2025-03-26', '2025-06-18'].includes(
        initialization.protocolVersion
      )
    )
      throw new Error('MCP returned an unsupported protocol version.');
    headers['MCP-Protocol-Version'] = initialization.protocolVersion;
    const session = initialized.headers.get('Mcp-Session-Id');
    if (session) headers['Mcp-Session-Id'] = session;
    await send({ jsonrpc: '2.0', method: 'notifications/initialized' });
    const tools = new Map<string, any>();
    let cursor: string | undefined;
    for (let page = 0; page < 10; page++) {
      const id = page + 2;
      const listing = await result(
        await send({
          jsonrpc: '2.0',
          id,
          method: 'tools/list',
          params: cursor ? { cursor } : {},
        }),
        id
      );
      if (!Array.isArray(listing.tools))
        throw new Error('MCP returned an invalid tool list.');
      for (const tool of listing.tools) tools.set(tool.name, tool);
      cursor = listing.nextCursor;
      if (!cursor) break;
    }
    if (cursor)
      throw new Error(
        'Tool discovery is incomplete. Try again or ask the facilitator.'
      );
    for (const [name, fields] of [
      ['get_customer_status', ['email']],
      [
        'set_customer_status',
        ['email', 'expected_status', 'status', 'justification'],
      ],
    ] as const) {
      if (readback && name !== 'get_customer_status') continue;
      const schema = tools.get(name)?.inputSchema;
      if (
        fields.some((field) => schema?.properties?.[field]?.type !== 'string')
      )
        throw new Error(
          `Workshop tool unavailable or incompatible: ${name}. Check Tools and workshop setup.`
        );
    }
    if (readback) {
      const toolResult = await result(
        await send({
          jsonrpc: '2.0',
          id: 100,
          method: 'tools/call',
          params: {
            name: 'get_customer_status',
            arguments: { email: readback.email },
          },
        }),
        100
      );
      const rows = workshopRows(toolResult);
      if (
        rows.length !== 1 ||
        rows[0].email !== readback.email ||
        !['standard', 'vip'].includes(rows[0].status)
      )
        throw new Error(
          'Workshop read returned an unexpected customer or status.'
        );
      return { row: rows[0], toolResult };
    }
    if (!action) return ['get_customer_status', 'set_customer_status'];
    const operation = action.operation;
    const read = await result(
      await send({
        jsonrpc: '2.0',
        id: 100,
        method: 'tools/call',
        params: {
          name: 'get_customer_status',
          arguments: { email: operation.email },
        },
      }),
      100
    );
    workshopPreflightRow(read, operation.email, operation.expectedStatus);
    const pending = await accountRead(
      '/api/v1/approval-requests?status=pending&limit=100'
    );
    if (!Array.isArray(pending) || pending.length)
      throw new Error(
        'Workshop approval already pending or unavailable. Resolve it before another request.'
      );
    signal.throwIfAborted();
    action.onSubmitting();
    const write = await result(
      await send({
        jsonrpc: '2.0',
        id: 101,
        method: 'tools/call',
        params: {
          name: 'set_customer_status',
          arguments: workshopChangeArguments(
            operation.email,
            operation.expectedStatus
          ),
          _meta: { progressToken },
        },
      }),
      101
    );
    try {
      const row = workshopRow(write, operation.targetStatus, operation.email);
      const verifiedRead = await result(
        await send({
          jsonrpc: '2.0',
          id: 102,
          method: 'tools/call',
          params: {
            name: 'get_customer_status',
            arguments: { email: operation.email },
          },
        }),
        102
      );
      workshopRow(verifiedRead, operation.targetStatus, operation.email);
      return {
        row,
        toolResult: write,
        verified: true,
      };
    } catch {
      return { toolResult: write, verified: false };
    }
  } finally {
    delete headers.Authorization;
  }
}

export async function checkWorkshopConnection(
  key: string,
  cancellation?: AbortSignal
): Promise<string[]> {
  return workshopSession(key, cancellation);
}

export async function requestWorkshopChange(
  key: string,
  userId: string,
  operation: WorkshopOperation,
  onSubmitting: () => void,
  cancellation?: AbortSignal,
  onApproval?: (requestId: string) => void
): Promise<{
  row?: { email: string; status: string };
  toolResult: unknown;
  verified: boolean;
}> {
  return workshopSession(key, cancellation, {
    userId,
    operation,
    onSubmitting,
    onApproval,
  });
}

export async function readWorkshopCustomer(
  key: string,
  userId: string,
  email: string,
  cancellation?: AbortSignal
): Promise<{ row: WorkshopCustomerRow; toolResult: unknown }> {
  return workshopSession(key, cancellation, undefined, { userId, email });
}
