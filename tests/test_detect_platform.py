"""Tests for _detect_platform routing logic in main.py"""

import pytest
from unittest.mock import patch
from pr_assistant.main import _detect_platform

MOCK_REGISTRY = [
    {
        "url_patterns": ["WeatherForcast"],
        "reviewer_class": "pr_assistant.agents.weather_forcast.reviewer_agent.WeatherForcastCodeReviewAgent",
        "replier_class": "pr_assistant.agents.weather_forcast.comment_replier_agent.WeatherForcastCommentReplyAgent",
    },
]


@pytest.fixture(autouse=True)
def mock_registry():
    with patch("pr_assistant.main._load_registry", return_value=MOCK_REGISTRY):
        yield


class TestDetectPlatform:
    def test_matches_github_pr_url(self):
        entry = _detect_platform(
            "https://github.com/chronicqazxc/WeatherForcast/pull/33"
        )
        assert "WeatherForcast" in entry["url_patterns"]

    def test_matches_github_pr_url_with_issuecomment(self):
        entry = _detect_platform(
            "https://github.com/chronicqazxc/WeatherForcast/pull/33#issuecomment-4103252065"
        )
        assert "WeatherForcast" in entry["url_patterns"]

    def test_matches_github_pr_url_with_discussion(self):
        entry = _detect_platform(
            "https://github.com/chronicqazxc/WeatherForcast/pull/33#discussion_r1234567890"
        )
        assert "WeatherForcast" in entry["url_patterns"]

    def test_returns_correct_reviewer_class(self):
        entry = _detect_platform(
            "https://github.com/chronicqazxc/WeatherForcast/pull/33"
        )
        assert entry["reviewer_class"] == "pr_assistant.agents.weather_forcast.reviewer_agent.WeatherForcastCodeReviewAgent"

    def test_raises_for_unknown_repo(self):
        with pytest.raises(ValueError, match="Cannot detect platform from URL"):
            _detect_platform(
                "https://github.com/unknown/repo/pull/1"
            )

    def test_raises_lists_supported_repos(self):
        with pytest.raises(ValueError) as exc_info:
            _detect_platform("https://github.com/X/unknown/pull/1")
        assert "WeatherForcast" in str(exc_info.value)
