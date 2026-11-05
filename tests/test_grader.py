"""The rubric grader: the rubric, the answers, the verdict and the prompt."""

from typing import Any

import pytest

from guildkit import grader

RUBRIC = [
    {"id": "fix", "criterion": "The fix is where it belongs."},
    {"id": "test", "criterion": "  A test pins it. "},
]


def test_rubric_parses_and_rejects() -> None:
    criteria = grader.rubric(RUBRIC)
    assert criteria == [
        {"id": "fix", "criterion": "The fix is where it belongs."},
        {"id": "test", "criterion": "A test pins it."},
    ]
    assert grader.rubric([]) == []
    for items, message in [
        ("x", "rubric: expected a list"),
        ([{"id": "a"}], "an id and a criterion"),
        ([{"id": "A", "criterion": "x"}], "rubric.id: 'A'"),
        ([{"id": "a", "criterion": " "}], "rubric.criterion: empty for a"),
        ([{"id": "a", "criterion": "x"}] * 2, "rubric.id: a twice"),
        ([{"id": str(n), "criterion": "x"} for n in range(21)], "at most 20"),
    ]:
        with pytest.raises(grader.GradeError, match=message):
            grader.rubric(items)


def answer(name: str, verdict: str, evidence: str = "seen") -> dict[str, Any]:
    return {"id": name, "answer": verdict, "evidence": evidence}


def test_validate_output_wants_one_answer_per_criterion() -> None:
    criteria = grader.rubric(RUBRIC)
    answers = grader.validate_output(
        {"answers": [answer("test", "unknown", "p\u0430ypal"), answer("fix", "met")]},
        criteria,
    )
    assert answers[0] == {"id": "test", "answer": "unknown", "evidence": "pU+0430ypal"}
    assert len(answers[1]["evidence"]) <= grader.EVIDENCE_LIMIT
    long = grader.validate_output(
        {"answers": [answer("fix", "met", "x" * 1000), answer("test", "met")]}, criteria
    )
    assert len(long[0]["evidence"]) == grader.EVIDENCE_LIMIT
    for obj, message in [
        ([], "not an object with answers"),
        ({"answers": {}}, "answers: expected a list"),
        ({"answers": [{"id": "fix"}]}, "answer: unexpected fields"),
        (
            {"answers": [answer("fix", "maybe"), answer("test", "met")]},
            "answer.answer: 'maybe'",
        ),
        (
            {"answers": [answer("fix", "met"), answer("fix", "met")]},
            "fix answered twice",
        ),
        (
            {"answers": [answer("fix", "met")]},
            r"expected one for each of \['fix', 'test'\]",
        ),
        (
            {
                "answers": [
                    answer("fix", "met"),
                    answer("test", "met"),
                    answer("x", "met"),
                ]
            },
            "one for each",
        ),
        (
            {
                "answers": [
                    {"id": 1, "answer": "met", "evidence": ""},
                    answer("test", "met"),
                ]
            },
            "answer.id: not a string",
        ),
        (
            {
                "answers": [
                    {"id": "fix", "answer": "met", "evidence": 1},
                    answer("test", "met"),
                ]
            },
            "evidence: not a string",
        ),
    ]:
        with pytest.raises(grader.GradeError, match=message):
            grader.validate_output(obj, criteria)


def test_grade_fails_on_not_met_only() -> None:
    criteria = grader.rubric(RUBRIC)
    answers = grader.validate_output(
        {
            "answers": [
                answer("fix", "not_met", "wrong file"),
                answer("test", "unknown"),
            ]
        },
        criteria,
    )
    result = grader.grade(answers)
    assert result["not_met"] == ["fix"]
    assert result["unknown"] == ["test"]
    assert grader.markdown(result).splitlines() == [
        "Rubric: 1 not met, 1 unknown of 2",
        "",
        "- fix: not_met; wrong file",
        "- test: unknown; seen",
    ]
    assert grader.grade([]) == {"not_met": [], "unknown": [], "answers": []}


def test_prompt_holds_the_rubric_the_brief_and_the_patch() -> None:
    system, user = grader.prompt(
        role="ROLE\n",
        handbook="HANDBOOK",
        charter="CHARTER",
        brief="BRIEF\n",
        criteria=grader.rubric(RUBRIC),
        diff="+x\n",
    )
    assert system == "ROLE\n\n# The handbook\n\nHANDBOOK\n\n# The charter\n\nCHARTER\n"
    assert user == (
        "# The brief the patch answers\n\nBRIEF\n\n# The rubric\n\n"
        "- fix: The fix is where it belongs.\n- test: A test pins it.\n\n"
        "# The patch\n\nThe checkout you are in already has it applied, with the"
        " grading tests added.\n\n+x\n"
    )
