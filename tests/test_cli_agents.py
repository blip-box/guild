"""The agent, check and pull request subcommands, with a fake Agent SDK runner."""

import base64
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ResultMessage

from guildkit import cli
from tests.test_brief import PLAN, RECORD, SNAP

FEATURE_RECORD: dict[str, Any] = {
    **RECORD,
    "kind": "feature",
    "clause": "C-SCOPE-5",
    "severity": "none",
    "template": "feature_accepted",
    "labels": ["guild:feature"],
}
FEATURE_SNAP: dict[str, Any] = {
    **SNAP,
    "body": (
        "The problem\nI cannot do X.\nThe behaviour you want\nA function.\n"
        "Charter clause\nC-SCOPE-5\nSpecification\nUTS #39 section 4\n"
    ),
}
DIFF = (
    "diff --git a/src/confusable/_skeleton.py b/src/confusable/_skeleton.py\n"
    "--- a/src/confusable/_skeleton.py\n+++ b/src/confusable/_skeleton.py\n"
    "@@ -1 +1 @@\n-old\n+new\n"
    "diff --git a/tests/test_skeleton.py b/tests/test_skeleton.py\n"
    "--- a/tests/test_skeleton.py\n+++ b/tests/test_skeleton.py\n"
    "@@ -1 +1,2 @@\n context\n+def test_more(): ...\n"
)
RUN_OK: dict[str, Any] = {
    "role": "builder",
    "model": "claude-opus-5-5",
    "subtype": "success",
    "is_error": False,
    "num_turns": 4,
    "duration_ms": 30_000,
    "usage": {
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    },
    "cost_usd": 0.0006,
    "reported_cost_usd": 0.0007,
    "tool_calls": {"Edit": 2, "Read": 3},
    "denials": 0,
    "repeated": False,
    "test_rounds_blocked": 0,
    "tests_passed": True,
    "structured_output": None,
}


def write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Handbook\nBe careful.\n", encoding="ascii")
    (root / "CHARTER.md").write_text("**C-SCOPE-5** Do it.\n", encoding="ascii")
    return root


@pytest.fixture
def test_config(tmp_path: Path, example_config: Path) -> Path:
    text = example_config.read_text(encoding="utf-8")
    old = 'test_command = "uv run --no-sync pytest -q -x"'
    assert old in text
    passing = f'test_command = "{sys.executable} -c pass"'
    path = tmp_path / "guild.toml"
    path.write_text(text.replace(old, passing), encoding="utf-8")
    return path


