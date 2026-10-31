#!/usr/bin/env bash
# Rebuilds the pinned browser SDK bundle served to the "Talk to this agent" button.
# Upgrade by changing the versions here (and the path in static/web_call.js and templates).
set -euo pipefail
SDK=3.0.3
LIVEKIT=2.22.4
EVENTEMITTER=5.0.1
ESBUILD=0.25.0
OUT="$(cd "$(dirname "$0")/.." && pwd)/static/vendor/retell-client-js-sdk-$SDK.min.js"
TMP="$(mktemp -d)"
cd "$TMP"
npm init -y >/dev/null
npm install --save-exact --ignore-scripts --no-audit --no-fund "retell-client-js-sdk@$SDK" "livekit-client@$LIVEKIT" "eventemitter3@$EVENTEMITTER" "esbuild@$ESBUILD" >/dev/null
npm rebuild esbuild >/dev/null
npx esbuild node_modules/retell-client-js-sdk/dist/index.m.js --bundle --format=esm --minify --target=es2020 --outfile="$OUT"
