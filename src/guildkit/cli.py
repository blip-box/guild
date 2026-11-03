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
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from guildkit import (
    __version__,
    brief,
    builder,
    commands,
    config,
    ledger,
    planner,
    reviewer,
    snapshot,
    tiers,
    triage,
)
from guildkit.roles import Role

# Tests set this to a fake that yields SDK messages; None means the SDK.
RUNNER: Any = None
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

HARNESS = f"guildkit-{__version__}"
# An API key, or workload identity federation, which the anthropic client
# picks up from its environment variables on its own.
CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_IDENTITY_TOKEN_FILE",
    "ANTHROPIC_IDENTITY_TOKEN",
)


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
        "role": "triage",
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
) -> ledger.Entry:
    entry: ledger.Entry = {
        "at": _now(),
        "repo": cfg["repo"],
        "number": number,
        "role": role,
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
) -> dict[str, Any]:
    """Run one agent and return its record. The SDK is imported here."""
    from claude_agent_sdk import query

    from guildkit import agents

    if RUNNER is None and not any(name in os.environ for name in CREDENTIALS):
        print(f"{role}: none of {CREDENTIALS} is set", file=sys.stderr)
        raise SystemExit(2)
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
    system, user = builder.prompt(
        role=role, handbook=handbook, charter=charter, brief=brief.render(data)
    )
    tests = agents.TestGate(
        args.root, cfg["build"]["test_command"], rounds=cfg["build"]["max_test_rounds"]
    )
    run = _agent_run(args, cfg, role="builder", system=system, user=user, tests=tests)
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
    unknown = sorted(set(_PLACEHOLDER.findall(template)) - set(values))
    if unknown:
        raise ValueError(f"unknown placeholders {unknown}")
    return _PLACEHOLDER.sub(lambda m: values[m[1]], template)


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
    elif args.kind == "check":
        print(f"Patch check: {'ok' if data['ok'] else 'failed'}, tier {data['tier']}.")
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
    p.set_defaults(func=_cmd_build)

    p = sub.add_parser("patch-check", help="the plain check on the Builder's diff")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument("--diff", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ledger-entry", type=Path, required=True)
    p.add_argument("--decider", default="")
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
    p.add_argument("--kind", choices=("plan", "review", "check", "run"), required=True)
    p.add_argument("--file", type=Path, required=True)
    p.set_defaults(func=_cmd_summary)

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
