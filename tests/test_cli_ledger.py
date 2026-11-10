"""The brake, ledger-input, ledger-report and grade subcommands."""

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from guildkit import cli, ledger
from tests.test_brief import SNAP
from tests.test_ledger import ENTRY


def write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_brake_command(
    tmp_path: Path, example_config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snap = write(tmp_path / "snapshot.json", SNAP)
    entry, post = tmp_path / "entry.json", tmp_path / "post.json"
    argv = [
        "brake",
        "--config",
        str(example_config),
        "--snapshot",
        str(snap),
        "--now",
        "2026-11-04T10:00:00Z",
        "--entry",
        str(entry),
        "--post",
        str(post),
    ]
    # No ledger file: everything goes.
    assert cli.main([*argv, "--ledger", str(tmp_path / "missing.jsonl")]) == 0
    assert "brake: go" in capsys.readouterr().out
    assert not entry.exists()
    # Three of the author's runs today: the author limit.
    path = tmp_path / "ledger.jsonl"
    for hour in (1, 2, 3):
        ledger.append(
            path, {**ENTRY, "at": f"2026-11-04T0{hour}:00:00Z", "author": "someone"}
        )
    assert cli.main([*argv, "--ledger", str(path)]) == 4
    assert "author limit" in capsys.readouterr().out
    skipped = json.loads(entry.read_text(encoding="ascii"))
    assert skipped["outcome"] == "skipped"
    assert skipped["author"] == "someone"
    assert skipped["model"] == "none"
    assert skipped["decided_by"] == "script"
    assert skipped["content_hash"] == SNAP["content_hash"]
    record = json.loads(post.read_text(encoding="ascii"))
    assert record["template"] == "queued"
    assert record["labels"] == ["guild:queued"]
    # Forty runs today by others: the daily limit, for a new author.
    for n in range(40):
        ledger.append(
            path, {**ENTRY, "at": "2026-11-04T05:00:00Z", "author": f"user{n}"}
        )
    other = write(tmp_path / "other.json", {**SNAP, "author": "fresh"})
    assert (
        cli.main(
            [*argv[:3], "--snapshot", str(other), *argv[5:], "--ledger", str(path)]
        )
        == 5
    )
    assert "daily limit" in capsys.readouterr().out


def test_ledger_input_command(tmp_path: Path, example_config: Path) -> None:
    current = tmp_path / "current.jsonl"
    ledger.append(current, ENTRY)
    e1 = write(tmp_path / "entry-triage.json", {**ENTRY, "number": 8})
    e2 = write(
        tmp_path / "entry-builder.json",
        {**ENTRY, "number": 8, "role": "builder", "outcome": "patched"},
    )
    out = tmp_path / "input.json"
    assert (
        cli.main(
            [
                "ledger-input",
                "--config",
                str(example_config),
                "--current",
                str(current),
                "--entry",
                str(e1),
                "--entry",
                str(e2),
                "--head",
                "0" * 40,
                "--run-url",
                "https://example.test/run/9",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="ascii"))["input"]
    assert payload["branch"]["branchName"] == "guild-ledger"
    assert payload["message"]["headline"] == "ledger: builder, triage for #8"
    assert "https://example.test/run/9" in payload["message"]["body"]
    text = base64.b64decode(payload["fileChanges"]["additions"][0]["contents"]).decode(
        "ascii"
    )
    assert text.count("\n") == 3
    bad = write(tmp_path / "bad.json", {**ENTRY, "outcome": "whatever"})
    with pytest.raises(ledger.LedgerError):
        cli.main(
            [
                "ledger-input",
                "--config",
                str(example_config),
                "--entry",
                str(bad),
                "--head",
                "0" * 40,
                "--run-url",
                "u",
                "--out",
                str(out),
            ]
        )


def test_ledger_report_command(tmp_path: Path, example_config: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, {**ENTRY, "at": "2026-11-01T00:00:00Z"})
    ledger.append(
        path,
        {
            **ENTRY,
            "at": "2026-11-02T00:00:00Z",
            "role": "builder",
            "outcome": "patched",
            "cost_usd": 1.5,
        },
    )
    out, data = tmp_path / "report.md", tmp_path / "report.json"
    assert (
        cli.main(
            [
                "ledger-report",
                "--config",
                str(example_config),
                "--ledger",
                str(path),
                "--since",
                "2026-10-29",
                "--until",
                "2026-11-05",
                "--out",
                str(out),
                "--json",
                str(data),
            ]
        )
        == 0
    )
    text = out.read_text(encoding="ascii")
    assert text.startswith("Guild, 2026-10-29 to 2026-11-05: 2 runs on 1 issues,")
    assert (
        json.loads(data.read_text(encoding="ascii"))["cost_by_role"]["builder"] == 1.5
    )


def test_grade_command(tmp_path: Path, example_config: Path) -> None:
    """A steward's `/guild overrule triage` becomes an entry; anyone else's,
    a verdict on nothing, or another command does not."""
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, {**ENTRY, "at": "2026-11-01T00:00:00Z", "number": 7})
    body = tmp_path / "body.md"
    body.write_text("Wrong kind.\n/guild overrule triage\n", encoding="utf-8")
    out = tmp_path / "entry-steward.json"
    args = [
        "grade",
        "--config",
        str(example_config),
        "--ledger",
        str(path),
        "--body",
        str(body),
        "--number",
        "7",
        "--login",
        "atillaguzel",
        "--out",
        str(out),
        "--now",
        "2026-11-05T12:00:00Z",
    ]
    assert cli.main(args) == 0
    entry = ledger.validate(json.loads(out.read_text(encoding="ascii")))
    assert entry["outcome"] == "overruled"
    assert entry["decided_by"] == "steward"
    assert entry["decider"] == "atillaguzel"
    assert entry["content_hash"] == ENTRY["content_hash"]
    assert entry["at"] == "2026-11-05T12:00:00Z"
    assert entry["harness"] == cli.HARNESS
    out.unlink()
    assert cli.main([*args[:8], "8", *args[9:]]) == 1  # nothing to grade on #8
    assert cli.main([*args[:10], "someone", *args[11:]]) == 1  # not a steward
    body.write_text("/guild build\n", encoding="utf-8")
    assert cli.main(args) == 1  # not a grade
    assert not out.exists()


def test_ledger_report_carries_the_shadow_section(
    tmp_path: Path, example_config: Path
) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, {**ENTRY, "at": "2026-11-01T00:00:00Z"})
    ledger.append(
        path,
        {
            **ENTRY,
            "at": "2026-11-02T00:00:00Z",
            "outcome": "confirmed",
            "decided_by": "steward",
            "decider": "atillaguzel",
            "cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        },
    )
    out, data = tmp_path / "report.md", tmp_path / "report.json"
    args = [
        "ledger-report",
        "--config",
        str(example_config),
        "--ledger",
        str(path),
        "--since",
        "2026-10-29",
        "--until",
        "2026-11-05",
        "--out",
        str(out),
        "--json",
        str(data),
        "--canary-passes",
        "3",
    ]
    assert cli.main(args) == 0
    text = out.read_text(encoding="ascii")
    assert "Graded this week: triage 1 confirmed, 0 overruled." in text
    assert "Shadow mode: 0 of 4 conditions met" in text
    assert (
        "| triage decisions graded | 1, 0 overruled | 10, at most 2 overruled | no |"
        in text
    )
    assert "| canary passes in a row | 3 | 4 | no |" in text
    shadow = json.loads(data.read_text(encoding="ascii"))["shadow"]
    assert shadow["roles"]["triage"]["graded"] == 1
    assert shadow["canary_passes"] == 3
    # Without the table, no section and no shadow in the numbers.
    text_without = example_config.read_text(encoding="utf-8")
    start, end = (
        text_without.index("[shadow]"),
        text_without.index("# US dollars per million"),
    )
    plain = tmp_path / "guild.toml"
    plain.write_text(text_without[:start] + text_without[end:], encoding="utf-8")
    assert cli.main([*args[:2], str(plain), *args[3:]]) == 0
    assert "Shadow mode" not in out.read_text(encoding="ascii")
    assert json.loads(data.read_text(encoding="ascii"))["shadow"] is None
