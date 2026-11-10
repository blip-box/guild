"""The Releaser: a script that proposes a release. No model call.

The plan gave the Releaser one bounded model call, for the release notes.
It makes none. The change list is the merged pull request titles, which a
steward wrote or approved and CI linted as Conventional Commits; the credits
come from the ledger; the version follows from the commit types and the
last tag. A model would add phrasing and nothing else, and no model text
may reach an issue.

A release is due when a merged fix or feature touched the library, or when
the oldest unreleased change is older than `release.stale_days`. The
proposal is an issue a steward acts on: releases are tier 3.

Two states are not proposals. When the version files at the head already
name a version newer than the last tag, a steward has merged the bump and
the tag is on its way: the release is in progress, and nothing is proposed,
because the push of the bump reaches this script before the tag does (the
first release under Guild got a second proposal that way). And when nothing
is due but a proposal is still open, `closing` says how to close it: as
shipped, when the last tag is the version it proposed, or as no longer due.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any, Literal, TypedDict

from guildkit import text, tiers
from guildkit.config import ReleaseRules
from guildkit.ledger import Entry

# Conventional Commit types that change what the library does.
BEHAVIOUR = ("feat", "fix", "perf")
SECTIONS = (
    ("breaking", "Breaking changes"),
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("perf", "Performance"),
)
# The public notice with one steward: 72 hours (docs/plan.md, section 5).
NOTICE_DAYS = 3
_SUBJECT = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: (?P<text>\S.*)$"
)
_REF = re.compile(r"#(\d+)\b")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_VERSION = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:(?P<pre>a|b|rc)(?P<n>\d+))?(?:\.dev(?P<dev>\d+))?$"
)
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


class Commit(TypedDict):
    """One unreleased commit, read from `git log`."""

    sha: str
    date: str
    type: str
    scope: str
    breaking: bool
    text: str
    paths: list[str]
    refs: list[int]


class Version(TypedDict):
    """A version, parsed: PEP 440's final and pre-release forms."""

    major: int
    minor: int
    patch: int
    pre: str
    n: int


class Proposal(TypedDict):
    """The release proposal: numbers, enumerations, identifiers and the reason."""

    due: bool
    # The bump is merged and the tag is not: propose nothing, close nothing.
    in_progress: bool
    reason: str
    version: str
    previous: str
    bump: str
    head: str
    commits: int
    by_type: dict[str, int]
    oldest: str
    credits: list[str]
    tests_passed: bool
    earliest: str
    content_hash: str


class ReleaseError(ValueError):
    """Input the Releaser cannot use."""


def parse_log(log: str) -> list[Commit]:
    """Read `git log --format='commit%x09%H%x09%cI%x09%s' --name-only`.

    Newest first, as git prints it. A subject that is not a Conventional
    Commit gets the type `other`.
    """
    commits: list[Commit] = []
    for line in log.split("\n"):
        if line.startswith("commit\t"):
            parts = line.split("\t", 3)
            if len(parts) != 4 or not _SHA.match(parts[1]) or len(parts[2]) < 10:
                raise ReleaseError(f"log line: {line[:80]!r}")
            _, sha, when, subject = parts
            match = _SUBJECT.match(subject)
            commits.append(
                {
                    "sha": sha,
                    "date": when[:10],
                    "type": match["type"] if match else "other",
                    "scope": (match["scope"] or "") if match else "",
                    "breaking": bool(match["bang"]) if match else False,
                    "text": text.escape(match["text"] if match else subject),
                    "paths": [],
                    "refs": [int(n) for n in _REF.findall(subject)],
                }
            )
        elif line.strip():
            if not commits:
                raise ReleaseError("a path before any commit")
            commits[-1]["paths"].append(line.strip())
    return commits


def parse_version(value: str) -> Version:
    """Return the parts of a version or tag, or raise ReleaseError."""
    match = _VERSION.match(value.strip())
    if not match:
        raise ReleaseError(f"version: {value!r}")
    return {
        "major": int(match["major"]),
        "minor": int(match["minor"]),
        "patch": int(match["patch"]),
        "pre": match["pre"] or "",
        "n": int(match["n"]) if match["n"] else 0,
    }


def _format(major: int, minor: int, patch: int, pre: str, n: int) -> str:
    return f"{major}.{minor}.{patch}" + (f"{pre}{n}" if pre else "")


# PEP 440 order of the pre-release segments; a final release sorts last.
_PRE_ORDER = {"a": 0, "b": 1, "rc": 2, "": 3}


def version_key(value: str) -> tuple[int, int, int, int, int, int, int]:
    """Return a sort key for a version or tag, in PEP 440 order.

    A dev release sorts before the release it leads to: 0.1.0.dev0 comes
    before 0.1.0a1, and 0.1.0a1.dev0 before 0.1.0a1.
    """
    match = _VERSION.match(value.strip())
    if not match:
        raise ReleaseError(f"version: {value!r}")
    dev = match["dev"]
    pre = match["pre"] or ""
    # A dev release of the final version sits below its first pre-release.
    pre_rank = _PRE_ORDER[pre] if pre or dev is None else -1
    return (
        int(match["major"]),
        int(match["minor"]),
        int(match["patch"]),
        pre_rank,
        int(match["n"]) if match["n"] else 0,
        0 if dev is not None else 1,
        int(dev) if dev is not None else 0,
    )


