"""
Comment Router - Intelligent routing of user comments to appropriate agents.

This module replaces manual regex-based detection with Claude-powered
analysis of user intentions.
"""

import json
import os
import re
from pathlib import Path
from pydantic import BaseModel
import subprocess
from typing import Dict, Literal, Optional

import requests

from deepagents import create_deep_agent

from ...agent_config import AgentConfig
from ..llm_factory import create_llm


class RoutingDecision(BaseModel):
    """Schema for routing decision output."""
    decision: Literal["pr_review", "comment_reply", "emoji_reaction"]
    reason: str
    greeting: str


class CommentRouter:
    """
    Intelligent comment router that analyzes user intentions and invokes appropriate agents.

    Replaces manual regex detection with Claude-powered analysis.
    """

    def __init__(self, config: AgentConfig):
        """Initialize comment router with configuration."""
        self.config = config
        self.github_token = config.github_token
        self.github_base_url = config.github_base_url

        os.environ['GH_TOKEN'] = config.github_token
        os.environ['GITHUB_BASE_URL'] = config.github_base_url

        self.project_root = Path.cwd()
        self.agent_dir = Path(__file__).parent

        self.llm = create_llm(config)

        print("CommentRouter initialized", flush=True)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PR-Assistant/2.0",
        }

    async def analyze_comment(self, comment_text: str) -> Dict[str, any]:
        """Analyze comment with LLM to determine routing decision.
        
        Note for Ollama: We use with_structured_output() instead of 
        create_deep_agent + ToolStrategy because:
        - ToolStrategy uses streaming internally, which breaks with Ollama
        - The direct with_structured_output() method works correctly
        """
        template_path = Path(__file__).parent / "route_prompt.md"
        prompt = template_path.read_text().format(comment_text=comment_text)

        if self.config.llm_provider == "ollama":
            # Use direct structured output for Ollama (see llm_factory.py for context)
            structured_llm = self.llm.with_structured_output(RoutingDecision)
            result = structured_llm.invoke(prompt)
            return result.model_dump() if hasattr(result, 'model_dump') else dict(result)

        from langchain.agents.structured_output import ToolStrategy

        agent = create_deep_agent(
            model=self.llm,
            tools=[],
            response_format=ToolStrategy(schema=RoutingDecision),
        )

        result = agent.invoke({"messages": [("user", prompt)]})
        routing = result.get("structured_response")

        if not routing:
            raise ValueError("No structured response from agent")

        return routing.model_dump() if hasattr(routing, 'model_dump') else dict(routing)

    def _parse_pr_url(self, pr_url: str) -> tuple:
        """Parse owner, repo, pr_number from GitHub PR URL."""
        pattern = r'github\.com/([^/]+)/([^/]+)/pull/(\d+)'
        match = re.search(pattern, pr_url)
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
        return match.group(1), match.group(2), int(match.group(3))

    def _post_emoji_reaction(self, pr_url: str, comment_id: str, emoji: str) -> bool:
        """Post emoji reaction to a comment using GitHub Reactions API."""
        owner, repo, pr_number = self._parse_pr_url(pr_url)

        emoji_map = {
            "thumbsup": "+1",
            "thumbsdown": "-1",
            "heart": "heart",
            "laugh": "laugh",
            "hooray": "hooray",
            "confused": "confused",
            "eyes": "eyes",
        }

        reaction = emoji_map.get(emoji, "+1")

        base_url = self.github_base_url.rstrip("/")

        api_url = f"{base_url}/repos/{owner}/{repo}/issues/comments/{comment_id}/reactions"

        payload = {"content": reaction}

        response = requests.post(
            api_url,
            headers=self._headers(),
            json=payload,
            timeout=10,
        )

        if response.status_code in [200, 201]:
            print(f"  ✅ Emoji reaction posted: {emoji}", flush=True)
            return True
        else:
            print(f"  ⚠️ Failed to post emoji reaction: HTTP {response.status_code}", flush=True)
            return False

    async def route_comment(
        self,
        comment_text: str,
        pr_url: str,
        comment_id: Optional[str] = None,
        user: Optional[str] = None
    ) -> Dict[str, any]:
        """Main routing method: analyze comment and invoke appropriate agent(s)."""
        print(f"🔀 Routing comment from: {user or 'Unknown'}", flush=True)
        print(f"📝 Comment text: {comment_text[:100]}...", flush=True)
        print("", flush=True)

        # Extract comment_id from URL anchor if present
        if '#' in pr_url:
            anchor = pr_url.split('#')[-1]
            if 'issuecomment' in anchor:
                comment_id = anchor.split('-')[-1]
            elif 'discussion_r' in anchor:
                comment_id = anchor.split('_')[-1]

        decision = await self.analyze_comment(comment_text)
        print(f"✅ Routing decision: {json.dumps(decision, indent=2)}", flush=True)
        print("", flush=True)

        # Save routing decision to file for agents
        routing_file = str(self.project_root / "pre-fetched-data" / "routing_decision.json")
        os.makedirs(os.path.dirname(routing_file), exist_ok=True)
        with open(routing_file, 'w') as f:
            json.dump(decision, f)
        os.environ['ROUTING_DECISION_FILE'] = routing_file

        results = []
        action = decision["decision"]

        if action == "pr_review":
            print(f"🤖 Invoking review agent for PR: {pr_url}", flush=True)
            print("", flush=True)
            try:
                cmd = ["pr-assistant", "review-pr", pr_url]
                if user:
                    cmd.extend(["--user", user])

                env = os.environ.copy()
                env['ROUTING_DECISION_FILE'] = routing_file

                result = subprocess.run(
                    cmd,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=1500,
                    env=env
                )

                if result.returncode != 0:
                    print(f"❌ pr-review failed: {result.stderr}", flush=True)
                    raise Exception(f"PR review failed: {result.stderr}")

                print("✅ pr-review completed successfully", flush=True)
                print("", flush=True)
                results.append({"agent": "review-pr", "status": "success"})

            except subprocess.TimeoutExpired:
                print("❌ pr-review timed out (25 min)", flush=True)
                raise Exception("PR review timed out after 25 minutes")

        elif action == "comment_reply":
            if not comment_id:
                print("⚠️  Comment ID not provided, skipping reply", flush=True)
                print("", flush=True)
            else:
                print(f"💬 Invoking reply agent for comment: {pr_url}", flush=True)
                print("", flush=True)
                try:
                    cmd = ["pr-assistant", "reply-pr-comment", pr_url]
                    if user:
                        cmd.extend(["--user", user])

                    env = os.environ.copy()
                    env['ROUTING_DECISION_FILE'] = routing_file

                    result = subprocess.run(
                        cmd,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=300,
                        env=env
                    )

                    if result.returncode != 0:
                        print(f"❌ reply-pr-comment failed: {result.stderr}", flush=True)
                        raise Exception(f"Comment reply failed: {result.stderr}")

                    print("✅ reply-pr-comment completed successfully", flush=True)
                    print("", flush=True)
                    results.append({"agent": "reply-pr-comment", "status": "success"})

                except subprocess.TimeoutExpired:
                    print("❌ reply-pr-comment timed out (5 min)", flush=True)
                    raise Exception("Comment reply timed out after 5 minutes")

        elif action == "emoji_reaction":
            if not comment_id:
                print("⚠️  Comment ID not provided, skipping emoji reaction", flush=True)
                print("", flush=True)
            else:
                emoji = "thumbsup"
                print(f"😊 Adding emoji reaction: {emoji}", flush=True)
                print("", flush=True)

                success = self._post_emoji_reaction(pr_url, comment_id, emoji)
                if success:
                    print(f"✅ Emoji reaction posted: :{emoji}:", flush=True)
                    print("", flush=True)
                    results.append({"agent": "emoji-reaction", "status": "success", "emoji": emoji})
                else:
                    print(f"⚠️  Failed to post emoji reaction", flush=True)
                    print("", flush=True)
                    results.append({"agent": "emoji-reaction", "status": "failed", "emoji": emoji})

        return {"routing_decision": decision, "results": results}
