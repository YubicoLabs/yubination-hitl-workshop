/** Presentation of recorded receipt evidence; no cryptographic verification or I/O. */
interface ReceiptInput {
  alg?: unknown;
  authenticator_data_hex?: unknown;
}

function receiptAlgorithm(receipt: ReceiptInput | null) {
  const alg = receipt?.alg;
  switch (alg) {
    case -7:
      return {
        alg,
        kind: 'es256' as const,
        name: 'ECDSA-P256 / ES256',
        label: 'COSE -7 (ECDSA-P256 / ES256)',
      };
    case -48:
    case -49:
    case -50: {
      const parameterSet = { [-48]: '44', [-49]: '65', [-50]: '87' }[alg];
      return {
        alg,
        kind: 'mldsa' as const,
        name: `ML-DSA-${parameterSet}`,
        label: `COSE ${alg} (ML-DSA-${parameterSet})`,
      };
    }
    case -65539:
      return {
        alg,
        kind: 'arkg' as const,
        name: 'ARKG prehash ECDSA-P256',
        label: 'COSE -65539 (ARKG previewSign / prehash ECDSA-P256)',
      };
    default:
      return {
        alg,
        kind: 'unknown' as const,
        name: 'Unknown receipt algorithm',
        label: `Unknown receipt algorithm (COSE ${alg ?? 'unknown'})`,
      };
  }
}

/** Missing/malformed authenticator data stays unknown, never a negative flag. */
export function describeReceipt(receipt: ReceiptInput | null) {
  const auth = receipt?.authenticator_data_hex;
  const valid =
    typeof auth === 'string' &&
    /^[0-9a-f]+$/i.test(auth) &&
    auth.length >= 74 &&
    auth.length % 2 === 0;
  const flags = valid ? parseInt(auth.slice(64, 66), 16) : null;
  const flag = (mask: number): boolean | null =>
    flags === null ? null : Boolean(flags & mask);
  return {
    algorithm: receiptAlgorithm(receipt),
    flags: {
      userPresent: flag(0x01),
      userVerified: flag(0x04),
      backupEligible: flag(0x08),
    },
    provenance: 'recorded-authenticator-data' as const,
  };
}
