"""The ledger: one line per run, append-only, no free text.

Every field is a number, an enumerated value or an identifier, so the ledger
can be read by scripts and never carries model output.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict

from guildkit.commands import CLAUSE

ROLES = ("triage", "planner", "builder", "reviewer", "releaser", "steward")
OUTCOMES = (
    "posted",
    "needs_info",
    "declined",
    "planned",
    "patched",
    "reviewed",
    "merged",
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
