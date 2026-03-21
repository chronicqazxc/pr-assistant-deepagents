#!/bin/bash
# Prefetch PR data: metadata, diff, comments, clone repo
#
# Required env vars:
#   GH_TOKEN    - GitHub API token
#   OWNER           - Repository owner
#   REPO            - Repository name
#   PR_NUMBER       - PR number
#   PROJECT_ROOT    - Project root directory
#
# Output files in $PROJECT_ROOT/pre-fetched-data/:
#   pr_metadata.json, pr_diff.txt, issue_comments.json,
#   review_comments.json, trigger_comment.json
#
# Exported env vars:
#   PR_METADATA_FILE, PR_DIFF_FILE, ISSUE_COMMENTS_FILE,
#   REVIEW_COMMENTS_FILE, CLONED_REPO_PATH, TRIGGER_COMMENT_FILE

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

# Source exports from setup step if available
if [ -f "$GITHUB_EXPORTS_FILE" ]; then
  source "$GITHUB_EXPORTS_FILE"
fi

log_step "📦 Prefetching PR Data"

mkdir -p "$PROJECT_ROOT/pre-fetched-data"

# Use trigger comment from step 1 if available
if [ -n "$TRIGGER_COMMENT_FILE" ] && [ -f "$TRIGGER_COMMENT_FILE" ]; then
  trigger_comment_file="$PROJECT_ROOT/pre-fetched-data/trigger_comment.json"
  cp "$TRIGGER_COMMENT_FILE" "$trigger_comment_file"
  export TRIGGER_COMMENT_FILE="$trigger_comment_file"
  log_success "Trigger comment file copied"
fi

log_info "Fetching PR metadata..."
curl -s -f -H "Authorization: Bearer ${GH_TOKEN}" \
     -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER" \
     > "$PROJECT_ROOT/pre-fetched-data/pr_metadata.json" || {
  log_warning "Failed to fetch PR metadata"
}

if [ -s "$PROJECT_ROOT/pre-fetched-data/pr_metadata.json" ]; then
  log_success "PR metadata fetched"
else
  log_warning "Failed to fetch PR metadata"
fi
export PR_METADATA_FILE="$PROJECT_ROOT/pre-fetched-data/pr_metadata.json"

log_info "Fetching PR diff..."
curl -s -f -H "Authorization: Bearer ${GH_TOKEN}" \
     -H "Accept: application/vnd.github.diff" \
     "https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER" \
     > "$PROJECT_ROOT/pre-fetched-data/pr_diff.txt" || {
  log_warning "Failed to fetch PR diff"
}

if [ -s "$PROJECT_ROOT/pre-fetched-data/pr_diff.txt" ]; then
  log_success "PR diff fetched"
else
  log_warning "Failed to fetch PR diff"
fi
export PR_DIFF_FILE="$PROJECT_ROOT/pre-fetched-data/pr_diff.txt"

log_info "Fetching PR comments..."

issue_comments_file="$PROJECT_ROOT/pre-fetched-data/issue_comments.json"
curl -s -f -H "Authorization: Bearer ${GH_TOKEN}" \
     -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" \
     > "$issue_comments_file" || {
  log_warning "Failed to fetch issue comments"
  echo "[]" > "$issue_comments_file"
}

review_comments_file="$PROJECT_ROOT/pre-fetched-data/review_comments.json"
curl -s -f -H "Authorization: Bearer ${GH_TOKEN}" \
     -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments" \
     > "$review_comments_file" || {
  log_warning "Failed to fetch review comments"
  echo "[]" > "$review_comments_file"
}

issue_count=$(jq 'length' "$issue_comments_file" 2>/dev/null || echo "0")
review_count=$(jq 'length' "$review_comments_file" 2>/dev/null || echo "0")
log_success "PR comments fetched: $issue_count issue comments + $review_count review comments"

# Clone the repository from PR source branch
log_info "Cloning repository from PR source branch..."
if [ -d "$CLONED_REPO_PATH" ]; then
  rm -rf "$CLONED_REPO_PATH"
fi

pr_source_branch=$(jq -r '.head.ref' "$PROJECT_ROOT/pre-fetched-data/pr_metadata.json" 2>/dev/null)
pr_source_sha=$(jq -r '.head.sha' "$PROJECT_ROOT/pre-fetched-data/pr_metadata.json" 2>/dev/null)

if [ -n "$pr_source_branch" ] && [ "$pr_source_branch" != "null" ]; then
  log_info "PR source branch: $pr_source_branch (sha: ${pr_source_sha:0:7})"
  
  git clone --depth 1 --branch "$pr_source_branch" \
    "https://github.com/$OWNER/$REPO.git" "$CLONED_REPO_PATH" 2>/dev/null || {
    log_warning "Failed to clone from branch $pr_source_branch, falling back to default branch"
    git clone --depth 1 "https://github.com/$OWNER/$REPO.git" "$CLONED_REPO_PATH" 2>/dev/null || {
      log_warning "Failed to clone repository, will use API data only"
    }
  }
else
  log_warning "Could not determine PR source branch, cloning default branch"
  git clone --depth 1 "https://github.com/$OWNER/$REPO.git" "$CLONED_REPO_PATH" 2>/dev/null || {
    log_warning "Failed to clone repository, will use API data only"
  }
fi

if [ -d "$CLONED_REPO_PATH" ]; then
  log_success "Repository cloned"
else
  log_warning "Repository clone failed"
fi

# Export variables for next steps
echo "export PR_METADATA_FILE=$PROJECT_ROOT/pre-fetched-data/pr_metadata.json" >> "$GITHUB_EXPORTS_FILE"
echo "export PR_DIFF_FILE=$PROJECT_ROOT/pre-fetched-data/pr_diff.txt" >> "$GITHUB_EXPORTS_FILE"
echo "export ISSUE_COMMENTS_FILE=$PROJECT_ROOT/pre-fetched-data/issue_comments.json" >> "$GITHUB_EXPORTS_FILE"
echo "export REVIEW_COMMENTS_FILE=$PROJECT_ROOT/pre-fetched-data/review_comments.json" >> "$GITHUB_EXPORTS_FILE"
echo "export CLONED_REPO_PATH=$CLONED_REPO_PATH" >> "$GITHUB_EXPORTS_FILE"
echo "export TRIGGER_COMMENT_FILE=$PROJECT_ROOT/pre-fetched-data/trigger_comment.json" >> "$GITHUB_EXPORTS_FILE"

log_success "Prefetch completed"
