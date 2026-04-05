# PR Assistant

> **⚠️ POC Project** - This is a proof-of-concept implementation under active development.

**User intention-driven PR review assistant powered by DeepAgents**

PR Assistant automatically reviews pull requests and responds to comments based on user intent. It analyzes PRs, provides code reviews, and replies to comments intelligently.

## Features

- **Intention Routing**: Analyzes comment text to determine if user wants a review, reply, or emoji reaction
- **Contextual Code Review**: Reviews PRs with full context (metadata, diff, comments, cloned repo)
- **Intelligent Replies**: Responds to comments with contextually relevant answers
- **GitHub Native**: Integrates seamlessly with GitHub Actions and GitHub API
- **Extensible**: Add support for any repository by registering a new agent

## Pre-Fetched Data

Before agents run, data is prefetched from GitHub API and stored in `pre-fetched-data/`:

| File | Source | Purpose |
|------|--------|---------|
| `pr_metadata.json` | `GET /repos/{owner}/{repo}/pulls/{pr}` | PR metadata (title, description, author, base/head branches, status, labels) |
| `pr_diff.txt` | `GET /repos/{owner}/{repo}/pulls/{pr}` (Accept: `application/vnd.github.diff`) | Full unified diff of all changes in the PR |
| `issue_comments.json` | `GET /repos/{owner}/{repo}/issues/{pr}/comments` | General PR conversation comments |
| `review_comments.json` | `GET /repos/{owner}/{repo}/pulls/{pr}/comments` | Code review inline comments (diff comments) |
| `trigger_comment.json` | `GET /repos/{owner}/{repo}/issues/comments/{id}` or `GET /repos/{owner}/{repo}/pulls/comments/{id}` | The specific comment that triggered the bot |
| `<repo>/` | `git clone` of the PR's source branch | Local repository copy for deeper analysis (file reading, grep, etc.) |

**Source**: All data is fetched from GitHub API using `GH_TOKEN` (GitHub Actions token).

## Architecture

```
User Comment → Router Agent → Route Decision → Review Agent / Reply Agent / Emoji
```

