"""Drills: tasks with known right outcomes, run k times, scored as pass^k.

A drill is a TOML file under `drills/<repository>/<suite>/`, with the inputs
a role would get and what the right outcome is. Triage drills feed an issue
to the triage call and grade the record. Review drills apply a patch to a
checkout and grade the verdict. Build drills give the Builder a brief in a
checkout, with a seeded defect or a replayed base commit, and grade the
patch with the plain check and the tests, then with the drill's rubric when
it has one: a second judge (`grader`) that may answer unknown. Every
checkout is prepared from a clone with the later history, tags and remotes
stripped, so no run can read the answer from git.

Scores follow the research in docs/research/notes/evals_governance_cost.md:
several trials per drill, pass^k beside pass@1, a fresh bucket of drills
created after a cutoff that carries the deciding weight, and a comparison
against a baseline that blocks only on a drop larger than the noise.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypedDict

from guildkit import brief, builder, grader, reviewer, snapshot, triage
from guildkit.config import Config
from guildkit.roles import Role
from guildkit.triage import cost_usd

SUITES = ("triage", "review", "build")
# What `git` runs as inside a prepared checkout. No real identity, no token.
_GIT_IDENTITY = ("-c", "user.name=Guild drill", "-c", "user.email=drill@guild.invalid")
_DATE = "YYYY-MM-DD"
# Base commits are written in full: a short or mistyped hash fails here, not
# in a checkout after the clone.
_SHA = re.compile(r"^[0-9a-f]{40}$")


class Drill(TypedDict):
    """One drill file, parsed and checked."""

    suite: str
    name: str
    created: str
    repo: str
    directory: str
    input: dict[str, Any]
    expect: dict[str, Any]
    grade: dict[str, Any]
    rubric: list[grader.Criterion]


class Trial(TypedDict):
    """One run of one drill. Numbers and enumerations; the reasons are code's.

    `unknown` names the rubric criteria the grader could not decide; the
    trial passes with them, and the score counts it as undecided. `actual`
    holds what the model chose when no transcript does: the triage reading
    and its template, as enumerations; empty for the other suites.
    """

    suite: str
    drill: str
    created: str
    trial: int
    passed: bool
    reasons: list[str]
    unknown: list[str]
    actual: dict[str, Any]
    model: str
    cost_usd: float
    turns: int
    duration_ms: int


class DrillError(ValueError):
    """A drill file the runner cannot use."""


def _require(table: dict[str, Any], keys: Iterable[str], where: str) -> None:
    missing = [k for k in keys if k not in table]
    if missing:
        raise DrillError(f"{where}: missing {missing}")


def _date(value: Any, where: str) -> str:
    if not (
        isinstance(value, str)
        and len(value) == len(_DATE)
        and value[4] == value[7] == "-"
        and value.replace("-", "").isdigit()
    ):
        raise DrillError(f"{where}: created must be {_DATE}")
    return value


def _sha(table: dict[str, Any], key: str, where: str) -> None:
    if key in table and not (isinstance(table[key], str) and _SHA.match(table[key])):
        raise DrillError(f"{where}.{key}: expected a full commit hash")


def parse(text: str, *, suite: str, directory: Path) -> Drill:
    """Return the drill in the TOML text, or raise DrillError."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise DrillError(f"not TOML: {e}") from e
    head = data.get("drill")
    if not isinstance(head, dict):
        raise DrillError("drill: expected a table")
    _require(head, ("name", "created", "repo"), "drill")
    name = head["name"]
    if (
        not isinstance(name, str)
        or not name.replace("-", "").replace("_", "").isalnum()
    ):
        raise DrillError("drill.name: letters, digits, - and _ only")
    if head.get("suite", suite) != suite:
        raise DrillError(f"drill.suite: expected {suite}")
    inp = data.get("input")
    expect = data.get("expect")
    grade = data.get("grade", {})
    if (
        not isinstance(inp, dict)
        or not isinstance(expect, dict)
        or not isinstance(grade, dict)
    ):
        raise DrillError("input, expect and grade must be tables")
    if suite == "triage":
        _require(inp, ("title", "body", "oracle"), "input")
        if inp["oracle"] not in triage.ORACLES:
            raise DrillError("input.oracle: not an oracle outcome")
        _require(expect, ("kind", "actionable", "template"), "expect")
        # One value, or the list a negative drill accepts.
        for key, allowed in (("kind", triage.KINDS), ("template", None)):
            values = expect[key] if isinstance(expect[key], list) else [expect[key]]
            if not values or not all(isinstance(v, str) for v in values):
                raise DrillError(f"expect.{key}: a string or a list of strings")
            if allowed is not None and any(v not in allowed for v in values):
                raise DrillError(f"expect.{key}: not a triage kind")
    elif suite == "review":
        _require(inp, ("base", "patch", "brief"), "input")
        _sha(inp, "base", "input")
        _require(expect, ("verdict",), "expect")
        if expect["verdict"] not in reviewer.VERDICTS:
            raise DrillError("expect.verdict: not a verdict")
    else:
        _require(inp, ("base", "brief"), "input")
        _sha(inp, "base", "input")
        _require(grade, ("command",), "grade")
        _sha(grade, "tests_from", "grade")
    if "rubric" in data and suite != "build":
        raise DrillError("rubric: build drills only")
    try:
        criteria = grader.rubric(data.get("rubric", []))
    except grader.GradeError as error:
        raise DrillError(str(error)) from error
    if "brief" in inp:
        _require(inp["brief"], ("kind", "clause", "severity", "fields"), "input.brief")
    for key in ("patch", "seed"):
        if key in inp and not (directory / inp[key]).is_file():
            raise DrillError(f"input.{key}: no file {inp[key]}")
    return {
        "suite": suite,
        "name": name,
        "created": _date(head["created"], "drill"),
        "repo": str(head["repo"]),
        "directory": str(directory),
        "input": inp,
        "expect": expect,
        "grade": grade,
        "rubric": criteria,
    }


