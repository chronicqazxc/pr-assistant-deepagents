#!/usr/bin/env python3
"""Scaffold a new PR Assistant platform agent.

Usage:
    python scripts/agent/register_agent.py <github_url> [agent_name]

Examples:
    python scripts/agent/register_agent.py https://github.com/owner/repo
    python scripts/agent/register_agent.py https://github.com/owner/repo my_agent

Note: GitHub Actions workflow template is at scripts/github/pr-assistant.yml
      Copy it to your repo's .github/workflows/ directory.
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
AGENTS_DIR = PROJECT_ROOT / "src" / "pr_assistant" / "agents"
REGISTRY = AGENTS_DIR / "registry.json"


def to_class_prefix(agent_name: str) -> str:
    return "".join(w.capitalize() for w in agent_name.split("_"))


REVIEWER_TEMPLATE = '''\
"""{prefix} code review agent."""

from pathlib import Path
from ..core.base_agent.base_reviewer import BaseReviewAgent
from ..agent_config import AgentConfig


class {reviewer_class}(BaseReviewAgent):

    def __init__(self, config: AgentConfig):
        super().__init__(config, agent_dir=Path(__file__).parent)
        print("{reviewer_class} initialized")

    def system_prompt_append(self) -> str:
        path = self.agent_dir / "docs" / "ROLE.md"
        soul = path.read_text() if path.exists() else ""
        return soul + "\\n\\nAt the very start of your response, introduce yourself in one sentence based on your identity above." if soul else ""

    def analysis_guideline_instruction(self) -> str:
        guidelines = self.agent_dir / "docs" / "REVIEW_GUIDELINES.md"
        return (
            f"Before analyzing files, read the review guidelines once:\\n"
            f"- Review guidelines: `{{guidelines}}` → output: `📋 Guidelines: [key areas you will focus on]`\\n"
            f"Then apply them to every file."
        ).format(guidelines=guidelines)
'''

ROLE_TEMPLATE = '''\
# {prefix} Agent Role

## Identity

TODO: Give this agent a name and one-line description.
e.g. "You are iOS Code Reviewer, an expert in Swift and iOS best practices."

## Expertise

TODO: Describe what this agent knows deeply.
e.g. "You have deep knowledge of iOS development, Swift best practices, and mobile architecture patterns."

## Communication Style

TODO: Describe how this agent communicates.
e.g. "Be direct and specific. Point to exact file and line. Explain why, not just what."
'''

REVIEW_GUIDELINES_TEMPLATE = '''\
# {prefix} Review Guidelines

TODO: Describe team conventions and the repo this agent reviews.

---

## Per-File Review Checklist

For every file in the PR diff, scan ADDED lines for these patterns:

**MAJOR (blocks merge):**
- TODO: add pattern → e.g. missing null check on API response → MAJOR

**MINOR (non-blocking):**
- TODO: add pattern → e.g. non-standard naming convention → MINOR

---

## Always Skip

- TODO: list files or patterns to ignore (e.g. generated files, vendor code, test fixtures)
'''

REPLIER_TEMPLATE = '''\
"""{prefix} comment reply agent."""

from pathlib import Path
from ..core.base_agent.base_comment_replier import BaseCommentReplyAgent
from ..agent_config import AgentConfig


class {replier_class}(BaseCommentReplyAgent):

    def __init__(self, config: AgentConfig):
        super().__init__(config, agent_dir=Path(__file__).parent)
        print("{replier_class} initialized")

    def system_prompt_append(self) -> str:
        path = self.agent_dir / "docs" / "ROLE.md"
        soul = path.read_text() if path.exists() else ""
        return soul + "\\n\\nAt the very start of your response, introduce yourself in one sentence based on your identity above." if soul else ""

    def analysis_guideline_instruction(self) -> str:
        return ""
'''


def extract_repo_slug(url: str) -> str:
    match = re.search(r'/repos/([^/]+)', url)
    if not match:
        match = re.search(r'github\.com/[^/]+/([^/]+?)(?:\.git)?$', url)
    if not match:
        sys.exit(f"Error: could not extract repo slug from URL: {url}")
    return match.group(1)


def slug_to_snake(slug: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', slug)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower().replace("-", "_")


def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python scripts/agent/register_agent.py <github_url> [agent_name]")
        print("Example: python scripts/agent/register_agent.py https://github.com/owner/repo")
        print("\nNote: GitHub Actions workflow template: scripts/github/pr-assistant.yml")
        sys.exit(1)

    url = sys.argv[1].strip()
    url_pattern = extract_repo_slug(url)

    agent_name = sys.argv[2].strip() if len(sys.argv) == 3 else slug_to_snake(url_pattern)
    print(f"Agent name: {agent_name}")

    if not re.match(r'^[a-z][a-z0-9_]+$', agent_name):
        sys.exit("Error: agent_name must be lowercase snake_case")

    agent_dir = AGENTS_DIR / agent_name
    if agent_dir.exists():
        sys.exit(f"Error: {agent_dir} already exists")

    prefix = to_class_prefix(agent_name)
    reviewer_class = f"{prefix}CodeReviewAgent"
    replier_class = f"{prefix}CommentReplyAgent"
    module_base = f"pr_assistant.agents.{agent_name}"

    agent_dir.mkdir()
    (agent_dir / "docs").mkdir()

    (agent_dir / "__init__.py").write_text("")
    (agent_dir / "reviewer_agent.py").write_text(
        REVIEWER_TEMPLATE.format(prefix=prefix, reviewer_class=reviewer_class)
    )
    (agent_dir / "comment_replier_agent.py").write_text(
        REPLIER_TEMPLATE.format(prefix=prefix, replier_class=replier_class)
    )
    (agent_dir / "docs" / "ROLE.md").write_text(
        ROLE_TEMPLATE.format(prefix=prefix)
    )
    (agent_dir / "docs" / "REVIEW_GUIDELINES.md").write_text(
        REVIEW_GUIDELINES_TEMPLATE.format(prefix=prefix)
    )

    registry = json.loads(REGISTRY.read_text())
    registry["agents"].append({
        "url_patterns": [url_pattern],
        "reviewer_class": f"{module_base}.reviewer_agent.{reviewer_class}",
        "replier_class": f"{module_base}.comment_replier_agent.{replier_class}"
    })
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")

    print(f"\n✅ Scaffold created: src/pr_assistant/agents/{agent_name}/")
    print("\nNext steps:")
    print(f"  1. Fill in docs/REVIEW_GUIDELINES.md — add your team's patterns and severity rules")
    print(f"  2. Fill in docs/ROLE.md — agent identity, expertise, communication style")
    print(f"  3. Verify: python -c \"from pr_assistant.agents.{agent_name}.reviewer_agent import {reviewer_class}; print('OK')\"")
    print(f"\n  4. Setup GitHub Actions:")
    print(f"     - Copy scripts/github/pr-assistant.yml to your repo at:")
    print(f"       .github/workflows/pr-assistant.yml")
    print(f"     - Add secrets to your repo:")
    print(f"       - PR_ASSISTANT_REPO: <your-username>/pr-assistant-deepagents")
    print(f"       - LLM_PROVIDER: ollama (or anthropic, gemini)")


if __name__ == "__main__":
    main()
