"""CLI entry point for PR Assistant - minimal version"""

import asyncio
import importlib
import json
import os
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from .agents.agent_config import load_config
from .agents.core.comment_router.agent import CommentRouter

console = Console()


@click.group()
@click.version_option(version="0.32.0")
def cli():
    """PR Assistant - Autonomous code review agent powered by Claude"""
    pass


def _load_agent_class(dotted_path: str):
    """Dynamically load an agent class from a dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


_registry_cache = None

def _get_registry() -> list:
    """Get cached agent registry from src/agents/registry.json."""
    global _registry_cache
    if _registry_cache is None:
        registry_path = os.path.join(os.path.dirname(__file__), "agents", "registry.json")
        with open(registry_path) as f:
            _registry_cache = json.load(f)["agents"]
    return _registry_cache


def _detect_platform(url: str) -> dict:
    """Detect platform entry from registry by matching URL patterns.

    Args:
        url: GitHub PR URL or comment URL

    Returns:
        Registry entry dict with platform, url_patterns, reviewer_class, replier_class

    Raises:
        ValueError: If no registry entry matches the URL
    """
    for entry in _get_registry():
        if any(pattern in url for pattern in entry["url_patterns"]):
            return entry

    supported = "\n".join(
        f"  - {', '.join(e['url_patterns'])}"
        for e in _get_registry()
    )
    raise ValueError(
        f"Cannot detect platform from URL: {url}\n"
        f"Supported repositories:\n{supported}"
    )


@cli.command()
@click.argument("pr_url")
@click.option(
    "--user",
    default=None,
    help="Username who triggered the review"
)
def review_pr(pr_url: str, user: str):
    """Review a pull request from GitHub

    Example:
        pr-assistant review-pr "https://github.com/owner/repo/pull/123"

    Note: Set USER_NAME environment variable to customize footer
        export USER_NAME="Wayne"
        pr-assistant review-pr "https://..."
    """
    # Set USER_NAME environment variable if provided
    if user:
        os.environ['USER_NAME'] = user

    asyncio.run(_review_pr_async(pr_url))


async def _review_pr_async(pr_url: str):
    """Async implementation of PR review"""
    try:
        # Detect platform from URL
        try:
            entry = _detect_platform(pr_url)
        except ValueError as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            raise click.exceptions.Exit(1)

        platform = entry["url_patterns"][0]
        console.print(Panel.fit(
            f"[bold cyan]Starting Review[/bold cyan]\n\nPlatform: {platform.upper()}\nPR: {pr_url}",
            border_style="cyan"
        ))

        # Load configuration
        config = load_config()

        # Initialize agent dynamically from registry
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Initializing {platform.upper()} agent...", total=None)

            AgentClass = _load_agent_class(entry["reviewer_class"])
            agent = AgentClass(config)

            progress.update(task, description="Reviewing PR...")
            await agent.review_pr(pr_url)

            progress.update(task, description="Complete!", completed=True)

        print("\n" + "=" * 80)
        print("✅ Review completed successfully! Comments posted to PR.")
        print("=" * 80)

    except Exception as e:
        # Use plain print to avoid Rich Console buffer overflow during error handling
        print(f"\n{'=' * 80}")
        print(f"❌ Error: {e}")
        print("=" * 80)
        raise click.exceptions.Exit(1)


@cli.command()
@click.argument("comment_text")
@click.option("--pr-url", required=True, help="GitHub PR URL")
@click.option("--comment-id", default=None, help="Comment ID (for reply mode)")
@click.option("--user", default=None, help="Username who triggered")
def route_comment(comment_text: str, pr_url: str, comment_id: str, user: str):
    """Route comment to appropriate agent(s) based on user intention

    Example:
        pr-assistant route-comment "please-code-review" --pr-url "https://..."
        pr-assistant route-comment "Why use weak? please-reply-me" --pr-url "https://..." --comment-id "2275795" --user "yuhan.a.hsiao"
    """
    asyncio.run(_route_comment_async(comment_text, pr_url, comment_id, user))


async def _route_comment_async(comment_text: str, pr_url: str, comment_id: str, user: str):
    """Async implementation of comment routing"""
    try:
        display_comment = comment_text[:100] + ("..." if len(comment_text) > 100 else "")
        console.print(Panel.fit(
            f"[bold cyan]Routing Comment[/bold cyan]\n\nComment: {display_comment}\nPR: {pr_url}",
            border_style="cyan"
        ))

        # Set USER_NAME environment variable if provided
        if user:
            os.environ['USER_NAME'] = user
            console.print(f"[dim]User: {user}[/dim]\n")

        # Load configuration
        config = load_config()

        # Initialize router (instantaneous - no spinner needed)
        print("Initializing comment router...\n", flush=True)
        router = CommentRouter(config)

        # Route comment (subprocess will have its own spinner)
        result = await router.route_comment(comment_text, pr_url, comment_id, user)

        # Display results
        print("\n" + "=" * 80)
        print("✅ Routing completed successfully!")
        print(f"Decision: {result['routing_decision']}")
        print(f"Invoked agents: {[r['agent'] for r in result['results']]}")
        print("=" * 80)

    except Exception as e:
        print(f"\n{'=' * 80}")
        print(f"❌ Error: {e}")
        print("=" * 80)
        raise click.exceptions.Exit(1)


@cli.command()
@click.argument("comment_url")
@click.option(
    "--user",
    default=None,
    help="Username who triggered the reply"
)
def reply_pr_comment(comment_url: str, user: str):
    """Reply to a PR comment thread

    Example:
        pr-assistant reply-pr-comment "https://github.com/owner/repo/pull/7288#discussion_comment_2275795"

    With user attribution:
        pr-assistant reply-pr-comment "https://..." --user "yuhan.a.hsiao"
    """
    asyncio.run(_reply_pr_comment_async(comment_url, user))


async def _reply_pr_comment_async(comment_url: str, user: str):
    """Async implementation of comment reply"""
    try:
        # Detect platform from URL
        try:
            entry = _detect_platform(comment_url)
        except ValueError as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            raise click.exceptions.Exit(1)
        platform = entry["url_patterns"][0]
        console.print(Panel.fit(
            f"[bold cyan]Replying to Comment[/bold cyan]\n\nPlatform: {platform.upper()}\nComment URL: {comment_url}",
            border_style="cyan"
        ))

        # Set USER_NAME environment variable if provided
        if user:
            os.environ['USER_NAME'] = user
            console.print(f"[dim]User: {user}[/dim]\n")

        # Load configuration
        config = load_config()

        # Initialize agent dynamically from registry
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Initializing {platform.upper()} comment reply agent...", total=None)

            AgentClass = _load_agent_class(entry["replier_class"])
            agent = AgentClass(config)

            progress.update(task, description=f"Replying to comment... {comment_url}")
            await agent.reply_to_comment(comment_url)

            progress.update(task, description="Complete!", completed=True)

        # Display success message (full output already streamed during execution)
        # Use plain print to avoid Rich Console buffer overflow
        print("\n" + "=" * 80)
        print("✅ Reply posted successfully! Check the comment thread on GitHub.")
        print("=" * 80)

    except Exception as e:
        # Use plain print to avoid Rich Console buffer overflow during error handling
        print(f"\n{'=' * 80}")
        print(f"❌ Error: {e}")
        print("=" * 80)
        raise click.exceptions.Exit(1)


if __name__ == "__main__":
    cli()
