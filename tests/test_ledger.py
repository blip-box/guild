from pathlib import Path

import pytest

from guildkit import ledger

ENTRY: ledger.Entry = {
    "at": "2026-10-30T00:00:00Z",
    "repo": "blip-box/confusable",
    "number": 7,
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
    assert line.startswith('{"at":"2026-10-30T00:00:00Z","cache_read_tokens":0,')
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
