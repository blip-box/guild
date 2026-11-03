"""The harness pin: one SDK version in both places, and it is the installed one."""

import re
import tomllib
from pathlib import Path

import claude_agent_sdk
from claude_agent_sdk._cli_version import __cli_version__

ROOT = Path(__file__).resolve().parents[1]


def test_agent_sdk_pin_is_one_version_and_installed() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = data["project"]["optional-dependencies"]["agents"]
    group = data["dependency-groups"]["test"]
    pins = {d for d in extra + group if d.startswith("claude-agent-sdk")}
    assert len(pins) == 1, pins
    match = re.fullmatch(r"claude-agent-sdk==(\d+\.\d+\.\d+)", pins.pop())
    assert match is not None
    assert match[1] == claude_agent_sdk.__version__
    # The SDK bundles the CLI; the handbook names the pair.
    handbook = (ROOT / "AGENTS.md").read_text(encoding="ascii")
    assert match[1] in handbook
    assert __cli_version__ in handbook
