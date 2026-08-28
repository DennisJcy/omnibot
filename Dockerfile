# Dockerfile for omnibot Linux x64 native build.
#
# Usage:
#   docker build -t omnibot-builder-linux .
#
# Output is placed at /build/dist/_entry.dist/ inside the image.
# Use `docker create` + `docker cp` to extract, or a volume mount.

FROM --platform=linux/amd64 python:3.13-slim

# System dependencies required by Nuitka + standalone linking.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    patchelf \
    ccache \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python build tooling.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir nuitka ordered-set zstandard

# Copy project source for the build context.
COPY . .

# Install the omnibot package + runtime dependencies so Nuitka can find them.
RUN pip install --no-cache-dir -e .

# Build the standalone Linux executable.
# Mirrors the flags used by .github/workflows/build-release.yml (linux matrix entry).
RUN python -m nuitka build-config/_entry.py \
    --mode=standalone \
    --assume-yes-for-downloads \
    --jobs=1 \
    --include-package=omnibot \
    --include-data-dir=src/omnibot/sop=omnibot/sop \
    --include-data-dir=src/omnibot/skills=omnibot/skills \
    --output-dir=dist \
    --output-filename=omnibot-bin

# Default to a shell so the caller can `docker run --rm omnibot-builder-linux`
# and inspect /build/dist/_entry.dist/ directly.
CMD ["bash"]