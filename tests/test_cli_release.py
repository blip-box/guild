"""The release, release-entry and config-get subcommands."""

import json
from pathlib import Path
from typing import Any

import pytest

from guildkit import cli, ledger
from tests.test_ledger import ENTRY
from tests.test_releaser import LOG, SHA

ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_release_command(
    tmp_path: Path, example_config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "log.txt"
    log.write_text(LOG, encoding="ascii")
    entries = tmp_path / "ledger.jsonl"
    ledger.append(
        entries,
        {
            **ENTRY,
            "number": 7,
            "role": "builder",
            "outcome": "patched",
            "author": "reporter",
        },
    )
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nversion = "0.1.0.dev0"\n', encoding="ascii"
    )
    out = tmp_path / "out"
    out.mkdir()
    argv = [
        "release",
        "--config",
        str(example_config),
        "--log",
        str(log),
        "--ledger",
        str(entries),
        "--last-tag",
        "",
        "--pyproject",
        str(pyproject),
        "--head",
        SHA[1],
        "--today",
        "2026-11-05",
        "--tests-exit",
        "0",
        "--templates",
        str(ROOT / "templates" / "release"),
        "--run-url",
        "https://example.invalid/run",
        "--out",
        str(out / "proposal.json"),
        "--out-title",
        str(out / "title.txt"),
        "--out-body",
        str(out / "body.md"),
    ]
    assert cli.main(argv) == 0
    assert capsys.readouterr().out.startswith("Release 0.1.0a1 due: a breaking change")
    proposal = json.loads((out / "proposal.json").read_text(encoding="ascii"))
    assert proposal["due"] is True
    assert proposal["version"] == "0.1.0a1"
    assert proposal["credits"] == ["reporter"]
    assert (out / "title.txt").read_text(
        encoding="ascii"
    ) == "Release 0.1.0a1 proposed\n"
    body = (out / "body.md").read_text(encoding="ascii")
    assert "Reports from reporter" in body
    assert "`pyproject.toml`, `src/confusable/__init__.py`" in body

    # Not due: only a tooling fix, merged today.
    log.write_text(
        f"commit\t{SHA[2]}\t2026-11-04T10:00:00+00:00\t"
        "fix(tools): stop a form field at a label (#31)\n\n"
        "tools/guild_oracle_check.py\n",
        encoding="ascii",
    )
    argv[argv.index("--last-tag") + 1] = "v0.1.0a1"
    assert cli.main(argv) == 4
    assert capsys.readouterr().out.startswith("Release 0.1.0a2 not due")
    assert (
        json.loads((out / "proposal.json").read_text(encoding="ascii"))["due"] is False
    )

    # A bad input is an error, not a proposal.
    log.write_text("commit\tnot-a-sha\t2026\tfix: x\n", encoding="ascii")
    assert cli.main(argv) == 2
    assert "release: log line" in capsys.readouterr().err
    argv[argv.index("--head") + 1] = "HEAD"
    log.write_text(LOG, encoding="ascii")
    assert cli.main(argv) == 2

    # Without a ledger file the credits are empty.
    argv[argv.index("--head") + 1] = SHA[1]
    argv[argv.index("--ledger") + 1] = str(tmp_path / "missing.jsonl")
    assert cli.main(argv) == 0
    assert (
        json.loads((out / "proposal.json").read_text(encoding="ascii"))["credits"] == []
    )

    # The step summary and the ledger entry.
    assert (
        cli.main(["summary", "--kind", "release", "--file", str(out / "proposal.json")])
        == 0
    )
    assert capsys.readouterr().out.startswith("Release 0.1.0a2 due")
    latest = json.loads((out / "proposal.json").read_text(encoding="ascii"))
    entry = tmp_path / "entry.json"
    assert (
        cli.main(
            [
                "release-entry",
                "--config",
                str(example_config),
                "--proposal",
                str(out / "proposal.json"),
                "--number",
                "41",
                "--out",
                str(entry),
            ]
        )
        == 0
    )
    record = json.loads(entry.read_text(encoding="ascii"))
    ledger.validate(record)
    assert record["role"] == "releaser"
    assert record["number"] == 41
    assert record["model"] == "none"
    assert record["outcome"] == "posted"
    assert record["decided_by"] == "script"
    assert record["cost_usd"] == 0.0
    assert record["content_hash"] == latest["content_hash"]
    assert record["content_hash"] != proposal["content_hash"]


def test_config_get_command(
    example_config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(["config-get", "--config", str(example_config), "test_command"]) == 0
    )
    assert capsys.readouterr().out == "uv run --no-sync pytest -q -x\n"
