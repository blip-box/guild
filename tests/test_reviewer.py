from typing import Any

import pytest

from guildkit import reviewer

GOOD: dict[str, Any] = {
    "findings": [
        {
            "kind": "correctness",
            "clause": "UTS #39 section 4",
            "file": "src/confusable/_skeleton.py",
            "line": 42,
            "verified": True,
            "summary": "The RTL branch skips the mapping for U+0430.",
        },
        {
            "kind": "tests",
            "clause": None,
            "file": "tests/test_skeleton.py",
            "line": None,
            "verified": False,
            "summary": "The test does not cover the direction argument.",
        },
    ]
}
FIRST: dict[str, Any] = GOOD["findings"][0]


def test_validate_output_accepts_and_escapes() -> None:
    findings = reviewer.validate_output(
        {"findings": [{**FIRST, "summary": "p" + chr(0x430) + "ypal " * 100}]}
    )
    assert findings[0]["summary"].startswith("pU+0430ypal")
    assert len(findings[0]["summary"]) == reviewer.SUMMARY_LIMIT
    assert findings[0]["summary"].isascii()
    assert reviewer.validate_output({"findings": []}) == []


@pytest.mark.parametrize(
    "bad",
    [
        "text",
        {},
        {"findings": "none"},
        {"findings": [], "verdict": "ok"},
        {"findings": [{**FIRST, "kind": "style"}]},
        {"findings": [{**FIRST, "clause": "see the docs"}]},
        {"findings": [{**FIRST, "file": "../etc/passwd"}]},
        {"findings": [{**FIRST, "line": "42"}]},
        {"findings": [{**FIRST, "verified": "yes"}]},
        {"findings": [{**FIRST, "extra": 1}]},
        {"findings": [FIRST] * (reviewer.MAX_FINDINGS + 1)},
    ],
)
def test_validate_output_rejects(bad: object) -> None:
    with pytest.raises(reviewer.ReviewError):
        reviewer.validate_output(bad)


def test_verdict_counts_verified_findings_only() -> None:
    review = reviewer.verdict(reviewer.validate_output(GOOD))
    assert review["verdict"] == "objections"
    assert review["objections"] == 1
    assert review["notes"] == 1
    unverified = {"findings": [{**FIRST, "verified": False}]}
    assert (
        reviewer.verdict(reviewer.validate_output(unverified))["verdict"]
        == "no_objection"
    )
    assert reviewer.verdict([])["verdict"] == "no_objection"


def test_prompt_sees_only_its_inputs() -> None:
    # A canary anywhere the Reviewer must not look: the Builder's transcript,
    # the issue body, the environment. The prompt is built from five texts.
    canary = "CANARY-7f3a9c"
    builder_transcript = f"the builder said {canary}"
    issue_body = f"the reporter said {canary}"
    system, user = reviewer.prompt(
        role="ROLE", handbook="HAND", charter="CHART", brief="BRIEF", diff="DIFF"
    )
    assert canary not in system
    assert canary not in user
    assert canary in builder_transcript
    assert canary in issue_body
    assert system.startswith("ROLE\n\n# The handbook\n\nHAND\n\n# The charter\n\nCHART")
    assert "# The contract\n\nBRIEF" in user
    assert "# The patch" in user
    assert user.rstrip().endswith("DIFF")


def test_prompt_cuts_a_huge_diff() -> None:
    _, user = reviewer.prompt(
        role="r",
        handbook="h",
        charter="c",
        brief="b",
        diff="x" * (reviewer.DIFF_LIMIT + 10),
    )
    assert "[cut:" in user
    assert len(user) < reviewer.DIFF_LIMIT + 200


def test_markdown_is_ascii_and_lists_findings() -> None:
    review = reviewer.verdict(reviewer.validate_output(GOOD))
    text = reviewer.markdown(review)
    assert text.startswith("Verdict: objections (1 objections, 1 notes)")
    assert (
        "- correctness, verified, src/confusable/_skeleton.py:42 [UTS #39 section 4]:"
        in text
    )
    assert "- tests, not verified, tests/test_skeleton.py:" in text
    assert text.isascii()
    assert "No findings." in reviewer.markdown(reviewer.verdict([]))
