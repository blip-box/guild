"""The ledger: one line per run, append-only, no free text.

Every field is a number, an enumerated value or an identifier, so the ledger
can be read by scripts and never carries model output. It lives on the
`guild-ledger` branch of the adopting repository, as `ledger.jsonl`, written
by plain jobs through GitHub's commit mutation (`commit_input`). The brakes
(`brake`) and the weekly report (`report`) read it.
"""

from __future__ import annotations

import base64
import json
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TypedDict

from guildkit.commands import CLAUSE

LEDGER_PATH = "ledger.jsonl"
LEDGER_BRANCH = "guild-ledger"

ROLES = ("triage", "planner", "builder", "reviewer", "releaser", "steward")
OUTCOMES = (
    "posted",
    "needs_info",
    "declined",
    "planned",
    "patched",
    "reviewed",
    "merged",
    "escalated",
    "failed",
    "paused",
    "skipped",
)
DECIDERS = ("script", "model", "steward")

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SPEC_CLAUSE = re.compile(r"^U(TS|AX) #\d+ section [0-9]+(\.[0-9]+)*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Entry(TypedDict):
    """One ledger line."""

    at: str
    repo: str
    number: int
    author: str
    role: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    outcome: str
    citation: str
    decided_by: str
    decider: str
    content_hash: str
    harness: str


class LedgerError(ValueError):
    """An entry that the ledger cannot hold."""


def validate(entry: dict[str, Any]) -> Entry:
    """Return the entry if every field is one the ledger allows."""
    expected = set(Entry.__annotations__)
    if set(entry) != expected:
        missing, extra = expected - set(entry), set(entry) - expected
        raise LedgerError(f"fields: missing {sorted(missing)}, extra {sorted(extra)}")

    def check(name: str, ok: bool) -> None:
        if not ok:
            raise LedgerError(f"{name}: {entry[name]!r}")

    check("at", isinstance(entry["at"], str) and bool(_TIMESTAMP.match(entry["at"])))
    check(
        "repo",
        isinstance(entry["repo"], str) and bool(_IDENTIFIER.match(entry["repo"])),
    )
    check("number", isinstance(entry["number"], int) and entry["number"] >= 0)
    author = entry["author"]
    check(
        "author",
        isinstance(author, str) and (author == "" or bool(_IDENTIFIER.match(author))),
    )
    check("role", entry["role"] in ROLES)
    check(
        "model",
        isinstance(entry["model"], str) and bool(_IDENTIFIER.match(entry["model"])),
    )
    for name in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ):
        check(name, isinstance(entry[name], int) and entry[name] >= 0)
    cost = entry["cost_usd"]
    check(
        "cost_usd",
        isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0,
    )
    check("outcome", entry["outcome"] in OUTCOMES)
    citation = entry["citation"]
    check(
        "citation",
        isinstance(citation, str)
        and (
            citation == ""
            or bool(CLAUSE.match(citation))
            or bool(_SPEC_CLAUSE.match(citation))
        ),
    )
    check("decided_by", entry["decided_by"] in DECIDERS)
    decider = entry["decider"]
    check(
        "decider",
        isinstance(decider, str)
        and (decider == "" or bool(_IDENTIFIER.match(decider))),
    )
    check(
        "content_hash",
        isinstance(entry["content_hash"], str)
        and bool(_SHA256.match(entry["content_hash"])),
    )
    check(
        "harness",
        isinstance(entry["harness"], str) and bool(_IDENTIFIER.match(entry["harness"])),
    )
    return entry  # type: ignore[return-value]


def to_line(entry: Entry) -> str:
    """Return the entry as one JSON line with sorted keys."""
    return json.dumps(validate(dict(entry)), sort_keys=True, separators=(",", ":"))


def append(path: Path, entry: Entry) -> None:
    """Append the entry to the ledger file, creating it if needed."""
    line = to_line(entry)
    with path.open("a", encoding="ascii") as f:
        f.write(line + "\n")


def read(path: Path) -> Iterator[Entry]:
    """Yield the entries of a ledger file, validating each."""
    with path.open(encoding="ascii") as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield validate(json.loads(line))
            except (json.JSONDecodeError, LedgerError) as e:
                raise LedgerError(f"{path}:{number}: {e}") from e


def identifier(value: str) -> str:
    """Return the value if the ledger may hold it as an identifier, else ""."""
    return value if _IDENTIFIER.match(value) else ""


def brake(
    entries: Iterable[Entry],
    *,
    author: str,
    now: str,
    per_author_per_day: int,
    daily_runs: int,
) -> str | None:
    """Return why triage must not run now, or None.

    Counts the triage entries of the UTC day of `now`: the author's, against
    `per_author_per_day`, and everyone's, against `daily_runs`. Skipped
    entries count too, so a flood cannot spend the day retrying.
    """
    day = now[:10]
    mine = total = 0
    for entry in entries:
        if entry["role"] != "triage" or entry["at"][:10] != day:
            continue
        total += 1
        if author and entry["author"] == author:
            mine += 1
    if author and mine >= per_author_per_day:
        return "author"
    if total >= daily_runs:
        return "daily"
    return None


