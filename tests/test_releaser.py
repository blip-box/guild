"""The Releaser: the log, the version, the changelog, the credits, the proposal."""

from pathlib import Path
from typing import Any

import pytest

from guildkit import config, releaser
from tests.test_ledger import ENTRY

ROOT = Path(__file__).resolve().parents[1]
SHA = [f"{n:040x}" for n in range(1, 8)]
LOG = (
    f"commit\t{SHA[1]}\t2026-11-05T10:00:00+00:00\t"
    "feat!: return None from match() (#14)\n"
    "\n"
    "src/confusable/_skeleton.py\n"
    "tests/test_skeleton.py\n"
    "\n"
    f"commit\t{SHA[2]}\t2026-11-04T10:00:00+00:00\t"
    "fix(tools): stop a form field at a label (#31)\n"
    "\n"
    "tools/guild_oracle_check.py\n"
    "\n"
    f"commit\t{SHA[3]}\t2026-10-01T10:00:00+00:00\t"
    "fix: resolve #7 under Guild (#30)\n"
    "\n"
    "src/confusable/_bidi.py\n"
    "\n"
    f"commit\t{SHA[4]}\t2026-09-30T10:00:00+00:00\t"
    "docs: add the project charter (#26)\n"
    "\n"
    "CHARTER.md\n"
    "\n"
    f"commit\t{SHA[5]}\t2026-09-29T10:00:00+00:00\tMerge something by hand\n"
    "\n"
    "README.md\n"
)
RULES: config.ReleaseRules = {
    "library": ["src/confusable/**"],
    "stale_days": 28,
    "version_files": ["pyproject.toml", "src/confusable/__init__.py"],
    "prerelease": "a",
}
LIBRARY = ["src/confusable/**"]


def test_parse_log_reads_subjects_paths_and_refs() -> None:
    commits = releaser.parse_log(LOG)
    assert [c["type"] for c in commits] == ["feat", "fix", "fix", "docs", "other"]
    assert commits[0]["breaking"] is True
    assert commits[0]["text"] == "return None from match() (#14)"
    assert commits[0]["refs"] == [14]
    assert commits[0]["paths"] == [
        "src/confusable/_skeleton.py",
        "tests/test_skeleton.py",
    ]
    assert commits[1]["scope"] == "tools"
    assert commits[2]["refs"] == [7, 30]
    assert commits[2]["date"] == "2026-10-01"
    assert commits[4] == {
        "sha": SHA[5],
        "date": "2026-09-29",
        "type": "other",
        "scope": "",
        "breaking": False,
        "text": "Merge something by hand",
        "paths": ["README.md"],
        "refs": [],
    }
    escaped = releaser.parse_log(
        f"commit\t{SHA[1]}\t2026-11-05T10:00:00Z\tfix: p\u0430ypal\n"
    )
    assert escaped[0]["text"] == "pU+0430ypal"
    assert releaser.parse_log("") == []
    for bad in (
        "commit\tabc\t2026-11-05\tfix: x\n",
        "src/x.py\n",
        f"commit\t{SHA[1]}\n",
    ):
        with pytest.raises(releaser.ReleaseError):
            releaser.parse_log(bad)


@pytest.mark.parametrize(
    ("last", "project", "kind", "pre", "expected"),
    [
        (None, "0.1.0.dev0", "minor", "a", "0.1.0a1"),
        ("", "0.1.0.dev0", "patch", "", "0.1.0"),
        ("v0.1.0a1", "0.1.0.dev0", "minor", "a", "0.1.0a2"),
        ("v0.1.0a2", "0.1.0.dev0", "major", "", "0.1.0"),
        ("v0.1.0a2", "0.1.0.dev0", "patch", "rc", "0.1.0rc1"),
        ("v0.1.0", "0.1.1.dev0", "patch", "", "0.1.1"),
        ("v0.1.0", "0.1.1.dev0", "minor", "", "0.2.0"),
        ("v0.1.0", "0.1.1.dev0", "minor", "a", "0.2.0a1"),
        ("v1.2.3", "1.2.4.dev0", "major", "b", "2.0.0b1"),
        ("1.2.3", "1.2.4.dev0", "patch", "", "1.2.4"),
    ],
)
def test_next_version(
    last: str | None, project: str, kind: str, pre: str, expected: str
) -> None:
    assert releaser.next_version(last, project, kind, pre) == expected


