#!/usr/bin/env bash
# Build + commit + push so GitHub Actions deploys to Pages.
# Usage:
#   ./scripts/publish.sh              # build, commit if dirty, push
#   ./scripts/publish.sh "msg"        # custom commit message
#   SKIP_PUSH=1 ./scripts/publish.sh  # build (+ optional commit) only
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SITE_URL="${SITE_URL:-https://spacexygrok.github.io}"
export SITE_URL

if [[ -f public/robots.txt ]]; then
  sed -i "s|^Sitemap:.*|Sitemap: ${SITE_URL%/}/sitemap-index.xml|" public/robots.txt
fi

echo "==> SITE_URL=$SITE_URL"
echo "==> npm ci / install"
if [[ -f package-lock.json ]]; then
  npm ci --prefer-offline
else
  npm install
fi

echo "==> astro build"
npm run build

echo "==> build OK: $ROOT/dist"
ls -la dist | head -30

# Verify local SEO markers quickly
if ! grep -q "Sitemap: ${SITE_URL%/}/sitemap-index.xml" public/robots.txt; then
  echo "ERROR: robots.txt Sitemap line does not match SITE_URL" >&2
  exit 1
fi
if ! grep -q "rel=\"sponsored nofollow\"" dist/posts/*/index.html 2>/dev/null; then
  echo "WARN: no rel=\"sponsored nofollow\" found in built posts" >&2
fi

if [[ "${SKIP_PUSH:-}" == "1" ]]; then
  echo "SKIP_PUSH=1 — not committing or pushing."
  exit 0
fi

if [[ ! -d .git ]]; then
  echo "ERROR: not a git repo; init/remote expected before publish." >&2
  exit 1
fi

MSG="${1:-chore: publish site $(date -Iseconds)}"

echo "==> git status"
git status --short

if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -m "$MSG"
else
  echo "Nothing to commit (working tree clean)."
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> git push origin $BRANCH"
git push -u origin "$BRANCH"

echo
echo "Pushed. GitHub Actions will deploy to $SITE_URL"
echo "Watch: gh run watch --repo \$(git remote get-url origin | sed -E 's#.*github.com[:/](.+)(\.git)?#\1#')"
