"""The release, release-entry, release-close and config-get subcommands."""

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


def test_release_close_command(
    tmp_path: Path, example_config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """After the tag, a run that finds nothing due closes the open proposal:
    as completed when it shipped, as not planned otherwise; an in-progress
    run refuses to."""
    log = tmp_path / "log.txt"
    log.write_text("", encoding="ascii")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nversion = "0.1.0a3"\n', encoding="ascii"
    )
    out = tmp_path / "out"
    out.mkdir()
    release = [
        "release",
        "--config",
        str(example_config),
        "--log",
        str(log),
        "--last-tag",
        "v0.1.0a3",
        "--pyproject",
        str(pyproject),
        "--head",
        SHA[6],
        "--today",
        "2026-11-10",
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
    assert cli.main(release) == 4
    assert capsys.readouterr().out.startswith("Release 0.1.0a4 not due:")
    proposal = json.loads((out / "proposal.json").read_text(encoding="ascii"))
    assert proposal["due"] is False
    assert proposal["in_progress"] is False
    title = tmp_path / "title.txt"
    title.write_text("Release 0.1.0a3 proposed\n", encoding="utf-8")
    close = [
        "release-close",
        "--title",
        str(title),
        "--last-tag",
        "v0.1.0a3",
        "--proposal",
        str(out / "proposal.json"),
        "--templates",
        str(ROOT / "templates" / "release"),
        "--run-url",
        "https://example.invalid/run",
        "--out-comment",
        str(out / "comment.md"),
        "--out-reason",
        str(out / "reason.txt"),
    ]
    assert cli.main(close) == 0
    assert (
        capsys.readouterr().out
        == "close as completed: this release shipped as v0.1.0a3\n"
    )
    assert (out / "reason.txt").read_text(encoding="ascii") == "completed\n"
    comment = (out / "comment.md").read_text(encoding="ascii")
    assert comment.startswith(
        "Guild closes this proposal: this release shipped as v0.1.0a3."
    )
    assert "Decision record: https://example.invalid/run" in comment
    title.write_text("Release 0.1.0a4 proposed\n", encoding="utf-8")
    assert cli.main(close) == 0
    assert (out / "reason.txt").read_text(encoding="ascii") == "not planned\n"
    assert "no longer due" in (out / "comment.md").read_text(encoding="ascii")
    # The closed proposal's ledger entry.
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
                "57",
                "--outcome",
                "declined",
                "--out",
                str(entry),
            ]
        )
        == 0
    )
    record = ledger.validate(json.loads(entry.read_text(encoding="ascii")))
    assert (record["role"], record["outcome"], record["number"]) == (
        "releaser",
        "declined",
        57,
    )
    # In progress: the bump is merged, the tag is not. Nothing proposed, nothing closed.
    release[release.index("--last-tag") + 1] = "v0.1.0a2"
    capsys.readouterr()
    assert cli.main(release) == 4
    out_text = capsys.readouterr().out
    assert out_text.startswith(
        "Release 0.1.0a3 in progress: the version files already name 0.1.0a3,"
        " newer than v0.1.0a2: a release is in progress, awaiting its tag."
    )
    assert (
        json.loads((out / "proposal.json").read_text(encoding="ascii"))["in_progress"]
        is True
    )
    close[close.index("--last-tag") + 1] = "v0.1.0a2"
    assert cli.main(close) == 2
    assert "the proposal stands" in capsys.readouterr().err
