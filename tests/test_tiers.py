import pytest

from guildkit import tiers

RULES: tiers.PathRules = {
    "reject": [".github/**", "AGENTS.md", "conftest.py"],
    "t0": ["*.md", "src/pkg/_data/**"],
    "t1": [],
    "t2": ["pyproject.toml", "tools/**"],
    "t3": [],
    "default": "t1",
}
SHAPE: tiers.ShapeRules = {
    "max_t0_lines": 50,
    "deleted_tests": "t2",
    "deleted_files": "t1",
    "changed_tests": "t1",
}


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        (".github/workflows/ci.yml", ".github/**", True),
        (".github/CODEOWNERS", ".github/**", True),
        ("docs/conftest.py", "conftest.py", True),
        ("conftest.py", "conftest.py", True),
        ("src/conftest.py.bak", "conftest.py", False),
        ("README.md", "*.md", True),
        ("docs/guide.md", "*.md", True),
        ("src/pkg/_data/x.py", "src/pkg/_data/**", True),
        ("src/pkg/data/x.py", "src/pkg/_data/**", False),
    ],
)
def test_matches(path: str, pattern: str, expected: bool) -> None:
    assert tiers.matches(path, pattern) is expected


def test_highest_tier_wins() -> None:
    decision = tiers.tier_for_paths(
        ["README.md", "src/pkg/core.py", "tools/gen.py"], RULES
    )
    assert decision["tier"] == "T2"
    assert decision["rejected"] == []
    assert decision["reasons"] == [
        "README.md: T0",
        "src/pkg/core.py: T1 (default)",
        "tools/gen.py: T2",
    ]


def test_docs_only_is_t0() -> None:
    assert tiers.tier_for_paths(["README.md", "docs/a.md"], RULES)["tier"] == "T0"


def test_reject_wins_over_every_tier() -> None:
    decision = tiers.tier_for_paths(["AGENTS.md", "README.md"], RULES)
    assert decision["rejected"] == ["AGENTS.md"]
    assert decision["tier"] == "T0"


def test_no_paths_gives_the_default() -> None:
    assert tiers.tier_for_paths([], RULES)["tier"] == "T1"


def test_shape_only_raises() -> None:
    t0 = tiers.tier_for_paths(["README.md"], RULES)
    assert tiers.raise_for_shape(t0, {"lines_changed": 10}, SHAPE)["tier"] == "T0"
    assert tiers.raise_for_shape(t0, {"lines_changed": 51}, SHAPE)["tier"] == "T1"
    assert (
        tiers.raise_for_shape(t0, {"lines_deleted_in_tests": 1}, SHAPE)["tier"] == "T2"
    )
    assert tiers.raise_for_shape(t0, {"files_deleted": 1}, SHAPE)["tier"] == "T1"
    assert tiers.raise_for_shape(t0, {"tests_changed": True}, SHAPE)["tier"] == "T1"
    t2 = tiers.tier_for_paths(["tools/gen.py"], RULES)
    assert tiers.raise_for_shape(t2, {"lines_changed": 1}, SHAPE)["tier"] == "T2"


def test_shape_reasons_are_recorded() -> None:
    raised = tiers.raise_for_shape(
        tiers.tier_for_paths(["README.md"], RULES), {"lines_deleted_in_tests": 3}, SHAPE
    )
    assert raised["reasons"][-1] == "lines deleted under tests: at least T2"


def test_kinds_raise_and_unknown_kinds_fail() -> None:
    t1 = tiers.tier_for_paths(["src/pkg/core.py"], RULES)
    floors = {"public_api": "t2", "release": "t3"}
    assert tiers.raise_for_kinds(t1, ["public_api"], floors)["tier"] == "T2"
    assert tiers.raise_for_kinds(t1, ["release", "public_api"], floors)["tier"] == "T3"
    assert tiers.raise_for_kinds(t1, [], floors)["tier"] == "T1"
    with pytest.raises(ValueError, match="unknown kind"):
        tiers.raise_for_kinds(t1, ["cosmetic"], floors)
