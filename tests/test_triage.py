from pathlib import Path

import pytest

from guildkit import triage

USAGE: triage.Usage = {
    "input_tokens": 1000,
    "output_tokens": 100,
    "cache_read_tokens": 500,
    "cache_write_tokens": 200,
}


def output(**overrides: object) -> triage.ModelOutput:
    base: dict[str, object] = {
        "kind": "bug",
        "severity": "high",
        "clause": "UTS #39 section 4",
        "missing": [],
    }
    base.update(overrides)
    return triage.validate_output(base)


def test_validate_output_accepts_the_schema() -> None:
    assert output() == {
        "kind": "bug",
        "severity": "high",
        "clause": "UTS #39 section 4",
        "missing": [],
    }
    assert output(kind="feature", clause="C-SCOPE-5", missing=["summary", "summary"])[
        "missing"
    ] == ["summary"]


@pytest.mark.parametrize(
    "bad",
    [
        "not an object",
        {"kind": "bug"},
        {
            "kind": "bug",
            "severity": "high",
            "clause": None,
            "missing": [],
            "note": "free text",
        },
        {"kind": "wish", "severity": "none", "clause": None, "missing": []},
        {"kind": "bug", "severity": "urgent", "clause": None, "missing": []},
        {"kind": "bug", "severity": "high", "clause": "see the docs", "missing": []},
        {"kind": "bug", "severity": "high", "clause": None, "missing": ["patience"]},
        {"kind": "bug", "severity": "high", "clause": None, "missing": "summary"},
    ],
)
def test_validate_output_rejects_everything_else(bad: object) -> None:
    with pytest.raises(triage.TriageError):
        triage.validate_output(bad)


def test_parse_output_finds_the_object_in_the_reply() -> None:
    reply = (
        'Sure! {"kind": "question", "severity": "none", "clause": null, "missing": []}'
        " Hope this helps."
    )
    assert triage.parse_output(reply)["kind"] == "question"
    with pytest.raises(triage.TriageError, match="no JSON"):
        triage.parse_output("I refuse")
    with pytest.raises(triage.TriageError, match="invalid JSON"):
        triage.parse_output("{kind: bug}")


def test_bug_policy() -> None:
    confirmed = triage.apply_policy(output(), "confirms")
    assert confirmed["actionable"] is True
    assert confirmed["template"] == "bug_accepted"
    assert confirmed["labels"] == ["guild:bug", "severity:high"]
    assert confirmed["outcome"] == "posted"

    unconfirmed = triage.apply_policy(output(), "not_run")
    assert unconfirmed["actionable"] is False
    assert unconfirmed["missing"] == ["reproducer"]
    assert unconfirmed["labels"] == ["guild:bug", "needs info"]
    assert unconfirmed["outcome"] == "needs_info"

    uncited = triage.apply_policy(output(clause=None), "confirms")
    assert uncited["actionable"] is False
    assert uncited["missing"] == ["citation"]

    disagrees = triage.apply_policy(output(), "disagrees")
    assert disagrees["actionable"] is False
    assert disagrees["template"] == "spec_disagrees"
    assert disagrees["labels"] == ["guild:bug", "spec disagrees"]
    assert disagrees["outcome"] == "declined"


def test_feature_policy() -> None:
    accepted = triage.apply_policy(
        output(kind="feature", clause="C-SCOPE-5"), "not_applicable"
    )
    assert accepted["actionable"] is True
    assert accepted["severity"] == "none"
    assert accepted["template"] == "feature_accepted"

    no_clause = triage.apply_policy(
        output(kind="feature", clause=None), "not_applicable"
    )
    assert no_clause["actionable"] is False
    assert no_clause["missing"] == ["clause"]

    spec_clause = triage.apply_policy(
        output(kind="feature", clause="UTS #39 section 4"), "not_applicable"
    )
    assert spec_clause["missing"] == ["clause"]

    incomplete = triage.apply_policy(
        output(kind="feature", clause="C-SCOPE-5", missing=["summary"]), "not_run"
    )
    assert incomplete["actionable"] is False
    assert incomplete["template"] == "needs_info"


