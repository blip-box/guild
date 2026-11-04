import base64
import json
from pathlib import Path

import pytest

from guildkit import ledger

ENTRY: ledger.Entry = {
    "at": "2026-10-30T00:00:00Z",
    "repo": "blip-box/confusable",
    "number": 7,
    "author": "someone",
    "role": "triage",
    "model": "claude-haiku-5-5",
    "input_tokens": 1200,
    "output_tokens": 80,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "cost_usd": 0.00016,
    "outcome": "needs_info",
    "citation": "C-GOV-3",
    "decided_by": "model",
    "decider": "",
    "content_hash": "a" * 64,
    "harness": "guildkit-0.1.0.dev0",
}


def test_valid_entry_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, ENTRY)
    ledger.append(path, {**ENTRY, "number": 8})
    assert [e["number"] for e in ledger.read(path)] == [7, 8]
    assert path.read_text(encoding="ascii").count("\n") == 2


def test_line_is_canonical_json() -> None:
    line = ledger.to_line(ENTRY)
    assert line.startswith(
        '{"at":"2026-10-30T00:00:00Z","author":"someone","cache_read_tokens":0,'
    )
    assert "\n" not in line


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("at", "yesterday"),
        ("repo", "not a repo!"),
        ("number", -1),
        ("role", "oracle"),
        ("model", "Claude Haiku"),
        ("input_tokens", 1.5),
        ("cost_usd", -0.1),
        ("cost_usd", True),
        ("outcome", "shipped"),
        ("citation", "because it seemed right"),
        ("citation", "UTS #39 section four"),
        ("decided_by", "atillaguzel"),
        ("decider", "a steward"),
        ("content_hash", "abc"),
        ("harness", "guildkit 0.1"),
    ],
)
def test_free_text_and_bad_values_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ledger.LedgerError, match=field):
        ledger.validate({**ENTRY, field: value})


def test_missing_and_extra_fields_are_rejected() -> None:
    with pytest.raises(ledger.LedgerError, match="missing"):
        ledger.validate({k: v for k, v in ENTRY.items() if k != "role"})
    with pytest.raises(ledger.LedgerError, match="extra"):
        ledger.validate({**ENTRY, "note": "free text"})


def test_spec_citations_and_steward_deciders_are_allowed() -> None:
    ledger.validate(
        {
            **ENTRY,
            "citation": "UTS #39 section 5.1",
            "decided_by": "steward",
            "decider": "atillaguzel",
        }
    )
    ledger.validate({**ENTRY, "citation": ""})


def test_read_reports_the_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text(ledger.to_line(ENTRY) + "\n{not json}\n", encoding="ascii")
    with pytest.raises(ledger.LedgerError, match=":2:"):
        list(ledger.read(path))


def test_identifier_keeps_logins_and_drops_the_rest() -> None:
    assert ledger.identifier("atillaguzel") == "atillaguzel"
    assert ledger.identifier("a-b.c/d") == "a-b.c/d"
    assert ledger.identifier("") == ""
    assert ledger.identifier("U+0430 u") == ""
    assert ledger.identifier("-leading") == ""
    with pytest.raises(ledger.LedgerError, match="author"):
        ledger.validate({**ENTRY, "author": "not a login"})


def entry(**overrides: object) -> ledger.Entry:
    data: dict[str, object] = {**ENTRY, **overrides}
    return ledger.validate(data)


def test_brake_counts_the_day_by_author_and_in_total() -> None:
    today = "2026-11-04T10:00:00Z"
    entries = [
        entry(at="2026-11-04T01:00:00Z", author="a"),
        entry(at="2026-11-04T02:00:00Z", author="a"),
        entry(at="2026-11-04T03:00:00Z", author="a", outcome="skipped"),
        entry(at="2026-11-04T04:00:00Z", author="b"),
        entry(at="2026-11-03T23:59:59Z", author="a"),
        entry(at="2026-11-04T05:00:00Z", author="a", role="builder"),
    ]
    limits = {"per_author_per_day": 3, "daily_runs": 40}
    assert ledger.brake(entries, author="a", now=today, **limits) == "author"
    assert ledger.brake(entries, author="b", now=today, **limits) is None
    assert ledger.brake(entries, author="c", now=today, **limits) is None
    assert ledger.brake(entries, author="", now=today, **limits) is None
    tight = {"per_author_per_day": 3, "daily_runs": 4}
    assert ledger.brake(entries, author="c", now=today, **tight) == "daily"
    assert ledger.brake(entries, author="a", now=today, **tight) == "author"
    assert ledger.brake([], author="a", now=today, **limits) is None
    tomorrow = "2026-11-05T00:00:00Z"
    assert ledger.brake(entries, author="a", now=tomorrow, **limits) is None


