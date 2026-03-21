import os
import tomllib
from pathlib import Path


def _read_version() -> str:
    pyproject = Path(__file__).parents[4] / "pyproject.toml"
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        return data["project"]["version"]
    except Exception:
        return "unknown"


def generate_footer(footer_type: str = "--inline") -> str:
    """Generate a review comment footer.

    Args:
        footer_type: "--inline" (default, includes disclaimer) or "--summary"

    Returns:
        Footer text string.
    """
    user = (
        os.environ.get("USER_DISPLAY_NAME")
        or os.environ.get("USER_NAME")
        or "Claude Agent"
    )
    run_url = os.environ.get("RUN_URL", "")
    version = _read_version()

    repo_url = os.environ.get("PR_ASSISTANT_REPO_URL", "https://github.com/your-org/pr-assistant")
    user_link = f"[{user}](https://github.com/{user})"
    bot_line = f"🤖 [PR Assistant (v{version})]({repo_url}) • {user_link}"
    if run_url:
        bot_line += f" • [Run Log]({run_url})"

    if footer_type == "--summary":
        return f"---\n{bot_line}"
    else:
        return f"---\n**:warning: Verify AI suggestions before implementation**\n{bot_line}"
