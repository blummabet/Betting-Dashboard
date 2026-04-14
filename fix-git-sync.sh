#!/bin/bash
# Fix git sync — run this from the Betting Dashboard folder
cd "$(dirname "$0")"
echo "🔧 Removing git lock file..."
rm -f .git/index.lock .git/objects/maintenance.lock
echo "📥 Pulling 2 latest commits from GitHub..."
git pull --rebase
echo "✅ Done. Features check:"
grep -c "copyCardImage\|_futureMax\|_igT" season-finish.html
echo "matches found (expect 16+)"
