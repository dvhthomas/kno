"""Unit tests for the pure-function cores of `.github/scripts/*.py`.

These tests are why workflow logic lives in scripts: they can run locally
in ~50ms, drive TDD red→green for each pure function, and catch the
exact bugs (loose regex matching, off-by-one label transitions) that
inline `script:` blocks in YAML would hide.

Per `feedback-no-logic-in-workflows`.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / ".github" / "scripts"


def _load(name: str):
    """Load `.github/scripts/<name>.py` as an importable module."""
    path = _SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── pr_label_sync.parse_issue_refs ───────────────────────────────────────────


@pytest.fixture
def pr_label_sync():
    return _load("pr_label_sync")


class TestParseIssueRefs:
    def test_single_closes(self, pr_label_sync):
        assert pr_label_sync.parse_issue_refs("Closes #11") == [11]

    def test_three_keyword_variants(self, pr_label_sync):
        body = "Closes #11\nFixes #12\nResolves #13"
        assert sorted(pr_label_sync.parse_issue_refs(body)) == [11, 12, 13]

    def test_deduplicates_repeated_refs(self, pr_label_sync):
        assert pr_label_sync.parse_issue_refs("Closes #11\nFixes #11") == [11]

    def test_no_match_returns_empty(self, pr_label_sync):
        assert pr_label_sync.parse_issue_refs("Just some prose, no refs.") == []

    def test_case_insensitive_keyword(self, pr_label_sync):
        assert pr_label_sync.parse_issue_refs("CLOSES #11") == [11]


class TestTargetLabel:
    @pytest.mark.parametrize(
        "action,is_draft,expected",
        [
            ("opened", True, "shaping"),
            ("opened", False, "in-review"),
            ("ready_for_review", False, "in-review"),
            ("converted_to_draft", True, "in-progress"),
            ("reopened", True, "in-progress"),
            ("reopened", False, "in-review"),
        ],
    )
    def test_known_actions(self, pr_label_sync, action, is_draft, expected):
        assert pr_label_sync.target_label(action, is_draft) == expected

    def test_unknown_action_returns_none(self, pr_label_sync):
        assert pr_label_sync.target_label("closed", False) is None


class TestTransitionLabels:
    """`transition_labels(current, target, action, is_draft)` -> (to_remove, to_add).

    Pure decision function — no I/O. Used by main() to compute API calls.
    """

    def test_already_target_is_noop(self, pr_label_sync):
        assert pr_label_sync.transition_labels(
            ["shaping", "enhancement"], "shaping", "opened", True
        ) == ([], [])

    def test_add_when_no_lifecycle_label(self, pr_label_sync):
        assert pr_label_sync.transition_labels(
            ["enhancement", "area:web"], "in-review", "ready_for_review", False
        ) == ([], ["in-review"])

    def test_swap_in_progress_to_in_review(self, pr_label_sync):
        assert pr_label_sync.transition_labels(
            ["in-progress", "enhancement"], "in-review", "ready_for_review", False
        ) == (["in-progress"], ["in-review"])

    def test_swap_in_review_back_to_in_progress(self, pr_label_sync):
        # PR was ready, gets converted_to_draft → step back to in-progress.
        assert pr_label_sync.transition_labels(
            ["in-review"], "in-progress", "converted_to_draft", True
        ) == (["in-review"], ["in-progress"])

    def test_opened_draft_does_not_downgrade_existing_lifecycle(self, pr_label_sync):
        # Issue already labeled in-progress; draft PR re-opens — don't reset to shaping.
        assert pr_label_sync.transition_labels(
            ["in-progress"], "shaping", "opened", True
        ) == ([], [])

    def test_opened_draft_applies_shaping_when_no_lifecycle(self, pr_label_sync):
        assert pr_label_sync.transition_labels(
            ["enhancement"], "shaping", "opened", True
        ) == ([], ["shaping"])
