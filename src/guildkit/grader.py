"""The rubric grader: the second judge of a build drill's patch.

The grading tests are the first judge. The grader reads the rubric a
maintainer wrote for the drill, the patch and the checkout, and answers
each criterion `met`, `not_met` or `unknown`. Only `not_met` fails the
trial; `unknown` is a legitimate answer that leaves the tests deciding and
is counted in the score, so a grader that abstains too often shows. Its
output is validated again here and the verdict is computed in code, as the
Reviewer's is.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from guildkit import text

ANSWERS = ("met", "not_met", "unknown")
EVIDENCE_LIMIT = 300
MAX_CRITERIA = 20
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "answer": {"type": "string", "enum": list(ANSWERS)},
                    "evidence": {"type": "string"},
                },
                "required": ["id", "answer", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answers"],
    "additionalProperties": False,
}


class Criterion(TypedDict):
    """One line of a drill's rubric: what a maintainer would check."""

    id: str
    criterion: str


class Answer(TypedDict):
    """The grader's answer to one criterion, after validation.

    The evidence is model text: escaped, cut, shown to stewards only.
    """

    id: str
    answer: str
    evidence: str


class Grade(TypedDict):
    """The verdict and its answers."""

    not_met: list[str]
    unknown: list[str]
    answers: list[Answer]


class GradeError(ValueError):
    """A rubric the grader cannot use, or model output the schema does not allow."""


def rubric(items: Any) -> list[Criterion]:
    """Return the rubric in a drill's `[[rubric]]` tables, or raise GradeError."""
    if not isinstance(items, list) or len(items) > MAX_CRITERIA:
        raise GradeError(f"rubric: expected a list of at most {MAX_CRITERIA}")
    criteria: list[Criterion] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "criterion"}:
            raise GradeError("rubric: each entry has an id and a criterion")
        if not isinstance(item["id"], str) or not _ID.match(item["id"]):
            raise GradeError(f"rubric.id: {item['id']!r}")
        if not isinstance(item["criterion"], str) or not item["criterion"].strip():
            raise GradeError(f"rubric.criterion: empty for {item['id']}")
        if any(c["id"] == item["id"] for c in criteria):
            raise GradeError(f"rubric.id: {item['id']} twice")
        criteria.append({"id": item["id"], "criterion": item["criterion"].strip()})
    return criteria


def validate_output(obj: Any, criteria: list[Criterion]) -> list[Answer]:
    """Return the answers in the model's output, one per criterion, or raise."""
    if not isinstance(obj, dict) or set(obj) != {"answers"}:
        raise GradeError("not an object with answers")
    raw = obj["answers"]
    if not isinstance(raw, list):
        raise GradeError("answers: expected a list")
    answers: list[Answer] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"id", "answer", "evidence"}:
            raise GradeError("answer: unexpected fields")
        if not isinstance(item["id"], str):
            raise GradeError("answer.id: not a string")
        if any(a["id"] == item["id"] for a in answers):
            raise GradeError(f"answer.id: {item['id']} answered twice")
        if item["answer"] not in ANSWERS:
            raise GradeError(f"answer.answer: {item['answer']!r}")
        if not isinstance(item["evidence"], str):
            raise GradeError("answer.evidence: not a string")
        answers.append(
            {
                "id": item["id"],
                "answer": item["answer"],
                "evidence": text.escape(item["evidence"])[:EVIDENCE_LIMIT],
            }
        )
    expected = [c["id"] for c in criteria]
    if sorted(a["id"] for a in answers) != sorted(expected):
        raise GradeError(f"answers: expected one for each of {expected}")
    return answers


def grade(answers: list[Answer]) -> Grade:
    """Return the verdict the rules give: `not_met` fails, `unknown` is counted."""
    return {
        "not_met": [a["id"] for a in answers if a["answer"] == "not_met"],
        "unknown": [a["id"] for a in answers if a["answer"] == "unknown"],
        "answers": answers,
    }


def prompt(
    *,
    role: str,
    handbook: str,
    charter: str,
    brief: str,
    criteria: list[Criterion],
    diff: str,
) -> tuple[str, str]:
    """Return the system prompt and the user text, from these inputs only."""
    system = (
        f"{role.rstrip()}\n\n# The handbook\n\n{handbook.rstrip()}"
        f"\n\n# The charter\n\n{charter.rstrip()}\n"
    )
    lines = [f"- {c['id']}: {c['criterion']}" for c in criteria]
    user = (
        "# The brief the patch answers\n\n"
        f"{brief.rstrip()}\n\n"
        "# The rubric\n\n" + "\n".join(lines) + "\n\n# The patch\n\n"
        "The checkout you are in already has it applied, with the grading tests"
        " added.\n\n"
        f"{diff.rstrip()}\n"
    )
    return system, user


def markdown(result: Grade) -> str:
    """Return the grade for a step summary. ASCII."""
    lines = [
        f"Rubric: {len(result['not_met'])} not met, {len(result['unknown'])} unknown"
        f" of {len(result['answers'])}",
        "",
    ]
    for answer in result["answers"]:
        lines.append(f"- {answer['id']}: {answer['answer']}; {answer['evidence']}")
    return "\n".join(lines) + "\n"
