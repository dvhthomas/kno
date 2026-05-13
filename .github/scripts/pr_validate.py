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

BRANCH_RE = re.compile(r"^(feat|fix|chore|docs|refactor|ci|build|test)/[0-9]+-[a-z0-9-]+$")
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


def find_closes_ref(body: str) -> int | None:
    """First `Closes|Fixes|Resolves #N` reference in body, or None."""
    m = CLOSES_RE.search(body)
    return int(m.group(1)) if m else None


def validate_issue_labels(labels: list[str], issue_num: int) -> list[str]:
    """Return failures for missing type / area labels on the linked issue."""
    failures: list[str] = []
    if not any(label in TYPE_LABELS for label in labels):
        failures.append(
            f"Linked issue #{issue_num} lacks a type label. "
            "Add one of: enhancement, bug, documentation, chore."
        )
    if not any(label.startswith("area:") for label in labels):
        failures.append(
            f"Linked issue #{issue_num} lacks an `area:*` label. "
            "See .github/labels.yml for the catalogue."
        )
    return failures


def _gh(args: list[str]) -> str:
    res = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return res.stdout


def main() -> int:
    branch = os.environ["PR_BRANCH"]
    body = os.environ.get("PR_BODY", "")
    repo = os.environ["GITHUB_REPOSITORY"]

    failures: list[str] = []
    failures.extend(validate_branch_name(branch))

    issue_num = find_closes_ref(body)
    if issue_num is None:
        failures.append(
            "PR body lacks a closing reference. Add `Closes #<n>` "
            "(or Fixes / Resolves) pointing at the issue this PR completes."
        )
    else:
        try:
            raw = _gh(
                [
                    "api",
                    f"/repos/{repo}/issues/{issue_num}",
                    "--jq",
                    "[.labels[].name]",
                ]
            )
            labels = json.loads(raw) if raw.strip() else []
            failures.extend(validate_issue_labels(labels, issue_num))
        except subprocess.CalledProcessError as e:
            if "404" in (e.stderr or ""):
                failures.append(f"Linked issue #{issue_num} does not exist.")
            else:
                raise

    if failures:
        print(
            "PR validation failed. Fix the following per docs/notes/dev-flow.md:\n",
            file=sys.stderr,
        )
        for i, f in enumerate(failures, 1):
            print(f"{i}. {f}\n", file=sys.stderr)
        return 1

    print("All PR validation rules passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
