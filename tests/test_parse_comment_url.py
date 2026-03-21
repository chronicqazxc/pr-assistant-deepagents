import pytest
from src.pr_assistant.agents.core.base_agent.base_comment_replier import BaseCommentReplyAgent


class TestAgent(BaseCommentReplyAgent):
    """Test wrapper for BaseCommentReplyAgent."""
    pass


@pytest.fixture
def agent():
    return TestAgent.__new__(TestAgent)


class TestParseCommentUrl:
    """Unit tests for _parse_comment_url method."""

    def test_issue_comment(self, agent):
        """Test parsing issue comment URL."""
        url = "https://github.com/chronicqazxc/WeatherForcast/pull/24#issuecomment-4067291856"
        result = agent._parse_comment_url(url)
        
        assert result['comment_type'] == 'issue'
        assert result['comment_id'] == '4067291856'
        assert result['owner'] == 'chronicqazxc'
        assert result['repo'] == 'WeatherForcast'
        assert result['pr_number'] == '24'
        assert '/pull/24' in result['pr_url']

    def test_discussion_comment(self, agent):
        """Test parsing discussion comment URL."""
        url = "https://github.com/chronicqazxc/WeatherForcast/pull/24#discussion_r2936867746"
        result = agent._parse_comment_url(url)
        
        assert result['comment_type'] == 'discussion'
        assert result['comment_id'] == '2936867746'
        assert result['owner'] == 'chronicqazxc'
        assert result['repo'] == 'WeatherForcast'
        assert result['pr_number'] == '24'

    def test_issue_comment_large_id(self, agent):
        """Test issue comment with large ID."""
        url = "https://github.com/org/repo/pull/123#issuecomment-9999999999"
        result = agent._parse_comment_url(url)
        
        assert result['comment_type'] == 'issue'
        assert result['comment_id'] == '9999999999'

    def test_discussion_comment_large_id(self, agent):
        """Test discussion comment with large ID."""
        url = "https://github.com/org/repo/pull/456#discussion_r1234567890"
        result = agent._parse_comment_url(url)
        
        assert result['comment_type'] == 'discussion'
        assert result['comment_id'] == '1234567890'

    def test_invalid_url_raises_error(self, agent):
        """Test invalid URL raises ValueError."""
        url = "https://notgithub.com/user/repo/pull/123"
        with pytest.raises(ValueError, match="Invalid comment URL"):
            agent._parse_comment_url(url)

    def test_invalid_url_no_anchor(self, agent):
        """Test URL without discussion or issuecomment anchor."""
        url = "https://github.com/user/repo/pull/123"
        with pytest.raises(ValueError, match="Invalid comment URL"):
            agent._parse_comment_url(url)
