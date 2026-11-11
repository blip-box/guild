"""The drill runner: files, graders, stripped checkouts, runs with fakes, scores."""

import json
import re
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ResultMessage

from guildkit import cli, config, drills, grader, triage

ROOT = Path(__file__).resolve().parents[1]
DRILLS = ROOT / "drills" / "confusable"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture
def source(tmp_path: Path) -> tuple[Path, str, str]:
    """A repository with a base commit and a later fix, tagged."""
    repo = tmp_path / "source"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    (repo / "AGENTS.md").write_text("# Handbook\nBe careful.\n", encoding="ascii")
    (repo / "CHARTER.md").write_text("**C-SCOPE-1** Do it.\n", encoding="ascii")
    (repo / "src").mkdir()
    (repo / "src" / "x.py").write_text("def f():\n    return 1\n", encoding="ascii")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("def test_f(): ...\n", encoding="ascii")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "base", cwd=repo)
    base = git("rev-parse", "HEAD", cwd=repo).strip()
    (repo / "src" / "x.py").write_text("def f():\n    return 2\n", encoding="ascii")
    (repo / "tests" / "test_future.py").write_text("FUTURE = 1\n", encoding="ascii")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "the fix", cwd=repo)
    fix = git("rev-parse", "HEAD", cwd=repo).strip()
    git("tag", "v1", cwd=repo)
    return repo, base, fix


def test_the_shipped_drills_load() -> None:
    names = {
        suite: [d["name"] for d in drills.load(DRILLS, suite)]
        for suite in drills.SUITES
    }
    assert "bug-confirmed-paypal" in names["triage"]
    assert "injection-in-a-bug-report" in names["triage"]
    assert names["review"] == ["replay-oracle-check-fields", "seeded-bidi-fast-path"]
    assert names["build"] == ["seeded-bidi-fast-path"]
    for suite in drills.SUITES:
        for drill in drills.load(DRILLS, suite):
            assert drill["repo"] == "blip-box/confusable"
            assert drill["created"] >= "2026-11-03"
    build = drills.load(DRILLS, "build")[0]
    assert [c["id"] for c in build["rubric"]] == [
        "fast-path-classes",
        "departure-explained",
        "pinned-by-test",
        "nothing-else",
    ]
    # The seeded drills share their base commit, the one the seed applies to.
    review = {d["name"]: d for d in drills.load(DRILLS, "review")}
    assert review["seeded-bidi-fast-path"]["input"]["base"] == build["input"]["base"]


def test_shipped_diffs_keep_their_context_lines() -> None:
    """A blank context line is one space; a whitespace hook must not trim it."""
    for path in sorted(DRILLS.rglob("*.diff")):
        in_hunk = False
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if line.startswith("@@"):
                in_hunk = True
            elif line.startswith(("diff ", "index ", "--- ", "+++ ")):
                in_hunk = False
            elif in_hunk and line:
                assert line[0] in " +-\\", f"{path.name}:{number}: {line!r}"
            elif in_hunk and not line:
                assert number == path.read_text(encoding="utf-8").count("\n") + 1, (
                    f"{path.name}:{number}: a blank line inside a hunk"
                )


def test_injection_drill_carries_hidden_characters() -> None:
    drill = next(
        d
        for d in drills.load(DRILLS, "triage")
        if d["name"] == "injection-in-a-bug-report"
    )
    body = drill["input"]["body"]
    assert chr(0x200B) in body
    assert chr(0x202E) in body
    # A negative drill: the report is never accepted, by any of three routes.
    assert drill["expect"]["actionable"] is False
    assert drill["expect"]["template"] == ["needs_info", "spam", "needs_steward"]
    assert drill["expect"]["kind"] == ["bug", "spam", "other"]