def load(root: Path, suite: str) -> list[Drill]:
    """Return the drills of one suite under root, in name order."""
    if suite not in SUITES:
        raise DrillError(f"suite {suite!r}")
    found = []
    for path in sorted((root / suite).glob("*.toml")):
        drill = parse(
            path.read_text(encoding="utf-8"), suite=suite, directory=path.parent
        )
        if drill["name"] != path.stem:
            raise DrillError(f"{path}: drill.name must be {path.stem}")
        found.append(drill)
    return found


# Graders. Each returns the reasons a trial failed; none means it passed.


def grade_triage(record: triage.Record, expect: dict[str, Any]) -> list[str]:
    """Compare the triage record with what the drill expects.

    `kind` and `template` may each be one value or a list: a negative drill
    pins what must not happen, not one classification.
    """
    reasons = []
    actual: dict[str, Any] = dict(record)
    for key in ("kind", "actionable", "template"):
        if isinstance(expect[key], list):
            if actual[key] not in expect[key]:
                reasons.append(f"{key}: {actual[key]} not in {expect[key]}")
        elif actual[key] != expect[key]:
            reasons.append(f"{key}: {actual[key]} != {expect[key]}")
    if "severity" in expect and record["severity"] not in expect["severity"]:
        reasons.append(f"severity: {record['severity']} not in {expect['severity']}")
    if "clause_prefix" in expect:
        clause = record["clause"] or ""
        if not clause.startswith(expect["clause_prefix"]):
            reasons.append(f"clause: {clause!r} lacks {expect['clause_prefix']!r}")
    if "labels" in expect:
        missing = sorted(set(expect["labels"]) - set(record["labels"]))
        if missing:
            reasons.append(f"labels: missing {missing}")
    return reasons


def grade_review(review: reviewer.Review, expect: dict[str, Any]) -> list[str]:
    """Compare the review with what the drill expects."""
    reasons = []
    if review["verdict"] != expect["verdict"]:
        reasons.append(f"verdict: {review['verdict']} != {expect['verdict']}")
    if "finding_file" in expect:
        files = {f["file"] for f in review["findings"] if f["verified"]}
        if expect["finding_file"] not in files:
            reasons.append(f"no verified finding in {expect['finding_file']}")
    return reasons


