"""Validate a PR's branch name, body, and linked issue's labels.

Three rules, all failures collected and reported together so the author
sees the whole punch-list in one CI run:

1. Branch name matches `<type>/<issue#>-<slug>`.
2. PR body contains `Closes|Fixes|Resolves #N`.
3. The linked issue has both a type label (enhancement | bug |
   documentation | chore) and an `area:*` label.

Local debug:
  PR_BRANCH=feat/14-x PR_BODY="Closes #11" \\
  GITHUB_REPOSITORY=dvhthomas/kno GH_TOKEN=$(gh auth token) \\
    python3 .github/scripts/pr_validate.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

BRANCH_RE = re.compile(
    r"^(feat|fix|chore|docs|refactor|ci|build|test)/[0-9]+-[a-z0-9-]+$"
)
CLOSES_RE = re.compile(r"(?:Closes|Fixes|Resolves)\s+#(\d+)", re.IGNORECASE)

TYPE_LABELS = frozenset({"enhancement", "bug", "documentation", "chore"})


def validate_branch_name(branch: str) -> list[str]:
    """Return list of failure messages (empty if valid)."""
    if BRANCH_RE.fullmatch(branch):
        return []
    return [
        f"Branch name `{branch}` does not match `<type>/<issue#>-<slug>`. "
        "Allowed types: feat, fix, chore, docs, refactor, ci, build, test. "
        "Example: feat/12-google-oauth"
    ]