def test_versions_are_checked() -> None:
    assert releaser.parse_version("v0.1.0rc3") == {
        "major": 0,
        "minor": 1,
        "patch": 0,
        "pre": "rc",
        "n": 3,
    }
    for bad in ("1.2", "v1", "1.2.3-beta", "latest", "1.2.3.post1"):
        with pytest.raises(releaser.ReleaseError, match="version"):
            releaser.parse_version(bad)


def test_due_and_bump() -> None:
    commits = releaser.parse_log(LOG)
    reason = releaser.due(commits, library=LIBRARY, stale_days=28, today="2026-11-05")
    assert reason == f"a breaking change to the library landed, {SHA[1][:7]}"
    tools_only = [commits[1]]
    assert (
        releaser.due(tools_only, library=LIBRARY, stale_days=28, today="2026-11-05")
        is None
    )
    stale = [commits[3]]
    assert releaser.due(stale, library=LIBRARY, stale_days=28, today="2026-11-05") == (
        "the oldest of 1 unreleased changes is 36 days old"
    )
    assert (
        releaser.due(stale, library=LIBRARY, stale_days=37, today="2026-11-05") is None
    )
    assert (
        releaser.due([], library=["src/**"], stale_days=1, today="2026-11-05") is None
    )
    assert releaser.bump(commits, major_is_breaking=False) == "minor"
    assert releaser.bump(commits, major_is_breaking=True) == "major"
    assert releaser.bump(commits[1:], major_is_breaking=True) == "patch"
    feat = releaser.parse_log(f"commit\t{SHA[6]}\t2026-11-05T00:00:00Z\tfeat: x\n")
    assert releaser.bump(feat, major_is_breaking=True) == "minor"
    assert releaser.bump([], major_is_breaking=True) == "patch"


def test_changelog_and_credits() -> None:
    commits = releaser.parse_log(LOG)
    assert releaser.changelog(commits) == (
        "### Breaking changes\n\n- return None from match() (#14)\n\n"
        "### Fixes\n\n- stop a form field at a label (#31)\n"
        "- resolve #7 under Guild (#30)\n\n"
        "And 2 other changes: documentation, tooling, dependencies.\n"
    )
    assert releaser.changelog([]) == "No changes.\n"
    one = releaser.changelog([commits[3]])
    assert one == "And 1 other change: documentation, tooling, dependencies.\n"

    def entry(number: int, role: str, outcome: str, author: str) -> Any:
        return {
            **ENTRY,
            "number": number,
            "role": role,
            "outcome": outcome,
            "author": author,
        }

    entries = [
        entry(7, "builder", "patched", "reporter"),
        entry(7, "triage", "posted", "reporter"),
        entry(30, "builder", "patched", "other"),
        entry(9, "builder", "patched", "unshipped"),
        entry(14, "builder", "failed", "failed"),
        entry(14, "builder", "patched", ""),
    ]
    assert releaser.credits(commits, entries) == ["other", "reporter"]
    assert releaser.credits(commits, []) == []


