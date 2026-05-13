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


def transition_labels(
    current: list[str], target: str, action: str, is_draft: bool
) -> tuple[list[str], list[str]]:
    """Return ``(to_remove, to_add)`` lifecycle label changes.

    Two special cases:

    - Already at target → no-op (``([], [])``).
    - Opened as draft + issue already has a lifecycle label → no-op (don't
      downgrade in-progress / in-review to shaping just because someone
      opens a new draft PR referencing the same issue).
    """
    if action == "opened" and is_draft and any(l in current for l in LIFECYCLE):
        return ([], [])
    if target in current:
        return ([], [])
    to_remove = [l for l in LIFECYCLE if l != target and l in current]
    return (to_remove, [target])
