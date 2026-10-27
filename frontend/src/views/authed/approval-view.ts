import {
  approvalTimestamp,
  approvalDeadline,
  approvalWasLate,
} from '../../utils/approval-time';
import { parseUTCDate } from '../../utils/date';
import { describeReceipt } from '../../services/receipt-description';
import { LitElement, html, css } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { AuthedElement, getUserProfile } from '../../api';
import { unifiedWebSocketManager } from '../../services/unified-websocket-manager';
import '@shoelace-style/shoelace/dist/components/card/card.js';
import '@shoelace-style/shoelace/dist/components/button/button.js';
import '@shoelace-style/shoelace/dist/components/spinner/spinner.js';
import '@shoelace-style/shoelace/dist/components/alert/alert.js';
import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';
import '@shoelace-style/shoelace/dist/components/badge/badge.js';
import '@shoelace-style/shoelace/dist/components/icon/icon.js';
import '@shoelace-style/shoelace/dist/components/divider/divider.js';
import '@shoelace-style/shoelace/dist/components/details/details.js';
import '@shoelace-style/shoelace/dist/components/tag/tag.js';

interface ApprovalRequest {
  id: string;
  account_id: string;
  tool_configuration_id: string;
  approval_workflow_id: string;
  execution_id: string | null;
  tool_name: string;
  tool_args: Record<string, any>;
  server_recorded_context?: {
    cryptographically_bound?: false;
    requester?: {
      authenticated_user_id?: string;
      display_name?: string;
      authentication?: { type?: string; credential_id?: string };
      agent?: { id?: string | null; identity_status?: string };
    };
    delegation?: { status?: string };
    purpose?: {
      status?: string;
      text?: string | null;
      source?: string | null;
      verified?: false;
    };
    policy?: {
      evaluation_source?: string;
      evaluation_outcome?: string;
      matched_rule?: {
        id?: string;
        action?: string;
        condition?: string | null;
        condition_type?: string;
        order?: number;
        content_digest?: string;
        digest_format?: string;
      } | null;
      evaluated_rule?: { id?: string } | null;
      evaluated_at?: string;
      approval_workflow_id?: string | null;
      context?: { completeness?: string };
    };
    workflow?: {
      id?: string;
      approval_type?: string | null;
      step_up_protocol?: string | null;
      timeout_seconds?: number | null;
      effective_step_up_required?: boolean;
    };
    advisory_assessment?: { model_used?: string | null; source?: string };
  } | null;
  rdt_envelope?: Record<string, unknown> | null;
  agent_reasoning: string | null;
  status: 'pending' | 'approved' | 'declined' | 'expired' | 'cancelled';
  requested_at: string;
  resolved_at: string | null;
  decided_by_user_id?: string | null;
  decided_at?: string | null;
  expires_at: string | null;
  approver_comment: string | null;
  webhook_posted_at: string | null;
  webhook_error: string | null;
  step_up_required: boolean;
  step_up_verified: boolean;
  approval_token: string | null;
  intent_hash_hex?: string | null;
  action_class?: string | null;
  intent_verified?: boolean;
  intent_risk_tier?: string | null;
  intent_step_up_override?: boolean | null;
  intent_description_match_score?: number | null;
  intent_flags?: string[] | null;
  intent_reasoning?: string | null;
  intent_model?: string | null;
  intent_latency_ms?: number | null;
}

@customElement('approval-view')
export class ApprovalView extends AuthedElement {
  @property({ type: String })
  requestId: string = '';

  @state()
  private approvalRequest: ApprovalRequest | null = null;

  @state()
  private loading = true;

  @state()
  private error: string | null = null;

  @state()
  private comment = '';

  @state()
  private submitting = false;

  @state()
  private actionResult: { type: 'success' | 'error'; message: string } | null =
    null;

  @state()
  private stepUpError: string | null = null;

  @state()
  private stepUpPending = false;

  @state()
  private receipt: Record<string, any> | null = null;

  @state()
  private receiptError: string | null = null;

  @state() private mdsKeyProtection: string | null = null;

  @state()
  private integrityVerification: {
    signature_valid: boolean;
    challenge_bound: boolean;
    intent_intact: boolean;
  } | null = null;

  @state()
  private integrityVerificationError: string | null = null;

  @state()
  private intentHashVerification: {
    envelope_version: number;
    intent_intact: boolean;
    signature_verified: boolean;
    detail: string;
  } | null = null;

  @state()
  private intentHashVerificationError: string | null = null;

  private unsubscribe?: () => void;

  // ---------------------------------------------------------------------------
  // WebAuthn helpers
  // ---------------------------------------------------------------------------

  private fromBase64Url(b64url: string): Uint8Array {
    const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/');
    const pad = '='.repeat((4 - (b64.length % 4)) % 4);
    return Uint8Array.from(atob(b64 + pad), (c) => c.charCodeAt(0));
  }

