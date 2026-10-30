"""The command line the workflows call. Thin: every step is a module function.

Each subcommand reads files and writes files. Only `triage` talks to the
network, to the model API, and only when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

from guildkit import __version__, commands, config, ledger, snapshot, tiers, triage

HARNESS = f"guildkit-{__version__}"


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
        if "ANTHROPIC_API_KEY" not in os.environ:
            print("triage: ANTHROPIC_API_KEY is not set", file=sys.stderr)
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