Built on [DeepAgents](https://github.com/langchain-ai/deepagents), a agentic framework from LangChain.

## Quick Start

### 1. Register Your Agent

Register an agent for your repository:

```bash
python scripts/agent/register_agent.py https://github.com/owner/repo
```

### 2. Configure Your Agent

Fill in the agent's configuration:

- `docs/ROLE.md` - Agent identity and expertise
- `docs/REVIEW_GUIDELINES.md` - Code review patterns and severity rules

### 3. Setup GitHub Actions

In your target repository:

```bash
# Copy workflow
mkdir -p .github/workflows
curl -o .github/workflows/pr-assistant.yml \
  https://raw.githubusercontent.com/your-username/pr-assistant-deepagents/main/scripts/github/pr-assistant.yml
```

Add secrets/variables to your repository (Settings → Secrets and variables → Actions):

**Secrets:**
- `ANTHROPIC_API_KEY` - Anthropic API key (if using `anthropic`)
- `GOOGLE_API_KEY` - Google API key (if using `gemini`)

Note: `GH_TOKEN` is auto-provided by GitHub Actions (no manual secret needed).

**Variables:**
- `PR_ASSISTANT_REPO` - This repository URL (e.g., `your-username/pr-assistant-deepagents`)
- `LLM_PROVIDER` - `ollama`, `lm_studio`, `anthropic`, or `gemini`
- `TRIGGER_KEYWORD` - Bot mention keyword to trigger (e.g., `DangerCI001`)

**LLM Provider Settings (Variables):**

| Provider | Variables |
|----------|-----------|
| Ollama | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` (tested with gpt-oss:20b local) |
| LM Studio | `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL`, `LM_STUDIO_CONTEXT_LENGTH` (tested with gpt-oss-20b, glm-4.7-flash) |
| Anthropic | `ANTHROPIC_MODEL` |
| Gemini | `GEMINI_MODEL` |

Only add variables for the provider you're using.

### 4. Use It

Comment on a PR mentioning the bot to trigger:

```
@DangerCI001 please review
```

- **Mention bot**: Triggers review
- **Ask questions**: Routes to reply agent for contextual answers

## Comment Types

GitHub has two types of comments on PRs:

| Type | URL Pattern | Description |
|------|-------------|-------------|
| **Issue Comment** | `#issuecomment-123456` | General PR conversation comments |
| **Discussion Comment** | `#discussion_r123456` | Code review discussion threads |

Both can trigger the reply agent when you ask questions.

## Development

### Local Testing

```bash
# PR review (no comment trigger)
./scripts/simulate_github_action.sh \
  --pr-url "https://github.com/owner/repo/pull/123" \
  --user your-username

# Issue comment trigger
./scripts/simulate_github_action.sh \
  --pr-url "https://github.com/owner/repo/pull/123#issuecomment-4103174829" \
  --user your-username

# Discussion comment trigger
./scripts/simulate_github_action.sh \
  --pr-url "https://github.com/owner/repo/pull/123#discussion_r2936867746" \
  --user your-username
```

The script fetches the comment automatically when you include the comment ID in the URL anchor.

### Project Structure

```
pr-assistant-deepagents/
├── src/pr_assistant/
│   ├── agents/
│   │   ├── core/              # Core agents (router, base agents, GitHub client)
│   │   ├── weather_forcast/   # Example: platform-specific agent
│   │   └── registry.json      # Agent registry
│   └── main.py                # CLI entry point
├── scripts/
│   ├── github/                # GitHub Actions scripts
│   │   ├── 01-setup-environment.sh
│   │   ├── 02-prefetch-data.sh
│   │   ├── 03-run-review.sh
│   │   └── pr-assistant.yml   # GitHub Actions workflow template
│   ├── agent/
│   │   └── register_agent.py  # Scaffold new agents
│   └── simulate_github_action.sh
└── tests/
```

## Extending PR Assistant

### Register a New Agent

```bash
python scripts/agent/register_agent.py https://github.com/your-org/your-repo
```

This creates:

```
src/pr_assistant/agents/your_repo/
├── __init__.py
├── reviewer_agent.py          # Code review logic
├── comment_replier_agent.py   # Comment reply logic
└── docs/
    ├── ROLE.md                # Agent identity
    └── REVIEW_GUIDELINES.md   # Review patterns
```

### Agent Customization

**Role** (`docs/ROLE.md`):

```markdown
## Identity

You are a [Your Platform] Code Reviewer, an expert in...

## Expertise

You have deep knowledge of...
```

**Review Guidelines** (`docs/REVIEW_GUIDELINES.md`):

```markdown
## Per-File Review Checklist

**MAJOR (blocks merge):**

- Missing null checks → MAJOR

**MINOR (non-blocking):**

- Non-standard naming → MINOR
```

## Configuration

Environment variables (`.env`). In GitHub Actions, these are set via secrets/variables:

```bash
# GitHub (auto-provided in GitHub Actions as GH_TOKEN)
GH_TOKEN=<auto-provided>

# LLM Provider
LLM_PROVIDER=ollama  # or lm_studio, anthropic, gemini

# Ollama (local) - tested with gpt-oss:20b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
OLLAMA_CONTEXT_LENGTH=32768
OLLAMA_NUM_PREDICT=8192

# LM Studio (local) - tested with gpt-oss-20b, glm-4.7-flash
# IMPORTANT: Context length must be set at load time (via LM Studio UI or CLI), not here
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=gpt-oss-20b

# Anthropic
ANTHROPIC_API_KEY=<your-api-key>
ANTHROPIC_MODEL=claude-sonnet-4-6

# Gemini
GOOGLE_API_KEY=<your-api-key>
GEMINI_MODEL=gemini-2.0-flash
```

## License

MIT
