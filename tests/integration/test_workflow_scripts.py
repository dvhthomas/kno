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


# ─── pr_review_gate ───────────────────────────────────────────────────────────


@pytest.fixture
def pr_review_gate():
    return _load("pr_review_gate")


class TestFindReviewComment:
    """`find_review_comment(comments)` returns the *latest* comment matching
    the `## Code-reviewer subagent` marker, or None."""

    def test_returns_none_when_no_marker(self, pr_review_gate):
        comments = [
            {"body": "looks good!", "created_at": "2026-05-13T10:00:00Z"},
            {"body": "## Some other heading\nbody", "created_at": "2026-05-13T11:00:00Z"},
        ]
        assert pr_review_gate.find_review_comment(comments) is None

    def test_returns_match_when_single(self, pr_review_gate):
        comments = [
            {"body": "## Code-reviewer subagent\n**Verdict:** APPROVE",
             "created_at": "2026-05-13T10:00:00Z"},
        ]
        result = pr_review_gate.find_review_comment(comments)
        assert result is not None
        assert "APPROVE" in result["body"]

    def test_returns_latest_when_multiple(self, pr_review_gate):
        comments = [
            {"body": "## Code-reviewer subagent\n**Verdict:** REQUEST CHANGES",
             "created_at": "2026-05-13T10:00:00Z"},
            {"body": "## Code-reviewer subagent\n**Verdict:** APPROVE",
             "created_at": "2026-05-13T11:00:00Z"},
        ]
        result = pr_review_gate.find_review_comment(comments)
        assert "APPROVE" in result["body"]

    def test_rejects_indented_heading(self, pr_review_gate):
        # Heading must be at column 0 — leading whitespace doesn't match.
        comments = [
            {"body": "  ## Code-reviewer subagent\n**Verdict:** APPROVE",
             "created_at": "2026-05-13T11:00:00Z"},
        ]
        assert pr_review_gate.find_review_comment(comments) is None


class TestIsApproved:
    """`is_approved(body)` returns True only when `**Verdict:** APPROVE`
    is the entire content of a line (no trailing text)."""

    def test_approve_alone_on_line(self, pr_review_gate):
        assert pr_review_gate.is_approved("## Header\n**Verdict:** APPROVE\nmore text") is True

    def test_request_changes_rejected(self, pr_review_gate):
        assert pr_review_gate.is_approved("**Verdict:** REQUEST CHANGES") is False

    def test_legend_text_rejected(self, pr_review_gate):
        # The skill's template legend reads "APPROVE | REQUEST CHANGES" —
        # this must NOT match.
        body = "Verdict line legend: **Verdict:** APPROVE | REQUEST CHANGES"
        assert pr_review_gate.is_approved(body) is False

    def test_approve_pending_rejected(self, pr_review_gate):
        assert pr_review_gate.is_approved("**Verdict:** APPROVE_PENDING") is False

    def test_no_verdict_at_all(self, pr_review_gate):
        assert pr_review_gate.is_approved("nothing useful here") is False


# ─── pr_validate ──────────────────────────────────────────────────────────────


@pytest.fixture
def pr_validate():
    return _load("pr_validate")


class TestValidateBranchName:
    @pytest.mark.parametrize(
        "branch",
        [
            "feat/12-google-oauth",
            "fix/47-config-leak",
            "chore/3-bump-pydantic",
            "docs/22-ops-manual",
            "refactor/14-workflow-scripts",
            "test/99-coverage",
            "ci/1-add-runner",
            "build/2-trim-image",
        ],
    )
    def test_valid_branch_names_have_no_failures(self, pr_validate, branch):
        assert pr_validate.validate_branch_name(branch) == []

    @pytest.mark.parametrize(
        "branch",
        [
            "junk-name",         # no type/n-slug structure
            "feature/12-x",      # 'feature' isn't an allowed type
            "Feat/12-x",         # caps
            "feat/12_x",         # underscore in slug
            "feat/abc-foo",      # non-numeric issue number
            "feat/-bar",         # missing issue number
            "feat/12-",          # missing slug
        ],
    )
    def test_invalid_branch_names_have_one_failure(self, pr_validate, branch):
        failures = pr_validate.validate_branch_name(branch)
        assert len(failures) == 1
        assert branch in failures[0]


