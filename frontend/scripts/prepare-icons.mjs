// Ship the installed Shoelace library with the app, including self-hosted builds.
import { writeFileSync, existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
const source = path.join(root, 'node_modules/@shoelace-style/shoelace/dist/assets/icons');
function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? walk(file) : [file];
  });
}
const missing = [];
for (const file of walk(path.join(root, 'src')).filter(file => file.endsWith('.ts') && !file.endsWith('.test.ts'))) {
  const text = readFileSync(file, 'utf8');
  for (const tag of text.matchAll(/<sl-icon(?:-button)?\b[^>]*>/g)) {
    const name = tag[0].match(/\bname="([\w-]+)"/);
    if (name && !tag[0].includes('library=') && !existsSync(path.join(source, `${name[1]}.svg`))) {
      missing.push(`${path.relative(root, file).split(path.sep).join('/')}: ${name[1]}`);
    }
  }
}
if (missing.length) throw new Error(`Unknown Shoelace icons:\n${missing.join('\n')}`);
const destination = path.join(root, 'public/vendor/shoelace/assets/icons');
mkdirSync(destination, { recursive: true });
// Read/write SVG bytes rather than copying filesystem metadata or using
// copyfile/clone operations that can fail across Docker Desktop mounts.
for (const name of readdirSync(source)) {
  if (name.endsWith('.svg')) writeFileSync(path.join(destination, name), readFileSync(path.join(source, name)));
}
console.log(`Prepared ${readdirSync(source).length} local icons; static icon references validated.`);
