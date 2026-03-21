"""Base class for platform-specific code review agents."""

import json
import os
import signal
import traceback
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.utils import create_file_data

from ...agent_config import AgentConfig
from ..github_client import GitHubWriteClient
from ..footer import generate_footer
from ..llm_factory import create_llm
from ..streaming import smart_truncate


def _load_json_safe(content: str) -> dict:
    """Parse JSON written by an LLM, handling common generation mistakes."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        from json_repair import repair_json
        return json.loads(repair_json(content))


class BaseReviewAgent:
    """Shared review logic for all platform agents.

    Subclasses pass their own agent_dir so the base class doesn't need to
    know its filesystem location. Platform-specific files are injected via
    extra_file_lines(). Platform name for summary titles is set via platform_name.
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
        Each entry must be formatted as "- <label>: <path>".
        """
        return []

    def analysis_guideline_instruction(self) -> str:
        """Return the per-file analysis instruction for Step 2.

        Override in subclasses to point to specific guidelines read in Step 1,
        or to describe what expertise to apply.
        """
        return "Apply your built-in platform expertise to identify issues"

    def system_prompt_append(self) -> str:
        """Return content to append to the system prompt (e.g. personality/Soul file).

        Override in subclasses to inject platform-specific identity.
        Returns empty string if not applicable.
        """
        return ""

    async def review_pr(self, pr_url: str):
        """Review a PR: read pre-fetched data → run agent → post comments."""
        result_file = None
        comment_id = None
        try:
            base_pr_url = pr_url
            if "?commentId=" in pr_url:
                base_pr_url, url_query = pr_url.split("?", 1)
                if "commentId=" in url_query:
                    comment_id = url_query.split("commentId=")[1].split("&")[0]
                    print(f"Reviewing PR: {base_pr_url} (triggered by comment {comment_id})")
            if base_pr_url == pr_url:
                print(f"Reviewing PR: {pr_url}")

            print(f"Agent directory: {self.agent_dir}")

            pr_metadata_file = os.environ.get('PR_METADATA_FILE')
            pr_diff_file = os.environ.get('PR_DIFF_FILE')
            cloned_repo_path = os.environ.get('CLONED_REPO_PATH')
            issue_comments_file = os.environ.get('ISSUE_COMMENTS_FILE')
            review_comments_file = os.environ.get('REVIEW_COMMENTS_FILE')
            trigger_comment_file = os.environ.get('TRIGGER_COMMENT_FILE')

            print("\n🔍 Pre-fetched data availability:")
            for env_var, value in [
                ('PR_METADATA_FILE', pr_metadata_file),
                ('PR_DIFF_FILE', pr_diff_file),
                ('CLONED_REPO_PATH', cloned_repo_path),
                ('ISSUE_COMMENTS_FILE', issue_comments_file),
                ('REVIEW_COMMENTS_FILE', review_comments_file),
                ('TRIGGER_COMMENT_FILE', trigger_comment_file),
            ]:
                if value:
                    print(f"  {'✅' if os.path.exists(value) else '❌'} {env_var}={value}")
                else:
                    print(f"  {'⚠️ ' if 'TRIGGER' in env_var else '❌'} {env_var}=<not set>")
            print()

            # ── Step 1: Add reviewer (optional) ─────────────────────────────────────────────
            skip_reviewer = os.environ.get("SKIP_REVIEWER", "false").lower() == "true"
            if not skip_reviewer and pr_metadata_file and os.path.exists(pr_metadata_file):
                print("🔧 Step 1: Adding reviewer...")
                result = self.client.add_reviewer(
                    pr_url=base_pr_url,
                    metadata_file=pr_metadata_file,
                )
                print(f"  add_reviewer result: {result}")
            else:
                print("🔧 Step 1: Skipping reviewer (set SKIP_REVIEWER=false to enable)")

            # Use pre-fetched-data as agent working directory and result file
            agent_work_dir = str(self.project_root / "pre-fetched-data")
            result_file = os.path.join(agent_work_dir, "review_result.json")
            print(f"  Agent working directory: {agent_work_dir}")
            print(f"\n📄 Review result file: {result_file}")

            # Read trigger comment body and user for quoting
            trigger_body = ""
            trigger_user = ""
            if trigger_comment_file and os.path.exists(trigger_comment_file):
                try:
                    with open(trigger_comment_file) as f:
                        trigger_data = json.load(f)
                        trigger_body = trigger_data.get('body', '')
                        trigger_user = trigger_data.get('user', {}).get('login', '')
                except (json.JSONDecodeError, IOError):
                    pass

            # Read routing decision from comment router
            greeting = ""
            routing_file = os.environ.get('ROUTING_DECISION_FILE')
            if routing_file and os.path.exists(routing_file):
                try:
                    with open(routing_file) as f:
                        routing = json.load(f)
                        greeting = routing.get('greeting', '')
                except (json.JSONDecodeError, IOError):
                    pass

            # Use greeting from routing or default
            if not greeting:
                greeting = "🤖 PR Review started... 🔍 Analyzing code changes..."

            # ── Step 3: Run agent ──────────────────────────────────────────────────────
            system_prompt = self.system_prompt_append()
            print(f"DEBUG: system_prompt length: {len(system_prompt)} chars")
            print(f"DEBUG: system_prompt preview: {system_prompt[:200]}...")

            # Use virtual file names that match what's loaded in initial_files
            # The following files are already loaded into the agent's virtual filesystem:
            # - pr_metadata.json (PR metadata from GitHub API)
            # - pr_diff.txt (PR diff from GitHub API)
            # - issue_comments.json (issue comments from GitHub API)
            # - review_comments.json (review comments from GitHub API)
            # - trigger_comment.json (trigger comment from GitHub API)
            # - review_result.json (output file - use write_file tool to write results)
            #
            # IMPORTANT: Use read_file tool to read these files
            # Example: read_file("pr_metadata.json")
            # For the cloned repository, use bash tool to run git commands or read files
            cloned_repo_name = os.path.basename(cloned_repo_path) if cloned_repo_path else ""
            virtual_file_lines = [
                "- PR metadata: /pr_metadata.json",
                "- PR diff: /pr_diff.txt",
            ]
            if cloned_repo_name:
                virtual_file_lines.append(f"- Cloned Repo: /{cloned_repo_name}")
            if issue_comments_file:
                virtual_file_lines.append("- Issue comments: /issue_comments.json")
            if review_comments_file:
                virtual_file_lines.append("- Review comments: /review_comments.json")
            if trigger_comment_file:
                virtual_file_lines.append("- Trigger comment: /trigger_comment.json")
            # Inject platform-specific files (hook for subclasses)
            virtual_file_lines.extend(self.extra_file_lines())

            # Read PR data to embed in prompt
            pr_metadata = ""
            pr_diff = ""
            issue_comments = ""
            review_comments = ""

            if pr_metadata_file and os.path.exists(pr_metadata_file):
                with open(pr_metadata_file) as f:
                    pr_metadata = f.read()[:15000]
            if pr_diff_file and os.path.exists(pr_diff_file):
                with open(pr_diff_file) as f:
                    pr_diff = f.read()[:30000]
            if issue_comments_file and os.path.exists(issue_comments_file):
                with open(issue_comments_file) as f:
                    issue_comments = f.read()[:5000]
            if review_comments_file and os.path.exists(review_comments_file):
                with open(review_comments_file) as f:
                    review_comments = f.read()[:5000]

            # Use virtual file paths for the agent's virtual filesystem
            # The agent will read/write these in the StateBackend (in-memory)
            # We use simple names that match what's pre-populated
            virtual_result_filename = "review_result.json"

            template_path = Path(__file__).parent / "review_prompt.md"

            prompt = template_path.read_text().format(
                base_pr_url=base_pr_url,
                analysis_guideline_instruction=self.analysis_guideline_instruction(),
                result_file=virtual_result_filename,
                file_locations="\n".join(virtual_file_lines),
            )

            # Embed PR data in prompt
            prompt += f"""

