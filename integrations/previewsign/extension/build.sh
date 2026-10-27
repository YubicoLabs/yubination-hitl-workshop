#!/bin/bash
# Build browser-specific extension packages from the shared source.
# Reads extension/manifest.json as the source of truth and produces:
#   dist/chrome/  — service_worker background, Chrome key
#   dist/firefox/ — scripts background, gecko settings, no key
set -euo pipefail
cd "$(dirname "$0")"

DIST="../dist"

for browser in chrome firefox; do
  out="$DIST/$browser"
  rm -rf "$out"
  mkdir -p "$out"

  # Copy all non-manifest extension files
  cp *.js *.html "$out/"

  # Build browser-specific manifest
  if [ "$browser" = "chrome" ]; then
    python3 -c "
import json, sys
m = json.load(open('manifest.json'))
m['background'] = {'service_worker': 'background.js'}
m.pop('browser_specific_settings', None)
json.dump(m, sys.stdout, indent=2)
print()
" > "$out/manifest.json"
  else
    python3 -c "
import json, sys
m = json.load(open('manifest.json'))
m['background'] = {'scripts': ['background.js']}
m.pop('key', None)
json.dump(m, sys.stdout, indent=2)
print()
" > "$out/manifest.json"
  fi

  echo "Built $browser extension → $out/"
done
