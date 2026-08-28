#!/usr/bin/env bash
set -euo pipefail

# Omnibot full release script.
#
# Usage:
#   ./scripts/release.sh <version>
#   ./scripts/release.sh 1.6.8
#
# What it does:
#   1. Verifies version consistency across all package locations.
#   2. Builds all platforms (Docker for Linux, native for macOS, optional Windows).
#   3. Creates a GitHub Release with platform zips.
#   4. Publishes to npm (@omniaibot/* packages).
#
# Prerequisites:
#   - Docker Desktop (or OrbStack) running
#   - uv installed
#   - gh authenticated (gh auth status)
#   - npm authenticated (npm whoami), or set NPM_TOKEN
#   - Git tag already created (v1.6.8)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${1:?Usage: release.sh <version>  e.g. release.sh 1.6.8}"
TAG="v$VERSION"

# ── Verify tag exists ──────────────────────────────────────────────────────
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "ERROR: Git tag $TAG does not exist. Create it first: git tag $TAG"
  exit 1
fi
echo "Tag $TAG found."

# ── Verify version consistency ─────────────────────────────────────────────
echo ""
echo "==> Verifying version consistency..."
echo "    pyproject.toml:         $(grep 'version = ' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')"
echo "    browser-extension:      $(grep '"version"' browser-extension/manifest.json | head -1 | sed 's/.*"\(.*\)".*/\1/')"
echo "    npm cli:                $(grep '"version"' npm-packages/cli/package.json | head -1 | sed 's/.*"\(.*\)".*/\1/')"
echo "    npm win-x64:            $(grep '"version"' npm-packages/win-x64/package.json | head -1 | sed 's/.*"\(.*\)".*/\1/')"
echo "    npm linux-x64:          $(grep '"version"' npm-packages/linux-x64/package.json | head -1 | sed 's/.*"\(.*\)".*/\1/')"
echo "    npm macos-arm64:        $(grep '"version"' npm-packages/macos-arm64/package.json | head -1 | sed 's/.*"\(.*\)".*/\1/')"
echo "    cli optDeps linux:      $(grep 'linux-x64' npm-packages/cli/package.json | sed 's/.*"\(.*\)".*/\1/')"
echo "    cli optDeps macos:      $(grep 'macos-arm64' npm-packages/cli/package.json | sed 's/.*"\(.*\)".*/\1/')"
echo "    cli optDeps win:        $(grep 'win-x64' npm-packages/cli/package.json | sed 's/.*"\(.*\)".*/\1/')"

# ── Build all platforms ────────────────────────────────────────────────────
echo ""
echo "==> Building all platforms..."
bash scripts/build-all.sh "$TAG"

RELEASE_DIR="dist/release"

# ── Package platform zips ──────────────────────────────────────────────────
echo ""
echo "==> Packaging platform zips..."

ZIPS=()
for PLATFORM_DIR in "$RELEASE_DIR"/omnibot-{linux-x64,windows-x64,macos-arm64,extension}; do
  if [ ! -d "$PLATFORM_DIR" ]; then
    echo "    Skipping $(basename "$PLATFORM_DIR") (not found)"
    continue
  fi
  BASE="$(basename "$PLATFORM_DIR")"
  ZIP_PATH="/tmp/omnibot-${BASE#omnibot-}.zip"
  rm -f "$ZIP_PATH"
  (cd "$(dirname "$PLATFORM_DIR")" && zip -r "$ZIP_PATH" "$BASE" -x "*.DS_Store")
  ls -lh "$ZIP_PATH"
  ZIPS+=("$ZIP_PATH")
done