def in_progress(last_tag: str | None, project_version: str) -> bool:
    """Return whether the version files are ahead of the last tag.

    A steward has merged the version bump and the tag is still to come:
    the release is theirs to finish, not the Releaser's to propose again.
    Without a tag nothing is in progress.
    """
    if last_tag is None or not last_tag.strip():
        return False
    return version_key(project_version) > version_key(last_tag)


def touches(commit: Commit, patterns: list[str]) -> bool:
    """Return whether the commit changed a path matching any pattern."""
    return any(
        tiers.matches(p, pattern) for p in commit["paths"] for pattern in patterns
    )


def due(
    commits: list[Commit], *, library: list[str], stale_days: int, today: str
) -> str | None:
    """Return why a release is due now, in code's words, or None."""
    for commit in commits:
        if (commit["type"] in BEHAVIOUR or commit["breaking"]) and touches(
            commit, library
        ):
            kind = "breaking change" if commit["breaking"] else commit["type"]
            return f"a {kind} to the library landed, {commit['sha'][:7]}"
    if commits:
        oldest = min(c["date"] for c in commits)
        age = (date.fromisoformat(today) - date.fromisoformat(oldest)).days
        if age >= stale_days:
            return f"the oldest of {len(commits)} unreleased changes is {age} days old"
    return None


def bump(commits: list[Commit], *, major_is_breaking: bool) -> str:
    """Return major, minor or patch from the commit types.

    Before 1.0 a breaking change bumps the minor version, as PEP 440 and
    semver both allow.
    """
    if any(c["breaking"] for c in commits):
        return "major" if major_is_breaking else "minor"
    if any(c["type"] == "feat" for c in commits):
        return "minor"
    return "patch"


def next_version(
    last_tag: str | None, project_version: str, bump_kind: str, prerelease: str
) -> str:
    """Return the version to propose.

    Without a tag, the project's own version with its dev or pre-release
    suffix dropped. After a pre-release of a base, the next pre-release of
    that base, or the base itself once `prerelease` is unset. After a final
    release, the bumped version, as a pre-release when `prerelease` is set.
    """
    if last_tag is None or not last_tag.strip():
        v = parse_version(project_version)
        return _format(v["major"], v["minor"], v["patch"], prerelease, 1)
    v = parse_version(last_tag)
    if v["pre"]:
        if not prerelease:
            return _format(v["major"], v["minor"], v["patch"], "", 0)
        n = v["n"] + 1 if prerelease == v["pre"] else 1
        return _format(v["major"], v["minor"], v["patch"], prerelease, n)
    major, minor, patch = v["major"], v["minor"], v["patch"]
    if bump_kind == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump_kind == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return _format(major, minor, patch, prerelease, 1)


def changelog(commits: list[Commit]) -> str:
    """Return the change list as Markdown sections, from the subjects."""
    lines: list[str] = []
    shown: set[str] = set()
    for key, title in SECTIONS:
        if key == "breaking":
            items = [c for c in commits if c["breaking"]]
        else:
            items = [c for c in commits if c["type"] == key and not c["breaking"]]
        if items:
            lines += [f"### {title}", ""]
            lines += [f"- {c['text']}" for c in items]
            lines.append("")
            shown.update(c["sha"] for c in items)
    other = sum(1 for c in commits if c["sha"] not in shown)
    if other:
        noun = "change" if other == 1 else "changes"
        lines += [
            f"And {other} other {noun}: documentation, tooling, dependencies.",
            "",
        ]
    if not commits:
        lines += ["No changes.", ""]
    return "\n".join(lines)


def credits(commits: list[Commit], entries: list[Entry]) -> list[str]:
    """Return the reporters to credit: authors of validated reports shipped here.

    A report was validated when the Builder patched it (the brief needs the
    oracle's confirmation), and shipped when a released commit names its
    issue.
    """
    numbers = {n for c in commits for n in c["refs"]}
    return sorted(
        {
            e["author"]
            for e in entries
            if e["role"] == "builder"
            and e["outcome"] == "patched"
            and e["number"] in numbers
            and e["author"]
        }
    )


