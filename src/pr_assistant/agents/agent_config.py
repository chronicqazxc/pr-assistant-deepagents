"""Configuration management for PR Assistant"""

from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv


# =============================================================================
# Context length options (easy to reference and change)
# =============================================================================
CONTEXT_LENGTHS = {
    "4k": 4096,
    "8k": 8192,
    "16k": 16384,
    "32k": 32768,
    "64k": 65536,
    "128k": 131072,
    "256k": 262144,
}


# =============================================================================
# Internal default settings (not in .env - change in code if needed)
# =============================================================================
# These have sensible defaults and typically don't need to be configured by users.

# Ollama defaults
OLLAMA_DEFAULTS = {
    "temperature": 0,
    "num_predict": -2,
    "context_length": CONTEXT_LENGTHS["128k"],
    "disable_reasoning": True,
}

# LM Studio defaults
LM_STUDIO_DEFAULTS = {
    "temperature": 0,
    "max_tokens": 4096,
    "context_length": CONTEXT_LENGTHS["128k"],
    "gpu_offload": "max",
}

# Gemini defaults
GEMINI_DEFAULTS = {
    "temperature": 0,
    "thinking_budget": 0,
    "max_output_tokens": CONTEXT_LENGTHS["128k"],
}


class AgentConfig(BaseModel):
    """Configuration for the code review agent.

    User-facing settings come from .env (or env vars).
    Internal defaults are set in the class below.
    """

    # =========================================================================
    # User-facing settings (from .env)
    # =========================================================================

    # LLM Provider
    llm_provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))

    # Ollama (local)
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gpt-oss:20b"))

    # LM Studio (local)
    lm_studio_base_url: str = Field(default_factory=lambda: os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"))
    lm_studio_model: str = Field(default_factory=lambda: os.getenv("LM_STUDIO_MODEL", ""))

    # Anthropic (remote)
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # Google Gemini (remote)
    google_api_key: str = Field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    # GitHub
    github_token: str = Field(default_factory=lambda: os.getenv("GH_TOKEN", ""))
    github_base_url: str = Field(default_factory=lambda: os.getenv("GITHUB_BASE_URL", "https://api.github.com"))

    # =========================================================================
    # Internal defaults (not from env - change in code if needed)
    # =========================================================================

    # Ollama settings
    ollama_temperature: float = OLLAMA_DEFAULTS["temperature"]
    ollama_num_predict: int = OLLAMA_DEFAULTS["num_predict"]
    ollama_context_length: int = OLLAMA_DEFAULTS["context_length"]
    ollama_disable_reasoning: bool = OLLAMA_DEFAULTS["disable_reasoning"]

    # LM Studio settings
    lm_studio_temperature: float = LM_STUDIO_DEFAULTS["temperature"]
    lm_studio_max_tokens: int = LM_STUDIO_DEFAULTS["max_tokens"]
    lm_studio_context_length: int = LM_STUDIO_DEFAULTS["context_length"]
    lm_studio_gpu_offload: str = LM_STUDIO_DEFAULTS["gpu_offload"]

    # Gemini settings
    gemini_temperature: float = GEMINI_DEFAULTS["temperature"]
    gemini_thinking_budget: int = GEMINI_DEFAULTS["thinking_budget"]
    gemini_max_output_tokens: int = GEMINI_DEFAULTS["max_output_tokens"]

    def validate_required_fields(self) -> None:
        """Validate that required configuration fields are set.

        Only validates fields without defaults - fields with defaults
        (like model names, base URLs) are optional and have sensible fallbacks.
        """
        # Remote providers require API keys (no defaults)
        if self.llm_provider == "anthropic":
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        elif self.llm_provider == "gemini":
            if not self.google_api_key:
                raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=gemini")

        # Local providers (ollama, lm_studio) have defaults - no validation needed
        # GitHub token is always required (no default)
        if not self.github_token:
            raise ValueError("GH_TOKEN is required")


def load_config() -> AgentConfig:
    """Load configuration from environment variables.

    Loads .env file if it exists, but existing environment variables take precedence.
    - Development: Uses .env file
    - CI/CD: env vars already exported by CI secrets, .env is a no-op
    """
    load_dotenv(override=False)

    config = AgentConfig()
    config.validate_required_fields()
    return config