def commit_input(
    current: str,
    entries: Iterable[Entry],
    *,
    repo: str,
    branch: str,
    head: str,
    message: str,
    path: str = LEDGER_PATH,
) -> dict[str, Any]:
    """Return the createCommitOnBranch input that appends the entries.

    `current` is the file as it is on the branch now (empty for a new file);
    `head` is the branch's head commit, which the mutation checks, so two
    runs cannot both append from the same state.
    """
    lines = [to_line(entry) for entry in entries]
    if not lines:
        raise LedgerError("nothing to append")
    text = current if current == "" or current.endswith("\n") else current + "\n"
    text += "\n".join(lines) + "\n"
    headline, _, body = message.partition("\n")
    return {
        "branch": {"repositoryNameWithOwner": repo, "branchName": branch},
        "expectedHeadOid": head,
        "message": {"headline": headline.strip(), "body": body.strip() + "\n"},
        "fileChanges": {
            "additions": [
                {
                    "path": path,
                    "contents": base64.b64encode(text.encode("ascii")).decode("ascii"),
                }
            ],
            "deletions": [],
        },
    }


class Report(TypedDict):
    """A period of the ledger, counted. Numbers and enumerations only."""

    since: str
    until: str
    runs: int
    by_role: dict[str, int]
    by_outcome: dict[str, int]
    by_role_outcome: dict[str, int]
    cost_usd: float
    cost_by_role: dict[str, float]
    tokens_in: int
    tokens_out: int
    cache_read_share: float
    issues: int
    steward_decisions: int
    escalated: int
    skipped: int
    failed: int


def report(entries: Iterable[Entry], *, since: str, until: str) -> Report:
    """Count the entries with `since <= at < until` (dates, YYYY-MM-DD)."""
    roles: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    pairs: Counter[str] = Counter()
    cost: dict[str, float] = {}
    numbers: set[int] = set()
    runs = tokens_in = tokens_out = cache_read = stewards = 0
    for entry in entries:
        day = entry["at"][:10]
        if not since <= day < until:
            continue
        runs += 1
        roles[entry["role"]] += 1
        outcomes[entry["outcome"]] += 1
        pairs[f"{entry['role']}:{entry['outcome']}"] += 1
        cost[entry["role"]] = cost.get(entry["role"], 0.0) + entry["cost_usd"]
        numbers.add(entry["number"])
        tokens_in += entry["input_tokens"] + entry["cache_read_tokens"]
        tokens_out += entry["output_tokens"]
        cache_read += entry["cache_read_tokens"]
        stewards += entry["decided_by"] == "steward"
    return {
        "since": since,
        "until": until,
        "runs": runs,
        "by_role": dict(sorted(roles.items())),
        "by_outcome": dict(sorted(outcomes.items())),
        "by_role_outcome": dict(sorted(pairs.items())),
        "cost_usd": round(sum(cost.values()), 4),
        "cost_by_role": {k: round(v, 4) for k, v in sorted(cost.items())},
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read_share": round(cache_read / tokens_in, 4) if tokens_in else 0.0,
        "issues": len(numbers),
        "steward_decisions": stewards,
        "escalated": outcomes["escalated"],
        "skipped": outcomes["skipped"],
        "failed": outcomes["failed"],
    }


def report_markdown(data: Report) -> str:
    """Return the report as the Markdown of the weekly issue comment."""
    lines = [
        f"Guild, {data['since']} to {data['until']}: {data['runs']} runs on"
        f" {data['issues']} issues, {data['cost_usd']} USD.",
        "",
        "| Role | Runs | Cost (USD) |",
        "|---|---|---|",
    ]
    for role, count in data["by_role"].items():
        lines.append(f"| {role} | {count} | {data['cost_by_role'].get(role, 0.0)} |")
    lines += [
        "",
        "| Outcome | Runs |",
        "|---|---|",
    ]
    lines += [
        f"| {outcome} | {count} |" for outcome, count in data["by_outcome"].items()
    ]
    lines += [
        "",
        f"Tokens: {data['tokens_in']} in, of which {data['cache_read_share']:.0%} cache"
        f" reads; {data['tokens_out']} out.",
        f"Steward decisions: {data['steward_decisions']}. Escalated:"
        f" {data['escalated']}. Skipped by the brakes: {data['skipped']}. Failed:"
        f" {data['failed']}.",
        "",
        "---",
        "This report is from Guild, the stewards' automation. Every number comes"
        " from the ledger on the guild-ledger branch; no model wrote any of it.",
    ]
    return "\n".join(lines) + "\n"
