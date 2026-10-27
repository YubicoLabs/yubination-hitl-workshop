import { setBasePath } from '@shoelace-style/shoelace/dist/utilities/base-path.js';

// Bundle every default icon locally. Inferring this path from a bundled JS URL
// points Shoelace at nonexistent assets and silently renders empty controls.
setBasePath('/vendor/shoelace');