@pytest.mark.parametrize(
    ("suite", "text", "message"),
    [
        ("triage", "not toml [", "not TOML"),
        ("triage", "[drill]\nname = 'x'\n", "missing"),
        (
            "triage",
            "[drill]\nname='a b'\ncreated='2026-11-03'\nrepo='o/r'\n"
            "[input]\n[expect]\n",
            "letters",
        ),
        (
            "triage",
            "[drill]\nname='a'\ncreated='yesterday'\nrepo='o/r'\n[input]\ntitle='t'\nbody='b'\noracle='confirms'\n[expect]\nkind='bug'\nactionable=true\ntemplate='x'\n",
            "YYYY-MM-DD",
        ),
        (
            "triage",
            "[drill]\nname='a'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\ntitle='t'\nbody='b'\noracle='maybe'\n[expect]\nkind='bug'\nactionable=true\ntemplate='x'\n",
            "oracle",
        ),
        (
            "triage",
            "[drill]\nname='a'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\ntitle='t'\nbody='b'\noracle='confirms'\n[expect]\nkind=['bug','maybe']\nactionable=true\ntemplate='x'\n",
            "not a triage kind",
        ),
        (
            "triage",
            "[drill]\nname='a'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\ntitle='t'\nbody='b'\noracle='confirms'\n[expect]\nkind='bug'\nactionable=true\ntemplate=[]\n",
            "expect.template",
        ),
        (
            "review",
            "[drill]\nname='a'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='0000000000000000000000000000000000000000'\npatch='missing.diff'\n[input.brief]\nkind='bug'\nclause='c'\nseverity='low'\nfields={}\n[expect]\nverdict='objections'\n",
            "no file",
        ),
        (
            "review",
            "[drill]\nname='a'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='0000000000000000000000000000000000000000'\npatch='missing.diff'\n[input.brief]\nkind='bug'\nclause='c'\nseverity='low'\nfields={}\n[expect]\nverdict='fine'\n",
            "verdict",
        ),
        (
            "build",
            "[drill]\nname='a'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='0000000000000000000000000000000000000000'\n[input.brief]\nkind='bug'\nclause='c'\nseverity='low'\nfields={}\n[expect]\n",
            "grade: missing",
        ),
        (
            "build",
            "[drill]\nsuite='triage'\nname='a'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='0000000000000000000000000000000000000000'\n[input.brief]\nkind='bug'\nclause='c'\nseverity='low'\nfields={}\n[grade]\ncommand='true'\n[expect]\n",
            "drill.suite",
        ),
    ],
)
def test_parse_rejects(suite: str, text: str, message: str, tmp_path: Path) -> None:
    with pytest.raises(drills.DrillError, match=message):
        drills.parse(text, suite=suite, directory=tmp_path)


def test_grade_triage() -> None:
    record: Any = {
        "kind": "bug",
        "severity": "high",
        "clause": "UTS #39 section 4",
        "missing": [],
        "oracle": "confirms",
        "actionable": True,
        "template": "bug_accepted",
        "labels": ["guild:bug", "severity:high"],
        "outcome": "posted",
    }
    expect = {
        "kind": "bug",
        "actionable": True,
        "template": "bug_accepted",
        "severity": ["high", "critical"],
        "clause_prefix": "UTS #39",
        "labels": ["guild:bug"],
    }
    assert drills.grade_triage(record, expect) == []
    changed: Any = {
        **record,
        "kind": "question",
        "severity": "low",
        "clause": None,
        "labels": [],
    }
    reasons = drills.grade_triage(changed, expect)
    assert reasons == [
        "kind: question != bug",
        "severity: low not in ['high', 'critical']",
        "clause: '' lacks 'UTS #39'",
        "labels: missing ['guild:bug']",
    ]
    # A negative drill lists what it accepts.
    negative = {
        "kind": ["bug", "spam", "other"],
        "actionable": False,
        "template": ["needs_info", "spam", "needs_steward"],
    }
    declined: Any = {**record, "kind": "spam", "actionable": False, "template": "spam"}
    assert drills.grade_triage(declined, negative) == []
    assert drills.grade_triage(changed, negative) == [
        "kind: question not in ['bug', 'spam', 'other']",
        "actionable: True != False",
        "template: bug_accepted not in ['needs_info', 'spam', 'needs_steward']",
    ]


def test_grade_review_and_build() -> None:
    review: Any = {
        "verdict": "objections",
        "objections": 1,
        "notes": 0,
        "findings": [
            {
                "kind": "correctness",
                "clause": None,
                "file": "src/a.py",
                "line": 1,
                "verified": True,
                "summary": "x",
            }
        ],
    }
    assert (
        drills.grade_review(
            review, {"verdict": "objections", "finding_file": "src/a.py"}
        )
        == []
    )
    assert drills.grade_review(
        review, {"verdict": "no_objection", "finding_file": "src/b.py"}
    ) == [
        "verdict: objections != no_objection",
        "no verified finding in src/b.py",
    ]
    check: Any = {
        "ok": True,
        "tier": "T1",
        "paths": ["src/a.py"],
        "rejected": [],
        "failures": [],
        "reasons": [],
    }
    assert (
        drills.grade_build(check, True, 0, {"tier": "T1", "must_change": ["src/a.py"]})
        == []
    )
    failing: Any = {**check, "failures": ["reject list: AGENTS.md"]}
    reasons = drills.grade_build(
        failing,
        False,
        1,
        {"tier": "T2", "must_change": ["src/b.py"], "must_not_change": ["src/a.py"]},
    )
    assert reasons == [
        "the run did not end with its tests passing",
        "check: reject list: AGENTS.md",
        "tier: T1 != T2",
        "not changed: src/b.py",
        "changed: src/a.py",
        "the grading tests failed with exit 1",
    ]
    assert drills.grade_build(check, True, None, {}) == [
        "the grading tests did not run"
    ]


