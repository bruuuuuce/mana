#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
if [ ! -d "$root/.git" ]; then
  echo "No .git directory found in $root; skipping hook installation."
  exit 0
fi
mkdir -p "$root/.git/hooks"
cp "$root/hooks/pre-commit" "$root/.git/hooks/pre-commit"
cp "$root/hooks/pre-push" "$root/.git/hooks/pre-push"
chmod +x "$root/.git/hooks/pre-commit" "$root/.git/hooks/pre-push"
echo "Git hooks installed"