def result(**overrides: Any) -> ResultMessage:
    base: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1000,
        "duration_api_ms": 800,
        "is_error": False,
        "num_turns": 2,
        "session_id": "s",
        "total_cost_usd": 0.01,
        "usage": {"input_tokens": 500, "output_tokens": 50},
    }
    base.update(overrides)
    return ResultMessage(**base)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {"messages": []}

    async def runner(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        seen["prompt"] = prompt
        seen["options"] = options
        for message in seen["messages"]:
            yield message

    monkeypatch.setattr(cli, "RUNNER", runner)
    return seen


def agent_args(root: Path, cfg: Path, out: Path, role: str) -> list[str]:
    return [
        "--config",
        str(cfg),
        "--root",
        str(root),
        "--role",
        str(Path(__file__).resolve().parents[1] / "roles" / f"{role}.md"),
        "--handbook",
        str(root / "AGENTS.md"),
        "--charter",
        str(root / "CHARTER.md"),
        "--run",
        str(out / "run.json"),
        "--transcript",
        str(out / "transcript.jsonl"),
        "--decider",
        "atillaguzel",
    ]


def test_brief_command(tmp_path: Path) -> None:
    snap = write(tmp_path / "snapshot.json", SNAP)
    record = write(tmp_path / "record.json", RECORD)
    out = tmp_path / "brief.json"
    argv = [
        "brief",
        "--snapshot",
        str(snap),
        "--record",
        str(record),
        "--out",
        str(out),
    ]
    assert cli.main(argv) == 0
    data = json.loads(out.read_text(encoding="ascii"))
    assert data["kind"] == "bug"
    assert data["fields"]["Function called"] == "skeleton"
    write(record, {**RECORD, "actionable": False})
    assert cli.main(argv) == 4
    plan = write(tmp_path / "plan.json", PLAN)
    write(record, FEATURE_RECORD)
    assert cli.main([*argv, "--plan", str(plan)]) == 0
    assert json.loads(out.read_text(encoding="ascii"))["plan"]["status"] == "plan"


def test_steward_command(example_config: Path) -> None:
    argv = ["steward", "--config", str(example_config), "--login"]
    assert cli.main([*argv, "atillaguzel"]) == 0
    assert cli.main([*argv, "someone"]) == 1


def test_patch_check_command(tmp_path: Path, example_config: Path) -> None:
    brief = write(tmp_path / "brief.json", {**json.loads(json.dumps(SNAP)), **{}})
    brief = write(
        tmp_path / "brief.json",
        {
            "repo": "blip-box/confusable",
            "number": 7,
            "kind": "bug",
            "clause": "UTS #39 section 4",
            "severity": "high",
            "content_hash": "a" * 64,
            "fields": {},
            "plan": None,
        },
    )
    run = write(tmp_path / "run.json", RUN_OK)
    diff = tmp_path / "patch.diff"
    diff.write_text(DIFF, encoding="ascii")
    out, entry = tmp_path / "check.json", tmp_path / "entry.json"
    argv = [
        "patch-check",
        "--config",
        str(example_config),
        "--brief",
        str(brief),
        "--diff",
        str(diff),
        "--run",
        str(run),
        "--out",
        str(out),
        "--ledger-entry",
        str(entry),
        "--decider",
        "atillaguzel",
    ]
    assert cli.main(argv) == 0
    check = json.loads(out.read_text(encoding="ascii"))
    assert check["ok"] is True
    assert check["tier"] == "T1"
    assert check["run_ok"] is True
    ledger_entry = json.loads(entry.read_text(encoding="ascii"))
    assert ledger_entry["outcome"] == "patched"
    assert ledger_entry["role"] == "builder"
    assert ledger_entry["decider"] == "atillaguzel"
    assert ledger_entry["citation"] == "UTS #39 section 4"
    assert ledger_entry["cost_usd"] == 0.0006

    diff.write_text(
        DIFF + "diff --git a/AGENTS.md b/AGENTS.md\n--- a/AGENTS.md\n+++ b/AGENTS.md\n"
        "@@ -1 +1 @@\n-a\n+b\n",
        encoding="ascii",
    )
    assert cli.main(argv) == 5
    check = json.loads(out.read_text(encoding="ascii"))
    assert check["failures"] == ["reject list: AGENTS.md"]
    assert check["attempt"] == 1
    assert check["escalate"] is True  # the example config has a second attempt
    ledger_entry = json.loads(entry.read_text(encoding="ascii"))
    assert ledger_entry["outcome"] == "failed"
    assert ledger_entry["attempt"] == 1
    assert cli.main([*argv, "--attempt", "2"]) == 5
    check = json.loads(out.read_text(encoding="ascii"))
    assert check["attempt"] == 2
    assert check["escalate"] is False
    assert json.loads(entry.read_text(encoding="ascii"))["attempt"] == 2

    diff.write_text(DIFF, encoding="ascii")
    write(run, {**RUN_OK, "tests_passed": False})
    assert cli.main(argv) == 5
    check = json.loads(out.read_text(encoding="ascii"))
    assert check["run_ok"] is False
    assert check["failures"] == []
    assert check["escalate"] is True

    # No second attempt configured: nothing to escalate to.
    text = example_config.read_text(encoding="utf-8")
    start, end = text.index("[builder.second_attempt]"), text.index("[reviewer]")
    one = tmp_path / "one.toml"
    one.write_text(text[:start] + text[end:], encoding="utf-8")
    argv[argv.index("--config") + 1] = str(one)
    assert cli.main(argv) == 5
    assert json.loads(out.read_text(encoding="ascii"))["escalate"] is False


def test_commit_input_command(tmp_path: Path, example_config: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a.txt").write_text("changed\n", encoding="ascii")
    (root / "new.bin").write_bytes(b"\x00\x01\xff")
    (root / "moved.txt").write_text("moved\n", encoding="ascii")
    status = tmp_path / "status.txt"
    status.write_text(
        "M\ta.txt\nA\tnew.bin\nD\tgone.txt\nR100\told.txt\tmoved.txt\n",
        encoding="ascii",
    )
    message = tmp_path / "message.txt"
    message.write_text("fix: resolve #7 under Guild\n\nBody line.\n\nAssisted-by: x\n")
    out = tmp_path / "input.json"
    assert (
        cli.main(
            [
                "commit-input",
                "--config",
                str(example_config),
                "--root",
                str(root),
                "--name-status",
                str(status),
                "--branch",
                "guild/issue-7",
                "--head",
                "0" * 40,
                "--message",
                str(message),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    data = json.loads(out.read_text(encoding="ascii"))["input"]
    assert data["branch"] == {
        "repositoryNameWithOwner": "blip-box/confusable",
        "branchName": "guild/issue-7",
    }
    assert data["expectedHeadOid"] == "0" * 40
    assert data["message"] == {
        "headline": "fix: resolve #7 under Guild",
        "body": "Body line.\n\nAssisted-by: x\n",
    }
    additions = {a["path"]: a["contents"] for a in data["fileChanges"]["additions"]}
    assert set(additions) == {"a.txt", "new.bin", "moved.txt"}
    assert base64.b64decode(additions["new.bin"]) == b"\x00\x01\xff"
    assert data["fileChanges"]["deletions"] == [
        {"path": "gone.txt"},
        {"path": "old.txt"},
    ]


def test_pr_text_command(tmp_path: Path, example_config: Path, root: Path) -> None:
    brief = write(
        tmp_path / "brief.json",
        {
            "repo": "blip-box/confusable",
            "number": 7,
            "kind": "bug",
            "clause": "UTS #39 section 4",
            "severity": "high",
            "content_hash": "a" * 64,
            "fields": {},
            "plan": None,
        },
    )
    check = write(tmp_path / "check.json", {"ok": True, "tier": "T1"})
    review = write(
        tmp_path / "review.json",
        {"verdict": "no_objection", "objections": 0, "notes": 1},
    )
    title, body, message = (
        tmp_path / n for n in ("title.txt", "body.md", "message.txt")
    )
    assert (
        cli.main(
            [
                "pr-text",
                "--config",
                str(example_config),
                "--brief",
                str(brief),
                "--check",
                str(check),
                "--review",
                str(review),
                "--run-url",
                "https://example.test/run/1",
                "--templates",
                str(root / "templates" / "pr"),
                "--out-title",
                str(title),
                "--out-body",
                str(body),
                "--out-message",
                str(message),
            ]
        )
        == 0
    )
    assert title.read_text(encoding="ascii") == "fix: resolve #7 under Guild\n"
    text = body.read_text(encoding="ascii")
    assert "Tier: T1." in text
    assert "no_objection, 0 objections and 1 notes" in text
    assert "https://example.test/run/1" in text
    assert "Closes #7." in text
    commit = message.read_text(encoding="ascii")
    assert commit.startswith("fix: resolve #7 under Guild\n\n")
    assert commit.rstrip().endswith("Assisted-by: Guild builder (claude-opus-5-5)")
    assert "{" not in text + commit


def test_summary_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = write(tmp_path / "run.json", RUN_OK)
    assert cli.main(["summary", "--kind", "run", "--file", str(run)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Run: success, 4 turns, 30 s, 0.0006 USD")
    assert "- Edit: 2" in out
    check = write(
        tmp_path / "check.json",
        {
            "ok": False,
            "tier": "T1",
            "failures": ["reject list: AGENTS.md"],
            "reasons": [],
        },
    )
    assert cli.main(["summary", "--kind", "check", "--file", str(check)]) == 0
    assert (
        "Patch check: failed, tier T1.\n- reject list: AGENTS.md"
        in capsys.readouterr().out
    )
    plan = write(tmp_path / "plan.json", {"status": "failed"})
    assert cli.main(["summary", "--kind", "plan", "--file", str(plan)]) == 0
    assert "did not return a plan" in capsys.readouterr().out
    review = write(
        tmp_path / "review.json",
        {"verdict": "no_objection", "objections": 0, "notes": 0, "findings": []},
    )
    assert cli.main(["summary", "--kind", "review", "--file", str(review)]) == 0
    assert "No findings." in capsys.readouterr().out


def test_build_command_runs_the_builder(
    checkout: Path, test_config: Path, tmp_path: Path, fake: dict[str, Any]
) -> None:
    fake["messages"] = [result()]
    brief = write(
        tmp_path / "brief.json",
        {
            "repo": "blip-box/confusable",
            "number": 7,
            "kind": "bug",
            "clause": "UTS #39 section 4",
            "severity": "high",
            "content_hash": "a" * 64,
            "fields": {"Code points": "U+0430", "Function called": "skeleton"},
            "plan": None,
        },
    )
    out = tmp_path / "out"
    out.mkdir()
    argv = [
        "build",
        *agent_args(checkout, test_config, out, "builder"),
        "--brief",
        str(brief),
    ]
    assert cli.main(argv) == 0
    run = json.loads((out / "run.json").read_text(encoding="ascii"))
    assert run["role"] == "builder"
    assert run["model"] == "claude-opus-5-5"
    assert run["subtype"] == "success"
    assert run["usage"]["input_tokens"] == 500
    assert run["cost_usd"] == 0.003  # 500 * 4 + 50 * 20 per million
    assert (out / "transcript.jsonl").read_text(encoding="ascii").count("\n") == 1
    options = fake["options"]
    assert options.setting_sources == []
    assert options.cwd == checkout
    assert options.model == "claude-opus-5-5"
    assert options.max_turns == 80
    assert "Be careful." in options.system_prompt
    assert "**C-SCOPE-5** Do it." in options.system_prompt
    assert fake["prompt"].startswith("Repository: blip-box/confusable\nIssue: #7\n")
    assert "Code points: U+0430" in fake["prompt"]
    assert set(options.hooks) == {"PreToolUse", "Stop"}
    assert options.effort == "high"

    # The second attempt: the escalated setting, and what the check said.
    first_check = write(
        tmp_path / "check.json",
        {"ok": False, "failures": ["reject list: AGENTS.md"], "run_ok": True},
    )
    first_run = write(tmp_path / "first-run.json", {**RUN_OK, "subtype": "success"})
    argv += [
        "--second-attempt",
        "--previous",
        str(first_check),
        "--previous-run",
        str(first_run),
    ]
    assert cli.main(argv) == 0
    options = fake["options"]
    assert options.effort == "max"
    assert options.max_turns == 100
    assert options.max_budget_usd == 6.0
    assert fake["prompt"].startswith("Repository: blip-box/confusable\nIssue: #7\n")
    assert "# A previous attempt" in fake["prompt"]
    assert (
        "- the plain check refused the patch: reject list: AGENTS.md" in fake["prompt"]
    )
    run = json.loads((out / "run.json").read_text(encoding="ascii"))
    assert run["role"] == "builder"

    # Without the table there is no second attempt.
    text = test_config.read_text(encoding="utf-8")
    start, end = text.index("[builder.second_attempt]"), text.index("[reviewer]")
    one = tmp_path / "one.toml"
    one.write_text(text[:start] + text[end:], encoding="utf-8")
    argv[argv.index("--config") + 1] = str(one)
    assert cli.main(argv) == 4


def test_review_command_validates_and_judges(
    checkout: Path, test_config: Path, tmp_path: Path, fake: dict[str, Any]
) -> None:
    findings = {
        "findings": [
            {
                "kind": "correctness",
                "clause": None,
                "file": "src/confusable/_skeleton.py",
                "line": 1,
                "verified": True,
                "summary": "Wrong.",
            }
        ]
    }
    fake["messages"] = [result(structured_output=findings)]
    brief = write(
        tmp_path / "brief.json",
        {
            "repo": "blip-box/confusable",
            "number": 7,
            "kind": "bug",
            "clause": "UTS #39 section 4",
            "severity": "high",
            "content_hash": "a" * 64,
            "fields": {},
            "plan": None,
        },
    )
    diff = tmp_path / "patch.diff"
    diff.write_text(DIFF, encoding="ascii")
    out = tmp_path / "out"
    out.mkdir()
    argv = [
        "review",
        *agent_args(checkout, test_config, out, "reviewer"),
        "--brief",
        str(brief),
        "--diff",
        str(diff),
        "--out",
        str(out / "review.json"),
        "--ledger-entry",
        str(out / "entry.json"),
    ]
    assert cli.main(argv) == 0
    review = json.loads((out / "review.json").read_text(encoding="ascii"))
    assert review["verdict"] == "objections"
    assert review["objections"] == 1
    entry = json.loads((out / "entry.json").read_text(encoding="ascii"))
    assert entry["role"] == "reviewer"
    assert entry["outcome"] == "reviewed"
    assert "# The patch" in fake["prompt"]
    assert "+def test_more(): ..." in fake["prompt"]
    assert fake["options"].output_format["schema"]["required"] == ["findings"]
    assert set(fake["options"].hooks) == {"PreToolUse"}

    fake["messages"] = [result(structured_output={"verdict": "fine"})]
    assert cli.main(argv) == 5
    assert (
        json.loads((out / "review.json").read_text(encoding="ascii"))["verdict"]
        == "failed"
    )
    assert (
        json.loads((out / "entry.json").read_text(encoding="ascii"))["outcome"]
        == "failed"
    )


def test_plan_command_posts_by_status(
    checkout: Path, test_config: Path, tmp_path: Path, fake: dict[str, Any]
) -> None:
    plan_output = {k: v for k, v in PLAN.items() if k != "outcome"}
    fake["messages"] = [result(structured_output=plan_output)]
    snap = write(tmp_path / "snapshot.json", FEATURE_SNAP)
    record = write(tmp_path / "record.json", FEATURE_RECORD)
    out = tmp_path / "out"
    out.mkdir()
    argv = [
        "plan",
        *agent_args(checkout, test_config, out, "planner"),
        "--snapshot",
        str(snap),
        "--record",
        str(record),
        "--out",
        str(out / "plan.json"),
        "--post",
        str(out / "post.json"),
        "--ledger-entry",
        str(out / "entry.json"),
    ]
    assert cli.main(argv) == 0
    plan = json.loads((out / "plan.json").read_text(encoding="ascii"))
    assert plan["status"] == "plan"
    assert plan["outcome"] == "planned"
    post = json.loads((out / "post.json").read_text(encoding="ascii"))
    assert post["template"] == "plan_ready"
    assert post["labels"] == ["guild:planned"]
    assert post["clause"] == "C-SCOPE-5"
    entry = json.loads((out / "entry.json").read_text(encoding="ascii"))
    assert entry["role"] == "planner"
    assert entry["outcome"] == "planned"
    assert entry["citation"] == "C-SCOPE-5"
    assert "The problem:\nI cannot do X." in fake["prompt"]
    assert fake["options"].tools == ["Read", "Glob", "Grep"]

    asking = {**plan_output, "status": "needs_clarification", "questions": ["Which?"]}
    fake["messages"] = [result(structured_output=asking)]
    assert cli.main(argv) == 0
    assert json.loads((out / "post.json").read_text(encoding="ascii"))["template"] == (
        "plan_needs_clarification"
    )

    fake["messages"] = [result(structured_output={"status": "plan"})]
    assert cli.main(argv) == 5
    assert json.loads((out / "plan.json").read_text(encoding="ascii")) == {
        "status": "failed"
    }
    assert json.loads((out / "post.json").read_text(encoding="ascii"))["template"] == (
        "needs_steward"
    )
    assert (
        json.loads((out / "entry.json").read_text(encoding="ascii"))["outcome"]
        == "failed"
    )

    write(record, RECORD)
    assert cli.main(argv) == 4


def test_agent_commands_need_a_credential(
    checkout: Path, test_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in cli.CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "RUNNER", None)
    brief = write(
        tmp_path / "brief.json",
        {
            "repo": "blip-box/confusable",
            "number": 7,
            "kind": "bug",
            "clause": None,
            "severity": "high",
            "content_hash": "a" * 64,
            "fields": {},
            "plan": None,
        },
    )
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(SystemExit) as info:
        cli.main(
            [
                "build",
                *agent_args(checkout, test_config, out, "builder"),
                "--brief",
                str(brief),
            ]
        )
    assert info.value.code == 2
