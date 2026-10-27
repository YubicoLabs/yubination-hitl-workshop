import { readFile, realpath, stat } from 'node:fs/promises';
import { isAbsolute, relative, resolve, sep } from 'node:path';

const artifactPath = '/previewsign/macos-arm64/previewsign-macos-arm64.tar.gz';

export function createPreviewSignArtifactMiddleware(publicDir) {
  return async (request, response, next) => {
    if (
      !publicDir ||
      !['GET', 'HEAD'].includes(request.method ?? '') ||
      request.url?.split('?')[0] !== artifactPath
    ) {
      next();
      return;
    }
    try {
      const root = await realpath(publicDir);
      const source = await realpath(resolve(root, artifactPath.slice(1)));
      const within = relative(root, source);
      if (isAbsolute(within) || within.split(sep).includes('..')) {
        next();
        return;
      }
      const metadata = await stat(source);
      if (!metadata.isFile()) {
        next();
        return;
      }
      const bytes = request.method === 'GET' ? await readFile(source) : undefined;
      response.statusCode = 200;
      response.setHeader('Content-Type', 'application/gzip');
      response.setHeader('Content-Length', bytes?.length ?? metadata.size);
      response.removeHeader('Content-Encoding');
      response.end(bytes);
    } catch (error) {
      if (['ENOENT', 'ENOTDIR'].includes(error.code ?? '')) {
        next();
      } else {
        next(error);
      }
    }
  };
}

export function previewsignArtifactPlugin() {
  return {
    name: 'previewsign-artifact-bytes',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use(createPreviewSignArtifactMiddleware(server.config.publicDir));
    },
  };
}
