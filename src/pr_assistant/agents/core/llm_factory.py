"""LLM Factory - Create LangChain chat models based on provider configuration."""

import json
from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Any
from langchain_core.language_models import BaseChatModel

from ..agent_config import AgentConfig


# =============================================================================
# LM Studio Context Length Issue
# =============================================================================
#
# IMPORTANT: LM Studio models must be loaded with the correct context length
# BEFORE running the app. The OpenAI-compatible API cannot set context length
# at inference time - it's a load-time parameter.
#
# To set context length:
# - Via LM Studio UI: Load model → Settings → Context Length (set to 128k)
# - Via CLI: lms load <model> --context-length 131072
#
# If model is loaded without sufficient context, you'll see error:
# "The number of tokens to keep from the initial prompt is greater than the context length"
# =============================================================================


# =============================================================================
# Local Model Tool Fix Wrapper
# =============================================================================
#
# Both Ollama and LM Studio (local models) have known issues with LangChain/LangGraph:
#
# 1. response_format=ToolStrategy doesn't work:
#    - ToolStrategy uses streaming internally, which breaks with local models
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
# Tested with:
# - Ollama: gpt-oss:20b model
# - LM Studio: gpt-oss-20b model (with 128k context)
#
# See also: test files in this directory for detailed tests
# =============================================================================

class LocalModelToolFixWrapper(BaseChatModel):
    """Wrapper that fixes local model dict arguments in tool calls.

    This wrapper ONLY fixes dict→JSON string conversion in tool calls.
    All other settings (temperature, max_tokens, streaming, etc.) are
    delegated to the wrapped LLM via __getattr__.
    
    The wrapped LLM (ChatOllama or ChatOpenAI) is initialized with config
    values from agent_config.py, so settings like temperature, max_tokens,
    etc. come from there.
    """

    llm: BaseChatModel

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "local_model"

    def bind_tools(self, *args, **kwargs):
        """Wrap bind_tools to fix dict→JSON in tool call arguments."""
        original_bound = self.llm.bind_tools(*args, **kwargs)
        return _LocalModelBoundTools(original_bound)

    def with_structured_output(self, schema, **kwargs):
        return self.llm.with_structured_output(schema, **kwargs)

    def _generate(self, messages, stop=None, **kwargs):
        """Delegate to wrapped LLM - config values are used."""
        return self.llm._generate(messages, stop=stop, **kwargs)

    def generate(self, messages, stop=None, **kwargs):
        """Delegate to wrapped LLM - config values are used."""
        return self.llm.generate(messages, stop=stop, **kwargs)

    def __getattr__(self, name: str):
        """Delegate all other attributes to the wrapped LLM."""
        return getattr(self.llm, name)


class _LocalModelBoundTools:
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
            temperature=config.ollama_temperature,
            num_ctx=config.ollama_context_length,
            num_predict=config.ollama_num_predict,
            reasoning=config.ollama_disable_reasoning
        )
        return LocalModelToolFixWrapper(llm=base_llm)
    elif provider == "anthropic":
        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for anthropic provider")
        return ChatAnthropic(
            api_key=config.anthropic_api_key,
            model=config.anthropic_model,
        )
    elif provider == "gemini":
        if not config.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required for gemini provider")
        return ChatGoogleGenerativeAI(
            model=config.gemini_model,
            google_api_key=config.google_api_key,
            timeout=600,
            temperature=config.gemini_temperature,
            thinking_budget=config.gemini_thinking_budget,
            max_output_tokens=config.gemini_max_output_tokens,
        )
    elif provider == "lm_studio":
        # Load model with configured context length using LM Studio SDK
        # Only load if not already loaded (to avoid duplicate model instances)
        import lmstudio as lms

        try:
            client = lms.get_default_client()
            loaded_models = client.llm.list_loaded()
            model_already_loaded = any(m.identifier == config.lm_studio_model for m in loaded_models)

            load_config = {
                "contextLength": config.lm_studio_context_length,
                "gpu": {"ratio": config.lm_studio_gpu_offload},
                "reasoning_parsing": "disabled",  # Always disabled for cleaner output
            }

            if model_already_loaded:
                print(f"[LM Studio] Model '{config.lm_studio_model}' already loaded, using existing instance", flush=True)
            else:
                print(f"[LM Studio] Loading model '{config.lm_studio_model}' with context_length={config.lm_studio_context_length}...", flush=True)
                lm_model = lms.llm(config.lm_studio_model, config=load_config)
                actual_context = lm_model.get_context_length()
                print(f"[LM Studio] Model loaded with context length: {actual_context}", flush=True)
        except Exception as e:
            print(f"[LM Studio] SDK load failed: {e}", flush=True)
            print(f"[LM Studio] Will use existing loaded model via API", flush=True)

        # Create ChatOpenAI client for the API
        from langchain_openai import ChatOpenAI
        base_llm = ChatOpenAI(
            model_name=config.lm_studio_model,
            openai_api_base=config.lm_studio_base_url,
            openai_api_key="not-needed",
            temperature=config.lm_studio_temperature,
            max_tokens=config.lm_studio_max_tokens,
            streaming=False,
        )
        return LocalModelToolFixWrapper(llm=base_llm)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: ollama, lm_studio, anthropic, gemini")