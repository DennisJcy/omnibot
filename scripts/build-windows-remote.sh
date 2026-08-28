#!/usr/bin/env bash
set -euo pipefail

# Build omnibot for Windows x64 on a remote Windows machine via SSH.
#
# Usage:
#   ./scripts/build-windows-remote.sh [VERSION]
#
# VERSION defaults to the latest git tag (e.g. v1.6.8).
#
# Prerequisites:
#   - SSH access to a Windows machine with Python 3.13 + uv installed
#   - The remote machine has Git, tar, and MSVC (cl.exe) available
#
# Environment variables:
#   WIN_HOST     — remote Windows SSH host (required, e.g. user@your-windows-host)
#   WIN_PROJECT  — remote project directory (optional, default: C:\Users\<remote user>\project\omnibot_src)

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

WIN_HOST="${WIN_HOST:?WIN_HOST is required (e.g. user@your-windows-host)}"
# Default project dir under the remote user's profile, derived from WIN_HOST.
WIN_PROJECT="${WIN_PROJECT:-}"
if [ -z "$WIN_PROJECT" ]; then
  REMOTE_USER="${WIN_HOST%%@*}"
  WIN_PROJECT="C:\\Users\\${REMOTE_USER}\\project\\omnibot_src"
fi

echo "==> Building omnibot $TAG for Windows x64 on $WIN_HOST"

# 1. Create source tarball (excluding build artifacts)
echo "==> Packaging source..."
TARBALL="/tmp/omnibot-src.tar.gz"
tar czf "$TARBALL" \
  --exclude='.git' \
  --exclude='dist' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='.uv' \
  --exclude='npm-packages/*/bin' \
  --exclude='.zcode' \
  --exclude='tests/reports' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  src/ pyproject.toml build-config/ scripts/ browser-extension/ build_ext.py

# 2. Transfer source to remote Windows
echo "==> Transferring source to $WIN_HOST..."
ssh "$WIN_HOST" "rmdir /s /q \"$WIN_PROJECT\" 2>nul & mkdir \"$WIN_PROJECT\" & echo ok" 2>&1
scp "$TARBALL" "$WIN_HOST:/tmp/omnibot-src.tar.gz"

# 3. Extract and clean AppleDouble files on remote
echo "==> Extracting source on remote..."
ssh "$WIN_HOST" "cd /d \"$WIN_PROJECT\" & tar xzf /tmp/omnibot-src.tar.gz & del /s /q ._*.py 2>nul & del /s /q ._*.toml 2>nul & del /s /q ._*.md 2>nul & del /s /q ._*.js 2>nul & del /s /q ._*.json 2>nul & del /s /q ._*.sh 2>nul & del /s /q ._browser-extension 2>nul & del /s /q ._build-config 2>nul & del /s /q ._build_ext.py 2>nul & del /s /q ._pyproject.toml 2>nul & del /s /q ._scripts 2>nul & del /s /q ._src 2>nul & echo cleaned" 2>&1

# 4. Create venv and install deps (skip if already exists)
echo "==> Setting up Python 3.13 venv on remote..."
ssh "$WIN_HOST" "cd /d \"$WIN_PROJECT\" & if not exist .venv313 (uv python install 3.13 & uv venv .venv313 --python 3.13) & powershell -NoProfile -Command \"Remove-Item .venv313\\Lib\\site-packages\\omnibot-*.dist-info,.venv313\\Lib\\site-packages\\__editable__.omnibot-*.pth -Recurse -Force -ErrorAction SilentlyContinue\" & uv pip install -e \".[dev]\" --python .venv313\\Scripts\\python.exe & .venv313\\Scripts\\python.exe scripts\\patch_nuitka_windows.py & echo deps-installed" 2>&1

# 5. Run Nuitka build
echo "==> Running Nuitka standalone build (this may take several minutes)..."
ssh "$WIN_HOST" "cd /d \"$WIN_PROJECT\" & .venv313\\Scripts\\python.exe -m nuitka build-config\\_entry.py --mode=standalone --assume-yes-for-downloads --jobs=0 --include-package=omnibot --include-data-dir=src\\omnibot\\sop=omnibot\\sop --include-data-dir=src\\omnibot\\skills=omnibot\\skills --output-dir=dist --output-filename=omnibot-bin" 2>&1 | tail -10

# 6. Normalize output
echo "==> Normalizing output..."
ssh "$WIN_HOST" "cd /d \"$WIN_PROJECT\" & .venv313\\Scripts\\python.exe scripts\\normalize_nuitka_standalone.py --src=dist\\_entry.dist --output-dir=dist\\npm-stage --platform=windows-x64 --version=$TAG" 2>&1

# 7. Sync VERSION and skills files
echo "==> Syncing VERSION and skills..."
ssh "$WIN_HOST" "cd /d \"$WIN_PROJECT\" & echo $VERSION> dist\\npm-stage\\omnibot-windows-x64\\VERSION & copy src\\omnibot\\skills\\omnibot\\SKILL.md dist\\npm-stage\\omnibot-windows-x64\\omnibot\\skills\\omnibot\\SKILL.md & copy src\\omnibot\\skills\\omnibot\\references\\command-reference.md dist\\npm-stage\\omnibot-windows-x64\\omnibot\\skills\\omnibot\\references\\command-reference.md & echo synced" 2>&1

# 8. Verify binary
echo "==> Verifying binary..."
ssh "$WIN_HOST" "cd /d \"$WIN_PROJECT\" & dist\\npm-stage\\omnibot-windows-x64\\omnibot-windows-x64.exe --help" 2>&1 | head -3

# 9. Package and transfer back
echo "==> Packaging and transferring back..."
ssh "$WIN_HOST" "cd /d \"$WIN_PROJECT\"\\dist\\npm-stage & tar -czf omni-win.tar.gz omnibot-windows-x64 & echo packaged" 2>&1
# OpenSSH scp expects a slash-prefixed Windows drive path, while the build
# commands above intentionally use cmd.exe's C:\\ form.
WIN_PROJECT_SCP="${WIN_PROJECT//\\//}"
scp "$WIN_HOST:$WIN_PROJECT_SCP/dist/npm-stage/omni-win.tar.gz" /tmp/omni-win.tar.gz

# 10. Extract into npm-packages
echo "==> Extracting into npm-packages..."
rm -rf npm-packages/win-x64/bin/omnibot-windows-x64
mkdir -p npm-packages/win-x64/bin
tar xf /tmp/omni-win.tar.gz -C npm-packages/win-x64/bin/
rm -f /tmp/omni-win.tar.gz

echo "==> Windows x64 build complete!"
echo "    Binary: npm-packages/win-x64/bin/omnibot-windows-x64/omnibot-windows-x64.exe"
echo "    VERSION: $(cat npm-packages/win-x64/bin/omnibot-windows-x64/VERSION)"
echo ""
echo "    Next: publish with:"
echo "      npm publish npm-packages/win-x64/ --access public"
echo "      (cd npm-packages/win-x64/bin && zip -r /tmp/omnibot-windows-x64.zip omnibot-windows-x64)"
echo "      gh release upload $TAG /tmp/omnibot-windows-x64.zip --clobber"
