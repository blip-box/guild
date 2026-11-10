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


def test_graphql_variables_travel_as_an_object() -> None:
    """Every GraphQL call sends its variables through --input.

    `gh api graphql -F input=@file` sends the file's text as the variable, and
    GitHub rejects a string where CreateCommitOnBranchInput is expected; the
    first shadow run's ledger job failed five times on it.
    """
    calls = 0
    for path in WORKFLOWS:
        text = path.read_text(encoding="ascii")
        assert "-F input=" not in text, path.name
        for line in text.splitlines():
            if "gh api graphql" in line:
                assert "--input" in line, f"{path.name}: {line.strip()}"
                calls += 1
    assert calls >= 4


def test_dispatchable_workflows_take_the_issue_from_the_input_too() -> None:
    """Where a workflow can be dispatched for an issue, every use of the number
    falls back to the input.

    The rehearsal dispatches the triage workflow for an issue; its post job
    read only the event's number, found none, and failed on an empty string.
    """
    checked = 0
    for path in WORKFLOWS:
        text = path.read_text(encoding="ascii")
        if not re.search(r"workflow_dispatch:\n    inputs:\n      issue:", text):
            continue
        checked += 1
        for match in re.finditer(
            r"\$\{\{[^}]*github\.event\.issue\.number[^}]*\}\}", text
        ):
            assert "|| inputs.issue" in match[0], f"{path.name}: {match[0]}"
    assert checked >= 1


def test_triage_intake_skips_what_bots_open_and_write() -> None:
    """Neither an issue a bot opened nor a bot's comment starts triage.

    The first weekly report opened its issue as the Triage App, and triage
    classified it and asked for a steward: the intake condition checked the
    comment's author but not the issue's. Guild's own issues, Actions' and
    Dependabot's are not submissions, whoever comments on them.
    """
    text = (ROOT / "templates" / "workflows" / "guild-triage.yml").read_text(
        encoding="ascii"
    )
    jobs = text[text.index("\njobs:\n") :]
    intake = re.search(r"\n  intake:\n(.*?)\n    runs-on:", jobs, re.S)
    assert intake is not None
    condition = re.search(r"\n    if: >-\n(.*)", intake[1], re.S)
    assert condition is not None
    assert "github.event.issue.pull_request == null" in condition[1]
    assert "github.event.issue.user.type != 'Bot'" in condition[1]
    assert "github.event.comment.user.type != 'Bot'" in condition[1]
    assert "github.event_name == 'workflow_dispatch'" in condition[1]


def test_triage_intake_skips_closed_issues_and_commands() -> None:
    """A closed issue is decided, and a `/guild` comment is a command.

    Without these, a steward's `/guild build` started a triage run on the
    command's text next to the build, and any comment on a closed issue
    brought the templated reply back.
    """
    text = (ROOT / "templates" / "workflows" / "guild-triage.yml").read_text(
        encoding="ascii"
    )
    jobs = text[text.index("\njobs:\n") :]
    intake = re.search(r"\n  intake:\n(.*?)\n    runs-on:", jobs, re.S)
    assert intake is not None
    assert "github.event.issue.state == 'open'" in intake[1]
    command = "startsWith(github.event.comment.body, '/guild ')"
    assert f"!{command}" in intake[1]
    # The same literal the build workflow's command job tests, so a comment
    # is a command for one workflow exactly when it is for the other.
    build = (ROOT / "templates" / "workflows" / "guild-build.yml").read_text(
        encoding="ascii"
    )
    assert f"&& {command}" in build


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


def test_build_template_records_grades_and_the_report_counts_them() -> None:
    """A steward's `/guild confirm` or `/guild overrule` is an entry the ledger
    job appends, and the report passes the canary's passes to the shell."""
    build = (ROOT / "templates" / "workflows" / "guild-build.yml").read_text(
        encoding="ascii"
    )
    assert "confirm|overrule)" in build
    assert "guildkit grade" in build
    assert "name: entry-steward" in build
    assert (
        "if: always() && (needs.intake.result == 'success'"
        " || needs.command.outputs.graded == 'true')"
    ) in build
    ledger_needs = re.search(
        r"\n  ledger:\n    name: ledger\n    needs: \[([^\]]+)\]", build
    )
    assert ledger_needs is not None
    assert ledger_needs[1].startswith("command, intake")
    report = (ROOT / "templates" / "workflows" / "guild-report.yml").read_text(
        encoding="ascii"
    )
    assert "--workflow canary.yml" in report
    assert '--canary-passes "$CANARY_PASSES"' in report


def test_grades_do_not_queue_behind_each_other() -> None:
    """A grade comment gets its own concurrency group, keyed by the comment.

    GitHub keeps one waiting run per group and cancels the rest; three
    grades posted within a minute on confusable #61 lost the middle one.
    """
    text = (ROOT / "templates" / "workflows" / "guild-build.yml").read_text(
        encoding="ascii"
    )
    group = re.search(r"\nconcurrency:\n  group: (.*)\n", text)
    assert group is not None
    assert group[1].startswith("guild-build-${{ github.event.issue.number }}")
    assert "startsWith(github.event.comment.body, '/guild confirm ')" in group[1]
    assert "startsWith(github.event.comment.body, '/guild overrule ')" in group[1]
    assert "format('-{0}', github.event.comment.id)" in group[1]
    assert "cancel-in-progress: false" in text


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
    assert [p.name for p in paths] == ["closed.md", "proposal.md", "title.md"]
    for path in paths:
        text = path.read_text(encoding="ascii")
        used = set(re.findall(r"\{([a-z_]+)\}", text))
        assert used <= known | {"why"}, f"{path.name}: {used - known}"
    for name in ("proposal.md", "closed.md"):
        body = (ROOT / "templates" / "release" / name).read_text(encoding="ascii")
        assert "no model wrote any of it" in body, name
        assert body.rstrip().endswith("Decision record: {run_url}"), name


def test_release_template_closes_a_stale_proposal_and_keeps_one_in_progress() -> None:
    """The close job runs only when nothing is due and no release is in
    progress, and the ledger job runs after it too."""
    text = (ROOT / "templates" / "workflows" / "guild-release.yml").read_text(
        encoding="ascii"
    )
    assert "in_progress: ${{ steps.release.outputs.in_progress }}" in text
    assert (
        "if: needs.propose.outputs.due == 'false'"
        " && needs.propose.outputs.in_progress == 'false'"
    ) in text
    assert "guildkit release-close" in text
    assert 'gh issue close "$number" --reason "$(cat reason.txt)"' in text
    assert "--outcome declined" in text
    assert "needs: [propose, post, close]" in text
    assert (
        "if: always() && (needs.post.result == 'success'"
        " || needs.close.result == 'success')"
    ) in text
