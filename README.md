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

Add secrets to your repository:

- `PR_ASSISTANT_REPO` - This repository URL (e.g., `your-username/pr-assistant-deepagents`)
- `LLM_PROVIDER` - `ollama` (local), `anthropic`, or `gemini`

### 4. Use It

- **Open a PR**: Automatically triggers review
- **Comment `/review`**: Triggers review on demand
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

Environment variables (`.env`):

```bash
# GitHub
GITHUB_TOKEN=ghp_xxx
GITHUB_BASE_URL=https://api.github.com

# LLM Provider
LLM_PROVIDER=ollama  # or anthropic, gemini

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_MODEL=claude-sonnet-4-6

# Gemini
GOOGLE_API_KEY=xxx
GEMINI_MODEL=gemini-2.0-flash
```

## License

MIT
