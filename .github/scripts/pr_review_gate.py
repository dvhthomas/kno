"""Fail the merge gate if no code-reviewer subagent comment with APPROVE.

Heading convention (STRICT): the comment must contain `## Code-reviewer
subagent` at the start of a line. Variations like emoji prefixes or
indented headings will not match.

Verdict convention (STRICT): a line containing exactly `**Verdict:**
APPROVE` (no trailing text). The skill template legend
`APPROVE | REQUEST CHANGES` does NOT match (it's not anchored to the
whole line).

Local debug:
  PR_NUMBER=15 GITHUB_REPOSITORY=dvhthomas/kno GH_TOKEN=$(gh auth token) \\
    python3 .github/scripts/pr_review_gate.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

MARKER_RE = re.compile(r"^##\s+Code-reviewer subagent", re.MULTILINE)
APPROVE_RE = re.compile(r"^\s*\*\*Verdict:\*\*\s*APPROVE\s*$", re.MULTILINE | re.IGNORECASE)


def find_review_comment(comments: list[dict[str, object]]) -> dict[str, object] | None:
    """Return the latest comment matching the marker, or None."""
    matches = [c for c in comments if MARKER_RE.search(str(c.get("body") or ""))]
    if not matches:
        return None
    return max(matches, key=lambda c: str(c["created_at"]))


def is_approved(body: str) -> bool:
    """True iff body contains a line that's exactly `**Verdict:** APPROVE`."""
    return APPROVE_RE.search(body) is not None


def _gh(args: list[str]) -> str:
    res = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return res.stdout


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]

    raw = _gh(["api", f"/repos/{repo}/issues/{pr_number}/comments", "--paginate"])
    comments = json.loads(raw) if raw.strip() else []

    review = find_review_comment(comments)
    if review is None:
        print(
            "No code-reviewer subagent comment found. Per AGENTS.md → "
            "Strict pre-merge review: invoke `Agent(subagent_type="
            '"agent-skills:code-reviewer")` and post findings as a PR '
            "comment starting with `## Code-reviewer subagent`.",
            file=sys.stderr,
        )
        return 1

    if not is_approved(str(review["body"])):
        print(
            f"Latest code-reviewer comment ({review.get('html_url', '(unknown url)')}) "
            "does not contain `**Verdict:** APPROVE` on its own line. "
            "Address findings, re-invoke the subagent, post the updated review.",
            file=sys.stderr,
        )
        return 1

    print(f"Code-reviewer APPROVE found at {review.get('html_url', '(unknown url)')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
