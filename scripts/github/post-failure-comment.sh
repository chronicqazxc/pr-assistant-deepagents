#!/bin/bash
# Post failure comment to GitHub PR
# Called when GitHub Actions workflow fails

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$SCRIPT_DIR/../../}"

source "$PROJECT_ROOT/.env" 2>/dev/null || true

RED='\033[0;31m'
NC='\033[0m'

log_error() { echo -e "${RED}❌ $*${NC}"; }

log_error "Workflow failed! Posting failure comment..."

# Get PR URL from exports
GITHUB_EXPORTS_FILE="${GITHUB_EXPORTS_FILE:-/tmp/github_action_exports.sh}"
if [ -f "$GITHUB_EXPORTS_FILE" ]; then
  source "$GITHUB_EXPORTS_FILE"
fi

if [ -z "$PR_URL" ]; then
  log_error "PR_URL not found, skipping failure comment"
  exit 0
fi

# Clean PR URL (remove anchor)
clean_pr_url="${PR_URL%%#*}"
user="${USER:-github-actions}"
repo_url="${PR_ASSISTANT_REPO_URL:-https://github.com/your-org/pr-assistant}"

failure_comment="❌ PR Review failed!

[@${user}](https://github.com/${user})

[PR Assistant](${repo_url}) • [Run Log](${RUN_URL})"

# Post comment using Python
cd "$PROJECT_ROOT" || exit 1

uv run python3 -c "
import os
import sys
sys.path.insert(0, 'src')

from pr_assistant.agents.core.github_client import GitHubWriteClient

token = os.environ.get('GH_TOKEN', os.environ.get('GITHUB_TOKEN', ''))
if not token:
    print('No token available')
    sys.exit(1)

client = GitHubWriteClient(github_token=token)
try:
    result = client.post_comment(pr_url='${clean_pr_url}', text='''${failure_comment}''')
    print(f'Failure comment posted: {result}')
except Exception as e:
    print(f'Failed to post comment: {e}')
"
