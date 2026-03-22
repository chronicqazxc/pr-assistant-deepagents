"""GitHub write operations client for posting comments and updating PR status."""

import os
import re
import json
import requests
from typing import Dict, Any, Optional


class GitHubWriteClient:
    """Client for GitHub write operations: add reviewer, post comments, update PR status."""

    def __init__(self, github_token: str, base_url: str = "https://api.github.com"):
        self.github_token = github_token
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def get_username_from_token(token: str, base_url: str = "https://api.github.com") -> str:
        """Get GitHub username from token.

        Args:
            token: GitHub token (PAT or GITHUB_TOKEN)
            base_url: GitHub API base URL

        Returns:
            Username (login) of the authenticated user
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        response = requests.get(f"{base_url.rstrip('/')}/user", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get("login", "")
        return ""

    def _parse_pr_url(self, pr_url: str):
        """Parse owner, repo, and PR number from a GitHub PR URL.

        Args:
            pr_url: Full GitHub PR URL

        Returns:
            Tuple of (owner, repo, pr_number)

        Raises:
            ValueError: If URL does not match expected format
        """
        pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
        match = re.search(pattern, pr_url)
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
        return match.group(1), match.group(2), int(match.group(3))

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PR-Assistant/2.0",
        }

    def _get_pr_head_sha(self, pr_url: str) -> str:
        """Get the head commit SHA for a PR.
        
        Args:
            pr_url: GitHub PR URL
            
        Returns:
            Commit SHA string
        """
        owner, repo, pr_number = self._parse_pr_url(pr_url)
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        response = requests.get(url, headers=self._headers(), timeout=30)
        if response.status_code == 200:
            return response.json().get("head", {}).get("sha", "")
        return ""

    def add_reviewer(
        self,
        pr_url: str,
        metadata_file: str = None,
        username: str = None,
    ) -> Dict[str, Any]:
        """Add a reviewer to the PR.

        Args:
            pr_url: GitHub PR URL
            metadata_file: Path to pre-fetched PR metadata JSON file (optional, for compatibility)
            username: GitHub username to add as reviewer

        Returns:
            Dict with keys: status_code, skipped (bool), message
        """
        owner, repo, pr_number = self._parse_pr_url(pr_url)

        if not username:
            username = os.environ.get("PR_REVIEWER_BOT", "DangerCI001")

        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/requested_reviewers"
        
        payload = {"reviewers": [username]}

        print(f"  🛠️ Adding reviewer {username} to PR #{pr_number}")
        print(f"  📤 Payload: {payload}")
        response = requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=30,
        )

        print(f"  📥 Response: {response.status_code} - {response.text[:200]}")
        
        if response.status_code == 201:
            print(f"  ✅ Reviewer added: HTTP 201")
            return {"status_code": 201, "skipped": False, "message": "Reviewer added"}
        elif response.status_code == 422:
            print(f"  ⚠️ Already a reviewer or invalid user — skipping")
            return {"status_code": 422, "skipped": True, "message": "Already a reviewer or invalid user"}
        else:
            msg = f"HTTP {response.status_code}: {response.text[:200]}"
            print(f"  ❌ Failed to add reviewer: {msg}")
            return {"status_code": response.status_code, "skipped": False, "message": msg}

    def post_comment(
        self,
        pr_url: str,
        text: str,
        file_path: Optional[str] = None,
        line_number: Optional[int] = None,
        line_type: str = "ADDED",
    ) -> Dict[str, Any]:
        """Post a regular (non-blocking) comment to a PR.

        If file_path and line_number are provided, posts an inline comment (PR review comment).
        Otherwise posts a general PR comment (issue comment).

        Args:
            pr_url: GitHub PR URL
            text: Comment text (markdown supported)
            file_path: File path for inline comment (optional)
            line_number: Line number for inline comment (optional)
            line_type: ADDED, REMOVED, or CONTEXT (default: ADDED)

        Returns:
            Dict with status_code and response data
        """
        owner, repo, pr_number = self._parse_pr_url(pr_url)

        if file_path and line_number is not None:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
            commit_id = self._get_pr_head_sha(pr_url)
            if not commit_id:
                print(f"  ⚠️ Could not get PR head SHA, skipping inline comment")
                return {"status_code": 400, "data": {}}
            side = "RIGHT" if line_type == "ADDED" else "LEFT"

            payload = {
                "body": text,
                "commit_id": commit_id,
                "path": file_path,
                "line": line_number,
                "side": side,
            }

            response = requests.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
        else:
            url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
            payload = {"body": text}

            response = requests.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=30,
            )

        if response.status_code == 201:
            comment_id = response.json().get("id", "?")
            location = f"{file_path}:{line_number}" if file_path else "general"
            print(f"  ✅ Comment posted (id={comment_id}) at {location}")
        else:
            print(f"  ❌ Failed to post comment: HTTP {response.status_code} — {response.text[:200]}")

        return {"status_code": response.status_code, "data": response.json() if response.content else {}}

    def post_reply(
        self,
        pr_url: str,
        parent_comment_id: int,
        text: str,
    ) -> Dict[str, Any]:
        """Post a threaded reply to an existing comment.

        Args:
            pr_url: GitHub PR URL
            parent_comment_id: Numeric ID of the comment to reply to
            text: Reply text (markdown supported)

        Returns:
            Dict with status_code and response data
        """
        owner, repo, pr_number = self._parse_pr_url(pr_url)

        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/comments"

        payload = {
            "body": text,
            "in_reply_to": parent_comment_id,
        }

        response = requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=30,
        )

        if response.status_code == 201:
            reply_id = response.json().get("id", "?")
            print(f"  ✅ Reply posted (id={reply_id}) under comment {parent_comment_id}")
        else:
            print(f"  ❌ Failed to post reply: HTTP {response.status_code} — {response.text[:200]}")

        return {"status_code": response.status_code, "data": response.json() if response.content else {}}

    def post_all_comments(
        self,
        base_pr_url: str,
        review_result: dict,
        inline_footer: str,
        summary_footer: str,
    ) -> None:
        """Post all inline comments, summary, and update PR status from a review result."""
        inline_comments = review_result.get("inline_comments", [])
        summary = review_result.get("summary", "")
        decision = review_result.get("decision", "needs_work")

        print(f"\n📝 Posting {len(inline_comments)} inline comment(s)...")

        for i, c in enumerate(inline_comments, 1):
            file_path = c.get("file_path", "")
            line_number = c.get("line_number")
            line_type = c.get("line_type", "ADDED")
            severity = c.get("severity", "MINOR")
            comment_text = c.get("comment", "")

            full_comment = comment_text + "\n\n" + inline_footer if inline_footer else comment_text

            print(f"  [{i}/{len(inline_comments)}] {severity} at {file_path}:{line_number}")

            self.post_comment(
                pr_url=base_pr_url,
                text=full_comment,
                file_path=file_path,
                line_number=line_number,
                line_type=line_type,
            )

        # Post summary only as review body, not as separate comment
        # The review body will appear in the PR review timeline
        state = "APPROVE" if decision == "approve" else "REQUEST_CHANGES"
        print(f"\n🔄 Submitting PR review with state: {state}...")
        
        # Include summary in review body (with footer)
        full_summary = summary + "\n\n" + summary_footer if summary_footer else summary
        self.submit_review(pr_url=base_pr_url, state=state, body=full_summary)

    def submit_review(
        self,
        pr_url: str,
        state: str,
        body: str = "",
    ) -> Dict[str, Any]:
        """Submit a PR review with a state (APPROVED, CHANGES_REQUESTED, COMMENTED).

        Args:
            pr_url: GitHub PR URL
            state: "APPROVED", "CHANGES_REQUESTED", or "COMMENTED"
            body: Review body/comment (optional)

        Returns:
            Dict with status_code and response data
        """
        owner, repo, pr_number = self._parse_pr_url(pr_url)

        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"

        commit_id = self._get_pr_head_sha(pr_url)
        
        payload = {
            "body": body,
            "event": state,
            "commit_id": commit_id,
        }

        print(f"  🛠️ Submitting {state} review for PR #{pr_number}")
        print(f"  📤 Payload: {payload}")
        response = requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=30,
        )

        print(f"  📥 Response: {response.status_code} - {response.text[:200]}")
        
        if response.status_code == 200:
            print(f"  ✅ Review submitted: {state}")
        else:
            print(f"  ❌ Failed to submit review: HTTP {response.status_code} — {response.text[:200]}")

        return {"status_code": response.status_code, "data": response.json() if response.content else {}}

    def _extract_comment_id_and_type(self, comment_url: str) -> tuple:
        """Extract comment ID and type from GitHub comment URL.

        Args:
            comment_url: Full GitHub comment URL (e.g., https://github.com/owner/repo/pull/24#issuecomment-123)

        Returns:
            Tuple of (comment_id: int, comment_type: str) where comment_type is 'issue' or 'discussion'
        """
        if "#issuecomment-" in comment_url:
            comment_id = comment_url.split("#issuecomment-")[-1]
            return int(comment_id), "issue"
        elif "#discussion_r" in comment_url:
            comment_id = comment_url.split("#discussion_r")[-1]
            return int(comment_id), "discussion"
        else:
            raise ValueError(f"Invalid comment URL format: {comment_url}")

    def post_trigger_comment(
        self,
        comment_url: str,
        text: str,
        quote_body: str = "",
    ) -> Dict[str, Any]:
        """Post a comment in response to a trigger comment, automatically handling quoting.

        For issue comments: quotes the trigger comment body, then posts reply
        For discussion comments: posts reply directly without quoting

        Args:
            comment_url: Full GitHub comment URL with anchor (e.g., https://github.com/owner/repo/pull/24#issuecomment-123)
            text: Comment text to post
            quote_body: Optional body text to quote (e.g., from trigger_comment.json).
                        If not provided, will try to fetch from API.

        Returns:
            Dict with status_code and response data
        """
        # If URL has no anchor, post as general comment
        if "#" not in comment_url:
            return self.post_comment(pr_url=comment_url, text=text)

        pr_url = comment_url.split("#")[0]
        comment_id, comment_type = self._extract_comment_id_and_type(comment_url)

        # Get the trigger comment body for quoting (issue comments only)
        if comment_type == "issue":
            if quote_body:
                trigger_body = quote_body
            else:
                trigger_body = self._get_comment_body(pr_url, comment_id, comment_type)
            
            if trigger_body:
                quoted = "\n".join(f"> {line}" for line in trigger_body.strip().split('\n'))
                full_text = f"{quoted}\n\n{text}"
            else:
                full_text = text
            # Issue comments don't support in_reply_to - post as new comment
            return self.post_comment(pr_url=pr_url, text=full_text)
        else:
            # Discussion comments support in_reply_to
            return self.post_reply(pr_url=pr_url, parent_comment_id=comment_id, text=text)

    def _get_comment_body(self, pr_url: str, comment_id: int, comment_type: str) -> str:
        """Fetch the body of an existing comment.

        Args:
            pr_url: GitHub PR URL
            comment_id: Comment ID
            comment_type: 'issue' or 'discussion'

        Returns:
            Comment body text, or empty string if fetch fails
        """
        owner, repo, pr_number = self._parse_pr_url(pr_url)

        if comment_type == "issue":
            url = f"{self.base_url}/repos/{owner}/{repo}/issues/comments/{comment_id}"
        else:
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/comments/{comment_id}"

        try:
            response = requests.get(url, headers=self._headers(), timeout=30)
            if response.status_code == 200:
                return response.json().get("body", "")
        except Exception as e:
            print(f"  ⚠️ Failed to fetch comment body: {e}")
        return ""
