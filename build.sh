#!/usr/bin/env bash
# DEPRECATED: Use `python -m build` or `uv build` from pyproject.toml instead.
# This script packages the pre-WI-034 flat layout and is no longer correct.
#
# build.sh — Produce a release tarball for cyberbrain.
#
# Usage:
#   bash build.sh         # build release tarball
#   bash build.sh --clean # wipe dist/ before building

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$REPO_DIR/dist"
VERSION_FILE="$REPO_DIR/VERSION"

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
CLEAN=0

for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: bash build.sh [--clean]"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
if [ -f "$VERSION_FILE" ]; then
  VERSION="$(cat "$VERSION_FILE" | tr -d '[:space:]')"
else
  VERSION="0.0.0"
fi

echo "Cyberbrain Build — v${VERSION}"
echo "============================================"
echo ""

# ---------------------------------------------------------------------------
# Prepare dist/
# ---------------------------------------------------------------------------
if [ "$CLEAN" -eq 1 ] && [ -d "$DIST_DIR" ]; then
  echo "Cleaning dist/..."
  rm -rf "$DIST_DIR"
fi

mkdir -p "$DIST_DIR"

echo "Building release tarball..."

TARBALL="$DIST_DIR/cyberbrain-${VERSION}.tar.gz"

# Assemble the tarball from repo root, including only distribution-relevant files.
# dist/*.skill files are included so the release is self-contained.
tar -czf "$TARBALL" \
  -C "$REPO_DIR" \
  --exclude="./dist/cyberbrain-*.tar.gz" \
  --exclude="./.git" \
  --exclude="./.gitignore" \
  --exclude="./.DS_Store" \
  --exclude="./skills" \
  --exclude="./.claude" \
  --exclude="./steering" \
  --exclude="*/__pycache__" \
  --exclude="*/*.pyc" \
  install.sh \
  uninstall.sh \
  README.md \
  VERSION \
  cyberbrain.example.json \
  cyberbrain.local.example.json \
  hooks \
  extractors \
  prompts \
  dist

tarball_size="$(du -sh "$TARBALL" | cut -f1)"
echo "  [built] cyberbrain-${VERSION}.tar.gz ($tarball_size)"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "Build complete."
echo ""
echo "Artifacts in dist/:"
ls -lh "$DIST_DIR" | tail -n +2 | awk '{print "  " $NF " (" $5 ")"}'
echo ""
echo "To install:    bash install.sh"
echo "To distribute: share dist/cyberbrain-${VERSION}.tar.gz"
echo "               recipient runs: tar xzf cyberbrain-${VERSION}.tar.gz && bash install.sh"
echo ""
