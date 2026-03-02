#!/usr/bin/env bash
# build.sh — Package cyberbrain skills into .skill archives and produce a release tarball.
#
# Usage:
#   bash build.sh               # build all skills + release tarball
#   bash build.sh --skills-only # build .skill files only, skip tarball
#   bash build.sh --clean       # wipe dist/ before building

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$REPO_DIR/skills"
DIST_DIR="$REPO_DIR/dist"
VERSION_FILE="$REPO_DIR/VERSION"

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
CLEAN=0
SKILLS_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --clean)       CLEAN=1 ;;
    --skills-only) SKILLS_ONLY=1 ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: bash build.sh [--clean] [--skills-only]"
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

# ---------------------------------------------------------------------------
# Package each skill into a .skill archive
# ---------------------------------------------------------------------------
echo "Packaging skills..."
echo ""

BUILT_SKILLS=()

for skill_dir in "$SKILLS_DIR"/*/; do
  # Skip .DS_Store and non-directories
  [ -d "$skill_dir" ] || continue

  skill_name="$(basename "$skill_dir")"

  # Require a SKILL.md to be considered a valid skill
  if [ ! -f "$skill_dir/SKILL.md" ]; then
    echo "  [skip]  $skill_name (no SKILL.md found)"
    continue
  fi

  output="$DIST_DIR/$skill_name.skill"

  # zip -r from the skills/ parent so the archive root is <skill_name>/
  (cd "$SKILLS_DIR" && zip -r -q "$output" "$skill_name/" --exclude "*/.DS_Store" --exclude "*/__pycache__/*" --exclude "*/*.pyc")

  size="$(du -sh "$output" | cut -f1)"
  echo "  [built] $skill_name.skill ($size)"
  BUILT_SKILLS+=("$skill_name")
done

echo ""
echo "${#BUILT_SKILLS[@]} skill(s) packaged: ${BUILT_SKILLS[*]}"

# ---------------------------------------------------------------------------
# Release tarball (unless --skills-only)
# ---------------------------------------------------------------------------
if [ "$SKILLS_ONLY" -eq 1 ]; then
  echo ""
  echo "============================================"
  echo "Build complete (skills only). Output: dist/"
  echo ""
  exit 0
fi

echo ""
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
echo "To install:"
echo "  bash install.sh"
echo ""
echo "To distribute:"
echo "  Share dist/cyberbrain-${VERSION}.tar.gz"
echo "  Recipient runs: tar xzf cyberbrain-${VERSION}.tar.gz && bash install.sh"
echo ""
