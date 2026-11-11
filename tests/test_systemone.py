"""The System One callers: question sets, thresholds, usage and the transport."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from guildkit import systemone, triage

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "Summary\nskeleton() keeps the Cyrillic a.\nSpecification clause\n"
    "UTS #39 section 4\nCharter\nC-SCOPE-3\nOracle check: confirms\n"
)
MISSING_NAMES = [f"missing_{name}" for name in systemone.MISSING_TEXT]


class Transport:
    """A transport with one canned reply that records what was posted."""

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def __call__(
        self, url: str, headers: dict[str, str], body: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((url, headers, body))
        return self.reply


def jev_reply(
    *,
    kind: str = "bug",
    kind_p: dict[str, float] | None = None,
    severity: str = "high",
    spec: str | None = "UTS #39 section 4",
    charter: str | None = "C-SCOPE-3",
    missing: dict[str, float] | None = None,
) -> dict[str, Any]:
    """A reply in TypeSafe's shape; a clause of None leaves its answer out."""
    answers: dict[str, Any] = {
        "kind": {
            "type": "choice",
            "choice": kind,
            "probabilities": kind_p or {kind: 0.86, "security": 0.14},
        },
        "severity": {
            "type": "choice",
            "choice": severity,
            "probabilities": {severity: 0.5, "medium": 0.3, "critical": 0.2},
        },
    }
    if spec is not None:
        answers["spec_clause"] = {
            "type": "choice",
            "choice": spec,
            "probabilities": {spec: 0.99, "none": 0.01},
        }
    if charter is not None:
        answers["charter_clause"] = {
            "type": "choice",
            "choice": charter,
            "probabilities": {charter: 0.9, "none": 0.1},
        }
    for name in systemone.MISSING_TEXT:
        answers[f"missing_{name}"] = {
            "type": "noul",
            "noul": (missing or {}).get(name, 0.02),
        }
    return {
        "model": "jev-1.14.0",
        "answers": answers,
        "usage": {"input_tokens": 1611, "output_tokens": 310},
    }


def luna_reply(
    *,
    kind: str = "bug",
    kind_p: dict[str, float] | None = None,
    severity: str = "medium",
    spec: str | None = "UTS #39 section 4",
    charter: str | None = "C-SCOPE-3",
    missing: dict[str, float] | None = None,
    cached: int = 0,
) -> dict[str, Any]:
    """A reply in the Decisions API's shape."""

    def table(values: dict[str, float]) -> list[dict[str, Any]]:
        return [{"value": k, "probability": v} for k, v in values.items()]

    answers: list[dict[str, Any]] = [
        {
            "type": "choice",
            "name": "kind",
            "choice": kind,
            "probabilities": table(kind_p or {kind: 0.97, "feature": 0.03}),
        },
        {
            "type": "choice",
            "name": "severity",
            "choice": severity,
            "probabilities": table({severity: 0.59, "high": 0.41}),
        },
    ]
    if spec is not None:
        answers.append(
            {
                "type": "choice",
                "name": "spec_clause",
                "choice": spec,
                "probabilities": table({spec: 1.0, "none": 0.0}),
            }
        )
    if charter is not None:
        answers.append(
            {
                "type": "choice",
                "name": "charter_clause",
                "choice": charter,
                "probabilities": table({charter: 0.8, "none": 0.2}),
            }
        )
    for name in systemone.MISSING_TEXT:
        answers.append(
            {
                "type": "predicate",
                "name": f"missing_{name}",
                "probability": (missing or {}).get(name, 0.0),
            }
        )
    return {
        "answers": answers,
        "usage": {
            "input_tokens": 2362,
            "input_tokens_details": {"cached_tokens": cached},
            "output_tokens": 0,
        },
    }