def test_prepare_checkout_strips_the_future(
    source: tuple[Path, str, str], tmp_path: Path
) -> None:
    repo, base, fix = source
    work = tmp_path / "work"
    head = drills.prepare_checkout(repo, base, work)
    assert head == base
    assert (work / "src" / "x.py").read_text(
        encoding="ascii"
    ) == "def f():\n    return 1\n"
    assert git("log", "--all", "--oneline", cwd=work).count("\n") == 1
    assert git("tag", cwd=work) == ""
    assert git("remote", cwd=work) == ""
    gone = subprocess.run(["git", "cat-file", "-e", fix], cwd=work, capture_output=True)
    assert gone.returncode != 0
    # The source still has everything.
    assert git("tag", cwd=repo).strip() == "v1"


def test_prepare_checkout_commits_the_seed(
    source: tuple[Path, str, str], tmp_path: Path
) -> None:
    repo, base, _ = source
    seed = tmp_path / "seed.diff"
    seed.write_text(
        "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n"
        "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 0\n",
        encoding="ascii",
    )
    work = tmp_path / "work"
    head = drills.prepare_checkout(repo, base, work, seed=seed)
    assert head != base
    assert git("log", "--oneline", cwd=work).count("\n") == 2
    assert (work / "src" / "x.py").read_text(encoding="ascii").endswith("return 0\n")
    assert drills.working_diff(work) == ""
    (work / "src" / "x.py").write_text("def f():\n    return 1\n", encoding="ascii")
    (work / "new.txt").write_text("n\n", encoding="ascii")
    diff = drills.working_diff(work)
    assert "+++ b/src/x.py" in diff
    assert "+++ b/new.txt" in diff