def propose(
    commits: list[Commit],
    *,
    entries: list[Entry],
    last_tag: str | None,
    project_version: str,
    head: str,
    today: str,
    tests_exit: int,
    rules: ReleaseRules,
) -> Proposal:
    """Return the proposal, due or not."""
    if not _SHA.match(head):
        raise ReleaseError(f"head: {head!r}")
    reason = due(
        commits, library=rules["library"], stale_days=rules["stale_days"], today=today
    )
    previous = last_tag.strip() if last_tag and last_tag.strip() else ""
    major_is_breaking = bool(previous) and parse_version(previous)["major"] >= 1
    kind = bump(commits, major_is_breaking=major_is_breaking)
    version = next_version(previous or None, project_version, kind, rules["prerelease"])
    pending = in_progress(previous or None, project_version)
    if pending:
        v = parse_version(project_version)
        version = _format(v["major"], v["minor"], v["patch"], v["pre"], v["n"])
        reason = None
    by_type: dict[str, int] = {}
    for c in commits:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    earliest = date.fromisoformat(today) + timedelta(days=NOTICE_DAYS)
    if pending:
        why = (
            f"the version files already name {version}, newer than {previous}:"
            " a release is in progress, awaiting its tag"
        )
    else:
        why = reason or "no fix or feature to the library, and nothing stale"
    return {
        "due": reason is not None,
        "in_progress": pending,
        "reason": why,
        "version": version,
        "previous": previous or "(none)",
        "bump": kind,
        "head": head,
        "commits": len(commits),
        "by_type": dict(sorted(by_type.items())),
        "oldest": min((c["date"] for c in commits), default=""),
        "credits": credits(commits, entries),
        "tests_passed": tests_exit == 0,
        "earliest": earliest.isoformat(),
        "content_hash": hashlib.sha256(f"{head}\n{version}".encode()).hexdigest(),
    }


def fill(template: str, values: dict[str, str]) -> str:
    """Fill `{name}` placeholders; an unknown one is an error, as in `cli`."""
    unknown = sorted(set(_PLACEHOLDER.findall(template)) - set(values))
    if unknown:
        raise ReleaseError(f"template: unknown placeholders {unknown}")
    return _PLACEHOLDER.sub(lambda m: values[m[1]], template)


def render(
    proposal: Proposal,
    commits: list[Commit],
    *,
    title_template: str,
    body_template: str,
    run_url: str,
    version_files: list[str],
) -> tuple[str, str]:
    """Return the issue title and body from the templates."""
    thanks = ""
    if proposal["credits"]:
        thanks = (
            "## Thanks\n\nReports from "
            + ", ".join(proposal["credits"])
            + " were confirmed and fixed in this release.\n\n"
        )
    values = {
        "version": proposal["version"],
        "previous": proposal["previous"],
        "head": proposal["head"][:7],
        "reason": proposal["reason"],
        "changelog": changelog(commits).rstrip("\n") + "\n",
        "credits": thanks,
        "earliest": proposal["earliest"],
        "tests": "passed" if proposal["tests_passed"] else "FAILED, fix it first",
        "version_files": ", ".join(f"`{f}`" for f in version_files),
        "run_url": run_url,
    }
    return fill(title_template, values), fill(body_template, values)


_TITLE = re.compile(r"^Release (?P<version>\S+) proposed\s*$")


class Closing(TypedDict):
    """How to close an open proposal when no release is due."""

    why: str
    reason: Literal["completed", "not planned"]


def closing(title: str, *, last_tag: str | None, proposal: Proposal) -> Closing:
    """Return why and how to close the open proposal `title`.

    Shipped, when the last tag is the version the proposal named; no longer
    due otherwise, with the Releaser's reason. Not for a due or in-progress
    run, which keeps the proposal.
    """
    if proposal["due"] or proposal["in_progress"]:
        raise ReleaseError("closing: the proposal stands")
    match = _TITLE.match(title.strip())
    proposed = match["version"] if match else ""
    tag = last_tag.strip() if last_tag and last_tag.strip() else ""
    if proposed and tag:
        try:
            shipped = version_key(proposed) == version_key(tag)
        except ReleaseError:
            shipped = False
        if shipped:
            return {"why": f"this release shipped as {tag}", "reason": "completed"}
    return {
        "why": f"a release is no longer due: {proposal['reason']}",
        "reason": "not planned",
    }


def render_closing(
    closing_: Closing, *, template: str, previous: str, run_url: str
) -> str:
    """Return the comment that closes the proposal, from the template."""
    return fill(
        template, {"why": closing_["why"], "previous": previous, "run_url": run_url}
    )


def markdown(proposal: Proposal) -> str:
    """Return the proposal for a step summary."""
    state = "due" if proposal["due"] else "not due"
    if proposal["in_progress"]:
        state = "in progress"
    lines = [
        f"Release {proposal['version']} {state}: {proposal['reason']}.",
        f"Since {proposal['previous']}: {proposal['commits']} commits"
        + (f", the oldest from {proposal['oldest']}" if proposal["oldest"] else "")
        + f"; bump {proposal['bump']}; tests"
        f" {'passed' if proposal['tests_passed'] else 'failed'};"
        f" {len(proposal['credits'])} reporters credited.",
    ]
    for kind, count in proposal["by_type"].items():
        lines.append(f"- {kind}: {count}")
    return "\n".join(lines) + "\n"


def as_dict(proposal: Proposal) -> dict[str, Any]:
    """Return the proposal as a plain dict for JSON."""
    return dict(proposal)
