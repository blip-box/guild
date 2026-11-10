import json
from pathlib import Path

from guildkit import cli

EVENT = {
    "issue": {
        "number": 7,
        "id": 1,
        "title": "match() misses p\u0430ypal",
        "body": "Expected MIXED_SCRIPT, got None. Version 0.1.0.dev0.",
        "user": {"login": "someone"},
        "author_association": "NONE",
        "created_at": "2026-10-30T00:00:00Z",
        "updated_at": "2026-10-30T00:00:00Z",
        "labels": [],
    }
}


def test_snapshot_tier_triage_render_pipeline(
    tmp_path: Path, root: Path, example_config: Path
) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps(EVENT), encoding="utf-8")
    snap = tmp_path / "snapshot.json"
    assert (
        cli.main(
            [
                "snapshot",
                "--repo",
                "blip-box/confusable",
                "--event",
                str(event),
                "--out",
                str(snap),
            ]
        )
        == 0
    )
    data = json.loads(snap.read_text(encoding="ascii"))
    assert data["title"] == "match() misses pU+0430ypal"

    reply = tmp_path / "reply.txt"
    reply.write_text(
        '{"kind": "bug", "severity": "high", "clause": "UTS #39 section 4",'
        ' "missing": []}',
        encoding="ascii",
    )
    record, entry = tmp_path / "record.json", tmp_path / "entry.json"
    assert (
        cli.main(
            [
                "triage",
                "--config",
                str(example_config),
                "--snapshot",
                str(snap),
                "--role",
                str(root / "roles" / "triage.md"),
                "--oracle",
                "confirms",
                "--reply",
                str(reply),
                "--out",
                str(record),
                "--ledger-entry",
                str(entry),
            ]
        )
        == 0
    )
    rec = json.loads(record.read_text(encoding="ascii"))
    assert rec["actionable"] is True
    ent = json.loads(entry.read_text(encoding="ascii"))
    assert ent["outcome"] == "posted"
    assert ent["citation"] == "UTS #39 section 4"
    assert ent["content_hash"] == data["content_hash"]

    comment, labels = tmp_path / "comment.md", tmp_path / "labels.json"
    assert (
        cli.main(
            [
                "render",
                "--record",
                str(record),
                "--templates",
                str(root / "templates" / "comments"),
                "--decision-url",
                "https://x.test/run/1",
                "--charter-url",
                "https://x.test/CHARTER.md",
                "--out-comment",
                str(comment),
                "--out-labels",
                str(labels),
            ]
        )
        == 0
    )
    assert (
        "accepted as a bug under UTS #39 section 4 with severity high"
        in comment.read_text(encoding="ascii")
    )
    assert json.loads(labels.read_text(encoding="ascii")) == [
        "guild:bug",
        "severity:high",
    ]

    ledger_file = tmp_path / "ledger.jsonl"
    assert (
        cli.main(["ledger-append", "--ledger", str(ledger_file), "--entry", str(entry)])
        == 0
    )
    assert ledger_file.read_text(encoding="ascii").count("\n") == 1


def test_tier_from_paths_and_numstat(tmp_path: Path, example_config: Path) -> None:
    paths = tmp_path / "paths.txt"
    paths.write_text("README.md\ntests/test_x.py\n", encoding="ascii")
    numstat = tmp_path / "numstat.txt"
    numstat.write_text(
        "3\t1\tREADME.md\n0\t4\ttests/test_x.py\n-\t-\timage.png\n", encoding="ascii"
    )
    out = tmp_path / "decision.json"
    assert (
        cli.main(
            [
                "tier",
                "--config",
                str(example_config),
                "--paths",
                str(paths),
                "--numstat",
                str(numstat),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    decision = json.loads(out.read_text(encoding="ascii"))
    assert decision["tier"] == "T2"
    assert "lines deleted under tests: at least T2" in decision["reasons"]


def test_tier_rejects_harness_paths(tmp_path: Path, example_config: Path) -> None:
    paths = tmp_path / "paths.txt"
    paths.write_text(
        ".github/workflows/ci.yml\nsrc/confusable/_skeleton.py\n", encoding="ascii"
    )
    out = tmp_path / "decision.json"
    assert (
        cli.main(
            [
                "tier",
                "--config",
                str(example_config),
                "--paths",
                str(paths),
                "--kind",
                "public_api",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    decision = json.loads(out.read_text(encoding="ascii"))
    assert decision["rejected"] == [".github/workflows/ci.yml"]
    assert decision["tier"] == "T2"


def test_command(tmp_path: Path, capsys: object) -> None:
    body = tmp_path / "body.md"
    body.write_text("/guild reject C-OUT-2\n", encoding="ascii")
    assert cli.main(["command", "--body", str(body)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out) == {
        "verb": "reject",
        "clause": "C-OUT-2",
        "role": None,
    }


def test_triage_without_a_key_fails_cleanly(
    tmp_path: Path, root: Path, example_config: Path, monkeypatch: object
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # type: ignore[attr-defined]
    snap = tmp_path / "snapshot.json"
    snap.write_text(
        json.dumps(
            {
                "number": 1,
                "content_hash": "a" * 64,
                "repo": "r/r",
                "kind": "issue",
                "author_association": "NONE",
                "labels": [],
                "hidden": [],
                "dropped": 0,
                "title": "t",
                "body": "b",
                "comment_id": None,
                "author": "a",
                "created_at": "c",
            }
        ),
        encoding="ascii",
    )
    code = cli.main(
        [
            "triage",
            "--config",
            str(example_config),
            "--snapshot",
            str(snap),
            "--role",
            str(root / "roles" / "triage.md"),
            "--oracle",
            "not_run",
            "--out",
            str(tmp_path / "r.json"),
            "--ledger-entry",
            str(tmp_path / "e.json"),
        ]
    )
    assert code == 2
