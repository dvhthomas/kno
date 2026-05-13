"""Enforce the closing rule from docs/notes/dev-flow.md.

Every issue close must reference a PR, commit, or related issue. Three
valid paths:
  1. Auto-close via merged PR's `Closes #N` (body or commit message).
     Detected via GraphQL `ClosedEvent.closer` — works regardless of
     merge style.
  2. Manual close with a reference (`#N` or commit SHA) in the last 2
     comments.
  3. Workflow-initiated close — skipped at the YAML level (sender.type
     != 'Bot' guard) before this script runs.

Otherwise: reopen the issue and post a comment explaining the rule.

Local debug:
  ISSUE_NUMBER=1 GITHUB_REPOSITORY=dvhthomas/kno GH_TOKEN=$(gh auth token) \\
    python3 .github/scripts/enforce_issue_close.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

REF_RE = re.compile(r"(#\d+|\b[0-9a-f]{7,40}\b)")

GRAPHQL_CLOSER_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      timelineItems(last: 30, itemTypes: [CLOSED_EVENT]) {
        nodes {
          ... on ClosedEvent {
            createdAt
            closer {
              __typename
              ... on PullRequest { number, merged }
              ... on Commit { abbreviatedOid }
            }
          }
        }
      }
    }
  }
}
"""


def is_auto_closed_by_pr_or_commit(closer: dict[str, object] | None) -> bool:
    """True iff the closer is a merged PR or a Commit."""
    if closer is None:
        return False
    t = closer.get("__typename")
    if t == "PullRequest":
        return bool(closer.get("merged"))
    if t == "Commit":
        return True
    return False


def recent_comments_have_reference(comments: list[dict[str, object]]) -> bool:
    """True iff any of the last 2 comments contains `#N` or a 7-40 hex SHA."""
    for c in comments[-2:]:
        if REF_RE.search(str(c.get("body") or "")):
            return True
    return False


def _gh(args: list[str], input_text: str | None = None) -> str:
    res = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, input=input_text
    )
    return res.stdout


def _gh_graphql_closer(repo: str, issue_num: int) -> dict[str, object] | None:
    owner, name = repo.split("/")
    raw = _gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={GRAPHQL_CLOSER_QUERY}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={name}",
            "-F",
            f"number={issue_num}",
        ]
    )
    data = json.loads(raw)
    nodes = data["data"]["repository"]["issue"]["timelineItems"]["nodes"]
    if not nodes:
        return None
    closer = nodes[-1].get("closer")
    return closer if isinstance(closer, dict) else None


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    issue_num = int(os.environ["ISSUE_NUMBER"])

    closer = _gh_graphql_closer(repo, issue_num)
    if is_auto_closed_by_pr_or_commit(closer):
        assert closer is not None  # narrowed by is_auto_closed... above
        t = closer["__typename"]
        ident = closer.get("number") if t == "PullRequest" else closer.get("abbreviatedOid")
        print(f"Auto-closed by {t} {ident} — OK.")
        return 0

    raw = _gh(
        [
            "api",
            f"/repos/{repo}/issues/{issue_num}/comments",
            "--paginate",
        ]
    )
    comments = json.loads(raw) if raw.strip() else []
    if recent_comments_have_reference(comments):
        print("Reference found in recent comments — OK.")
        return 0

    print(f"Issue #{issue_num} closed without reference. Reopening.")
    _gh(
        [
            "api",
            "-X",
            "PATCH",
            f"/repos/{repo}/issues/{issue_num}",
            "-f",
            "state=open",
        ]
    )

    body = (
        "🚩 **Closed without a reference — reopening.**\n\n"
        "Per [`docs/notes/dev-flow.md` → Closing rule](../blob/main/docs/notes/dev-flow.md#closing-rule), "
        "every issue close must cite a **PR** (`#N`), **commit SHA** (≥7 chars), or **related issue** (`#N`).\n\n"
        "**Three patterns that satisfy the rule:**\n\n"
        f"1. **Auto-close via PR merge** — include `Closes #{issue_num}` in a PR body, then merge.\n"
        f"2. **Auto-close via commit** — include `Closes #{issue_num}` in a commit message pushed to `main`.\n"
        "3. **Manual close with a comment naming the artifact**:\n"
        "   ```bash\n"
        f'   gh issue close {issue_num} --reason "not planned" \\\n'
        '       --comment "Duplicate of #M."   # or: "Wontfix — see PR #M." / "Superseded by commit abc1234."\n'
        "   ```\n"
    )
    _gh(
        [
            "api",
            "-X",
            "POST",
            f"/repos/{repo}/issues/{issue_num}/comments",
            "-f",
            f"body={body}",
        ]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
