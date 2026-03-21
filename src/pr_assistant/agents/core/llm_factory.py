"""LLM Factory - Create LangChain chat models based on provider configuration."""

from langchain.chat_models import init_chat_model
from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Any

from ..agent_config import AgentConfig

# Ollama context length options
OLLAMA_CONTEXT_LENGTHS = {
    "4k": 4096,
    "8k": 8192,
    "16k": 16384,
    "32k": 32768,
    "64k": 65536,
    "128k": 131072,
    "256k": 262144,
}

# Current Ollama settings - change these to test
OLLAMA_SETTINGS = {
    "context_length": "128k",  # Options: 4k, 8k, 16k, 32k, 64k, 128k, 256k
    "temperature": 0,
    "num_predict": -2,  # -1 = infinite, -2 = fill context
    "reasoning": False
}


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
        ctx_length = OLLAMA_CONTEXT_LENGTHS.get(
            OLLAMA_SETTINGS["context_length"],
            OLLAMA_SETTINGS["context_length"]
        )
        return ChatOllama(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            temperature=OLLAMA_SETTINGS["temperature"],
            num_ctx=ctx_length,
            num_predict=OLLAMA_SETTINGS["num_predict"],
        )
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
            max_output_tokens=OLLAMA_CONTEXT_LENGTHS.get("128k"),  # High limit
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: ollama, anthropic, gemini")
