#!/usr/bin/env bash
set -euo pipefail

# Local macOS ARM64 build + upload to GitHub release.
# Usage:
#   ./scripts/build-macos-local.sh              # build + upload
#   ./scripts/build-macos-local.sh --build-only # build without uploading
#
# Prerequisites:
#   - uv installed
#   - gh authenticated (gh auth status)
#   - Tag already pushed (e.g. v1.2.0)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

VERSION_RAW="${1:-}"
BUILD_ONLY=false

if [ "$VERSION_RAW" = "--build-only" ]; then
  BUILD_ONLY=true
  VERSION_RAW=""
fi

# Resolve version from git tag
if [ -z "$VERSION_RAW" ]; then
  VERSION_RAW="$(git describe --tags --abbrev=0 2>/dev/null || echo "")"
fi
if [ -z "$VERSION_RAW" ]; then
  echo "ERROR: Could not resolve version. Pass version as argument or ensure a git tag exists."
  exit 1
fi

VERSION="${VERSION_RAW#v}"
TAG="v$VERSION"
PLATFORM="macos-arm64"
OUTPUT_DIR="dist/macos-release"
STAGING_DIR="dist/npm-stage"

echo "==> Building omnibot $TAG for $PLATFORM"

# 1. Sync dependencies
echo "==> Syncing dependencies..."
uv sync --all-extras

# 2. Verify import
echo "==> Verifying import..."
uv run python -c "from omnibot import main; print('import OK')"

# 3. Build with Nuitka
echo "==> Building standalone executable with Nuitka (this may take a few minutes)..."
rm -rf "$OUTPUT_DIR"
uv run python -m nuitka build-config/_entry.py \
  --mode=standalone \
  --assume-yes-for-downloads \
  --jobs=0 \
  --include-package=omnibot \
  --include-data-dir=src/omnibot/sop=omnibot/sop \
  --include-data-dir=src/omnibot/skills=omnibot/skills \
  --output-dir="$OUTPUT_DIR" \
  --output-filename=omnibot-bin

# 4. Normalize standalone directory
echo "==> Normalizing standalone directory..."
python3 scripts/normalize_nuitka_standalone.py \
  --src="$OUTPUT_DIR/_entry.dist" \
  --output-dir="$STAGING_DIR" \
  --platform="$PLATFORM" \
  --version="$TAG" \
  --binary-name="omnibot-$PLATFORM"

# 5. Sync VERSION and skills files
echo "==> Syncing VERSION and skills..."
BINARY_DIR="$STAGING_DIR/omnibot-$PLATFORM"
echo "$VERSION" > "$BINARY_DIR/VERSION"
cp src/omnibot/skills/omnibot/SKILL.md "$BINARY_DIR/omnibot/skills/omnibot/SKILL.md"
cp src/omnibot/skills/omnibot/references/command-reference.md "$BINARY_DIR/omnibot/skills/omnibot/references/command-reference.md"

# 6. Verify binary
echo "==> Verifying binary..."
chmod +x "$BINARY_DIR/omnibot-$PLATFORM"
"$BINARY_DIR/omnibot-$PLATFORM" --help
"$BINARY_DIR/omnibot-$PLATFORM" skills path

# 7. Create zip
echo "==> Creating zip..."
ZIP="/tmp/omnibot-$PLATFORM.zip"
rm -f "$ZIP"
(cd "$STAGING_DIR" && zip -r "$ZIP" "omnibot-$PLATFORM" -x "*.DS_Store")
ls -lh "$ZIP"

if [ "$BUILD_ONLY" = true ]; then
  echo "==> Build-only mode. Zip at: $ZIP"
  echo "    To upload: gh release upload $TAG $ZIP --clobber"
  exit 0
fi

# 8. Upload to GitHub release
echo "==> Uploading to GitHub release $TAG..."
gh release upload "$TAG" "$ZIP" --clobber

echo "==> Done. macOS ARM64 artifact uploaded to release $TAG"