class TestFindClosesRef:
    """`find_closes_ref(body)` -> int|None — the first issue number cited."""

    @pytest.mark.parametrize(
        "body,expected",
        [
            ("Closes #11", 11),
            ("fixes #47", 47),
            ("Resolves #999", 999),
            ("Closes #11 and Fixes #12", 11),  # first wins
            ("no reference here", None),
            ("", None),
        ],
    )
    def test_cases(self, pr_validate, body, expected):
        assert pr_validate.find_closes_ref(body) == expected


class TestValidateIssueLabels:
    """`validate_issue_labels(labels, issue_num)` returns list of failures."""

    def test_has_type_and_area(self, pr_validate):
        assert pr_validate.validate_issue_labels(
            ["enhancement", "area:web"], 11
        ) == []

    def test_missing_type(self, pr_validate):
        failures = pr_validate.validate_issue_labels(["area:web"], 11)
        assert len(failures) == 1
        assert "type label" in failures[0]
        assert "#11" in failures[0]

    def test_missing_area(self, pr_validate):
        failures = pr_validate.validate_issue_labels(["enhancement"], 11)
        assert len(failures) == 1
        assert "area" in failures[0].lower()

    def test_missing_both(self, pr_validate):
        failures = pr_validate.validate_issue_labels([], 11)
        assert len(failures) == 2

    @pytest.mark.parametrize(
        "type_label", ["enhancement", "bug", "documentation", "chore"]
    )
    def test_all_four_type_labels_accepted(self, pr_validate, type_label):
        assert pr_validate.validate_issue_labels([type_label, "area:web"], 11) == []


# ─── enforce_issue_close ──────────────────────────────────────────────────────


@pytest.fixture
def enforce_issue_close():
    return _load("enforce_issue_close")


class TestIsAutoClosedByPrOrCommit:
    """`is_auto_closed_by_pr_or_commit(closer)` reads the latest `ClosedEvent.closer`
    GraphQL node and returns True iff a merged PR or commit closed the issue."""

    def test_merged_pr_closer(self, enforce_issue_close):
        closer = {"__typename": "PullRequest", "number": 2, "merged": True}
        assert enforce_issue_close.is_auto_closed_by_pr_or_commit(closer) is True

    def test_unmerged_pr_closer_is_false(self, enforce_issue_close):
        closer = {"__typename": "PullRequest", "number": 2, "merged": False}
        assert enforce_issue_close.is_auto_closed_by_pr_or_commit(closer) is False

    def test_commit_closer(self, enforce_issue_close):
        closer = {"__typename": "Commit", "abbreviatedOid": "abc1234"}
        assert enforce_issue_close.is_auto_closed_by_pr_or_commit(closer) is True

    def test_no_closer(self, enforce_issue_close):
        assert enforce_issue_close.is_auto_closed_by_pr_or_commit(None) is False

    def test_unknown_typename(self, enforce_issue_close):
        closer = {"__typename": "SomeOther"}
        assert enforce_issue_close.is_auto_closed_by_pr_or_commit(closer) is False


class TestRecentCommentsHaveReference:
    """`recent_comments_have_reference(comments)` scans the last 2 comments
    for `#N` or a 7-40-char hex SHA reference."""

    def test_no_comments(self, enforce_issue_close):
        assert enforce_issue_close.recent_comments_have_reference([]) is False

    def test_issue_number_reference(self, enforce_issue_close):
        comments = [{"body": "Duplicate of #42."}]
        assert enforce_issue_close.recent_comments_have_reference(comments) is True

    def test_commit_sha_reference(self, enforce_issue_close):
        comments = [{"body": "Closed by abc1234 — already shipped."}]
        assert enforce_issue_close.recent_comments_have_reference(comments) is True

    def test_no_reference_in_text(self, enforce_issue_close):
        comments = [{"body": "Closing for now."}]
        assert enforce_issue_close.recent_comments_have_reference(comments) is False

    def test_only_last_two_checked(self, enforce_issue_close):
        # The reference is in comment[0] but only last 2 are checked.
        comments = [
            {"body": "see #42"},
            {"body": "no ref"},
            {"body": "still no ref"},
            {"body": "nothing"},
        ]
        assert enforce_issue_close.recent_comments_have_reference(comments) is False

    def test_reference_in_recent(self, enforce_issue_close):
        comments = [
            {"body": "no ref"},
            {"body": "see #42"},  # second-from-end, within last 2
        ]
        assert enforce_issue_close.recent_comments_have_reference(comments) is True
