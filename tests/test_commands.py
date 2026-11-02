import pytest

from guildkit import commands


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("/guild build", {"verb": "build", "clause": None}),
        ("Looks good.\n/guild build\nthanks", {"verb": "build", "clause": None}),
        ("/guild reject C-OUT-1", {"verb": "reject", "clause": "C-OUT-1"}),
        ("/guild retry", {"verb": "retry", "clause": None}),
        ("/guild pause", {"verb": "pause", "clause": None}),
        ("/guild resume", {"verb": "resume", "clause": None}),
        (
            "/guild reject C-OUT-1\n/guild build",
            {"verb": "reject", "clause": "C-OUT-1"},
        ),
        ("/guild build now", None),
        ("/guild reject", None),
        ("/guild reject c-out-1", None),
        ("/guild reject C-OUT-0", None),
        ("/guild merge", None),
        ("> /guild build", None),
        ("```\n/guild build\n```", None),
        ("  /guild build", None),
        ("please /guild build", None),
        ("", None),
    ],
)
def test_parse(body: str, expected: commands.Command | None) -> None:
    assert commands.parse(body) == expected


def test_fenced_block_does_not_hide_a_later_command() -> None:
    body = "```\n/guild pause\n```\n/guild build\n"
    assert commands.parse(body) == {"verb": "build", "clause": None}


def test_plan_is_a_command() -> None:
    assert commands.parse("/guild plan") == {"verb": "plan", "clause": None}
    assert commands.parse("/guild plan now") is None
