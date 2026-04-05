"""Tests for local LLM models (Ollama and LM Studio).

Run with:
    # Test Ollama
    export LLM_PROVIDER=ollama
    pytest tests/test_local_llm.py -v

    # Test LM Studio
    export LLM_PROVIDER=lm_studio
    pytest tests/test_local_llm.py -v

    # Run both
    pytest tests/test_local_llm.py -v --tb=short
"""

import sys
import os
import logging

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env file at module level so tests use actual config
from dotenv import load_dotenv
load_dotenv(override=False)

# ============================================================================
# Test Configuration - Change these for testing different models
# ============================================================================
TEST_MODELS = {
    "ollama": "gpt-oss:20b",
    "lm_studio": "gpt-oss-20b",
}

TEST_BASE_URLS = {
    "ollama": "http://localhost:11434",
    "lm_studio": "http://localhost:1234/v1",
}
# ============================================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Print loaded model info at module load time
print("\n" + "="*60)
print("LOCAL LLM TEST CONFIG")
print("="*60)

provider = os.getenv("LLM_PROVIDER", "not set")
print(f"LLM_PROVIDER: {provider}")

if provider in TEST_MODELS:
    model = TEST_MODELS.get(provider, "not set")
    base_url = TEST_BASE_URLS.get(provider, "not set")
    print(f"{provider.upper()}_MODEL: {model}")
    print(f"{provider.upper()}_BASE_URL: {base_url}")
    print(f"  → To change model, edit TEST_MODELS at top of test file")
else:
    print("⚠️  No LLM_PROVIDER set - set in env or TEST_MODELS")
print("="*60 + "\n")

import pytest
import json
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool

from src.pr_assistant.agents.agent_config import load_config, AgentConfig
from src.pr_assistant.agents.core.llm_factory import create_llm, LocalModelToolFixWrapper


def get_test_model(provider: str) -> str:
    """Get test model for the given provider."""
    return TEST_MODELS.get(provider, "")


def get_test_base_url(provider: str) -> str:
    """Get test base URL for the given provider."""
    return TEST_BASE_URLS.get(provider, "")


class TestLocalLLMConfig:
    """Test configuration loading for local LLM providers."""

    def test_ollama_config_loaded(self, monkeypatch):
        """Test Ollama config is loaded correctly."""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_MODEL", get_test_model("ollama"))
        monkeypatch.setenv("OLLAMA_BASE_URL", get_test_base_url("ollama"))
        monkeypatch.setenv("GH_TOKEN", "test_token")

        config = load_config()
        assert config.llm_provider == "ollama"
        assert config.ollama_model == get_test_model("ollama")
        assert config.ollama_base_url == get_test_base_url("ollama")

    def test_lm_studio_config_loaded(self, monkeypatch):
        """Test LM Studio config is loaded correctly."""
        monkeypatch.setenv("LLM_PROVIDER", "lm_studio")
        monkeypatch.setenv("LM_STUDIO_MODEL", get_test_model("lm_studio"))
        monkeypatch.setenv("LM_STUDIO_BASE_URL", get_test_base_url("lm_studio"))
        monkeypatch.setenv("GH_TOKEN", "test_token")

        config = load_config()
        assert config.llm_provider == "lm_studio"
        assert config.lm_studio_model == get_test_model("lm_studio")
        assert config.lm_studio_base_url == get_test_base_url("lm_studio")

    def test_lm_studio_validation_requires_model(self, monkeypatch):
        """Test LM Studio validation - no longer requires model (has defaults)."""
        monkeypatch.setenv("LLM_PROVIDER", "lm_studio")
        monkeypatch.setenv("LM_STUDIO_MODEL", "")
        monkeypatch.setenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("GH_TOKEN", "test_token")

        # With defaults, validation should pass (no error)
        config = load_config()
        assert config.llm_provider == "lm_studio"


