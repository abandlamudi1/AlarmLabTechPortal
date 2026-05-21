#!/bin/bash
# Auto-sync GitHub Project board daily
# Run this via cron or manually to keep GITHUB_PROJECT_TASKS.md current

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "🔄 Auto-syncing GitHub Project board..."

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the sync tool
python "scripts/daily-routine/sync_project_status.py" --update-local

# Check if there are changes
if git diff --quiet GITHUB_PROJECT_TASKS.md; then
    echo "✅ No changes to project tasks"
    exit 0
fi

# Commit and push if there are changes
echo "📝 Changes detected in project tasks"
git add GITHUB_PROJECT_TASKS.md

git commit -m "docs: auto-sync GitHub Project tasks $(date +%Y-%m-%d)"

echo "📤 Pushing to remote..."
git push origin main

echo "✅ Project tasks synced successfully!"
