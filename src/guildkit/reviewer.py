"""The Reviewer: a fresh reader of the patch, the rules and the contract.

It sees the diff, the handbook and charter from the base branch, and the
brief the Builder worked from. It does not see the Builder's transcript, the
issue, or anything else; `prompt` takes only those inputs, and a test proves
a canary planted anywhere else never reaches it. Its findings arrive as
structured output, are validated again here, and the verdict is computed
from them in code: a verified finding on correctness or the charter is an
objection; anything else is a note.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from guildkit import text

Kind = Literal["correctness", "charter", "tests"]
KINDS: tuple[Kind, ...] = ("correctness", "charter", "tests")
VERDICTS = ("no_objection", "objections")
SUMMARY_LIMIT = 300
MAX_FINDINGS = 20
# Past this the Reviewer sees the head of the diff and a note. A patch that
# large is not a Guild patch anyway.
DIFF_LIMIT = 200_000

_CLAUSE = re.compile(
    r"^(C-[A-Z]+-[1-9][0-9]*|U(TS|AX) #\d+ section [0-9]+(\.[0-9]+)*)$"
)
_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "clause": {"type": ["string", "null"]},
                    "file": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "verified": {"type": "boolean"},
                    "summary": {"type": "string"},
                },
                "required": ["kind", "clause", "file", "line", "verified", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}


class Finding(TypedDict):
    """One finding, after validation.

    The summary is model text: escaped, cut, shown to stewards only, never
    posted as a comment.
    """

    kind: Kind
    clause: str | None
    file: str
    line: int | None
    verified: bool
    summary: str


class Review(TypedDict):
    """The verdict and its findings."""

    verdict: str
    objections: int
    notes: int
    findings: list[Finding]


class ReviewError(ValueError):
    """Model output that the schema does not allow."""


def validate_output(obj: Any) -> list[Finding]:
    """Return the findings in the model's output, or raise ReviewError."""
    if not isinstance(obj, dict) or set(obj) != {"findings"}:
        raise ReviewError("not an object with findings")
    raw = obj["findings"]
    if not isinstance(raw, list) or len(raw) > MAX_FINDINGS:
        raise ReviewError("findings: expected a list of at most 20")
    findings: list[Finding] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "kind",
            "clause",
            "file",
            "line",
            "verified",
            "summary",
        }:
            raise ReviewError("finding: unexpected fields")
        if item["kind"] not in KINDS:
            raise ReviewError(f"finding.kind: {item['kind']!r}")
        clause = item["clause"]
        if clause is not None and not (
            isinstance(clause, str) and _CLAUSE.match(clause)
        ):
            raise ReviewError("finding.clause: not a clause")
        if not isinstance(item["file"], str) or not _PATH.match(item["file"]):
            raise ReviewError("finding.file: not a path")
        line = item["line"]
        if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
            raise ReviewError("finding.line: not an integer")
        if not isinstance(item["verified"], bool):
            raise ReviewError("finding.verified: not a boolean")
        if not isinstance(item["summary"], str):
            raise ReviewError("finding.summary: not a string")
        findings.append(
            {
                "kind": item["kind"],
                "clause": clause,
                "file": item["file"],
                "line": line if line is None or line > 0 else None,
                "verified": item["verified"],
                "summary": text.escape(item["summary"])[:SUMMARY_LIMIT],
            }
        )
    return findings


def verdict(findings: list[Finding]) -> Review:
    """Return the verdict the rules give: verified findings object, others note."""
    objections = sum(1 for f in findings if f["verified"])
    return {
        "verdict": "objections" if objections else "no_objection",
        "objections": objections,
        "notes": len(findings) - objections,
        "findings": findings,
    }


def prompt(
    *, role: str, handbook: str, charter: str, brief: str, diff: str
) -> tuple[str, str]:
    """Return the system prompt and the user text, from these inputs only."""
    system = (
        f"{role.rstrip()}\n\n# The handbook\n\n{handbook.rstrip()}"
        f"\n\n# The charter\n\n{charter.rstrip()}\n"
    )
    shown = diff
    if len(diff) > DIFF_LIMIT:
        shown = diff[:DIFF_LIMIT] + "\n[cut: the patch is longer than the limit]\n"
    user = (
        "# The contract\n\n"
        f"{brief.rstrip()}\n\n"
        "# The patch\n\n"
        "The checkout you are in already has it applied.\n\n"
        f"{shown.rstrip()}\n"
    )
    return system, user


def markdown(review: Review) -> str:
    """Return the review for a step summary or a check run. ASCII."""
    lines = [
        f"Verdict: {review['verdict']} ({review['objections']} objections,"
        f" {review['notes']} notes)",
        "",
    ]
    for finding in review["findings"]:
        where = finding["file"] + (f":{finding['line']}" if finding["line"] else "")
        state = "verified" if finding["verified"] else "not verified"
        clause = f" [{finding['clause']}]" if finding["clause"] else ""
        lines.append(
            f"- {finding['kind']}, {state}, {where}{clause}: {finding['summary']}"
        )
    if not review["findings"]:
        lines.append("No findings.")
    return "\n".join(lines) + "\n"