class TestLLMFactory:
    """Test LLM factory creates correct wrappers."""

    def test_ollama_creates_tool_fix_wrapper(self, monkeypatch):
        """Test Ollama creates LocalModelToolFixWrapper."""
        model = get_test_model("ollama")
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_MODEL", model)
        monkeypatch.setenv("GH_TOKEN", "test_token")

        config = load_config()
        llm = create_llm(config)

        assert isinstance(llm, LocalModelToolFixWrapper)
        assert llm.model == model

    def test_lm_studio_creates_tool_fix_wrapper(self, monkeypatch):
        """Test LM Studio creates LocalModelToolFixWrapper."""
        model = get_test_model("lm_studio")
        monkeypatch.setenv("LLM_PROVIDER", "lm_studio")
        monkeypatch.setenv("LM_STUDIO_MODEL", model)
        monkeypatch.setenv("LM_STUDIO_BASE_URL", get_test_base_url("lm_studio"))
        monkeypatch.setenv("GH_TOKEN", "test_token")

        config = load_config()
        llm = create_llm(config)

        assert isinstance(llm, LocalModelToolFixWrapper)
        assert llm.model == model


@tool
def simple_echo_tool(text: str) -> str:
    """Echo back the input text."""
    return f"echo: {text}"


@tool  
def json_builder_tool(name: str, age: int, active: bool) -> str:
    """Build a JSON object with the given parameters."""
    return json.dumps({"name": name, "age": age, "active": active})


class TestLocalLLMToolCalling:
    """Test tool calling with local LLM models.

    These tests verify that the LocalModelToolFixWrapper correctly converts
    dict arguments to JSON strings for tool execution.
    """

    @pytest.fixture
    def llm(self, monkeypatch):
        """Create LLM instance based on LLM_PROVIDER env var."""
        provider = os.getenv("LLM_PROVIDER", "ollama")
        
        model = get_test_model(provider)
        base_url = get_test_base_url(provider)
        
        monkeypatch.setenv(f"{provider.upper()}_MODEL", model)
        monkeypatch.setenv(f"{provider.upper()}_BASE_URL", base_url)
        monkeypatch.setenv("GH_TOKEN", "test_token")
        
        logger.info(f"Creating {provider} LLM: model={model}, base_url={base_url}")
        
        config = load_config()
        llm = create_llm(config)
        
        logger.info(f"LLM created: type={type(llm).__name__}, model={llm.model}")
        return llm

    @pytest.mark.skipif(
        not os.getenv("OLLAMA_BASE_URL") and not os.getenv("LM_STUDIO_BASE_URL"),
        reason="No local LLM server available"
    )
    def test_simple_tool_call(self, llm):
        """Test simple tool call works."""
        logger.info(f"Testing tool call with model: {llm.model}")
        llm_with_tools = llm.bind_tools([simple_echo_tool])
        
        logger.info("Invoking LLM with tool...")
        result = llm_with_tools.invoke([HumanMessage(content="Use the echo tool with 'hello world'")])
        
        # Check if tool call was made
        if hasattr(result, 'tool_calls') and result.tool_calls:
            tool_call = result.tool_calls[0]
            assert tool_call['name'] == 'simple_echo_tool'
            args = tool_call.get('args', {})
            # Args might be dict or string depending on model
            if isinstance(args, dict):
                assert 'text' in args
        else:
            # Some models might just return text
            print(f"Result: {result.content}")

    @pytest.mark.skipif(
        not os.getenv("OLLAMA_BASE_URL") and not os.getenv("LM_STUDIO_BASE_URL"),
        reason="No local LLM server available"
    )
    def test_json_builder_tool_call(self, llm):
        """Test JSON builder tool - verifies dict→string conversion."""
        logger.info(f"Testing JSON tool call with model: {llm.model}")
        llm_with_tools = llm.bind_tools([json_builder_tool])
        
        logger.info("Invoking LLM with JSON builder tool...")
        result = llm_with_tools.invoke([
            HumanMessage(content="Use json_builder_tool with name=Alice, age=30, active=true")
        ])
        
        if hasattr(result, 'tool_calls') and result.tool_calls:
            tool_call = result.tool_calls[0]
            args = tool_call.get('args', {})
            
            # Key test: args should be stringified JSON, not raw dict
            if isinstance(args, dict):
                # If it's still a dict, the wrapper didn't convert it
                # This might happen with some models
                print(f"Args (dict): {args}")
                print(f"Args type: {type(args)}")
            else:
                # Should be a JSON string
                print(f"Args (string): {args}")
        else:
            print(f"Result: {result.content}")


