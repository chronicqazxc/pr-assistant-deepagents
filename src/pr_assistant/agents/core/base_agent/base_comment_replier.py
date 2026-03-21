"""Base class for platform-specific comment reply agents."""

import json
import os
import traceback
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from ...agent_config import AgentConfig
from ..github_client import GitHubWriteClient
from ..footer import generate_footer
from ..llm_factory import create_llm


class BaseCommentReplyAgent:
    """Shared reply logic for all platform agents.

    Subclasses pass their own agent_dir and optionally override
    extra_file_lines() to inject platform-specific files.
    Platform name is set via platform_name class attribute.
    """

    def __init__(self, config: AgentConfig, agent_dir: Path):
        os.environ['GITHUB_TOKEN'] = config.github_token
        os.environ['GITHUB_BASE_URL'] = config.github_base_url

        self.config = config
        self.agent_dir = agent_dir
        self.project_root = Path.cwd()

        self.client = GitHubWriteClient(
            github_token=config.github_token,
            base_url=config.github_base_url,
        )

        self.llm = create_llm(config)

    def extra_file_lines(self) -> list:
        """Return additional file lines to inject into the agent prompt.

        Override in subclasses to add platform-specific files.
        """
        return []

    def analysis_guideline_instruction(self) -> str:
        """Return platform-specific guideline instruction for Step 2.

        Override in subclasses to inject explicit guideline file paths with read instructions.
        """
        return ""

    def system_prompt_append(self) -> str:
        """Return content to append to the system prompt (e.g. personality/Soul file).

        Override in subclasses to inject platform-specific identity.
        """
        return ""

    def _parse_comment_url(self, comment_url: str) -> dict:
        # Simple: extract anchor (after #) and determine type
        anchor = comment_url.split('#')[-1] if '#' in comment_url else ''

        if 'issuecomment' in anchor:
            comment_type = 'issue'
            comment_id = anchor.split('-')[-1]
        elif 'discussion' in anchor:
            comment_type = 'discussion'
            # Format: discussion_r123456 -> extract number after r
            comment_id = anchor.split('r')[-1]
        else:
            raise ValueError(f"Invalid comment URL: {comment_url}")

        pr_url = comment_url.split('#')[0]

        return {
            'comment_id': comment_id,
            'comment_type': comment_type,
            'pr_url': pr_url,
        }

    async def reply_to_comment(self, comment_url: str) -> str:
        """Reply to a PR comment thread."""
        result_file = None
        try:
            print(f"Replying to comment: {comment_url}")
            print(f"Agent directory: {self.agent_dir}")

            parsed = self._parse_comment_url(comment_url)
            pr_url = parsed['pr_url']
            print(f"parsed['comment_id']: {parsed['comment_id']}")
            comment_id = int(parsed['comment_id'])
            comment_type = parsed['comment_type']
            print(f"Parsed: PR={pr_url}, CommentID={comment_id}, Type={comment_type}")

            print("\n🔍 Pre-fetched data availability:")
            for env_var in ['PR_METADATA_FILE', 'PR_DIFF_FILE', 'CLONED_REPO_PATH']:
                value = os.environ.get(env_var)
                if value:
                    print(f"  {'✅' if os.path.exists(value) else '❌'} {env_var}={value}")
                else:
                    print(f"  ⚠️  {env_var}=<not set>")
            print()

            # ── Step 2: Run agent ───────────────────────────────────────────────────────
            custom_system_prompt = self.system_prompt_append()
            system_prompt = custom_system_prompt

            # Read trigger comment from file (full JSON object)
            trigger_comment_file = os.environ.get("TRIGGER_COMMENT_FILE", "")
            trigger_comment_obj = {}
            if trigger_comment_file and os.path.exists(trigger_comment_file):
                try:
                    with open(trigger_comment_file) as f:
                        trigger_comment_obj = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"⚠️ Failed to read trigger comment file: {e}")

            # Read routing decision from comment router (for future use)
            routing_file = os.environ.get('ROUTING_DECISION_FILE')
            routing_decision = {}
            if routing_file and os.path.exists(routing_file):
                try:
                    with open(routing_file) as f:
                        routing_decision = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass

            # Use virtual paths for the agent's filesystem
            virtual_result_filename = "reply_result.json"

            # Build simplified file_locations for agent - let it explore
            cloned_repo_path = os.environ.get("CLONED_REPO_PATH", "")
            cloned_repo_name = os.path.basename(cloned_repo_path) if cloned_repo_path else "WeatherForecast"
            virtual_file_lines = [
                "- PR metadata: /pr_metadata.json",
                "- PR diff: /pr_diff.txt",
                f"- Cloned Repo: /{cloned_repo_name}"
            ]
            issue_comments_file = os.environ.get("ISSUE_COMMENTS_FILE", "")
            if issue_comments_file:
                virtual_file_lines.append("- Issue comments: /issue_comments.json")
            review_comments_file = os.environ.get("REVIEW_COMMENTS_FILE", "")
            if review_comments_file:
                virtual_file_lines.append("- Review comments: /review_comments.json")
            if trigger_comment_file:
                virtual_file_lines.append("- Trigger comment: /trigger_comment.json")

            template_path = Path(__file__).parent / "reply_prompt.md"

            pr_metadata_content = ""
            pr_diff_content = ""

            pr_metadata_file = os.environ.get('PR_METADATA_FILE')
            if pr_metadata_file and os.path.exists(pr_metadata_file):
                with open(pr_metadata_file) as f:
                    pr_metadata_content = f.read()

            pr_diff_file = os.environ.get('PR_DIFF_FILE')
            if pr_diff_file and os.path.exists(pr_diff_file):
                with open(pr_diff_file) as f:
                    pr_diff_content = f.read()[:50000]

            prompt = template_path.read_text().format(
                comment_url=comment_url,
                file_lines="\n".join(virtual_file_lines),
                analysis_guideline_instruction=self.analysis_guideline_instruction(),
                result_file=virtual_result_filename,
            )

            # Use pre-fetched-data as agent working directory (same as base_reviewer)
            agent_work_dir = str(self.project_root / "pre-fetched-data")
            result_file = os.path.join(agent_work_dir, "reply_result.json")

            # Delete result file before agent runs so it can create fresh
            if os.path.exists(result_file):
                os.remove(result_file)

            print(f"  Agent working directory: {agent_work_dir}")
            print(f"  Reply result file: {result_file}")

            # Copy pre-fetched data to agent's working directory
            print(f"  pr_metadata_content: {len(pr_metadata_content) if pr_metadata_content else 0} chars")
            if pr_metadata_content:
                with open(os.path.join(agent_work_dir, "pr_metadata.json"), "w") as f:
                    f.write(pr_metadata_content)
                print(f"    Wrote pr_metadata.json")
            print(f"  pr_diff_content: {len(pr_diff_content) if pr_diff_content else 0} chars")
            if pr_diff_content:
                with open(os.path.join(agent_work_dir, "pr_diff.txt"), "w") as f:
                    f.write(pr_diff_content)
                print(f"    Wrote pr_diff.txt")
            if trigger_comment_obj:
                with open(os.path.join(agent_work_dir, "trigger_comment.json"), "w") as f:
                    json.dump(trigger_comment_obj, f, indent=2)
                print(f"    Wrote trigger_comment.json")

            # Note: Cloned repo is already in pre-fetched-data/WeatherForecast

            backend = FilesystemBackend(root_dir=agent_work_dir, virtual_mode=True)
            agent = create_deep_agent(
                model=self.llm,
                backend=backend,
                system_prompt=system_prompt,
            )

            response_text = ""
            print("\n🤖 Comment Reply Agent Execution:\n")
            print("=" * 80)

            try:
                result = agent.invoke({"messages": [("user", prompt)]})

                # Get response content and print debug info
                print(f"DEBUG: result messages count: {len(result.get('messages', []))}")
                if result.get("messages"):
                    for i, msg in enumerate(result.get("messages", [])):
                        msg_type = type(msg).__name__
                        print(f"msg_type:", msg_type)
                        content = msg.content if hasattr(msg, 'content') and msg.content else ""
                        if 'AIMessage' in msg_type:
                            print(f"\n=== AIMessage {i} ===\n{content}\n=== END ===")
                        elif 'ToolMessage' in msg_type:
                            print(f"\n=== ToolMessage {i} ===\n{content}\n=== END ===")

                        if isinstance(msg.content, str):
                            response_text += msg.content
                        elif isinstance(msg.content, list):
                            for block in msg.content:
                                if isinstance(block, str):
                                    response_text += block
                                elif isinstance(block, dict) and 'text' in block:
                                    response_text += block['text']
            except Exception as e:
                print(f"Error during agent execution: {e}")
                traceback.print_exc()

            print("\n" + "=" * 80)
            print("\n✅ Agent execution complete")
            print()

            # ── Step 3: Parse JSON result ──────────────────────────────────────────────
            # Read from agent's working directory (pre-fetched-data)
            agent_result_path = os.path.join(agent_work_dir, virtual_result_filename)
            print(f"📂 Reading reply result from: {agent_result_path}")

            content = ""
            if os.path.exists(agent_result_path):
                with open(agent_result_path) as f:
                    content = f.read()
                print(f"  ✅ Found result file with {len(content)} chars")
            else:
                raise FileNotFoundError(
                    f"Agent did not write reply result to {agent_result_path}. "
                    "Check agent logs for errors."
                )

            reply_result = json.loads(content)

            reply_text = reply_result.get("reply", "")
            print(f"  ✅ Parsed: {len(reply_text)} chars in reply")

            # ── Step 4: Generate footer ───────────────────────────────────────────────
            print("\n🔧 Generating footer...")
            footer = generate_footer()
            print(f"  ✅ Footer: {len(footer)} chars")

            # ── Step 5: Post reply ─────────────────────────────────────────────────────
            print("\n🚀 Posting reply to GitHub...")

            # For issue comments, quote the original comment
            # For discussion comments, reply directly (no quote needed)
            trigger_comment_body = trigger_comment_obj.get('body', '') if trigger_comment_obj else ''
            full_reply = reply_text + "\n\n" + footer if footer else reply_text

            print(f"DEBUG: comment_type={comment_type}, comment_id={comment_id}")

            # Use shared helper to post comment (handles quoting automatically)
            self.client.post_trigger_comment(comment_url=comment_url, text=full_reply, quote_body=trigger_comment_body)

            print("\n✅ Reply complete\n")
            return response_text

        except Exception as e:
            print(f"❌ Error replying to comment: {e}")
            traceback.print_exc()
            raise
