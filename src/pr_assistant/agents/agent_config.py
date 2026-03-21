"""Configuration management for PR Assistant"""

from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv


class AgentConfig(BaseModel):
    """Configuration for the code review agent"""

    # LLM Provider selection
    llm_provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))

    # Ollama (local)
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gpt-oss:20b"))

    # Anthropic (remote)
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # Google Gemini (remote)
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    # GitHub Integration
    github_token: str = Field(default_factory=lambda: os.getenv("GH_TOKEN", ""))
    github_base_url: str = Field(default_factory=lambda: os.getenv("GITHUB_BASE_URL", "https://api.github.com"))

    def validate_required_fields(self) -> None:
        """Validate that required configuration fields are set"""
        if self.llm_provider == "ollama":
            pass
        elif self.llm_provider == "anthropic":
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        elif self.llm_provider == "gemini":
            if not self.gemini_api_key:
                raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=gemini")

        if not self.github_token:
            raise ValueError("GH_TOKEN is required")


def load_config() -> AgentConfig:
    """Load configuration from environment variables

    Loads .env file if it exists, but existing environment variables take precedence.
    - Development: Uses .env file
    - CI/CD: env vars already exported by CI secrets, .env is a no-op
    """
    load_dotenv(override=False)

    config = AgentConfig()
    config.validate_required_fields()
    return config
