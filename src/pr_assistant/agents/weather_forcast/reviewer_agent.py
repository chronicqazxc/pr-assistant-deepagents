"""WeatherForcast code review agent."""

from pathlib import Path
from ..core.base_agent.base_reviewer import BaseReviewAgent
from ..agent_config import AgentConfig


class WeatherForcastCodeReviewAgent(BaseReviewAgent):

    def __init__(self, config: AgentConfig):
        super().__init__(config, agent_dir=Path(__file__).parent)
        print("WeatherForcastCodeReviewAgent initialized")

    def system_prompt_append(self) -> str:
        path = self.agent_dir / "docs" / "ROLE.md"
        soul = path.read_text() if path.exists() else ""
        return soul + "\n\nAt the very start of your response, introduce yourself in one sentence based on your identity above." if soul else ""

    def analysis_guideline_instruction(self) -> str:
        guidelines_path = self.agent_dir / "docs" / "REVIEW_GUIDELINES.md"
        guidelines_content = guidelines_path.read_text() if guidelines_path.exists() else ""
        return f"## Review Guidelines\n{guidelines_content}" if guidelines_content else ""
