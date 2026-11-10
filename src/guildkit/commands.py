"""Steward commands in comments: `/guild plan`, `/guild build`, `/guild reject ...`.

A plain parser. Whether the author may command is the caller's check, against
live permissions, never against the comment.

`/guild confirm <role>` and `/guild overrule <role>` are a steward's grade of
the latest decision a role made on the issue; the ledger records it, and the
shadow exit counts rest on it (docs/plan.md, decision 73).
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from guildkit.text import normalize_newlines

Verb = Literal[
    "plan", "build", "reject", "retry", "pause", "resume", "confirm", "overrule"
]

# The roles a steward may grade: those that decide something on an issue.
GRADED_ROLES = ("triage", "planner", "builder", "reviewer")
GRADES: dict[str, str] = {"confirm": "confirmed", "overrule": "overruled"}

CLAUSE = re.compile(r"^C-[A-Z]+-[1-9][0-9]*$")
_FENCED = re.compile(
    r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", re.DOTALL | re.MULTILINE
)
_BARE: dict[str, Verb] = {
    "plan": "plan",
    "build": "build",
    "retry": "retry",
    "pause": "pause",
    "resume": "resume",
}
_COMMAND = re.compile(r"^/guild[ \t]+([a-z]+)(?:[ \t]+(\S+))?[ \t]*$", re.MULTILINE)


class Command(TypedDict):
    """One steward command."""

    verb: Verb
    clause: str | None
    role: str | None


def parse(body: str) -> Command | None:
    r"""Return the first command in the comment body, or None.

    A command is a whole line. Lines inside code fences do not count; neither
    do quoted lines, which start with `>`. `reject` takes a charter clause;
    `confirm` and `overrule` take a graded role.

    >>> parse("Thanks.\n/guild reject C-OUT-1\n")
    {'verb': 'reject', 'clause': 'C-OUT-1', 'role': None}
    >>> parse("/guild overrule triage")
    {'verb': 'overrule', 'clause': None, 'role': 'triage'}
    >>> parse("```\n/guild build\n```") is None
    True
    """
    text = _FENCED.sub("", normalize_newlines(body))
    for match in _COMMAND.finditer(text):
        verb, argument = match[1], match[2]
        if verb == "reject":
            if argument is not None and CLAUSE.match(argument):
                return {"verb": "reject", "clause": argument, "role": None}
            continue
        if verb in GRADES:
            if argument in GRADED_ROLES:
                graded: Verb = "confirm" if verb == "confirm" else "overrule"
                return {"verb": graded, "clause": None, "role": argument}
            continue
        if verb in _BARE and argument is None:
            return {"verb": _BARE[verb], "clause": None, "role": None}
    return None