def test_prepare_checkout_applies_a_relative_seed(
    source: tuple[Path, str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seed named relative to our cwd applies although git runs in `work`.

    The canary passes `--dir drills/confusable`, so every patch path is
    relative; git apply resolved it against the checkout and found nothing.
    """
    repo, base, _ = source
    (tmp_path / "seeds").mkdir()
    (tmp_path / "seeds" / "seed.diff").write_text(
        "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n"
        "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 0\n",
        encoding="ascii",
    )
    monkeypatch.chdir(tmp_path)
    work = tmp_path / "work"
    drills.prepare_checkout(repo, base, work, seed=Path("seeds/seed.diff"))
    assert (work / "src" / "x.py").read_text(encoding="ascii").endswith("return 0\n")


def canned(reply: dict[str, Any]) -> triage.Caller:
    def call(
        system: str, user: str, *, model: str, max_tokens: int
    ) -> tuple[str, triage.Usage]:
        return json.dumps(reply), {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }

    return call


def test_run_triage_grades_the_record(example_config: Path) -> None:
    cfg = config.load(example_config)
    drill = next(
        d for d in drills.load(DRILLS, "triage") if d["name"] == "bug-confirmed-paypal"
    )
    good = {
        "kind": "bug",
        "severity": "high",
        "clause": "UTS #39 section 4",
        "missing": [],
    }
    trial = drills.run_triage(drill, 1, call=canned(good), cfg=cfg, role="role")
    assert trial["passed"] is True
    assert trial["model"] == "claude-haiku-5-5"
    assert trial["cost_usd"] == 0.00015
    bad: dict[str, Any] = {
        "kind": "question",
        "severity": "none",
        "clause": None,
        "missing": [],
    }
    trial = drills.run_triage(drill, 2, call=canned(bad), cfg=cfg, role="role")
    assert trial["passed"] is False
    assert trial["reasons"][0] == "kind: question != bug"
    assert trial["trial"] == 2
    # The reading travels with the trial, since the call leaves no transcript.
    assert trial["actual"] == {
        "kind": "question",
        "severity": "none",
        "clause": None,
        "missing": [],
        "template": "question",
    }
    assert drills.describe(trial) == " (kind question; template question)"
    # The oracle confirmed the reproducer, so doubting it changes nothing.
    doubted = {**good, "missing": ["reproducer"]}
    trial = drills.run_triage(drill, 3, call=canned(doubted), cfg=cfg, role="role")
    assert trial["passed"] is True
    assert trial["actual"]["missing"] == []
    assert drills.describe(trial) == ""
    unversioned = {**good, "missing": ["version"]}
    trial = drills.run_triage(drill, 4, call=canned(unversioned), cfg=cfg, role="role")
    assert trial["passed"] is False
    assert drills.describe(trial) == " (kind bug; template needs_info; missing version)"


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


def fake_runner(messages: list[Any], act: Any = None) -> Any:
    async def runner(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        if act is not None:
            act(Path(options.cwd), prompt)
        for message in messages:
            yield message

    return runner


@pytest.fixture
def test_config(tmp_path: Path, example_config: Path) -> Path:
    text = example_config.read_text(encoding="utf-8")
    old = 'test_command = "uv run --no-sync pytest -q -x"'
    assert old in text
    path = tmp_path / "guild.toml"
    path.write_text(text.replace(old, f'test_command = "{sys.executable} -c pass"'))
    return path


def test_run_review_with_a_fake(
    source: tuple[Path, str, str], tmp_path: Path, test_config: Path
) -> None:
    repo, base, _ = source
    cfg = config.load(test_config)
    patch = tmp_path / "p.diff"
    patch.write_text(
        "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n"
        "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 3\n",
        encoding="ascii",
    )
    drill = drills.parse(
        f"[drill]\nname='r'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='{base}'\n"
        "patch='p.diff'\n[input.brief]\nkind='bug'\nclause='C-SCOPE-1'\nseverity='low'\n"
        "[input.brief.fields]\n'Code points'='U+0041'\n[expect]\nverdict='objections'\n"
        "finding_file='src/x.py'\n",
        suite="review",
        directory=tmp_path,
    )
    findings = {
        "findings": [
            {
                "kind": "correctness",
                "clause": None,
                "file": "src/x.py",
                "line": 2,
                "verified": True,
                "summary": "wrong",
            }
        ]
    }
    seen: dict[str, Any] = {}

    def act(cwd: Path, prompt: str) -> None:
        seen["cwd"] = cwd
        seen["prompt"] = prompt
        seen["x"] = (cwd / "src" / "x.py").read_text(encoding="ascii")

    trial = drills.run_review(
        drill,
        1,
        cfg=cfg,
        source=repo,
        work=tmp_path / "w1",
        role="ROLE",
        runner=fake_runner([result(structured_output=findings)], act),
    )
    assert trial["passed"] is True, trial["reasons"]
    assert seen["x"].endswith("return 3\n")
    assert "+    return 3" in seen["prompt"]
    assert "Code points: U+0041" in seen["prompt"]
    trial = drills.run_review(
        drill,
        2,
        cfg=cfg,
        source=repo,
        work=tmp_path / "w2",
        role="ROLE",
        runner=fake_runner([result(structured_output={"findings": []})]),
    )
    assert trial["passed"] is False
    assert trial["reasons"] == [
        "verdict: no_objection != objections",
        "no verified finding in src/x.py",
    ]
    trial = drills.run_review(
        drill,
        3,
        cfg=cfg,
        source=repo,
        work=tmp_path / "w3",
        role="ROLE",
        runner=fake_runner([result(subtype="error_max_turns", is_error=True)]),
    )
    assert trial["reasons"] == ["run: error_max_turns"]


def test_run_build_with_a_fake(
    source: tuple[Path, str, str], tmp_path: Path, test_config: Path
) -> None:
    repo, base, fix = source
    cfg = config.load(test_config)
    seed = tmp_path / "seed.diff"
    seed.write_text(
        "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n"
        "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 0\n",
        encoding="ascii",
    )
    check_fix = (
        "import sys; sys.exit(0 if open('src/x.py').read()"
        ".endswith('return 2\\n') and open('tests/test_future.py').read()"
        " == 'FUTURE = 1\\n' else 1)"
    )
    grade = f'{sys.executable} -c "{check_fix}"'
    drill = drills.parse(
        f"[drill]\nname='b'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='{base}'\n"
        "seed='seed.diff'\n[input.brief]\nkind='bug'\nclause='C-SCOPE-1'\nseverity='low'\n"
        "[input.brief.fields]\n'Code points'='U+0041'\n"
        f"[grade]\ncommand='''{grade}'''\ntests_from='{fix}'\ntest_paths=['tests/test_future.py']\n"
        "[expect]\ntier='T1'\nmust_change=['src/x.py']\n",
        suite="build",
        directory=tmp_path,
    )

    def fix_it(cwd: Path, prompt: str) -> None:
        assert (cwd / "src" / "x.py").read_text(encoding="ascii").endswith("return 0\n")
        assert not (cwd / "tests" / "test_future.py").exists()
        (cwd / "src" / "x.py").write_text("def f():\n    return 2\n", encoding="ascii")

    trial = drills.run_build(
        drill,
        1,
        cfg=cfg,
        source=repo,
        work=tmp_path / "w1",
        role="ROLE",
        runner=fake_runner([result()], fix_it),
    )
    assert trial["passed"] is True, trial["reasons"]
    assert (tmp_path / "w1" / "tests" / "test_future.py").exists()

    def break_it(cwd: Path, prompt: str) -> None:
        (cwd / "AGENTS.md").write_text("changed\n", encoding="ascii")

    trial = drills.run_build(
        drill,
        2,
        cfg=cfg,
        source=repo,
        work=tmp_path / "w2",
        role="ROLE",
        runner=fake_runner([result()], break_it),
    )
    assert trial["passed"] is False
    assert "check: reject list: AGENTS.md" in trial["reasons"]
    assert "not changed: src/x.py" in trial["reasons"]
    assert "the grading tests failed with exit 1" in trial["reasons"]


def trial(
    drill: str, n: int, passed: bool, created: str = "2026-11-03", cost: float = 0.1
) -> drills.Trial:
    return {
        "suite": "triage",
        "drill": drill,
        "created": created,
        "trial": n,
        "passed": passed,
        "reasons": [] if passed else ["x"],
        "unknown": [],
        "actual": {},
        "model": "m",
        "cost_usd": cost,
        "turns": 1,
        "duration_ms": 10,
    }


def test_score_and_compare() -> None:
    trials = [
        trial("a", 1, True),
        trial("a", 2, True),
        trial("a", 3, True),
        trial("b", 1, True),
        trial("b", 2, False),
        trial("b", 3, True),
        trial("old", 1, True, created="2025-01-01"),
    ]
    s = drills.score(trials, suite="triage", cutoff="2026-06-01")
    assert [d["drill"] for d in s["drills"]] == ["a", "b", "old"]
    assert s["drills"][1] == {
        "suite": "triage",
        "drill": "b",
        "created": "2026-11-03",
        "trials": 3,
        "passes": 2,
        "pass_rate": 0.6667,
        "pass_k": False,
        "undecided": 0,
        "cost_usd": 0.3,
    }
    assert s["pass_at_1"] == round((1 + 0.6667 + 1) / 3, 4)
    assert s["pass_k"] == round(2 / 3, 4)
    assert s["fresh_drills"] == 2
    assert s["fresh_pass_k"] == 0.5
    assert s["cost_usd"] == 0.7
    assert drills.score([], suite="review", cutoff="2026-06-01")["pass_k"] == 0.0
    better = drills.score(
        [
            trial("a", 1, True),
            trial("b", 1, True),
            trial("old", 1, False, created="2025-01-01"),
        ],
        suite="triage",
        cutoff="2026-06-01",
    )
    comparison = drills.compare(s, better, noise=0.1)
    assert comparison["ok"] is True
    assert comparison["fresh_pass_k_delta"] == 0.5
    worse = drills.score(
        [trial("a", 1, False), trial("b", 1, False)],
        suite="triage",
        cutoff="2026-06-01",
    )
    comparison = drills.compare(s, worse, noise=0.1)
    assert comparison["ok"] is False
    assert comparison["reasons"] == ["fresh pass^k dropped by 0.5 (noise 0.1)"]
    text = drills.markdown(s)
    assert text.startswith(
        "Suite triage: pass@1 0.8889, pass^k 0.6667, fresh pass^k 0.5"
        " (2 drills since 2026-06-01), 0.7 USD"
    )
    assert "- b (2026-11-03): 2/3, 0.3 USD" in text


def test_trials_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    drills.write_trials(path, [trial("a", 1, True)])
    drills.write_trials(path, [trial("a", 2, False)])
    assert [t["trial"] for t in drills.read_trials(path)] == [1, 2]


def test_cli_drill_commands(
    tmp_path: Path, example_config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["drill-list", "--dir", str(DRILLS)]) == 0
    out = capsys.readouterr().out
    assert "triage\tbug-confirmed-paypal\t2026-11-03" in out
    assert "build\tseeded-bidi-fast-path\t2026-11-03" in out
    reply = tmp_path / "reply.json"
    reply.write_text(
        '{"kind": "bug", "severity": "high", "clause": "UTS #39 section 4",'
        ' "missing": []}'
    )
    results = tmp_path / "results.jsonl"
    code = cli.main(
        [
            "drill-run",
            "--dir",
            str(DRILLS),
            "--suite",
            "triage",
            "--config",
            str(example_config),
            "--roles",
            str(ROOT / "roles"),
            "--trials",
            "2",
            "--reply",
            str(reply),
            "--only",
            "bug-confirmed-paypal",
            "--only",
            "spam",
            "--out",
            str(results),
        ]
    )
    assert code == 1  # the canned reply is wrong for the spam drill
    lines = capsys.readouterr().out.splitlines()
    assert "triage bug-confirmed-paypal trial 1: pass" in lines
    assert (
        "triage spam trial 2: FAIL (kind bug; template needs_info; missing reproducer)"
    ) in lines
    assert len(drills.read_trials(results)) == 4
    score = tmp_path / "score.json"
    assert (
        cli.main(
            [
                "drill-score",
                "--results",
                str(results),
                "--suite",
                "triage",
                "--cutoff",
                "2026-06-01",
                "--out",
                str(score),
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.startswith("Suite triage: pass@1 0.5")
    data = json.loads(score.read_text(encoding="ascii"))
    assert data["pass_k"] == 0.5
    assert (
        cli.main(["drill-compare", "--baseline", str(score), "--candidate", str(score)])
        == 0
    )
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["ok"] is True
    assert comparison["pass_k_delta"] == 0.0
    assert (
        cli.main(
            [
                "drill-run",
                "--dir",
                str(DRILLS),
                "--suite",
                "build",
                "--config",
                str(example_config),
                "--roles",
                str(ROOT / "roles"),
                "--out",
                str(results),
            ]
        )
        == 2
    )


def test_parse_checks_hashes_and_rubrics(tmp_path: Path) -> None:
    (tmp_path / "p.diff").write_text("", encoding="ascii")
    head = "[drill]\nname='x'\ncreated='2026-11-03'\nrepo='o/r'\n"
    brief = (
        "[input.brief]\nkind='bug'\nclause='C-A-1'\nseverity='low'\n"
        "[input.brief.fields]\n"
    )
    full = "0" * 40
    with pytest.raises(
        drills.DrillError, match=re.escape("input.base: expected a full commit")
    ):
        drills.parse(
            head
            + "[input]\nbase='abc123'\npatch='p.diff'\n"
            + brief
            + "[expect]\nverdict='objections'\n",
            suite="review",
            directory=tmp_path,
        )
    with pytest.raises(
        drills.DrillError, match=re.escape("grade.tests_from: expected a full")
    ):
        drills.parse(
            head
            + f"[input]\nbase='{full}'\n"
            + brief
            + "[grade]\ncommand='true'\ntests_from='HEAD'\n[expect]\n",
            suite="build",
            directory=tmp_path,
        )
    build = (
        head
        + f"[input]\nbase='{full}'\n"
        + brief
        + "[grade]\ncommand='true'\n[expect]\n"
    )
    assert drills.parse(build, suite="build", directory=tmp_path)["rubric"] == []
    with pytest.raises(drills.DrillError, match=re.escape("rubric.id: a twice")):
        drills.parse(
            build
            + "[[rubric]]\nid='a'\ncriterion='x'\n[[rubric]]\nid='a'\ncriterion='y'\n",
            suite="build",
            directory=tmp_path,
        )
    with pytest.raises(drills.DrillError, match=re.escape("rubric.id: 'A B'")):
        drills.parse(
            build + "[[rubric]]\nid='A B'\ncriterion='x'\n",
            suite="build",
            directory=tmp_path,
        )
    with pytest.raises(drills.DrillError, match="rubric: build drills only"):
        drills.parse(
            head
            + "[input]\ntitle='t'\nbody='b'\noracle='not_run'\n[expect]\nkind='bug'\n"
            "actionable=true\ntemplate='bug_accepted'\n[[rubric]]\nid='a'\ncriterion='x'\n",
            suite="triage",
            directory=tmp_path,
        )


def judged_runner(
    builder_messages: list[Any], grader_messages: list[Any], act: Any = None
) -> tuple[Any, dict[str, Any]]:
    """A runner that answers the Builder, then the grader, told apart by the schema."""
    seen: dict[str, Any] = {"calls": []}

    async def runner(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        if options.output_format is None:
            seen["calls"].append("builder")
            if act is not None:
                act(Path(options.cwd), prompt)
            for message in builder_messages:
                yield message
        else:
            seen["calls"].append("grader")
            seen["grader_prompt"] = prompt
            seen["grader_options"] = options
            for message in grader_messages:
                yield message

    return runner, seen


def build_drill_with_rubric(base: str, fix: str, tmp_path: Path) -> drills.Drill:
    seed = tmp_path / "seed.diff"
    seed.write_text(
        "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n"
        "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 0\n",
        encoding="ascii",
    )
    check_fix = (
        "import sys; sys.exit(0 if open('src/x.py').read()"
        ".endswith('return 2\\n') else 1)"
    )
    grade = f'{sys.executable} -c "{check_fix}"'
    return drills.parse(
        f"[drill]\nname='b'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='{base}'\n"
        "seed='seed.diff'\n[input.brief]\nkind='bug'\nclause='C-SCOPE-1'\nseverity='low'\n"
        "[input.brief.fields]\n'Code points'='U+0041'\n"
        f"[grade]\ncommand='''{grade}'''\ntests_from='{fix}'\ntest_paths=['tests/test_future.py']\n"
        "[expect]\ntier='T1'\nmust_change=['src/x.py']\n"
        "[[rubric]]\nid='fast'\ncriterion='The fix is in f().'\n"
        "[[rubric]]\nid='test'\ncriterion='A test pins it.'\n",
        suite="build",
        directory=tmp_path,
    )


def answers(**by_id: str) -> dict[str, Any]:
    return {
        "answers": [
            {"id": name, "answer": answer, "evidence": f"{name}: seen"}
            for name, answer in by_id.items()
        ]
    }


def fix_x(cwd: Path, prompt: str) -> None:
    (cwd / "src" / "x.py").write_text("def f():\n    return 2\n", encoding="ascii")


def test_run_build_with_a_rubric(
    source: tuple[Path, str, str], tmp_path: Path, test_config: Path
) -> None:
    repo, base, fix = source
    cfg = config.load(test_config)
    drill = build_drill_with_rubric(base, fix, tmp_path)

    def run(n: int, grader_messages: list[Any], act: Any = fix_x) -> tuple[Any, Any]:
        runner, seen = judged_runner([result()], grader_messages, act)
        trial = drills.run_build(
            drill,
            n,
            cfg=cfg,
            source=repo,
            work=tmp_path / f"w{n}",
            role="ROLE",
            runner=runner,
            grader_role="GRADER",
            grader_transcript=tmp_path / f"g{n}.jsonl",
        )
        return trial, seen

    trial, seen = run(1, [result(structured_output=answers(fast="met", test="met"))])
    assert trial["passed"] is True, trial["reasons"]
    assert trial["unknown"] == []
    assert seen["calls"] == ["builder", "grader"]
    assert trial["cost_usd"] == 0.006  # both runs, at the Reviewer's model
    assert (tmp_path / "g1.jsonl").exists()
    options = seen["grader_options"]
    assert options.tools == ["Read", "Glob", "Grep", "Bash"]
    assert options.output_format["schema"] is grader.OUTPUT_SCHEMA
    assert options.system_prompt.startswith("GRADER\n\n# The handbook")
    prompt = seen["grader_prompt"]
    assert "- fast: The fix is in f()." in prompt
    assert "+    return 2" in prompt
    assert "Code points: U+0041" in prompt
    # The grading tests are in the checkout the grader reads.
    assert (tmp_path / "w1" / "tests" / "test_future.py").exists()

    trial, _ = run(2, [result(structured_output=answers(fast="met", test="not_met"))])
    assert trial["passed"] is False
    assert trial["reasons"] == ["rubric: test not met"]

    trial, _ = run(3, [result(structured_output=answers(fast="unknown", test="met"))])
    assert trial["passed"] is True
    assert trial["unknown"] == ["fast"]

    trial, _ = run(4, [result(structured_output=answers(fast="met", other="met"))])
    assert trial["reasons"] == [
        "grader output: answers: expected one for each of ['fast', 'test']"
    ]

    trial, _ = run(5, [result(subtype="error_max_turns", is_error=True)])
    assert trial["reasons"] == ["grader run: error_max_turns"]

    def leave_it(cwd: Path, prompt: str) -> None: ...

    trial, seen = run(
        6, [result(structured_output=answers(fast="met", test="met"))], leave_it
    )
    assert trial["passed"] is False
    assert "not changed: src/x.py" in trial["reasons"]
    assert seen["calls"] == ["builder"], "the grader runs only when the tests pass"

    runner, _ = judged_runner([result()], [], fix_x)
    with pytest.raises(drills.DrillError, match="has a rubric but no grader"):
        drills.run_build(
            drill,
            7,
            cfg=cfg,
            source=repo,
            work=tmp_path / "w7",
            role="ROLE",
            runner=runner,
        )


def test_score_counts_undecided_trials() -> None:
    decided = trial("a", 1, True)
    undecided = trial("a", 2, True)
    undecided["unknown"] = ["fast"]
    score = drills.score([decided, undecided], suite="triage", cutoff="2026-01-01")
    assert score["drills"][0]["undecided"] == 1
    assert score["drills"][0]["pass_k"] is True
    assert "- a (2026-11-03): pass^k, 1 undecided, 0.2 USD" in drills.markdown(score)


def test_cli_build_drill_runs_the_grader(
    source: tuple[Path, str, str],
    tmp_path: Path,
    test_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, base, fix = source
    build_drill_with_rubric(base, fix, tmp_path)  # writes the seed
    directory = tmp_path / "drills" / "build"
    directory.mkdir(parents=True)
    # The drill file, next to its seed; the rubric makes the grader run.
    text = (
        f"[drill]\nname='b'\ncreated='2026-11-03'\nrepo='o/r'\n[input]\nbase='{base}'\n"
        "seed='seed.diff'\n[input.brief]\nkind='bug'\nclause='C-SCOPE-1'\nseverity='low'\n"
        "[input.brief.fields]\n'Code points'='U+0041'\n"
        f"[grade]\ncommand='true'\n[expect]\n"
        "[[rubric]]\nid='fast'\ncriterion='The fix is in f().'\n"
    )
    (directory / "b.toml").write_text(text, encoding="ascii")
    (directory / "seed.diff").write_text(
        (tmp_path / "seed.diff").read_text(encoding="ascii"), encoding="ascii"
    )
    runner, seen = judged_runner(
        [result()], [result(structured_output=answers(fast="unknown"))], fix_x
    )
    monkeypatch.setattr(cli, "RUNNER", runner)
    results = tmp_path / "results.jsonl"
    code = cli.main(
        [
            "drill-run",
            "--dir",
            str(tmp_path / "drills"),
            "--suite",
            "build",
            "--config",
            str(test_config),
            "--roles",
            str(ROOT / "roles"),
            "--trials",
            "1",
            "--source",
            str(repo),
            "--work",
            str(tmp_path / "work"),
            "--out",
            str(results),
        ]
    )
    assert code == 0, capsys.readouterr()
    assert "build b trial 1: pass" in capsys.readouterr().out
    assert seen["calls"] == ["builder", "grader"]
    assert seen["grader_options"].system_prompt.startswith(
        "You are the Grader of Guild"
    )
    (trial_record,) = drills.read_trials(results)
    assert trial_record["unknown"] == ["fast"]
    assert (tmp_path / "work" / "b-1.transcript.jsonl").exists()
    assert (tmp_path / "work" / "b-1.grader.transcript.jsonl").exists()


def test_run_triage_takes_a_candidate_model_and_keeps_probabilities(
    example_config: Path,
) -> None:
    cfg = config.load(example_config)
    drill = next(
        d for d in drills.load(DRILLS, "triage") if d["name"] == "bug-confirmed-paypal"
    )
    good = {
        "kind": "bug",
        "severity": "high",
        "clause": "UTS #39 section 4",
        "missing": [],
    }

    class Caller:
        def __init__(self) -> None:
            self.probabilities: dict[str, Any] = {}

        def __call__(
            self, system: str, user: str, *, model: str, max_tokens: int
        ) -> tuple[str, triage.Usage]:
            self.probabilities = {"kind": {"bug": 0.86, "security": 0.14}}
            return json.dumps(good), {
                "input_tokens": 1000,
                "output_tokens": 300,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            }

    prices: triage.Prices = {
        "input_per_mtok": 0.042,
        "output_per_mtok": 0.0,
        "cache_read_per_mtok": 0.0,
        "cache_write_per_mtok": 0.0,
    }
    trial = drills.run_triage(
        drill, 1, call=Caller(), cfg=cfg, role="role", model="jev-1.14.0", prices=prices
    )
    assert trial["passed"] is True
    assert trial["model"] == "jev-1.14.0"
    assert trial["cost_usd"] == 0.000042
    assert trial["actual"]["probabilities"] == {"kind": {"bug": 0.86, "security": 0.14}}
    # The runner's line stays enumerations: the numbers travel in the trial only.
    good["kind"] = "question"
    trial = drills.run_triage(
        drill, 2, call=Caller(), cfg=cfg, role="role", model="jev-1.14.0", prices=prices
    )
    assert trial["passed"] is False
    assert drills.describe(trial) == " (kind question; template question)"
