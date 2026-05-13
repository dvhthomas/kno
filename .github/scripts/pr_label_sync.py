"""Auto-apply lifecycle labels to issues referenced by `Closes #N` in a PR body.

Local debug:
  PR_NUMBER=15 PR_ACTION=opened PR_IS_DRAFT=true \\
  PR_BODY="Closes #11" \\
  GITHUB_REPOSITORY=dvhthomas/kno GH_TOKEN=$(gh auth token) \\
  python3 .github/scripts/pr_label_sync.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

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
    if action == "opened" and is_draft and any(label in current for label in LIFECYCLE):
        return ([], [])
    if target in current:
        return ([], [])
    to_remove = [label for label in LIFECYCLE if label != target and label in current]
    return (to_remove, [target])


def _gh(args: list[str]) -> str:
    """Run gh and return stdout. Caller handles non-zero exit."""
    res = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return res.stdout


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    body = os.environ.get("PR_BODY", "")
    action = os.environ["PR_ACTION"]
    is_draft = os.environ.get("PR_IS_DRAFT", "false").lower() == "true"

    refs = parse_issue_refs(body)
    if not refs:
        print("No `Closes #N` — skip (pr-validate enforces presence separately).")
        return 0

    target = target_label(action, is_draft)
    if target is None:
        print(f"Unhandled action: {action}")
        return 0

    for n in refs:
        try:
            raw = _gh(["api", f"/repos/{repo}/issues/{n}", "--jq", "[.labels[].name]"])
        except subprocess.CalledProcessError as e:
            if "404" in (e.stderr or ""):
                print(f"#{n} not found — skip.")
                continue
            raise
        current = json.loads(raw) if raw.strip() else []

        to_remove, to_add = transition_labels(current, target, action, is_draft)
        if not to_remove and not to_add:
            print(f"#{n} already at `{target}` (or protected from downgrade) — no-op.")
            continue

        for label in to_remove:
            _gh(["api", "-X", "DELETE", f"/repos/{repo}/issues/{n}/labels/{label}"])
            print(f"Removed `{label}` from #{n}")
        for label in to_add:
            _gh(
                ["api", "-X", "POST", f"/repos/{repo}/issues/{n}/labels", "-f", f"labels[]={label}"]
            )
            print(f"Added `{label}` to #{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
