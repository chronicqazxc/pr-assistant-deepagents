"""WeatherForcast comment reply agent."""

from pathlib import Path
from ..core.base_agent.base_comment_replier import BaseCommentReplyAgent
from ..agent_config import AgentConfig


class WeatherForcastCommentReplyAgent(BaseCommentReplyAgent):

    def __init__(self, config: AgentConfig):
        super().__init__(config, agent_dir=Path(__file__).parent)
        print("WeatherForcastCommentReplyAgent initialized")

    def system_prompt_append(self) -> str:
        path = self.agent_dir / "docs" / "ROLE.md"
        soul = path.read_text() if path.exists() else ""
        return soul + "\n\nAt the very start of your response, introduce yourself in one sentence based on your identity above." if soul else ""

    def analysis_guideline_instruction(self) -> str:
        # TODO: point to your code analysis guidelines file in docs/
        return ""
