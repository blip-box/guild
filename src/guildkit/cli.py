"""The command line the workflows call. Thin: every step is a module function.

Each subcommand reads files and writes files. Only `triage`, `plan`, `build`
and `review` talk to the network, to the model API, and only with a
credential in the environment. The three agent commands import the Agent SDK
when they run, so the shell installs without it for the triage jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import datetime
import json
import os
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from guildkit import (
    __version__,
    brief,
    builder,
    commands,
    config,
    drills,
    ledger,
    planner,
    releaser,
    reviewer,
    snapshot,
    systemone,
    tiers,
    triage,
)
from guildkit.roles import Role

# Tests set this to a fake that yields SDK messages; None means the SDK.
RUNNER: Any = None

HARNESS = f"guildkit-{__version__}"
# An API key, or workload identity federation, which the anthropic client
# picks up from its environment variables on its own.
CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_IDENTITY_TOKEN_FILE",
    "ANTHROPIC_IDENTITY_TOKEN",
)
# The triage callers a drill run may use, with the variables each needs.
CALLERS = ("anthropic", "typesafe", "openai")
CALLER_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "anthropic": CREDENTIALS,
    "typesafe": ("TYPESAFE_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="ascii",
    )


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_snapshot(args: argparse.Namespace) -> int:
    event = _read_json(args.event)
    snap = snapshot.snapshot(args.repo, event["issue"], event.get("comment"))
    _write_json(args.out, snap)
    return 0


def _shape(args: argparse.Namespace, tests: list[str]) -> tiers.Shape:
    shape: tiers.Shape = {}
    if args.numstat is not None:
        changed = deleted_in_tests = 0
        tests_changed = False
        for line in args.numstat.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added, removed, path = parts[0], parts[1], parts[-1]
            is_test = any(tiers.matches(path, p) for p in tests)
            tests_changed = tests_changed or is_test
            if added != "-":
                changed += int(added) + int(removed)
                if is_test:
                    deleted_in_tests += int(removed)
        shape["lines_changed"] = changed
        shape["lines_deleted_in_tests"] = deleted_in_tests
        shape["tests_changed"] = tests_changed
    if args.name_status is not None:
        statuses = args.name_status.read_text(encoding="utf-8").splitlines()
        shape["files_deleted"] = sum(1 for s in statuses if s.startswith("D"))
    return shape


def _cmd_tier(args: argparse.Namespace) -> int:
    cfg = config.load(args.config)
    paths = [p for p in args.paths.read_text(encoding="utf-8").splitlines() if p]
    decision = tiers.tier_for_paths(paths, cfg["paths"])
    decision = tiers.raise_for_shape(decision, _shape(args, cfg["tests"]), cfg["shape"])
    decision = tiers.raise_for_kinds(decision, args.kind, cfg["kinds"])
    _write_json(args.out, decision)
    return 0


def _cmd_triage(args: argparse.Namespace) -> int:
    cfg = config.load(args.config)
    snap = _read_json(args.snapshot)
    system = args.role.read_text(encoding="ascii")
    user = snapshot.render(snap) + f"\nOracle check: {args.oracle}\n"
    call: triage.Caller
    if args.reply is not None:
        canned = args.reply.read_text(encoding="utf-8")

        def call(
            system: str, user: str, *, model: str, max_tokens: int
        ) -> tuple[str, triage.Usage]:
            usage: triage.Usage = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            }
            return canned, usage

    else:
        if not any(name in os.environ for name in CREDENTIALS):
            print(f"triage: none of {CREDENTIALS} is set", file=sys.stderr)
            return 2
        import anthropic

        call = triage.anthropic_caller(anthropic.Anthropic(max_retries=1))
    record, usage, parsed = triage.triage(
        call,
        system=system,
        user=user,
        oracle=args.oracle,
        model=cfg["triage"]["model"],
        max_tokens=cfg["triage"]["max_tokens"],
    )
    cost = triage.cost_usd(usage, cfg["prices"][cfg["triage"]["model"]])
    entry: ledger.Entry = {
        "at": _now(),
        "repo": cfg["repo"],
        "number": int(snap["number"]),
        "author": ledger.identifier(str(snap["author"])),
        "role": "triage",
        "attempt": 1,
        "model": cfg["triage"]["model"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_write_tokens": usage["cache_write_tokens"],
        "cost_usd": cost,
        "outcome": record["outcome"] if parsed else "failed",
        "citation": record["clause"] or "",
        "decided_by": "model" if parsed else "script",
        "decider": "",
        "content_hash": snap["content_hash"],
        "harness": HARNESS,
    }
    ledger.validate(dict(entry))
    _write_json(args.out, record)
    _write_json(args.ledger_entry, entry)
    if cost > cfg["triage"]["cap_usd"]:
        print(
            f"triage: cost {cost} over the cap {cfg['triage']['cap_usd']}",
            file=sys.stderr,
        )
        return 3
    return 0


def _entry(
    cfg: config.Config,
    *,
    number: int,
    role: str,
    model: str,
    usage: triage.Usage,
    cost: float,
    outcome: str,
    citation: str | None,
    decided_by: str,
    decider: str,
    content_hash: str,
    author: str = "",
    attempt: int = 1,
) -> ledger.Entry:
    entry: ledger.Entry = {
        "at": _now(),
        "repo": cfg["repo"],
        "number": number,
        "author": ledger.identifier(author),
        "role": role,
        "attempt": attempt,
        "model": model,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_write_tokens": usage["cache_write_tokens"],
        "cost_usd": cost,
        "outcome": outcome,
        "citation": citation or "",
        "decided_by": decided_by,
        "decider": decider,
        "content_hash": content_hash,
        "harness": HARNESS,
    }
    ledger.validate(dict(entry))
    return entry


def _agent_run(
    args: argparse.Namespace,
    cfg: config.Config,
    *,
    role: Role,
    system: str,
    user: str,
    output_format: dict[str, Any] | None = None,
    tests: Any = None,
    agent: config.AgentConfig | None = None,
) -> dict[str, Any]:
    """Run one agent and return its record. The SDK is imported here.

    `agent` overrides the role's settings: the Builder's second attempt.
    """
    from claude_agent_sdk import query

    from guildkit import agents

    if RUNNER is None and not any(name in os.environ for name in CREDENTIALS):
        print(f"{role}: none of {CREDENTIALS} is set", file=sys.stderr)
        raise SystemExit(2)
    if agent is None:
        agent = cfg["agents"][role]
    gate = agents.Gate(args.root, role=role, reject=cfg["paths"]["reject"])
    with tempfile.TemporaryDirectory(prefix="guild-claude-") as config_dir:
        agent_options = agents.options(
            root=args.root,
            config_dir=Path(config_dir),
            system_prompt=system,
            role=role,
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
                agent_options,
                role=role,
                prices=cfg["prices"][agent["model"]],
                gate=gate,
                tests=tests,
                transcript=args.transcript,
                runner=RUNNER if RUNNER is not None else query,
            )
        )
    return dict(record)


def _run_ok(record: dict[str, Any]) -> bool:
    """Whether a run record says the agent finished normally."""
    return (
        not record["is_error"]
        and record["subtype"] == "success"
        and not record["repeated"]
        and record["tests_passed"] is not False
    )


def _texts(args: argparse.Namespace) -> tuple[str, str, str]:
    """Return the role prompt, handbook and charter, read before the agent starts."""
    return (
        args.role.read_text(encoding="ascii"),
        args.handbook.read_text(encoding="utf-8"),
        args.charter.read_text(encoding="utf-8"),
    )


def _post_record(
    template: str, labels: list[str], clause: str | None
) -> dict[str, Any]:
    """Return a record `render` accepts, for a comment that is not a decision."""
    return {
        "kind": "other",
        "severity": "none",
        "clause": clause,
        "missing": [],
        "oracle": "not_applicable",
        "actionable": False,
        "template": template,
        "labels": sorted(labels),
        "outcome": "posted",
    }


def _cmd_brief(args: argparse.Namespace) -> int:
    snap = _read_json(args.snapshot)
    record = _read_json(args.record)
    plan = _read_json(args.plan) if args.plan is not None else None
    try:
        data = brief.from_triage(snap, record, plan)
    except brief.BriefError as error:
        print(f"brief: {error}", file=sys.stderr)
        return 4
    _write_json(args.out, data)
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    cfg = config.load(args.config)
    snap = _read_json(args.snapshot)
    record = _read_json(args.record)
    try:
        request_text = planner.request(snap, record)
    except planner.PlanError as error:
        print(f"plan: {error}", file=sys.stderr)
        return 4
    role, handbook, charter = _texts(args)
    system, user = planner.prompt(
        role=role, handbook=handbook, charter=charter, request_text=request_text
    )
    run = _agent_run(
        args,
        cfg,
        role="planner",
        system=system,
        user=user,
        output_format={"type": "json_schema", "schema": planner.OUTPUT_SCHEMA},
    )
    plan: dict[str, Any] = {"status": "failed"}
    outcome = "failed"
    template = "needs_steward"
    labels = ["needs steward"]
    if _run_ok(run):
        try:
            plan = dict(
                planner.validate_output(run["structured_output"], list(cfg["kinds"]))
            )
            outcome = str(plan["outcome"])
            template = {
                "planned": "plan_ready",
                "needs_info": "plan_needs_clarification",
                "declined": "plan_out_of_scope",
            }[outcome]
            labels = {
                "planned": ["guild:planned"],
                "needs_info": ["needs info"],
                "declined": ["needs steward"],
            }[outcome]
        except planner.PlanError:
            pass
    entry = _entry(
        cfg,
        number=int(snap["number"]),
        role="planner",
        model=run["model"],
        usage=run["usage"],
        cost=run["cost_usd"],
        outcome=outcome,
        citation=plan.get("clause") or record["clause"],
        decided_by="model",
        decider=args.decider,
        content_hash=snap["content_hash"],
        author=str(snap["author"]),
    )
    _write_json(args.out, plan)
    _write_json(args.run, run)
    _write_json(args.ledger_entry, entry)
    _write_json(
        args.post,
        _post_record(template, labels, plan.get("clause") or record["clause"]),
    )
    return 0 if outcome != "failed" else 5


def _cmd_build(args: argparse.Namespace) -> int:
    from guildkit import agents

    cfg = config.load(args.config)
    data = _read_json(args.brief)
    role, handbook, charter = _texts(args)
    agent = None
    previous = None
    if args.second_attempt:
        agent = cfg["second_attempt"]
        if agent is None:
            print("build: guild.toml has no [builder.second_attempt]", file=sys.stderr)
            return 4
        if args.previous is not None:
            run = _read_json(args.previous_run) if args.previous_run else {}
            previous = builder.previous_attempt(_read_json(args.previous), run)
    system, user = builder.prompt(
        role=role,
        handbook=handbook,
        charter=charter,
        brief=brief.render(data),
        previous=previous,
    )
    tests = agents.TestGate(
        args.root, cfg["build"]["test_command"], rounds=cfg["build"]["max_test_rounds"]
    )
    run = _agent_run(
        args, cfg, role="builder", system=system, user=user, tests=tests, agent=agent
    )
    _write_json(args.run, run)
    return 0


def _cmd_patch_check(args: argparse.Namespace) -> int:
    cfg = config.load(args.config)
    data = _read_json(args.brief)
    run = _read_json(args.run)
    plan = data.get("plan")
    kinds = list(plan["kinds"]) if plan else []
    check = dict(
        builder.check_patch(
            args.diff.read_text(encoding="utf-8", errors="replace"),
            paths=cfg["paths"],
            shape=cfg["shape"],
            tests=cfg["tests"],
            rules=cfg["build"],
            kinds=kinds,
            floors=cfg["kinds"],
        )
    )
    check["run_ok"] = _run_ok(run)
    check["ok"] = bool(check["ok"] and check["run_ok"])
    check["outcome"] = "patched" if check["ok"] else "failed"
    check["attempt"] = args.attempt
    # A failed first attempt gets a second, on the escalated setting, when
    # guild.toml has one; the workflow reads this and nothing else.
    check["escalate"] = bool(
        not check["ok"] and args.attempt == 1 and cfg["second_attempt"] is not None
    )
    entry = _entry(
        cfg,
        number=int(data["number"]),
        role="builder",
        model=run["model"],
        usage=run["usage"],
        cost=run["cost_usd"],
        outcome=str(check["outcome"]),
        citation=data["clause"],
        decided_by="model",
        decider=args.decider,
        content_hash=data["content_hash"],
        author=str(data.get("author", "")),
        attempt=args.attempt,
    )
    _write_json(args.out, check)
    _write_json(args.ledger_entry, entry)
    return 0 if check["ok"] else 5


def _cmd_review(args: argparse.Namespace) -> int:
    cfg = config.load(args.config)
    data = _read_json(args.brief)
    role, handbook, charter = _texts(args)
    system, user = reviewer.prompt(
        role=role,
        handbook=handbook,
        charter=charter,
        brief=brief.render(data),
        diff=args.diff.read_text(encoding="utf-8", errors="replace"),
    )
    run = _agent_run(
        args,
        cfg,
        role="reviewer",
        system=system,
        user=user,
        output_format={"type": "json_schema", "schema": reviewer.OUTPUT_SCHEMA},
    )
    review: dict[str, Any] = {
        "verdict": "failed",
        "objections": 0,
        "notes": 0,
        "findings": [],
    }
    outcome = "failed"
    if _run_ok(run):
        try:
            findings = reviewer.validate_output(run["structured_output"])
            review = dict(reviewer.verdict(findings))
            outcome = "reviewed"
        except reviewer.ReviewError:
            pass
    entry = _entry(
        cfg,
        number=int(data["number"]),
        role="reviewer",
        model=run["model"],
        usage=run["usage"],
        cost=run["cost_usd"],
        outcome=outcome,
        citation=data["clause"],
        decided_by="model",
        decider=args.decider,
        content_hash=data["content_hash"],
        author=str(data.get("author", "")),
    )
    _write_json(args.out, review)
    _write_json(args.run, run)
    _write_json(args.ledger_entry, entry)
    return 0 if outcome == "reviewed" else 5


def _cmd_steward(args: argparse.Namespace) -> int:
    cfg = config.load(args.config)
    return 0 if args.login in cfg["stewards"] else 1


def _cmd_commit_input(args: argparse.Namespace) -> int:
    """Write the input of GitHub's createCommitOnBranch mutation.

    The App that runs the mutation signs the commit. `--name-status` is the
    output of `git diff --cached --name-status`; the file contents are read
    from the working tree and sent base64-encoded.
    """
    cfg = config.load(args.config)
    additions: list[dict[str, str]] = []
    deletions: list[dict[str, str]] = []
    for line in args.name_status.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, paths = parts[0], parts[1:]
        if status.startswith(("R", "C")):
            deletions.append({"path": paths[0]})
            keep = paths[-1]
        elif status.startswith("D"):
            deletions.append({"path": paths[0]})
            continue
        else:
            keep = paths[0]
        content = (args.root / keep).read_bytes()
        additions.append(
            {"path": keep, "contents": base64.b64encode(content).decode("ascii")}
        )
    message = args.message.read_text(encoding="ascii")
    headline, _, body = message.partition("\n")
    payload = {
        "branch": {"repositoryNameWithOwner": cfg["repo"], "branchName": args.branch},
        "expectedHeadOid": args.head,
        "message": {"headline": headline.strip(), "body": body.strip() + "\n"},
        "fileChanges": {"additions": additions, "deletions": deletions},
    }
    _write_json(args.out, {"input": payload})
    return 0


def _fill(template: str, values: dict[str, str]) -> str:
    return releaser.fill(template, values)


def _cmd_pr_text(args: argparse.Namespace) -> int:
    """Write the pull request title and body and the commit message."""
    cfg = config.load(args.config)
    data = _read_json(args.brief)
    check = _read_json(args.check)
    review = _read_json(args.review)
    values = {
        "number": str(int(data["number"])),
        "kind": str(data["kind"]),
        "type": "fix" if data["kind"] == "bug" else "feat",
        "clause": str(data["clause"] or "(no clause)"),
        "tier": str(check["tier"]),
        "verdict": str(review["verdict"]),
        "objections": str(int(review["objections"])),
        "notes": str(int(review["notes"])),
        "run_url": args.run_url,
        "model": cfg["agents"]["builder"]["model"],
    }
    message = _fill((args.templates / "message.md").read_text(encoding="ascii"), values)
    body = _fill((args.templates / "body.md").read_text(encoding="ascii"), values)
    args.out_message.write_text(message, encoding="ascii")
    args.out_title.write_text(message.split("\n", 1)[0] + "\n", encoding="ascii")
    args.out_body.write_text(body, encoding="ascii")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    """Markdown for the step summary. Enumerations and numbers, escaped text."""
    data = _read_json(args.file)
    if args.kind == "plan":
        if data.get("status") == "failed":
            print("The Planner did not return a plan.")
        else:
            print(planner.markdown(data))
    elif args.kind == "review":
        print(reviewer.markdown(data))
    elif args.kind == "release":
        print(releaser.markdown(data))
    elif args.kind == "check":
        state = "ok" if data["ok"] else "failed"
        attempt = f", attempt {data['attempt']}" if "attempt" in data else ""
        print(f"Patch check: {state}, tier {data['tier']}{attempt}.")
        if data.get("escalate"):
            print("A second attempt follows, on the escalated setting.")
        for failure in data["failures"]:
            print(f"- {failure}")
        for reason in data["reasons"]:
            print(f"- {reason}")
    else:
        print(
            f"Run: {data['subtype']}, {data['num_turns']} turns,"
            f" {data['duration_ms'] // 1000} s, {data['cost_usd']} USD"
            f" ({data['reported_cost_usd']} USD reported), {data['denials']} refused"
            f" calls, tests passed: {data['tests_passed']}."
        )
        for tool, count in data["tool_calls"].items():
            print(f"- {tool}: {count}")
    return 0


def _cmd_config_get(args: argparse.Namespace) -> int:
    """Print one value of guild.toml, for a workflow step."""
    cfg = config.load(args.config)
    if args.key == "test_command":
        print(cfg["build"]["test_command"])
    return 0


def _cmd_release(args: argparse.Namespace) -> int:
    """Propose a release from the unreleased commits: exit 0 due, 4 not due."""
    cfg = config.load(args.config)
    try:
        commits = releaser.parse_log(
            args.log.read_text(encoding="utf-8", errors="replace")
        )
        with args.pyproject.open("rb") as f:
            project_version = str(tomllib.load(f)["project"]["version"])
        proposal = releaser.propose(
            commits,
            entries=_read_ledger(args.ledger),
            last_tag=args.last_tag,
            project_version=project_version,
            head=args.head,
            today=args.today,
            tests_exit=args.tests_exit,
            rules=cfg["release"],
        )
        title, body = releaser.render(
            proposal,
            commits,
            title_template=(args.templates / "title.md").read_text(encoding="ascii"),
            body_template=(args.templates / "proposal.md").read_text(encoding="ascii"),
            run_url=args.run_url,
            version_files=cfg["release"]["version_files"],
        )
    except (releaser.ReleaseError, ValueError, KeyError) as error:
        print(f"release: {error}", file=sys.stderr)
        return 2
    _write_json(args.out, releaser.as_dict(proposal))
    args.out_title.write_text(title, encoding="ascii")
    args.out_body.write_text(body, encoding="ascii")
    print(releaser.markdown(proposal))
    return 0 if proposal["due"] else 4


def _cmd_release_close(args: argparse.Namespace) -> int:
    """Write the comment and the reason that close an open proposal."""
    proposal = _read_json(args.proposal)
    try:
        closing = releaser.closing(
            args.title.read_text(encoding="utf-8", errors="replace"),
            last_tag=args.last_tag,
            proposal=proposal,
        )
        comment = releaser.render_closing(
            closing,
            template=(args.templates / "closed.md").read_text(encoding="ascii"),
            previous=str(proposal["previous"]),
            run_url=args.run_url,
        )
    except (releaser.ReleaseError, KeyError) as error:
        print(f"release-close: {error}", file=sys.stderr)
        return 2
    args.out_comment.write_text(comment, encoding="ascii")
    args.out_reason.write_text(closing["reason"] + "\n", encoding="ascii")
    print(f"close as {closing['reason']}: {closing['why']}")
    return 0


def _cmd_release_entry(args: argparse.Namespace) -> int:
    """Write the ledger entry for a posted or closed proposal: no model, no tokens."""
    cfg = config.load(args.config)
    proposal = _read_json(args.proposal)
    entry = _entry(
        cfg,
        number=args.number,
        role="releaser",
        model="none",
        usage={
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
        cost=0.0,
        outcome=args.outcome,
        citation=None,
        decided_by="script",
        decider="",
        content_hash=str(proposal["content_hash"]),
    )
    _write_json(args.out, entry)
    return 0


def _read_ledger(path: Path | None) -> list[ledger.Entry]:
    if path is None or not path.is_file():
        return []
    return list(ledger.read(path))


def _cmd_brake(args: argparse.Namespace) -> int:
    """Decide whether triage may run now: exit 0 to go, 4 or 5 to queue."""
    cfg = config.load(args.config)
    snap = _read_json(args.snapshot)
    author = ledger.identifier(str(snap["author"]))
    now = args.now or _now()
    reason = ledger.brake(
        _read_ledger(args.ledger),
        author=author,
        now=now,
        per_author_per_day=cfg["triage"]["per_author_per_day"],
        daily_runs=cfg["triage"]["daily_runs"],
    )
    if reason is None:
        print("brake: go")
        return 0
    usage: triage.Usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    entry = _entry(
        cfg,
        number=int(snap["number"]),
        role="triage",
        model="none",
        usage=usage,
        cost=0.0,
        outcome="skipped",
        citation="",
        decided_by="script",
        decider="",
        content_hash=snap["content_hash"],
        author=author,
    )
    _write_json(args.entry, entry)
    _write_json(args.post, _post_record("queued", ["guild:queued"], None))
    print(f"brake: queued, the {reason} limit is reached")
    return 4 if reason == "author" else 5


def _cmd_ledger_input(args: argparse.Namespace) -> int:
    """Write the commit input that appends the entry files to the ledger."""
    cfg = config.load(args.config)
    entries = [ledger.validate(_read_json(path)) for path in args.entry]
    current = (
        args.current.read_text(encoding="ascii")
        if args.current is not None and args.current.is_file()
        else ""
    )
    roles = ", ".join(sorted({e["role"] for e in entries}))
    numbers = ", ".join(f"#{n}" for n in sorted({e["number"] for e in entries}))
    message = f"ledger: {roles} for {numbers}\n\nRun: {args.run_url}\n"
    payload = ledger.commit_input(
        current,
        entries,
        repo=cfg["repo"],
        branch=args.branch,
        head=args.head,
        message=message,
    )
    _write_json(args.out, {"input": payload})
    return 0


def _cmd_ledger_report(args: argparse.Namespace) -> int:
    """Count the week, and the whole ledger against the shadow targets."""
    cfg = config.load(args.config)
    entries = _read_ledger(args.ledger)
    data = ledger.report(entries, since=args.since, until=args.until)
    shadow = None
    if cfg["shadow"] is not None:
        shadow = ledger.shadow_progress(
            entries, cfg["shadow"], canary_passes=args.canary_passes
        )
    args.out.write_text(ledger.report_markdown(data, shadow), encoding="ascii")
    if args.json is not None:
        _write_json(args.json, {**data, "shadow": shadow})
    return 0


def _cmd_grade(args: argparse.Namespace) -> int:
    """Write a steward's grade of a role's latest decision as a ledger entry."""
    cfg = config.load(args.config)
    if args.login not in cfg["stewards"]:
        print(f"{args.login} is not a steward", file=sys.stderr)
        return 1
    command = commands.parse(args.body.read_text(encoding="utf-8"))
    if command is None or command["verb"] not in commands.GRADES:
        print("no confirm or overrule command", file=sys.stderr)
        return 1
    assert command["role"] is not None
    try:
        entry = ledger.grade(
            _read_ledger(args.ledger),
            number=args.number,
            role=command["role"],
            verb=command["verb"],
            login=args.login,
            at=args.now or _now(),
            harness=HARNESS,
        )
    except ledger.LedgerError as e:
        print(str(e), file=sys.stderr)
        return 1
    _write_json(args.out, entry)
    print(f"{entry['outcome']} {entry['role']} on #{entry['number']}")
    return 0


def _cmd_drill_list(args: argparse.Namespace) -> int:
    for suite in drills.SUITES:
        for drill in drills.load(args.dir, suite):
            print(f"{suite}\t{drill['name']}\t{drill['created']}")
    return 0


def _canned_caller(path: Path) -> triage.Caller:
    canned = path.read_text(encoding="utf-8")

    def call(
        system: str, user: str, *, model: str, max_tokens: int
    ) -> tuple[str, triage.Usage]:
        usage: triage.Usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
        return canned, usage

    return call


def _cmd_drill_run(args: argparse.Namespace) -> int:
    """Run every drill of a suite `--trials` times, appending trials to `--out`."""
    cfg = config.load(args.config)
    found = drills.load(args.dir, args.suite)
    if args.only:
        found = [d for d in found if d["name"] in args.only]
    if args.suite == "triage":
        model = args.triage_model or cfg["triage"]["model"]
        prices = cfg["prices"].get(model)
        if prices is None and args.models is not None:
            prices = config.load_models(args.models).get(model)
        if prices is None:
            print(f"drill-run: no prices for {model}; pass --models", file=sys.stderr)
            return 2
        if args.reply is not None:
            call = _canned_caller(args.reply)
        else:
            needed = CALLER_CREDENTIALS[args.caller]
            if not any(name in os.environ for name in needed):
                print(f"drill-run: none of {needed} is set", file=sys.stderr)
                return 2
            if args.caller == "typesafe":
                call = systemone.typesafe_caller(
                    systemone.urllib_transport(), os.environ["TYPESAFE_API_KEY"]
                )
            elif args.caller == "openai":
                call = systemone.openai_caller(
                    systemone.urllib_transport(), os.environ["OPENAI_API_KEY"]
                )
            else:
                import anthropic

                call = triage.anthropic_caller(anthropic.Anthropic(max_retries=1))
        role = (args.roles / "triage.md").read_text(encoding="ascii")
    else:
        if args.source is None or args.work is None:
            print("drill-run: --source and --work are needed", file=sys.stderr)
            return 2
        if RUNNER is None and not any(name in os.environ for name in CREDENTIALS):
            print(f"drill-run: none of {CREDENTIALS} is set", file=sys.stderr)
            return 2
        role = (args.roles / f"{args.suite}er.md").read_text(encoding="ascii")
        judge = (args.roles / "grader.md").read_text(encoding="ascii")
    failed = 0
    for drill in found:
        for trial in range(1, args.trials + 1):
            try:
                if args.suite == "triage":
                    result = drills.run_triage(
                        drill,
                        trial,
                        call=call,
                        cfg=cfg,
                        role=role,
                        model=model,
                        prices=prices,
                    )
                elif args.suite == "review":
                    work = args.work / f"{drill['name']}-{trial}"
                    transcript = args.work / f"{drill['name']}-{trial}.transcript.jsonl"
                    result = drills.run_review(
                        drill,
                        trial,
                        cfg=cfg,
                        source=args.source,
                        work=work,
                        role=role,
                        transcript=transcript,
                        runner=RUNNER,
                    )
                else:
                    work = args.work / f"{drill['name']}-{trial}"
                    transcript = args.work / f"{drill['name']}-{trial}.transcript.jsonl"
                    result = drills.run_build(
                        drill,
                        trial,
                        cfg=cfg,
                        source=args.source,
                        work=work,
                        role=role,
                        transcript=transcript,
                        runner=RUNNER,
                        grader_role=judge,
                        grader_transcript=args.work
                        / f"{drill['name']}-{trial}.grader.transcript.jsonl",
                    )
            except (drills.DrillError, systemone.SystemOneError) as error:
                if isinstance(error, systemone.SystemOneError) and error.detail:
                    print(f"drill-run: {error}: {error.detail}", file=sys.stderr)
                result = {
                    "suite": args.suite,
                    "drill": drill["name"],
                    "created": drill["created"],
                    "trial": trial,
                    "passed": False,
                    "reasons": [f"drill error: {error}"],
                    "unknown": [],
                    "actual": {},
                    "model": "",
                    "cost_usd": 0.0,
                    "turns": 0,
                    "duration_ms": 0,
                }
            drills.write_trials(args.out, [result])
            state = "pass" if result["passed"] else "FAIL"
            failed += not result["passed"]
            print(
                f"{args.suite} {drill['name']} trial {trial}: {state}"
                f"{drills.describe(result)}"
            )
    return 0 if not failed else 1


def _cmd_drill_score(args: argparse.Namespace) -> int:
    result = drills.score(
        drills.read_trials(args.results), suite=args.suite, cutoff=args.cutoff
    )
    _write_json(args.out, result)
    print(drills.markdown(result))
    return 0


def _cmd_drill_compare(args: argparse.Namespace) -> int:
    comparison = drills.compare(
        _read_json(args.baseline), _read_json(args.candidate), noise=args.noise
    )
    print(json.dumps(comparison, sort_keys=True, indent=2))
    return 0 if comparison["ok"] else 1


def _cmd_render(args: argparse.Namespace) -> int:
    record = _read_json(args.record)
    values = {"decision_url": args.decision_url, "charter_url": args.charter_url}
    comment = triage.render_comment(record, args.templates, values)
    args.out_comment.write_text(comment, encoding="ascii")
    _write_json(args.out_labels, record["labels"])
    return 0


def _cmd_command(args: argparse.Namespace) -> int:
    body = args.body.read_text(encoding="utf-8")
    print(json.dumps(commands.parse(body)))
    return 0


def _cmd_ledger_append(args: argparse.Namespace) -> int:
    entry = ledger.validate(_read_json(args.entry))
    ledger.append(args.ledger, entry)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser."""
    parser = argparse.ArgumentParser(prog="guildkit", description=__doc__)
    parser.add_argument("--version", action="version", version=HARNESS)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "snapshot", help="escape an issue or comment event into a snapshot"
    )
    p.add_argument("--repo", required=True)
    p.add_argument("--event", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_cmd_snapshot)

    p = sub.add_parser("tier", help="compute the risk tier of a change")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--paths", type=Path, required=True, help="one path per line")
    p.add_argument("--numstat", type=Path, help="output of git diff --numstat")
    p.add_argument("--name-status", type=Path, help="output of git diff --name-status")
    p.add_argument(
        "--kind", action="append", default=[], help="a declared kind of change"
    )
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_cmd_tier)

    p = sub.add_parser("triage", help="run the triage call and the policy")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--role", type=Path, required=True, help="the triage role prompt")
    p.add_argument("--oracle", choices=triage.ORACLES, required=True)
    p.add_argument(
        "--reply", type=Path, help="use this reply instead of calling the model"
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ledger-entry", type=Path, required=True)
    p.set_defaults(func=_cmd_triage)

    p = sub.add_parser("render", help="build the comment and labels for a record")
    p.add_argument("--record", type=Path, required=True)
    p.add_argument("--templates", type=Path, required=True)
    p.add_argument("--decision-url", required=True)
    p.add_argument("--charter-url", required=True)
    p.add_argument("--out-comment", type=Path, required=True)
    p.add_argument("--out-labels", type=Path, required=True)
    p.set_defaults(func=_cmd_render)

    def agent_arguments(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", type=Path, required=True)
        p.add_argument("--root", type=Path, required=True, help="the checkout")
        p.add_argument("--role", type=Path, required=True, help="the role prompt")
        p.add_argument("--handbook", type=Path, required=True)
        p.add_argument("--charter", type=Path, required=True)
        p.add_argument("--run", type=Path, required=True, help="the run record")
        p.add_argument("--transcript", type=Path, required=True)
        p.add_argument("--decider", default="", help="the steward who commanded")

    p = sub.add_parser("brief", help="build the Builder's brief from the record")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--record", type=Path, required=True)
    p.add_argument("--plan", type=Path, help="the approved plan, for a feature")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_cmd_brief)

    p = sub.add_parser("plan", help="run the Planner on an accepted feature")
    agent_arguments(p)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--record", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True, help="the plan")
    p.add_argument("--post", type=Path, required=True, help="the record to render")
    p.add_argument("--ledger-entry", type=Path, required=True)
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("build", help="run the Builder in the checkout")
    agent_arguments(p)
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument(
        "--second-attempt",
        action="store_true",
        help="the escalated setting of [builder.second_attempt]",
    )
    p.add_argument("--previous", type=Path, help="the first attempt's check record")
    p.add_argument("--previous-run", type=Path, help="the first attempt's run record")
    p.set_defaults(func=_cmd_build)

    p = sub.add_parser("patch-check", help="the plain check on the Builder's diff")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument("--diff", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ledger-entry", type=Path, required=True)
    p.add_argument("--decider", default="")
    p.add_argument("--attempt", type=int, default=1, choices=(1, 2))
    p.set_defaults(func=_cmd_patch_check)

    p = sub.add_parser("review", help="run the Reviewer on the applied patch")
    agent_arguments(p)
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument("--diff", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True, help="the review")
    p.add_argument("--ledger-entry", type=Path, required=True)
    p.set_defaults(func=_cmd_review)

    p = sub.add_parser("steward", help="exit 0 when the login is a steward")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--login", required=True)
    p.set_defaults(func=_cmd_steward)

    p = sub.add_parser("commit-input", help="createCommitOnBranch input from the tree")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--name-status", type=Path, required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--head", required=True, help="the expected head commit")
    p.add_argument("--message", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_cmd_commit_input)

    p = sub.add_parser("pr-text", help="the pull request text, from templates")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument("--check", type=Path, required=True)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--run-url", required=True)
    p.add_argument("--templates", type=Path, required=True)
    p.add_argument("--out-title", type=Path, required=True)
    p.add_argument("--out-body", type=Path, required=True)
    p.add_argument("--out-message", type=Path, required=True)
    p.set_defaults(func=_cmd_pr_text)

    p = sub.add_parser("summary", help="Markdown for the step summary")
    p.add_argument(
        "--kind", choices=("plan", "review", "check", "run", "release"), required=True
    )
    p.add_argument("--file", type=Path, required=True)
    p.set_defaults(func=_cmd_summary)

    p = sub.add_parser("brake", help="whether triage may run now, by the ledger")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--ledger", type=Path, help="the ledger file; absent means empty")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--now", help="an ISO timestamp, for tests")
    p.add_argument("--entry", type=Path, required=True, help="the skipped entry")
    p.add_argument("--post", type=Path, required=True, help="the record to render")
    p.set_defaults(func=_cmd_brake)

    p = sub.add_parser("ledger-input", help="createCommitOnBranch input for entries")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--current", type=Path, help="the ledger as it is on the branch")
    p.add_argument("--entry", type=Path, action="append", required=True)
    p.add_argument("--branch", default=ledger.LEDGER_BRANCH)
    p.add_argument("--head", required=True, help="the branch head the input expects")
    p.add_argument("--run-url", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_cmd_ledger_input)

    p = sub.add_parser("ledger-report", help="the weekly report from the ledger")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--since", required=True, help="YYYY-MM-DD, inclusive")
    p.add_argument("--until", required=True, help="YYYY-MM-DD, exclusive")
    p.add_argument("--out", type=Path, required=True, help="the Markdown")
    p.add_argument("--json", type=Path, help="the numbers")
    p.add_argument(
        "--canary-passes",
        type=int,
        default=0,
        help="consecutive passes of the shell's canary, for the shadow section",
    )
    p.set_defaults(func=_cmd_ledger_report)
    p = sub.add_parser("grade", help="a steward's grade of a decision, as an entry")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--body", type=Path, required=True, help="the comment")
    p.add_argument("--number", type=int, required=True, help="the issue")
    p.add_argument("--login", required=True, help="the commenter")
    p.add_argument("--out", type=Path, required=True, help="the entry")
    p.add_argument("--now", help=argparse.SUPPRESS)
    p.set_defaults(func=_cmd_grade)

    p = sub.add_parser("config-get", help="print one value of guild.toml")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("key", choices=("test_command",))
    p.set_defaults(func=_cmd_config_get)

    p = sub.add_parser("release", help="propose a release from the unreleased commits")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--log", type=Path, required=True, help="git log, see releaser")
    p.add_argument("--ledger", type=Path, help="ledger.jsonl, for the credits")
    p.add_argument("--last-tag", default="", help="the last v* tag, or empty")
    p.add_argument("--pyproject", type=Path, required=True)
    p.add_argument("--head", required=True, help="the commit proposed")
    p.add_argument("--today", required=True, help="YYYY-MM-DD")
    p.add_argument("--tests-exit", type=int, required=True)
    p.add_argument("--templates", type=Path, required=True)
    p.add_argument("--run-url", required=True)
    p.add_argument("--out", type=Path, required=True, help="the proposal")
    p.add_argument("--out-title", type=Path, required=True)
    p.add_argument("--out-body", type=Path, required=True)
    p.set_defaults(func=_cmd_release)

    p = sub.add_parser("release-entry", help="the ledger entry for a proposal")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--number", type=int, required=True, help="the issue")
    p.add_argument(
        "--outcome",
        choices=["posted", "declined"],
        default="posted",
        help="posted (opened or rewritten) or declined (closed)",
    )
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_cmd_release_entry)
    p = sub.add_parser("release-close", help="how to close an open proposal")
    p.add_argument("--title", type=Path, required=True, help="the issue's title")
    p.add_argument("--last-tag", default="", help="the last v* tag, or empty")
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--templates", type=Path, required=True)
    p.add_argument("--run-url", required=True)
    p.add_argument("--out-comment", type=Path, required=True)
    p.add_argument("--out-reason", type=Path, required=True)
    p.set_defaults(func=_cmd_release_close)

    p = sub.add_parser("drill-list", help="list the drills under a directory")
    p.add_argument("--dir", type=Path, required=True)
    p.set_defaults(func=_cmd_drill_list)

    p = sub.add_parser("drill-run", help="run a suite of drills, k trials each")
    p.add_argument("--dir", type=Path, required=True, help="the drills directory")
    p.add_argument("--suite", choices=drills.SUITES, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--roles", type=Path, required=True, help="the roles directory")
    p.add_argument("--trials", type=int, default=1)
    p.add_argument("--only", action="append", default=[], help="a drill name")
    p.add_argument("--source", type=Path, help="a clone of the adopting repository")
    p.add_argument("--work", type=Path, help="where the checkouts are made")
    p.add_argument("--reply", type=Path, help="a canned triage reply, for tests")
    p.add_argument(
        "--caller", choices=CALLERS, default="anthropic", help="the triage caller"
    )
    p.add_argument("--triage-model", help="the triage model, instead of the config's")
    p.add_argument(
        "--models", type=Path, help="a price table for models the config lacks"
    )
    p.add_argument("--out", type=Path, required=True, help="trials, JSON lines")
    p.set_defaults(func=_cmd_drill_run)

    p = sub.add_parser("drill-score", help="summarise trials as pass@1 and pass^k")
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--suite", choices=drills.SUITES, required=True)
    p.add_argument("--cutoff", required=True, help="the fresh bucket starts here")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_cmd_drill_score)

    p = sub.add_parser("drill-compare", help="candidate score against a baseline")
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--noise", type=float, default=0.1)
    p.set_defaults(func=_cmd_drill_compare)

    p = sub.add_parser("command", help="parse a steward command from a comment body")
    p.add_argument("--body", type=Path, required=True)
    p.set_defaults(func=_cmd_command)

    p = sub.add_parser("ledger-append", help="append a validated entry to the ledger")
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--entry", type=Path, required=True)
    p.set_defaults(func=_cmd_ledger_append)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line."""
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