def test_typesafe_caller_asks_the_question_set_and_builds_the_record() -> None:
    transport = Transport(jev_reply())
    call = systemone.typesafe_caller(transport, "key")
    text, usage = call("the role prompt", TEXT, model="jev-1.14.0", max_tokens=1)
    url, headers, body = transport.calls[0]
    assert url == systemone.TYPESAFE_URL
    assert headers == {"Authorization": "Bearer key"}
    assert body["model"] == "jev-1.14.0"
    assert body["state"] == {"issue": TEXT}
    assert list(body["questions"]) == [
        "kind",
        "severity",
        "spec_clause",
        "charter_clause",
        *MISSING_NAMES,
    ]
    # A clause can only be a string the text holds, or none.
    assert list(body["questions"]["spec_clause"]["criteria"]) == [
        "UTS #39 section 4",
        "none",
    ]
    assert list(body["questions"]["charter_clause"]["criteria"]) == [
        "C-SCOPE-3",
        "none",
    ]
    # The role prompt is not sent: the question set is the rubric.
    assert "the role prompt" not in json.dumps(body)
    assert triage.parse_output(text) == {
        "kind": "bug",
        "severity": "high",
        "clause": "UTS #39 section 4",
        "missing": [],
    }
    assert usage == {
        "input_tokens": 1611,
        "output_tokens": 310,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    assert call.probabilities["kind"] == {"bug": 0.86, "security": 0.14}
    assert call.probabilities["spec_clause"] == {
        "UTS #39 section 4": 0.99,
        "none": 0.01,
    }
    assert call.probabilities["missing"]["summary"] == 0.02


def test_the_kind_settles_the_clause_and_the_fields_that_can_be_missing() -> None:
    # A feature takes the charter clause, and only its own fields count.
    reply = jev_reply(
        kind="feature",
        kind_p={"feature": 0.97},
        missing={"actual": 0.83, "version": 0.98, "expected": 0.37},
    )
    call = systemone.typesafe_caller(Transport(reply), "key")
    text, _ = call("", TEXT, model="jev-1.14.0", max_tokens=1)
    assert triage.parse_output(text) == {
        "kind": "feature",
        "severity": "high",
        "clause": "C-SCOPE-3",
        "missing": [],
    }
    reply = jev_reply(
        kind="feature", kind_p={"feature": 0.97}, missing={"summary": 0.9}
    )
    call = systemone.typesafe_caller(Transport(reply), "key")
    text, _ = call("", TEXT, model="jev-1.14.0", max_tokens=1)
    assert triage.parse_output(text)["missing"] == ["summary"]
    # The other kinds carry no clause and no missing fields.
    reply = jev_reply(
        kind="question", kind_p={"question": 0.9}, missing={"actual": 1.0}
    )
    call = systemone.typesafe_caller(Transport(reply), "key")
    text, _ = call("", TEXT, model="jev-1.14.0", max_tokens=1)
    assert triage.parse_output(text) == {
        "kind": "question",
        "severity": "high",
        "clause": None,
        "missing": [],
    }


def test_thresholds_map_doubt_to_other_and_list_missing_fields() -> None:
    reply = jev_reply(
        kind="bug",
        kind_p={"bug": 0.49, "spam": 0.31, "other": 0.2},
        spec="none",
        missing={"expected": 0.83, "actual": 0.7, "reproducer": 0.71},
    )
    call = systemone.typesafe_caller(Transport(reply), "key")
    text, _ = call("", TEXT, model="jev-1.14.0", max_tokens=1)
    output = triage.parse_output(text)
    assert output["kind"] == "other"  # under KIND_FLOOR
    assert output["clause"] is None
    assert output["missing"] == []  # not a bug: the fields are the bug form's
    reply = jev_reply(
        spec="none", missing={"expected": 0.83, "actual": 0.7, "reproducer": 0.71}
    )
    call = systemone.typesafe_caller(Transport(reply), "key")
    text, _ = call("", TEXT, model="jev-1.14.0", max_tokens=1)
    output = triage.parse_output(text)
    assert output["clause"] is None
    # Strictly above the threshold: 0.7 itself is not listed.
    assert output["missing"] == ["expected", "reproducer"]


def test_a_text_without_clauses_is_not_asked_about_them() -> None:
    text = "Hello dev, we provide real github stars.\nOracle check: not_applicable\n"
    transport = Transport(
        jev_reply(kind="spam", kind_p={"spam": 0.9}, spec=None, charter=None)
    )
    call = systemone.typesafe_caller(transport, "key")
    reply, _ = call("", text, model="jev-1.14.0", max_tokens=1)
    assert list(transport.calls[0][2]["questions"]) == [
        "kind",
        "severity",
        *MISSING_NAMES,
    ]
    assert triage.parse_output(reply)["clause"] is None
    assert call.probabilities["spec_clause"] == {}
    transport = Transport(
        luna_reply(kind="spam", kind_p={"spam": 0.9}, spec=None, charter=None)
    )
    call = systemone.openai_caller(transport, "key")
    reply, _ = call("", text, model="gpt-6-luna", max_tokens=1)
    assert [q["name"] for q in transport.calls[0][2]["questions"]] == [
        "kind",
        "severity",
        *MISSING_NAMES,
    ]
    assert triage.parse_output(reply)["kind"] == "spam"


def test_openai_caller_asks_the_question_set_and_splits_cached_tokens() -> None:
    transport = Transport(luna_reply(cached=1000, missing={"version": 0.9}))
    call = systemone.openai_caller(transport, "key")
    text, usage = call("the role prompt", TEXT, model="gpt-6-luna", max_tokens=1)
    url, headers, body = transport.calls[0]
    assert url == systemone.OPENAI_URL
    assert headers == {"Authorization": "Bearer key"}
    assert body["model"] == "gpt-6-luna"
    assert body["input"] == TEXT
    names = [q["name"] for q in body["questions"]]
    assert names == [
        "kind",
        "severity",
        "spec_clause",
        "charter_clause",
        *MISSING_NAMES,
    ]
    assert [c["value"] for c in body["questions"][2]["choices"]] == [
        "UTS #39 section 4",
        "none",
    ]
    assert [c["value"] for c in body["questions"][3]["choices"]] == [
        "C-SCOPE-3",
        "none",
    ]
    assert "the role prompt" not in json.dumps(body)
    assert "`issue`" not in json.dumps(body)
    assert triage.parse_output(text) == {
        "kind": "bug",
        "severity": "medium",
        "clause": "UTS #39 section 4",
        "missing": ["version"],
    }
    # The API counts cached tokens inside input_tokens; the price table
    # charges them apart.
    assert usage == {
        "input_tokens": 1362,
        "output_tokens": 0,
        "cache_read_tokens": 1000,
        "cache_write_tokens": 0,
    }
    assert call.probabilities["severity"] == {"medium": 0.59, "high": 0.41}
    assert call.probabilities["charter_clause"] == {"C-SCOPE-3": 0.8, "none": 0.2}


def test_the_record_passes_the_policy_as_the_anthropic_reply_does() -> None:
    call = systemone.openai_caller(Transport(luna_reply()), "key")
    record, usage, parsed = triage.triage(
        call, system="", user=TEXT, oracle="confirms", model="gpt-6-luna", max_tokens=1
    )
    assert parsed is True
    assert record["actionable"] is True
    assert record["template"] == "bug_accepted"
    assert usage["input_tokens"] == 2362


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ({"answers": None}, "no answers"),
        ({"answers": {}}, "kind: no choice"),
        (jev_reply(spec="UTS #39 section 5"), "not a candidate"),
        (jev_reply(charter="C-SCOPE-4"), "not a candidate"),
        (jev_reply(kind="urgent", kind_p={"urgent": 1.0}), "kind 'urgent'"),
        (jev_reply(severity="worst"), "severity 'worst'"),
        (jev_reply(spec=None), "spec_clause: no choice"),
    ],
)
def test_rejects_replies_that_do_not_fit(reply: dict[str, Any], message: str) -> None:
    call = systemone.typesafe_caller(Transport(reply), "key")
    with pytest.raises(systemone.SystemOneError, match=message):
        call("", TEXT, model="jev-1.14.0", max_tokens=1)


