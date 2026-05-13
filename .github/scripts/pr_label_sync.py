"""Auto-apply lifecycle labels to issues referenced by `Closes #N` in a PR body.

Local debug:
  PR_NUMBER=15 PR_ACTION=opened PR_IS_DRAFT=true \\
  PR_BODY="Closes #11" \\
  GITHUB_REPOSITORY=dvhthomas/kno GH_TOKEN=$(gh auth token) \\
  python3 .github/scripts/pr_label_sync.py
"""

from __future__ import annotations

import re

CLOSES_RE = re.compile(r"(?:Closes|Fixes|Resolves)\s+#(\d+)", re.IGNORECASE)

LIFECYCLE = ("shaping", "in-progress", "in-review")


def parse_issue_refs(body: str) -> list[int]:
    """Extract unique issue numbers from `Closes|Fixes|Resolves #N` references."""
    return sorted({int(m) for m in CLOSES_RE.findall(body)})


def target_label(action: str, is_draft: bool) -> str | None:
    """Decide which lifecycle label the linked issue should have for this PR state.

    Returns ``None`` if the action is one we don't transition on.
    """
    if action == "opened":
        return "shaping" if is_draft else "in-review"
    if action == "ready_for_review":
        return "in-review"
    if action == "converted_to_draft":
        return "in-progress"
    if action == "reopened":
        return "in-progress" if is_draft else "in-review"
    return None
