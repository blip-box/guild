"""Steward commands in comments: `/guild plan`, `/guild build`, `/guild reject ...`.

A plain parser. Whether the author may command is the caller's check, against
live permissions, never against the comment.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from guildkit.text import normalize_newlines

Verb = Literal["plan", "build", "reject", "retry", "pause", "resume"]

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


def parse(body: str) -> Command | None:
    r"""Return the first command in the comment body, or None.

    A command is a whole line. Lines inside code fences do not count; neither
    do quoted lines, which start with `>`. `reject` takes a charter clause.

    >>> parse("Thanks.\n/guild reject C-OUT-1\n")
    {'verb': 'reject', 'clause': 'C-OUT-1'}
    >>> parse("```\n/guild build\n```") is None
    True
    """
    text = _FENCED.sub("", normalize_newlines(body))
    for match in _COMMAND.finditer(text):
        verb, argument = match[1], match[2]
        if verb == "reject":
            if argument is not None and CLAUSE.match(argument):
                return {"verb": "reject", "clause": argument}
            continue
        if verb in _BARE and argument is None:
            return {"verb": _BARE[verb], "clause": None}
    return None
