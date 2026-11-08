#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: publish-refresh.sh data/watchlist.json|data/statuses.json" >&2
  exit 2
fi
case "$1" in
  data/watchlist.json) message="Refresh Trakt viewing progress" ;;
  data/statuses.json) message="Refresh sourced production information" ;;
  *) echo "Only public refresh data may be published." >&2; exit 2 ;;
esac
file="$1"

if git diff --quiet -- "$file"; then
  echo "changed=false" >> "$GITHUB_OUTPUT"
  echo "No saved-data changes; skipping website rebuild and publication."
  exit 0
fi

# Check dates are public data too: they keep the dashboard's freshness labels accurate.
python3 -m unittest discover -s tests -v
scripts/rebuild-site

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -- "$file"
git commit -m "$message"
git pull --rebase origin main
git push origin HEAD:main
echo "changed=true" >> "$GITHUB_OUTPUT"

# GITHUB_TOKEN pushes do not trigger the Pages push workflow.
gh workflow run pages.yml --ref main