  private toBase64Url(buf: ArrayBuffer): string {
    return btoa(String.fromCharCode(...new Uint8Array(buf)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
  }

  // ---------------------------------------------------------------------------
  // ARKG / P-256 helpers — client-side key derivation for previewSign step-up.
  // Implements ARKG public-key derivation for PreviewSign assertions.
  // ---------------------------------------------------------------------------

  private static readonly _P = BigInt(
    '0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff'
  );
  private static readonly _N = BigInt(
    '0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551'
  );
  private static readonly _A = BigInt(
    '0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFC'
  );
  private static readonly _GX = BigInt(
    '0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296'
  );
  private static readonly _GY = BigInt(
    '0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5'
  );
  private static readonly _ARKG_DST = new TextEncoder().encode('ARKG-P256');

  private static _mp(a: bigint, m: bigint) {
    return ((a % m) + m) % m;
  }
  private static _mpow(b: bigint, e: bigint, m: bigint) {
    let r = 1n;
    b = ApprovalView._mp(b, m);
    while (e > 0n) {
      if (e & 1n) r = (r * b) % m;
      e >>= 1n;
      b = (b * b) % m;
    }
    return r;
  }
  private static _minv(n: bigint, p: bigint) {
    return ApprovalView._mpow(n, p - 2n, p);
  }

  private static _ecAdd(
    p1: { x: bigint; y: bigint } | null,
    p2: { x: bigint; y: bigint } | null
  ): { x: bigint; y: bigint } | null {
    if (!p1) return p2;
    if (!p2) return p1;
    const P = ApprovalView._P,
      A = ApprovalView._A;
    let k: bigint;
    if (p1.x === p2.x) {
      if (p1.y === ApprovalView._mp(-p2.y, P)) return null;
      k = ((3n * p1.x * p1.x + A) * ApprovalView._minv(2n * p1.y, P)) % P;
    } else {
      k = ((p2.y - p1.y) * ApprovalView._minv(p2.x - p1.x, P)) % P;
    }
    const xr = ApprovalView._mp(k * k - p1.x - p2.x, P);
    const yr = ApprovalView._mp(k * (p1.x - xr) - p1.y, P);
    return { x: xr, y: yr };
  }

  private static _ecMul(
    pt: { x: bigint; y: bigint } | null,
    scalar: bigint
  ): { x: bigint; y: bigint } | null {
    let r: { x: bigint; y: bigint } | null = null;
    let base = pt;
    scalar = ApprovalView._mp(scalar, ApprovalView._N);
    while (scalar > 0n) {
      if (scalar & 1n) r = ApprovalView._ecAdd(r, base);
      base = ApprovalView._ecAdd(base, base);
      scalar >>= 1n;
    }
    return r;
  }

  private static _b2i(b: Uint8Array): bigint {
    let r = 0n;
    for (const x of b) r = (r << 8n) | BigInt(x);
    return r;
  }
  private static _i2b(v: bigint, n: number): Uint8Array {
    const b = new Uint8Array(n);
    for (let i = n - 1; i >= 0; i--) {
      b[i] = Number(v & 0xffn);
      v >>= 8n;
    }
    return b;
  }
  private static _ptUncomp(pt: { x: bigint; y: bigint }): Uint8Array {
    const b = new Uint8Array(65);
    b[0] = 4;
    b.set(ApprovalView._i2b(pt.x, 32), 1);
    b.set(ApprovalView._i2b(pt.y, 32), 33);
    return b;
  }
  private static _cat(...aa: Uint8Array[]): Uint8Array {
    const t = new Uint8Array(aa.reduce((s, a) => s + a.length, 0));
    let o = 0;
    for (const a of aa) {
      t.set(a, o);
      o += a.length;
    }
    return t;
  }
  private static _xor(a: Uint8Array, b: Uint8Array): Uint8Array {
    const r = new Uint8Array(a.length);
    for (let i = 0; i < a.length; i++) r[i] = a[i] ^ b[i];
    return r;
  }
  private static async _sha256(d: Uint8Array) {
    return new Uint8Array(
      await crypto.subtle.digest('SHA-256', d as unknown as BufferSource)
    );
  }

  private static async _xmd(
    msg: Uint8Array,
    dst: Uint8Array,
    len: number
  ): Promise<Uint8Array> {
    const ell = Math.ceil(len / 32);
    const dstp = ApprovalView._cat(dst, new Uint8Array([dst.length]));
    const mp = ApprovalView._cat(
      new Uint8Array(64),
      msg,
      new Uint8Array([(len >> 8) & 0xff, len & 0xff, 0]),
      dstp
    );
    const b0 = await ApprovalView._sha256(mp);
    const b: Uint8Array[] = [b0];
    b.push(
      await ApprovalView._sha256(
        ApprovalView._cat(b0, new Uint8Array([1]), dstp)
      )
    );
    for (let i = 2; i <= ell; i++)
      b.push(
        await ApprovalView._sha256(
          ApprovalView._cat(
            ApprovalView._xor(b[0], b[i - 1]),
            new Uint8Array([i]),
            dstp
          )
        )
      );
    return ApprovalView._cat(...b.slice(1)).slice(0, len);
  }

  private static async _h2s(msg: Uint8Array, dst: Uint8Array): Promise<bigint> {
    const u = await ApprovalView._xmd(msg, dst, 48);
    return ApprovalView._mp(ApprovalView._b2i(u), ApprovalView._N);
  }

  private static async _hmacKemEncaps(
    pkKem: { x: bigint; y: bigint },
    ikm: Uint8Array,
    ctx: Uint8Array
  ): Promise<[Uint8Array, Uint8Array]> {
    const enc = new TextEncoder();
    const aug = enc.encode('ARKG-ECDH.ARKG-P256');
    const G = { x: ApprovalView._GX, y: ApprovalView._GY };
    const ephSk = await ApprovalView._h2s(
      ikm,
      ApprovalView._cat(enc.encode('ARKG-KEM-ECDH-KG.'), aug)
    );
    const ephPk = ApprovalView._ecMul(G, ephSk)!;
    const toB64 = (b: Uint8Array) =>
      btoa(String.fromCharCode(...b))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=/g, '');
    const pkKemCK = await crypto.subtle.importKey(
      'raw',
      ApprovalView._ptUncomp(pkKem) as unknown as BufferSource,
      { name: 'ECDH', namedCurve: 'P-256' },
      false,
      []
    );
    const ephSkCK = await crypto.subtle.importKey(
      'jwk',
      {
        kty: 'EC',
        crv: 'P-256',
        x: toB64(ApprovalView._i2b(ephPk.x, 32)),
        y: toB64(ApprovalView._i2b(ephPk.y, 32)),
        d: toB64(ApprovalView._i2b(ephSk, 32)),
      },
      { name: 'ECDH', namedCurve: 'P-256' },
      false,
      ['deriveBits']
    );
    const kp = new Uint8Array(
      await crypto.subtle.deriveBits(
        { name: 'ECDH', public: pkKemCK },
        ephSkCK,
        256
      )
    );
    const cp = ApprovalView._ptUncomp(ephPk);
    const macInfo = ApprovalView._cat(
      enc.encode('ARKG-KEM-HMAC-mac.'),
      aug,
      ctx
    );
    const sharedInfo = ApprovalView._cat(
      enc.encode('ARKG-KEM-HMAC-shared.'),
      aug,
      ctx
    );
    const hk = await crypto.subtle.importKey(
      'raw',
      kp as unknown as BufferSource,
      { name: 'HKDF' },
      false,
      ['deriveBits', 'deriveKey']
    );
    const mk = await crypto.subtle.deriveKey(
      {
        name: 'HKDF',
        hash: 'SHA-256',
        salt: new Uint8Array([]) as unknown as BufferSource,
        info: macInfo as unknown as BufferSource,
      },
      hk,
      { name: 'HMAC', hash: 'SHA-256', length: 256 },
      false,
      ['sign']
    );
    const t = new Uint8Array(
      await crypto.subtle.sign('HMAC', mk, cp as unknown as BufferSource)
    ).slice(0, 16);
    const k = new Uint8Array(
      await crypto.subtle.deriveBits(
        {
          name: 'HKDF',
          hash: 'SHA-256',
          salt: new Uint8Array([]) as unknown as BufferSource,
          info: sharedInfo as unknown as BufferSource,
        },
        hk,
        kp.length * 8
      )
    );
    return [k, ApprovalView._cat(t, cp)];
  }

  private static async _arkgDerive(
    seed: { pkBl: { x: bigint; y: bigint }; pkKem: { x: bigint; y: bigint } },
    ikm: Uint8Array,
    ctx: Uint8Array
  ): Promise<{ pk: { x: bigint; y: bigint }; kh: Uint8Array }> {
    const enc = new TextEncoder();
    const ctxP = ApprovalView._cat(new Uint8Array([ctx.length]), ctx);
    const ctxKem = ApprovalView._cat(enc.encode('ARKG-Derive-Key-KEM.'), ctxP);
    const ctxBl = ApprovalView._cat(enc.encode('ARKG-Derive-Key-BL.'), ctxP);
    const [ikmTau, c] = await ApprovalView._hmacKemEncaps(
      seed.pkKem,
      ikm,
      ctxKem
    );
    const tau = await ApprovalView._h2s(
      ikmTau,
      ApprovalView._cat(
        enc.encode('ARKG-BL-EC.'),
        ApprovalView._ARKG_DST,
        ctxBl
      )
    );
    const G = { x: ApprovalView._GX, y: ApprovalView._GY };
    const pk = ApprovalView._ecAdd(seed.pkBl, ApprovalView._ecMul(G, tau))!;
    return { pk, kh: new Uint8Array(c) };
  }

  private static _decodeCBOR(data: Uint8Array): unknown {
    let off = 0;
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    function u8() {
      return view.getUint8(off++);
    }
    function u16() {
      const v = view.getUint16(off);
      off += 2;
      return v;
    }
    function u32() {
      const v = view.getUint32(off);
      off += 4;
      return v;
    }
    function head(): { major: number; val: number } {
      const b = u8();
      const major = b >> 5;
      const info = b & 0x1f;
      let val: number;
      if (info < 24) val = info;
      else if (info === 24) val = u8();
      else if (info === 25) val = u16();
      else if (info === 26) val = u32();
      else throw new Error('CBOR: unsupported info ' + info);
      return { major, val };
    }
    function dc(): unknown {
      const { major, val } = head();
      if (major === 0) return val;
      if (major === 1) return -1 - val;
      if (major === 2) {
        const b = data.slice(off, off + val);
        off += val;
        return b;
      }
      if (major === 3) {
        const b = data.slice(off, off + val);
        off += val;
        return new TextDecoder().decode(b);
      }
      if (major === 4) {
        const a: unknown[] = [];
        for (let i = 0; i < val; i++) a.push(dc());
        return a;
      }
      if (major === 5) {
        const m = new Map<unknown, unknown>();
        for (let i = 0; i < val; i++) m.set(dc(), dc());
        return m;
      }
      throw new Error('CBOR: unsupported major ' + major);
    }
    return dc();
  }

  private static _encodeCBOR(value: unknown): Uint8Array {
    const parts: Uint8Array[] = [];
    function wi(major: number, val: number) {
      if (val < 24) parts.push(new Uint8Array([(major << 5) | val]));
      else if (val < 256) parts.push(new Uint8Array([(major << 5) | 24, val]));
      else if (val < 65536) {
        const b = new Uint8Array(3);
        b[0] = (major << 5) | 25;
        new DataView(b.buffer).setUint16(1, val);
        parts.push(b);
      } else {
        const b = new Uint8Array(5);
        b[0] = (major << 5) | 26;
        new DataView(b.buffer).setUint32(1, val);
        parts.push(b);
      }
    }
    function enc(v: unknown) {
      if (typeof v === 'number' && Number.isInteger(v)) {
        if (v >= 0) wi(0, v);
        else wi(1, -1 - v);
      } else if (v instanceof Uint8Array) {
        wi(2, v.length);
        parts.push(v);
      } else if (v instanceof Map) {
        const es = [...v.entries()].sort((a, b) => {
          const am = (a[0] as number) >= 0 ? 0 : 1,
            bm = (b[0] as number) >= 0 ? 0 : 1;
          if (am !== bm) return am - bm;
          return am === 0
            ? (a[0] as number) - (b[0] as number)
            : (b[0] as number) - (a[0] as number);
        });
        wi(5, es.length);
        for (const [k, vv] of es) {
          enc(k);
          enc(vv);
        }
      } else throw new Error('CBOR: unsupported ' + typeof v);
    }
    enc(value);
    const t = new Uint8Array(parts.reduce((s, p) => s + p.length, 0));
    let o = 0;
    for (const p of parts) {
      t.set(p, o);
      o += p.length;
    }
    return t;
  }

  private static _parseArkgSeed(coseKeyBytes: Uint8Array) {
    const key = ApprovalView._decodeCBOR(coseKeyBytes) as Map<number, unknown>;
    const pkBl = key.get(-1) as Map<number, Uint8Array>;
    const pkKem = key.get(-2) as Map<number, Uint8Array>;
    if (!pkBl || !pkKem) throw new Error('ARKG seed missing pkBl or pkKem');
    const pt = (k: Map<number, Uint8Array>) => ({
      x: ApprovalView._b2i(k.get(-2)!),
      y: ApprovalView._b2i(k.get(-3)!),
    });
    return { pkBl: pt(pkBl), pkKem: pt(pkKem) };
  }

  // ---------------------------------------------------------------------------

  private async runStepUpCeremony(token: string): Promise<string | null> {
    const id = this.requestId;

    // 1. Get challenge
    const beginResp = await fetch(
      `/approval/${id}/step-up/begin?token=${encodeURIComponent(token)}`,
      { method: 'POST' }
    );
    if (!beginResp.ok) {
      const err = await beginResp.json();
      throw new Error(err.detail || 'Failed to start verification');
    }
    const {
      session_id,
      options,
      preview_sign_tbs_b64,
      preview_sign_kh_b64,
      preview_sign_seed_pub_b64,
      preview_sign_credential_id_b64,
    } = await beginResp.json();

    // 2. Build PublicKeyCredentialRequestOptions
    const publicKey: PublicKeyCredentialRequestOptions = {
      challenge: this.fromBase64Url(
        options.challenge
      ) as unknown as BufferSource,
      rpId: options.rpId,
      userVerification: (options.userVerification ||
        'required') as UserVerificationRequirement,
      timeout: options.timeout || 60000,
    };
    if (options.allowCredentials?.length) {
      publicKey.allowCredentials = options.allowCredentials.map((c: any) => ({
        type: 'public-key' as PublicKeyCredentialType,
        id: this.fromBase64Url(c.id),
      }));
    }

    // ARKG previewSign step-up using signByCredential format (previewSign v4).
    // The frontend derives a fresh P-256 key pair from the ARKG seed so the
    // YubiKey signs the intent hash with that derived key. The derived public
    // key is sent to the backend for offline ECDSA verification.
    let arkgDerivedPkB64: string | undefined;
    if (
      preview_sign_tbs_b64 &&
      preview_sign_kh_b64 &&
      preview_sign_seed_pub_b64 &&
      preview_sign_credential_id_b64
    ) {
      try {
        const tbs = this.fromBase64Url(preview_sign_tbs_b64);
        const origKh = this.fromBase64Url(preview_sign_kh_b64);
        const seedBytes = this.fromBase64Url(preview_sign_seed_pub_b64);
        const seed = ApprovalView._parseArkgSeed(seedBytes);
        const ikm = crypto.getRandomValues(new Uint8Array(32));
        const ctx = new TextEncoder().encode('preloop-step-up');
        const derived = await ApprovalView._arkgDerive(seed, ikm, ctx);
        arkgDerivedPkB64 = this.toBase64Url(
          ApprovalView._ptUncomp(derived.pk).buffer as ArrayBuffer
        );
        const additionalArgs = ApprovalView._encodeCBOR(
          new Map<number, unknown>([
            [3, -65539], // COSE alg: ARKG-P256
            [-1, derived.kh], // derived key handle
            [-2, ctx], // context
          ])
        );
        const credIdB64 = preview_sign_credential_id_b64;
        const signByCredential: Record<string, unknown> = {
          [credIdB64]: {
            keyHandle: origKh.buffer,
            tbs: tbs.buffer,
            additionalArgs: additionalArgs.buffer,
          },
        };
        publicKey.extensions = {
          previewSign: { signByCredential },
        } as AuthenticationExtensionsClientInputs;
      } catch {
        // ARKG derivation failed (shouldn't happen) — fall back to plain WebAuthn
        arkgDerivedPkB64 = undefined;
      }
    }

    // 3. Browser prompt — throws NotAllowedError if cancelled.
    // No hints: let the browser present all authenticators in allowCredentials,
    // including platform passkeys (Touch ID, Windows Hello) and hardware keys.
    const getOptions = {
      publicKey,
    } as CredentialRequestOptions;
    const credential = (await navigator.credentials.get(
      getOptions
    )) as PublicKeyCredential;
    const authResp = credential.response as AuthenticatorAssertionResponse;

    // Extract previewSign ARKG output. With signByCredential format, the
    // Yubico Authenticator returns previewSign.signature (not .sig/.pk).
    const extResults = credential.getClientExtensionResults() as Record<
      string,
      unknown
    >;
    const psResult = extResults?.previewSign as
      | { signature?: ArrayBuffer }
      | undefined;
    const previewSignSigB64 = psResult?.signature
      ? this.toBase64Url(psResult.signature)
      : undefined;
    // The derived public key was computed client-side during ARKG derivation above.
    const previewSignPkB64 = previewSignSigB64 ? arkgDerivedPkB64 : undefined;

    // 4. Serialize and submit
    const completeBody: Record<string, unknown> = {
      session_id,
      response: {
        id: this.toBase64Url(credential.rawId),
        rawId: this.toBase64Url(credential.rawId),
        type: credential.type,
        response: {
          clientDataJSON: this.toBase64Url(authResp.clientDataJSON),
          authenticatorData: this.toBase64Url(authResp.authenticatorData),
          signature: this.toBase64Url(authResp.signature),
          userHandle: authResp.userHandle
            ? this.toBase64Url(authResp.userHandle)
            : null,
        },
      },
      ...(previewSignSigB64
        ? {
            preview_sign_sig_b64: previewSignSigB64,
            preview_sign_pk_b64: previewSignPkB64,
          }
        : {}),
    };
    const completeResp = await fetch(
      `/approval/${id}/step-up/complete?token=${encodeURIComponent(token)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(completeBody),
      }
    );
    if (!completeResp.ok) {
      const err = await completeResp.json();
      throw new Error(err.detail || 'Verification failed');
    }
    const { verified, credential_name } = await completeResp.json();
    if (!verified) throw new Error('Server did not confirm verification');
    return (credential_name ?? null) as string | null;
  }

  static styles = css`
    :host {
      display: block;
      padding: 2rem;
      max-width: 840px;
      width: 100%;
      box-sizing: border-box;
      min-width: 0;
      overflow-wrap: anywhere;
      margin: 0 auto;
    }

    .header {
      margin-bottom: 2rem;
    }

    .header h1 {
      margin: 0 0 0.5rem 0;
      font-size: 1.75rem;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .header p {
      margin: 0;
      color: var(--sl-color-neutral-600);
    }

    .status-badge {
      font-size: 0.875rem;
    }

    .requested-parameters {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 0.5rem 1rem;
      margin: 1rem 0;
    }
    .requested-parameters dt {
      margin: 0;
      padding: 0;
      text-align: start;
      grid-column: auto;
      color: var(--sl-color-neutral-600);
    }
    .requested-parameters dd {
      margin: 0;
      padding: 0;
      text-align: start;
      grid-column: auto;
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .parameter-value {
      white-space: pre-wrap;
    }
    .requested-parameters pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 0.875rem;
    }
    @media (max-width: 600px) {
      .requested-parameters {
        grid-template-columns: minmax(0, 1fr);
        gap: 0.25rem;
      }
      .requested-parameters dd {
        margin-bottom: 0.5rem;
      }
    }
    .content-section {
      margin-bottom: 1.5rem;
    }

    .content-section h2 {
      font-size: 1.125rem;
      margin: 0 0 0.75rem 0;
      font-weight: 600;
    }

    .info-grid {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 0.75rem;
      margin-bottom: 1rem;
    }

    @media (max-width: 600px) {
      :host {
        padding: 1rem;
      }
      .info-grid {
        grid-template-columns: minmax(0, 1fr);
        gap: 0.35rem;
      }
      .info-value {
        margin-bottom: 0.65rem;
      }
      .header h1 {
        font-size: 1.4rem;
      }
      .flag-list sl-tag {
        max-width: 100%;
      }
      .flag-list sl-tag::part(content) {
        white-space: normal;
        overflow-wrap: anywhere;
      }
    }

    .info-label {
      font-weight: 600;
      color: var(--sl-color-neutral-700);
    }

    .info-value {
      color: var(--sl-color-neutral-900);
    }

    .code-block {
      background: var(--sl-color-neutral-100);
      padding: 1rem;
      border-radius: 4px;
      overflow-x: auto;
      font-family: monospace;
      font-size: 0.875rem;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .reasoning-text {
      background: var(--sl-color-primary-50);
      border-left: 3px solid var(--sl-color-primary-600);
      padding: 1rem;
      border-radius: 4px;
      margin-top: 0.5rem;
      color: var(--sl-color-neutral-900);
      line-height: 1.6;
    }

    .evidence-note {
      color: var(--sl-color-neutral-600);
      font-size: 0.875rem;
      line-height: 1.5;
    }

    .flag-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .actions {
      display: flex;
      gap: 1rem;
      margin-top: 2rem;
    }

    .actions sl-button {
      flex: 1;
    }

    .decision-history {
      margin: 1.25rem 0;
      padding: 1rem;
      background: var(--sl-color-neutral-50);
      border-radius: 0.5rem;
    }
    .decision-history h2 {
      font-size: 1rem;
    }
    .decision-history ol {
      padding-left: 1.25rem;
      line-height: 1.8;
    }
    .comment-section {
      margin-top: 1.5rem;
    }

    .decision-summary .action-title {
      font-size: 1.4rem;
      margin-bottom: 1rem;
      overflow-wrap: anywhere;
    }
    .decision-facts {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }
    .decision-facts p {
      margin: 0;
    }
    .fact-label {
      display: block;
      color: var(--sl-color-neutral-600);
      font-size: 0.8rem;
    }
    .purpose-summary {
      background: var(--sl-color-neutral-50);
      padding: 0.75rem 1rem;
      border-radius: 0.5rem;
      margin: 1rem 0;
    }
    .purpose-summary h3 {
      font-size: 0.875rem;
      margin: 0 0 0.4rem;
    }
    .supplied-purpose {
      white-space: normal;
      overflow-wrap: anywhere;
      text-align: start;
    }
    .purpose-summary sl-details {
      margin-top: 0.5rem;
    }
    .policy-summary {
      margin: 0.75rem 0 0.3rem;
    }
    .header {
      margin-bottom: 1rem;
    }
    .content-section {
      margin-bottom: 1rem;
    }
    .actions {
      margin-top: 1rem;
    }
    .comment-section {
      margin-top: 1rem;
    }
    sl-card {
      width: 100%;
      min-width: 0;
    }
    sl-details {
      overflow-wrap: anywhere;
    }
    .decision-summary sl-details::part(base) {
      border-color: var(--sl-color-neutral-200);
    }
    @media (max-width: 600px) {
      .decision-facts {
        grid-template-columns: minmax(0, 1fr);
        gap: 0.5rem;
      }
      .actions {
        gap: 0.5rem;
        flex-direction: column;
        align-items: stretch;
      }
      .actions sl-button {
        min-width: 0;
        width: 100%;
        flex: none;
      }
      .actions sl-button::part(label) {
        white-space: normal;
      }
      .decision-summary .action-title {
        font-size: 1.2rem;
      }
    }

    .approval-details {
      display: grid;
      gap: 0.5rem;
      margin-top: 1rem;
    }
    .loading-state {
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 3rem;
    }

    .resolved-info {
      margin-top: 1rem;
      padding: 1rem;
      background: var(--sl-color-neutral-50);
      border-radius: 4px;
    }

    .resolved-info h3 {
      margin: 0 0 0.5rem 0;
      font-size: 1rem;
      font-weight: 600;
    }

    .metadata {
      font-size: 0.875rem;
      color: var(--sl-color-neutral-600);
      margin-top: 1rem;
    }

    sl-alert[variant='warning'] {
      margin-bottom: 0.5rem;
    }

    .arkg-proof-badge {
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      margin-top: 1rem;
      padding: 0.875rem 1rem;
      background: var(--sl-color-success-50);
      border: 1px solid var(--sl-color-success-200);
      border-radius: 6px;
      font-size: 0.875rem;
    }

    .arkg-proof-badge .badge-icon {
      color: var(--sl-color-success-600);
      font-size: 1.25rem;
      flex-shrink: 0;
      margin-top: 0.1rem;
    }

    .arkg-proof-badge .badge-body {
      flex: 1;
    }

    .arkg-proof-badge .badge-title {
      font-weight: 600;
      color: var(--sl-color-success-800);
      margin-bottom: 0.25rem;
    }

    .arkg-proof-badge .badge-detail {
      color: var(--sl-color-neutral-600);
      font-family: monospace;
      font-size: 0.8rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .arkg-proof-badge .badge-meta {
      color: var(--sl-color-neutral-500);
      font-size: 0.75rem;
      margin-top: 0.25rem;
    }

    .audit-report {
      margin-top: 1.5rem;
    }

    .audit-header {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--sl-color-neutral-200);
    }

    .audit-header sl-icon {
      font-size: 1.5rem;
      color: var(--sl-color-primary-600);
      flex-shrink: 0;
    }

    .audit-header h2 {
      margin: 0 0 0.2rem 0;
      font-size: 1.1rem;
      font-weight: 600;
    }

    .audit-header p {
      margin: 0;
      font-size: 0.8rem;
      color: var(--sl-color-neutral-500);
    }

    .audit-step {
      display: grid;
      grid-template-columns: 1.5rem 1fr;
      gap: 0.5rem;
      padding: 0.625rem 0;
      border-bottom: 1px solid var(--sl-color-neutral-100);
      font-size: 0.85rem;
    }

    .audit-step:last-child {
      border-bottom: none;
    }

    .step-icon {
      font-weight: 700;
      padding-top: 0.1rem;
    }

    .step-icon.pass {
      color: var(--sl-color-success-600);
    }
    .step-icon.info {
      color: var(--sl-color-primary-600);
    }

    .step-name {
      font-weight: 500;
      margin-bottom: 0.2rem;
    }

    .step-detail {
      color: var(--sl-color-neutral-600);
      font-family: monospace;
      font-size: 0.78rem;
      word-break: break-all;
    }

    .audit-bullet-list {
      margin: 0;
      padding-left: 1.25rem;
      font-size: 0.875rem;
      line-height: 1.7;
    }

    .audit-bullet-list li {
      margin-bottom: 0.5rem;
    }

    .glossary-term {
      margin-bottom: 1rem;
      font-size: 0.875rem;
    }

    .glossary-term dt {
      font-weight: 600;
      color: var(--sl-color-neutral-800);
      margin-bottom: 0.2rem;
    }

    .glossary-term dd {
      margin: 0;
      color: var(--sl-color-neutral-600);
      line-height: 1.6;
    }

    .offline-verify-box {
      margin-top: 1.25rem;
      padding: 0.875rem 1rem;
      background: var(--sl-color-neutral-950);
      border-radius: 6px;
      color: var(--sl-color-neutral-100);
      font-family: monospace;
      font-size: 0.8rem;
      line-height: 1.8;
    }

    .offline-verify-box .comment {
      color: var(--sl-color-neutral-400);
    }
    .offline-verify-box .cmd {
      color: var(--sl-color-success-400);
    }

    sl-details::part(base) {
      border: none;
      border-bottom: 1px solid var(--sl-color-neutral-200);
      border-radius: 0;
    }

    sl-details:last-of-type::part(base) {
      border-bottom: none;
    }

    sl-details::part(summary) {
      font-weight: 600;
      font-size: 0.9rem;
      padding: 0.75rem 0;
    }

    sl-details::part(content) {
      padding: 0.25rem 0 0.75rem 0;
    }
  `;

  private timingInterval?: ReturnType<typeof setInterval>;

  async connectedCallback() {
    super.connectedCallback();
    this.timingInterval = setInterval(() => this.requestUpdate(), 1000);
    // Extract requestId from URL if not set
    if (!this.requestId) {
      const path = window.location.pathname;
      const match = path.match(/\/console\/approval\/([^/?]+)/);
      if (match) {
        this.requestId = match[1];
      }
    }
    await this.loadApprovalRequest();

    // Connect to WebSocket for real-time approval updates
    this.connectWebSocket();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearInterval(this.timingInterval);
    // Disconnect from WebSocket when view is destroyed
    this.unsubscribe?.();
  }

  private connectWebSocket() {
    this.unsubscribe = unifiedWebSocketManager.subscribe(
      'approvals',
      (message: any) => this.handleWebSocketMessage(message),
      // Filter to only receive messages for this approval request
      (message: any) => message.request_id === this.requestId
    );

    // Track connection state
    unifiedWebSocketManager.onStateChange((state) => {
      console.log(`Approval view WebSocket state: ${state}`);
    });
  }

  private handleWebSocketMessage(message: any) {
    // Only process updates for the current approval request
    if (
      message.approval_request_id === this.requestId &&
      this.approvalRequest
    ) {
      console.log('Received approval update:', message);

      // Update the status
      this.approvalRequest = {
        ...this.approvalRequest,
        status: message.status,
        resolved_at: message.resolved_at || this.approvalRequest.resolved_at,
      };

      // Show notification based on event type
      if (message.type === 'approval_approved') {
        this.actionResult = {
          type: 'success',
          message: 'This request was approved!',
        };
      } else if (message.type === 'approval_declined') {
        this.actionResult = {
          type: 'error',
          message: 'This request was declined.',
        };
      } else if (message.type === 'approval_expired') {
        this.actionResult = {
          type: 'error',
          message: 'This request has expired.',
        };
      }
    }
  }

  @state() private currentRequesterName: string | null = null;

  private async loadCurrentRequesterName() {
    try {
      const profile = await getUserProfile();
      const requester =
        this.approvalRequest?.server_recorded_context?.requester;
      if (profile.id && profile.id === requester?.authenticated_user_id) {
        this.currentRequesterName =
          profile.full_name || profile.username || null;
      }
    } catch {
      /* Names are optional presentation data, not identity evidence. */
    }
  }

  private async loadApprovalRequest() {
    this.loading = true;
    this.error = null;

    try {
      const data = await this.fetchData(
        `/api/v1/approval-requests/${this.requestId}`
      );
      if (data) {
        this.approvalRequest = data;
        this.currentRequesterName = null;
        void this.loadCurrentRequesterName();
        if (data.step_up_verified) {
          this.loadReceipt();
        }
      } else {
        this.error = 'Approval request not found';
      }
    } catch (err: any) {
      this.error = err.message || 'Failed to load approval request';
      console.error('Error loading approval request:', err);
    } finally {
      this.loading = false;
    }
  }

  private async loadReceipt(): Promise<void> {
    const req = this.approvalRequest;
    if (!req?.step_up_verified || !req.approval_token || this.receipt) return;
    try {
      const resp = await fetch(
        `/approval/${req.id}/step-up/receipt?token=${encodeURIComponent(req.approval_token)}`
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        this.receiptError = (err as any).detail ?? `HTTP ${resp.status}`;
        return;
      }
      this.receipt = await resp.json();
      const aaguid = this.receipt?.aaguid;
      if (
        !this.receipt?.authenticator_key_protection &&
        typeof aaguid === 'string' &&
        /^[0-9a-f-]{36}$/i.test(aaguid)
      ) {
        // This endpoint reads the server cache, not MDS on every page view.
        try {
          const metadata = await this.fetchData(
            `/api/v1/webauthn/mds/${encodeURIComponent(aaguid)}`
          );
          this.mdsKeyProtection =
            metadata?.found && Array.isArray(metadata.key_protection)
              ? metadata.key_protection.join(', ') || null
              : null;
        } catch {
          this.mdsKeyProtection = null;
        }
      }
    } catch {
      this.receiptError = 'Could not load verification receipt.';
    }
  }

  private async verifyStoredEvidence(): Promise<void> {
    if (!this.approvalRequest) return;
    this.integrityVerification = null;
    this.integrityVerificationError = null;
    try {
      const result = await this.fetchData(
        `/api/v1/audit/decisions/${this.approvalRequest.id}/verify`
      );
      if (!result) {
        this.integrityVerificationError =
          'Stored evidence could not be verified';
        return;
      }
      this.integrityVerification = result;
    } catch (err: any) {
      this.integrityVerificationError =
        err.message || 'Stored evidence could not be verified';
    }
  }

  private async verifyIntentHash(): Promise<void> {
    if (!this.approvalRequest) return;
    this.intentHashVerification = null;
    this.intentHashVerificationError = null;
    const result = await this.fetchData(
      `/api/v1/approval-requests/${this.approvalRequest.id}/verify-intent`
    );
    if (!result) {
      this.intentHashVerificationError = 'Intent Hash could not be verified';
      return;
    }
    this.intentHashVerification = result;
  }

  private async handleApprove() {
    if (!this.approvalRequest) return;
    if (
      this.approvalRequest.expires_at &&
      parseUTCDate(this.approvalRequest.expires_at).getTime() <= Date.now()
    ) {
      this.actionResult = {
        type: 'error',
        message: 'Approval window ended. Request a new action.',
      };
      return;
    }

    this.submitting = true;
    this.actionResult = null;
    this.stepUpError = null;

    let credentialName: string | null = null;
    try {
      // Step-up ceremony required before we can approve
      if (
        this.approvalRequest.step_up_required &&
        !this.approvalRequest.step_up_verified
      ) {
        const token = this.approvalRequest.approval_token;
        if (!token) {
          throw new Error('No approval token — cannot complete verification');
        }
        this.stepUpPending = true;
        try {
          credentialName = await this.runStepUpCeremony(token);
        } finally {
          this.stepUpPending = false;
        }
        // Mark locally so the approve call goes through without re-checking
        this.approvalRequest = {
          ...this.approvalRequest,
          step_up_verified: true,
        };
      }

      const response = await fetch(
        `/api/v1/approval-requests/${this.requestId}/approve`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('accessToken')}`,
          },
          body: JSON.stringify({
            approved: true,
            comment: this.comment || null,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to approve request');
      }

      const updated = await response.json();
      this.approvalRequest = updated;
      this.actionResult = {
        type: 'success',
        message: credentialName
          ? `Approved with ${credentialName}`
          : 'Request approved successfully!',
      };
      this.comment = '';
      if (updated.step_up_verified) {
        this.loadReceipt();
      }
    } catch (err: any) {
      if (
        err.name === 'NotAllowedError' ||
        (err.message || '').includes('cancelled')
      ) {
        this.stepUpError = /\bPinInvalid\b|\bPIN_INVALID\b/.test(
          String(err.message ?? '')
        )
          ? 'Incorrect YubiKey PIN. The request is still pending. If you know the correct PIN, choose Approve to try again. Repeated incorrect attempts can block the key.'
          : 'Verification did not complete. The request is still pending. Choose Approve when you are ready to try again.';
      } else if (
        this.approvalRequest?.step_up_required &&
        !this.approvalRequest.step_up_verified
      ) {
        this.stepUpError =
          err.message ||
          'Could not verify. Make sure your passkey is available and try again.';
      } else {
        this.actionResult = {
          type: 'error',
          message: err.message || 'Failed to approve request',
        };
      }
    } finally {
      this.submitting = false;
    }
  }

  private async handleDecline() {
    if (!this.approvalRequest) return;

    this.submitting = true;
    this.actionResult = null;

    try {
      const response = await fetch(
        `/api/v1/approval-requests/${this.requestId}/decline`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('accessToken')}`,
          },
          body: JSON.stringify({
            approved: false,
            comment: this.comment || null,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to decline request');
      }

      const updated = await response.json();
      this.approvalRequest = updated;
      this.actionResult = {
        type: 'success',
        message: 'Request declined.',
      };
      this.comment = '';
    } catch (err: any) {
      this.actionResult = {
        type: 'error',
        message: err.message || 'Failed to decline request',
      };
    } finally {
      this.submitting = false;
    }
  }

  private formatDate(dateStr: string): string {
    return approvalTimestamp(dateStr);
  }

  private getStatusVariant(
    status: string
  ): 'primary' | 'success' | 'warning' | 'danger' | 'neutral' {
    switch (status) {
      case 'pending':
        return 'warning';
      case 'approved':
        return 'success';
      case 'declined':
        return 'danger';
      case 'expired':
        return 'neutral';
      case 'cancelled':
        return 'neutral';
      default:
        return 'neutral';
    }
  }

  private formatToolArgs(args: Record<string, any>): string {
    // Convert args to JSON string with proper formatting
    const jsonStr = JSON.stringify(args, null, 2);

    // Replace escaped newlines with actual newlines for better readability
    // This handles strings that contain \n, \r\n, etc.
    return jsonStr
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\r')
      .replace(/\\t/g, '\t');
  }

  private renderWebAuthnProofBadge() {
    const req = this.approvalRequest;
    if (!req?.step_up_verified) return '';

    const r = this.receipt;
    const description = describeReceipt(r);
    const receiptAlgorithm = description.algorithm;
    const authLabel =
      description.flags.backupEligible === null
        ? 'Passkey'
        : description.flags.backupEligible
          ? 'Backup-eligible credential'
          : 'Single-device credential';

    const copyWebAuthnReceipt = async () => {
      const token = req.approval_token;
      if (!token) {
        console.error(
          'No approval token — cannot fetch WebAuthn ConsumptionReceipt'
        );
        return;
      }
      try {
        const resp = await fetch(
          `/approval/${req.id}/step-up/receipt?token=${encodeURIComponent(token)}`
        );
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(
            (err as { detail?: string }).detail ?? `HTTP ${resp.status}`
          );
        }
        const receipt = await resp.json();
        navigator.clipboard.writeText(JSON.stringify(receipt, null, 2));
      } catch (err) {
        console.error('Failed to fetch WebAuthn proof receipt:', err);
      }
    };

    return html`
      <div class="arkg-proof-badge">
        <sl-icon class="badge-icon" name="shield-fill-check"></sl-icon>
        <div class="badge-body">
          <div class="badge-title">Passkey verified ✓</div>
          <div class="badge-detail">
            ${receiptAlgorithm.name} · ${authLabel}
          </div>
          <div class="badge-detail" style="margin-top:0.5rem;">
            <sl-button
              size="small"
              variant="default"
              @click=${copyWebAuthnReceipt}
              title="Copy self-contained WebAuthn proof bundle JSON for offline verification"
              style="font-size:0.75rem;"
            >
              <sl-icon slot="prefix" name="clipboard"></sl-icon>
              Copy WebAuthn proof bundle
            </sl-button>
          </div>
        </div>
      </div>
    `;
  }

  private renderReceiptSummary() {
    if (!this.approvalRequest?.step_up_verified) return '';
    const receipt = this.receipt;
    const description = describeReceipt(receipt);
    const algorithm = description.algorithm;
    const flagLabel = (flag: boolean | null) =>
      flag === null
        ? 'Unavailable'
        : flag
          ? 'Verified by server'
          : 'Not verified';
    return html`<sl-card aria-label="Approval receipt">
      <h2>Approval receipt</h2>
      <div class="info-grid">
        <div class="info-label">Signature</div>
        <div>${algorithm.name}</div>
        <div class="info-label">Post-quantum</div>
        <div>
          ${algorithm.kind === 'mldsa'
            ? 'Yes'
            : algorithm.kind === 'unknown'
              ? 'Unknown'
              : 'No'}
        </div>
        <div class="info-label">User present</div>
        <div
          title="User-presence flag in the assertion accepted by the server."
        >
          ${flagLabel(description.flags.userPresent)}
        </div>
        <div class="info-label">User verified</div>
        <div
          title="User-verification flag in the assertion accepted by the server, for example using a PIN."
        >
          ${flagLabel(description.flags.userVerified)}
        </div>
        <div class="info-label">Hardware protection</div>
        <div
          title="Key protection reported for the AAGUID model by cached FIDO MDS metadata. This is model information, not verification of this credential’s attestation."
        >
          ${receipt?.authenticator_key_protection || this.mdsKeyProtection
            ? `${receipt?.authenticator_key_protection || this.mdsKeyProtection} (MDS model metadata)`
            : 'MDS metadata unavailable'}
        </div>
      </div>
      <sl-button
        @click=${this.verifyStoredEvidence}
        title="Recheck the stored signature on the server. This does not check action execution."
        >Verify signature</sl-button
      >
      ${this.integrityVerification
        ? html`<p role="status">
            ${this.integrityVerification.signature_valid
              ? 'Signature verified by server'
              : 'See verification details'}
          </p>`
        : ''}
      <sl-details summary="Receipt JSON">
        <pre class="code-block">
${JSON.stringify(receipt ?? { status: 'Loading' }, null, 2)}</pre
        >
      </sl-details>
    </sl-card>`;
  }

  private renderAuditReport() {
    const req = this.approvalRequest;
    if (!req?.step_up_verified || req.status !== 'approved') return '';

    const r = this.receipt;
    const env = r?.intent_envelope ?? {};
    const toolArgs = env.tool_args ?? req.tool_args ?? {};
    const intentHash = r?.intent_hash_hex ?? req.intent_hash_hex ?? '';
    const signedAt = r?.signed_at ?? '';
    const aaguid = r?.aaguid ?? null;
    const description = describeReceipt(r);
    const receiptAlgorithm = description.algorithm;

    // ARKG path: previewSign extension returned sig+pk → direct prehash ECDSA-P256
    const arkgSig = (r?.arkg_signature_hex as string | null) ?? null;
    const arkgPk = (r?.arkg_derived_pk_hex as string | null) ?? null;
    const isArkg = receiptAlgorithm.kind === 'arkg' && !!(arkgSig && arkgPk);

    // WebAuthn standard-path variables (unused in ARKG branch)
    const challengeNonce = r?.challenge_nonce_hex ?? '';
    const challengeHex = r?.challenge_hex ?? '';

    const {
      userPresent: upSet,
      userVerified: uvSet,
      backupEligible: beSet,
    } = description.flags;

    const algLabel = receiptAlgorithm.label;

    // ARKG: 4-step chain — direct sig over intent_hash bytes, no challenge indirection
    const arkgSteps =
      r && isArkg
        ? [
            {
              name: 'Confirm receipt type and algorithm',
              detail: `receipt_type = "${r.receipt_type}"  ·  alg = ${r.alg ?? '-65539'} (COSE ARKG prehash ES256)`,
            },
            {
              name: 'Verify intent_hash = SHA-256(JCS(intent_envelope))',
              detail: intentHash
                ? `intent_hash = ${intentHash.slice(0, 32)}…`
                : 'intent_hash not present',
            },
            {
              name: 'Decode ARKG derived public key (uncompressed ECDSA-P256)',
              detail: arkgPk
                ? `derived_pk = ${arkgPk.slice(0, 32)}… (65 bytes, 04-prefix uncompressed point)`
                : 'derived_pk not present',
            },
            {
              name: 'Verify ECDSA-P256 prehash signature over intent_hash bytes',
              detail: arkgSig
                ? 'Authenticator signed intent_hash bytes directly — no challenge indirection. Server verified; run offline verifier for independent confirmation.'
                : 'arkg_signature_hex absent — ARKG data unavailable.',
            },
            {
              name: 'WebAuthn ceremony flags (from authenticatorData byte 32)',
              detail: `UP=${upSet ?? 'Unavailable'} (user physically touched key)  ·  UV=${uvSet ?? 'Unavailable'} (PIN or biometric verified by authenticator)  ·  BE=${beSet ?? 'Unavailable'} (backup eligible${beSet ? ' — key may reside in cloud backup' : ''})${r.authenticator_sign_count != null ? `  ·  sign_count=${r.authenticator_sign_count}` : ''}`,
            },
          ]
        : [];

    // WebAuthn standard: 7-step chain
    const webauthnSteps =
      r && !isArkg
        ? [
            {
              name: 'Confirm receipt type and algorithm',
              detail: `receipt_type = "${r.receipt_type}"  ·  alg = ${r.alg ?? 'unknown'} (${receiptAlgorithm.name})`,
            },
            {
              name: 'Verify intent_hash = SHA-256(JCS(intent_envelope))',
              detail: intentHash
                ? `intent_hash = ${intentHash.slice(0, 32)}…`
                : 'intent_hash not present',
            },
            {
              name: 'Verify challenge = SHA-256(intent_hash ∥ nonce)',
              detail: challengeHex
                ? `challenge = ${challengeHex.slice(0, 32)}…`
                : 'challenge not present',
            },
            {
              name: 'Verify clientDataJSON.challenge == base64url(challenge)',
              detail: 'Challenge is bound into the signed clientDataJSON blob.',
            },
            {
              name: 'Parse authenticatorData flags and sign counter',
              detail: `UP=${upSet ?? 'Unavailable'} (User Present)  ·  UV=${uvSet ?? 'Unavailable'} (User Verified / PIN)  ·  BE=${beSet ?? 'Unavailable'} (Backup Eligible)${r.authenticator_sign_count != null ? `  ·  sign_count=${r.authenticator_sign_count} (FIDO2 clone-detection counter — a regression signals potential credential cloning)` : '  ·  sign_count=not recorded'}`,
            },
            {
              name: 'Compute client_data_hash = SHA-256(clientDataJSON)',
              detail: 'Hash is part of the signed payload.',
            },
            {
              name:
                receiptAlgorithm.kind === 'unknown'
                  ? 'Receipt signature algorithm is unknown'
                  : `Verify ${receiptAlgorithm.name} signature over (authData ∥ client_data_hash)`,
              detail: r.public_key_cbor_hex
                ? receiptAlgorithm.kind === 'es256'
                  ? 'Server verified the stored assertion. Run the bundled offline verifier for independent assertion confirmation; this does not verify tool execution.'
                  : receiptAlgorithm.kind === 'mldsa'
                    ? 'Server verified the stored assertion. This browser does not perform ML-DSA verification; use independent ML-DSA-capable tooling to confirm the assertion offline. This does not verify tool execution.'
                    : 'The server accepted the stored assertion, but this UI has no independent verification instructions for the unknown algorithm. This does not verify tool execution.'
                : 'public_key_cbor_hex absent — key was de-enrolled after step-up.',
            },
          ]
        : [];

    const steps = isArkg ? arkgSteps : webauthnSteps;
    const stepCount = isArkg ? 5 : 7;

    const proven = isArkg
      ? [
          'The approval data is tamper-evident. Altering any field — account, request ID, tool name, any argument, or the requested_at timestamp — changes the intent_hash, which immediately breaks the ARKG signature.',
          'The server accepted an ECDSA-P256 signature over the intent_hash using the registered ARKG-derived public key. Independently verify the stored signature with the bundled verifier.',
          'The receipt records the ARKG key handle and derived public key. These fields alone do not establish hardware key protection or device uniqueness.',
          upSet === null
            ? 'User presence is unavailable: authenticator data is missing or malformed.'
            : upSet
              ? "The User Present (UP) flag was set in the WebAuthn ceremony that authorized this ARKG signature — the key's touch sensor was activated. This is enforced by authenticator firmware and recorded in authenticatorData."
              : 'UP (User Present) was NOT set in the WebAuthn ceremony — no touch confirmation was recorded.',
          ...(uvSet
            ? [
                'The User Verified (UV) flag was set: the authenticator required a PIN or biometric check as part of the WebAuthn ceremony that produced the ARKG signature.',
              ]
            : []),
          ...(beSet
            ? [
                '⚠ BE (Backup Eligible) is set: the signing credential may reside in cloud backup (e.g. iCloud Keychain, Google Password Manager). Hardware-binding is not guaranteed — verify key protection level via the authenticator information above.',
              ]
            : []),
        ]
      : [
          'The approval data is tamper-evident. Altering any field — account, request ID, tool name, any argument, or the requested_at timestamp — changes the intent_hash, which changes the challenge, which breaks the clientDataJSON binding and the signature.',
          receiptAlgorithm.kind === 'unknown'
            ? 'The receipt records an unrecognized signature algorithm. This UI does not infer its cryptographic properties or claim independent signature verification.'
            : `The server accepted a ${receiptAlgorithm.name} assertion from the registered credential. This presentation alone is not independent cryptographic verification and does not verify that the approved tool execution occurred.`,
          upSet === null
            ? 'User presence is unavailable: authenticator data is missing or malformed.'
            : upSet
              ? 'The User Present (UP) flag was set in the recorded authenticator response.'
              : 'The User Present (UP) flag was not set in the recorded authenticator response.',
          ...(uvSet
            ? [
                'The enrolled credential holder was verified (UV = set): the authenticator required a PIN or biometric check before signing. This is the same level of identity assurance that major identity providers deliver with passkeys.',
              ]
            : []),
        ];

    const notProven = isArkg
      ? [
          uvSet === null
            ? 'User verification is unavailable: authenticator data is missing or malformed.'
            : uvSet
              ? 'The specific verification method (PIN vs biometric) — UV was set, but the WebAuthn receipt does not record which UV mechanism the authenticator used.'
              : 'User identity — UV (User Verified) was NOT set: only physical possession of the authenticator was demonstrated. No PIN or biometric check was required.',
          'Whether the registered credential belongs to exactly one individual. If a device PIN or biometric is shared, this proof covers the credential holder — not a unique biological person.',
          'That the public key still corresponds to an active enrolled credential. The verifier cannot confirm the ARKG seed was not de-enrolled after the step-up.',
          'Merkle-anchored non-repudiation — the scitt_receipt field is null in this receipt.',
        ]
      : [
          uvSet === null
            ? 'User verification is unavailable: authenticator data is missing or malformed.'
            : uvSet
              ? 'The specific verification method (PIN vs biometric) — UV was set and the credential holder authenticated, but the WebAuthn receipt does not record which UV mechanism was used by the authenticator.'
              : 'User identity — UV (User Verified) was NOT set: only physical possession of the authenticator was demonstrated. No PIN or biometric check was required at the time of this step-up.',
          'Whether the registered credential belongs to exactly one individual. If a device PIN or biometric is shared, this proof covers the credential holder — not a unique biological person.',
          ...(beSet
            ? [
                'Physical device uniqueness — BE (Backup Eligible) is set: this credential may be synced across devices (e.g. a platform passkey). Hardware-bound uniqueness cannot be assumed.',
              ]
            : []),
          'That the public key still corresponds to an active enrolled credential. This verifier cannot confirm the key was not de-enrolled after the step-up.',
          'Merkle-anchored non-repudiation — the scitt_receipt field is null in this receipt.',
        ];

    const arkgGlossaryEntries: Array<[string, string]> = [
      [
        'ARKG (Asymmetric Ratchet Key Generation)',
        'A key derivation protocol that lets an authenticator derive fresh ECDSA key pairs from a seed without storing the private key. The Yubico previewSign extension implements ARKG: at registration, the authenticator returns a seed public key and a key handle (kh); at authentication, it uses the kh to re-derive the same key pair and signs the payload.',
      ],
      [
        'previewSign extension',
        'A Yubico-proprietary WebAuthn extension implemented in YubiKey firmware 5.8+ and the Yubico Authenticator browser extension. At authentication, tbs (to-be-signed bytes = intent_hash) and kh (key handle) are sent; the authenticator returns sig (ECDSA-P256 signature) and pk (derived public key). The extension is silently ignored by all other authenticators.',
      ],
      [
        'COSE algorithm -65539',
        "Yubico's COSE identifier for the ARKG previewSign scheme. The signing operation is prehash ECDSA-P256: the authenticator signs the raw intent_hash bytes directly (the hash itself is the TBS), rather than hashing again. This is distinct from COSE -7 (ES256), which signs (authData ∥ SHA-256(clientDataJSON)).",
      ],
      [
        'Prehash ECDSA-P256',
        'The authenticator computes ECDSA-P256 over the raw 32-byte intent_hash (already a SHA-256 digest). Offline verification uses `ec.ECDSA(hashes.Prehashed())` from the Python cryptography library.',
      ],
    ];

    const webauthnGlossaryEntries: Array<[string, string]> = [
      [
        'WebAuthn / FIDO2',
        'W3C + FIDO Alliance protocol for phishing-resistant authentication. The browser mediates between an authenticator and the server. For roaming hardware keys (YubiKey, etc.), the private key is stored in a secure element and never exported. For platform authenticators (Touch ID, Windows Hello, Android), the OS may sync private key material to the cloud — look up the AAGUID in the FIDO MDS to confirm the key protection level.',
      ],
      [
        'AAGUID',
        'A 16-byte UUID that identifies the authenticator model (e.g. YubiKey 5 NFC, Apple Touch ID, Windows Hello). Preloop looks up the AAGUID in the FIDO Metadata Service (MDS v3) at registration time and stores the authenticator name, key protection type, and icon. Different device generations have different AAGUIDs.',
      ],
      receiptAlgorithm.kind === 'es256'
        ? [
            'COSE algorithm -7 (ES256)',
            'ECDSA over P-256 with SHA-256 — the standard WebAuthn signature scheme. The key is registered in the standard WebAuthn fashion and the signed payload is (authenticatorData ∥ SHA-256(clientDataJSON)).',
          ]
        : receiptAlgorithm.kind === 'mldsa'
          ? [
              `COSE algorithm ${receiptAlgorithm.alg} (${receiptAlgorithm.name})`,
              'A post-quantum ML-DSA WebAuthn signature algorithm. Preloop can ask the server to verify the stored assertion, but this browser UI does not perform ML-DSA verification.',
            ]
          : [
              'Unknown receipt algorithm',
              `The receipt reports COSE algorithm ${receiptAlgorithm.alg ?? 'unknown'}. This UI does not map it to a signature scheme or verification procedure.`,
            ],
      [
        'Challenge derivation',
        'The WebAuthn challenge is SHA-256(intent_hash_bytes ∥ challenge_nonce_bytes). This binds the authenticator response to the action fingerprint and nonce. Replay prevention also depends on freshness, session consumption and executor enforcement; this receipt alone does not establish those checks.',
      ],
      [
        'authenticatorData flags',
        'A flags byte at offset 32 of the authenticatorData blob. UP (bit 0) = User Present (touch). UV (bit 2) = User Verified (PIN/biometric). BE (bit 3) = Backup Eligible (cloud-syncable key).',
      ],
      [
        'Signed payload',
        'The bytes the authenticator actually signs: authenticatorData ∥ SHA-256(clientDataJSON). clientDataJSON includes the challenge, origin, and type. Both are verified by the offline script.',
      ],
      [
        'Sign counter (FIDO2 §6.1.1)',
        'A monotonically increasing counter stored on the authenticator and incremented on every signature. A server observing a counter value ≤ a previously seen value should treat this as a security alert (FIDO2 §6.1.1): it indicates the authenticator may have been cloned — either the credential material was extracted from hardware or a backup was restored from an older snapshot. Hardware security keys maintain the counter in tamper-resistant storage; software passkeys (platform authenticators) may reset it on device restore.',
      ],
    ];

    const sharedGlossaryEntries: Array<[string, string]> = [
      [
        'intent_hash',
        'SHA-256 fingerprint of the JCS-canonical authorization envelope. Covers account_id, approval_request_id, tool_name, tool_args, and requested_at. Any change to any field invalidates the hash and breaks the signature.',
      ],
      [
        'JCS (JSON Canonicalization Scheme)',
        'RFC 8785 — produces a deterministic UTF-8 byte string from any JSON value regardless of key ordering or whitespace. Used to compute intent_hash so both the client and an offline auditor produce the same bytes.',
      ],
      [
        'COSE (CBOR Object Signing and Encryption)',
        'RFC 8152 / RFC 9052 — defines algorithm IDs (e.g. -7 for ES256, -65539 for ARKG prehash ES256) and key formats used by FIDO2. The public key in the receipt is encoded as a COSE key in CBOR.',
      ],
      [
        'Offline verification',
        receiptAlgorithm.kind === 'es256' || isArkg
          ? "No network call, no Preloop account, and no trust in Preloop's servers is required when the matching bundled offline verifier succeeds. Verification uses only the receipt fields and cryptographic primitives."
          : 'This page does not independently verify this receipt algorithm. Server assertion verification is a separate check and does not prove that tool execution occurred.',
      ],
    ];

    const glossary = isArkg
      ? [...arkgGlossaryEntries, ...sharedGlossaryEntries]
      : [...webauthnGlossaryEntries, ...sharedGlossaryEntries];

    const offlineInstruction = isArkg
      ? html`<span class="cmd"
          >python scripts/verify_arkg_proof.py receipt.json</span
        >`
      : receiptAlgorithm.kind === 'es256'
        ? html`<span class="cmd"
            >python scripts/verify_webauthn_proof.py receipt.json</span
          >`
        : receiptAlgorithm.kind === 'mldsa'
          ? html`<span class="comment"
              >Verify offline: python scripts/verify_webauthn_proof.py
              receipt.json. Use the workshop Python environment with ML-DSA
              support.</span
            >`
          : html`<span class="comment"
              >No offline verification instructions are available for
              ${receiptAlgorithm.label}.</span
            >`;

    const reportTitle = 'Verification details';

    const reportSubtitle = isArkg
      ? html`Mirrors <code>scripts/verify_arkg_proof.py</code> — the offline
          auditor script included in this repository. ARKG previewSign path: the
          authenticator signed the intent hash directly.`
      : receiptAlgorithm.kind === 'es256'
        ? html`Mirrors <code>scripts/verify_webauthn_proof.py</code> — the
            offline auditor script included in this repository.`
        : receiptAlgorithm.kind === 'mldsa'
          ? html`Receipt presentation for ${receiptAlgorithm.name}. The browser
            does not independently verify this ML-DSA assertion.`
          : html`The receipt algorithm is not recognized. No signature scheme or
            verifier is inferred.`;

    return html`
      <sl-card class="audit-report">
        <div class="audit-header">
          <sl-icon name="journal-check"></sl-icon>
          <div>
            <h2>${reportTitle}</h2>
            <p>${reportSubtitle}</p>
          </div>
        </div>
        <sl-button variant="primary" @click=${this.verifyStoredEvidence}>
          Verify stored evidence
        </sl-button>
        <p class="evidence-note">
          This requests server assertion verification. It is not browser-side
          independent verification and does not independently verify tool
          execution.
        </p>
        ${this.integrityVerification
          ? html`<p class="evidence-note">
              Intent Hash match:
              <strong
                >${this.integrityVerification.intent_intact
                  ? 'valid'
                  : 'invalid'}</strong
              >; challenge binding:
              <strong
                >${this.integrityVerification.challenge_bound
                  ? 'valid'
                  : 'invalid'}</strong
              >; signature verification:
              <strong
                >${this.integrityVerification.signature_valid
                  ? 'valid'
                  : 'invalid'}</strong
              >.
            </p>`
          : ''}
        ${this.integrityVerificationError
          ? html`<sl-alert variant="danger" open>
              ${this.integrityVerificationError}
            </sl-alert>`
          : ''}

        <!-- What was authorized -->
        <sl-details summary="Signed action envelope">
          <div class="info-grid" style="font-size:0.85rem;">
            <div class="info-label">Request ID</div>
            <div class="info-value">
              <code style="font-size:0.78rem;">${req.id}</code>
            </div>
            <div class="info-label">Account ID</div>
            <div class="info-value">
              <code style="font-size:0.78rem;"
                >${env.account_id ?? req.account_id}</code
              >
            </div>
            <div class="info-label">Tool / Action</div>
            <div class="info-value">
              <strong>${env.tool_name ?? req.tool_name}</strong>
            </div>
            <div class="info-label">Requested at</div>
            <div class="info-value">
              ${env.requested_at ?? req.requested_at}
            </div>
            ${signedAt
              ? html` <div class="info-label">Signed at</div>
                  <div class="info-value">${signedAt}</div>`
              : ''}
            <div class="info-label">Algorithm</div>
            <div class="info-value">${algLabel}</div>
            ${aaguid
              ? (() => {
                  const mdsDesc =
                    (r?.authenticator_description as string | null) ?? null;
                  const mdsKp =
                    (r?.authenticator_key_protection as string | null) ?? '';
                  const mdsIcon =
                    (r?.authenticator_icon as string | null) ?? null;
                  const isHw = mdsKp.includes('hardware');
                  const isSe =
                    mdsKp.includes('tee') || mdsKp.includes('secure_element');
                  const isSw = mdsKp.includes('software') && !isHw;
                  return html` <div class="info-label">Authenticator</div>
                    <div
                      class="info-value"
                      style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;"
                    >
                      ${mdsIcon
                        ? html`<img
                            src="${mdsIcon}"
                            style="height:36px;width:auto;border-radius:4px;"
                            alt="authenticator icon"
                          />`
                        : ''}
                      <strong style="font-size:0.85rem;"
                        >${mdsDesc || aaguid}</strong
                      >
                      ${isSe
                        ? html`<sl-badge variant="success" pill
                            >TEE or secure element (model metadata)</sl-badge
                          >`
                        : ''}
                      ${isHw && !isSe
                        ? html`<sl-badge variant="success" pill
                            >Hardware protection (model metadata)</sl-badge
                          >`
                        : ''}
                      ${isSw
                        ? html`<sl-badge variant="warning" pill
                            >Software-protected key</sl-badge
                          >`
                        : ''}
                      ${!mdsDesc
                        ? ''
                        : html`<code
                            style="font-size:0.72rem;opacity:0.55;margin-left:0.25rem;"
                            >${aaguid}</code
                          >`}
                      ${beSet
                        ? html`<sl-badge variant="warning" pill
                            >Backup-eligible</sl-badge
                          >`
                        : ''}
                    </div>`;
                })()
              : ''}
            ${intentHash
              ? html` <div class="info-label">Intent hash</div>
                  <div
                    class="info-value"
                    style="font-family:monospace;font-size:0.72rem;word-break:break-all;"
                  >
                    ${intentHash}
                  </div>`
              : ''}
            ${isArkg && arkgPk
              ? html` <div class="info-label">ARKG derived public key</div>
                  <div
                    class="info-value"
                    style="font-family:monospace;font-size:0.72rem;word-break:break-all;"
                  >
                    ${arkgPk.slice(0, 64)}…
                  </div>`
              : ''}
          </div>
          ${Object.keys(toolArgs).length
            ? html` <div
                  style="margin-top:0.75rem;font-size:0.85rem;font-weight:600;"
                >
                  Tool Arguments
                </div>
                <div
                  class="code-block"
                  style="margin-top:0.25rem;font-size:0.8rem;"
                >
                  ${JSON.stringify(toolArgs, null, 2)}
                </div>`
            : ''}
        </sl-details>

        <!-- Verification chain — step count depends on ARKG vs WebAuthn path -->
        <sl-details
          summary="Cryptographic Verification Chain — ${stepCount} Steps"
        >
          ${r
            ? steps.map(
                (s, i) =>
                  html` <div class="audit-step">
                    <div class="step-icon pass">✓</div>
                    <div>
                      <div class="step-name">Step ${i + 1} — ${s.name}</div>
                      <div class="step-detail">${s.detail}</div>
                    </div>
                  </div>`
              )
            : this.receiptError
              ? html`<p
                  style="color:var(--sl-color-neutral-500);font-size:0.85rem;"
                >
                  ${this.receiptError}
                </p>`
              : html`<sl-spinner style="font-size:1.5rem;"></sl-spinner>`}
        </sl-details>

        <!-- What it proves -->
        <sl-details summary="What This Verification Proves">
          <ol class="audit-bullet-list">
            ${proven.map((p) => html`<li>${p}</li>`)}
          </ol>
        </sl-details>

        <!-- Limitations -->
        <sl-details summary="Limitations — What This Does Not Prove">
          <ol class="audit-bullet-list">
            ${notProven.map((p) => html`<li>${p}</li>`)}
          </ol>
        </sl-details>

        <!-- Glossary -->
        <sl-details summary="Glossary of Terms">
          <dl>
            ${glossary.map(
              ([term, def]) =>
                html` <div class="glossary-term">
                  <dt>${term}</dt>
                  <dd>${def}</dd>
                </div>`
            )}
          </dl>
        </sl-details>

        <!-- Offline verification -->
        <div class="offline-verify-box">
          ${receiptAlgorithm.kind === 'es256' || isArkg
            ? html`<span class="comment"># Install dependencies</span><br />
                <span class="cmd">pip install cryptography jcs cbor2</span
                ><br /><br />`
            : ''}
          ${receiptAlgorithm.kind === 'es256' || isArkg
            ? html`<span class="comment"
                  ># Copy proof bundle to receipt.json (button above), then run
                  the offline verifier:</span
                ><br />`
            : ''}
          ${offlineInstruction}
        </div>
      </sl-card>
    `;
  }

  private renderActionDetails(open: boolean) {
    if (!this.approvalRequest) return '';
    return html`<sl-details summary="Action details" ?open=${open}>
      <h3>Tool arguments</h3>
      <pre class="code-block">
${this.formatToolArgs(this.approvalRequest.tool_args)}</pre
      >
      <sl-details summary="Request metadata">
        ${this.approvalRequest.decided_by_user_id
          ? html`<p>
              Final decision by:
              <code>${this.approvalRequest.decided_by_user_id}</code>
            </p>`
          : ''}
        ${this.approvalRequest.decided_at
          ? html`<p>
              Decision time: ${this.formatDate(this.approvalRequest.decided_at)}
            </p>`
          : ''}
        <div class="content-section">
          <h2>Tool Information</h2>
          <div class="info-grid">
            <div class="info-label">Tool Name:</div>
            <div class="info-value">
              <strong>${this.approvalRequest.tool_name}</strong>
            </div>

            <div class="info-label">Request ID:</div>
            <div class="info-value">
              <code style="font-size: 0.75rem;"
                >${this.approvalRequest.id}</code
              >
            </div>

            <div class="info-label">Requested:</div>
            <div class="info-value">
              ${this.formatDate(this.approvalRequest.requested_at)}
            </div>

            ${this.approvalRequest.expires_at
              ? html`
                  <div class="info-label">Approval deadline:</div>
                  <div class="info-value">
                    ${this.formatDate(this.approvalRequest.expires_at)}
                  </div>
                `
              : ''}
            ${this.approvalRequest.execution_id
              ? html`
                  <div class="info-label">Execution ID:</div>
                  <div class="info-value">
                    <code style="font-size: 0.75rem;"
                      >${this.approvalRequest.execution_id}</code
                    >
                  </div>
                `
              : ''}
          </div>
        </div>
      </sl-details>
    </sl-details>`;
  }

  private renderReasonDetails() {
    if (!this.approvalRequest) return '';
    const hasMeasuredAssessment = Boolean(
      this.approvalRequest.intent_verified &&
      this.approvalRequest.intent_model &&
      this.approvalRequest.intent_model !== 'rule_based'
    );
    const assessmentStatus = !this.approvalRequest.intent_risk_tier
      ? 'Not configured or no assessment recorded'
      : !this.approvalRequest.intent_verified
        ? 'Verifier unavailable or failed; rule result retained'
        : this.approvalRequest.intent_model === 'rule_based'
          ? 'Rule-only assessment'
          : 'Model assessment completed';

    return html`
      <sl-details summary="Assessment and signature binding">
        <div class="content-section" data-testid="intent-assessment">
          <h2>Intent Verifier Assessment</h2>
          <div class="info-grid">
            <div class="info-label">Assessment status:</div>
            <div class="info-value">${assessmentStatus}</div>
            <div class="info-label">Intent Risk Tier:</div>
            <div class="info-value">
              ${this.approvalRequest.intent_risk_tier ?? 'Unavailable'}
            </div>
            <div class="info-label">Action Class:</div>
            <div class="info-value">
              ${this.approvalRequest.action_class ?? 'Not classified'}
            </div>
            <div class="info-label">Description Match:</div>
            <div class="info-value">
              ${!this.approvalRequest.agent_reasoning
                ? 'Not interpretable — Agent Reasoning was not supplied'
                : !hasMeasuredAssessment ||
                    this.approvalRequest.intent_description_match_score == null
                  ? 'Not measured by a model'
                  : `${Math.round(
                      this.approvalRequest.intent_description_match_score * 100
                    )}% verifier-assessed match (model estimate)`}
            </div>
          </div>
          <div class="flag-list" aria-label="Intent flags">
            ${(this.approvalRequest.intent_flags ?? []).length
              ? (this.approvalRequest.intent_flags ?? []).map(
                  (flag) => html`<sl-tag variant="warning">${flag}</sl-tag>`
                )
              : html`<span class="evidence-note">No flags recorded</span>`}
          </div>
          ${this.approvalRequest.intent_reasoning
            ? html`<h3>
                  Intent Reasoning <small>(verifier assessment)</small>
                </h3>
                <div class="reasoning-text">
                  ${this.approvalRequest.intent_reasoning}
                </div>`
            : html`<p class="evidence-note">
                No verifier reasoning is available for this request.
              </p>`}
          <p class="evidence-note">
            Intent Hash matching checks covered evidence integrity. It does not
            verify a hardware signature, prove the agent's assertion, or endorse
            the verifier assessment.
          </p>
          ${this.approvalRequest.intent_hash_hex
            ? html`<sl-button
                  variant="default"
                  data-testid="verify-intent-hash"
                  @click=${this.verifyIntentHash}
                >
                  Verify Intent Hash
                </sl-button>
                ${this.intentHashVerification
                  ? html`<p class="evidence-note" role="status">
                      Version ${this.intentHashVerification.envelope_version}
                      envelope:
                      <strong
                        >${this.intentHashVerification.intent_intact
                          ? 'hash matches'
                          : 'hash mismatch'}</strong
                      >. Hardware signature:
                      <strong>not verified by this check</strong>.
                    </p>`
                  : ''}
                ${this.intentHashVerificationError
                  ? html`<sl-alert variant="danger" open>
                      ${this.intentHashVerificationError}
                    </sl-alert>`
                  : ''}`
            : ''}
        </div>
      </sl-details>
    `;
  }

  private renderRequestedParameters() {
    const args: unknown = this.approvalRequest?.tool_args;
    const entries =
      args && typeof args === 'object' && !Array.isArray(args)
        ? Object.entries(args)
        : [['Arguments', args]];
    return html`<dl
      class="requested-parameters"
      aria-label="Requested parameters"
    >
      ${entries.length
        ? entries.map(
            ([key, value]) =>
              html`<dt>${key.replaceAll('_', ' ')}</dt>
                <dd>
                  ${typeof value === 'string'
                    ? html`<span class="parameter-value">${value}</span>`
                    : html`<pre>
${JSON.stringify(value, null, 2) ?? 'Not recorded'}</pre
                      >`}
                </dd>`
          )
        : html`<dd>No parameters supplied.</dd>`}
    </dl>`;
  }

  private decisionLabel() {
    switch (this.approvalRequest?.status) {
      case 'approved':
        return 'Approval recorded';
      case 'declined':
        return 'Request denied';
      case 'expired':
        return 'Request expired';
      case 'cancelled':
        return 'Request cancelled';
      default:
        return 'Review requested action';
    }
  }

  private renderDecisionHistory() {
    const request = this.approvalRequest!;
    if (request.status === 'pending') return '';
    return html`<section class="decision-history" aria-label="Decision history">
      <h2>Decision history</h2>
      <ol>
        <li>
          <strong>Requested</strong> · ${this.formatDate(request.requested_at)}
        </li>
        <li>
          <strong>${this.decisionLabel()}</strong>${request.decided_at ||
          request.resolved_at
            ? html` ·
              ${this.formatDate(request.decided_at || request.resolved_at!)}`
            : ''}
        </li>
        ${request.status === 'approved'
          ? html`<li>
              <strong>Execution not checked</strong>
              <p class="evidence-note">
                Check the tool result and resulting state separately.
              </p>
            </li>`
          : ''}
      </ol>
    </section>`;
  }

  private renderDecisionSummary() {
    const request = this.approvalRequest!;
    const context = request.server_recorded_context;
    const policy = context?.policy;
    const reason =
      policy?.evaluation_outcome === 'error_fallback'
        ? 'Policy evaluation failed; human review is required.'
        : policy?.matched_rule?.action === 'require_approval'
          ? 'A configured policy rule requires approval.'
          : policy?.evaluation_source === 'tool_configuration'
            ? 'This tool requires approval.'
            : 'The policy reason was not recorded.';
    const suppliedReason = context?.purpose?.text ?? request.agent_reasoning;
    return html`<section
      class="content-section decision-summary"
      aria-label="Decision summary"
      data-testid="decision-summary"
    >
      <h2 class="action-title">${request.tool_name}</h2>
      <div class="decision-facts">
        <p>
          <span class="fact-label">Requested by</span
          ><strong
            >${context?.requester?.display_name ||
            this.currentRequesterName ||
            'Requester not recorded'}</strong
          >${context?.requester?.authentication?.type === 'api_key_credential'
            ? html`<span class="evidence-note"> · Using their API key</span>`
            : context?.requester?.authentication?.type ===
                'authenticated_user_session'
              ? html`<span class="evidence-note"> · Signed-in user</span>`
              : ''}
        </p>
        <p>
          <span class="fact-label">Approval window</span>${request.expires_at
            ? approvalDeadline(request.expires_at, request.status)
            : 'Expiry not recorded.'}
        </p>
      </div>
      ${this.renderRequestedParameters()}
      <div class="purpose-summary" data-testid="agent-reasoning">
        <h3 title="Caller supplied, not independently verified">
          Reason provided
        </h3>
        <div class="supplied-purpose">
          <span class="parameter-value"
            >${typeof suppliedReason === 'string' && suppliedReason.trim()
              ? suppliedReason
              : 'No reason supplied.'}</span
          >
        </div>
      </div>
      <p class="policy-summary">${reason}</p>
      <p class="evidence-note">
        This exact request
        only.${request.status === 'pending' && request.step_up_required
          ? ' Passkey confirmation required.'
          : ''}
      </p>
    </section>`;
  }

  private renderRecordedEvidence() {
    if (!this.approvalRequest) return html``;
    const evidence = this.approvalRequest.server_recorded_context;
    const requester = evidence?.requester;
    const policy = evidence?.policy;
    const rule = policy?.matched_rule;
    const workflow = evidence?.workflow;
    const fallback = policy?.evaluation_outcome === 'error_fallback';
    return html` <section
        class="content-section"
        aria-label="Role Delegation Token"
        data-testid="rdt-authority-summary"
      >
        <h2>Who is requesting authority?</h2>
        <div class="info-grid">
          <div class="info-label">Authenticated requester:</div>
          <div class="info-value">
            ${requester?.authenticated_user_id
              ? html`User <code>${requester.authenticated_user_id}</code>`
              : 'Identity not recorded in this request'}
          </div>
          <div class="info-label">Requesting agent:</div>
          <div class="info-value">
            ${requester?.agent?.id
              ? html`Configured association:
                  <code>${requester.agent.id}</code> — agent identity unverified`
              : 'Agent identity not established'}
          </div>
          <div class="info-label">Acting for:</div>
          <div class="info-value">Delegating principal not recorded</div>
          <div class="info-label">Requested scope:</div>
          <div class="info-value">
            ${this.approvalRequest.tool_name}, with the exact arguments below.
            Broader authority is not established.
          </div>
          <div class="info-label">Approval deadline:</div>
          <div class="info-value">
            ${this.approvalRequest.expires_at
              ? this.formatDate(this.approvalRequest.expires_at)
              : 'Not recorded'}
          </div>
        </div>
        <p class="evidence-note">
          ${evidence
            ? 'Server-recorded context. These identity and policy details are not covered by the hardware signature.'
            : 'Historical identity and policy context was not recorded; it cannot be reconstructed from current settings.'}
        </p>
        <sl-details summary="Role Delegation Token: authority and evidence">
          <p>
            This record uses Preloop's existing envelope. Compatibility with
            external RDT authorization and consent contracts is not yet
            validated.
          </p>
          <p>
            A hardware signature does not by itself establish agent identity,
            delegated authority or execution.
          </p>
          <p>
            Authentication source:
            ${requester?.authentication?.type === 'api_key_credential'
              ? 'API-key credential associated with this user; not a verified agent identity'
              : requester?.authentication?.type === 'authenticated_user_session'
                ? 'Authenticated user session'
                : 'Not recorded'}
          </p>
        </sl-details>
      </section>
      <section
        class="content-section"
        aria-label="Policy decision"
        data-testid="recorded-policy"
      >
        <h2>Why is approval required?</h2>
        <p>
          ${fallback
            ? 'Policy evaluation failed. This request was escalated for approval; no successful rule match is recorded.'
            : rule?.action === 'require_approval'
              ? 'A configured policy rule matched this request and required approval.'
              : rule
                ? 'A configured policy rule was recorded. Review its action and the workflow below.'
                : policy?.evaluation_source === 'tool_configuration'
                  ? 'The tool configuration requires approval for this action.'
                  : 'The rule and decision context were not recorded for this request.'}
        </p>
        ${workflow
          ? html`<p>
              ${workflow.effective_step_up_required === true
                ? 'Additional verification is required for this decision.'
                : workflow.effective_step_up_required === false
                  ? 'No additional verification is required by this recorded decision.'
                  : 'The additional verification requirement was not recorded.'}
            </p>`
          : ''}
        <p>
          Configured policy is evaluated at request time. An optional intent
          assessment is separate from that policy.
        </p>
        <sl-details summary="Policy rule and decision context">
          <div class="info-grid">
            <div class="info-label">Rule:</div>
            <div class="info-value">
              ${rule?.id ?? 'No successful match recorded'}
            </div>
            ${fallback
              ? html`<div class="info-label">
                    Rule evaluated before failure:
                  </div>
                  <div class="info-value">
                    ${policy?.evaluated_rule?.id ?? 'Not recorded'}
                  </div>`
              : ''}
            <div class="info-label">Recorded action:</div>
            <div class="info-value">${rule?.action ?? 'Not recorded'}</div>
            <div class="info-label">Condition:</div>
            <div class="info-value">
              <code>${rule ? rule.condition || 'Always' : 'Not recorded'}</code>
            </div>
            <div class="info-label">Condition language:</div>
            <div class="info-value">
              ${rule?.condition_type ?? 'Not recorded'}
            </div>
            <div class="info-label">Evaluation position (zero-based):</div>
            <div class="info-value">${rule?.order ?? 'Not recorded'}</div>
            <div class="info-label">Workflow:</div>
            <div class="info-value">
              ${workflow?.id ?? policy?.approval_workflow_id ?? 'Not recorded'}
            </div>
            <div class="info-label">Workflow type:</div>
            <div class="info-value">
              ${workflow?.approval_type ?? 'Not recorded'}
            </div>
            <div class="info-label">Step-up protocol:</div>
            <div class="info-value">
              ${workflow?.step_up_protocol ?? 'Not recorded'}
            </div>
            <div class="info-label">Evaluated:</div>
            <div class="info-value">
              ${policy?.evaluated_at
                ? this.formatDate(policy.evaluated_at)
                : 'Not recorded'}
            </div>
            <div class="info-label">Assessment source:</div>
            <div class="info-value">
              ${evidence?.advisory_assessment?.model_used ?? 'Not recorded'}
            </div>
            <div class="info-label">Policy content digest:</div>
            <div class="info-value">
              <code>${rule?.content_digest ?? 'Not recorded'}</code>
            </div>
          </div>
          <p>
            This digest identifies the recorded policy content; it is not an RDT
            proof or hardware signature. Captured context is minimal and does
            not reproduce the full evaluation.
          </p>
        </sl-details>
      </section>`;
  }

  render() {
    if (this.loading) {
      return html`
        <div class="loading-state">
          <sl-spinner style="font-size: 3rem;"></sl-spinner>
        </div>
      `;
    }

    if (this.error) {
      return html`
        <sl-alert variant="danger" open>
          <sl-icon slot="icon" name="exclamation-octagon"></sl-icon>
          <strong>Error:</strong> ${this.error}
        </sl-alert>
      `;
    }

    if (!this.approvalRequest) {
      return html`
        <sl-alert variant="warning" open>
          <sl-icon slot="icon" name="exclamation-triangle"></sl-icon>
          <strong>Not Found:</strong> Approval request not found
        </sl-alert>
      `;
    }

    const isPending = this.approvalRequest.status === 'pending';

    return html`
      <div class="header">
        <h1>
          <sl-icon name="shield-check"></sl-icon>
          ${this.decisionLabel()}
        </h1>
      </div>

      ${this.actionResult
        ? html`
            <sl-alert
              variant=${this.actionResult.type === 'success'
                ? 'success'
                : 'danger'}
              open
              closable
              @sl-hide=${() => (this.actionResult = null)}
            >
              <sl-icon
                slot="icon"
                name=${this.actionResult.type === 'success'
                  ? 'check-circle'
                  : 'exclamation-octagon'}
              ></sl-icon>
              ${this.actionResult.message}
            </sl-alert>
          `
        : ''}

      <sl-card>
        ${this.renderDecisionSummary()}
        ${(this.approvalRequest.intent_flags ?? []).length
          ? html`<div class="content-section" aria-label="Review warnings">
              <div class="flag-list">
                ${(this.approvalRequest.intent_flags ?? []).map(
                  (flag) => html`<sl-tag variant="warning">${flag}</sl-tag>`
                )}
              </div>
            </div> `
          : ''}
        ${isPending
          ? html`
              ${this.approvalRequest.step_up_required &&
              !this.approvalRequest.step_up_verified &&
              (this.stepUpPending || this.stepUpError)
                ? html`
                    <sl-alert
                      variant=${this.stepUpPending ? 'primary' : 'warning'}
                      open
                      style="margin-top: 1rem;"
                    >
                      <sl-icon
                        slot="icon"
                        name=${this.stepUpPending
                          ? 'shield-check'
                          : 'shield-lock'}
                      ></sl-icon>
                      ${this.stepUpPending
                        ? html`<strong>Authenticate with your passkey</strong>
                            to sign this approval. This signature will be
                            permanently recorded in the audit log.`
                        : html`<strong>Passkey required</strong> — Authenticate
                            when prompted to authorize this approval.`}
                      ${this.stepUpError
                        ? html`<br /><span
                              style="color: var(--sl-color-danger-600);"
                              >${this.stepUpError}</span
                            >`
                        : ''}
                    </sl-alert>
                  `
                : ''}

              <div class="actions">
                <sl-button
                  variant="success"
                  size="large"
                  @click=${this.handleApprove}
                  ?loading=${this.submitting}
                  ?disabled=${this.submitting ||
                  (this.approvalRequest.expires_at &&
                    parseUTCDate(this.approvalRequest.expires_at).getTime() <=
                      Date.now()) ||
                  (this.approvalRequest.step_up_required &&
                    !this.approvalRequest.step_up_verified &&
                    !this.approvalRequest.approval_token)}
                >
                  <sl-icon slot="prefix" name="check-circle"></sl-icon>
                  ${this.approvalRequest.step_up_required &&
                  !this.approvalRequest.step_up_verified
                    ? 'Approve once with passkey'
                    : 'Approve once'}
                </sl-button>
                <sl-button
                  variant="danger"
                  size="large"
                  @click=${this.handleDecline}
                  ?loading=${this.submitting}
                  ?disabled=${this.submitting}
                >
                  <sl-icon slot="prefix" name="x-circle"></sl-icon>
                  Deny
                </sl-button>
              </div>
              <sl-details
                summary="Add a comment (optional)"
                class="comment-section"
              >
                <sl-textarea
                  label="Comment (optional)"
                  placeholder="Add a comment explaining your decision..."
                  rows="2"
                  .value=${this.comment}
                  @sl-input=${(e: any) => (this.comment = e.target.value)}
                  ?disabled=${this.submitting}
                ></sl-textarea>
              </sl-details>
            `
          : ''}
        ${this.renderDecisionHistory()}
        <div
          class="approval-details"
          aria-label="Request and verification details"
        >
          ${this.renderActionDetails(false)} ${this.renderReasonDetails()}
          <sl-details summary="Role Delegation Token">
            <p
              title="The WebAuthn signature binds the challenge to the intent_envelope hash. The entire RDT record, including server identity and policy context, is not signed."
            >
              Includes signed action data and additional context.
            </p>
            <pre class="code-block">
${JSON.stringify(
                this.approvalRequest.rdt_envelope ?? { status: 'Not recorded' },
                null,
                2
              )}</pre
            >
            <sl-details summary="Identity, authority and policy context">
              ${this.renderRecordedEvidence()}
            </sl-details>
          </sl-details>
        </div>
      </sl-card>

      ${approvalWasLate(
        this.approvalRequest.expires_at,
        this.approvalRequest.resolved_at,
        this.approvalRequest.status
      )
        ? html`<sl-alert variant="danger" open
            >Decision recorded after the approval deadline. This historical
            decision must not be treated as valid authorization. A verified
            signature does not establish execution.</sl-alert
          >`
        : ''}
      <sl-details summary="Receipt verification details"
        >${this.renderReceiptSummary()}${this.renderAuditReport()}</sl-details
      >
    `;
  }
}
