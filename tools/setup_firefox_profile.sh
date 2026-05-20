#!/usr/bin/env bash
# One-time: launch Firefox via Playwright using this project's dedicated profile
# so you can log into Airbnb. The login persists in ./browser-profile/ and is
# reused by every Claude-driven session afterward.
#
# Run once. After logging in and dismissing popups, close the browser. Done.
#
# Requires: npx (Node.js), Playwright will auto-download Firefox the first time.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROFILE_DIR="$PROJECT_DIR/browser-profile"

mkdir -p "$PROFILE_DIR"

echo "Launching Firefox with profile: $PROFILE_DIR"
echo "→ Go to airbnb.com, log in, dismiss popups, then close the window."
echo

# Drives Playwright's bundled Firefox against the persistent profile dir.
# --headed forces a visible window; --no-quit keeps the runner alive until
# you close the window manually.
npx --yes playwright open --browser=firefox \
  --user-data-dir="$PROFILE_DIR" \
  https://www.airbnb.com/