@pytest.mark.parametrize(
    ("kind", "template", "labels"),
    [
        ("question", "question", ["guild:question"]),
        ("security", "security", ["guild:security", "needs steward"]),
        ("spam", "spam", ["guild:spam"]),
        ("other", "needs_steward", ["guild:other", "needs steward"]),
    ],
)
def test_other_kinds_are_never_actionable(
    kind: str, template: str, labels: list[str]
) -> None:
    record = triage.apply_policy(output(kind=kind, clause=None), "not_applicable")
    assert record["actionable"] is False
    assert record["template"] == template
    assert record["labels"] == labels
    assert record["outcome"] == "declined"


def test_policy_rejects_an_unknown_oracle_value() -> None:
    with pytest.raises(triage.TriageError):
        triage.apply_policy(output(), "maybe")  # type: ignore[arg-type]


def test_triage_uses_the_fallback_when_the_reply_does_not_parse() -> None:
    calls: list[tuple[str, str, str, int]] = []

    def call(
        system: str, user: str, *, model: str, max_tokens: int
    ) -> tuple[str, triage.Usage]:
        calls.append((system, user, model, max_tokens))
        return "I would rather chat.", USAGE

    record, usage, parsed = triage.triage(
        call, system="S", user="U", oracle="not_run", model="m-1", max_tokens=99
    )
    assert calls == [("S", "U", "m-1", 99)]
    assert parsed is False
    assert usage == USAGE
    assert record["kind"] == "other"
    assert record["labels"] == ["guild:other", "needs steward"]


def test_cost_from_the_price_table() -> None:
    prices: triage.Prices = {
        "input_per_mtok": 0.10,
        "output_per_mtok": 0.50,
        "cache_read_per_mtok": 0.01,
        "cache_write_per_mtok": 0.125,
    }
    assert triage.cost_usd(USAGE, prices) == pytest.approx(
        0.0001 + 0.00005 + 0.000005 + 0.000025
    )


def test_render_comment_fills_only_known_placeholders(root: Path) -> None:
    record = triage.apply_policy(output(), "not_run")
    comment = triage.render_comment(
        record,
        root / "templates" / "comments",
        {"decision_url": "https://x.test/d", "charter_url": "https://x.test/c"},
    )
    assert "- a reproducer the oracle check can run" in comment
    assert "Decision record: https://x.test/d" in comment
    assert "{" not in comment
    assert comment.isascii()


def test_render_comment_fails_on_an_unknown_placeholder(tmp_path: Path) -> None:
    (tmp_path / "needs_info.md").write_text("Hello {reporter_name}", encoding="ascii")
    record = triage.apply_policy(output(), "not_run")
    with pytest.raises(triage.TriageError, match="reporter_name"):
        triage.render_comment(
            record, tmp_path, {"decision_url": "u", "charter_url": "c"}
        )


def test_every_template_renders_for_its_record(root: Path) -> None:
    templates = root / "templates" / "comments"
    cases = [
        (output(), "confirms"),
        (output(), "not_run"),
        (output(), "disagrees"),
        (output(kind="feature", clause="C-SCOPE-5"), "not_applicable"),
        (output(kind="question", clause=None), "not_applicable"),
        (output(kind="security", clause=None), "not_applicable"),
        (output(kind="spam", clause=None), "not_applicable"),
        (output(kind="other", clause=None), "not_applicable"),
    ]
    seen = set()
    for out, oracle in cases:
        record = triage.apply_policy(out, oracle)  # type: ignore[arg-type]
        seen.add(record["template"])
        comment = triage.render_comment(
            record, templates, {"decision_url": "u", "charter_url": "c"}
        )
        assert comment.endswith("Decision record: u\n")
    assert seen == {p.stem for p in templates.glob("*.md")}