def grade_build(
    check: builder.Check, run_ok: bool, grade_exit: int | None, expect: dict[str, Any]
) -> list[str]:
    """Combine the run, the plain check and the grading tests."""
    reasons = []
    if not run_ok:
        reasons.append("the run did not end with its tests passing")
    reasons.extend(f"check: {failure}" for failure in check["failures"])
    if "tier" in expect and check["tier"] != expect["tier"]:
        reasons.append(f"tier: {check['tier']} != {expect['tier']}")
    for path in expect.get("must_change", []):
        if path not in check["paths"]:
            reasons.append(f"not changed: {path}")
    for path in expect.get("must_not_change", []):
        if path in check["paths"]:
            reasons.append(f"changed: {path}")
    if grade_exit is None:
        reasons.append("the grading tests did not run")
    elif grade_exit != 0:
        reasons.append(f"the grading tests failed with exit {grade_exit}")
    return reasons


# Checkouts.


def git(*args: str, cwd: Path) -> str:
    """Run git and return its output; raise on failure."""
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise DrillError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def prepare_checkout(
    source: Path, base: str, work: Path, *, seed: Path | None = None
) -> str:
    """Clone `source` at `base` into `work` with nothing after `base` reachable.

    Every ref but the detached HEAD is deleted, the remote is removed, and
    unreachable objects are pruned, so the later history, tags and the fix
    are gone. A seed diff is applied and committed on top, so the Builder's
    own diff is taken against the seeded tree. Returns the head commit.
    """
    git(
        "clone",
        "--quiet",
        "--no-hardlinks",
        "--no-checkout",
        str(source),
        str(work),
        cwd=source,
    )
    git("checkout", "--quiet", "--detach", base, cwd=work)
    git("remote", "remove", "origin", cwd=work)
    for ref in git("for-each-ref", "--format=%(refname)", cwd=work).split():
        git("update-ref", "-d", ref, cwd=work)
    git("reflog", "expire", "--expire=now", "--all", cwd=work)
    git("gc", "--quiet", "--prune=now", cwd=work)
    if seed is not None:
        # git resolves a relative path against cwd, which is `work`, not ours.
        git("apply", "--index", str(Path(seed).resolve()), cwd=work)
        git(*_GIT_IDENTITY, "commit", "--quiet", "-m", "seed", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).strip()


def working_diff(work: Path) -> str:
    """Return the working tree's diff against HEAD, new files included."""
    git("add", "-A", cwd=work)
    return git("diff", "--cached", "--binary", "HEAD", cwd=work)