def test_propose_and_render() -> None:
    commits = releaser.parse_log(LOG)
    entries: list[Any] = [
        {
            **ENTRY,
            "number": 7,
            "role": "builder",
            "outcome": "patched",
            "author": "reporter",
        }
    ]
    proposal = releaser.propose(
        commits,
        entries=entries,
        last_tag="",
        project_version="0.1.0.dev0",
        head=SHA[1],
        today="2026-11-05",
        tests_exit=0,
        rules=RULES,
    )
    assert proposal["due"] is True
    assert proposal["version"] == "0.1.0a1"
    assert proposal["previous"] == "(none)"
    assert proposal["bump"] == "minor"
    assert proposal["commits"] == 5
    assert proposal["by_type"] == {"docs": 1, "feat": 1, "fix": 2, "other": 1}
    assert proposal["oldest"] == "2026-09-29"
    assert proposal["credits"] == ["reporter"]
    assert proposal["earliest"] == "2026-11-08"
    assert proposal["tests_passed"] is True
    assert len(proposal["content_hash"]) == 64
    templates = ROOT / "templates" / "release"
    title, body = releaser.render(
        proposal,
        commits,
        title_template=(templates / "title.md").read_text(encoding="ascii"),
        body_template=(templates / "proposal.md").read_text(encoding="ascii"),
        run_url="https://example.invalid/run",
        version_files=RULES["version_files"],
    )
    assert title == "Release 0.1.0a1 proposed\n"
    assert body.startswith(
        f"Guild proposes releasing 0.1.0a1 from {SHA[1][:7]}, the last release"
        " being (none)."
    )
    assert f"Why now: a breaking change to the library landed, {SHA[1][:7]}." in body
    assert "### Breaking changes\n\n- return None from match() (#14)\n" in body
    assert "Reports from reporter were confirmed and fixed in this release." in body
    assert "may run from 2026-11-08 onwards" in body
    assert "The test suite at " in body
    assert ": passed." in body
    assert (
        "Bump the version to 0.1.0a1 in `pyproject.toml`, `src/confusable/__init__.py`"
        in body
    )
    assert "Decision record: https://example.invalid/run" in body
    assert body.isascii()
    not_due = releaser.propose(
        [commits[1]],
        entries=[],
        last_tag="v0.1.0a1",
        project_version="0.1.0.dev0",
        head=SHA[1],
        today="2026-11-05",
        tests_exit=1,
        rules=RULES,
    )
    assert not_due["due"] is False
    assert not_due["reason"] == "no fix or feature to the library, and nothing stale"
    assert not_due["version"] == "0.1.0a2"
    assert not_due["previous"] == "v0.1.0a1"
    assert not_due["credits"] == []
    _, body = releaser.render(
        not_due,
        [commits[1]],
        title_template="{version}",
        body_template="{tests}{credits}",
        run_url="u",
        version_files=[],
    )
    assert body == "FAILED, fix it first"
    assert releaser.markdown(not_due).startswith(
        "Release 0.1.0a2 not due: no fix or feature to the library, and nothing"
        " stale.\nSince v0.1.0a1: 1 commits, the oldest from 2026-11-04; bump patch;"
        " tests failed; 0 reporters credited.\n- fix: 1\n"
    )
    with pytest.raises(releaser.ReleaseError, match="unknown placeholders"):
        releaser.fill("{version} {nope}", {"version": "1"})
    with pytest.raises(releaser.ReleaseError, match="head"):
        releaser.propose(
            [],
            entries=[],
            last_tag="",
            project_version="0.1.0",
            head="abc",
            today="2026-11-05",
            tests_exit=0,
            rules=RULES,
        )


def test_a_merged_bump_awaiting_its_tag_is_in_progress() -> None:
    """The push of the version bump reaches the Releaser before the tag does.

    The first release under Guild got a second proposal that way: the bump
    merged as c1238d0, the run saw v0.1.0a2 as the last tag and proposed
    0.1.0a3 again, with a checklist to bump a version already bumped.
    """
    bump = releaser.parse_log(
        f"commit\t{SHA[6]}\t2026-11-10T01:43:55+00:00\t"
        "chore(release): bump the version to 0.1.0a3 (#56)\n\n"
        "pyproject.toml\nsrc/confusable/__init__.py\n"
    )
    feat = releaser.parse_log(
        f"commit\t{SHA[5]}\t2026-11-10T01:19:00+00:00\t"
        "feat(compat): add an opt-in install() (#46)\n\n"
        "src/confusable/compat/homoglyphs/__init__.py\n"
    )
    proposal = releaser.propose(
        bump + feat,
        entries=[],
        last_tag="v0.1.0a2",
        project_version="0.1.0a3",
        head=SHA[6],
        today="2026-11-10",
        tests_exit=0,
        rules=RULES,
    )
    assert proposal["in_progress"] is True
    assert proposal["due"] is False
    assert proposal["version"] == "0.1.0a3"
    assert proposal["reason"] == (
        "the version files already name 0.1.0a3, newer than v0.1.0a2:"
        " a release is in progress, awaiting its tag"
    )
    assert releaser.markdown(proposal).startswith("Release 0.1.0a3 in progress:")
    # The same feat before the bump is due, as it was.
    assert (
        releaser.propose(
            feat,
            entries=[],
            last_tag="v0.1.0a2",
            project_version="0.1.0a2",
            head=SHA[5],
            today="2026-11-10",
            tests_exit=0,
            rules=RULES,
        )["due"]
        is True
    )
    # Once tagged, nothing is unreleased and nothing is in progress.
    after = releaser.propose(
        [],
        entries=[],
        last_tag="v0.1.0a3",
        project_version="0.1.0a3",
        head=SHA[6],
        today="2026-11-10",
        tests_exit=0,
        rules=RULES,
    )
    assert after["in_progress"] is False
    assert after["due"] is False
    # Without a tag nothing is in progress; a dev version is not ahead.
    assert releaser.in_progress("", "0.2.0") is False
    assert releaser.in_progress("v0.1.0a3", "0.1.0a3.dev0") is False
    assert releaser.in_progress("v0.1.0a3", "0.1.0") is True
    assert releaser.in_progress("v0.1.0", "0.1.0rc1") is False
    assert releaser.in_progress("v0.1.0a1", "0.1.0.dev0") is False
    assert releaser.version_key("0.1.0a2") < releaser.version_key("0.1.0b1")
    assert releaser.version_key("0.1.0rc1") < releaser.version_key("0.1.0")
    assert releaser.version_key("0.1.0.dev0") < releaser.version_key("0.1.0a1")
    assert releaser.version_key("0.1.0a1.dev0") < releaser.version_key("0.1.0a1")
    assert releaser.version_key("v0.1.0a1") == releaser.version_key("0.1.0a1")
    with pytest.raises(releaser.ReleaseError, match="version"):
        releaser.version_key("1.2")


