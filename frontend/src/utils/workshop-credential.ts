/** Compact WebAuthn identifier; full value remains available in the UI. */
export function shortCredentialId(value?: string): string {
  if (!value) return 'Unavailable';
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-8)}` : value;
}

export function workshopAlgorithm(algorithm?: number): string {
  if (algorithm === -7) return 'Classical ES256';
  if (algorithm === -48) return 'Post-quantum ML-DSA-44';
  return `Algorithm ${algorithm ?? 'unavailable'}`;
}