def test_a_missing_predicate_is_an_error_not_a_guess() -> None:
    reply = luna_reply()
    reply["answers"] = [a for a in reply["answers"] if a["name"] != "missing_version"]
    call = systemone.openai_caller(Transport(reply), "key")
    with pytest.raises(systemone.SystemOneError, match="missing_version"):
        call("", TEXT, model="gpt-6-luna", max_tokens=1)


def test_clause_candidates_keep_order_drop_repeats_and_cap() -> None:
    text = "C-SCOPE-1 then UTS #39 section 4, C-SCOPE-1 again, UAX #29 section 3.1.1"
    assert systemone.clause_candidates(text) == (
        ["UTS #39 section 4", "UAX #29 section 3.1.1"],
        ["C-SCOPE-1"],
    )
    many = " ".join(f"C-SCOPE-{n}" for n in range(1, 301))
    spec, charter = systemone.clause_candidates(many)
    assert spec == []
    assert len(charter) == systemone.MAX_CANDIDATES
    assert charter[0] == "C-SCOPE-1"


def test_the_question_set_is_the_role_prompts_rubric() -> None:
    role = " ".join((ROOT / "roles" / "triage.md").read_text(encoding="ascii").split())
    for kind in ("bug", "feature", "security", "spam"):
        assert systemone.KIND_CRITERIA[kind] in role
    assert "a missed look-alike is a security bug" in role
    assert (
        "a missed look-alike is a security bug" in systemone.SEVERITY_CRITERIA["high"]
    )
    # The two fields the policy derives from the clause are not asked.
    assert set(systemone.MISSING_TEXT) == set(triage.MISSING) - {"citation", "clause"}
    assert systemone.FEATURE_FIELDS <= set(systemone.MISSING_TEXT)