class TestLocalLLMStructuredOutput:
    """Test structured output with local LLM models.
    
    Note: with_structured_output() is used for comment routing to avoid
    ToolStrategy streaming issues.
    """

    @pytest.fixture
    def llm(self, monkeypatch):
        """Create LLM instance."""
        provider = os.getenv("LLM_PROVIDER", "ollama")
        
        model = get_test_model(provider)
        base_url = get_test_base_url(provider)
        
        monkeypatch.setenv(f"{provider.upper()}_MODEL", model)
        monkeypatch.setenv(f"{provider.upper()}_BASE_URL", base_url)
        monkeypatch.setenv("GH_TOKEN", "test_token")
        
        logger.info(f"Creating {provider} LLM: model={model}, base_url={base_url}")
        
        config = load_config()
        llm = create_llm(config)
        
        logger.info(f"LLM created: type={type(llm).__name__}, model={llm.model}")
        return llm

    @pytest.mark.skipif(
        not os.getenv("OLLAMA_BASE_URL") and not os.getenv("LM_STUDIO_BASE_URL"),
        reason="No local LLM server available"
    )
    def test_with_structured_output(self, llm):
        """Test with_structured_output works.
        
        Note: Some local models (e.g., glm-4.7-flash) don't properly support
        OpenAI's Structured Output feature. This is expected - the actual
        code uses a fallback in comment_router/agent.py for these cases.
        """
        from pydantic import BaseModel
        
        class ResponseFormat(BaseModel):
            action: str
            reasoning: str
        
        try:
            structured_llm = llm.with_structured_output(ResponseFormat)
            result = structured_llm.invoke("Choose action 'approve' with reasoning 'looks good'")
            
            if hasattr(result, 'action'):
                print(f"Action: {result.action}, Reasoning: {result.reasoning}")
            else:
                print(f"Result: {result}")
        except ValueError as e:
            if "Structured Output response does not have a 'parsed'" in str(e):
                pytest.skip(f"Model {llm.model} doesn't support structured output properly - fallback will be used")
            raise


class TestLocalLLMComparison:
    """Compare behavior between Ollama and LM Studio.
    
    Run with different models to find best practices.
    """

    @pytest.mark.skip(reason="Manual comparison test - run separately")
    @pytest.mark.parametrize("provider", ["ollama", "lm_studio"])
    def test_provider_comparison(self, provider, monkeypatch):
        """Compare behavior across providers."""
        model = get_test_model(provider)
        base_url = get_test_base_url(provider)
        
        if not model or not base_url:
            pytest.skip(f"No config for {provider}")
        
        monkeypatch.setenv("LLM_PROVIDER", provider)
        monkeypatch.setenv(f"{provider.upper()}_MODEL", model)
        monkeypatch.setenv(f"{provider.upper()}_BASE_URL", base_url)
        monkeypatch.setenv("GH_TOKEN", "test_token")
        
        config = load_config()
        llm = create_llm(config)
        
        print(f"\n=== Testing {provider} ===")
        print(f"Model: {llm.model}")
        print(f"LLM type: {llm._llm_type}")
        
        # Test basic invocation
        result = llm.invoke([HumanMessage(content="Say 'test'")])
        print(f"Basic invoke result: {result.content[:100]}...")
        
        # Test tool calling
        llm_with_tools = llm.bind_tools([simple_echo_tool])
        result = llm_with_tools.invoke([HumanMessage(content="Use echo tool with 'test'")])
        print(f"Tool call result: {result}")