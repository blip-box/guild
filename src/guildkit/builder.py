"""The Builder's plain check: what the agent made, read as a diff.

The agent works in a checkout with no token; the workflow takes the diff
against the base commit and this module reads it. It refuses a patch that
touches the reject list, deletes a test, adds a skip or an xfail, or changes
generated files without touching their generator, and it tiers the rest. The
agent's own account of its work is not consulted.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TypedDict

from guildkit import tiers

_DIFF_HEADER = re.compile(r"^diff --git a/(.*?) b/(.*)$")
_TEST_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(test_[A-Za-z0-9_]*)")
_SKIP = re.compile(
    r"pytest\.mark\.(skip|skipif|xfail)\b|pytest\.(skip|xfail|importorskip)\(|"
    r"unittest\.(skip|skipIf|skipUnless|expectedFailure)\b"
)


class BuildRules(TypedDict):
    """The Builder's test command and the generated-file rule, from guild.toml."""

    test_command: str
    max_test_rounds: int
    generated: list[str]
    generators: list[str]


class Patch(TypedDict):
    """A unified diff, reduced to what the check needs."""

    paths: list[str]
    deleted_files: list[str]
    lines_changed: int
    added: dict[str, list[str]]
    removed: dict[str, list[str]]


class Check(TypedDict):
    """The verdict on a patch: tiered when ok, otherwise the failures."""

    ok: bool
    tier: str
    paths: list[str]
    rejected: list[str]
    failures: list[str]
    reasons: list[str]


def parse_diff(diff: str) -> Patch:
    r"""Read a `git diff` (unified, `--binary` or not) into a Patch.

    >>> p = parse_diff(
    ...     "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
    ... )
    >>> p["paths"], p["lines_changed"], p["added"]
    (['x.py'], 2, {'x.py': ['b']})
    """
    paths: list[str] = []
    deleted: list[str] = []
    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    current: str | None = None
    in_hunk = False
    changed = 0
    for line in diff.split("\n"):
        header = _DIFF_HEADER.match(line)
        if header:
            current = header[2]
            paths.append(current)
            added[current] = []
            removed[current] = []
            in_hunk = False
            continue
        if current is None:
            continue
        if line.startswith("+++ /dev/null"):
            deleted.append(current)
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+") and not line.startswith("+++"):
            added[current].append(line[1:])
            changed += 1
        elif in_hunk and line.startswith("-") and not line.startswith("---"):
            removed[current].append(line[1:])
            changed += 1
        elif line.startswith(("diff ", "Binary files", "GIT binary patch")):
            in_hunk = False
    return {
        "paths": paths,
        "deleted_files": deleted,
        "lines_changed": changed,
        "added": added,
        "removed": removed,
    }


def _is_test(path: str, tests: Sequence[str]) -> bool:
    return any(tiers.matches(path, pattern) for pattern in tests)


def deleted_tests(patch: Patch, tests: Sequence[str]) -> list[str]:
    """Return the test functions the patch removes without adding back."""
    gone: list[str] = []
    for path in patch["paths"]:
        if not _is_test(path, tests):
            continue
        before = {
            m[1] for line in patch["removed"][path] if (m := _TEST_DEF.match(line))
        }
        after = {m[1] for line in patch["added"][path] if (m := _TEST_DEF.match(line))}
        gone.extend(f"{path}: {name}" for name in sorted(before - after))
    return gone


def new_skips(patch: Patch) -> list[str]:
    """Return the added lines that skip or expect a test to fail."""
    return [
        f"{path}: {line.strip()}"
        for path in patch["paths"]
        for line in patch["added"][path]
        if _SKIP.search(line)
    ]


def generated_without_generator(patch: Patch, rules: BuildRules) -> list[str]:
    """Return generated files changed while no generator changed."""
    generated = [
        p
        for p in patch["paths"]
        if any(tiers.matches(p, g) for g in rules["generated"])
    ]
    touched = any(
        tiers.matches(p, g) for p in patch["paths"] for g in rules["generators"]
    )
    return [] if touched else generated


def check_patch(
    diff: str,
    *,
    paths: tiers.PathRules,
    shape: tiers.ShapeRules,
    tests: Sequence[str],
    rules: BuildRules,
    kinds: Sequence[str],
    floors: dict[str, str],
) -> Check:
    """Return the plain verdict on the diff: failures first, then the tier."""
    patch = parse_diff(diff)
    failures: list[str] = []
    if not patch["paths"]:
        failures.append("no change")
    decision = tiers.tier_for_paths(patch["paths"], paths)
    failures.extend(f"reject list: {path}" for path in decision["rejected"])
    failures.extend(f"deleted test: {name}" for name in deleted_tests(patch, tests))
    failures.extend(f"new skip or xfail: {line}" for line in new_skips(patch))
    failures.extend(
        f"generated without its generator: {path}"
        for path in generated_without_generator(patch, rules)
    )
    tests_changed = any(_is_test(p, tests) for p in patch["paths"])
    deleted_in_tests = sum(
        len(patch["removed"][p]) for p in patch["paths"] if _is_test(p, tests)
    )
    decision = tiers.raise_for_shape(
        decision,
        {
            "lines_changed": patch["lines_changed"],
            "lines_deleted_in_tests": deleted_in_tests,
            "files_deleted": len(patch["deleted_files"]),
            "tests_changed": tests_changed,
        },
        shape,
    )
    decision = tiers.raise_for_kinds(decision, kinds, floors)
    return {
        "ok": not failures,
        "tier": decision["tier"],
        "paths": patch["paths"],
        "rejected": decision["rejected"],
        "failures": failures,
        "reasons": decision["reasons"],
    }


def prompt(*, role: str, handbook: str, charter: str, brief: str) -> tuple[str, str]:
    """Return the Builder's system prompt and its user text: the brief."""
    system = (
        f"{role.rstrip()}\n\n# The handbook\n\n{handbook.rstrip()}"
        f"\n\n# The charter\n\n{charter.rstrip()}\n"
    )
    return system, brief
