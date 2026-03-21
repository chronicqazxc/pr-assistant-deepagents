#!/bin/bash
# Run PR review agent based on routing decision
#
# Required env vars:
#   COMMENT_ID      - Comment ID (if triggered by comment)
#   PR_URL          - Full PR URL
#   USER            - User who triggered the review
#   PROJECT_ROOT    - Project root directory
#   TRIGGER_COMMENT_FILE - File containing trigger comment JSON

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$SCRIPT_DIR/../../}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_success() { echo -e "${GREEN}✅ $*${NC}"; }
log_error() { echo -e "${RED}❌ ERROR: $*${NC}" >&2; }

# Source exports from previous steps
GITHUB_EXPORTS_FILE="${GITHUB_EXPORTS_FILE:-/tmp/github_action_exports.sh}"
if [ -f "$GITHUB_EXPORTS_FILE" ]; then
  source "$GITHUB_EXPORTS_FILE"
fi

cd "$PROJECT_ROOT" || exit 1

# Extract COMMENT_TEXT from trigger comment file if available
if [ -n "$TRIGGER_COMMENT_FILE" ] && [ -f "$TRIGGER_COMMENT_FILE" ]; then
  COMMENT_TEXT=$(jq -r '.body // ""' "$TRIGGER_COMMENT_FILE" 2>/dev/null || echo "")
fi

log_info "Running pr-assistant..."

if [ -n "$COMMENT_ID" ]; then
  log_info "Comment ID detected - using route-comment"
  pr_assistant_args=("route-comment" "$COMMENT_TEXT" "--pr-url" "${PR_URL}")
  if [ -n "$USER" ]; then
    pr_assistant_args+=("--user" "$USER")
  fi
  pr_assistant_args+=("--comment-id" "$COMMENT_ID")
else
  log_info "No comment ID - using review-pr"
  pr_assistant_args=("review-pr" "$PR_URL")
  if [ -n "$USER" ]; then
    pr_assistant_args+=("--user" "$USER")
  fi
fi

uv run pr-assistant "${pr_assistant_args[@]}"