if [ ${#ZIPS[@]} -eq 0 ]; then
  echo "ERROR: No platform directories found in $RELEASE_DIR"
  exit 1
fi

# ── Create GitHub Release ──────────────────────────────────────────────────
echo ""
echo "==> Creating GitHub Release $TAG..."

# Check if release already exists.
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "    Release $TAG already exists. Uploading artifacts..."
  for Z in "${ZIPS[@]}"; do
    gh release upload "$TAG" "$Z" --clobber
  done
else
  echo "    Creating new release..."
  gh release create "$TAG" "${ZIPS[@]}" \
    --title "$TAG" \
    --generate-notes \
    --draft=false
fi

# ── Prepare npm packages ───────────────────────────────────────────────────
echo ""
echo "==> Preparing npm packages..."

# macOS ARM64
if [ -d "$RELEASE_DIR/omnibot-macos-arm64" ]; then
  MACOS_NPM_BIN="npm-packages/macos-arm64/bin/omnibot-macos-arm64"
  rm -rf "$MACOS_NPM_BIN"
  mkdir -p "$(dirname "$MACOS_NPM_BIN")"
  cp -R "$RELEASE_DIR/omnibot-macos-arm64" "$MACOS_NPM_BIN"
  echo "    macOS ARM64 prepared."
else
  echo "    WARNING: macOS ARM64 build not found, skipping npm prep."
  rm -rf npm-packages/macos-arm64/bin
fi

# Linux x64
if [ -d "$RELEASE_DIR/omnibot-linux-x64" ]; then
  LINUX_NPM_BIN="npm-packages/linux-x64/bin/omnibot-linux-x64"
  rm -rf "$LINUX_NPM_BIN"
  mkdir -p "$(dirname "$LINUX_NPM_BIN")"
  cp -R "$RELEASE_DIR/omnibot-linux-x64" "$LINUX_NPM_BIN"
  chmod +x "$LINUX_NPM_BIN/omnibot-linux-x64"
  echo "    Linux x64 prepared."
else
  echo "    WARNING: Linux x64 build not found, skipping npm prep."
  rm -rf npm-packages/linux-x64/bin
fi

# Windows x64
# build-windows-remote.sh outputs directly to npm-packages/win-x64/bin/.
# If that directory already has content, use it; otherwise fall back to dist/release/.
WIN_NPM_BIN="npm-packages/win-x64/bin/omnibot-windows-x64"
if [ -d "$WIN_NPM_BIN" ] && [ -f "$WIN_NPM_BIN/omnibot-windows-x64.exe" ]; then
  echo "    Windows x64: using existing build from build-windows-remote.sh."
  echo "    VERSION: $(cat "$WIN_NPM_BIN/VERSION")"
elif [ -d "$RELEASE_DIR/omnibot-windows-x64" ]; then
  rm -rf "$WIN_NPM_BIN"
  mkdir -p "$(dirname "$WIN_NPM_BIN")"
  cp -R "$RELEASE_DIR/omnibot-windows-x64" "$WIN_NPM_BIN"
  echo "    Windows x64 prepared from dist/release/."
else
  echo "    WARNING: Windows x64 build not found, skipping npm prep."
  rm -rf npm-packages/win-x64/bin
fi

# ── Publish npm packages ───────────────────────────────────────────────────
echo ""
echo "==> Publishing npm packages..."

# Publish platform packages.
for PLATFORM in macos-arm64 linux-x64 win-x64; do
  PKG_DIR="npm-packages/$PLATFORM"
  if [ ! -d "$PKG_DIR/bin" ] || [ -z "$(ls -A "$PKG_DIR/bin" 2>/dev/null)" ]; then
    echo "    Skipping @omniaibot/$PLATFORM (no build artifacts)"
    continue
  fi
  PKG_NAME="@omniaibot/$PLATFORM"

  # Verify skills files are present.
  # Windows uses "omnibot-windows-x64" dir name instead of "omnibot-win-x64".
  if [ "$PLATFORM" = "win-x64" ]; then
    ARTIFACT_DIR="$PKG_DIR/bin/omnibot-windows-x64"
  else
    ARTIFACT_DIR="$PKG_DIR/bin/omnibot-$PLATFORM"
  fi
  if [ ! -f "$ARTIFACT_DIR/omnibot/skills/omnibot/SKILL.md" ]; then
    echo "    ERROR: Skills file missing in $ARTIFACT_DIR"
    exit 1
  fi

  # Check if already published.
  if npm view "$PKG_NAME@$VERSION" version --registry=https://registry.npmjs.org/ >/dev/null 2>&1; then
    echo "    $PKG_NAME@$VERSION already published, skipping."
  else
    echo "    Publishing $PKG_NAME@$VERSION..."
    (cd "$PKG_DIR" && npm publish --access public)
  fi
done

# Publish main CLI package.
CLI_DIR="npm-packages/cli"
if npm view "@omniaibot/omnibot@$VERSION" version --registry=https://registry.npmjs.org/ >/dev/null 2>&1; then
  echo "    @omniaibot/omnibot@$VERSION already published, skipping."
else
  echo "    Publishing @omniaibot/omnibot@$VERSION..."
  (cd "$CLI_DIR" && npm publish --access public)
fi

# ── Publish to Edge Add-ons Store ─────────────────────────────────────────
# Requires EDGE_API_KEY environment variable to be set
if [ -n "${EDGE_API_KEY:-}" ]; then
  echo ""
  echo "==> Publishing extension to Edge Add-ons Store..."
  bash scripts/publish-edge-extension.sh "/tmp/omnibot-extension.zip"
else
  echo ""
  echo "==> Skipping Edge Add-ons Store publish (EDGE_API_KEY not set)"
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo "==> Release $TAG completed!"
echo "    GitHub release: gh release view $TAG"
echo "    npm packages:"
for PKG in omnibot linux-x64 macos-arm64 win-x64; do
  echo "      @omniaibot/$PKG@$VERSION"
done
if [ -n "${EDGE_API_KEY:-}" ]; then
  echo "    Edge Add-ons: published"
fi