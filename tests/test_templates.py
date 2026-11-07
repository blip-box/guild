"""The workflow and comment templates keep their invariants."""

import re
from pathlib import Path

from guildkit import triage

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / "templates" / "workflows").glob("*.yml"))
OWN = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
COMMENTS = sorted((ROOT / "templates" / "comments").glob("*.md"))
KNOWN_PLACEHOLDERS = {
    "decision_url",
    "charter_url",
    "clause",
    "severity",
    "oracle",
    "missing_list",
}


def first_job_checks_the_kill_switch(path: Path) -> None:
    text = path.read_text(encoding="ascii")
    jobs = text.index("\njobs:\n")
    first = re.search(r"\n  ([a-z-]+):\n(.*?)\n    steps:", text[jobs:], re.S)
    assert first is not None, path.name
    assert "vars.GUILD_PAUSED != 'true'" in first[2], f"{path.name}: {first[1]}"


def test_every_workflow_checks_the_kill_switch_first() -> None:
    """The first job of every template skips when GUILD_PAUSED is true."""
    assert len(WORKFLOWS) >= 4
    for path in WORKFLOWS:
        first_job_checks_the_kill_switch(path)


def test_every_workflow_pins_actions_and_holds_no_credentials() -> None:
    assert len(OWN) >= 3
    for path in WORKFLOWS + OWN:
        text = path.read_text(encoding="ascii")
        assert "permissions: {}" in text, path.name
        for match in re.finditer(r"uses: ([^@\n]+)@([0-9a-f]+) # v", text):
            assert len(match[2]) == 40, f"{path.name}: {match[0]}"
        assert re.search(r"uses: [^\n]+@(?![0-9a-f]{40} # v)", text) is None, path.name
        for match in re.finditer(
            r"uses: actions/checkout@[^\n]+\n((?:          [^\n]*\n)+)", text
        ):
            assert "persist-credentials: false" in match[1], path.name


APP_TOKEN = re.compile(
    r"uses: actions/create-github-app-token@[0-9a-f]{40} # v[^\n]*\n"
    r"(?:[ ]+(?!with:)[a-z-]+: [^\n]*\n){0,2}"
    r"[ ]+with:\n"
    r"[ ]+client-id: \$\{\{ vars\.GUILD_(TRIAGE|BUILDER|GATE)_CLIENT_ID \}\}\n"
    r"[ ]+private-key: \$\{\{ secrets\.GUILD_\1_APP_KEY \}\}\n"
)


def test_app_tokens_come_from_client_ids() -> None:
    """Every App token step passes the App's Client ID and its private key.

    create-github-app-token retired ``app-id`` for ``client-id``, and the
    variable is named for what it holds.
    """
    steps = 0
    for path in WORKFLOWS + OWN:
        text = path.read_text(encoding="ascii")
        assert "app-id" not in text, path.name
        assert "_APP_ID" not in text, path.name
        uses = text.count("uses: actions/create-github-app-token@")
        assert len(APP_TOKEN.findall(text)) == uses, path.name
        steps += uses
    assert steps >= 12


def test_scheduled_workflows_pause_and_are_watched_by_ci() -> None:
    """A scheduled workflow stops on GUILD_PAUSED, and CI fails while it is disabled."""
    scheduled = [
        path.name
        for path in OWN
        if "\n  schedule:\n" in path.read_text(encoding="ascii")
    ]
    assert scheduled == ["canary.yml"]
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="ascii")
    listed = re.search(r"for name in ([^;]+); do", ci)
    assert listed is not None
    assert sorted(listed[1].split()) == sorted(scheduled)
    for name in scheduled:
        path = ROOT / ".github" / "workflows" / name
        first_job_checks_the_kill_switch(path)
        text = path.read_text(encoding="ascii")
        assert "if: failure()" in text or "needs.canary.result" in text, name
        assert "gh issue create" in text, name


def test_comment_templates_use_known_placeholders_only() -> None:
    assert COMMENTS
    for path in COMMENTS:
        text = path.read_text(encoding="ascii")
        used = set(re.findall(r"\{([a-z_]+)\}", text))
        assert used <= KNOWN_PLACEHOLDERS, f"{path.name}: {used - KNOWN_PLACEHOLDERS}"
        assert "{decision_url}" in text, path.name
        assert text.rstrip().endswith("Decision record: {decision_url}"), path.name


def test_queued_template_renders() -> None:
    record = triage.apply_policy(
        {"kind": "other", "severity": "none", "clause": None, "missing": []}, "not_run"
    )
    record["template"] = "queued"
    comment = triage.render_comment(
        record,
        ROOT / "templates" / "comments",
        {"decision_url": "u", "charter_url": "c"},
    )
    assert comment.startswith("Thank you. Guild has reached its limit")


def test_build_template_makes_two_attempts_at_most() -> None:
    text = (ROOT / "templates" / "workflows" / "guild-build.yml").read_text(
        encoding="ascii"
    )
    jobs = re.findall(r"\n  ([a-z0-9-]+):\n", text[text.index("\njobs:\n") :])
    assert jobs == [
        "command",
        "intake",
        "triage",
        "plan",
        "plan-post",
        "build",
        "check",
        "build-2",
        "check-2",
        "build-failed",
        "review",
        "open",
        "ledger",
    ]
    assert "--attempt 1 ||" in text
    assert "--attempt 2 ||" in text
    assert "--second-attempt" in text
    assert "needs.check.outputs.escalate == 'true'" in text
    assert "'build_escalated' || 'build_failed'" in text
    # The attempt that passed is the one reviewed and opened.
    assert text.count("needs.check.outputs.ok == 'true' && 'build' || 'build-2'") == 2
    assert text.count("needs.check.outputs.ok == 'true' && 'check' || 'check-2'") == 1


def test_release_templates_use_known_placeholders_only() -> None:
    known = {
        "version",
        "previous",
        "head",
        "reason",
        "changelog",
        "credits",
        "earliest",
        "tests",
        "version_files",
        "run_url",
    }
    paths = sorted((ROOT / "templates" / "release").glob("*.md"))
    assert [p.name for p in paths] == ["proposal.md", "title.md"]
    for path in paths:
        text = path.read_text(encoding="ascii")
        used = set(re.findall(r"\{([a-z_]+)\}", text))
        assert used <= known, f"{path.name}: {used - known}"
    body = (ROOT / "templates" / "release" / "proposal.md").read_text(encoding="ascii")
    assert "no model wrote any of it" in body
    assert body.rstrip().endswith("Decision record: {run_url}")
