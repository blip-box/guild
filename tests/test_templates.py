"""The workflow and comment templates keep their invariants."""

import re
from pathlib import Path

from guildkit import triage

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / "templates" / "workflows").glob("*.yml"))
COMMENTS = sorted((ROOT / "templates" / "comments").glob("*.md"))
KNOWN_PLACEHOLDERS = {
    "decision_url",
    "charter_url",
    "clause",
    "severity",
    "oracle",
    "missing_list",
}


def test_every_workflow_checks_the_kill_switch_first() -> None:
    """The first job of every template skips when GUILD_PAUSED is true."""
    assert len(WORKFLOWS) >= 4
    for path in WORKFLOWS:
        text = path.read_text(encoding="ascii")
        jobs = text.index("\njobs:\n")
        first = re.search(r"\n  ([a-z-]+):\n(.*?)\n    steps:", text[jobs:], re.S)
        assert first is not None, path.name
        assert "vars.GUILD_PAUSED != 'true'" in first[2], f"{path.name}: {first[1]}"


def test_every_workflow_pins_actions_and_holds_no_credentials() -> None:
    for path in WORKFLOWS:
        text = path.read_text(encoding="ascii")
        assert "permissions: {}" in text, path.name
        for match in re.finditer(r"uses: ([^@\n]+)@([0-9a-f]+) # v", text):
            assert len(match[2]) == 40, f"{path.name}: {match[0]}"
        assert re.search(r"uses: [^\n]+@(?![0-9a-f]{40} # v)", text) is None, path.name
        for match in re.finditer(
            r"uses: actions/checkout@[^\n]+\n((?:          [^\n]*\n)+)", text
        ):
            assert "persist-credentials: false" in match[1], path.name


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
