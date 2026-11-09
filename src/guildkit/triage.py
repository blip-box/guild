"""Triage: one model call with no tools, then policy in plain code.

The model reads the escaped snapshot and the oracle's verdict and returns a
record of closed enumerations. Plain code then applies the rules that decide
what is actionable, so the model cannot talk its way past them, and builds the
comment from templates, so no model text reaches the issue.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict

from guildkit.commands import CLAUSE

KINDS = ("bug", "feature", "question", "security", "spam", "other")
SEVERITIES = ("none", "low", "medium", "high", "critical")
MISSING = (
    "summary",
    "code_points",
    "function",
    "expected",
    "actual",
    "version",
    "citation",
    "clause",
    "reproducer",
)
ORACLES = ("confirms", "disagrees", "not_applicable", "not_run", "error")
# The fields the oracle check reads before it can run: when it says
# "confirms" or "disagrees", the issue holds them, whatever the model thought.
ORACLE_FIELDS = frozenset({"code_points", "function", "reproducer"})

Kind = Literal["bug", "feature", "question", "security", "spam", "other"]
Oracle = Literal["confirms", "disagrees", "not_applicable", "not_run", "error"]

_SPEC_CLAUSE = re.compile(r"^U(TS|AX) #\d+ section [0-9]+(\.[0-9]+)*$")
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class ModelOutput(TypedDict):
    """What the model may say. Nothing else gets through."""

    kind: Kind
    severity: str
    clause: str | None
    missing: list[str]


class Record(TypedDict):
    """The triage decision, after policy."""

    kind: Kind
    severity: str
    clause: str | None
    missing: list[str]
    oracle: Oracle
    actionable: bool
    template: str
    labels: list[str]
    outcome: str


class Usage(TypedDict):
    """Tokens the call used, as the API reports them."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


class Prices(TypedDict):
    """US dollars per million tokens."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    cache_write_per_mtok: float


class Caller(Protocol):
    """One tool-less model call: system prompt and user text in, text out."""

    def __call__(
        self, system: str, user: str, *, model: str, max_tokens: int
    ) -> tuple[str, Usage]:
        """Return the reply text and the tokens used."""
        ...


class TriageError(ValueError):
    """Model output that the schema does not allow."""


def validate_output(obj: Any) -> ModelOutput:
    """Return the model output if it holds only the allowed values."""
    if not isinstance(obj, dict):
        raise TriageError("not an object")
    expected = {"kind", "severity", "clause", "missing"}
    if set(obj) != expected:
        raise TriageError(f"fields {sorted(obj)}, expected {sorted(expected)}")
    if obj["kind"] not in KINDS:
        raise TriageError(f"kind {obj['kind']!r}")
    if obj["severity"] not in SEVERITIES:
        raise TriageError(f"severity {obj['severity']!r}")
    clause = obj["clause"]
    if clause is not None and not (
        isinstance(clause, str) and (CLAUSE.match(clause) or _SPEC_CLAUSE.match(clause))
    ):
        raise TriageError(f"clause {clause!r}")
    missing = obj["missing"]
    if not isinstance(missing, list) or any(m not in MISSING for m in missing):
        raise TriageError(f"missing {missing!r}")
    return {
        "kind": obj["kind"],
        "severity": obj["severity"],
        "clause": clause,
        "missing": sorted(set(missing)),
    }


def parse_output(text: str) -> ModelOutput:
    """Return the record in the model's reply, which may have text around it."""
    match = _JSON_OBJECT.search(text)
    if match is None:
        raise TriageError("no JSON object in the reply")
    try:
        return validate_output(json.loads(match[0]))
    except json.JSONDecodeError as e:
        raise TriageError(f"invalid JSON: {e}") from e


def fallback() -> ModelOutput:
    """Return the stand-in for a reply the schema rejects: a steward looks."""
    return {"kind": "other", "severity": "none", "clause": None, "missing": ["summary"]}


