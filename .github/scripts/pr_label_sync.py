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


def parse_issue_refs(body: str) -> list[int]:
    """Extract unique issue numbers from `Closes|Fixes|Resolves #N` references."""
    return sorted({int(m) for m in CLOSES_RE.findall(body)})
