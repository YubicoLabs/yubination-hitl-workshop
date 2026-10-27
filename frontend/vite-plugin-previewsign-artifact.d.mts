import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

export function createPreviewSignArtifactMiddleware(publicDir: string | false): (
  request: IncomingMessage,
  response: ServerResponse,
  next: (error?: Error) => void
) => Promise<void>;
export function previewsignArtifactPlugin(): Plugin;
