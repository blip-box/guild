"""Risk tiers, computed by plain code from the paths a change touches.

The highest tier any rule gives wins. The shape of the diff (its size, deleted
code, edited tests) can only raise the tier. Paths on the reject list are not
tiered at all: agents draft such changes and a steward commits them.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import TypedDict


class Tier(enum.IntEnum):
    """How much human approval a change needs. Higher needs more."""

    T0 = 0  # green CI and a Reviewer pass; a steward merges without review
    T1 = 1  # one steward approves
    T2 = 2  # two stewards approve
    T3 = 3  # two stewards approve and a steward runs it


class PathRules(TypedDict):
    """Glob patterns per tier, from guild.toml. Unlisted paths get `default`."""

    reject: list[str]
    t0: list[str]
    t1: list[str]
    t2: list[str]
    t3: list[str]
    default: str


class Shape(TypedDict, total=False):
    """What a diff looks like, from `git diff --numstat` and the file list."""

    lines_changed: int
    lines_deleted_in_tests: int
    files_deleted: int
    tests_changed: bool


class ShapeRules(TypedDict):
    """Thresholds from guild.toml. Each raises the tier to at least the given one."""

    max_t0_lines: int
    deleted_tests: str
    deleted_files: str
    changed_tests: str


class Decision(TypedDict):
    """The tier, the paths that are not tiered, and why."""

    tier: str
    rejected: list[str]
    reasons: list[str]


def matches(path: str, pattern: str) -> bool:
    """Return whether the repository path matches the glob pattern.

    Patterns are the shell globs `PurePosixPath.full_match` takes, with `**`
    for any number of segments. A pattern without a slash matches a file of
    that name in any directory, as .gitignore does.

    >>> matches(".github/workflows/ci.yml", ".github/**")
    True
    >>> matches("docs/conftest.py", "conftest.py")
    True
    """
    if "/" not in pattern:
        pattern = f"**/{pattern}"
    return PurePosixPath(path).full_match(pattern)


def tier_for_paths(paths: Iterable[str], rules: PathRules) -> Decision:
    """Return the tier the touched paths need: the highest tier of any path.

    A path that no pattern matches gets the default. With no paths at all, the
    default stands.
    """
    default = Tier[rules["default"].upper()]
    found: list[Tier] = []
    rejected: list[str] = []
    reasons: list[str] = []
    for path in sorted(set(paths)):
        if any(matches(path, p) for p in rules["reject"]):
            rejected.append(path)
            continue
        for candidate in (Tier.T3, Tier.T2, Tier.T1, Tier.T0):
            key = candidate.name.lower()
            if any(matches(path, p) for p in rules[key]):  # type: ignore[literal-required]
                found.append(candidate)
                reasons.append(f"{path}: {candidate.name}")
                break
        else:
            found.append(default)
            reasons.append(f"{path}: {default.name} (default)")
    tier = max(found, default=default)
    return {"tier": tier.name, "rejected": rejected, "reasons": reasons}


def raise_for_shape(decision: Decision, shape: Shape, rules: ShapeRules) -> Decision:
    """Return the decision raised, never lowered, for the shape of the diff."""
    tier = Tier[decision["tier"]]
    reasons = list(decision["reasons"])

    def at_least(name: str, why: str) -> None:
        nonlocal tier
        floor = Tier[name.upper()]
        if floor > tier:
            tier = floor
            reasons.append(f"{why}: at least {floor.name}")

    if tier == Tier.T0 and shape.get("lines_changed", 0) > rules["max_t0_lines"]:
        at_least("t1", f"more than {rules['max_t0_lines']} lines changed")
    if shape.get("lines_deleted_in_tests", 0) > 0:
        at_least(rules["deleted_tests"], "lines deleted under tests")
    if shape.get("files_deleted", 0) > 0:
        at_least(rules["deleted_files"], "files deleted")
    if shape.get("tests_changed", False):
        at_least(rules["changed_tests"], "tests changed")
    return {"tier": tier.name, "rejected": decision["rejected"], "reasons": reasons}


def raise_for_kinds(
    decision: Decision, kinds: Sequence[str], floors: dict[str, str]
) -> Decision:
    """Return the decision raised for the declared kinds of change.

    A kind is something paths cannot show, such as "public_api" or
    "spec_departure"; the plan or the steward declares it, and `floors` maps
    it to the least tier it needs. Unknown kinds are an error, not a default.
    """
    tier = Tier[decision["tier"]]
    reasons = list(decision["reasons"])
    for kind in kinds:
        if kind not in floors:
            raise ValueError(f"unknown kind of change: {kind}")
        floor = Tier[floors[kind].upper()]
        if floor > tier:
            tier = floor
            reasons.append(f"kind {kind}: at least {floor.name}")
    return {"tier": tier.name, "rejected": decision["rejected"], "reasons": reasons}