def apply_policy(output: ModelOutput, oracle: Oracle) -> Record:
    """Return the decision the rules give for the model's reading.

    A bug is actionable only with a reproducer the oracle confirms and a
    citation; when the oracle could not run, a steward looks rather than the
    reporter being asked again. A feature is actionable only with the charter
    clause it serves. Security reports, questions, spam and the rest are never
    actionable here: a steward or a template answers them.

    The oracle's verdict outranks the model's reading of the reproducer: when
    the check ran, the fields it needed are in the text, so the model's doubt
    about them cannot turn a confirmed bug into a request for information.
    """
    if oracle not in ORACLES:
        raise TriageError(f"oracle {oracle!r}")
    kind = output["kind"]
    clause = output["clause"]
    missing = set(output["missing"])
    if oracle in ("confirms", "disagrees"):
        missing -= ORACLE_FIELDS
    severity = output["severity"] if kind == "bug" else "none"
    actionable = False
    template: str
    labels = [f"guild:{kind}"]

    if kind == "bug":
        if clause is None:
            missing.add("citation")
        if oracle == "disagrees":
            template = "spec_disagrees"
            labels.append("spec disagrees")
        elif oracle in ("not_run", "error"):
            template = "needs_steward"
            labels.append("needs steward")
        elif oracle == "confirms" and not missing:
            actionable = True
            template = "bug_accepted"
            labels.append(f"severity:{severity}")
        else:
            if oracle == "not_applicable":
                missing.add("reproducer")
            template = "needs_info"
            labels.append("needs info")
    elif kind == "feature":
        if clause is None or not clause.startswith("C-"):
            missing.add("clause")
            template = "needs_info"
            labels.append("needs info")
        elif missing:
            template = "needs_info"
            labels.append("needs info")
        else:
            actionable = True
            template = "feature_accepted"
    elif kind == "security":
        template = "security"
        labels.append("needs steward")
    elif kind == "question":
        template = "question"
    elif kind == "spam":
        template = "spam"
    else:
        template = "needs_steward"
        labels.append("needs steward")

    if actionable:
        outcome = "posted"
    elif "needs info" in labels:
        outcome = "needs_info"
    elif "needs steward" in labels:
        outcome = "escalated"
    else:
        outcome = "declined"
    return {
        "kind": kind,
        "severity": severity,
        "clause": clause,
        "missing": sorted(missing),
        "oracle": oracle,
        "actionable": actionable,
        "template": template,
        "labels": sorted(labels),
        "outcome": outcome,
    }


def triage(
    call: Caller,
    *,
    system: str,
    user: str,
    oracle: Oracle,
    model: str,
    max_tokens: int,
) -> tuple[Record, Usage, bool]:
    """Run the triage call and the policy. The flag says whether the reply parsed."""
    reply, usage = call(system, user, model=model, max_tokens=max_tokens)
    try:
        output, parsed = parse_output(reply), True
    except TriageError:
        output, parsed = fallback(), False
    return apply_policy(output, oracle), usage, parsed


def cost_usd(usage: Usage, prices: Prices) -> float:
    """Return what the call cost, from the price table."""
    return round(
        (
            usage["input_tokens"] * prices["input_per_mtok"]
            + usage["output_tokens"] * prices["output_per_mtok"]
            + usage["cache_read_tokens"] * prices["cache_read_per_mtok"]
            + usage["cache_write_tokens"] * prices["cache_write_per_mtok"]
        )
        / 1_000_000,
        6,
    )


_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_MISSING_TEXT = {
    "summary": "a short summary in your own words",
    "code_points": "the exact code points, as U+XXXX",
    "function": "the function you called",
    "expected": "the result you expected",
    "actual": "the result you got",
    "version": "the library version",
    "citation": "the specification clause or oracle that gives the expected result",
    "clause": "the charter clause the request serves, by ID",
    "reproducer": "a reproducer the oracle check can run",
}


def render_comment(record: Record, templates: Path, values: Mapping[str, str]) -> str:
    """Return the comment for the record from its template.

    Placeholders are filled from `values` (links the workflow knows) and from
    the record's enumerations. Anything else in the template is an error.
    """
    text = (templates / f"{record['template']}.md").read_text(encoding="ascii")
    fields = dict(values)
    fields["missing_list"] = "\n".join(
        f"- {_MISSING_TEXT[m]}" for m in record["missing"]
    )
    fields["clause"] = record["clause"] or "(none)"
    fields["oracle"] = record["oracle"]
    fields["severity"] = record["severity"]
    unknown = sorted(set(_PLACEHOLDER.findall(text)) - set(fields))
    if unknown:
        raise TriageError(f"{record['template']}.md: unknown placeholders {unknown}")
    return _PLACEHOLDER.sub(lambda m: fields[m[1]], text)


# The reply's schema, enforced by the API's structured output. The policy
# code validates the reply again: the schema is a convenience, not a trust.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "clause": {"type": ["string", "null"]},
        "missing": {
            "type": "array",
            "items": {"type": "string", "enum": list(MISSING)},
        },
    },
    "required": ["kind", "severity", "clause", "missing"],
    "additionalProperties": False,
}


def anthropic_caller(client: Any) -> Caller:
    """Return a Caller over an `anthropic.Anthropic` client. No tools, ever.

    The call is one message with a system prompt, structured output in the
    record's schema, and low effort: classification, not reasoning.
    """

    def call(
        system: str, user: str, *, model: str, max_tokens: int
    ) -> tuple[str, Usage]:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        return text, {
            "input_tokens": int(usage.input_tokens),
            "output_tokens": int(usage.output_tokens),
            "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            "cache_write_tokens": int(
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            ),
        }

    return call