def test_commit_input_appends_lines_and_names_the_head() -> None:
    current = ledger.to_line(ENTRY) + "\n"
    payload = ledger.commit_input(
        current,
        [entry(number=8), entry(number=9, role="builder")],
        repo="blip-box/confusable",
        branch="guild-ledger",
        head="0" * 40,
        message="ledger: triage, builder for #8, #9\n\nRun: u\n",
    )
    assert payload["branch"] == {
        "repositoryNameWithOwner": "blip-box/confusable",
        "branchName": "guild-ledger",
    }
    assert payload["expectedHeadOid"] == "0" * 40
    assert payload["message"] == {
        "headline": "ledger: triage, builder for #8, #9",
        "body": "Run: u\n",
    }
    assert payload["fileChanges"]["deletions"] == []
    (addition,) = payload["fileChanges"]["additions"]
    assert addition["path"] == "ledger.jsonl"
    text = base64.b64decode(addition["contents"]).decode("ascii")
    assert text.startswith(current)
    assert text.count("\n") == 3
    lines = text.splitlines()
    assert json.loads(lines[1])["number"] == 8
    assert json.loads(lines[2])["role"] == "builder"
    # A current file without its final newline still gets whole lines.
    again = ledger.commit_input(
        current.rstrip("\n"),
        [entry(number=8)],
        repo="o/r",
        branch="b",
        head="1" * 40,
        message="m",
    )
    assert (
        base64.b64decode(again["fileChanges"]["additions"][0]["contents"])
        .decode()
        .count("\n")
        == 2
    )
    with pytest.raises(ledger.LedgerError, match="nothing"):
        ledger.commit_input("", [], repo="o/r", branch="b", head="1" * 40, message="m")


def test_report_counts_the_window() -> None:
    entries = [
        entry(at="2026-10-27T00:00:00Z", number=1),
        entry(at="2026-10-28T00:00:00Z", number=2, cost_usd=0.5, cache_read_tokens=800),
        entry(
            at="2026-10-30T00:00:00Z",
            number=2,
            role="builder",
            outcome="patched",
            cost_usd=2.0,
            input_tokens=1000,
            output_tokens=200,
        ),
        entry(
            at="2026-10-31T00:00:00Z",
            number=3,
            outcome="escalated",
            decided_by="steward",
            decider="atillaguzel",
        ),
        entry(at="2026-11-01T00:00:00Z", number=4, outcome="skipped", model="none"),
        entry(at="2026-11-03T00:00:00Z", number=5),
    ]
    data = ledger.report(entries, since="2026-10-28", until="2026-11-03")
    assert data["runs"] == 4
    assert data["issues"] == 3
    assert data["by_role"] == {"builder": 1, "triage": 3}
    assert data["by_outcome"] == {
        "escalated": 1,
        "needs_info": 1,
        "patched": 1,
        "skipped": 1,
    }
    assert data["by_role_outcome"]["triage:needs_info"] == 1
    assert data["cost_usd"] == round(0.5 + 2.0 + 0.00016 * 2, 4)
    assert data["cost_by_role"]["builder"] == 2.0
    assert data["tokens_in"] == 1200 + 800 + 1000 + 1200 + 1200
    assert data["tokens_out"] == 80 + 200 + 80 + 80
    assert data["cache_read_share"] == round(800 / data["tokens_in"], 4)
    assert data["steward_decisions"] == 1
    assert data["escalated"] == 1
    assert data["skipped"] == 1
    assert data["failed"] == 0
    empty = ledger.report([], since="2026-10-28", until="2026-11-03")
    assert empty["runs"] == 0
    assert empty["cache_read_share"] == 0.0
    text = ledger.report_markdown(data)
    assert text.startswith("Guild, 2026-10-28 to 2026-11-03: 4 runs on 3 issues,")
    assert "| builder | 1 | 2.0 |" in text
    assert "| skipped | 1 |" in text
    assert "Skipped by the brakes: 1." in text
    assert text.isascii()
    assert "no model wrote any of it" in text