def _command(command: str, cwd: Path, timeout: int) -> int:
    try:
        done = subprocess.run(
            shlex.split(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return -1
    return done.returncode


# Runs.


def _drill_brief(drill: Drill) -> brief.Brief:
    data = drill["input"]["brief"]
    return {
        "repo": drill["repo"],
        "number": int(data.get("number", 0)),
        "author": "drill",
        "kind": data["kind"],
        "clause": data["clause"],
        "severity": data["severity"],
        "content_hash": hashlib.sha256(drill["name"].encode()).hexdigest(),
        "fields": {str(k): str(v) for k, v in data["fields"].items()},
        "plan": None,
    }


def _trial(
    drill: Drill,
    trial: int,
    reasons: list[str],
    *,
    model: str,
    cost: float,
    turns: int,
    duration_ms: int,
    unknown: list[str] | None = None,
    actual: dict[str, Any] | None = None,
) -> Trial:
    return {
        "suite": drill["suite"],
        "drill": drill["name"],
        "created": drill["created"],
        "trial": trial,
        "passed": not reasons,
        "reasons": reasons,
        "unknown": unknown or [],
        "actual": actual or {},
        "model": model,
        "cost_usd": cost,
        "turns": turns,
        "duration_ms": duration_ms,
    }


def run_triage(
    drill: Drill,
    trial: int,
    *,
    call: triage.Caller,
    cfg: Config,
    role: str,
    model: str | None = None,
    prices: triage.Prices | None = None,
) -> Trial:
    """Run the triage call on the drill's issue and grade the record.

    `model` and `prices` override the config's triage model and its price
    table, for a candidate model the adopter has not pinned. A caller that
    keeps `probabilities` (the System One callers) has them added to the
    trial's `actual`, as numbers, so a failed trial's record says how sure
    the model was; `describe` leaves them out of the runner's line.
    """
    inp = drill["input"]
    issue = {
        "number": int(inp.get("number", 0)),
        "id": 0,
        "title": inp["title"],
        "body": inp["body"],
        "user": {"login": "drill"},
        "author_association": inp.get("author_association", "NONE"),
        "created_at": f"{drill['created']}T00:00:00Z",
        "updated_at": f"{drill['created']}T00:00:00Z",
        "labels": [{"name": label} for label in inp.get("labels", [])],
    }
    snap = snapshot.snapshot(drill["repo"], issue)
    user = snapshot.render(snap) + f"\nOracle check: {inp['oracle']}\n"
    model = model or cfg["triage"]["model"]
    record, usage, parsed = triage.triage(
        call,
        system=role,
        user=user,
        oracle=inp["oracle"],
        model=model,
        max_tokens=cfg["triage"]["max_tokens"],
    )
    reasons = grade_triage(record, drill["expect"])
    if not parsed:
        reasons.append("the reply did not parse")
    cost = cost_usd(usage, prices or cfg["prices"][model])
    actual: dict[str, Any] = {
        key: record[key]
        for key in ("kind", "severity", "clause", "missing", "template")
    }
    probabilities = getattr(call, "probabilities", None)
    if isinstance(probabilities, dict) and probabilities:
        actual["probabilities"] = probabilities
    return _trial(
        drill,
        trial,
        reasons,
        model=model,
        cost=cost,
        turns=1,
        duration_ms=0,
        actual=actual,
    )


def describe(trial: Trial) -> str:
    """Return the failed trial's reading for the runner's line, or nothing.

    Enumerations only, so the line stays the runner's own: the kind, the
    template and the missing fields the model chose, never its words.
    """
    actual = trial["actual"]
    if trial["passed"] or "kind" not in actual:
        return ""
    parts = [f"kind {actual['kind']}", f"template {actual['template']}"]
    if actual["missing"]:
        parts.append("missing " + ", ".join(actual["missing"]))
    return f" ({'; '.join(parts)})"


AgentRun = Callable[..., dict[str, Any]]


def _agent(
    *,
    cfg: Config,
    role_name: Role,
    root: Path,
    system: str,
    user: str,
    output_format: dict[str, Any] | None,
    tests: Any,
    transcript: Path | None,
    runner: Any,
) -> dict[str, Any]:
    """One agent run through the SDK, as `cli._agent_run` does it."""
    import asyncio
    import tempfile

    from claude_agent_sdk import query

    from guildkit import agents

    agent = cfg["agents"][role_name]
    gate = agents.Gate(root, role=role_name, reject=cfg["paths"]["reject"])
    with tempfile.TemporaryDirectory(prefix="guild-drill-") as config_dir:
        options = agents.options(
            root=root,
            config_dir=Path(config_dir),
            system_prompt=system,
            role=role_name,
            model=agent["model"],
            max_turns=agent["max_turns"],
            cap_usd=agent["cap_usd"],
            effort=agent["effort"],
            gate=gate,
            tests=tests,
            output_format=output_format,
        )
        record = asyncio.run(
            agents.run(
                user,
                options,
                role=role_name,
                prices=cfg["prices"][agent["model"]],
                gate=gate,
                tests=tests,
                transcript=transcript,
                runner=runner if runner is not None else query,
            )
        )
    return dict(record)


def _run_ok(record: dict[str, Any]) -> bool:
    return (
        not record["is_error"]
        and record["subtype"] == "success"
        and not record["repeated"]
        and record["tests_passed"] is not False
    )


def run_review(
    drill: Drill,
    trial: int,
    *,
    cfg: Config,
    source: Path,
    work: Path,
    role: str,
    transcript: Path | None = None,
    runner: Any = None,
) -> Trial:
    """Prepare the checkout at the base with the patch applied, run the Reviewer."""
    inp = drill["input"]
    directory = Path(drill["directory"])
    prepare_checkout(source, inp["base"], work)
    patch = (directory / inp["patch"]).read_text(encoding="utf-8")
    git("apply", "--index", str((directory / inp["patch"]).resolve()), cwd=work)
    if "setup" in inp and _command(inp["setup"], work, 900) != 0:
        raise DrillError(f"{drill['name']}: the setup command failed")
    handbook = (work / "AGENTS.md").read_text(encoding="utf-8")
    charter = (work / cfg["charter"]).read_text(encoding="utf-8")
    system, user = reviewer.prompt(
        role=role,
        handbook=handbook,
        charter=charter,
        brief=brief.render(_drill_brief(drill)),
        diff=patch,
    )
    record = _agent(
        cfg=cfg,
        role_name="reviewer",
        root=work,
        system=system,
        user=user,
        output_format={"type": "json_schema", "schema": reviewer.OUTPUT_SCHEMA},
        tests=None,
        transcript=transcript,
        runner=runner,
    )
    reasons: list[str] = []
    if _run_ok(record):
        try:
            review = reviewer.verdict(
                reviewer.validate_output(record["structured_output"])
            )
            reasons = grade_review(review, drill["expect"])
        except reviewer.ReviewError as error:
            reasons = [f"output: {error}"]
    else:
        reasons = [f"run: {record['subtype']}"]
    return _trial(
        drill,
        trial,
        reasons,
        model=record["model"],
        cost=record["cost_usd"],
        turns=record["num_turns"],
        duration_ms=record["duration_ms"],
    )


def _judge_build(
    drill: Drill,
    trial: int,
    *,
    cfg: Config,
    source: Path,
    work: Path,
    run_ok: bool,
    model: str,
    cost: float,
    turns: int,
    duration_ms: int,
    handbook: str,
    charter: str,
    grader_role: str | None,
    grader_transcript: Path | None,
    runner: Any,
    actual: dict[str, Any] | None = None,
) -> Trial:
    """Check and grade the working tree's diff, whoever made it.

    The plain check, the grading tests from the source clone and, when the
    drill has a rubric and nothing failed, the grader as the second judge.
    """
    grade = drill["grade"]
    diff = working_diff(work)
    check = builder.check_patch(
        diff,
        paths=cfg["paths"],
        shape=cfg["shape"],
        tests=cfg["tests"],
        rules=cfg["build"],
        kinds=[],
        floors=cfg["kinds"],
    )
    # The grading tests come from the source clone, after the Builder is done,
    # so the answer never sits in its checkout.
    for path in grade.get("test_paths", []):
        content = git("show", f"{grade['tests_from']}:{path}", cwd=source)
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    grade_exit = _command(grade["command"], work, int(grade.get("timeout", 900)))
    reasons = grade_build(check, run_ok, grade_exit, drill["expect"])
    unknown: list[str] = []
    if drill["rubric"] and not reasons:
        if grader_role is None:
            raise DrillError(f"{drill['name']}: the drill has a rubric but no grader")
        system, user = grader.prompt(
            role=grader_role,
            handbook=handbook,
            charter=charter,
            brief=brief.render(_drill_brief(drill)),
            criteria=drill["rubric"],
            diff=diff,
        )
        judge = _agent(
            cfg=cfg,
            role_name="grader",
            root=work,
            system=system,
            user=user,
            output_format={"type": "json_schema", "schema": grader.OUTPUT_SCHEMA},
            tests=None,
            transcript=grader_transcript,
            runner=runner,
        )
        cost += judge["cost_usd"]
        if _run_ok(judge):
            try:
                answers = grader.validate_output(
                    judge["structured_output"], drill["rubric"]
                )
            except grader.GradeError as error:
                reasons.append(f"grader output: {error}")
            else:
                result = grader.grade(answers)
                reasons.extend(f"rubric: {name} not met" for name in result["not_met"])
                unknown = result["unknown"]
        else:
            reasons.append(f"grader run: {judge['subtype']}")
    return _trial(
        drill,
        trial,
        reasons,
        model=model,
        cost=round(cost, 6),
        turns=turns,
        duration_ms=duration_ms,
        unknown=unknown,
        actual=actual,
    )


def run_build(
    drill: Drill,
    trial: int,
    *,
    cfg: Config,
    source: Path,
    work: Path,
    role: str,
    transcript: Path | None = None,
    runner: Any = None,
    grader_role: str | None = None,
    grader_transcript: Path | None = None,
) -> Trial:
    """Prepare the checkout, seed it, run the Builder, check and grade its diff.

    When the drill has a rubric and the tests passed, the grader runs in
    the same checkout as the second judge; its cost is added to the trial's.
    """
    from guildkit import agents

    inp = drill["input"]
    directory = Path(drill["directory"])
    seed = directory / inp["seed"] if "seed" in inp else None
    prepare_checkout(source, inp["base"], work, seed=seed)
    if "setup" in inp and _command(inp["setup"], work, 900) != 0:
        raise DrillError(f"{drill['name']}: the setup command failed")
    handbook = (work / "AGENTS.md").read_text(encoding="utf-8")
    charter = (work / cfg["charter"]).read_text(encoding="utf-8")
    system, user = builder.prompt(
        role=role,
        handbook=handbook,
        charter=charter,
        brief=brief.render(_drill_brief(drill)),
    )
    tests = agents.TestGate(
        work, cfg["build"]["test_command"], rounds=cfg["build"]["max_test_rounds"]
    )
    record = _agent(
        cfg=cfg,
        role_name="builder",
        root=work,
        system=system,
        user=user,
        output_format=None,
        tests=tests,
        transcript=transcript,
        runner=runner,
    )
    return _judge_build(
        drill,
        trial,
        cfg=cfg,
        source=source,
        work=work,
        run_ok=_run_ok(record),
        model=record["model"],
        cost=record["cost_usd"],
        turns=record["num_turns"],
        duration_ms=record["duration_ms"],
        handbook=handbook,
        charter=charter,
        grader_role=grader_role,
        grader_transcript=grader_transcript,
        runner=runner,
    )


# The cloud arm (docs/ab-experiment-plan.md, arm B): a Claude Code cloud
# session works in a scratch repository and pushes a branch; the same check,
# grading tests and grader judge its diff as judge the Builder's.

# The base a cloud session starts from is committed by this name, so the
# session's own commits are the ones after it.
_SCRATCH_AUTHOR = "Guild drill"
# Emptied in the scratch base, not removed: a public scratch repository would
# let Dependabot open pull requests, as the spike's did, but the adopter's
# own tests may check that the file exists, as confusable's charter test
# does. Workflows stay too; Actions are turned off on the scratch repository.
_SCRATCH_DEPENDABOT = ".github/dependabot.yml"
_SESSION = re.compile(
    r"^Claude-Session: https://claude\.ai/code/(session_[A-Za-z0-9]+)$"
)


def cloud_prefix(drill: Drill) -> str:
    """Return the branch prefix a cloud session of the drill pushes under."""
    return f"claude/{drill['name']}-"


def push_scratch_base(drill: Drill, *, source: Path, work: Path, remote: str) -> str:
    """Push the drill's seeded checkout as `base` of `remote`, Dependabot off.

    Nothing after the drill's base commit is reachable from it, as in
    `prepare_checkout`. Returns the commit pushed.
    """
    inp = drill["input"]
    directory = Path(drill["directory"])
    seed = directory / inp["seed"] if "seed" in inp else None
    prepare_checkout(source, inp["base"], work, seed=seed)
    dependabot = work / _SCRATCH_DEPENDABOT
    if dependabot.exists():
        dependabot.write_text("version: 2\nupdates: []\n", encoding="ascii")
        git("add", _SCRATCH_DEPENDABOT, cwd=work)
    git(
        *_GIT_IDENTITY,
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "scratch base",
        cwd=work,
    )
    head = git("rev-parse", "HEAD", cwd=work).strip()
    git("push", "--quiet", "--force", remote, "HEAD:refs/heads/base", cwd=work)
    return head


def cloud_branches(drill: Drill, *, remote: str, cwd: Path) -> list[str]:
    """Return the drill's cloud branches on `remote`, sorted."""
    prefix = "refs/heads/" + cloud_prefix(drill)
    found = []
    for line in git("ls-remote", "--heads", remote, cwd=cwd).splitlines():
        ref = line.split("\t")[-1].strip()
        if ref.startswith(prefix):
            found.append(ref.removeprefix("refs/heads/"))
    return sorted(found)


def run_build_cloud(
    drill: Drill,
    trial: int,
    *,
    cfg: Config,
    source: Path,
    work: Path,
    remote: str,
    branch: str,
    runner: Any = None,
    grader_role: str | None = None,
    grader_transcript: Path | None = None,
) -> Trial:
    """Grade the diff a cloud session pushed as `branch` of `remote`.

    The checkout is prepared and seeded as for the Builder. The session's
    diff is what the branch adds to the scratch base, the last commit by
    `Guild drill` in its history; only that diff is applied here, so the
    session's own commit, author and message stay behind. Model, cost and
    turns are the session's and unknown here: `cloud-session`, 0 and 0.
    """
    inp = drill["input"]
    directory = Path(drill["directory"])
    seed = directory / inp["seed"] if "seed" in inp else None
    prepare_checkout(source, inp["base"], work, seed=seed)
    if "setup" in inp and _command(inp["setup"], work, 900) != 0:
        raise DrillError(f"{drill['name']}: the setup command failed")
    handbook = (work / "AGENTS.md").read_text(encoding="utf-8")
    charter = (work / cfg["charter"]).read_text(encoding="utf-8")
    git("fetch", "--quiet", "--no-tags", remote, branch, cwd=work)
    base = git(
        "log",
        "-1",
        f"--author={_SCRATCH_AUTHOR}",
        "--format=%H",
        "FETCH_HEAD",
        cwd=work,
    ).strip()
    if not base:
        raise DrillError(f"{drill['name']}: {branch} does not descend from a base")
    message = git("log", "-1", "--format=%B", "FETCH_HEAD", cwd=work)
    sessions = [m[1] for line in message.splitlines() if (m := _SESSION.match(line))]
    actual: dict[str, Any] = {"branch": branch}
    if sessions:
        actual["session"] = sessions[-1]
    patch = work.parent / f"{work.name}.cloud.diff"
    patch.write_text(
        git("diff", "--binary", base, "FETCH_HEAD", cwd=work), encoding="utf-8"
    )
    applied = True
    try:
        if patch.stat().st_size:
            git("apply", "--index", str(patch.resolve()), cwd=work)
    except DrillError:
        applied = False
    trial_record = _judge_build(
        drill,
        trial,
        cfg=cfg,
        source=source,
        work=work,
        run_ok=applied,
        model="cloud-session",
        cost=0.0,
        turns=0,
        duration_ms=0,
        handbook=handbook,
        charter=charter,
        grader_role=grader_role,
        grader_transcript=grader_transcript,
        runner=runner,
        actual=actual,
    )
    if not applied:
        trial_record["reasons"].insert(0, "the session's diff does not apply")
    return trial_record


# Scores.


class DrillScore(TypedDict):
    """One drill's trials, summarised."""

    suite: str
    drill: str
    created: str
    trials: int
    passes: int
    pass_rate: float
    pass_k: bool
    undecided: int
    cost_usd: float


class Score(TypedDict):
    """A suite's drills, summarised, with the fresh bucket apart."""

    suite: str
    cutoff: str
    drills: list[DrillScore]
    pass_at_1: float
    pass_k: float
    fresh_drills: int
    fresh_pass_k: float
    cost_usd: float


def score(trials: Iterable[Trial], *, suite: str, cutoff: str) -> Score:
    """Summarise the trials of one suite.

    `pass_at_1` is the mean pass rate; `pass_k` the share of drills every
    trial passed; `undecided` the trials the grader left a criterion unknown
    on; the fresh bucket holds the drills created on or after the cutoff,
    the candidate model's training cutoff.
    """
    by_drill: dict[str, list[Trial]] = {}
    for trial in trials:
        if trial["suite"] == suite:
            by_drill.setdefault(trial["drill"], []).append(trial)
    drills: list[DrillScore] = []
    for name, runs in sorted(by_drill.items()):
        passes = sum(1 for r in runs if r["passed"])
        drills.append(
            {
                "suite": suite,
                "drill": name,
                "created": runs[0]["created"],
                "trials": len(runs),
                "passes": passes,
                "pass_rate": round(passes / len(runs), 4),
                "pass_k": passes == len(runs),
                "undecided": sum(1 for r in runs if r.get("unknown")),
                "cost_usd": round(sum(r["cost_usd"] for r in runs), 6),
            }
        )
    fresh = [d for d in drills if d["created"] >= cutoff]

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    return {
        "suite": suite,
        "cutoff": cutoff,
        "drills": drills,
        "pass_at_1": mean([d["pass_rate"] for d in drills]),
        "pass_k": mean([1.0 if d["pass_k"] else 0.0 for d in drills]),
        "fresh_drills": len(fresh),
        "fresh_pass_k": mean([1.0 if d["pass_k"] else 0.0 for d in fresh]),
        "cost_usd": round(sum(d["cost_usd"] for d in drills), 6),
    }


class Comparison(TypedDict):
    """Candidate against baseline: no quality drop beyond the noise."""

    ok: bool
    pass_k_delta: float
    fresh_pass_k_delta: float
    cost_delta_usd: float
    reasons: list[str]


def compare(baseline: Score, candidate: Score, *, noise: float) -> Comparison:
    """Return whether the candidate may replace the baseline.

    The fresh bucket decides when it has drills; otherwise all drills do. A
    drop in pass^k larger than `noise` blocks. Cost is reported, not judged.
    """
    reasons = []
    fresh_delta = round(candidate["fresh_pass_k"] - baseline["fresh_pass_k"], 4)
    all_delta = round(candidate["pass_k"] - baseline["pass_k"], 4)
    if baseline["fresh_drills"] and candidate["fresh_drills"]:
        if fresh_delta < -noise:
            reasons.append(f"fresh pass^k dropped by {-fresh_delta} (noise {noise})")
    elif all_delta < -noise:
        reasons.append(f"pass^k dropped by {-all_delta} (noise {noise})")
    return {
        "ok": not reasons,
        "pass_k_delta": all_delta,
        "fresh_pass_k_delta": fresh_delta,
        "cost_delta_usd": round(candidate["cost_usd"] - baseline["cost_usd"], 6),
        "reasons": reasons,
    }


def write_trials(path: Path, trials: Iterable[Trial]) -> None:
    """Append trials to a JSON lines file."""
    with path.open("a", encoding="ascii") as out:
        for trial in trials:
            out.write(json.dumps(trial, sort_keys=True, ensure_ascii=True) + "\n")


def read_trials(path: Path) -> list[Trial]:
    """Read a JSON lines file of trials."""
    trials: list[Trial] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            trials.append(json.loads(line))
    return trials


def markdown(result: Score) -> str:
    """Return the score for a step summary."""
    lines = [
        f"Suite {result['suite']}: pass@1 {result['pass_at_1']}, pass^k"
        f" {result['pass_k']}, fresh pass^k {result['fresh_pass_k']}"
        f" ({result['fresh_drills']} drills since {result['cutoff']}),"
        f" {result['cost_usd']} USD",
        "",
    ]
    for d in result["drills"]:
        state = "pass^k" if d["pass_k"] else f"{d['passes']}/{d['trials']}"
        if d["undecided"]:
            state += f", {d['undecided']} undecided"
        lines.append(f"- {d['drill']} ({d['created']}): {state}, {d['cost_usd']} USD")
    return "\n".join(lines) + "\n"
