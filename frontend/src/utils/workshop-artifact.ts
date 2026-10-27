export type WorkshopPlatform = 'macos-arm64' | 'windows-x64';

export interface WorkshopArtifact {
  sha256: string;
  distribution: 'local-evaluation' | 'participant-release';
  sourceRevision?: string;
  byteSize?: number;
  qualified?: boolean;
  qualificationEvidence?: unknown;
}

function validOrigin(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  try {
    const origin = new URL(value);
    return (
      ['http:', 'https:'].includes(origin.protocol) && origin.origin === value
    );
  } catch {
    return false;
  }
}

export function parseWorkshopArtifact(
  value: unknown,
  platform: WorkshopPlatform,
  page: URL
): WorkshopArtifact | null {
  if (!value || typeof value !== 'object') return null;
  const manifest = value as Record<string, unknown>;
  const filename =
    platform === 'macos-arm64'
      ? 'previewsign-macos-arm64.tar.gz'
      : 'previewsign-windows-x64.zip';
  const local =
    ['localhost', '127.0.0.1', '[::1]'].includes(page.hostname) &&
    manifest.distribution === 'local-evaluation' &&
    typeof manifest.qualified === 'boolean';
  const hosted =
    page.protocol === 'https:' &&
    ['local-evaluation', 'participant-release'].includes(
      String(manifest.distribution)
    ) &&
    typeof manifest.sourceRevision === 'string' &&
    /^[a-f0-9]{40}$/.test(manifest.sourceRevision) &&
    Number.isSafeInteger(manifest.byteSize) &&
    Number(manifest.byteSize) > 0 &&
    manifest.format === (platform === 'macos-arm64' ? 'tar.gz' : 'zip');
  if (
    !(local || hosted) ||
    manifest.schemaVersion !== 1 ||
    manifest.platform !== platform ||
    manifest.artifact !== filename ||
    typeof manifest.sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(manifest.sha256) ||
    !Array.isArray(manifest.workshopOrigins) ||
    !manifest.workshopOrigins.includes(page.origin) ||
    manifest.workshopOrigins.some((origin: unknown) => !validOrigin(origin))
  )
    return null;
  return {
    sha256: manifest.sha256,
    distribution: manifest.distribution as WorkshopArtifact['distribution'],
    sourceRevision:
      typeof manifest.sourceRevision === 'string' &&
      /^[a-f0-9]{40}$/.test(manifest.sourceRevision)
        ? manifest.sourceRevision
        : undefined,
    byteSize: hosted ? Number(manifest.byteSize) : undefined,
    qualified:
      typeof manifest.qualified === 'boolean' ? manifest.qualified : undefined,
    qualificationEvidence: manifest.qualificationEvidence,
  };
}