class FakeReply:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeReply:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def http_error(code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(body))  # type: ignore[arg-type]


def test_urllib_transport_retries_once_then_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes: list[Any] = [http_error(429, b"slow down"), FakeReply(b'{"ok": 1}')]
    seen: list[Any] = []
    slept: list[float] = []

    def urlopen(request: Any, timeout: float) -> Any:
        seen.append((request.full_url, request.get_header("Content-type"), timeout))
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    post = systemone.urllib_transport(timeout=5.0, sleep=slept.append)
    assert post("https://x/v1", {"Authorization": "Bearer k"}, {"a": 1}) == {"ok": 1}
    assert slept == [2.0]
    assert seen == [
        ("https://x/v1", "application/json", 5.0),
        ("https://x/v1", "application/json", 5.0),
    ]
    outcomes[:] = [http_error(429), http_error(429, b"still")]
    with pytest.raises(systemone.SystemOneError, match="HTTP 429") as info:
        post("https://x/v1", {}, {})
    assert info.value.detail == "still"
    outcomes[:] = [http_error(500, b"<html>boom</html>")]
    with pytest.raises(systemone.SystemOneError, match="HTTP 500") as info:
        post("https://x/v1", {}, {})
    # The vendor's words stay in `detail`, out of the message.
    assert "boom" not in str(info.value)
    assert info.value.detail == "<html>boom</html>"
    outcomes[:] = [urllib.error.URLError("refused")]
    with pytest.raises(systemone.SystemOneError, match="no reply"):
        post("https://x/v1", {}, {})
    outcomes[:] = [FakeReply(b"[1, 2]")]
    with pytest.raises(systemone.SystemOneError, match="not an object"):
        post("https://x/v1", {}, {})
