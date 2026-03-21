#!/bin/bash
# Test GitHub Actions workflow locally
# Simulates the complete GitHub Actions CI/CD workflow with environment variables,
# allowing fast iteration for PR Assistant development.
#
# This script orchestrates by calling scripts in the github folder.
#
# Usage:
#   ./scripts/simulate_github_action.sh \
#     --pr-url "https://github.com/owner/repo/pull/14" \
#     [--user "wayne"]

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GITHUB_SCRIPTS_DIR="$SCRIPT_DIR/github"

PR_URL=""
USER=""
START_TIME=$(date +%s)

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

cleanup() {
  log_info "🧹 Cleaning up..."

  if [ -f "$PROJECT_ROOT/review.log" ] || [ -f "$PROJECT_ROOT/test_github_action_env.txt" ]; then
    log_info "Logs preserved:"
    [ -f "$PROJECT_ROOT/review.log" ] && echo "  - review.log"
    [ -f "$PROJECT_ROOT/test_github_action_env.txt" ] && echo "  - test_github_action_env.txt"
  fi
}

trap cleanup EXIT

handle_error() {
  local exit_code=$?
  local line_number=$1

  log_error "Script failed at line $line_number with exit code $exit_code"
  exit $exit_code
}

trap 'handle_error $LINENO' ERR

show_help() {
  cat << EOF
Simulate GitHub Actions Workflow Locally

USAGE:
  $0 --pr-url <URL> [--user <USERNAME>]

REQUIRED ARGUMENTS:
  --pr-url <URL>    GitHub PR URL. Include issue comment ID to simulate a comment trigger:
                      https://github.com/owner/repo/pull/14
                      https://github.com/owner/repo/pull/14#issuecomment-4058947586

OPTIONAL ARGUMENTS:
  --user <USERNAME>  Username for footer attribution (default: \$(whoami))
  --help             Show this help message

EXAMPLES:
  # General review (no comment trigger)
  $0 --pr-url "https://github.com/owner/repo/pull/14"

  # Comment-triggered (fetches comment text automatically from GitHub)
  $0 --pr-url "https://github.com/owner/repo/pull/14#issuecomment-4058947586" --user wayne

NOTES:
  - Comment text is fetched automatically from GitHub when issue comment ID is in URL
  - Cleanup happens automatically (preserves logs)

EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case $1 in
      --pr-url)
        PR_URL="$2"
        shift 2
        ;;
      --user)
        USER="$2"
        shift 2
        ;;
      --help)
        show_help
        exit 0
        ;;
      *)
        log_error "Unknown option: $1"
        echo ""
        show_help
        exit 1
        ;;
    esac
  done

  if [ -z "$PR_URL" ]; then
    log_error "Missing required argument: --pr-url"
    echo ""
    show_help
    exit 1
  fi

  if [[ ! "$PR_URL" =~ ^https://github\.com/[^/]+/[^/]+/pull/[0-9]+(#.*)?$ ]]; then
    log_error "Invalid PR URL format: $PR_URL"
    echo "Expected format: https://github.com/owner/repo/pull/NUMBER"
    echo "               or: https://github.com/owner/repo/pull/NUMBER#issuecomment-ID"
    exit 1
  fi
}

validate_prerequisites() {
  log_step "🔍 Validating prerequisites"

  local has_errors=false

  if [ ! -f "$PROJECT_ROOT/.env" ]; then
    log_error ".env file not found"
    has_errors=true
  else
    log_success ".env file exists"
  fi

  if [ ! -f "$PROJECT_ROOT/pyproject.toml" ]; then
    log_error "pyproject.toml not found"
    has_errors=true
  else
    log_success "pyproject.toml exists"
  fi

  if [ ! -d "$PROJECT_ROOT/src/pr_assistant/agents/core" ]; then
    log_error "src/pr_assistant/agents/core/ directory not found"
    has_errors=true
  else
    log_success "src/pr_assistant/agents/core/ directory exists"
  fi

  if ! command -v jq &> /dev/null; then
    log_error "jq is not installed"
    has_errors=true
  else
    log_success "jq is installed"
  fi

  if ! command -v git &> /dev/null; then
    log_error "git is not installed"
    has_errors=true
  else
    log_success "git is installed"
  fi

  if [ "$has_errors" = true ]; then
    log_error "Prerequisites validation failed"
    exit 1
  fi

  log_success "All prerequisites validated"
  echo ""
}

main() {
  log_step "🚀 Starting Local GitHub Actions Workflow Test"

  parse_args "$@"

  validate_prerequisites

  # Clean up pre-fetched-data before execution
  if [ -d "$PROJECT_ROOT/pre-fetched-data" ]; then
    log_info "Cleaning up previous pre-fetched-data directory"
    rm -rf "$PROJECT_ROOT/pre-fetched-data"
  fi

  export PR_URL USER PROJECT_ROOT

  log_step "▶️  Executing Workflow Steps"

  bash "$GITHUB_SCRIPTS_DIR/01-setup-environment.sh"
  bash "$GITHUB_SCRIPTS_DIR/02-prefetch-data.sh"
  bash "$GITHUB_SCRIPTS_DIR/03-run-review.sh"

  local end_time=$(date +%s)
  local elapsed=$((end_time - START_TIME))
  local minutes=$((elapsed / 60))
  local seconds=$((elapsed % 60))

  log_step "✅ Test Completed Successfully"
  log_success "Total time: ${minutes}m ${seconds}s"

  echo ""
  echo "📊 Results:"
  echo "  PR URL: $PR_URL"
  [ -f "$PROJECT_ROOT/review.log" ] && echo "  Review log: review.log"
  [ -f "$PROJECT_ROOT/test_github_action_env.txt" ] && echo "  Environment: test_github_action_env.txt"
  echo ""
  echo "🧹 Cleanup:"
  echo "  Cloned repo will be removed automatically on exit"
  echo "  Logs are preserved for debugging"
  echo ""
}

main "$@"
