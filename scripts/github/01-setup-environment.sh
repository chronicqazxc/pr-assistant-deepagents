#!/bin/bash
# Setup GitHub Actions environment
# Parses PR_URL, loads credentials, sets up env vars, fetches trigger comment
#
# Required:
#   PR_URL          - GitHub PR URL
#   PROJECT_ROOT    - Project root directory
#   (from .env)     - GITHUB_TOKEN, LLM_PROVIDER
#
# Optional:
#   USER            - Username who triggered the review
#
# Output:
#   Sets OWNER, REPO, PR_NUMBER, COMMENT_ID, COMMENT_TEXT, TRIGGER_COMMENT_RESPONSE
#   Exports to GITHUB_EXPORTS_FILE

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$SCRIPT_DIR/../../}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $*${NC}"; }
log_success() { echo -e "${GREEN}✅ $*${NC}"; }
log_error() { echo -e "${RED}❌ ERROR: $*${NC}" >&2; }
log_warning() { echo -e "${YELLOW}⚠️  WARNING: $*${NC}"; }

log_step() {
  echo ""
  echo "================================================"
  echo "$1"
  echo "================================================"
  echo ""
}

GITHUB_EXPORTS_FILE="${GITHUB_EXPORTS_FILE:-/tmp/github_action_exports.sh}"
rm -f "$GITHUB_EXPORTS_FILE"
touch "$GITHUB_EXPORTS_FILE"

log_step "🔧 Setting up GitHub Actions environment"

cd "$PROJECT_ROOT" || exit 1
log_info "Working directory: $PROJECT_ROOT"

if [ -f "$PROJECT_ROOT/.env" ]; then
  log_info "Loading API credentials from .env..."
  set -a
  source "$PROJECT_ROOT/.env"
  set +a

  if [ -z "$GITHUB_TOKEN" ]; then
    log_error "GITHUB_TOKEN not set in .env"
    exit 1
  fi

  if [ -z "$LLM_PROVIDER" ]; then
    export LLM_PROVIDER="ollama"
  fi

  log_success "API credentials loaded"
else
  log_error ".env file not found at: $PROJECT_ROOT/.env"
  echo "Create .env with GITHUB_TOKEN and LLM_PROVIDER"
  exit 1
fi

# Parse GitHub PR URL
if [[ "$PR_URL" =~ ^https://github\.com/([^/]+)/([^/]+)/pull/([0-9]+) ]]; then
  OWNER="${BASH_REMATCH[1]}"
  REPO="${BASH_REMATCH[2]}"
  PR_NUMBER="${BASH_REMATCH[3]}"
else
  log_error "Failed to parse PR URL: $PR_URL"
  log_error "Expected: https://github.com/owner/repo/pull/NUMBER"
  exit 1
fi

log_info "PR Details:"
log_info "  Owner: $OWNER"
log_info "  Repo: $REPO"
log_info "  PR Number: $PR_NUMBER"

# Extract COMMENT_ID from URL anchor if present
if [[ "$PR_URL" =~ issuecomment-([0-9]+) ]]; then
  COMMENT_ID="${BASH_REMATCH[1]}"
  log_info "Comment ID (issuecomment): $COMMENT_ID"
elif [[ "$PR_URL" =~ discussion_r([0-9]+) ]]; then
  COMMENT_ID="${BASH_REMATCH[1]}"
  log_info "Comment ID (discussion): $COMMENT_ID"
fi

# Fetch trigger comment if COMMENT_ID is set
if [ -n "$COMMENT_ID" ]; then
  log_info "Fetching comment $COMMENT_ID from GitHub..."

  if [[ "$PR_URL" == *"#discussion"* ]]; then
    log_info "Detected discussion comment, using PR review API"
    comment_response=$(curl -s -f \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/$OWNER/$REPO/pulls/comments/$COMMENT_ID") || {
      log_warning "Failed to fetch PR review comment"
    }
  else
    log_info "Detected issue comment, using issue comments API"
    comment_response=$(curl -s -f \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/$OWNER/$REPO/issues/comments/$COMMENT_ID") || {
      log_warning "Failed to fetch issue comment"
    }
  fi

  if [ -n "$comment_response" ]; then
    COMMENT_TEXT=$(echo "$comment_response" | jq -r '.body // ""')
    if [ -n "$COMMENT_TEXT" ] && [ "$COMMENT_TEXT" != "null" ]; then
      log_success "Comment fetched: ${COMMENT_TEXT:0:100}..."
      TRIGGER_COMMENT_RESPONSE="$comment_response"
    else
      log_warning "Could not fetch comment text (continuing without it)"
    fi
  fi
fi

# Export all variables
export GITHUB_REPOSITORY="$OWNER/$REPO"
export GITHUB_BASE_REF="refs/pull/$PR_NUMBER/head"
export GITHUB_HEAD_REF=""
export GITHUB_EVENT_NAME="pull_request"
export GITHUB_EVENT_PATH=""
export GITHUB_ACTOR="${USER:-$(whoami)}"
export GITHUB_ACTION="pr-assistant"
export GITHUB_RUN_ID="test-run-$(date +%s)"
export GITHUB_RUN_NUMBER="1"
export OWNER REPO PR_NUMBER
export CLONED_REPO_PATH="$PROJECT_ROOT/pre-fetched-data/$REPO"

# Save TRIGGER_COMMENT_RESPONSE to file (JSON may contain special chars)
if [ -n "$TRIGGER_COMMENT_RESPONSE" ]; then
  mkdir -p "$PROJECT_ROOT/pre-fetched-data"
  echo "$TRIGGER_COMMENT_RESPONSE" > "$PROJECT_ROOT/pre-fetched-data/trigger_comment_raw.json"
  export TRIGGER_COMMENT_FILE="$PROJECT_ROOT/pre-fetched-data/trigger_comment_raw.json"
fi

# Write exports to file for sourcing in subsequent steps
{
  echo "export GITHUB_TOKEN=$GITHUB_TOKEN"
  echo "export LLM_PROVIDER=$LLM_PROVIDER"
  echo "export GITHUB_REPOSITORY=$GITHUB_REPOSITORY"
  echo "export OWNER=$OWNER"
  echo "export REPO=$REPO"
  echo "export PR_NUMBER=$PR_NUMBER"
  echo "export PR_URL=\"$PR_URL\""
  echo "export COMMENT_ID=$COMMENT_ID"
  echo "export USER=\"$USER\""
  echo "export CLONED_REPO_PATH=$CLONED_REPO_PATH"
  [ -n "$TRIGGER_COMMENT_FILE" ] && echo "export TRIGGER_COMMENT_FILE=$TRIGGER_COMMENT_FILE"
} >> "$GITHUB_EXPORTS_FILE"

log_success "Environment setup complete"
echo ""
