"""LLM Factory - Create LangChain chat models based on provider configuration."""

import json
from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Any, List
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from ..agent_config import AgentConfig

# Context length options (generic, used by all providers)
CONTEXT_LENGTHS = {
    "4k": 4096,
    "8k": 8192,
    "16k": 16384,
    "32k": 32768,
    "64k": 65536,
    "128k": 131072,
    "256k": 262144,
}

# Default Ollama settings
OLLAMA_SETTINGS = {
    "context_length": CONTEXT_LENGTHS["128k"],
    "temperature": 0,
    "num_predict": -2,
    "reasoning": False
}


# =============================================================================
# Ollama-specific fixes
# =============================================================================
#
# Ollama models have two known issues with LangChain/LangGraph:
#
# 1. response_format=ToolStrategy doesn't work:
#    - ToolStrategy uses streaming internally, which breaks with Ollama
#    - Fix: Use llm.with_structured_output() instead (done in comment_router/agent.py)
#
# 2. Tool arguments sent as dict instead of string:
#    - When the model wants to write JSON, it sends {'content': {...}} instead of
#      {'content': '{"json": "string"}'} (a string). This causes tool execution errors
#      because tools like write_file expect string parameters, not dicts.
#    - Fix: This wrapper post-processes tool calls to convert dict values to JSON strings
#
# The write_file tool being used is DeepAgents built-in tool (deepagents/middleware/filesystem.py),
# which expects 'content' parameter to be a string. Our wrapper converts dict to JSON string
# before the tool receives it.
#
# Tested with: gpt-oss:20b model (local Ollama)
#
# NOTE: These issues have been verified with local Ollama models. For Ollama Cloud,
# the same behavior is expected since both use the same langchain_ollama library.
# If you use Ollama Cloud and encounter issues, please verify and report.
#
# See also: test files in this directory for detailed tests
# =============================================================================

class OllamaToolFixWrapper(BaseChatModel):
    """Wrapper that fixes Ollama dict arguments in tool calls.

    Ollama models sometimes send dict objects instead of JSON strings for
    complex tool arguments. This wrapper post-processes tool calls to
    convert dict values to JSON strings.
    """

    llm: ChatOllama

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self.llm.model

    def bind_tools(self, tools: List[BaseTool], **kwargs):
        original_bound = self.llm.bind_tools(tools, **kwargs)
        return _OllamaBoundTools(original_bound)

    def with_structured_output(self, schema):
        return self.llm.with_structured_output(schema)

    def _generate(self, messages, stop=None, **kwargs):
        return self.llm._generate(messages, stop=stop, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self.llm, name)


class _OllamaBoundTools:
    """Bound LLM that fixes dict arguments in tool calls."""

    def __init__(self, bound_llm: Any):
        self.bound_llm = bound_llm

    def invoke(self, input):
        result = self.bound_llm.invoke(input)

        if hasattr(result, 'tool_calls') and result.tool_calls:
            for tc in result.tool_calls:
                args = tc.get('args', {})
                fixed_args = {}
                for key, value in args.items():
                    if isinstance(value, dict):
                        fixed_args[key] = json.dumps(value, indent=2)
                    elif isinstance(value, list):
                        fixed_args[key] = [
                            json.dumps(v, indent=2) if isinstance(v, dict) else v
                            for v in value
                        ]
                    else:
                        fixed_args[key] = value
                tc['args'] = fixed_args

        return result


def create_llm(config: AgentConfig) -> Any:
    """Create LangChain chat model based on LLM_PROVIDER config.

    Args:
        config: AgentConfig with provider settings

    Returns:
        LangChain chat model instance

    Raises:
        ValueError: If provider is unknown or required credentials are missing
    """
    provider = config.llm_provider.lower()

    if provider == "ollama":
        base_llm = ChatOllama(
            validate_model_on_init=True,
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            temperature=OLLAMA_SETTINGS["temperature"],
            num_ctx=OLLAMA_SETTINGS["context_length"],
            num_predict=OLLAMA_SETTINGS["num_predict"],
            reasoning=OLLAMA_SETTINGS["reasoning"]
        )
        return OllamaToolFixWrapper(llm=base_llm)
    elif provider == "anthropic":
        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for anthropic provider")
        return ChatAnthropic(
            api_key=config.anthropic_api_key,
            model=config.anthropic_model,
        )
    elif provider == "gemini":
        if not config.gemini_api_key:
            raise ValueError("GOOGLE_API_KEY is required for gemini provider")
        return ChatGoogleGenerativeAI(
            model=config.gemini_model,
            google_api_key=config.gemini_api_key,
            timeout=600,
            temperature=0,
            thinking_budget=0, # Gemini 2.5: 0 (off), -1 (dynamic), or a positive integer (token limit)
            max_output_tokens=CONTEXT_LENGTHS["128k"],
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: ollama, anthropic, gemini")