def test_closing_a_stale_proposal() -> None:
    """Shipped when the last tag is the proposed version, no longer due
    otherwise; a due or in-progress run keeps the proposal."""
    after = releaser.propose(
        [],
        entries=[],
        last_tag="v0.1.0a3",
        project_version="0.1.0a3",
        head=SHA[6],
        today="2026-11-10",
        tests_exit=0,
        rules=RULES,
    )
    shipped = releaser.closing(
        "Release 0.1.0a3 proposed\n", last_tag="v0.1.0a3", proposal=after
    )
    assert shipped == {"why": "this release shipped as v0.1.0a3", "reason": "completed"}
    stale = releaser.closing(
        "Release 0.1.0a4 proposed", last_tag="v0.1.0a3", proposal=after
    )
    assert stale["reason"] == "not planned"
    assert stale["why"] == (
        "a release is no longer due:"
        " no fix or feature to the library, and nothing stale"
    )
    odd = releaser.closing("Something else", last_tag="v0.1.0a3", proposal=after)
    assert odd["reason"] == "not planned"
    assert (
        releaser.closing(
            "Release nonsense proposed", last_tag="v0.1.0a3", proposal=after
        )["reason"]
        == "not planned"
    )
    template = (ROOT / "templates" / "release" / "closed.md").read_text(
        encoding="ascii"
    )
    comment = releaser.render_closing(
        shipped,
        template=template,
        previous=after["previous"],
        run_url="https://example.invalid/run",
    )
    assert comment.startswith(
        "Guild closes this proposal: this release shipped as v0.1.0a3."
        " The last release is v0.1.0a3."
    )
    assert comment.rstrip().endswith("Decision record: https://example.invalid/run")
    assert comment.isascii()
    due = releaser.propose(
        releaser.parse_log(LOG),
        entries=[],
        last_tag="",
        project_version="0.1.0.dev0",
        head=SHA[1],
        today="2026-11-05",
        tests_exit=0,
        rules=RULES,
    )
    with pytest.raises(releaser.ReleaseError, match="the proposal stands"):
        releaser.closing("Release 0.1.0a1 proposed", last_tag="", proposal=due)
    pending = releaser.propose(
        [],
        entries=[],
        last_tag="v0.1.0a2",
        project_version="0.1.0a3",
        head=SHA[6],
        today="2026-11-10",
        tests_exit=0,
        rules=RULES,
    )
    with pytest.raises(releaser.ReleaseError, match="the proposal stands"):
        releaser.closing(
            "Release 0.1.0a3 proposed", last_tag="v0.1.0a2", proposal=pending
        )
