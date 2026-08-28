#!/usr/bin/env bash
set -euo pipefail

# Publish extension to Microsoft Edge Add-ons Store.
#
# Usage:
#   EDGE_API_KEY=<key> ./scripts/publish-edge-extension.sh <extension.zip>
#
# Environment variables:
#   EDGE_PRODUCT_ID  - Edge Add-ons product ID (required, from Partner Center)
#   EDGE_CLIENT_ID   - Edge Add-ons client ID (required, from Partner Center)
#   EDGE_API_KEY     - Edge Add-ons API key (required)
#
# API Documentation:
#   https://learn.microsoft.com/en-us/microsoft-edge/extensions/update/api/using-addons-api

EXTENSION_ZIP="${1:?Usage: publish-edge-extension.sh <extension.zip>}"

if [ ! -f "$EXTENSION_ZIP" ]; then
  echo "ERROR: Extension zip not found: $EXTENSION_ZIP"
  exit 1
fi

EDGE_PRODUCT_ID="${EDGE_PRODUCT_ID:?EDGE_PRODUCT_ID is required}"
EDGE_CLIENT_ID="${EDGE_CLIENT_ID:?EDGE_CLIENT_ID is required}"
EDGE_API_KEY="${EDGE_API_KEY:?EDGE_API_KEY is required}"

BASE_URL="https://api.addons.microsoftedge.microsoft.com"

echo "==> Edge Add-ons Store Publish"
echo "    Product ID: $EDGE_PRODUCT_ID"
echo "    Client ID:  $EDGE_CLIENT_ID"
echo "    Extension:  $EXTENSION_ZIP"
echo ""

# Step 1: Upload package to draft submission
echo "==> Step 1: Uploading extension package..."
UPLOAD_HEADERS="/tmp/edge-upload-headers.txt"
UPLOAD_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -D "$UPLOAD_HEADERS" -X POST \
  -H "Authorization: ApiKey $EDGE_API_KEY" \
  -H "X-ClientID: $EDGE_CLIENT_ID" \
  -H "Content-Type: application/zip" \
  --data-binary "@$EXTENSION_ZIP" \
  "$BASE_URL/v1/products/$EDGE_PRODUCT_ID/submissions/draft/package")

HTTP_CODE=$(echo "$UPLOAD_RESPONSE" | grep "HTTP_STATUS:" | sed 's/HTTP_STATUS://')
BODY=$(echo "$UPLOAD_RESPONSE" | grep -v "HTTP_STATUS:")

echo "    HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "202" ]; then
  echo "    Response: $BODY"
  echo "ERROR: Failed to upload package"
  exit 1
fi

# Extract operation ID from Location header
UPLOAD_OP_ID=$(grep -i "^Location:" "$UPLOAD_HEADERS" 2>/dev/null | awk '{print $2}' | tr -d '\r\n' || echo "")

if [ -z "$UPLOAD_OP_ID" ]; then
  echo "    WARNING: Could not extract operation ID from Location header"
  echo "    Headers: $(cat "$UPLOAD_HEADERS" 2>/dev/null)"
else
  echo "    Upload Operation ID: $UPLOAD_OP_ID"
fi

echo "    Upload accepted"
echo ""

# Step 2: Check upload status (if we have operation ID)
if [ -n "$UPLOAD_OP_ID" ]; then
  echo "==> Step 2: Checking upload status..."
  MAX_RETRIES=10
  RETRY_COUNT=0
  UPLOAD_STATUS="InProgress"

  while [ "$UPLOAD_STATUS" = "InProgress" ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 3
    RETRY_COUNT=$((RETRY_COUNT + 1))

    STATUS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET \
      -H "Authorization: ApiKey $EDGE_API_KEY" \
      -H "X-ClientID: $EDGE_CLIENT_ID" \
      "$BASE_URL/v1/products/$EDGE_PRODUCT_ID/submissions/draft/package/operations/$UPLOAD_OP_ID")

    STATUS_CODE=$(echo "$STATUS_RESPONSE" | grep "HTTP_STATUS:" | sed 's/HTTP_STATUS://')
    STATUS_BODY=$(echo "$STATUS_RESPONSE" | grep -v "HTTP_STATUS:")

    # Parse status from JSON response
    UPLOAD_STATUS=$(echo "$STATUS_BODY" | jq -r '.status // "Unknown"' 2>/dev/null || echo "Unknown")
    echo "    Attempt $RETRY_COUNT/$MAX_RETRIES: Status = $UPLOAD_STATUS"

    if [ "$UPLOAD_STATUS" = "Succeeded" ]; then
      echo "    Upload completed successfully"
      break
    elif [ "$UPLOAD_STATUS" = "Failed" ]; then
      echo "    Response: $STATUS_BODY"
      echo "ERROR: Upload failed"
      exit 1
    fi
  done

  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "    WARNING: Upload status check timed out, proceeding with publish..."
  fi
  echo ""
fi

# Step 3: Publish the submission
echo "==> Step 3: Publishing submission..."
PUBLISH_HEADERS="/tmp/edge-publish-headers.txt"
PUBLISH_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -D "$PUBLISH_HEADERS" -X POST \
  -H "Authorization: ApiKey $EDGE_API_KEY" \
  -H "X-ClientID: $EDGE_CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Automated release"}' \
  "$BASE_URL/v1/products/$EDGE_PRODUCT_ID/submissions")

HTTP_CODE=$(echo "$PUBLISH_RESPONSE" | grep "HTTP_STATUS:" | sed 's/HTTP_STATUS://')
BODY=$(echo "$PUBLISH_RESPONSE" | grep -v "HTTP_STATUS:")

echo "    HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "202" ]; then
  echo "    Response: $BODY"
  echo "ERROR: Failed to publish submission"
  exit 1
fi

# Extract publish operation ID
PUBLISH_OP_ID=$(grep -i "^Location:" "$PUBLISH_HEADERS" 2>/dev/null | awk '{print $2}' | tr -d '\r\n' || echo "")

if [ -n "$PUBLISH_OP_ID" ]; then
  echo "    Publish Operation ID: $PUBLISH_OP_ID"
fi

echo ""
echo "==> Edge Add-ons publish complete!"
echo "    Extension has been submitted for review."

# Cleanup
rm -f "$UPLOAD_HEADERS" "$PUBLISH_HEADERS"