## PR Data (embedded):

### PR Metadata:
{pr_metadata}

### PR Diff:
{pr_diff}

### Issue Comments:
{issue_comments}

### Review Comments:
{review_comments}

Now proceed with the review following the steps above.
"""

            print(f"DEBUG: user prompt length: {len(prompt)} chars")
            print(f"DEBUG: user prompt preview: {prompt[:300]}...")

            # Use pre-fetched-data as agent working directory
            agent_work_dir = str(self.project_root / "pre-fetched-data")
            print(f"  Agent working directory: {agent_work_dir}")

            # Delete result file before agent runs (so it can create fresh)
            result_file = os.path.join(agent_work_dir, "review_result.json")
            if os.path.exists(result_file):
                os.remove(result_file)

            backend = FilesystemBackend(root_dir=agent_work_dir, virtual_mode=True)
            agent = create_deep_agent(
                model=self.llm,
                backend=backend,
                system_prompt=system_prompt,
            )

            started_comment = f"[@\"{trigger_user}\"](https://github.com/{trigger_user}) {greeting}" if trigger_user else greeting
            clean_pr_url = pr_url.split("#")[0]
            self.client.post_trigger_comment(comment_url=clean_pr_url, text=started_comment, quote_body=trigger_body)

            response = ""
            print("\n🤖 Agent Execution:\n")
            print("=" * 80)

            try:
                import signal
                def timeout_handler(signum, frame):
                    raise TimeoutError("Agent execution timed out")

                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(300)  # 5 minute timeout

                result = agent.invoke({"messages": [("user", prompt)]})

                signal.alarm(0)  # Cancel alarm

                # Get all messages to find the full response
                all_content = ""
                print(f"DEBUG: result messages count: {len(result.get('messages', []))}")
                for i, msg in enumerate(result.get('messages', [])):
                    msg_type = type(msg).__name__
                    content = msg.content if hasattr(msg, 'content') and msg.content else ""
                    if 'AIMessage' in msg_type:
                        print(f"\n=== AIMessage {i} ===\n{content[:500]}\n=== END ===")
                    elif 'ToolMessage' in msg_type:
                        print(f"\n=== ToolMessage {i} ===\n{content}\n=== END ===")
                if result.get("messages"):
                    for msg in result["messages"]:
                        if hasattr(msg, 'content') and msg.content:
                            if isinstance(msg.content, str):
                                all_content += msg.content
                            elif isinstance(msg.content, list):
                                for block in msg.content:
                                    if isinstance(block, str):
                                        all_content += block
                                    elif isinstance(block, dict) and 'text' in block:
                                        all_content += block['text']

                if all_content:
                    response = all_content

                # Check if result file exists in agent working directory
                agent_result_path = os.path.join(agent_work_dir, virtual_result_filename)
                if not os.path.exists(agent_result_path):
                    print(f"  ⚠️ Result file not found at {agent_result_path}")
                    print(f"  Files in agent_work_dir: {os.listdir(agent_work_dir) if os.path.exists(agent_work_dir) else 'dir not found'}")
            except TimeoutError as te:
                print(f"⏱️ Agent execution timed out: {te}")
                signal.alarm(0)
            except Exception as e:
                print(f"Error during agent execution: {e}")
                traceback.print_exc()

            print("\n" + "=" * 80)
            print("\n✅ Agent execution complete")
            print()

            # ── Step 4: Parse JSON result ──────────────────────────────────────────────
            print(f"📂 Reading review result JSON: {result_file}")
            if not os.path.exists(result_file):
                raise FileNotFoundError(
                    f"Agent did not write review result to {result_file}. "
                    "Check agent logs for errors."
                )

            with open(result_file) as f:
                content = f.read()

            if not content.strip():
                raise ValueError(
                    f"Agent wrote an empty result file ({result_file}). "
                    "Check agent logs — agent may have skipped the Output Review JSON step."
                )

            print(f"  📄 Result file content (first 500 chars): {content[:500]}")

            review_result = _load_json_safe(content)

            if isinstance(review_result, str):
                print(f"  ❌ JSON parsing returned string instead of dict: {review_result[:200]}")
                raise ValueError("Failed to parse review JSON - agent may not have output valid JSON")

            inline_count = len(review_result.get("inline_comments", []))
            decision = review_result.get("decision", "needs_work")
            print(f"  ✅ Parsed: {inline_count} inline comment(s), decision={decision}")

            # ── Step 5: Generate footers ───────────────────────────────────────────────
            print("\n🔧 Generating footers...")
            inline_footer = generate_footer("--inline")
            summary_footer = generate_footer("--summary")
            print(f"  ✅ Inline footer: {len(inline_footer)} chars")
            print(f"  ✅ Summary footer: {len(summary_footer)} chars")

            print("\n🚀 Posting review to GitHub...")
            self.client.post_all_comments(base_pr_url, review_result, inline_footer, summary_footer)

            print("\n✅ Review complete\n")
            return {"response": response}

        except Exception as e:
            print(f"❌ Error: {e}")
            traceback.print_exc()
            raise
