#!/usr/bin/env bash
set -euo pipefail

# Build omnibot for all platforms locally.
#
# Usage:
#   ./scripts/build-all.sh [VERSION]
#
# VERSION defaults to the latest git tag (e.g. v1.6.8).
#
# Prerequisites:
#   - Docker Desktop (or OrbStack) running
#   - uv installed
#   - gh authenticated (gh auth status)
#
# Outputs:
#   dist/release/omnibot-linux-x64/
#   dist/release/omnibot-windows-x64/
#   dist/release/omnibot-macos-arm64/
#   dist/release/omnibot-extension/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

VERSION_RAW="${1:-}"
if [ -z "$VERSION_RAW" ]; then
  VERSION_RAW="$(git describe --tags --abbrev=0 2>/dev/null || echo "")"
fi
if [ -z "$VERSION_RAW" ]; then
  echo "ERROR: Could not resolve version. Pass version as argument or ensure a git tag exists."
  exit 1
fi
VERSION="${VERSION_RAW#v}"
TAG="v$VERSION"

RELEASE_DIR="dist/release"
echo "==> Building omnibot $TAG for all platforms"
echo "    Release dir: $RELEASE_DIR"

mkdir -p "$RELEASE_DIR"

# ── 1. Linux x64 (Docker) ──────────────────────────────────────────────────
echo ""
echo "==> [1/4] Building Linux x64 via Docker..."
DOCKER_LINUX_IMAGE="omnibot-builder-linux:latest"
docker build --platform linux/amd64 -t "$DOCKER_LINUX_IMAGE" -f Dockerfile .

# Extract the build output from the image.
LINUX_CONTAINER=$(docker create "$DOCKER_LINUX_IMAGE")
# Copy the whole dist directory, then point normalize at the *.dist subdir.
rm -rf "dist/docker-linux-build"
docker cp "$LINUX_CONTAINER:/build/dist" "dist/docker-linux-build"
docker rm "$LINUX_CONTAINER" > /dev/null

# Normalize: rename binary, write VERSION.
python3 scripts/normalize_nuitka_standalone.py \
  --src "dist/docker-linux-build" \
  --output-dir "$RELEASE_DIR" \
  --platform linux-x64 \
  --version "$TAG" \
  --binary-name "omnibot-linux-x64"

# Sync skills files.
LINUX_BIN_DIR="$RELEASE_DIR/omnibot-linux-x64"
cp src/omnibot/skills/omnibot/SKILL.md "$LINUX_BIN_DIR/omnibot/skills/omnibot/SKILL.md"
cp src/omnibot/skills/omnibot/references/command-reference.md "$LINUX_BIN_DIR/omnibot/skills/omnibot/references/command-reference.md"
echo "    Linux x64 build complete."

# ── 2. Windows x64 (Docker cross-compilation) ──────────────────────────────
echo ""
echo "==> [2/4] Building Windows x64 via Docker (MinGW-w64 cross-compilation)..."
DOCKER_WINDOWS_IMAGE="omnibot-builder-windows:latest"
if ! docker build --platform linux/amd64 -t "$DOCKER_WINDOWS_IMAGE" -f Dockerfile.windows .; then
  echo ""
  echo "WARNING: Windows cross-compilation via Docker failed."
  echo "  This is expected if MinGW-w64 cross-compilation is not fully supported."
  echo "  Falling back to remote Windows build (see AGENTS.md for instructions)."
  echo "  Skipping Windows build."
  WINDOWS_SKIPPED=true
else
  WINDOWS_CONTAINER=$(docker create "$DOCKER_WINDOWS_IMAGE")
  # Copy the whole dist directory, then point normalize at the *.dist subdir.
  rm -rf "dist/docker-windows-build"
  docker cp "$WINDOWS_CONTAINER:/build/dist" "dist/docker-windows-build"
  docker rm "$WINDOWS_CONTAINER" > /dev/null

  python3 scripts/normalize_nuitka_standalone.py \
    --src "dist/docker-windows-build" \
    --output-dir "$RELEASE_DIR" \
    --platform windows-x64 \
    --version "$TAG" \
    --binary-name "omnibot-windows-x64"

  WIN_BIN_DIR="$RELEASE_DIR/omnibot-windows-x64"
  cp src/omnibot/skills/omnibot/SKILL.md "$WIN_BIN_DIR/omnibot/skills/omnibot/SKILL.md"
  cp src/omnibot/skills/omnibot/references/command-reference.md "$WIN_BIN_DIR/omnibot/skills/omnibot/references/command-reference.md"
  echo "    Windows x64 build complete."
fi

# ── 3. macOS ARM64 (native) ────────────────────────────────────────────────
echo ""
echo "==> [3/4] Building macOS ARM64 (native)..."
bash scripts/build-macos-local.sh --build-only "$TAG"

# Copy the macOS build output into the release directory.
MACOS_STAGING="dist/npm-stage/omnibot-macos-arm64"
if [ -d "$MACOS_STAGING" ]; then
  rm -rf "$RELEASE_DIR/omnibot-macos-arm64"
  cp -R "$MACOS_STAGING" "$RELEASE_DIR/omnibot-macos-arm64"
  echo "    macOS ARM64 build complete."
else
  echo "ERROR: macOS build output not found at $MACOS_STAGING"
  exit 1
fi

# ── 4. Browser extension ───────────────────────────────────────────────────
echo ""
echo "==> [4/4] Building browser extension..."
rm -rf "$RELEASE_DIR/omnibot-extension"
mkdir -p "$RELEASE_DIR/omnibot-extension"
python3 build_ext.py
cp -R dist/omnibot/* "$RELEASE_DIR/omnibot-extension/"
echo "    Extension build complete."

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo "==> Build complete. Artifacts:"
for dir in "$RELEASE_DIR"/omnibot-*; do
  if [ -d "$dir" ]; then
    echo "    $(basename "$dir")/"
  fi
done
if [ "${WINDOWS_SKIPPED:-false}" = "true" ]; then
  echo ""
  echo "    NOTE: Windows build was skipped (Docker cross-compilation failed)."
  echo "    Build Windows manually on a remote Windows machine (see AGENTS.md)."
fi
echo ""
echo "==> Next step: ./scripts/release.sh $VERSION"